"""Tests for src.preprocessing.preprocess (cleaning, masking, dedup, split)."""
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.preprocessing import preprocess as pp
from src.preprocessing.schema import COLUMNS, make_frame


# =============================== clean_text ================================= #
def test_clean_collapses_whitespace_and_strips() -> None:
    assert pp.clean_text("  hello \t\n  world  \r\n") == "hello world"


def test_clean_normalises_unicode_to_nfc() -> None:
    assert pp.clean_text("é") == "é"           # e + combining acute -> é


def test_clean_drops_invisible_marks_but_keeps_zwj_zwnj() -> None:
    assert pp.clean_text("﻿hi​ there­") == "hi there"
    assert "‍" in pp.clean_text("क्‍ष")       # ZWJ inside an Indic conjunct
    assert "‌" in pp.clean_text("a‌b")


def test_clean_turns_control_chars_into_spaces() -> None:
    assert pp.clean_text("a\x00b\x07c") == "a b c"


def test_clean_keeps_case_and_punctuation() -> None:
    assert pp.clean_text("URGENT!!! Click NOW.") == "URGENT!!! Click NOW."


def test_clean_is_idempotent_and_handles_empty() -> None:
    text = "  Mixed   text \n here "
    assert pp.clean_text(pp.clean_text(text)) == pp.clean_text(text)
    assert pp.clean_text("") == "" and pp.clean_text("   \n ") == ""


# ================================ mask_urls ================================= #
@pytest.mark.parametrize(
    "text, masked, urls",
    [
        ("Visit http://fastcash.in/abc now", "Visit <URL> now", ["http://fastcash.in/abc"]),
        ("Go to HTTPS://Example.COM/a?b=1&c=2 today", "Go to <URL> today", ["HTTPS://Example.COM/a?b=1&c=2"]),
        ("see www.claim-prize.top for details", "see <URL> for details", ["www.claim-prize.top"]),
        ("click bit.ly/3xYz9 fast", "click <URL> fast", ["bit.ly/3xYz9"]),
        ("bank site sbi.co.in is real", "bank site <URL> is real", ["sbi.co.in"]),
        ("port http://10.0.0.1:8080/login ok", "port <URL> ok", ["http://10.0.0.1:8080/login"]),
    ],
)
def test_mask_urls_variants(text: str, masked: str, urls: list[str]) -> None:
    assert pp.mask_urls(text) == (masked, urls)


def test_mask_urls_keeps_trailing_punctuation_out_of_the_url() -> None:
    assert pp.mask_urls("Open http://a.com/x.") == ("Open <URL>.", ["http://a.com/x"])
    assert pp.mask_urls("(see http://a.com/x)") == ("(see <URL>)", ["http://a.com/x"])
    assert pp.mask_urls("Is it http://a.com/x?") == ("Is it <URL>?", ["http://a.com/x"])


def test_mask_urls_multiple_in_order() -> None:
    masked, urls = pp.mask_urls("a http://one.com b www.two.in c bit.ly/x")
    assert masked == "a <URL> b <URL> c <URL>"
    assert urls == ["http://one.com", "www.two.in", "bit.ly/x"]


def test_mask_urls_stops_at_devanagari_danda() -> None:
    masked, urls = pp.mask_urls("यहाँ क्लिक करें http://a.com/x। धन्यवाद")
    assert urls == ["http://a.com/x"] and "<URL>।" in masked


@pytest.mark.parametrize(
    "text",
    [
        "mail me at user@gmail.com please",   # e-mail addresses are not URLs
        "e.g. this and i.e. that",
        "Rs.500 debited on 12.05.2024",
        "Mr.Sharma called",
        "No links here at all",
        "",
    ],
)
def test_mask_urls_leaves_non_urls_alone(text: str) -> None:
    assert pp.mask_urls(text) == (text, [])


def test_mask_urls_is_idempotent_on_masked_text() -> None:
    assert pp.mask_urls("already <URL> masked") == ("already <URL> masked", [])


def test_extract_urls() -> None:
    assert pp.extract_urls("x http://a.com y") == ["http://a.com"]
    assert pp.extract_urls("nothing") == []


