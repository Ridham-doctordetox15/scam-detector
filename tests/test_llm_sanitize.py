"""Tests for src.llm.sanitize: masking and capping LLM-authored text."""
from __future__ import annotations

from src.llm import sanitize as S


def test_url_in_llm_text_is_masked() -> None:
    result = S.sanitize_text("This is safe, visit http://example-verify.tk for details.")
    assert "http://example-verify.tk" not in result
    assert "<URL>" in result


def test_phone_number_in_llm_text_is_masked() -> None:
    result = S.sanitize_text("Call 9876543210 to confirm.")
    assert "9876543210" not in result
    assert "<PHONE>" in result


def test_otp_like_code_in_llm_text_is_masked() -> None:
    result = S.sanitize_text("Your otp is 384921, enter it now.")
    assert "384921" not in result


def test_combined_injection_example_is_fully_masked() -> None:
    """The exact style of manipulated response called out for this phase."""
    result = S.sanitize_text("Safe, call 9876543210 or visit http://example-verify.tk")
    assert "9876543210" not in result
    assert "http://example-verify.tk" not in result


def test_clean_text_is_left_unchanged() -> None:
    text = "This message shows signs of a fake KYC scam."
    assert S.sanitize_text(text) == text


def test_text_longer_than_max_is_truncated() -> None:
    text = "a" * 1000
    result = S.sanitize_text(text, max_length=50)
    assert len(result) <= 50
    assert result.endswith("...")


def test_sanitize_list_caps_item_count() -> None:
    items = [f"flag {i}" for i in range(20)]
    result = S.sanitize_list(items, max_items=6)
    assert len(result) == 6


def test_sanitize_list_caps_each_item_length() -> None:
    items = ["x" * 500]
    result = S.sanitize_list(items, max_item_length=50)
    assert len(result[0]) <= 50


def test_sanitize_list_masks_each_item() -> None:
    items = ["call 9876543210 now", "visit http://bad-example.tk"]
    result = S.sanitize_list(items)
    assert not any("9876543210" in r or "http://bad-example.tk" in r for r in result)
