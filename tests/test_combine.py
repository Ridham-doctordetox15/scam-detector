"""Tests for src.preprocessing.combine (no network access)."""
import json
from pathlib import Path

import pandas as pd
import pytest

from src.preprocessing import combine, generate_synthetic
from src.preprocessing.load_kaggle import KAGGLE_SPECS
from src.preprocessing.schema import COLUMNS, make_frame


def frame(texts, labels, source, **kw):
    return make_frame(texts, labels, source=source, **kw)


def test_clean_text_and_dedup_key() -> None:
    assert combine.clean_text("  hi\x00 there \n") == "hi there"
    assert combine.dedup_key("Hello   WORLD\n") == combine.dedup_key("hello world")


def test_normalize_frame_drops_empty_and_overlong() -> None:
    df = frame(["ok text", "   ", "x" * 50], ["safe", "safe", "scam"], "s")
    out, too_long = combine.normalize_frame(df, max_chars=10)
    assert out["text"].tolist() == ["ok text"]
    assert too_long == 1


def test_tag_language_only_touches_real_rows() -> None:
    real = frame(["आपका खाता बंद", "Your account is blocked"], ["scam", "scam"], "r")
    synth = frame(["whatever text"], ["scam"], "s", is_synthetic=True, language="ta_en")
    out = combine.tag_language(pd.concat([real, synth], ignore_index=True))
    assert out["language"].tolist() == ["hi", "en", "ta_en"]


def test_deduplicate_keeps_first_source_and_drops_conflicts() -> None:
    df = pd.concat(
        [
            frame(["Free prize!!", "same text", "Ambiguous msg"], ["scam", "safe", "scam"], "first"),
            frame(["free   PRIZE!!", "same text", "ambiguous MSG", "unique"],
                  ["scam", "safe", "safe", "safe"], "second"),
        ],
        ignore_index=True,
    )
    out, stats = combine.deduplicate(df)
    assert sorted(out["text"]) == ["Free prize!!", "same text", "unique"]
    assert out.set_index("text").loc["Free prize!!", "source"] == "first"   # priority wins
    assert stats["conflicts"] == 2                       # both copies of the ambiguous text
    assert stats["duplicates"] == 2
    assert stats["duplicates_by_source"] == {"second": 2}


def test_merge_sources_end_to_end_and_report() -> None:
    frames = {
        "a": frame(["Send OTP now", "Lunch at 1?"], ["scam", "safe"], "src_a"),
        "b": frame(["send otp NOW", "x" * 20, "Aapka paisa aur account band hai kya"],
                   ["scam", "scam", "scam"], "src_b"),
    }
    out, report = combine.merge_sources(frames, max_chars=10 ** 6)
    assert list(out.columns) == COLUMNS
    assert len(out) == 4
    assert report["loaded"] == {"src_a": 2, "src_b": 3}
    assert report["duplicates"] == 1
    assert "hinglish_guess" in out["language"].tolist()


def test_merge_sources_rejects_invalid_source_and_empty_input() -> None:
    bad = frame(["x"], ["scam"], "s")
    bad["label"] = "spam"
    with pytest.raises(ValueError):
        combine.merge_sources({"bad": bad})
    with pytest.raises(ValueError, match="no sources"):
        combine.merge_sources({})


def test_summarize_contains_all_breakdowns() -> None:
    frames = {
        "a": frame(["Send OTP now", "Lunch at 1?"], ["scam", "safe"], "src_a"),
        "b": frame(["Win lottery"], ["scam"], "synthetic_llm", scam_type="lottery",
                   language="hi", is_synthetic=True, generator="groq/m"),
    }
    out, report = combine.merge_sources(frames)
    text = combine.summarize(out, report)
    for expected in ("By source", "By label", "By language", "By scam_type",
                     "By is_synthetic", "Source x label", "src_a", "lottery", "groq/m"):
        assert expected in text


