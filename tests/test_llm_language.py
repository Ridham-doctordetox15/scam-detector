"""Tests for src.llm.language: the simple language-detection heuristic."""
from __future__ import annotations

import pytest

from src.llm import language as L


@pytest.mark.parametrize("text", [
    "Your OTP for login is 384921, do not share this with anyone.",
    "Congratulations, you have won a cash prize! Call now to claim.",
])
def test_plain_english_detected_as_en(text: str) -> None:
    assert L.detect_language(text) == "en"


@pytest.mark.parametrize("text", [
    "आपका ओटीपी 384921 है, इसे किसी के साथ साझा न करें।",
    "यह संदेश सुरक्षित लगता है।",
])
def test_devanagari_detected_as_hi(text: str) -> None:
    assert L.detect_language(text) == "hi"


@pytest.mark.parametrize("text", [
    "aapka kyc update nahi hua hai, turant update karein",
    "yeh message scam jaisa lagta hai, paise mat bhejein",
])
def test_romanized_hindi_detected_as_hinglish(text: str) -> None:
    assert L.detect_language(text) == "hinglish"


def test_single_hinglish_word_is_not_enough() -> None:
    """One common word alone (which may also appear in English-adjacent text) shouldn't flip the result."""
    assert L.detect_language("hai") == "en"  # below _HINGLISH_MIN_HITS


def test_devanagari_takes_priority_over_romanized_check() -> None:
    mixed = "आपका account hai"
    assert L.detect_language(mixed) == "hi"


def test_empty_text_defaults_to_en() -> None:
    assert L.detect_language("") == "en"


def test_language_names_cover_all_language_values() -> None:
    for lang in ("en", "hi", "hinglish"):
        assert lang in L.LANGUAGE_NAMES
