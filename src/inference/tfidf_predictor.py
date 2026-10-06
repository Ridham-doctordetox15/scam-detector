"""CPU inference for the deployed TF-IDF + Linear SVM classifier.

results.md's Phase 4 "Deployment recommendation" ships this model as
**primary** - it ties or wins on every accuracy metric measured, wins
decisively on leave-one-source-out generalisation, and is roughly two orders
of magnitude smaller/faster than the ONNX DistilBERT alternative
(:mod:`src.inference.predictor`), which stays available as a documented
secondary option, not the default.

A model folder (default ``models/baseline_phase4``) holds ``<model>.joblib``
- a dict of ``{vectorizer, clf, config, threshold, max_chars}`` written by
:mod:`src.training.baseline`.

``LinearSVC`` has no calibrated ``predict_proba`` - only a real-valued
``decision_function`` margin relative to the tuned decision threshold.
``scam_probability`` here is ``sigmoid(margin - threshold)``: a bounded,
monotonic **heuristic confidence** for risk tiering, not a calibrated
probability (results.md explicitly recommends never showing a raw
probability to users - only risk bands derived from the fixed threshold).
``is_scam`` uses the raw margin against the threshold directly, not the
sigmoid, so it exactly reproduces the model's tuned operating point.
"""
from __future__ import annotations

import math
from pathlib import Path
from typing import Sequence

import joblib
import numpy as np

from src.inference.predictor import Prediction
from src.preprocessing.normalize import LEVEL_A, normalize_text
from src.preprocessing.preprocess import preprocess_text

DEFAULT_MODEL_DIR = Path("models/baseline_phase4")
DEFAULT_MODEL_NAME = "svm"
# Matches src.training.baseline.MAX_CHARS - the training-time truncation,
# applied to the already normalised+masked text, same as at training time.
MAX_CHARS = 2_000


def sigmoid(x: float) -> float:
    """Numerically stable logistic sigmoid."""
    if x >= 0:
        z = math.exp(-x)
        return 1.0 / (1.0 + z)
    z = math.exp(x)
    return z / (1.0 + z)


class TfidfPredictor:
    """Scam confidence from the deployed TF-IDF + Linear SVM model.

    Args:
        vectorizer: A fitted scikit-learn vectorizer (``.transform``).
        clf: A fitted classifier with ``.decision_function``.
        threshold: The tuned decision threshold (see :mod:`src.training.baseline`).

    Use :meth:`load` to build one from a model folder.
    """

    def __init__(self, vectorizer, clf, threshold: float) -> None:
        self.vectorizer = vectorizer
        self.clf = clf
        self.threshold = threshold

    @classmethod
    def load(cls, model_dir: str | Path = DEFAULT_MODEL_DIR, model_name: str = DEFAULT_MODEL_NAME) -> "TfidfPredictor":
        """Load a model folder written by :mod:`src.training.baseline`.

        Raises:
            FileNotFoundError: If the ``.joblib`` artifact is missing.
        """
        path = Path(model_dir) / f"{model_name}.joblib"
        if not path.exists():
            raise FileNotFoundError(f"no TF-IDF model at {path}")
        art = joblib.load(path)
        return cls(art["vectorizer"], art["clf"], float(art["threshold"]))

    def prepare(self, text: str) -> str:
        """The training-time text pipeline: normalise (LEVEL_A), clean, mask URLs/OTPs/phones, truncate.

        Raises:
            ValueError: If ``text`` is not a string or is empty after cleaning.
        """
        if not isinstance(text, str):
            raise ValueError("message must be a string")
        normalised = normalize_text(text, LEVEL_A)
        masked, _urls = preprocess_text(normalised)
        if not masked.strip():
            raise ValueError("message is empty after cleaning")
        return masked[:MAX_CHARS]

    def _margins(self, prepared: list[str]) -> np.ndarray:
        return np.asarray(self.clf.decision_function(self.vectorizer.transform(prepared)), dtype=np.float64)

    def predict_proba(self, texts: Sequence[str]) -> np.ndarray:
        """Heuristic scam confidence for each message (same order as the input)."""
        if isinstance(texts, str):
            raise TypeError("pass a list of messages, or use predict() for a single one")
        prepared = [self.prepare(t) for t in texts]
        margins = self._margins(prepared)
        return np.array([sigmoid(m - self.threshold) for m in margins], dtype=np.float64)

    def predict(self, text: str) -> Prediction:
        """Heuristic confidence and verdict for one message.

        ``is_scam`` is the raw margin vs. threshold (not the sigmoid), so it
        exactly reproduces the tuned operating point measured in results.md.
        """
        prepared = self.prepare(text)
        margin = float(self._margins([prepared])[0])
        return Prediction(
            scam_probability=sigmoid(margin - self.threshold),
            is_scam=margin >= self.threshold,
            threshold=self.threshold,
        )
