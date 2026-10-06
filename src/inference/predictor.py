"""CPU inference for the fine-tuned scam classifier (quantized ONNX).

A model folder produced by the Phase 4 notebook holds three files::

    model_quantized.onnx      the int8 (or fp32) ONNX graph
    tokenizer.json            standalone fast-tokenizer file (no ``transformers`` needed at inference)
    inference_config.json     model name, max_length, decision threshold, label order

``ScamPredictor`` applies **exactly the text pipeline the model was trained on** (normalise, clean, mask,
lowercase; see :meth:`ScamPredictor.prepare`), tokenizes, runs the graph and returns the probability that
the message is a scam. The message is only ever data: it is tokenized, never interpreted.

The classifier's verdict is final. Downstream components (LLM explainer) may explain it but must not override it.

``onnxruntime`` and ``tokenizers`` are imported lazily, so the module (and the unit tests, which pass fake
objects) work without them.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

import numpy as np

from src.preprocessing.normalize import LEVEL_A, normalize_text
from src.preprocessing.preprocess import preprocess_text

MODEL_FILES = ("model_quantized.onnx", "model.onnx")     # first one found is used
TOKENIZER_FILE = "tokenizer.json"
CONFIG_FILE = "inference_config.json"
MAX_INPUT_CHARS = 10_000          # training dropped longer rows; also bounds regex work on hostile input
DEFAULT_BATCH_SIZE = 16
SCAM_INDEX = 1                    # label order is ["safe", "scam"]


@dataclass(frozen=True)
class InferenceConfig:
    """Settings saved next to the model by the training notebook."""

    model_name: str
    max_length: int
    threshold: float
    lowercase: bool = True
    labels: tuple[str, ...] = ("safe", "scam")
    pad_token_id: int = 0
    pad_token: str = "[PAD]"

    @classmethod
    def from_file(cls, path: Path) -> "InferenceConfig":
        """Read ``inference_config.json``; raises ``ValueError`` if a required field is missing or out of range."""
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        missing = [k for k in ("model_name", "max_length", "threshold") if k not in raw]
        if missing:
            raise ValueError(f"{path}: missing field(s) {missing}")
        cfg = cls(model_name=str(raw["model_name"]), max_length=int(raw["max_length"]), threshold=float(raw["threshold"]),
                  lowercase=bool(raw.get("lowercase", True)), labels=tuple(raw.get("labels", ("safe", "scam"))),
                  pad_token_id=int(raw.get("pad_token_id", 0)), pad_token=str(raw.get("pad_token", "[PAD]")))
        if cfg.max_length < 8:
            raise ValueError("max_length must be at least 8")
        if not 0.0 <= cfg.threshold <= 1.0:
            raise ValueError("threshold must be a probability in [0, 1]")
        if cfg.labels != ("safe", "scam"):
            raise ValueError(f"unexpected label order {cfg.labels}")
        return cfg


@dataclass(frozen=True)
class Prediction:
    """Result for one message."""

    scam_probability: float
    is_scam: bool
    threshold: float


def softmax_scam_probability(logits: np.ndarray) -> np.ndarray:
    """Numerically stable softmax over the last axis; returns the scam-class probability per row."""
    logits = np.asarray(logits, dtype=np.float64)
    if logits.ndim != 2 or logits.shape[1] != 2:
        raise ValueError(f"expected logits of shape (n, 2), got {logits.shape}")
    shifted = logits - logits.max(axis=1, keepdims=True)
    exp = np.exp(shifted)
    return exp[:, SCAM_INDEX] / exp.sum(axis=1)


class ScamPredictor:
    """Scam probability for messages, from an ONNX model on CPU.

    Args:
        session: An ``onnxruntime.InferenceSession``-like object (``get_inputs()`` and ``run()``).
        tokenizer: A ``tokenizers.Tokenizer``-like object (``encode_batch``, ``enable_truncation``, ``enable_padding``).
        config: Threshold and tokenizer settings.
        batch_size: Messages per forward pass.

    Use :meth:`load` to build one from a model folder.
    """

    def __init__(self, session: Any, tokenizer: Any, config: InferenceConfig, batch_size: int = DEFAULT_BATCH_SIZE) -> None:
        if batch_size < 1:
            raise ValueError("batch_size must be at least 1")
        self.session = session
        self.tokenizer = tokenizer
        self.config = config
        self.batch_size = batch_size
        self._input_names = {i.name for i in session.get_inputs()}
        self.tokenizer.enable_truncation(max_length=config.max_length)
        self.tokenizer.enable_padding(pad_id=config.pad_token_id, pad_token=config.pad_token)

    # ------------------------------------------------------------------ construction
    @classmethod
    def load(cls, model_dir: str | Path, batch_size: int = DEFAULT_BATCH_SIZE, threads: int | None = None) -> "ScamPredictor":
        """Load a model folder written by the training notebook.

        Raises:
            FileNotFoundError: If the ONNX file, tokenizer or config is missing.
        """
        model_dir = Path(model_dir)
        model_path = next((model_dir / n for n in MODEL_FILES if (model_dir / n).exists()), None)
        if model_path is None:
            raise FileNotFoundError(f"no ONNX model ({' or '.join(MODEL_FILES)}) in {model_dir}")
        for name in (TOKENIZER_FILE, CONFIG_FILE):
            if not (model_dir / name).exists():
                raise FileNotFoundError(f"{model_dir / name} not found")
        import onnxruntime as ort                      # lazy: heavy, and absent in unit tests
        from tokenizers import Tokenizer

        options = ort.SessionOptions()
        if threads:
            options.intra_op_num_threads = threads
        session = ort.InferenceSession(str(model_path), options, providers=["CPUExecutionProvider"])
        tokenizer = Tokenizer.from_file(str(model_dir / TOKENIZER_FILE))
        return cls(session, tokenizer, InferenceConfig.from_file(model_dir / CONFIG_FILE), batch_size)

    # ------------------------------------------------------------------ pipeline
    def prepare(self, text: str) -> str:
        """The training-time text pipeline: normalise (L3), clean, mask URLs/OTPs/phones, lowercase.

        Raises:
            ValueError: If ``text`` is not a string or is empty after cleaning.
        """
        if not isinstance(text, str):
            raise ValueError("message must be a string")
        normalised = normalize_text(text[:MAX_INPUT_CHARS], LEVEL_A)
        masked, _urls = preprocess_text(normalised)
        if not masked.strip():
            raise ValueError("message is empty after cleaning")
        return masked.lower() if self.config.lowercase else masked

    def _run(self, prepared: list[str]) -> np.ndarray:
        encodings = self.tokenizer.encode_batch(prepared)
        feed = {"input_ids": np.array([e.ids for e in encodings], dtype=np.int64),
                "attention_mask": np.array([e.attention_mask for e in encodings], dtype=np.int64)}
        if "token_type_ids" in self._input_names:
            feed["token_type_ids"] = np.zeros_like(feed["input_ids"])
        feed = {k: v for k, v in feed.items() if k in self._input_names}
        logits = self.session.run(None, feed)[0]
        return softmax_scam_probability(logits)

    def predict_proba(self, texts: Sequence[str]) -> np.ndarray:
        """Scam probability for each message (same order as the input)."""
        if isinstance(texts, str):
            raise TypeError("pass a list of messages, or use predict() for a single one")
        prepared = [self.prepare(t) for t in texts]
        out = [self._run(prepared[i:i + self.batch_size]) for i in range(0, len(prepared), self.batch_size)]
        return np.concatenate(out) if out else np.array([], dtype=np.float64)

    def predict(self, text: str) -> Prediction:
        """Probability and verdict for one message; ``is_scam`` is ``probability >= threshold``."""
        p = float(self.predict_proba([text])[0])
        return Prediction(scam_probability=p, is_scam=p >= self.config.threshold, threshold=self.config.threshold)
