"""Tests for src.preprocessing.normalize, including that real scam signals are never removed."""
import pandas as pd
import pytest

from src.preprocessing import normalize as N
from src.training.feature_audit import SIGNAL_TERMS


# ------------------------------- quote markers -------------------------------- #
def test_leading_quote_markers_are_removed_but_the_text_stays() -> None:
    text = "> > hello there\n> > this is quoted\n>   more"
    assert N.strip_quote_markers(text) == "hello there\nthis is quoted\nmore"


def test_marker_after_wrote_and_standalone_markers() -> None:
    assert N.strip_quote_markers("Gordon Mohr wrote:> Users don't like passphrases") == "Gordon Mohr wrote: Users don't like passphrases"
    assert N.strip_quote_markers("a > b > c") == "a  b  c"


def test_angle_brackets_that_are_not_quote_markers_survive() -> None:
    assert N.strip_quote_markers("<a href='x'>click</a>") == "<a href='x'>click</a>"
    assert N.strip_quote_markers("go->there and x=>y") == "go->there and x=>y"
    assert N.strip_quote_markers("mail <bob@example.com> now") == "mail <bob@example.com> now"


# ------------------------------- reply boilerplate ------------------------------ #
def test_reply_attribution_original_message_and_forwarded_by_are_removed() -> None:
    a = N.strip_reply_boilerplate("On Sun, 11 Aug 2002, Gordon Mohr wrote: passphrases are hard")
    assert "wrote" not in a and "passphrases are hard" in a
    b = N.strip_reply_boilerplate("fyi - - - - - original message - - - - - from : smith , john")
    assert "original message" not in b and "fyi" in b and "from : smith , john" in b
    c = N.strip_reply_boilerplate("- - - - - - - - - - forwarded by vince j kaminski / hou / ect on 04 / 13 / 2001 09 : 55 pm the report")
    assert "forwarded" not in c and "kaminski" not in c and "the report" in c


def test_dash_rulers_are_removed_but_short_dashes_are_kept() -> None:
    assert "-----" not in N.strip_reply_boilerplate("part one ---------- part two")
    assert N.strip_reply_boilerplate("pre-approved loan -- apply") == "pre-approved loan -- apply"


# ---------------------------------- years / currency ---------------------------- #
@pytest.mark.parametrize("text, expected", [
    ("win tickets 21st May 2005", "win tickets 21st May <YEAR>"),
    ("on 10 / 13 / 2000 at noon", "on 10 / 13 / <YEAR> at noon"),
    ("valid till 31 Dec 2024", "valid till 31 Dec 2024"),
    ("call 0870 2005 123", "call 0870 <YEAR> 123"),
    ("order 20051", "order 20051"),
])
def test_years(text: str, expected: str) -> None:
    assert N.mask_years(text) == expected


@pytest.mark.parametrize("text, expected", [
    ("win £1000 now", "win <CUR> 1000 now"),
    ("Rs.500 cashback", "<CUR> 500 cashback"),
    ("Rs 1,50,000 loan", "<CUR> 1,50,000 loan"),
    ("INR 98,744.00 spent", "<CUR> 98,744.00 spent"),
    ("₹4500 credited", "<CUR> 4500 credited"),
    ("get $50 and €20", "get <CUR> 50 and <CUR> 20"),
    ("earn $$$ fast", "earn $$$ fast"),
    ("hours today", "hours today"),
    ("our team", "our team"),
])
def test_currency(text: str, expected: str) -> None:
    assert N.normalize_currency(text) == expected


def test_tokenized_spacing() -> None:
    assert N.fix_tokenized_spacing("hello , how are you ? fine .") == "hello, how are you? fine."
    assert N.fix_tokenized_spacing("no change here.") == "no change here."
    assert N.fix_tokenized_spacing("x = 3 . 5 units") == "x = 3. 5 units"


# ------------------------------------ row filters ------------------------------- #
def test_web_crawl_pipeline_and_enron_detection() -> None:
    assert N.is_web_crawl_row("URL: http://www.newsisfree.com/click/1\nDate: 2002-09-29T00:40:02+01:00 story")
    assert not N.is_web_crawl_row("Please visit URL: http://example.com to verify")          # not at the start
    assert not N.is_web_crawl_row("URL: http://example.com")                                # no Date:
    assert N.is_pipeline_notice("schedule crawler : hourahead failure start date : 1 / 19 / 02")
    assert N.is_enron_internal("re : meeting vince j kaminski enron")
    assert N.is_enron_internal("forward to john / hou / ect")
    assert N.is_enron_internal("hpl nominations for june")
    assert not N.is_enron_internal("your electricity bill is due, pay at the link")
    assert not N.is_enron_internal("select the correct option")                               # 'ect' only as a whole token


# ---------------------------------- configuration ------------------------------- #
def test_none_config_is_the_identity() -> None:
    text = "> URGENT!  win £1000 in 2005 ."
    assert N.normalize_text(text, N.NONE) == text
    assert not N.NONE.transforms_text and not N.NONE.drops_rows


