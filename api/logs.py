"""Privacy-safe structured (JSON-lines) logging for the API.

Rules enforced here, not just by convention:

* API log records carry only **allowlisted** fields (:data:`SAFE_FIELDS`):
  ids, route, status, durations, counts, verdict labels, error codes and
  exception *type names*. Anything else passed via ``extra=`` is dropped.
* Messages from the API itself are fixed event names - never formatted
  with request data.
* Tracebacks are never emitted (they can contain exception messages, and
  exception messages can contain user text): only ``exc_type`` is kept.
* Third-party loggers that could echo request details are raised to WARNING.

Never logged: message text, OCR text, URLs from messages, upload filenames,
client IP addresses, user agents, API keys.
"""
from __future__ import annotations

import json
import logging
import sys
import time
from typing import IO, Any

API_LOGGER_NAME = "api"

SAFE_FIELDS = frozenset({
    "event", "request_id", "method", "route", "status", "duration_ms",
    "input_type", "input_chars", "image_bytes", "verdict", "risk_level", "explainer_path",
    "classifier_model", "timings_ms", "error_code", "exc_type", "component", "ready",
    "seconds", "prediction_known", "limit_bucket", "retry_after_s", "status_code",
})

# Libraries that log per-request details at INFO (URLs, headers) or chatty internals.
_QUIET_LOGGERS = ("httpx", "httpcore", "urllib3", "uvicorn.access", "chromadb", "sentence_transformers",
                  "huggingface_hub", "transformers", "multipart", "PIL", "python_multipart")


class JsonFormatter(logging.Formatter):
    """One JSON object per line. API records keep only allowlisted fields."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(record.created)) + "Z",
            "level": record.levelname,
            "logger": record.name,
        }
        if record.name == API_LOGGER_NAME or record.name.startswith(API_LOGGER_NAME + "."):
            payload["event"] = record.msg if isinstance(record.msg, str) else "event"
            for key in SAFE_FIELDS:
                if key != "event" and key in record.__dict__:
                    payload[key] = record.__dict__[key]
        else:
            # Library/src logs: their own fixed-format messages (e.g. "Loaded 512 OpenPhish URLs").
            payload["message"] = record.getMessage()
        if record.exc_info and record.exc_info[0] is not None:
            payload["exc_type"] = record.exc_info[0].__name__
        return json.dumps(payload, ensure_ascii=False, default=str)


def configure_logging(stream: IO[str] | None = None, level: int = logging.INFO) -> logging.Handler:
    """Route all logging through one JSON handler on ``stream`` (default stdout). Idempotent."""
    root = logging.getLogger()
    for handler in list(root.handlers):
        if getattr(handler, "_scam_api_handler", False):
            root.removeHandler(handler)
    handler = logging.StreamHandler(stream or sys.stdout)
    handler.setFormatter(JsonFormatter())
    handler._scam_api_handler = True  # type: ignore[attr-defined]
    root.addHandler(handler)
    root.setLevel(level)
    for name in _QUIET_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)
    return handler


def get_logger() -> logging.Logger:
    return logging.getLogger(API_LOGGER_NAME)


def log_event(event: str, level: int = logging.INFO, **fields: Any) -> None:
    """Log a fixed event name with allowlisted fields only (others are silently dropped)."""
    safe = {k: v for k, v in fields.items() if k in SAFE_FIELDS and k != "event"}
    get_logger().log(level, event, extra=safe)
