"""Build the hand-collected ``real_indian_test`` evaluation set from a CSV.

The public corpora contain almost no Hinglish or Indian scam patterns, and the
synthetic data may not be used for evaluation. This set fills that gap: 100-200
real messages collected and labelled by hand. It is **never used for training or
tuning**; it is only ever evaluated on.

What this script does:

1. **Validates** the CSV (columns, labels, scam types, channel, language) and
   refuses rows that still contain personal information (Aadhaar, PAN, card
   numbers, e-mail/UPI addresses, bank account numbers).
2. Applies the **same cleaning and masking** as the training pipeline
   (URLs -> ``<URL>`` with originals kept, OTPs -> ``<OTP>``, phones ->
   ``<PHONE>``).
3. **Deduplicates** the rows against themselves and against the train, validation
   and test splits (exact and near-duplicate), so nothing leaks in from training.
4. Writes ``data/processed/real_indian_test.parquet`` (+ a JSON report). The raw
   text is *not* stored, only the masked text.

Re-run it whenever the splits are rebuilt. Template: ``docs/real_indian_test_template.csv``;
guidelines: ``docs/labeling_guidelines.md``.

Usage::

    python -m src.preprocessing.real_indian_test data/real_indian/messages.csv
"""
from __future__ import annotations

import argparse
import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from src.preprocessing.language import detect_language
from src.preprocessing.preprocess import (
    NEAR_DUP_THRESHOLD,
    cross_near_duplicates,
    dedup_key,
    make_id,
    preprocess_frame,
    remove_exact_duplicates,
    remove_near_duplicates,
)
from src.preprocessing.schema import (
    COLUMNS,
    LABEL_SAFE,
    LABEL_SCAM,
    SCAM_TYPE_NONE,
    SCAM_TYPE_UNKNOWN,
    SYNTHETIC_SCAM_TYPES,
    validate_frame,
)

logger = logging.getLogger(__name__)

DEFAULT_PROCESSED_DIR = Path("data/processed")
OUTPUT_NAME = "real_indian_test.parquet"
REPORT_NAME = "real_indian_test_report.json"
SOURCE_NAME = "real_indian_test"

REQUIRED_COLUMNS = ["text", "label", "scam_type", "language", "channel", "collected_from", "notes"]
CHANNELS = frozenset({"sms", "whatsapp", "email"})
# "other" in the scam_type column is accepted and stored as ``unknown``.
SCAM_TYPE_CHOICES = frozenset({*SYNTHETIC_SCAM_TYPES, "other"})
LANGUAGES = frozenset(
    {"en", "hi", "hinglish", "ta_en", "te_en", "bn_en", "mr_en", "gu_en", "kn_en", "ml_en",
     "pa_en", "ta", "te", "bn", "mr", "gu", "kn", "ml", "pa", "other"}
)
EXAMPLE_MARKER = "example"        # rows with collected_from == "example" are dropped
MIN_CHARS, MAX_CHARS = 5, 2_000
RECOMMENDED_MIN_ROWS = 100


# --------------------------------------------------------------------------- #
# Personal-information detection
# --------------------------------------------------------------------------- #
def _luhn_ok(digits: str) -> bool:
    """Luhn checksum, used to tell card numbers from arbitrary long digit strings."""
    total, alt = 0, False
    for ch in reversed(digits):
        d = int(ch)
        if alt:
            d = d * 2 - 9 if d * 2 > 9 else d * 2
        total += d
        alt = not alt
    return total % 10 == 0


_AADHAAR_RE = re.compile(r"(?<!\d)[2-9]\d{3}[\s-]\d{4}[\s-]\d{4}(?!\d)|(?<!\d)(?!91)[2-9]\d{11}(?!\d)")
_PAN_RE = re.compile(r"\b[A-Z]{5}\d{4}[A-Z]\b")
_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)*")
_CARD_RE = re.compile(r"(?<!\d)(?:\d[ -]?){12,18}\d(?!\d)")
_ACCOUNT_RE = re.compile(r"(?i)\b(?:a/c|acct|account)\b(?:\s*(?:no|number|num|#))?\.?[\s:.-]*\d{9,18}\b")


