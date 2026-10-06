"""Tests for src.preprocessing.real_indian_test (validation, PII, build, holdout guard)."""
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.preprocessing import preprocess as pp
from src.preprocessing import real_indian_test as rit
from src.preprocessing.schema import make_frame

HEADER = "text,label,scam_type,language,channel,collected_from,notes\n"


def row(text: str, label: str = "scam", scam_type: str = "lottery", language: str = "hinglish",
        channel: str = "sms", src: str = "own inbox", notes: str = "") -> dict:
    return dict(text=text, label=label, scam_type=scam_type, language=language,
                channel=channel, collected_from=src, notes=notes)


def table(*rows: dict) -> pd.DataFrame:
    return pd.DataFrame(list(rows), dtype=str)


GOOD_SCAM = "Aapne lottery jeeti hai kya aap abhi claim karo, fee bharein"
GOOD_SAFE = "Aapka OTP 482915 hai. Kisi ke saath share na karein. HDFC Bank"


# ================================== PII ===================================== #
@pytest.mark.parametrize(
    "text, expected",
    [
        ("my aadhaar 2345 6789 0123 ok", ["aadhaar"]),
        ("aadhaar 234567890123", ["aadhaar"]),
        ("PAN is ABCDE1234F", ["pan"]),
        ("mail rahul.k@gmail.com", ["email"]),
        ("pay to raj@okhdfcbank", ["email"]),
        ("card 4111 1111 1111 1111 exp", ["card"]),
        ("A/c no 123456789012 debited", ["account_number"]),
        ("account number: 9876543210123 ok", ["account_number"]),
    ],
)
def test_find_pii_detects(text: str, expected: list[str]) -> None:
    assert set(expected) <= set(rit.find_pii(text))


@pytest.mark.parametrize(
    "text",
    [
        "Call 9876543210 now",                   # phones are masked later, not flagged
        "Call +91 98765 43210",
        "Call 919876543210 now",                 # 12 digits starting with 91 is a phone
        "Rs 1,50,000 credited",
        "Your OTP is 482915",
        "Order 12345 shipped",
        "Visit http://a.com/x",
        "Aapka account block ho jayega",
        "card 1234 5678 1234 5679 exp",          # fails Luhn, and not Aadhaar-shaped at the start
    ],
)
def test_find_pii_ignores_harmless_text(text: str) -> None:
    found = rit.find_pii(text)
    assert "card" not in found and "pan" not in found and "email" not in found


def test_luhn() -> None:
    assert rit._luhn_ok("4111111111111111")
    assert not rit._luhn_ok("4111111111111112")


# ============================== validation ================================== #
def test_valid_rows_are_normalised() -> None:
    res = rit.validate_csv_frame(table(
        row(GOOD_SCAM, "Scam", "Lottery", "Hinglish", " SMS "),
        row(GOOD_SAFE, "safe", "", "hinglish", "sms"),
        row("Aapka account block hoga, kya karo? abhi link", "scam", "other", "hinglish", "whatsapp"),
    ))
    assert res.ok, res.errors
    f = res.frame
    assert f["label"].tolist() == ["scam", "safe", "scam"]
    assert f["scam_type"].tolist() == ["lottery", "none", "unknown"]     # blank->none, other->unknown
    assert f["channel"].tolist() == ["sms", "sms", "whatsapp"]


def test_missing_columns_reported() -> None:
    res = rit.validate_csv_frame(pd.DataFrame({"text": ["x"], "label": ["scam"]}))
    assert not res.ok and "missing column" in res.errors[0] and "channel" in res.errors[0]


