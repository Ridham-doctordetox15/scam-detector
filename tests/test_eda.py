"""Tests for src.preprocessing.eda (statistics exactly; charts are written and non-empty)."""
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.preprocessing import eda
from src.preprocessing.schema import make_frame


def frame() -> pd.DataFrame:
    rows = (
        [("win free prize now click <URL> call <PHONE>", "scam", "uci")] * 12
        + [("your otp is <OTP> keep it safe", "safe", "uci")] * 8
        + [("free prize claim fee urgent", "scam", "hf")] * 10
        + [("meeting agenda attached tomorrow", "safe", "hf")] * 20
        + [("aapka account band ho jayega", "scam", "synth")] * 5
    )
    df = make_frame([r[0] for r in rows], [r[1] for r in rows], source="x")
    df["source"] = [r[2] for r in rows]
    df["is_synthetic"] = df["source"] == "synth"
    df["language"] = np.where(df["source"] == "synth", "hinglish", "en")
    return df


def test_class_counts_fixed_order_and_shares() -> None:
    c = eda.class_counts(frame())
    assert c.index.tolist() == ["safe", "scam"]
    assert c["rows"].tolist() == [28, 27]
    assert c["share"].sum() == pytest.approx(1.0)


def test_class_counts_handles_missing_class() -> None:
    only_safe = frame().query("label == 'safe'")
    c = eda.class_counts(only_safe)
    assert c.loc["scam", "rows"] == 0


def test_scam_rate_by_source() -> None:
    r = eda.scam_rate_by_source(frame())
    assert r.loc["uci", "scam_rate"] == pytest.approx(12 / 20)
    assert r.loc["hf", "scam_rate"] == pytest.approx(10 / 30)
    assert r.loc["synth", "scam_rate"] == 1.0 and r.loc["synth", "synthetic_share"] == 1.0
    assert r.index[0] == "hf"                               # largest first


def test_length_stats_uses_raw_text_when_available() -> None:
    df = frame()
    df["text_raw"] = df["text"] + " " * 10
    stats = eda.length_stats(df)
    masked_len = len("aapka account band ho jayega")
    assert stats.loc[("synth", "scam"), "median"] == masked_len + 10
    assert {"rows", "median", "mean", "p95", "max"} == set(stats.columns)


def test_language_counts() -> None:
    t = eda.language_counts(frame())
    assert t.loc["en", "total"] == 50 and t.loc["hinglish", "scam"] == 5 and t.loc["hinglish", "safe"] == 0
    assert t.index[0] == "en"


def test_top_words_by_class_finds_distinctive_words() -> None:
    words = eda.top_words_by_class(frame(), n=5, min_df=5)
    scam, safe = words["scam"]["word"].tolist(), words["safe"]["word"].tolist()
    assert "prize" in scam and "free" in scam
    assert "meeting" in safe or "otp" in safe
    assert not set(scam) & set(safe)
    assert words["scam"]["log_odds"].iloc[0] > 0 > words["safe"]["log_odds"].iloc[0]
    assert words["scam"]["log_odds"].is_monotonic_decreasing


def test_top_words_min_df_and_stopwords() -> None:
    words = eda.top_words_by_class(frame(), n=50, min_df=13)
    every = set(words["scam"]["word"]) | set(words["safe"]["word"])
    assert "the" not in every and "your" not in every        # english stop words removed
    assert "meeting" in every and "prize" in every           # df >= 13
    assert "urgent" not in every                             # appears in only 10 docs


def test_masked_token_rates() -> None:
    r = eda.masked_token_rates(frame())
    assert r.loc["scam", "<URL>"] == pytest.approx(12 / 27)
    assert r.loc["safe", "<OTP>"] == pytest.approx(8 / 28)
    assert r.loc["safe", "<URL>"] == 0


# ------------------------------- charts ------------------------------------ #
def _report() -> dict:
    return {
        "input_rows": 100, "rows_after_cleaning": 99, "rows_after_exact_dedup": 90,
        "near_duplicates": {"removed": 10, "threshold": 0.9}, "rows_after_dedup": 79,
    }


def assert_png(path: Path) -> None:
    assert path.exists() and path.stat().st_size > 2_000
    assert path.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"


def test_all_charts_are_written(tmp_path: Path) -> None:
    df = frame()
    words = eda.top_words_by_class(df, n=5, min_df=5)
    splits = {"train": df.iloc[:40], "val": df.iloc[40:50], "test": df.iloc[50:].assign(is_synthetic=False)}
    for path in (
        eda.plot_class_balance(df, tmp_path / "a.png"),
        eda.plot_scam_rate_by_source(df, tmp_path / "b.png"),
        eda.plot_length_distribution(df, tmp_path / "c.png"),
        eda.plot_top_words(words, tmp_path / "d.png"),
        eda.plot_language_distribution(df, tmp_path / "e.png"),
        eda.plot_real_vs_synthetic(splits, tmp_path / "f.png"),
        eda.plot_dedup_funnel(_report(), tmp_path / "g.png"),
    ):
        assert_png(path)


def test_chart_directory_is_created(tmp_path: Path) -> None:
    out = eda.plot_class_balance(frame(), tmp_path / "nested" / "dir" / "x.png")
    assert_png(out)


def test_colors_follow_the_class_not_the_rank() -> None:
    assert eda.CLASS_COLORS == {"safe": eda.SAFE, "scam": eda.SCAM}
    assert eda.SAFE != eda.SCAM
