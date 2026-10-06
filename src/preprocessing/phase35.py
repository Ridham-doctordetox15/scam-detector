"""Phase 3.5 data levels: rebuild the Phase 3 splits under each rung of the ablation ladder.

Every level starts from the *reference* splits written by Phase 2 (``data/processed/phase3_reference``)
so that a surviving row keeps the split it had in Phase 3 ("stable splits"). A level then applies,
cumulatively:

======  =====================================================================================
Level   What changes
======  =====================================================================================
L0      Nothing: the Phase 3 data (UCI/India-style "spam" counts as scam, raw synthetic labels).
L1      L0 + the audited synthetic labels (owner-approved flips and removals).
L2a     L1 + the scam-definition policy **D** and the India SMS rows: only *fraud* counts as scam;
        legitimate promotions and service notices are withheld from training and reported as a
        false-positive benchmark.
L2b     L1 + policy **A** (contrast): promotions and service notices are relabelled ``safe`` and
        used as hard negatives; India SMS rows added.
L3      L2a + text normalisation (quote markers, reply boilerplate, years, currency).
L4      L3 + drop non-messages (web-crawl rows, pipeline notices).
L5      L4 + drop Enron-internal email.
======  =====================================================================================

New rows (India SMS) are deduplicated against the reference and assigned a split with the same
70/15/15 stratified recipe; they are real data, so they may enter the test set. Rows whose text
changes under normalisation are re-deduplicated within each split and trimmed for cross-split
leakage (held-out rows are trimmed, train never is).

Nothing here reads model scores or labels of the test set; it only prepares frames.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split

from src.preprocessing import label_audit as la
from src.preprocessing import normalize as nz
from src.preprocessing.combine import merge_sources
from src.preprocessing.load_kaggle import KAGGLE_SPECS, load_kaggle
from src.preprocessing.preprocess import (
    NEAR_DUP_THRESHOLD,
    SPLIT_FRACTIONS,
    _strata,
    check_split_integrity,
    cross_near_duplicates,
    make_id,
    preprocess_frame,
    remove_exact_duplicates,
    remove_near_duplicates,
    trim_cross_split_leakage,
)
from src.preprocessing.uci_spam import uci_spam_subtype

logger = logging.getLogger(__name__)

REFERENCE_DIR = Path("data/processed/phase3_reference")
INDIA_SPEC = "junioralive_india_spam_sms"
UCI_SOURCE = "uci_sms_spam"
INDIA_SOURCE = "kaggle_india_spam_sms"
LEGIT_SUBTYPES = ("promo", "service")           # "spam" that is not fraud
SPLIT_NAMES = ("train", "val", "test")
SEED = 42


@dataclass(frozen=True)
class Level:
    """One rung of the ablation ladder (see the module docstring)."""

    name: str
    description: str
    audit: bool = False
    policy: str = "old"                       # old | D | A
    india: bool = False
    normalize: nz.NormalizeConfig = nz.NONE


LEVELS: dict[str, Level] = {
    "L0": Level("L0", "Phase 3 data as it was (old spam=scam definition)"),
    "L1": Level("L1", "L0 + audited synthetic labels", audit=True),
    "L2a": Level("L2a", "L1 + policy D (promo/service withheld) + India SMS", audit=True, policy="D", india=True),
    "L2b": Level("L2b", "L1 + policy A (promo/service -> safe) + India SMS", audit=True, policy="A", india=True),
    "L3": Level("L3", "L2a + text normalisation", audit=True, policy="D", india=True, normalize=nz.LEVEL_A),
    "L4": Level("L4", "L3 + drop web-crawl rows and pipeline notices", audit=True, policy="D", india=True,
                normalize=nz.LEVEL_A_B1),
    "L5": Level("L5", "L4 + drop Enron-internal email", audit=True, policy="D", india=True,
                normalize=nz.LEVEL_A_B1_B2),
}
# Added after the ladder, at the owner's request: the Phase 4 candidate (policy A on top of text normalisation).
LEVELS["L3b"] = Level("L3b", "L3 with policy A (promo/service -> safe) instead of D", audit=True, policy="A", india=True,
                      normalize=nz.LEVEL_A)
LADDER_ORDER = ("L0", "L1", "L2a", "L3", "L4", "L5")      # the cumulative path; L2b is the contrast branch


@dataclass
class LevelData:
    """Frames of one level plus a report of what was changed."""

    level: Level
    train: pd.DataFrame
    val: pd.DataFrame
    test: pd.DataFrame
    report: dict = field(default_factory=dict)

    def frames(self) -> dict[str, pd.DataFrame]:
        return {"train": self.train, "val": self.val, "test": self.test}


# --------------------------------------------------------------------------- #
# Reference frame
# --------------------------------------------------------------------------- #
def load_reference(reference_dir: Path = REFERENCE_DIR) -> pd.DataFrame:
    """All Phase 3 rows with a ``split`` column, plus ``subtype`` and the untouched labels."""
    parts = []
    for name in SPLIT_NAMES:
        part = pd.read_parquet(Path(reference_dir) / f"{name}.parquet")
        parts.append(part.assign(split=name))
    df = pd.concat(parts, ignore_index=True)
    df["subtype"] = "unspecified"
    uci_spam = (df["source"] == UCI_SOURCE) & (df["label"] == "scam")
    df.loc[uci_spam, "subtype"] = df.loc[uci_spam, "text_raw"].map(uci_spam_subtype)
    df.loc[df["is_synthetic"] & (df["label"] == "scam"), "subtype"] = "fraud"
    df["original_label"] = df["label"]
    return df


# --------------------------------------------------------------------------- #
# Audit, India rows, policy
# --------------------------------------------------------------------------- #
def apply_audit(df: pd.DataFrame, actions: dict[str, str]) -> tuple[pd.DataFrame, dict]:
    """Apply the owner-approved synthetic audit (``row_id -> keep|flip|remove``) to synthetic rows."""
    out = df.copy()
    syn = out["is_synthetic"]
    ids = pd.Series(np.nan, index=out.index, dtype=object)
    ids[syn] = out.loc[syn, "text_raw"].map(la.row_id)
    action = ids.map(actions)
    report = {"synthetic_rows": int(syn.sum()), "matched": int(action.notna().sum()),
              **{a: int((action == a).sum()) for a in la.DECISIONS}}
    flip = action == "flip"
    to_safe, to_scam = flip & (out["label"] == "scam"), flip & (out["label"] == "safe")
    out.loc[to_safe, ["label", "scam_type", "subtype"]] = ["safe", "none", "unspecified"]
    out.loc[to_scam, ["label", "scam_type", "subtype"]] = ["scam", "unknown", "fraud"]
    return out[action != "remove"].reset_index(drop=True), report


def build_india_rows(reference: pd.DataFrame, raw_dir: Path = Path("data/raw"), seed: int = SEED) -> tuple[pd.DataFrame, dict]:
    """India SMS rows in the reference schema: cleaned, masked, deduplicated against the reference, split-assigned."""
    spec = KAGGLE_SPECS[INDIA_SPEC]
    raw = load_kaggle(spec, Path(raw_dir) / "kaggle", download=False)
    combined, merge_report = merge_sources({"india": raw})
    df = preprocess_frame(combined)
    df["id"] = df["text"].map(make_id)
    n_in = len(df)
    df, exact = remove_exact_duplicates(df)
    df, near = remove_near_duplicates(df)
    dup_ref, _ = cross_near_duplicates(df["text"].tolist(), reference["text"].tolist())
    df = df[~dup_ref].reset_index(drop=True)
    df["original_label"] = df["label"]
    df["split"] = assign_splits(df, seed)
    report = {"loaded": len(raw), "after_merge": len(combined), "after_masking": n_in,
              "exact_duplicates": exact, "near_duplicates_removed": near["removed"],
              "overlap_with_reference": int(dup_ref.sum()), "kept": len(df),
              "by_split": df["split"].value_counts().to_dict(),
              "by_label_subtype": {f"{k[0]}/{k[1]}": int(v) for k, v in df.groupby(["label", "subtype"]).size().items()}}
    return df, report


def assign_splits(df: pd.DataFrame, seed: int = SEED, fractions: tuple[float, float, float] = SPLIT_FRACTIONS) -> np.ndarray:
    """Train/val/test assignment stratified by label and subtype (rare strata are merged, never crash)."""
    _, val_frac, test_frac = fractions
    strata = _strata(df.assign(source=df["subtype"]))
    idx = np.arange(len(df))
    rest, test = train_test_split(idx, test_size=test_frac, stratify=strata, random_state=seed)
    train, val = train_test_split(rest, test_size=val_frac / (1 - test_frac), stratify=strata.iloc[rest], random_state=seed)
    out = np.empty(len(df), dtype=object)
    out[train], out[val], out[test] = "train", "val", "test"
    return out


def apply_policy(df: pd.DataFrame, policy: str) -> pd.DataFrame:
    """Scam-definition policy for UCI/India "spam" rows that are legitimate promotions or service notices.

    Adds ``benchmark`` (True for those rows under every policy, so their behaviour can always be
    measured) and ``withheld`` (excluded from training and headline metrics: policy ``D``).
    ``A`` relabels them ``safe``; ``old`` leaves them ``scam`` (Phase 3 behaviour).
    """
    if policy not in ("old", "D", "A"):
        raise ValueError(f"unknown policy {policy!r}")
    out = df.copy()
    legit = out["source"].isin([UCI_SOURCE, INDIA_SOURCE]) & (out["original_label"] == "scam") & out["subtype"].isin(LEGIT_SUBTYPES)
    out["benchmark"] = legit
    out["withheld"] = legit & (policy == "D")
    if policy == "A":
        out.loc[legit, "label"] = "safe"
        out.loc[legit, "scam_type"] = "none"
    return out


# --------------------------------------------------------------------------- #
# Normalisation
# --------------------------------------------------------------------------- #
def renormalize(df: pd.DataFrame, cfg: nz.NormalizeConfig, threshold: float = NEAR_DUP_THRESHOLD) -> tuple[pd.DataFrame, dict]:
    """Re-derive the model text from ``text_raw`` under ``cfg`` and rebuild clean splits.

    Rows dropped by ``cfg`` disappear; the rest are re-masked, deduplicated within each split
    (exact then near duplicates, label conflicts dropped) and finally trimmed so no validation or
    test row resembles a training row. Train is never trimmed, so surviving rows keep their split.
    """
    kept, dropped = nz.filter_rows(df, cfg, column="text_raw")
    inputs = kept.drop(columns=["text", "urls"]).assign(text=kept["text_raw"]).drop(columns=["text_raw"])
    rebuilt = preprocess_frame(inputs, cfg)                    # sets text_raw (= input), masked text, urls
    rebuilt["id"] = rebuilt["text"].map(make_id)
    parts, stats = {}, {"dropped_by_rule": dropped, "rows_after_filter": len(kept)}
    for name in SPLIT_NAMES:
        part = rebuilt[rebuilt["split"] == name]
        part, exact = remove_exact_duplicates(part)
        part, near = remove_near_duplicates(part, threshold)
        parts[name] = part.reset_index(drop=True)
        stats[f"{name}_dedup"] = {"exact": exact["removed"] + exact["conflict_rows"], "near": near["removed"]}
    train, val, test, trimmed = trim_cross_split_leakage(parts["train"], parts["val"], parts["test"], threshold)
    stats["leakage_trimmed"] = trimmed
    return pd.concat([train, val, test], ignore_index=True), stats


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #
def load_audit_actions(path: Path = la.AUDIT_DIR / "decisions_final.csv") -> dict[str, str]:
    """``row_id -> action`` from the finalized synthetic audit."""
    return {d.row_id: d.action for d in la.load_decisions(path)}


def build_level(
    level: Level | str,
    reference: pd.DataFrame,
    india: pd.DataFrame | None,
    actions: dict[str, str],
) -> LevelData:
    """Assemble train/val/test frames for ``level`` from the reference (and India) rows."""
    level = LEVELS[level] if isinstance(level, str) else level
    report: dict = {"level": level.name, "description": level.description}
    df = reference.copy()
    if level.audit:
        df, report["audit"] = apply_audit(df, actions)
    if level.india:
        if india is None:
            raise ValueError("this level needs the India rows (build_india_rows)")
        df = pd.concat([df, india], ignore_index=True)
    df = apply_policy(df, level.policy)
    if level.normalize != nz.NONE:
        df, report["normalize"] = renormalize(df, level.normalize)
    parts = {name: df[df["split"] == name].reset_index(drop=True) for name in SPLIT_NAMES}
    if level.normalize != nz.NONE or level.india:
        check_split_integrity(parts["train"], parts["val"], parts["test"])
    report["rows"] = {name: len(p) for name, p in parts.items()}
    return LevelData(level, parts["train"], parts["val"], parts["test"], report)


def describe(data: LevelData) -> dict:
    """Counts per split, label, source and withheld/benchmark rows (for the report)."""
    out: dict = {}
    for name, frame in data.frames().items():
        out[name] = {
            "rows": len(frame),
            "by_label": frame["label"].value_counts().to_dict(),
            "by_source": frame["source"].value_counts().to_dict(),
            "withheld": int(frame["withheld"].sum()),
            "benchmark": int(frame["benchmark"].sum()),
        }
    return out
