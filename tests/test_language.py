"""Tests for src.preprocessing.language."""
import pytest

from src.preprocessing.language import detect_language, is_likely_hinglish


@pytest.mark.parametrize(
    "text, expected",
    [
        ("आपका खाता बंद हो जाएगा", "hi"),
        ("உங்கள் கணக்கு முடக்கப்பட்டது", "ta"),
        ("మీ ఖాతా నిలిపివేయబడింది", "te"),
        ("আপনার অ্যাকাউন্ট বন্ধ", "bn"),
        ("Your KYC is pending. आज ही update करें", "hi"),     # mixed script -> Indic wins
        ("Aapka account band ho jayega, kya aap abhi verify karo", "hinglish_guess"),
        ("Your account has been blocked. Click the link to verify.", "en"),
        ("Привет, как дела", "other"),
        ("", "en"),
        ("12345 !!!", "en"),
    ],
)
def test_detect_language(text: str, expected: str) -> None:
    assert detect_language(text) == expected


def test_single_marker_is_not_enough_for_hinglish() -> None:
    # One marker word could be a name or quotation; need >= 2 distinct hits.
    assert not is_likely_hinglish("Please call Bhai for the parcel")
    assert detect_language("Please call Bhai for the parcel") == "en"


def test_repeated_marker_counts_once() -> None:
    assert not is_likely_hinglish("hai hai hai hai")


def test_english_collisions_are_not_markers() -> None:
    # 'to', 'me', 'main', 'par', 'ho', 'is', 'hi' are common English words/abbreviations.
    assert detect_language("hi to me main par ho is") == "en"