def test_errors_carry_csv_line_numbers() -> None:
    res = rit.validate_csv_frame(table(
        row(GOOD_SCAM),                                   # line 2: fine
        row(GOOD_SCAM + " b", label="spam"),              # line 3
        row(GOOD_SCAM + " c", channel="telegram"),        # line 4
        row(GOOD_SCAM + " d", language="klingon"),        # line 5
        row(GOOD_SCAM + " e", scam_type="phishing"),      # line 6
        row(GOOD_SAFE, label="safe", scam_type="lottery"),  # line 7
        row("hi", label="safe", scam_type=""),            # line 8: too short
    ))
    text = "\n".join(res.errors)
    for line, needle in [(3, "label must be"), (4, "channel must be"), (5, "language must be"),
                         (6, "scam_type must be one of"), (7, "blank"), (8, "shorter than")]:
        assert f"line {line}:" in text and needle in text
    assert "line 2:" not in text


def test_empty_text_and_blank_rows() -> None:
    res = rit.validate_csv_frame(table(row(""), row("", "", "", "", "", "", "")))
    assert len(res.errors) == 1 and "line 2: empty text" in res.errors[0]     # blank row 3 ignored


def test_overlong_text_rejected() -> None:
    res = rit.validate_csv_frame(table(row("x " * 1500)))
    assert any("longer than" in e for e in res.errors)


def test_pii_rows_rejected_unless_allowed() -> None:
    bad = row("Send money to raj@okhdfcbank now, kya aap karo jaldi")
    res = rit.validate_csv_frame(table(bad))
    assert not res.ok and "personal information (email)" in res.errors[0]
    assert rit.validate_csv_frame(table(bad), allow_pii=frozenset({"email"})).ok


def test_example_rows_are_dropped_with_a_warning() -> None:
    res = rit.validate_csv_frame(table(row("Made-up example message text", src="example"), row(GOOD_SCAM)))
    assert res.ok and len(res.frame) == 1
    assert any("example" in w for w in res.warnings)


def test_language_mismatch_warnings() -> None:
    res = rit.validate_csv_frame(table(
        row("आपका खाता बंद हो जाएगा आज ही", language="hinglish"),
        row("Aapka account band ho jayega, kya aap abhi verify karo", language="hi"),
        row("Aapka account band ho jayega, kya aap abhi verify karo", language="en"),
    ))
    assert res.ok
    joined = " ".join(res.warnings)
    assert "did you mean 'hi'" in joined and "did you mean 'hinglish'" in joined


def test_size_and_balance_warnings() -> None:
    rows = [row(f"Aapka parcel {i} customs mein hai kripya fee bharein warna wapas") for i in range(30)]
    res = rit.validate_csv_frame(table(*rows))
    assert res.ok
    assert any("recommended" in w for w in res.warnings)
    assert any("only one class" in w for w in res.warnings)


def test_load_csv_handles_bom_and_case_insensitive_headers(tmp_path: Path) -> None:
    p = tmp_path / "m.csv"
    p.write_text("﻿" + HEADER.upper() + f'"{GOOD_SCAM}",scam,lottery,hinglish,sms,inbox,\n', encoding="utf-8")
    res = rit.validate_csv_frame(rit.load_csv(p))
    assert res.ok and len(res.frame) == 1


# ================================== build =================================== #
TRAIN_TEXTS = [
    "your electricity will be disconnected tonight pay the bill now call the officer immediately",
    "hi are we still meeting for lunch tomorrow at the usual place near the office building",
    "the quarterly report is attached please review the numbers and share your comments soon",
    "congratulations you won a lottery reward send a small processing fee to receive the prize",
    "your parcel is held at the warehouse pay the delivery charge at the link to release it",
    "meeting moved to thursday afternoon please confirm your availability by end of day today",
    "dear customer your account will be suspended verify your details within twenty four hours",
    "reminder your appointment with the doctor is scheduled for monday morning at ten thirty",
]


def _write_splits(d: Path) -> None:
    def part(texts: list[str], label_cycle: tuple[str, ...]) -> pd.DataFrame:
        df = make_frame(texts, [label_cycle[i % len(label_cycle)] for i in range(len(texts))], source="hf_phishing_texts")
        df["id"] = df["text"].map(pp.make_id)
        return df

    part(TRAIN_TEXTS[:5], ("scam", "safe")).to_parquet(d / "train.parquet", index=False)
    part(TRAIN_TEXTS[5:7], ("safe",)).to_parquet(d / "val.parquet", index=False)
    part(TRAIN_TEXTS[7:], ("safe",)).to_parquet(d / "test.parquet", index=False)


