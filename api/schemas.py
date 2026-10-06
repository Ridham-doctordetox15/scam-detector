"""Request/response models for the public API.

Deliberately absent from every response: the classifier's scam probability
or margin, the URL analyzer's numeric score, and raw OCR confidence. Users
get verdict/risk bands and reasons, never a number that looks like a
calibrated probability (see results.md: the SVM confidence is a heuristic).
Links from the message are returned *defanged* (``hxxp://x[.]tk``) so no UI
can accidentally render them as clickable.
"""
from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

Verdict = Literal["safe", "suspicious", "scam"]
RiskLevel = Literal["low", "medium", "high"]

DISCLAIMER = (
    "Automated assessment - it can be wrong. Never share OTPs, PINs or passwords, and verify "
    "requests through the official app or number of the organisation, not the message."
)


class AnalyzeTextRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(description="The SMS / WhatsApp / email text to check.")


class URLFindingOut(BaseModel):
    url_defanged: str = Field(description="The link with its scheme and dots defanged so it is not clickable.")
    risk_band: RiskLevel
    reasons: list[str]


class OCROut(BaseModel):
    extracted_text: str = Field(description="Text read from the screenshot (returned to you only, never logged).")
    quality: Literal["good", "fair", "poor"]
    dark_mode: bool


class AnalyzeResponse(BaseModel):
    prediction_id: UUID = Field(description="Send this to POST /feedback. Remembered for 24 hours.")
    input_type: Literal["text", "image"]
    verdict: Verdict
    risk_level: RiskLevel
    red_flags: list[str]
    explanation: str
    what_to_do: list[str]
    matched_pattern: str | None = Field(description="Id of the closest known scam pattern, if a confident match.")
    url_findings: list[URLFindingOut]
    explainer_path: Literal["groq", "gemini", "template"]
    language: Literal["en", "hi", "hinglish"] = Field(
        description="Language of red_flags/explanation/what_to_do, detected from the message: English, Hindi "
                    "(Devanagari) or Hinglish (romanized Hindi). Use it to set the lang attribute and font.")
    classifier_model: str
    timings_ms: dict[str, float]
    ocr: OCROut | None = None
    disclaimer: str = DISCLAIMER


class FeedbackRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    prediction_id: UUID
    user_verdict: Literal["correct", "incorrect"]


class FeedbackResponse(BaseModel):
    status: Literal["saved"] = "saved"
    prediction_id: UUID


class ComponentHealth(BaseModel):
    ready: bool
    detail: str


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded", "unavailable"]
    components: dict[str, ComponentHealth]


class ErrorBody(BaseModel):
    code: str
    message: str
    request_id: str


class ErrorResponse(BaseModel):
    error: ErrorBody


def defang_url(url: str) -> str:
    """``http://sbi-kyc.tk/x`` -> ``hxxp://sbi-kyc[.]tk/x`` (standard threat-intel defanging)."""
    scheme, sep, rest = url.partition("://")
    if not sep:
        scheme, rest = "", url
    scheme = {"http": "hxxp", "https": "hxxps"}.get(scheme.lower(), scheme)
    host, slash, path = rest.partition("/")
    return f"{scheme}{sep}{host.replace('.', '[.]')}{slash}{path}"


def ocr_quality(mean_confidence: float) -> Literal["good", "fair", "poor"]:
    """Band OCR confidence instead of exposing the raw number."""
    if mean_confidence >= 0.75:
        return "good"
    if mean_confidence >= 0.5:
        return "fair"
    return "poor"