# ================================ mask_otps ================================= #
@pytest.mark.parametrize(
    "text, expected",
    [
        ("Your OTP is 482915. Do not share.", "Your OTP is <OTP>. Do not share."),
        ("482915 is your OTP for login", "<OTP> is your OTP for login"),
        ("OTP: 4521", "OTP: <OTP>"),
        ("OTP-123456 valid 5 min", "OTP-<OTP> valid 5 min"),
        ("otp 7391", "otp <OTP>"),
        ("Use one time password 604815 to pay", "Use one time password <OTP> to pay"),
        ("Verification code 123 456", "Verification code <OTP>"),
        ("Your security code: 88231907", "Your security code: <OTP>"),
        ("आपका ओटीपी 482915 है", "आपका ओटीपी <OTP> है"),
        ("OTP 111222 and OTP 333444", "OTP <OTP> and OTP <OTP>"),
        ("(OTP 482915)", "(OTP <OTP>)"),
        ("Aapka OTP hai 482915 kisi ko na batayein", "Aapka OTP hai <OTP> kisi ko na batayein"),
    ],
)
def test_mask_otps_masks_codes_next_to_keywords(text: str, expected: str) -> None:
    assert pp.mask_otps(text) == expected


@pytest.mark.parametrize(
    "text",
    [
        "Your order 482915 has shipped",                      # bare number
        "Pincode 110001 Delhi",
        "Balance Rs 5000 available",
        "OTP is valid for 10 minutes. Ref 482915",            # number in a later sentence
        "Never share OTP with anyone. Balance 5000",           # sentence break before number
        "OTP 12345678901",                                     # 11 digits is not an OTP
        "OTP 123",                                             # too short
        "hotpot 1234 special",                                 # 'otp' inside a word
        "",
    ],
)
def test_mask_otps_leaves_other_numbers(text: str) -> None:
    assert pp.mask_otps(text) == text


def test_mask_otps_idempotent() -> None:
    once = pp.mask_otps("OTP 482915")
    assert pp.mask_otps(once) == once == "OTP <OTP>"


# ================================ mask_phones =============================== #
@pytest.mark.parametrize(
    "text",
    [
        "Call +91 98765 43210 now",
        "Call +91-9876543210 now",
        "Call +919876543210 now",
        "Call 919876543210 now",
        "Call 09876543210 now",
        "Call 98765-43210 now",
        "Call 98765 43210 now",
        "Call 9876543210 now",
        "Call 987 654 3210 now",
        "Call 98765.43210 now",
        "Call 1800-11-4000 now",
        "Call 1800 123 4567 now",
        "Call 18001234567 now",
        "Call 1860 500 1234 now",
        "Call 011-23456789 now",
        "Call 022 23456789 now",
        "Call +91 11 23456789 now",
        "Call +44 7911 123456 now",
    ],
)
def test_mask_phones_positive(text: str) -> None:
    assert pp.mask_phones(text) == "Call <PHONE> now"


def test_mask_phones_keeps_trailing_punctuation_and_multiple_numbers() -> None:
    assert pp.mask_phones("Ring 9876543210, or 8123456789.") == "Ring <PHONE>, or <PHONE>."
    assert pp.mask_phones("(9876543210)") == "(<PHONE>)"


@pytest.mark.parametrize(
    "text",
    [
        "Rs 1,50,000 credited",
        "Amount Rs. 98765 only",
        "Txn 12345678901234 done",          # 14-digit id
        "Order 9876543210123 shipped",      # 13 digits: too long for a phone
        "Date 2023-10-15 noted",
        "Call 5876543210 now",              # Indian mobiles start with 6-9
        "OTP 482915 sent",
        "PIN 110001",
        "Ref 4321 123456 noted",            # 4+6 digits without a leading 0/+91 is not a landline
        "Get +50 100 points",
        "",
    ],
)
def test_mask_phones_negative(text: str) -> None:
    assert pp.mask_phones(text) == text


def test_mask_phones_not_inside_longer_tokens() -> None:
    assert pp.mask_phones("ID AB9876543210 ok") == "ID AB9876543210 ok"


# ================================ mask_text ================================= #
def test_mask_text_order_url_digits_are_not_phones() -> None:
    masked, urls = pp.mask_text("Pay at http://pay.example.com/9876543210 or call 9876543210")
    assert masked == "Pay at <URL> or call <PHONE>"
    assert urls == ["http://pay.example.com/9876543210"]


def test_mask_text_all_three_together() -> None:
    masked, urls = pp.mask_text(
        "URGENT: OTP 482915 for a12. Call +91 98765 43210 or visit bit.ly/x9 now"
    )
    assert masked == "URGENT: OTP <OTP> for a12. Call <PHONE> or visit <URL> now"
    assert urls == ["bit.ly/x9"]