def _csv(path: Path, rows: list[dict]) -> Path:
    pd.DataFrame(rows).to_csv(path, index=False)
    return path


def _indian_rows() -> list[dict]:
    return [
        row("Aapka KYC pending hai, kya aap abhi update karo: http://kyc-sbi.example.top/x?id=1. Call 98765 43210",
            "scam", "fake_kyc", "hinglish", "sms"),
        row("Aapka OTP 482915 hai, yeh kisi se share na karein. HDFC Bank", "safe", "", "hinglish", "sms"),
        row("Congratulations! KBC lucky draw mein aapne 25 lakh jeete hain, claim karne ke liye call karein +91 91234 56780",
            "scam", "lottery", "hinglish", "whatsapp"),
        row("Kal ka office meeting 11 baje hai, kya aap aa rahe ho? Agenda mail kar diya hai", "safe", "", "hinglish", "whatsapp"),
        row("Your DHL parcel is on hold at customs, pay Rs 450 fee at bit.ly/dhl-fee9 to release", "scam", "courier_customs", "en", "email"),
    ]


def test_build_saves_masked_holdout_without_raw_text(tmp_path: Path) -> None:
    _write_splits(tmp_path)
    csv = _csv(tmp_path / "m.csv", _indian_rows())
    result = rit.build_real_indian_test(csv, tmp_path)

    out = pd.read_parquet(tmp_path / "real_indian_test.parquet")
    assert len(out) == len(result.frame) == 5
    assert set(out["source"]) == {"real_indian_test"} and not out["is_synthetic"].any()
    assert "text_raw" not in out.columns                         # privacy: raw text is not stored
    assert not out["text"].str.contains(r"98765|91234|482915|http|bit\.ly", regex=True).any()
    masked = out.set_index("label", drop=False)
    assert "<PHONE>" in " ".join(out["text"]) and "<OTP>" in " ".join(out["text"]) and "<URL>" in " ".join(out["text"])
    kyc = out[out["scam_type"] == "fake_kyc"].iloc[0]
    assert kyc["urls"][0].startswith("http://kyc-sbi.example.top")         # original URL kept for the analyzer
    assert masked.shape[0] == 5 and {"channel", "collected_from", "id"} <= set(out.columns)

    report = json.loads((tmp_path / "real_indian_test_report.json").read_text(encoding="utf-8"))
    assert report["final_rows"] == 5 and report["by_label"] == {"scam": 3, "safe": 2}
    assert report["duplicates_vs_splits"] == 0


def test_build_removes_duplicates_of_train_val_test_and_within_file(tmp_path: Path) -> None:
    _write_splits(tmp_path)
    rows = _indian_rows() + [
        row(TRAIN_TEXTS[0], "scam", "electricity_bill", "en", "sms"),            # exact copy of a train row
        row(TRAIN_TEXTS[7] + " today", "safe", "", "en", "sms"),                 # near copy of a test row
        row("Kal ka office meeting 11 baje hai, kya aap aa rahe ho? Agenda mail kar diya hai", "safe", "", "hinglish", "whatsapp"),   # within-file dup
    ]
    result = rit.build_real_indian_test(_csv(tmp_path / "m.csv", rows), tmp_path)
    assert result.report["duplicates_vs_splits"] == 2
    assert result.report["duplicates_within_file"]["exact"] == 1
    assert len(result.frame) == 5
    train = pd.read_parquet(tmp_path / "train.parquet")
    rit.verify_holdout_disjoint(result.frame, train)                             # must not raise


def test_build_raises_with_all_errors_listed(tmp_path: Path) -> None:
    _write_splits(tmp_path)
    csv = _csv(tmp_path / "m.csv", [row(GOOD_SCAM, label="maybe"), row(GOOD_SCAM + " x", channel="fax")])
    with pytest.raises(ValueError) as exc:
        rit.build_real_indian_test(csv, tmp_path)
    assert "2 validation error(s)" in str(exc.value) and "line 2" in str(exc.value) and "line 3" in str(exc.value)
    assert not (tmp_path / "real_indian_test.parquet").exists()


