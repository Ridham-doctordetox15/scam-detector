"""Tests for src.llm.rules: the fixed, documented verdict/risk_level table."""
from __future__ import annotations

import pytest

from src.llm import rules as R


# One test per cell of the documented table, plus the high-confidence override.
@pytest.mark.parametrize("is_scam, prob, url_band, expected_verdict, expected_risk", [
    # confident scam (>= 0.8): always scam/high, regardless of URL
    (True, 0.8, "none", "scam", "high"),
    (True, 0.95, "none", "scam", "high"),
    (True, 0.8, "low", "scam", "high"),
    (True, 0.85, "high", "scam", "high"),
    # scam, below high-confidence threshold
    (True, 0.6, "none", "scam", "medium"),
    (True, 0.6, "low", "scam", "medium"),
    (True, 0.6, "medium", "scam", "high"),
    (True, 0.6, "high", "scam", "high"),
    # not scam
    (False, 0.1, "none", "safe", "low"),
    (False, 0.1, "low", "safe", "low"),
    (False, 0.1, "medium", "suspicious", "medium"),
    (False, 0.1, "high", "suspicious", "high"),
])
def test_verdict_table(is_scam: bool, prob: float, url_band: str, expected_verdict: str, expected_risk: str) -> None:
    result = R.compute_verdict(is_scam, prob, url_band)
    assert result.verdict == expected_verdict
    assert result.risk_level == expected_risk


def test_high_confidence_boundary_is_inclusive() -> None:
    just_below = R.compute_verdict(True, 0.7999, "none")
    at_threshold = R.compute_verdict(True, 0.8, "none")
    assert just_below == R.VerdictResult("scam", "medium")
    assert at_threshold == R.VerdictResult("scam", "high")


def test_no_link_scam_still_reaches_high_risk() -> None:
    """A confident scam with no URL at all (e.g. digital arrest, OTP phone call) must reach high risk."""
    result = R.compute_verdict(True, 0.9, "none")
    assert result == R.VerdictResult("scam", "high")


def test_high_risk_url_escalates_even_when_classifier_says_safe() -> None:
    """Defense in depth: the URL analyzer must not be overridden by a safe text classification."""
    result = R.compute_verdict(False, 0.05, "high")
    assert result.verdict == "suspicious"
    assert result.risk_level == "high"


# ---------------------------- worst_url_band ---------------------------- #
def test_worst_url_band_empty_is_none() -> None:
    assert R.worst_url_band([]) == "none"


@pytest.mark.parametrize("bands, expected", [
    (["low"], "low"),
    (["low", "medium"], "medium"),
    (["low", "medium", "high"], "high"),
    (["high", "low"], "high"),
    (["medium", "medium"], "medium"),
])
def test_worst_url_band_picks_most_severe(bands: list[str], expected: str) -> None:
    assert R.worst_url_band(bands) == expected
