"""Fixed, documented rules for the final verdict and risk level.

These rules run in code and are never influenced by the LLM - the explainer
narrates them, it cannot change them. This is the module that decides what
"safe" / "suspicious" / "scam" and "low" / "medium" / "high" mean for this
product.

Rule (in order):
1. A confident scam call (``scam_probability >= HIGH_CONFIDENCE_THRESHOLD``)
   is always ``scam`` / ``high``, with or without a URL - many scams (digital
   arrest, fake bank OTP calls, sextortion) contain no link at all, so URL
   evidence must never be required to reach the top tier.
2. Otherwise, a classifier "scam" call is ``scam`` / ``medium``, escalated to
   ``scam`` / ``high`` if the URL analyzer's worst finding is medium or high
   risk (both signals agreeing).
3. A classifier "safe" call stays ``safe`` / ``low`` unless the URL analyzer's
   worst finding is medium or high risk, in which case it is escalated to
   ``suspicious`` (medium or high risk respectively) - the URL analyzer exists
   specifically to catch brand-impersonation/phishing links the text
   classifier alone can miss (defense in depth), so a high-risk link is never
   waved through as "safe".
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Verdict = Literal["safe", "suspicious", "scam"]
RiskLevel = Literal["low", "medium", "high"]
UrlBand = Literal["none", "low", "medium", "high"]

HIGH_CONFIDENCE_THRESHOLD = 0.8


@dataclass(frozen=True)
class VerdictResult:
    verdict: Verdict
    risk_level: RiskLevel


def worst_url_band(url_bands: list[UrlBand]) -> UrlBand:
    """The most severe band among a message's URLs, or ``"none"`` if it has none."""
    if not url_bands:
        return "none"
    order = {"low": 0, "medium": 1, "high": 2}
    return max(url_bands, key=lambda b: order[b])


def compute_verdict(
    is_scam: bool, scam_probability: float, url_band: UrlBand
) -> VerdictResult:
    """The fixed verdict/risk_level rule table. See the module docstring."""
    if is_scam and scam_probability >= HIGH_CONFIDENCE_THRESHOLD:
        return VerdictResult("scam", "high")
    if is_scam:
        if url_band in ("medium", "high"):
            return VerdictResult("scam", "high")
        return VerdictResult("scam", "medium")
    # not scam, per the classifier
    if url_band == "high":
        return VerdictResult("suspicious", "high")
    if url_band == "medium":
        return VerdictResult("suspicious", "medium")
    return VerdictResult("safe", "low")
