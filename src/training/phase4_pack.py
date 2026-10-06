"""Package the Phase 4 (L3b) data for Google Colab.

Writes one small zip that you upload to Google Drive. It holds the train / val / test parquet files with the
masked ``text`` and the metadata the notebook needs, and **never** ``text_raw`` (the un-masked original): only
its length (``raw_chars``) is kept, so the short-message slice matches Phase 3.5. The hand-collected real
Indian test set is added when it exists (evaluation only, never training data).

    python -m src.training.phase4_pack            # -> data/phase4_data.zip
"""
from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pandas as pd

SOURCE_DIR = Path("data/processed_phase4")
HOLDOUT_CANDIDATES = (Path("data/processed_phase4/real_indian_test.parquet"),
                      Path("data/processed/real_indian_test.parquet"))
OUTPUT_ZIP = Path("data/phase4_data.zip")
SPLITS = ("train", "val", "test")
PACK_COLUMNS = ["id", "text", "label", "source", "is_synthetic", "language", "scam_type", "subtype",
                "benchmark", "raw_chars"]
FORBIDDEN_COLUMNS = ("text_raw", "urls")     # raw original text must never travel with the pack


def slim(df: pd.DataFrame) -> pd.DataFrame:
    """Keep only :data:`PACK_COLUMNS`, adding ``raw_chars`` (length of ``text_raw``) first.

    Columns a source lacks (the real Indian set has no ``benchmark``) get neutral defaults.
    """
    out = df.copy()
    if "raw_chars" not in out:
        out["raw_chars"] = out["text_raw"].astype(str).str.len() if "text_raw" in out else out["text"].str.len()
    defaults = {"benchmark": False, "subtype": "unspecified", "scam_type": "unknown", "language": "other",
                "is_synthetic": False}
    for col, value in defaults.items():
        if col not in out:
            out[col] = value
    out = out[PACK_COLUMNS].reset_index(drop=True)
    out["text"] = out["text"].astype(str)
    return out


def check_pack(frames: dict[str, pd.DataFrame]) -> None:
    """Assert the invariants the notebook's protocol relies on. Raises ``ValueError`` on any violation."""
    for name, frame in frames.items():
        bad = [c for c in FORBIDDEN_COLUMNS if c in frame.columns]
        if bad:
            raise ValueError(f"{name}: forbidden column(s) {bad}")
        if not set(frame["label"]).issubset({"safe", "scam"}):
            raise ValueError(f"{name}: labels must be 'safe' or 'scam'")
        if (frame["text"].str.strip() == "").any():
            raise ValueError(f"{name}: empty text")
    if frames["test"]["is_synthetic"].any():
        raise ValueError("the test set must be 100% real data")
    if "real_indian_test" in frames and frames["real_indian_test"]["is_synthetic"].any():
        raise ValueError("the real Indian test set must not be synthetic")
    ids = {n: set(frames[n]["id"]) for n in SPLITS}
    for a, b in (("train", "val"), ("train", "test"), ("val", "test")):
        if ids[a] & ids[b]:
            raise ValueError(f"id overlap between {a} and {b}")
    texts = {n: set(frames[n]["text"]) for n in SPLITS}
    for a, b in (("train", "val"), ("train", "test"), ("val", "test")):
        if texts[a] & texts[b]:
            raise ValueError(f"identical text in {a} and {b}")
    if "real_indian_test" in frames:
        held = set(frames["real_indian_test"]["text"])
        if held & (texts["train"] | texts["val"]):
            raise ValueError("real Indian test set overlaps training or validation text")


def build_pack(source_dir: Path = SOURCE_DIR, output: Path = OUTPUT_ZIP,
               holdout_candidates: tuple[Path, ...] = HOLDOUT_CANDIDATES) -> dict:
    """Build the zip and return a summary (rows per file, scam rates, whether the Indian set was included)."""
    frames = {n: slim(pd.read_parquet(Path(source_dir) / f"{n}.parquet")) for n in SPLITS}
    holdout = next((p for p in holdout_candidates if Path(p).exists()), None)
    if holdout is not None:
        frames["real_indian_test"] = slim(pd.read_parquet(holdout))
    check_pack(frames)
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    summary: dict = {"files": {}, "real_indian_test_included": holdout is not None}
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, frame in frames.items():
            tmp = output.with_name(f"_{name}.parquet")
            frame.to_parquet(tmp, index=False)
            zf.write(tmp, f"{name}.parquet")
            tmp.unlink()
            summary["files"][name] = {"rows": len(frame), "scam_rate": round(float((frame["label"] == "scam").mean()), 4)}
    summary["zip_bytes"] = output.stat().st_size
    return summary


def main() -> int:
    """Build ``data/phase4_data.zip`` and print what went in."""
    summary = build_pack()
    print(json.dumps(summary, indent=1))
    print(f"\nUpload {OUTPUT_ZIP} to Google Drive at MyDrive/scam-detector/phase4_data.zip")
    if not summary["real_indian_test_included"]:
        print("(no real Indian test set found: the notebook will report it as not built)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