def test_build_raises_if_everything_is_a_duplicate(tmp_path: Path) -> None:
    _write_splits(tmp_path)
    csv = _csv(tmp_path / "m.csv", [row(TRAIN_TEXTS[0], "scam", "electricity_bill", "en", "sms")])
    with pytest.raises(ValueError, match="no rows left"):
        rit.build_real_indian_test(csv, tmp_path)


def test_shipped_template_parses_but_has_no_real_rows(tmp_path: Path) -> None:
    template = Path(__file__).resolve().parent.parent / "docs" / "real_indian_test_template.csv"
    res = rit.validate_csv_frame(rit.load_csv(template))
    assert res.ok and res.frame.empty                       # both rows are 'example' rows
    _write_splits(tmp_path)
    with pytest.raises(ValueError, match="no valid rows"):
        rit.build_real_indian_test(template, tmp_path)


def test_build_requires_split_files(tmp_path: Path) -> None:
    csv = _csv(tmp_path / "m.csv", _indian_rows())
    with pytest.raises(FileNotFoundError):
        rit.build_real_indian_test(csv, tmp_path)


def test_verify_holdout_disjoint_catches_overlap() -> None:
    hold = make_frame(["some holdout text here"], ["scam"], source="real_indian_test")
    hold["id"] = hold["text"].map(pp.make_id)
    other = make_frame(["SOME holdout   text here"], ["scam"], source="x")
    other["id"] = "different"
    with pytest.raises(AssertionError, match="text overlaps"):
        rit.verify_holdout_disjoint(hold, other)
    same_id = other.assign(text="unrelated words entirely", id=hold["id"].iloc[0])
    with pytest.raises(AssertionError, match="id overlaps"):
        rit.verify_holdout_disjoint(hold, same_id)
    rit.verify_holdout_disjoint(hold, other.assign(text="unrelated words entirely", id="z"))


def test_cli_exit_codes(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    _write_splits(tmp_path)
    good = _csv(tmp_path / "good.csv", _indian_rows())
    assert rit.main([str(good), "--processed-dir", str(tmp_path)]) == 0
    assert "Saved 5 rows" in capsys.readouterr().out
    bad = _csv(tmp_path / "bad.csv", [row(GOOD_SCAM, label="nope")])
    assert rit.main([str(bad), "--processed-dir", str(tmp_path)]) == 1
    assert "validation error" in capsys.readouterr().out


# ======================= holdout protection in preprocessing ================ #
def test_rebuilding_splits_removes_rows_similar_to_the_holdout(tmp_path: Path) -> None:
    rng = np.random.default_rng(2)
    vocab = ["".join(rng.choice(list("abcdefghijklmnopqrstuvwxyz"), 6)) for _ in range(500)]
    texts = [" ".join(rng.choice(vocab, 14)) for _ in range(200)]
    df = make_frame(texts, ["scam" if i % 3 == 0 else "safe" for i in range(200)], source="hf_phishing_texts")
    df.to_parquet(tmp_path / "combined.parquet", index=False)

    first = pp.run_preprocessing(tmp_path / "combined.parquet", tmp_path)
    assert first.report["holdout_overlap_removed"] == 0

    hold = make_frame([texts[0], texts[1] + " extra"], ["scam", "safe"], source="real_indian_test")
    hold["id"] = hold["text"].map(pp.make_id)
    hold.to_parquet(tmp_path / "real_indian_test.parquet", index=False)

    second = pp.run_preprocessing(tmp_path / "combined.parquet", tmp_path)
    assert second.report["holdout_overlap_removed"] == 2
    assert second.report["rows_after_dedup"] == first.report["rows_after_dedup"] - 2
    all_ids = set(second.train["id"]) | set(second.val["id"]) | set(second.test["id"])
    assert not set(hold["id"]) & all_ids