def test_mask_text_otp_not_swallowed_by_phone_pattern() -> None:
    assert pp.mask_text("OTP 98765432")[0] == "OTP <OTP>"     # 8 digits next to a keyword


def test_preprocess_text_cleans_then_masks() -> None:
    masked, urls = pp.preprocess_text("  Call   9876543210 \n at http://a.com/x ")
    assert masked == "Call <PHONE> at <URL>" and urls == ["http://a.com/x"]


def test_preprocess_frame_adds_columns_and_drops_empty() -> None:
    df = make_frame(["Call 9876543210 http://a.com", "   ", "plain text"], ["scam", "safe", "safe"], source="s")
    out = pp.preprocess_frame(df)
    assert len(out) == 2
    assert out.loc[0, "text"] == "Call <PHONE> <URL>"
    assert out.loc[0, "text_raw"] == "Call 9876543210 http://a.com"
    assert out.loc[0, "urls"] == ["http://a.com"]
    assert out.loc[1, "urls"] == []
    assert set(COLUMNS) <= set(out.columns)


def test_make_id_is_stable_short_and_distinct() -> None:
    assert pp.make_id("abc") == pp.make_id("abc")
    assert len(pp.make_id("abc")) == 12
    assert pp.make_id("abc") != pp.make_id("abd")


# ============================ exact duplicates ============================== #
def _frame(rows: list[tuple[str, str, bool]], source: str = "s") -> pd.DataFrame:
    """Build a masked frame (text, label, is_synthetic) with ids."""
    df = make_frame([r[0] for r in rows], [r[1] for r in rows], source=source)
    df["is_synthetic"] = [r[2] for r in rows]
    df["id"] = df["text"].map(pp.make_id)
    return df


def test_dedup_key_ignores_case_and_whitespace() -> None:
    assert pp.dedup_key("Hello   WORLD\n") == pp.dedup_key("hello world")


def test_exact_duplicates_found_after_masking() -> None:
    raw = make_frame(["Call 98765 43210 now", "call 91234 56789   NOW"], ["scam", "scam"], source="s")
    out, stats = pp.remove_exact_duplicates(pp.preprocess_frame(raw))
    assert len(out) == 1 and stats == {"removed": 1, "conflict_rows": 0}


def test_exact_dedup_prefers_real_over_synthetic() -> None:
    df = _frame([("Win a prize now", "scam", True), ("win a prize NOW", "scam", False)])
    out, _ = pp.remove_exact_duplicates(df)
    assert len(out) == 1 and not out.loc[0, "is_synthetic"]


def test_exact_dedup_drops_label_conflicts_entirely() -> None:
    df = _frame([("Same text", "scam", False), ("same text", "safe", False), ("other", "safe", False)])
    out, stats = pp.remove_exact_duplicates(df)
    assert out["text"].tolist() == ["other"]
    assert stats == {"removed": 0, "conflict_rows": 2}


def test_exact_dedup_empty_frame() -> None:
    out, stats = pp.remove_exact_duplicates(_frame([]))
    assert out.empty and stats["removed"] == 0


# ============================ near duplicates =============================== #
TEMPLATE = (
    "schedule crawler hourahead failure start date {d} hour {h} the process failed to complete "
    "please check the scheduling system and rerun the job before the next cycle begins"
)
OTHER = [
    "hi are we still meeting for lunch tomorrow at the usual place near the office",
    "your electricity bill is overdue pay now to avoid disconnection tonight call the officer",
    "congratulations you have won a lottery prize claim your reward by sending a small fee",
    "the quarterly report is attached please review the numbers and share your comments soon",
    "aapka parcel customs mein ruka hai kripya fee bharein warna wapas bhej diya jayega",
]


def _corpus(n_template: int = 6) -> list[tuple[str, str, bool]]:
    rows = [(TEMPLATE.format(d=f"1 / {i} / 02", h=i), "safe", False) for i in range(1, n_template + 1)]
    rows += [(t, "scam" if i % 2 else "safe", False) for i, t in enumerate(OTHER)]
    return rows