def test_levels_are_cumulative() -> None:
    assert N.LEVEL_A.transforms_text and not N.LEVEL_A.drops_rows
    assert N.LEVEL_A_B1.drop_web_crawl and N.LEVEL_A_B1.drop_pipeline_notices and not N.LEVEL_A_B1.drop_enron_internal
    assert N.LEVEL_A_B1_B2.drop_enron_internal and N.LEVEL_A_B1_B2.strip_quote_markers


def test_normalize_text_full_example() -> None:
    raw = "On Sun, 8 Sep 2002, Tom wrote:\n> WIN £1000 now !\n> claim at 21st May 2005 ."
    out = N.normalize_text(raw, N.LEVEL_A)
    import re

    assert not re.search(r"(?m)^\s*>", out) and "wrote" not in out and "£" not in out
    assert "2005" not in out and "2002" not in out
    assert "WIN <CUR> 1000 now!" in out and "claim at 21st May <YEAR>." in out


def test_normalize_frame_drops_by_content_regardless_of_label_and_reports() -> None:
    df = pd.DataFrame({
        "text": ["URL: http://x.com/a\nDate: 2002-01-01 news", "enron report for vince j kaminski",
                 "spam mentioning enron shares", "urgent verify your account > now", "plain ok message"],
        "label": ["safe", "safe", "scam", "scam", "safe"],
    })
    out, rep = N.normalize_frame(df, N.LEVEL_A_B1_B2)
    assert out["text"].tolist() == ["urgent verify your account now", "plain ok message"]
    assert rep["dropped"]["web_crawl"] == {"total": 1, "safe": 1}
    assert rep["dropped"]["enron_internal"]["total"] == 2 and rep["dropped"]["enron_internal"]["scam"] == 1
    assert rep["rows_in"] == 5 and rep["rows_out"] == 2 and rep["changed"] == 1
    kept_a, _ = N.normalize_frame(df, N.LEVEL_A_B1)
    assert len(kept_a) == 4                                                              # Enron rows stay at B1


def test_normalize_frame_handles_frames_without_labels() -> None:
    out, rep = N.normalize_frame(pd.DataFrame({"text": ["a > b", "URL: http://x\nDate: y"]}), N.LEVEL_A_B1)
    assert len(out) == 1 and rep["dropped"]["web_crawl"] == {"total": 1}


# ------------------------- scam signals must survive normalisation -------------- #
SCAM_SENTENCES = [
    "URGENT! Your account will be blocked. Verify your KYC now: http://sbi-kyc.example.top/login",
    "Congratulations! You won a lottery prize of Rs.5,00,000. Claim now, pay a processing fee of Rs 500.",
    "> Dear customer, your OTP is 482915. Do not share it. Click the link to update details immediately.",
    "Your parcel is held at customs. Pay the refund fee at bit.ly/xyz within 24 hours or it will be cancelled.",
    "win £1000 cash prize 2005 call 0870 123 4567 free entry reply STOP",
    "On Mon, 3 Jun 2002, Bank wrote:\n> Your card is suspended. Login to verify password and pin at www.bank-secure.com",
]


@pytest.mark.parametrize("cfg", [N.LEVEL_A, N.LEVEL_A_B1, N.LEVEL_A_B1_B2])
@pytest.mark.parametrize("sentence", SCAM_SENTENCES)
def test_scam_signal_words_survive_every_level(cfg: N.NormalizeConfig, sentence: str) -> None:
    import re

    def signals(t: str) -> set[str]:
        words = {w for w in re.findall(r"[a-z]+", t.lower()) if w in SIGNAL_TERMS}
        # currency words are replaced by the <CUR> token, which stands in for them
        return {"cur" if w in ("rs", "inr") else w for w in words}

    out = N.normalize_text(sentence, cfg)
    assert signals(sentence) <= signals(out), (signals(sentence) - signals(out), out)


@pytest.mark.parametrize("cfg", [N.LEVEL_A, N.LEVEL_A_B1_B2])
def test_urls_phone_numbers_and_amount_digits_survive(cfg: N.NormalizeConfig) -> None:
    out = N.normalize_text("Call 9876543210 or visit http://a.b/c to pay Rs 500 today", cfg)
    assert "9876543210" in out and "http://a.b/c" in out and "500" in out


def test_scam_rows_are_not_dropped_by_the_non_enron_filters() -> None:
    df = pd.DataFrame({"text": SCAM_SENTENCES, "label": "scam"})
    out, rep = N.normalize_frame(df, N.LEVEL_A_B1_B2)
    assert len(out) == len(SCAM_SENTENCES) and rep["dropped"] == {}


def test_normalization_is_idempotent() -> None:
    for s in SCAM_SENTENCES:
        once = N.normalize_text(s, N.LEVEL_A_B1_B2)
        assert N.normalize_text(once, N.LEVEL_A_B1_B2) == once