def find_pii(text: str) -> list[str]:
    """Names of personal-information patterns found in ``text``.

    Detects Aadhaar numbers, PAN, payment-card numbers (Luhn-valid), e-mail / UPI
    addresses and bank account numbers. Phone numbers are *not* flagged because
    they are masked to ``<PHONE>`` anyway. Personal names cannot be detected
    automatically; see the labeling guidelines.
    """
    found: list[str] = []
    if _AADHAAR_RE.search(text):
        found.append("aadhaar")
    if _PAN_RE.search(text):
        found.append("pan")
    if _EMAIL_RE.search(text):
        found.append("email")
    if any(_luhn_ok(re.sub(r"\D", "", m.group(0))) for m in _CARD_RE.finditer(text)):
        found.append("card")
    if _ACCOUNT_RE.search(text):
        found.append("account_number")
    return found


# --------------------------------------------------------------------------- #
# Validation
# --------------------------------------------------------------------------- #
@dataclass
class ValidationResult:
    """Outcome of :func:`validate_csv_frame`."""

    frame: pd.DataFrame                       # valid rows only, with normalised values
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        """True if there are no blocking errors."""
        return not self.errors


def load_csv(path: Path) -> pd.DataFrame:
    """Read the annotation CSV as strings (UTF-8, tolerating an Excel BOM)."""
    return pd.read_csv(path, dtype=str, keep_default_na=False, encoding="utf-8-sig")


def validate_csv_frame(df: pd.DataFrame, allow_pii: frozenset[str] = frozenset()) -> ValidationResult:
    """Validate the raw annotation table and normalise its values.

    Errors block the build (they name the CSV line so they are easy to fix).
    Warnings are informational.

    Args:
        df: Table as returned by :func:`load_csv`.
        allow_pii: PII kinds that may stay in the text (e.g. ``{"email"}`` for a
            scammer's fake contact address you decided to keep).
    """
    res = ValidationResult(frame=df.iloc[0:0])
    df = df.copy()
    df.columns = [str(c).strip().lower() for c in df.columns]
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        res.errors.append(f"missing column(s): {', '.join(missing)}")
        return res

    for col in REQUIRED_COLUMNS:
        df[col] = df[col].astype(str).str.strip()
    df["_line"] = np.arange(len(df)) + 2               # CSV line number (header is line 1)

    is_example = df["collected_from"].str.lower() == EXAMPLE_MARKER
    if is_example.any():
        res.warnings.append(f"dropped {int(is_example.sum())} example row(s) (collected_from='example')")
        df = df[~is_example]
    df = df[~(df[REQUIRED_COLUMNS].apply(lambda r: "".join(r) == "", axis=1))]   # fully blank rows

    keep = []
    for _, row in df.iterrows():
        problems = _row_problems(row, allow_pii)
        if problems:
            res.errors += [f"line {row['_line']}: {p}" for p in problems]
        else:
            keep.append(row["_line"])
        res.warnings += [f"line {row['_line']}: {w}" for w in _row_warnings(row)]

    good = df[df["_line"].isin(keep)].copy()
    good["label"] = good["label"].str.lower()
    good["channel"] = good["channel"].str.lower()
    good["language"] = good["language"].str.lower()
    good["scam_type"] = [
        SCAM_TYPE_NONE if lab == LABEL_SAFE else (SCAM_TYPE_UNKNOWN if st.lower() == "other" else st.lower())
        for lab, st in zip(good["label"], good["scam_type"])
    ]
    res.frame = good.drop(columns="_line").reset_index(drop=True)

    if res.ok:
        if len(good) < RECOMMENDED_MIN_ROWS:
            res.warnings.append(f"only {len(good)} valid rows; {RECOMMENDED_MIN_ROWS}+ recommended")
        counts = good["label"].value_counts()
        if len(counts) == 2 and counts.min() / counts.sum() < 0.25:
            res.warnings.append(f"class imbalance: {counts.to_dict()} (aim for at least 25% of each)")
        elif len(counts) < 2:
            res.warnings.append(f"only one class present: {counts.to_dict()}")
    return res


