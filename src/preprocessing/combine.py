"""Merge all data sources into ``data/processed/combined.parquet``.

Pipeline: load each source -> clean text -> tag language (real data only) ->
drop label-conflicting and exact-duplicate texts -> validate -> write parquet
-> print a summary.

Deduplication happens here, *before* any train/test split (CLAUDE.md rule).
Near-duplicate removal and the split itself belong to Phase 2; synthetic rows
must stay out of the test set there.

Usage::

    python -m src.preprocessing.combine              # download missing data, merge
    python -m src.preprocessing.combine --no-download
    python -m src.preprocessing.combine --skip kaggle synthetic
"""
from __future__ import annotations

import argparse
import logging
from pathlib import Path

import pandas as pd

from src.preprocessing.generate_synthetic import DEFAULT_OUTPUT as SYNTHETIC_JSONL
from src.preprocessing.generate_synthetic import load_synthetic
from src.preprocessing.language import detect_language
from src.preprocessing.load_hf_phishing import load_hf_phishing
from src.preprocessing.load_kaggle import KAGGLE_SPECS, load_kaggle
from src.preprocessing.load_uci import load_uci
from src.preprocessing.schema import COLUMNS, validate_frame

logger = logging.getLogger(__name__)

DEFAULT_RAW_DIR = Path("data/raw")
DEFAULT_OUTPUT = Path("data/processed/combined.parquet")
# Texts longer than this are dropped (e.g. one HF row is ~17M characters).
MAX_TEXT_CHARS = 10_000
# Only the first N characters are inspected when tagging language.
LANGUAGE_SAMPLE_CHARS = 2_000
SOURCE_CHOICES = ("uci", "hf", "kaggle", "synthetic")


def clean_text(text: str) -> str:
    """Strip whitespace and NUL characters; the text is otherwise left untouched."""
    return text.replace("\x00", "").strip()


def dedup_key(text: str) -> str:
    """Case-insensitive, whitespace-collapsed key used to detect duplicates."""
    return " ".join(text.casefold().split())


def normalize_frame(df: pd.DataFrame, max_chars: int = MAX_TEXT_CHARS) -> tuple[pd.DataFrame, int]:
    """Clean texts and drop empty or over-long ones.

    Returns:
        ``(cleaned_frame, number_of_over_long_rows_dropped)``.
    """
    out = df.copy()
    out["text"] = out["text"].astype(str).map(clean_text)
    out = out[out["text"] != ""]
    too_long = out["text"].str.len() > max_chars
    return out[~too_long].reset_index(drop=True), int(too_long.sum())


def tag_language(df: pd.DataFrame) -> pd.DataFrame:
    """Set ``language`` from the script/Hinglish heuristic on *real* rows only.

    Synthetic rows keep the language they were generated in.
    """
    out = df.copy()
    real = ~out["is_synthetic"]
    out.loc[real, "language"] = [
        detect_language(t[:LANGUAGE_SAMPLE_CHARS]) for t in out.loc[real, "text"]
    ]
    return out


def deduplicate(df: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, int]]:
    """Remove label-conflicting and exact-duplicate texts.

    * A text that appears with *both* labels is ambiguous, so every copy is
      dropped rather than guessing.
    * Among the remaining exact duplicates the first occurrence wins, so the
      order of ``df`` is the source priority (real before synthetic).

    Returns:
        ``(deduplicated_frame, stats)`` where stats has ``conflicts`` (rows
        dropped for conflicting labels), ``duplicates`` (redundant copies
        dropped) and ``duplicates_by_source``.
    """
    work = df.copy()
    work["_key"] = work["text"].map(dedup_key)
    n_labels = work.groupby("_key")["label"].transform("nunique")
    conflict = n_labels > 1
    work = work[~conflict]
    dup = work.duplicated("_key", keep="first")
    stats = {
        "conflicts": int(conflict.sum()),
        "duplicates": int(dup.sum()),
        "duplicates_by_source": {k: int(v) for k, v in work[dup]["source"].value_counts().items()},
    }
    return work[~dup].drop(columns="_key").reset_index(drop=True), stats


def merge_sources(
    frames: dict[str, pd.DataFrame], max_chars: int = MAX_TEXT_CHARS
) -> tuple[pd.DataFrame, dict]:
    """Validate, clean, language-tag and deduplicate the given sources.

    Args:
        frames: Mapping of source name -> schema-conformant DataFrame. Dict
            order is the dedup priority (earlier wins).
        max_chars: Length cap passed to :func:`normalize_frame`.

    Returns:
        ``(combined_frame, report)``; ``report`` holds per-source loaded/cleaned
        counts and the dedup statistics.
    """
    cleaned: list[pd.DataFrame] = []
    report: dict = {"loaded": {}, "too_long": {}}
    for name, df in frames.items():
        validate_frame(df, name)
        frame, too_long = normalize_frame(df, max_chars)
        # Report keys are the values of the ``source`` column (one per frame).
        source = str(df["source"].iloc[0]) if len(df) else name
        report["loaded"][source] = len(df)
        report["too_long"][source] = too_long
        cleaned.append(frame)
    if not cleaned:
        raise ValueError("no sources to merge")
    combined = tag_language(pd.concat(cleaned, ignore_index=True))
    combined, dedup_stats = deduplicate(combined)
    report.update(dedup_stats)
    return validate_frame(combined[COLUMNS], "combined"), report