def test_build_combined_writes_parquet(tmp_path: Path) -> None:
    raw = tmp_path / "raw"
    (raw / "uci_sms").mkdir(parents=True)
    (raw / "uci_sms" / "SMSSpamCollection").write_text(
        "ham\tSee you soon\nspam\tWin a free prize now\n", encoding="utf-8")
    (raw / "hf_phishing").mkdir(parents=True)
    (raw / "hf_phishing" / "texts.json").write_text(
        json.dumps([{"text": "Win a free prize now", "label": 1},      # duplicate of UCI
                    {"text": "Your invoice is attached", "label": 0}]), encoding="utf-8")
    spec = KAGGLE_SPECS["subhajournal_phishingemails"]
    kdir = raw / "kaggle" / spec.dirname
    kdir.mkdir(parents=True)
    pd.DataFrame({"Email Text": ["Verify your bank password"], "Email Type": ["Phishing Email"]}
                 ).to_csv(kdir / spec.filename, index=False)
    synth = tmp_path / "synth.jsonl"
    generate_synthetic.ProgressStore(synth).append({
        "key": "k", "label": "scam", "topic": "lottery", "scam_type": "lottery",
        "language": "hinglish", "provider": "groq", "model": "m",
        "messages": ["Aapne lottery jeeti hai, kya aap abhi claim karo"]})

    out_path = tmp_path / "processed" / "combined.parquet"
    df, report = combine.build_combined(raw, out_path, synth, download=False, kaggle_specs=("subhajournal_phishingemails",))

    on_disk = pd.read_parquet(out_path)
    assert list(on_disk.columns) == COLUMNS
    assert len(on_disk) == len(df) == 5                      # 6 loaded, 1 duplicate dropped
    assert report["duplicates"] == 1
    assert on_disk["is_synthetic"].sum() == 1
    assert on_disk.loc[on_disk["is_synthetic"], "generator"].iloc[0] == "groq/m"
    assert on_disk.loc[~on_disk["is_synthetic"], "generator"].isna().all()


def test_build_combined_can_add_the_india_source_and_read_audited_parquet(tmp_path: Path) -> None:
    raw = tmp_path / "raw"
    ikey = "junioralive_india_spam_sms"
    spec = KAGGLE_SPECS[ikey]
    (raw / "kaggle" / spec.dirname).mkdir(parents=True)
    pd.DataFrame({"Msg": ["Click i.airtel.in/x for FREE 5GB data now", "Meeting at 5 pm today ok"],
                  "Label": ["spam", "ham"]}).to_csv(raw / "kaggle" / spec.dirname / spec.filename, index=False)
    audited = tmp_path / "synthetic_audited.parquet"
    make_frame(["Aapne lottery jeeti hai kya aap abhi claim karo"], ["scam"], source="synthetic_llm", scam_type="lottery",
               language="hinglish", is_synthetic=True, generator="groq/m", subtype="fraud").to_parquet(audited, index=False)
    df, _ = combine.build_combined(raw, tmp_path / "out.parquet", audited, skip=("uci", "hf"), download=False, kaggle_specs=(ikey,))
    assert set(df["source"]) == {"kaggle_india_spam_sms", "synthetic_llm"}
    assert df.set_index("source").loc["kaggle_india_spam_sms"].query("label == 'scam'")["subtype"].iloc[0] == "promo"
    assert df[df.source == "synthetic_llm"]["subtype"].iloc[0] == "fraud"
    assert list(df.columns) == COLUMNS


def test_build_combined_skip_and_missing_synthetic(tmp_path: Path) -> None:
    raw = tmp_path / "raw"
    (raw / "uci_sms").mkdir(parents=True)
    (raw / "uci_sms" / "SMSSpamCollection").write_text("ham\thello there\n", encoding="utf-8")
    df, _ = combine.build_combined(
        raw, tmp_path / "out.parquet", tmp_path / "none.jsonl",
        skip=("hf", "kaggle"), download=False)
    assert df["source"].unique().tolist() == ["uci_sms_spam"]
