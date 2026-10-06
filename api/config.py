"""API settings, read once from environment variables.

Every value has a safe default so the app starts with no configuration at
all (text analysis with the template explainer, no feedback storage, no
cross-origin access). Secrets (Supabase key) are held in fields excluded from
``repr`` so they never end up in a log line or traceback.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping

from src.ocr.validate import max_image_bytes

DEFAULT_TFIDF_MODEL_DIR = Path("models/baseline_phase4")
DEFAULT_ONNX_MODEL_DIR = Path("models/distilbert")
DEFAULT_CHROMA_DIR = Path("chroma_db")


def _bool(env: Mapping[str, str], key: str, default: bool) -> bool:
    raw = env.get(key)
    if raw is None or not raw.strip():
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _int(env: Mapping[str, str], key: str, default: int, minimum: int = 0) -> int:
    try:
        value = int(env.get(key, "") or default)
    except ValueError:
        return default
    return value if value >= minimum else default


def _float(env: Mapping[str, str], key: str, default: float, minimum: float = 0.0) -> float:
    try:
        value = float(env.get(key, "") or default)
    except ValueError:
        return default
    return value if value > minimum else default


def _supabase_base_url(raw: str) -> str:
    """Project base URL. Accepts the REST URL too (``.../rest/v1``) - an easy thing to paste from
    the dashboard - since the feedback store appends ``/rest/v1/<table>`` itself."""
    url = raw.strip().rstrip("/")
    if url.endswith("/rest/v1"):
        url = url[: -len("/rest/v1")]
    return url


@dataclass(frozen=True)
class Settings:
    """All tunables for the API. Build with :meth:`from_env`."""

    # Input limits
    max_text_chars: int = 5000
    max_image_bytes: int = 5 * 1024 * 1024
    max_json_body_bytes: int = 64 * 1024

    # Per-client rate limits (requests per minute)
    rate_text_per_min: int = 20
    rate_image_per_min: int = 6
    rate_feedback_per_min: int = 30
    # Number of trusted reverse proxies in front of the app (Hugging Face: 1).
    # 0 = use the socket peer address and ignore X-Forwarded-For entirely.
    trusted_proxy_hops: int = 0

    # CORS: exact origins allowed to call the API from a browser. Empty = none.
    cors_origins: tuple[str, ...] = ()

    # Time and concurrency (the free CPU host has 2 vCPUs)
    text_timeout_s: float = 25.0
    image_timeout_s: float = 45.0
    queue_wait_s: float = 10.0
    max_concurrent_analyses: int = 2
    max_concurrent_ocr: int = 1

    # Models
    use_onnx_classifier: bool = False
    tfidf_model_dir: Path = DEFAULT_TFIDF_MODEL_DIR
    onnx_model_dir: Path = DEFAULT_ONNX_MODEL_DIR
    chroma_dir: Path = DEFAULT_CHROMA_DIR
    load_models: bool = True
    warmup: bool = True
    verify_artifacts: bool = True

    # Feedback (Supabase)
    supabase_url: str = ""
    supabase_key: str = field(default="", repr=False)
    supabase_table: str = "feedback"
    supabase_timeout_s: float = 5.0
    prediction_cache_ttl_s: float = 24 * 3600.0
    prediction_cache_max: int = 10_000

    @property
    def feedback_configured(self) -> bool:
        return bool(self.supabase_url.strip() and self.supabase_key.strip())

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "Settings":
        """Read settings from ``env`` (default: ``os.environ``). Invalid numbers fall back to defaults."""
        env = os.environ if env is None else env
        origins = tuple(o.strip().rstrip("/") for o in env.get("CORS_ORIGINS", "").split(",") if o.strip())
        return cls(
            max_text_chars=_int(env, "MAX_TEXT_CHARS", 5000, minimum=1),
            max_image_bytes=max_image_bytes(),
            rate_text_per_min=_int(env, "RATE_LIMIT_TEXT_PER_MIN", 20),
            rate_image_per_min=_int(env, "RATE_LIMIT_IMAGE_PER_MIN", 6),
            rate_feedback_per_min=_int(env, "RATE_LIMIT_FEEDBACK_PER_MIN", 30),
            trusted_proxy_hops=_int(env, "TRUSTED_PROXY_HOPS", 0),
            cors_origins=origins,
            text_timeout_s=_float(env, "TEXT_TIMEOUT_S", 25.0),
            image_timeout_s=_float(env, "IMAGE_TIMEOUT_S", 45.0),
            queue_wait_s=_float(env, "QUEUE_WAIT_S", 10.0),
            max_concurrent_analyses=_int(env, "MAX_CONCURRENT_ANALYSES", 2, minimum=1),
            max_concurrent_ocr=_int(env, "MAX_CONCURRENT_OCR", 1, minimum=1),
            use_onnx_classifier=_bool(env, "USE_ONNX_CLASSIFIER", False),
            tfidf_model_dir=Path(env.get("TFIDF_MODEL_DIR") or DEFAULT_TFIDF_MODEL_DIR),
            onnx_model_dir=Path(env.get("ONNX_MODEL_DIR") or DEFAULT_ONNX_MODEL_DIR),
            chroma_dir=Path(env.get("CHROMA_DIR") or DEFAULT_CHROMA_DIR),
            load_models=_bool(env, "LOAD_MODELS", True),
            warmup=_bool(env, "WARMUP", True),
            verify_artifacts=_bool(env, "VERIFY_ARTIFACTS", True),
            supabase_url=_supabase_base_url(env.get("SUPABASE_URL") or ""),
            supabase_key=(env.get("SUPABASE_KEY") or "").strip(),
            supabase_table=(env.get("SUPABASE_FEEDBACK_TABLE") or "feedback").strip(),
        )
