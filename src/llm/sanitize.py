"""Sanitize LLM-generated explainer text before it reaches a user.

Even with prompt-injection defenses, a manipulated or hallucinating LLM could
put a fresh URL, phone number, or OTP-like code into its own explanation
text - e.g. steering a user toward a malicious link under the guise of
"safety advice". Every piece of LLM-authored text is masked with the same
``<URL>``/``<OTP>``/``<PHONE>`` tokens used on untrusted input (see
:mod:`src.preprocessing.preprocess`), then length- and list-capped, so
nothing the LLM writes can hand a user a live link or number.
"""
from __future__ import annotations

from src.preprocessing.preprocess import mask_text

MAX_TEXT_LENGTH = 500
MAX_ITEM_LENGTH = 200
MAX_LIST_ITEMS = 6

_TRUNCATION_SUFFIX = "..."


def _cap_length(text: str, max_length: int) -> str:
    if len(text) <= max_length:
        return text
    return text[: max_length - len(_TRUNCATION_SUFFIX)].rstrip() + _TRUNCATION_SUFFIX


def sanitize_text(text: str, max_length: int = MAX_TEXT_LENGTH) -> str:
    """Mask any URL/OTP/phone-like content in ``text`` and cap its length."""
    masked, _urls = mask_text(text)
    return _cap_length(masked, max_length)


def sanitize_list(items: list[str], max_items: int = MAX_LIST_ITEMS, max_item_length: int = MAX_ITEM_LENGTH) -> list[str]:
    """Mask and length-cap each item, and cap how many items survive."""
    return [sanitize_text(item, max_item_length) for item in items[:max_items]]