def _row_problems(row: pd.Series, allow_pii: frozenset[str]) -> list[str]:
    """Blocking problems for one row (empty list if the row is valid)."""
    problems: list[str] = []
    text = row["text"]
    label = row["label"].lower()
    if not text:
        return ["empty text"]
    if len(text) < MIN_CHARS:
        problems.append(f"text shorter than {MIN_CHARS} characters")
    if len(text) > MAX_CHARS:
        problems.append(f"text longer than {MAX_CHARS} characters")
    if label not in (LABEL_SCAM, LABEL_SAFE):
        problems.append(f"label must be 'scam' or 'safe', got '{row['label']}'")
    st = row["scam_type"].lower()
    if label == LABEL_SCAM and st not in SCAM_TYPE_CHOICES:
        problems.append(f"scam_type must be one of {sorted(SCAM_TYPE_CHOICES)} for scam rows, got '{row['scam_type']}'")
    if label == LABEL_SAFE and st not in ("", SCAM_TYPE_NONE):
        problems.append("scam_type must be blank (or 'none') for safe rows")
    if row["channel"].lower() not in CHANNELS:
        problems.append(f"channel must be one of {sorted(CHANNELS)}, got '{row['channel']}'")
    if row["language"].lower() not in LANGUAGES:
        problems.append(f"language must be one of {sorted(LANGUAGES)}, got '{row['language']}'")
    pii = [p for p in find_pii(text) if p not in allow_pii]
    if pii:
        problems.append(f"possible personal information ({', '.join(pii)}) - redact it (see guidelines)")
    return problems


def _row_warnings(row: pd.Series) -> list[str]:
    """Non-blocking hints, e.g. the declared language disagrees with the heuristic."""
    declared, detected = row["language"].lower(), detect_language(row["text"])
    if declared == "hinglish" and detected == "hi":
        return ["marked hinglish but the text is mostly Devanagari (did you mean 'hi'?)"]
    if declared == "hi" and detected != "hi":
        return ["marked hi but the text is not mostly Devanagari (did you mean 'hinglish'?)"]
    if declared == "en" and detected == "hinglish_guess":
        return ["marked en but looks like romanized Hindi (did you mean 'hinglish'?)"]
    return []


# --------------------------------------------------------------------------- #
# Build
# --------------------------------------------------------------------------- #
def to_schema_frame(valid: pd.DataFrame) -> pd.DataFrame:
    """Convert validated rows to the shared schema (+ ``channel``/``collected_from``)."""
    out = pd.DataFrame(
        {
            "text": valid["text"].tolist(),
            "label": valid["label"].tolist(),
            "scam_type": valid["scam_type"].tolist(),
            "language": valid["language"].tolist(),
            "source": SOURCE_NAME,
            "is_synthetic": False,
            "generator": None,
            "subtype": "unspecified",
            "channel": valid["channel"].tolist(),
            "collected_from": valid["collected_from"].tolist(),
        }
    )
    return out


def verify_holdout_disjoint(holdout: pd.DataFrame, *training_like: pd.DataFrame) -> None:
    """Assert no holdout row also appears (by id or exact text) in any given split.

    Raises:
        AssertionError: If the holdout overlaps a training split.
    """
    hold_ids, hold_keys = set(holdout["id"]), {dedup_key(t) for t in holdout["text"]}
    for i, part in enumerate(training_like):
        assert not hold_ids & set(part["id"]), f"holdout id overlaps split #{i}"
        assert not hold_keys & {dedup_key(t) for t in part["text"]}, f"holdout text overlaps split #{i}"


@dataclass
class BuildResult:
    """Outputs of :func:`build_real_indian_test`."""

    frame: pd.DataFrame
    report: dict