def test_near_duplicates_collapse_template_siblings() -> None:
    out, stats = pp.remove_near_duplicates(_frame(_corpus()))
    templates = [t for t in out["text"] if t.startswith("schedule crawler")]
    assert len(templates) == 1
    assert len(out) == 1 + len(OTHER)
    assert stats["removed"] == 5 and stats["clusters"] == 1 and stats["max_cluster"] == 6
    assert stats["removed_real"] == 5 and stats["removed_synthetic"] == 0


def test_near_duplicates_prefer_real_row() -> None:
    rows = _corpus(4)
    rows[0] = (rows[0][0], rows[0][1], True)             # first sibling is synthetic
    out, stats = pp.remove_near_duplicates(_frame(rows))
    kept = out[out["text"].str.startswith("schedule crawler")]
    assert len(kept) == 1 and not kept.iloc[0]["is_synthetic"]
    assert stats["removed_synthetic"] == 1


def test_near_duplicates_drop_mixed_label_clusters_entirely() -> None:
    rows = [(TEMPLATE.format(d="1 / 1 / 02", h=1), "safe", False),
            (TEMPLATE.format(d="1 / 2 / 02", h=2), "scam", False)] + [(t, "safe", False) for t in OTHER]
    out, stats = pp.remove_near_duplicates(_frame(rows))
    assert not out["text"].str.startswith("schedule crawler").any()
    assert stats["mixed_label_rows"] == 2 and stats["removed"] == 2


def test_near_duplicates_keep_distinct_texts() -> None:
    df = _frame([(t, "safe", False) for t in OTHER])
    out, stats = pp.remove_near_duplicates(df)
    assert len(out) == len(OTHER) and stats["removed"] == 0


def test_near_duplicates_digits_do_not_hide_duplicates() -> None:
    # differ only in numbers -> same after digit collapsing
    a = "your account 123456 has been debited with rs 5000 on 12 / 05 / 2024 for order 778899 thank you"
    b = "your account 654321 has been debited with rs 7500 on 01 / 06 / 2024 for order 112233 thank you"
    out, _ = pp.remove_near_duplicates(_frame([(a, "safe", False), (b, "safe", False)] + [(t, "safe", False) for t in OTHER]))
    assert len(out) == 1 + len(OTHER)


@pytest.mark.parametrize("n", [0, 1])
def test_near_duplicates_tiny_inputs(n: int) -> None:
    df = _frame([("only one text here", "safe", False)][:n])
    out, stats = pp.remove_near_duplicates(df)
    assert len(out) == n and stats["removed"] == 0


def test_similar_pairs_and_sensitivity_are_monotonic() -> None:
    texts = [t for t, _, _ in _corpus()]
    rows, cols, sims = pp.similar_pairs(texts, 0.8)
    assert (rows < cols).all() and (sims >= 0.8).all() and len(rows) == 15   # C(6,2) template pairs
    sens = pp.near_duplicate_sensitivity(texts, (0.8, 0.9, 0.95))
    assert sens[0.8] >= sens[0.9] >= sens[0.95] >= 0 and sens[0.9] == 5


def test_cross_near_duplicates_flags_exact_near_and_leaves_unrelated() -> None:
    ref = [t for t, _, _ in _corpus()]
    new = [
        ref[0],                                            # exact
        TEMPLATE.format(d="9 / 9 / 09", h=9),              # near
        "completely different message about a football match tonight",
    ]
    dup, sim = pp.cross_near_duplicates(new, ref, 0.9)
    assert dup.tolist() == [True, True, False]
    assert sim[1] >= 0.9 and sim[2] < 0.5


def test_cross_near_duplicates_empty_inputs() -> None:
    dup, sim = pp.cross_near_duplicates([], ["a b c"], 0.9)
    assert len(dup) == 0 and len(sim) == 0
    dup, _ = pp.cross_near_duplicates(["x y z"], [], 0.9)
    assert dup.tolist() == [False]