def _table(title: str, counts: pd.Series) -> str:
    lines = [f"\n{title}"]
    lines += [f"  {str(k):<40} {v:>8,}" for k, v in counts.items()]
    return "\n".join(lines)


def summarize(df: pd.DataFrame, report: dict | None = None) -> str:
    """Human-readable summary: counts per source, label, language, scam_type."""
    parts = [f"COMBINED DATASET: {len(df):,} rows"]
    if report:
        parts.append("\nPer-source pipeline (loaded -> too long dropped -> duplicates dropped):")
        for name, n in report["loaded"].items():
            dups = report["duplicates_by_source"].get(name, 0)
            parts.append(
                f"  {name:<40} loaded={n:>7,}  too_long={report['too_long'][name]:>4,}  duplicates={dups:>7,}"
            )
        parts.append(f"  label-conflict rows dropped: {report['conflicts']:,}")
    parts.append(_table("By source", df["source"].value_counts()))
    parts.append(_table("By label", df["label"].value_counts()))
    parts.append(_table("By language", df["language"].value_counts()))
    parts.append(_table("By scam_type", df["scam_type"].value_counts()))
    parts.append(_table("By is_synthetic", df["is_synthetic"].value_counts()))
    parts.append("\nSource x label\n" + pd.crosstab(df["source"], df["label"]).to_string())
    parts.append("\nLanguage x label\n" + pd.crosstab(df["language"], df["label"]).to_string())
    synth = df[df["is_synthetic"]]
    if not synth.empty:
        parts.append(_table("Synthetic by generator", synth["generator"].value_counts()))
    return "\n".join(parts)


def load_synthetic_any(path: Path) -> pd.DataFrame:
    """Synthetic rows from the raw generator JSONL or from an audited parquet file.

    An audited parquet (written after the Phase 3.5 label audit) must already follow the shared
    schema; it is validated and returned as is.
    """
    path = Path(path)
    if path.suffix == ".parquet":
        return validate_frame(pd.read_parquet(path)[COLUMNS], "audited synthetic")
    return load_synthetic(path)


def build_combined(
    raw_dir: Path = DEFAULT_RAW_DIR,
    output: Path = DEFAULT_OUTPUT,
    synthetic_path: Path = SYNTHETIC_JSONL,
    skip: tuple[str, ...] = (),
    download: bool = True,
    hf_token: str | None = None,
    kaggle_specs: tuple[str, ...] | None = None,
) -> tuple[pd.DataFrame, dict]:
    """Load every enabled source, merge, write parquet, and return (df, report).

    ``kaggle_specs`` lists the keys of ``KAGGLE_SPECS`` to load (default: all registered).
    ``synthetic_path`` may be the raw JSONL or an audited ``.parquet``.
    """
    raw_dir = Path(raw_dir)
    frames: dict[str, pd.DataFrame] = {}
    if "uci" not in skip:
        frames["uci"] = load_uci(raw_dir / "uci_sms", download=download)
    if "hf" not in skip:
        frames["hf"] = load_hf_phishing(raw_dir / "hf_phishing", download=download, token=hf_token)
    if "kaggle" not in skip:
        chosen = KAGGLE_SPECS if kaggle_specs is None else {k: KAGGLE_SPECS[k] for k in kaggle_specs}
        for spec in chosen.values():
            frames[f"kaggle:{spec.slug}"] = load_kaggle(spec, raw_dir / "kaggle", download=download)
    if "synthetic" not in skip:
        synth = load_synthetic_any(synthetic_path)
        if synth.empty:
            logger.warning("No synthetic data found at %s", synthetic_path)
        else:
            frames["synthetic"] = synth
    combined, report = merge_sources(frames)
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    combined.to_parquet(output, index=False, engine="pyarrow")
    logger.info("Wrote %s (%.1f MB)", output, output.stat().st_size / 1e6)
    return combined, report


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("--raw-dir", type=Path, default=DEFAULT_RAW_DIR)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--synthetic", type=Path, default=SYNTHETIC_JSONL)
    parser.add_argument("--skip", nargs="*", choices=SOURCE_CHOICES, default=[])
    parser.add_argument("--no-download", action="store_true", help="only use files already on disk")
    parser.add_argument("--kaggle", nargs="*", choices=sorted(KAGGLE_SPECS), default=None,
                        help="Kaggle sources to load (default: all registered)")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    from dotenv import load_dotenv
    import os

    load_dotenv()
    df, report = build_combined(
        args.raw_dir,
        args.output,
        args.synthetic,
        skip=tuple(args.skip),
        download=not args.no_download,
        kaggle_specs=tuple(args.kaggle) if args.kaggle is not None else None,
        hf_token=os.getenv("HF_TOKEN") or None,
    )
    print(summarize(df, report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
