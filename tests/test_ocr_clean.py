"""Tests for src.ocr.clean: chrome/timestamp removal, line joining, URL repair.

The main invariant: UI noise is removed only as whole segments/lines, so
message content that merely *contains* a UI word or a time is never lost.
"""
from __future__ import annotations

import pytest

from src.ocr.clean import (
    clean_line,
    clean_ocr_text,
    clean_paragraphs,
    fix_url_spacing,
    is_noise_line,
    is_time_like,
    join_lines,
)


# ------------------------------ noise lines ------------------------------ #
@pytest.mark.parametrize("line", [
    "10:45", "10:45 AM", "9:05 pm", "10.45 am", "10 : 45", "21:07", "10:42 AM ✓✓", "10:43 AM vv",
    "Delivered", "Read", "Seen", "Sent", "Reply", "Forward", "Copy", "Type a message", "Text message",
    "Today", "Yesterday", "Monday", "Delivered 10:45 AM", "Read 9:12 pm", "Yesterday, 9:30 PM",
    "Mon 10:45", "3 Oct", "Oct 3, 2026", "12/03/2026", "VoLTE 4G 85%", "4G", "85%", "LTE",
    "last seen today at 10:45", "✓✓", "", "   ",
])
def test_noise_lines_are_detected(line: str) -> None:
    assert is_noise_line(line)


@pytest.mark.parametrize("line", [
    "Reply STOP to unsubscribe",
    "Your OTP is 482913",
    "482913",  # a lone number could be an OTP - never dropped
    "Read the terms carefully",
    "Meet me today at 10:30",
    "Delivered to your address tomorrow",
    "Copy this code: 5521",
    "Your account will be BLOCKED within 24 hours",
    "Hi",
    "Oct offer: 50% off",
    "Sent Rs 500 to your account",
])
def test_content_lines_are_kept(line: str) -> None:
    assert not is_noise_line(line)


@pytest.mark.parametrize("seg, expected", [
    ("10:42 AM", True), ("10:42", True), ("9.15 pm", True), ("10:43 AM ✓✓", True), ("10:43 AM vv", True),
    ("at 10:42", False), ("1pm", False), ("10", False), ("482913", False),
])
def test_is_time_like(seg: str, expected: bool) -> None:
    assert is_time_like(seg) is expected


def test_clean_line_strips_trailing_time_with_ticks_only() -> None:
    assert clean_line("Is this real? 10:39 AM ✓✓") == "Is this real?"
    assert clean_line("Is this real? ✓✓") == "Is this real?"
    # A time without receipt ticks may be content: kept.
    assert clean_line("See you at 10:30") == "See you at 10:30"


# ------------------------------ line joining ------------------------------ #
def test_join_lines_uses_spaces_for_wrapped_words() -> None:
    assert join_lines(["Your account will be", "blocked today."]) == "Your account will be blocked today."


def test_join_lines_glues_url_wrapped_mid_link() -> None:
    assert join_lines(["Update: http://sbi-kyc-", "verify.tk/update"]) == "Update: http://sbi-kyc-verify.tk/update"
    assert join_lines(["visit http://example.top/", "pay?id=5"]) == "visit http://example.top/pay?id=5"
    assert join_lines(["go to www.bank-", "secure.in now"]) == "go to www.bank-secure.in now"


def test_join_lines_url_continuation_without_trailing_separator() -> None:
    assert join_lines(["Pay here http://courier", "-fee.top/pay"]) == "Pay here http://courier-fee.top/pay"
    assert join_lines(["Pay here http://courier-fee", ".top/pay"]) == "Pay here http://courier-fee.top/pay"


def test_join_lines_does_not_glue_words_after_a_complete_url() -> None:
    assert join_lines(["visit http://bit.ly/abc", "Click now"]) == "visit http://bit.ly/abc Click now"
    # A second URL on the next line is a new token, not a continuation.
    assert join_lines(["a http://x.top/", "http://y.top"]) == "a http://x.top/ http://y.top"


def test_join_lines_keeps_real_hyphen_and_glues() -> None:
    assert join_lines(["a well-", "known brand"]) == "a well-known brand"


def test_join_lines_skips_blank_lines() -> None:
    assert join_lines(["", "hello", "  ", "world"]) == "hello world"


# ------------------------------ URL spacing ------------------------------ #
@pytest.mark.parametrize("raw, fixed", [
    ("http: //sbi-kyc.tk", "http://sbi-kyc.tk"),
    ("https : / / bank.in/x", "https://bank.in/x"),
    ("www . paytm-kyc.top", "www.paytm-kyc.top"),
    ("visit amazon-offer . com now", "visit amazon-offer.com now"),
    ("courier-fee. top/pay", "courier-fee.top/pay"),
])
def test_fix_url_spacing(raw: str, fixed: str) -> None:
    assert fix_url_spacing(raw) == fixed


def test_fix_url_spacing_leaves_sentences_alone() -> None:
    text = "Call me later. In the evening."
    assert fix_url_spacing(text) == text


# ------------------------------ paragraphs ------------------------------ #
def test_clean_paragraphs_full_whatsapp_like_screen() -> None:
    paragraphs = [
        [["10:45", "VoLTE 4G 85%"]],               # status bar
        [["+91 98XXX XXX21"]],                      # header (kept: sender info)
        [["Today"]],                                # date chip
        [["Congratulations! Aapka number lucky"], ["draw mein select hua hai."], ["10:40 AM"]],
        [["Aap kaun bol rahe ho?"], ["10:43 AM", "vv"]],
        [["Type a message"]],
    ]
    assert clean_paragraphs(paragraphs) == (
        "+91 98XXX XXX21\n\n"
        "Congratulations! Aapka number lucky draw mein select hua hai.\n\n"
        "Aap kaun bol rahe ho?"
    )


