"""Tests for src.llm.providers: the time-budgeted Groq/Gemini clients.

No real network access or real sleeping - HTTP is faked (same pattern as
tests/test_generate_synthetic.py) and time.sleep is monkeypatched.
"""
from __future__ import annotations

import json

import pytest

from src.llm import providers as P


class FakeResponse:
    def __init__(self, status: int = 200, payload: dict | None = None, text: str = "", headers: dict | None = None) -> None:
        self.status_code = status
        self._payload = payload
        self.text = text or (json.dumps(payload) if payload is not None else "")
        self.headers = headers or {}

    def json(self) -> dict:
        if self._payload is None:
            raise ValueError("no json")
        return self._payload


class FakeSession:
    """Returns scripted responses in order; records every request including its timeout."""

    def __init__(self, responses: list) -> None:
        self.responses = list(responses)
        self.requests: list[dict] = []

    def post(self, url: str, headers: dict, json: dict, timeout: float):  # noqa: A002
        self.requests.append({"url": url, "headers": headers, "json": json, "timeout": timeout})
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def groq_ok(text: str) -> FakeResponse:
    return FakeResponse(200, {"choices": [{"message": {"content": text}}]})


def gemini_ok(text: str) -> FakeResponse:
    return FakeResponse(200, {"candidates": [{"content": {"parts": [{"text": text}]}}]})


class FakeClock:
    """A controllable clock: advances only when .advance() is called."""

    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


# ---------------------------- Deadline ---------------------------- #
def test_deadline_remaining_counts_down() -> None:
    clock = FakeClock()
    deadline = P.Deadline(total_seconds=10.0, clock=clock)
    assert deadline.remaining() == pytest.approx(10.0)
    clock.advance(4.0)
    assert deadline.remaining() == pytest.approx(6.0)


def test_deadline_expires_and_never_goes_negative() -> None:
    clock = FakeClock()
    deadline = P.Deadline(total_seconds=1.0, clock=clock)
    clock.advance(5.0)
    assert deadline.expired() is True
    assert deadline.remaining() == 0.0


# ---------------------------- bounded_sleep ---------------------------- #
def test_bounded_sleep_sleeps_when_within_budget(monkeypatch: pytest.MonkeyPatch) -> None:
    clock = FakeClock()
    deadline = P.Deadline(total_seconds=10.0, clock=clock)
    slept = []
    monkeypatch.setattr(P.time, "sleep", slept.append)
    P.bounded_sleep(deadline, 2.0)
    assert slept == [2.0]


def test_bounded_sleep_raises_when_exceeding_budget(monkeypatch: pytest.MonkeyPatch) -> None:
    clock = FakeClock()
    deadline = P.Deadline(total_seconds=1.0, clock=clock)
    monkeypatch.setattr(P.time, "sleep", lambda s: pytest.fail("should not sleep"))
    with pytest.raises(P.BudgetExceeded):
        P.bounded_sleep(deadline, 5.0)


# ---------------------------- BoundedGroqClient ---------------------------- #
def test_bounded_groq_client_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(P.time, "sleep", lambda s: None)
    deadline = P.Deadline(total_seconds=10.0, clock=FakeClock())
    session = FakeSession([groq_ok("hello")])
    client = P.BoundedGroqClient("key", deadline, session=session)
    assert client.generate("prompt") == "hello"


def test_bounded_groq_client_timeout_shrinks_to_remaining_budget() -> None:
    clock = FakeClock()
    deadline = P.Deadline(total_seconds=3.0, clock=clock)  # less than PER_CALL_TIMEOUT_S
    session = FakeSession([groq_ok("hello")])
    client = P.BoundedGroqClient("key", deadline, session=session)
    client.generate("prompt")
    assert session.requests[0]["timeout"] <= 3.0


def test_bounded_groq_client_raises_immediately_if_budget_already_spent() -> None:
    clock = FakeClock()
    deadline = P.Deadline(total_seconds=1.0, clock=clock)
    clock.advance(2.0)  # budget already gone
    session = FakeSession([])  # no response scripted - must not be called
    client = P.BoundedGroqClient("key", deadline, session=session)
    with pytest.raises(P.BudgetExceeded):
        client.generate("prompt")
    assert session.requests == []


def test_bounded_groq_client_gives_up_on_long_retry_after_instead_of_sleeping(monkeypatch: pytest.MonkeyPatch) -> None:
    """A 429 with a long Retry-After must abort via BudgetExceeded, not sleep through it."""
    clock = FakeClock()
    deadline = P.Deadline(total_seconds=2.0, clock=clock)
    monkeypatch.setattr(P.time, "sleep", lambda s: pytest.fail("should not really sleep"))
    session = FakeSession([FakeResponse(429, text="rate limited", headers={"Retry-After": "30"})])
    client = P.BoundedGroqClient("key", deadline, session=session, max_retries=3)
    with pytest.raises(P.BudgetExceeded):
        client.generate("prompt")


# ---------------------------- BoundedGeminiClient ---------------------------- #
def test_bounded_gemini_client_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(P.time, "sleep", lambda s: None)
    deadline = P.Deadline(total_seconds=10.0, clock=FakeClock())
    session = FakeSession([gemini_ok("hello")])
    client = P.BoundedGeminiClient("key", deadline, session=session)
    assert client.generate("prompt") == "hello"


def test_bounded_gemini_client_raises_immediately_if_budget_already_spent() -> None:
    clock = FakeClock()
    deadline = P.Deadline(total_seconds=1.0, clock=clock)
    clock.advance(2.0)
    session = FakeSession([])
    client = P.BoundedGeminiClient("key", deadline, session=session)
    with pytest.raises(P.BudgetExceeded):
        client.generate("prompt")
    assert session.requests == []