def build_real_indian_test(
    csv_path: Path,
    processed_dir: Path = DEFAULT_PROCESSED_DIR,
    allow_pii: frozenset[str] = frozenset(),
    threshold: float = NEAR_DUP_THRESHOLD,
) -> BuildResult:
    """Validate, preprocess, deduplicate and save the hand-collected test set.

    Raises:
        ValueError: If validation finds errors (all listed in the message) or no
            rows survive deduplication.
        FileNotFoundError: If the train/val/test parquet files are missing (run
            ``python -m src.preprocessing.preprocess`` first).
    """
    processed_dir = Path(processed_dir)
    validation = validate_csv_frame(load_csv(csv_path), allow_pii)
    if not validation.ok:
        shown = validation.errors[:50]
        more = f"\n... and {len(validation.errors) - 50} more" if len(validation.errors) > 50 else ""
        raise ValueError(f"{len(validation.errors)} validation error(s):\n" + "\n".join(shown) + more)

    if validation.frame.empty:
        raise ValueError("no valid rows in the CSV (only blank or example rows?)")
    splits = {n: pd.read_parquet(processed_dir / f"{n}.parquet") for n in ("train", "val", "test")}
    report: dict = {"csv_rows_valid": len(validation.frame), "warnings": validation.warnings}

    df = preprocess_frame(to_schema_frame(validation.frame))
    df["id"] = df["text"].map(make_id)
    df, exact = remove_exact_duplicates(df)
    df, near = remove_near_duplicates(df, threshold)
    report["duplicates_within_file"] = {"exact": exact["removed"], "near": near["removed"]}

    reference = pd.concat([s["text"] for s in splits.values()]).tolist()
    is_dup, max_sim = cross_near_duplicates(df["text"].tolist(), reference, threshold)
    report["duplicates_vs_splits"] = int(is_dup.sum())
    report["max_similarity_before_removal"] = round(float(max_sim.max()), 4) if len(max_sim) else 0.0
    df = df[~is_dup].reset_index(drop=True)
    if df.empty:
        raise ValueError("no rows left after deduplication against train/val/test")

    verify_holdout_disjoint(df, *splits.values())
    keep_cols = ["id", *COLUMNS, "urls", "channel", "collected_from"]      # no text_raw: privacy
    validate_frame(df[COLUMNS], SOURCE_NAME)
    df = df[keep_cols]
    df.to_parquet(processed_dir / OUTPUT_NAME, index=False, engine="pyarrow")

    report["final_rows"] = len(df)
    for col in ("label", "scam_type", "language", "channel"):
        report[f"by_{col}"] = df[col].value_counts().to_dict()
    (processed_dir / REPORT_NAME).write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    return BuildResult(df, report)


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Exit code 1 if validation fails."""
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("csv", type=Path, help="your filled-in CSV (see docs/real_indian_test_template.csv)")
    parser.add_argument("--processed-dir", type=Path, default=DEFAULT_PROCESSED_DIR)
    parser.add_argument("--allow", nargs="*", default=[], choices=["aadhaar", "pan", "email", "card", "account_number"],
                        help="PII kinds you deliberately keep (e.g. a scammer's fake e-mail)")
    parser.add_argument("--threshold", type=float, default=NEAR_DUP_THRESHOLD)
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    try:
        result = build_real_indian_test(args.csv, args.processed_dir, frozenset(args.allow), args.threshold)
    except ValueError as exc:
        print(exc)
        return 1
    r = result.report
    print(f"Saved {r['final_rows']} rows to {args.processed_dir / OUTPUT_NAME}")
    print(f"  valid in CSV: {r['csv_rows_valid']}; duplicates within file: {r['duplicates_within_file']}; "
          f"duplicates of train/val/test removed: {r['duplicates_vs_splits']}")
    for key in ("by_label", "by_scam_type", "by_language", "by_channel"):
        print(f"  {key}: {r[key]}")
    for w in r["warnings"]:
        print(f"  warning: {w}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