def test_clean_paragraphs_drops_trailing_time_box_but_keeps_inline_time() -> None:
    # The bubble timestamp is its own OCR box at the end of the line.
    assert clean_paragraphs([[["Meet me at 10:30", "10:31 AM"]]]) == "Meet me at 10:30"
    # A time inside the text box is content.
    assert clean_paragraphs([[["Lunch at 1pm tomorrow?"]]]) == "Lunch at 1pm tomorrow?"


def test_clean_paragraphs_drops_trailing_receipt_box() -> None:
    assert clean_paragraphs([[["Who is this?", "Delivered"]]]) == "Who is this?"
    assert clean_paragraphs([[["Who is this?", "✓✓"]]]) == "Who is this?"


def test_clean_paragraphs_keeps_single_word_content_box() -> None:
    # "Read" as the only box on a line is chrome, but as part of a sentence it stays.
    assert clean_paragraphs([[["Please", "read"]]]) == "Please read"


def test_clean_paragraphs_returns_empty_for_all_chrome() -> None:
    assert clean_paragraphs([[["10:45", "VoLTE 4G 85%"]], [["Today"]], [["Type a message"]]]) == ""
    assert clean_paragraphs([]) == ""


def test_clean_ocr_text_plain_text_entry_point() -> None:
    raw = "10:45 VoLTE 4G 85%\n\nYour parcel is on hold.\nPay here: http: //indiapost-\nredeliver.top/pay\n10:38 AM\n\nType a message"
    assert clean_ocr_text(raw) == "Your parcel is on hold. Pay here: http://indiapost-redeliver.top/pay"


def test_clean_keeps_devanagari_text() -> None:
    assert clean_ocr_text("आपका बैंक खाता बंद हो जाएगा।\n10:42 AM") == "आपका बैंक खाता बंद हो जाएगा।"


# ------------------------- OCR character fixes ------------------------- #
from src.ocr.clean import normalize_ocr_chars, repair_ocr_urls  # noqa: E402


@pytest.mark.parametrize("raw, fixed", [
    ("BLOCKED within २४ hours", "BLOCKED within 24 hours"),
    ("Rs ४९९९", "Rs 4999"),
    ("VoLTE ४G ८५%", "VoLTE 4G 85%"),
    ("Update immediatelyः", "Update immediately:"),
    ("httpःllsite", "http:llsite"),
    ("दुःख", "दुःख"),  # a real visarga inside a Hindi word is kept
    ("बंद हो जाएगा| तुरंत", "बंद हो जाएगा। तुरंत"),
    ("बंद हो जाएगा |", "बंद हो जाएगा।"),
    ("a | b", "a | b"),  # a pipe in Latin text is kept
])
def test_normalize_ocr_chars(raw: str, fixed: str) -> None:
    assert normalize_ocr_chars(raw) == fixed


@pytest.mark.parametrize("raw, fixed", [
    # Exact misreads observed from EasyOCR on the generated samples.
    ("Update: http:lIsbi-kyc-verify.tklupdate", "Update: http://sbi-kyc-verify.tk/update"),
    ("http:llsbi-kyc-verify.tklupdate", "http://sbi-kyc-verify.tk/update"),
    ("returned: http:llindiapost-redeliver toplpay", "returned: http://indiapost-redeliver.top/pay"),
    ("http:llindiapost-redeliver.top/pay", "http://indiapost-redeliver.top/pay"),
    ("httpillsbi-kyc.tk", "http://sbi-kyc.tk"),
    ("https:IIbank-verify.in/login", "https://bank-verify.in/login"),
    ("http: /x-y.top", "http://x-y.top"),
])
def test_repair_ocr_urls_fixes_observed_misreads(raw: str, fixed: str) -> None:
    assert repair_ocr_urls(raw) == fixed


@pytest.mark.parametrize("text", [
    "http://sbi-kyc-verify.tk/update",           # already correct
    "https://www.myvi.in/offers",
    "http://shop.colab.in",                       # ".co" + "lab.in" is a longer valid host
    "http://bit.ly/abc Click now",
    "Visit http://abc.com in the evening",        # host already has a dot: no TLD join
    "I will call later in the evening",           # no URL at all
    "The httpd server is down",
])
def test_repair_ocr_urls_leaves_valid_text_alone(text: str) -> None:
    assert repair_ocr_urls(text) == text


def test_clean_paragraphs_repairs_wrapped_mangled_url() -> None:
    paragraphs = [[["Pay here: http:llcourier-"], ["fee.toplpay"], ["10:38 AM"]]]
    assert clean_paragraphs(paragraphs) == "Pay here: http://courier-fee.top/pay"


def test_clean_paragraphs_drops_status_bar_with_devanagari_digits() -> None:
    assert clean_paragraphs([[["10:45", "VOLTE ४G ८५%"]], [["Hi"]]]) == "Hi"


@pytest.mark.parametrize("raw, fixed", [
    ("lunch tomorrow at Ipm?", "lunch tomorrow at 1pm?"),
    ("Rs I000 only", "Rs 1000 only"),
    ("within I2 hours", "within 12 hours"),
    ("OTP 4829l3", "OTP 482913"),
    ("I am coming", "I am coming"),           # "I am" must survive
    ("I will call", "I will call"),
    ("Illegal login", "Illegal login"),
    ("bit.ly/l2abc", "bit.ly/l2abc"),         # short-link codes are case-sensitive: untouched
    ("http:l1sbi.tk", "http:l1sbi.tk"),       # URL-ish token: left for repair_ocr_urls
])
def test_normalize_ocr_chars_fixes_misread_one(raw: str, fixed: str) -> None:
    assert normalize_ocr_chars(raw) == fixed
