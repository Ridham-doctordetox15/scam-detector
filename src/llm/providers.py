"""Time-budgeted Groq/Gemini clients for the explainer.

Reuses the HTTP + retry/backoff layer already built for synthetic data
generation (:mod:`src.preprocessing.generate_synthetic`), but that layer was
designed for offline batch generation, where sleeping through a long
``Retry-After`` wait or a slow exponential backoff is fine. An interactive
explainer step is not: it needs a short, predictable total time budget, after
which it must give up on the current provider (and, if the budget is spent,
skip straight to the next one or the template fallback) rather than sleep.

:class:`Deadline` is shared across both provider attempts in one explain()
call; :func:`bounded_sleep` raises :class:`BudgetExceeded` instead of
sleeping once ``seconds`` would overrun what's left, so the base client's own
retry loop aborts immediately instead of blocking.
"""
from __future__ import annotations

import time
from dataclasses import dataclass

import requests

from src.preprocessing.generate_synthetic import GeminiClient, GroqClient

# Per-HTTP-call timeout cap, independent of (and generally shorter than) the
# overall budget, so one slow request can't eat the whole thing by itself.
PER_CALL_TIMEOUT_S = 6.0
DEFAULT_TOTAL_BUDGET_S = 10.0
# Below this much remaining budget, don't bother attempting another provider -
# there isn't enough time left for a meaningful HTTP round trip.
MIN_ATTEMPT_BUDGET_S = 1.0


class BudgetExceeded(Exception):
    """Raised when honoring a retry/backoff wait would exceed the remaining time budget."""


@dataclass
class Deadline:
    """A shared wall-clock budget for one explain() call."""

    total_seconds: float = DEFAULT_TOTAL_BUDGET_S
    clock: callable = time.monotonic

    def __post_init__(self) -> None:
        self._end = self.clock() + self.total_seconds

    def remaining(self) -> float:
        return max(0.0, self._end - self.clock())

    def expired(self) -> bool:
        return self.remaining() <= 0.0


def bounded_sleep(deadline: Deadline, seconds: float) -> None:
    """Sleep, unless doing so would exceed ``deadline`` - then raise instead."""
    if seconds > deadline.remaining():
        raise BudgetExceeded(f"would need to sleep {seconds:.1f}s but only {deadline.remaining():.1f}s remain")
    time.sleep(seconds)


class BoundedGroqClient(GroqClient):
    """:class:`GroqClient` whose HTTP timeout shrinks to fit the remaining budget."""

    def __init__(self, api_key: str, deadline: Deadline, model: str | None = None, **kw) -> None:
        kw.setdefault("sleep", lambda s: bounded_sleep(deadline, s))
        kw.setdefault("max_retries", 1)
        super().__init__(api_key, model=model, **kw)
        self._deadline = deadline

    def _send(self, prompt: str) -> requests.Response:
        body = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 1.0,
            "max_completion_tokens": 4096,
            "response_format": {"type": "json_object"},
        }
        if self.model.startswith("openai/gpt-oss"):
            body["reasoning_effort"] = "low"
        timeout = min(PER_CALL_TIMEOUT_S, self._deadline.remaining())
        if timeout <= 0:
            raise BudgetExceeded("no time remaining for a Groq request")
        return self.session.post(
            self.URL, headers={"Authorization": f"Bearer {self.api_key}"}, json=body, timeout=timeout
        )


class BoundedGeminiClient(GeminiClient):
    """:class:`GeminiClient` whose HTTP timeout shrinks to fit the remaining budget."""

    def __init__(self, api_key: str, deadline: Deadline, model: str | None = None, **kw) -> None:
        kw.setdefault("sleep", lambda s: bounded_sleep(deadline, s))
        kw.setdefault("max_retries", 1)
        super().__init__(api_key, model=model, **kw)
        self._deadline = deadline

    def _send(self, prompt: str) -> requests.Response:
        gen_cfg: dict = {
            "temperature": 1.0,
            "maxOutputTokens": 8192,
            "responseMimeType": "application/json",
        }
        if "2.5-flash" in self.model:
            gen_cfg["thinkingConfig"] = {"thinkingBudget": 0}
        timeout = min(PER_CALL_TIMEOUT_S, self._deadline.remaining())
        if timeout <= 0:
            raise BudgetExceeded("no time remaining for a Gemini request")
        return self.session.post(
            self.URL.format(model=self.model),
            headers={"x-goog-api-key": self.api_key},
            json={"contents": [{"parts": [{"text": prompt}]}], "generationConfig": gen_cfg},
            timeout=timeout,
        )
