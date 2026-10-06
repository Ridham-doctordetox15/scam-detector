"""Feedback storage: a short-lived prediction cache plus a Supabase (PostgREST) writer.

Feedback rows never contain message text. When the user says a prediction
was correct/incorrect, the row stores the ``prediction_id``, their answer,
and the *non-text* facts about that prediction (verdict, risk level, input
type, classifier, explainer path, matched KB pattern id) taken from an
in-memory cache. The cache is what makes feedback useful without storing
text - and it is also why feedback for an unknown/expired id is rejected:
predictions are forgotten after 24 hours and on every restart (including a
free Space going to sleep).

Supabase is called over its REST API with ``httpx`` (no SDK dependency),
using a **secret** key server-side only. Secret keys (``sb_secret_...``) go
in the ``apikey`` header; a legacy ``service_role`` JWT additionally needs
``Authorization: Bearer``.
"""
from __future__ import annotations

import threading
import time
from collections import OrderedDict
from dataclasses import asdict, dataclass
from typing import Callable, Protocol

import httpx


@dataclass(frozen=True)
class PredictionRecord:
    """Non-text facts about one prediction, kept briefly for feedback enrichment."""

    predicted_verdict: str
    predicted_risk_level: str
    input_type: str
    classifier_model: str
    explainer_path: str
    matched_pattern: str | None


class PredictionCache:
    """Thread-safe TTL + size-bounded map of prediction_id -> :class:`PredictionRecord`."""

    def __init__(self, ttl_s: float, max_items: int, clock: Callable[[], float] = time.monotonic) -> None:
        self.ttl_s = ttl_s
        self.max_items = max_items
        self.clock = clock
        self._items: OrderedDict[str, tuple[float, PredictionRecord]] = OrderedDict()
        self._lock = threading.Lock()

    def put(self, prediction_id: str, record: PredictionRecord) -> None:
        with self._lock:
            self._items[prediction_id] = (self.clock() + self.ttl_s, record)
            self._items.move_to_end(prediction_id)
            while len(self._items) > self.max_items:
                self._items.popitem(last=False)

    def get(self, prediction_id: str) -> PredictionRecord | None:
        with self._lock:
            item = self._items.get(prediction_id)
            if item is None:
                return None
            expires, record = item
            if expires <= self.clock():
                del self._items[prediction_id]
                return None
            return record

    def __len__(self) -> int:
        with self._lock:
            return len(self._items)


class FeedbackError(RuntimeError):
    """Storing feedback failed (network error or a non-2xx response). Message has no user data."""


class FeedbackStore(Protocol):
    def save(self, row: dict) -> None: ...


def build_row(prediction_id: str, user_verdict: str, record: PredictionRecord) -> dict:
    """The exact row written to the ``feedback`` table (``created_at`` is set by the database)."""
    return {"prediction_id": prediction_id, "user_verdict": user_verdict, **asdict(record)}


class SupabaseFeedbackStore:
    """Upserts feedback rows into ``<url>/rest/v1/<table>`` (one row per prediction_id)."""

    def __init__(self, url: str, key: str, table: str = "feedback", timeout_s: float = 5.0,
                 transport: httpx.BaseTransport | None = None) -> None:
        self.endpoint = f"{url.rstrip('/')}/rest/v1/{table}"
        self._key = key
        self.timeout_s = timeout_s
        self._transport = transport

    def __repr__(self) -> str:  # never show the key
        return f"SupabaseFeedbackStore(endpoint={self.endpoint!r})"

    def _headers(self) -> dict[str, str]:
        headers = {
            "apikey": self._key,
            "Content-Type": "application/json",
            # Upsert on the unique prediction_id: a user changing their answer updates the row.
            "Prefer": "resolution=merge-duplicates,return=minimal",
        }
        if self._key.startswith("eyJ"):  # legacy service_role JWT
            headers["Authorization"] = f"Bearer {self._key}"
        return headers

    def save(self, row: dict) -> None:
        try:
            with httpx.Client(timeout=self.timeout_s, transport=self._transport) as client:
                response = client.post(self.endpoint, params={"on_conflict": "prediction_id"},
                                       headers=self._headers(), json=row)
        except httpx.HTTPError as exc:
            raise FeedbackError(f"feedback storage unreachable ({type(exc).__name__})") from None
        if response.status_code >= 300:
            raise FeedbackError(f"feedback storage returned HTTP {response.status_code}")