# ================================== split =================================== #
def _big_frame(seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    parts = []
    spec = [("uci", 400, 0.12, False), ("hf", 400, 0.40, False), ("synthetic_llm", 200, 0.50, True), ("tiny", 3, 0.5, False)]
    for source, n, p, synth in spec:
        labels = np.where(rng.random(n) < p, "scam", "safe").tolist()
        df = make_frame([f"{source} message number {i}" for i in range(n)], labels, source=source)
        df["is_synthetic"] = synth
        parts.append(df)
    df = pd.concat(parts, ignore_index=True)
    df["id"] = df["text"].map(pp.make_id)
    return df


def test_split_sizes_are_70_15_15() -> None:
    df = _big_frame()
    train, val, test = pp.split_dataset(df)
    n = len(df)
    assert len(train) + len(val) + len(test) == n
    assert len(test) == round(0.15 * n) and len(val) == round(0.15 * n)
    assert len(train) == n - len(test) - len(val)


def test_test_set_is_100_percent_real_and_synthetic_lands_in_train_and_val() -> None:
    df = _big_frame()
    train, val, test = pp.split_dataset(df)
    assert not test["is_synthetic"].any()
    assert train["is_synthetic"].sum() > 0 and val["is_synthetic"].sum() > 0
    assert train["is_synthetic"].sum() + val["is_synthetic"].sum() == df["is_synthetic"].sum()
    # synthetic share is (approximately) equal in train and val
    assert abs(train["is_synthetic"].mean() - val["is_synthetic"].mean()) < 0.04


def test_split_is_stratified_by_label() -> None:
    df = _big_frame()
    train, val, test = pp.split_dataset(df)
    scam = lambda part: (part["label"] == "scam").mean()  # noqa: E731
    # test is real-only, so it mirrors the *real* class balance; train/val mirror the rest
    assert abs(scam(test) - scam(df[~df["is_synthetic"]])) < 0.03
    rest = pd.concat([train, val])
    assert abs(scam(train) - scam(rest)) < 0.03
    assert abs(scam(val) - scam(rest)) < 0.03


def test_split_is_stratified_by_source() -> None:
    df = _big_frame()
    train, val, test = pp.split_dataset(df)
    share = lambda part, src: (part["source"] == src).mean()  # noqa: E731
    real = df[~df["is_synthetic"]]
    assert abs(share(test, "uci") - share(real, "uci")) < 0.04
    rest = pd.concat([train, val])
    for src in ("uci", "hf", "synthetic_llm"):
        assert abs(share(train, src) - share(rest, src)) < 0.04
        assert abs(share(val, src) - share(rest, src)) < 0.04


def test_split_rejects_datasets_too_small_to_split() -> None:
    tiny = _big_frame().iloc[:3]
    with pytest.raises(ValueError, match="too small"):
        pp.split_dataset(tiny)


def test_split_is_disjoint_and_complete() -> None:
    df = _big_frame()
    train, val, test = pp.split_dataset(df)
    ids = train["id"].tolist() + val["id"].tolist() + test["id"].tolist()
    assert len(ids) == len(set(ids)) == len(df)
    pp.check_split_integrity(train, val, test)         # must not raise


def test_split_is_deterministic_and_seed_dependent() -> None:
    df = _big_frame()
    a1, _, _ = pp.split_dataset(df, seed=7)
    a2, _, _ = pp.split_dataset(df, seed=7)
    b, _, _ = pp.split_dataset(df, seed=8)
    assert a1["id"].tolist() == a2["id"].tolist()
    assert a1["id"].tolist() != b["id"].tolist()


def test_split_handles_tiny_strata_without_crashing() -> None:
    df = _big_frame()
    assert (df["source"] == "tiny").sum() == 3
    train, val, test = pp.split_dataset(df)              # must not raise
    assert len(train) + len(val) + len(test) == len(df)


def test_split_rejects_bad_fractions_and_too_few_real_rows() -> None:
    df = _big_frame()
    with pytest.raises(ValueError, match="sum to 1"):
        pp.split_dataset(df, fractions=(0.5, 0.2, 0.2))
    mostly_synth = df.copy()
    mostly_synth["is_synthetic"] = True
    mostly_synth.loc[:30, "is_synthetic"] = False
    with pytest.raises(ValueError, match="more real rows"):
        pp.split_dataset(mostly_synth)


def test_integrity_check_catches_violations() -> None:
    df = _big_frame()
    train, val, test = pp.split_dataset(df)
    bad_test = test.copy()
    bad_test.loc[bad_test.index[0], "is_synthetic"] = True
    with pytest.raises(AssertionError, match="synthetic"):
        pp.check_split_integrity(train, val, bad_test)
    leaked = pd.concat([test, train.iloc[:1]])
    with pytest.raises(AssertionError, match="id overlap"):
        pp.check_split_integrity(train, val, leaked)
    same_text = train.iloc[:1].copy()
    same_text["id"] = "different-id"
    with pytest.raises(AssertionError, match="exact-text"):
        pp.check_split_integrity(train, val, pd.concat([test, same_text]))


def test_leakage_audit_reports_all_boundaries() -> None:
    rows = _corpus()
    df = _frame(rows)
    train, val, test = df.iloc[:6], df.iloc[6:8], df.iloc[8:]
    report = pp.leakage_audit(train, val, test, 0.9)
    assert set(report) == {"val_vs_train", "test_vs_train", "test_vs_val"}
    assert all({"near_duplicate_rows", "max_similarity"} <= set(v) for v in report.values())


def test_trim_removes_heldout_rows_that_resemble_training_rows() -> None:
    df = _frame(_corpus())
    train = df.iloc[:3]                                   # template siblings 1-3
    val = df.iloc[3:5]                                    # siblings 4-5  -> near-dups of train
    test = df.iloc[[5, 6, 7]]                             # sibling 6 -> near-dup; two unrelated rows
    tr, va, te, trimmed = pp.trim_cross_split_leakage(train, val, test, 0.9)
    assert len(tr) == 3                                   # train is never trimmed
    assert va.empty and trimmed["val"] == 2
    assert len(te) == 2 and trimmed["test"] == 1
    assert pp.leakage_audit(tr, va, te, 0.9)["test_vs_train"]["near_duplicate_rows"] == 0


def test_trim_is_a_noop_on_clean_splits() -> None:
    df = _frame([(t, "safe", False) for t in OTHER])
    tr, va, te, trimmed = pp.trim_cross_split_leakage(df.iloc[:3], df.iloc[3:4], df.iloc[4:], 0.9)
    assert (len(tr), len(va), len(te)) == (3, 1, 1) and trimmed == {"val": 0, "test": 0}


def test_leakage_audit_detects_a_planted_duplicate() -> None:
    df = _frame(_corpus())
    train = df.iloc[:5]
    test = df.iloc[5:6]                                   # sibling of train rows
    report = pp.leakage_audit(train, df.iloc[6:8], test, 0.9)
    assert report["test_vs_train"]["near_duplicate_rows"] == 1


# ============================ end-to-end pipeline =========================== #
def _write_combined(path: Path) -> None:
    """300 diverse rows (240 real + 60 synthetic), each with a phone number and a URL."""
    rng = np.random.default_rng(1)
    # Random letter-only words: the near-duplicate step collapses digits, so "w1", "w2" would be identical.
    vocab = ["".join(rng.choice(list("abcdefghijklmnopqrstuvwxyz"), 6)) for _ in range(500)]
    texts, labels, synth, sources = [], [], [], []
    for i in range(300):
        real = i < 240
        body = " ".join(rng.choice(vocab, 14))
        texts.append(f"{body} call 98765 4{i:04d} http://x{i % 7}.com/p{i}")
        labels.append("scam" if rng.random() < 0.4 else "safe")
        synth.append(not real)
        sources.append("hf_phishing_texts" if real else "synthetic_llm")
    df = make_frame(texts, labels, source="x")
    df["source"], df["is_synthetic"] = sources, synth
    df.to_parquet(path, index=False)


def test_run_preprocessing_end_to_end(tmp_path: Path) -> None:
    src = tmp_path / "combined.parquet"
    _write_combined(src)
    result = pp.run_preprocessing(src, tmp_path, seed=3)

    for name in ("train", "val", "test", "deduplicated"):
        assert (tmp_path / f"{name}.parquet").exists()
    report = json.loads((tmp_path / "split_report.json").read_text(encoding="utf-8"))
    assert report["input_rows"] == 300
    assert report["rows_after_dedup"] == len(result.deduplicated)
    assert sum(s["rows"] for s in report["splits"].values()) == report["rows_after_dedup"]
    assert report["splits"]["test"]["synthetic"] == 0

    test = pd.read_parquet(tmp_path / "test.parquet")
    assert not test["is_synthetic"].any()
    assert {"id", "text", "text_raw", "urls", "label", "source", "is_synthetic"} <= set(test.columns)
    assert not test["text"].str.contains("98765|http").any()          # masked
    assert test["text"].str.contains("<PHONE>").all() and test["text"].str.contains("<URL>").all()
    assert test["urls"].map(len).min() == 1                           # originals preserved for the URL analyzer
    assert "http" in test.iloc[0]["text_raw"]
    assert "removed" in pp.format_report(report)
