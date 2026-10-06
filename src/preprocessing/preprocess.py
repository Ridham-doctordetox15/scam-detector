"""Phase 2 preprocessing: cleaning, masking, deduplication and splitting.

Pipeline (see :func:`run_preprocessing`)::

    combined.parquet
      -> clean_text            unicode/whitespace normalisation
      -> mask_urls/otps/phones URLs -> <URL> (originals kept in ``urls``),
                               OTPs -> <OTP>, phone numbers -> <PHONE>
      -> exact dedup           on the *masked* text
      -> near-duplicate dedup  TF-IDF cosine >= 0.90, one row kept per cluster
      -> stratified split      70/15/15; test set is 100% real data
      -> leakage audit         nothing similar across splits

Two design points worth knowing:

* Deduplication runs on the **masked** text, so scam templates that differ only
  by a phone number, link or OTP collapse into one row. Doing it on raw text
  would leave those siblings free to land on both sides of the split.
* Near-duplicates are found with sparse TF-IDF cosine similarity (word 1-2-grams,
  digits collapsed to ``0``, first 3,000 characters), computed exactly in
  chunks, then joined into clusters with connected components. It needs no extra
  dependency, is deterministic, and is fast at this scale (the whole pipeline takes
  about a minute for 25k rows).
  Connected components can chain A~B and B~C; that only removes *more*, which
  errs on the side of preventing leakage.

Usage::

    python -m src.preprocessing.preprocess
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
import scipy.sparse as sp
from scipy.sparse.csgraph import connected_components
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.model_selection import train_test_split

from src.preprocessing.normalize import NormalizeConfig, normalize_text
from src.preprocessing.schema import COLUMNS

logger = logging.getLogger(__name__)

URL_TOKEN = "<URL>"
PHONE_TOKEN = "<PHONE>"
OTP_TOKEN = "<OTP>"

DEFAULT_INPUT = Path("data/processed/combined.parquet")
DEFAULT_OUTPUT_DIR = Path("data/processed")
DEFAULT_SEED = 42
NEAR_DUP_THRESHOLD = 0.90
SENSITIVITY_THRESHOLDS = (0.80, 0.90, 0.95)
SPLIT_FRACTIONS = (0.70, 0.15, 0.15)  # train / val / test
NEAR_DUP_CHARS = 3_000                # only the start of a text is compared
MIN_STRATUM_SIZE = 10                 # smaller strata are merged before splitting


# --------------------------------------------------------------------------- #
# Cleaning
# --------------------------------------------------------------------------- #
# Invisible characters to drop. ZWNJ (U+200C) and ZWJ (U+200D) are deliberately kept:
# Indic scripts need them to form correct conjuncts.
_INVISIBLE = dict.fromkeys(map(ord, "﻿​‎‏⁠­"), None)


def clean_text(text: str) -> str:
    """Normalise ``text`` without changing its meaning.

    NFC-normalises Unicode, drops control characters and invisible marks (except
    ZWJ/ZWNJ), and collapses every run of whitespace to one space. Case and
    punctuation are left untouched because they are useful scam signals.
    """
    text = unicodedata.normalize("NFC", text).translate(_INVISIBLE)
    text = "".join(" " if unicodedata.category(c) == "Cc" else c for c in text)
    return " ".join(text.split())


# --------------------------------------------------------------------------- #
# Masking
# --------------------------------------------------------------------------- #
_URL_END = r"""[^\s<>"'\)\]।]"""
_TLDS = (
    "com|in|net|org|co|info|biz|xyz|top|club|online|site|link|live|app|shop|store|vip|cc|tk|"
    "ml|ga|cf|gq|ly|me|us|io|gov|edu|ru|cn|uk|page|help|support|click|work|cyou|icu"
)
_URL_RE = re.compile(
    rf"""
    (?:https?://|ftp://|www\.){_URL_END}+                         # explicit scheme / www
    |
    (?<![@\w.-])                                                   # not part of an e-mail/word
    (?:[a-z0-9-]+\.)+(?:{_TLDS})(?![a-z0-9-])(?:/{_URL_END}*)?     # bare domain[/path]
    """,
    re.IGNORECASE | re.VERBOSE,
)
_URL_TRAILING = ".,;:!?)]}>'\""


def mask_urls(text: str) -> tuple[str, list[str]]:
    """Replace URLs with ``<URL>`` and return the originals in order.

    Handles ``http(s)://``, ``www.`` and bare domains/shortlinks (``bit.ly/x``,
    ``sbi.co.in``). Trailing punctuation is not treated as part of the URL, and
    e-mail addresses are left alone.
    """
    found: list[str] = []

    def _sub(m: re.Match[str]) -> str:
        url = m.group(0)
        stripped = url.rstrip(_URL_TRAILING)
        if not stripped:
            return url
        found.append(stripped)
        return URL_TOKEN + url[len(stripped):]

    return _URL_RE.sub(_sub, text), found


def extract_urls(text: str) -> list[str]:
    """Return the URLs found in ``text`` (see :func:`mask_urls`)."""
    return mask_urls(text)[1]


# Words that introduce an OTP. Devanagari "ओटीपी" needs no Latin word boundary.
_OTP_KEYWORD = (
    r"(?:(?<![a-z])(?:o\.?t\.?p|one[\s-]?time[\s-]?(?:password|pin|passcode|code)|"
    r"verification[\s-]?(?:code|pin)|security[\s-]?code|authentication[\s-]?code|"
    r"login[\s-]?code|passcode)(?![a-z])|ओटीपी)"
)
_OTP_NUMBER = r"(?:(?<!\d)\d{4,8}(?!\d)|(?<!\d)\d{3}[ -]\d{3}(?!\d))"
# Filler between keyword and number: no digits, no sentence breaks, short.
_OTP_GAP = r"[^\d\n.!?]{0,20}?"
_OTP_AFTER = re.compile(
    rf"(?P<kw>{_OTP_KEYWORD})(?P<gap>{_OTP_GAP})(?P<num>{_OTP_NUMBER})", re.IGNORECASE
)
_OTP_BEFORE = re.compile(
    rf"(?P<num>{_OTP_NUMBER})(?P<gap>{_OTP_GAP})(?P<kw>{_OTP_KEYWORD})", re.IGNORECASE
)


def mask_otps(text: str) -> str:
    """Replace one-time codes with ``<OTP>``.

    Only a 4-8 digit number (or ``123 456``) that sits next to an OTP-style keyword
    is masked, in either order ("OTP is 4521", "4521 is your OTP"). A bare number
    is left alone because it is far more often an amount, PIN code or ID.
    """
    text = _OTP_AFTER.sub(lambda m: f"{m['kw']}{m['gap']}{OTP_TOKEN}", text)
    return _OTP_BEFORE.sub(lambda m: f"{OTP_TOKEN}{m['gap']}{m['kw']}", text)


_SEP = r"[\s.-]?"
_PHONE_RE = re.compile(
    rf"""
    (?<![\d\w])                                                   # not inside a longer token
    (?:
        # Indian mobile: optional +91 / 91 / 0 prefix, 10 digits starting 6-9,
        # written as 10 contiguous digits, 5+5, or 3+3+4.
        (?:\+91{_SEP}|91{_SEP}|0)?
        (?:[6-9]\d{{4}}{_SEP}\d{{5}}|[6-9]\d{{2}}{_SEP}\d{{3}}{_SEP}\d{{4}})
      |
        # Toll-free 1800 / 1860
        1(?:800|860){_SEP}\d{{2,4}}{_SEP}\d{{3,4}}
      |
        # Landline with STD code and a separator, e.g. 011-23456789 or +91 11 23456789.
        # A leading 0 or +91 is required, otherwise "Ref 4321 123456" would match.
        (?:\+91{_SEP}\d{{2,4}}[\s-]|0\d{{1,4}}[\s-])\d{{6,8}}
      |
        # Other international numbers, e.g. +44 7911 123456
        \+(?!91)\d{{1,3}}[\s-]?\(?\d{{2,5}}\)?(?:[\s-]?\d{{2,5}}){{1,3}}
    )
    (?![\d\w])
    """,
    re.VERBOSE,
)


def mask_phones(text: str) -> str:
    """Replace phone numbers with ``<PHONE>``.

    Covers Indian mobiles (with or without +91/91/0 and common separators),
    toll-free 1800/1860 numbers, STD landlines and ``+CC`` international numbers.
    Amounts (``Rs 1,50,000``), dates and long IDs are not touched.
    """
    return _PHONE_RE.sub(PHONE_TOKEN, text)


def mask_text(text: str) -> tuple[str, list[str]]:
    """Mask URLs, then OTPs, then phones (this order matters).

    URLs go first so digits inside a link cannot be mistaken for a phone number;
    OTPs go before phones so a code next to an OTP keyword is not eaten by the
    generic number patterns.

    Returns:
        ``(masked_text, original_urls)``.
    """
    text, urls = mask_urls(text)
    text = mask_otps(text)
    return mask_phones(text), urls


def preprocess_text(raw: str) -> tuple[str, list[str]]:
    """Clean then mask one message. Returns ``(model_text, original_urls)``."""
    return mask_text(clean_text(raw))


def preprocess_frame(df: pd.DataFrame, normalize_cfg: "NormalizeConfig | None" = None) -> pd.DataFrame:
    """Add ``text_raw`` (input text), masked ``text`` and ``urls`` columns.

    If ``normalize_cfg`` is given, its text transformations (quote markers, reply boilerplate,
    years, currency, spacing) run *before* cleaning and masking; ``text_raw`` still holds the
    untouched original. Row dropping is a separate step (``normalize.filter_rows``).

    The returned frame has ``text`` replaced by the cleaned/masked version, the
    original in ``text_raw`` (for error analysis only, never a model input) and
    the extracted originals in ``urls`` (a list per row, for the URL analyzer).
    Rows whose cleaned text is empty are dropped.
    """
    out = df.copy()
    out["text_raw"] = out["text"]
    source_texts = out["text_raw"]
    if normalize_cfg is not None and normalize_cfg.transforms_text:
        source_texts = source_texts.map(lambda t: normalize_text(str(t), normalize_cfg))
    processed = [preprocess_text(t) for t in source_texts]
    out["text"] = [t for t, _ in processed]
    out["urls"] = [u for _, u in processed]
    out = out[out["text"].str.strip() != ""].reset_index(drop=True)
    return out


def make_id(text: str) -> str:
    """Stable 12-hex-character id derived from the masked text."""
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:12]


# --------------------------------------------------------------------------- #
# Deduplication
# --------------------------------------------------------------------------- #
def dedup_key(text: str) -> str:
    """Case-insensitive, whitespace-collapsed key for exact-duplicate detection."""
    return " ".join(text.casefold().split())


def _prefer_real_first(df: pd.DataFrame) -> pd.DataFrame:
    """Stable-sort so real rows precede synthetic ones (so real rows survive dedup).

    If the frame has an ``is_new`` column (rows that had no split in the reference build), rows
    that already have a split come first, so a stable rebuild never replaces an assigned row.
    """
    keys = ["is_synthetic"] + (["is_new"] if "is_new" in df.columns else [])
    return df.sort_values(keys, kind="stable").reset_index(drop=True)


def remove_exact_duplicates(df: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, int]]:
    """Drop exact duplicates (on masked text) and label-conflicting texts.

    A text that appears with both labels is ambiguous, so all its copies are
    dropped. Otherwise the first copy wins, with real rows preferred over
    synthetic ones.

    Returns:
        ``(frame, stats)``; stats has ``removed`` (redundant copies) and
        ``conflict_rows`` (rows dropped for conflicting labels).
    """
    work = _prefer_real_first(df)
    work["_key"] = work["text"].map(dedup_key)
    conflict = work.groupby("_key")["label"].transform("nunique") > 1
    work = work[~conflict]
    dup = work.duplicated("_key", keep="first")
    stats = {"removed": int(dup.sum()), "conflict_rows": int(conflict.sum())}
    return work[~dup].drop(columns="_key").reset_index(drop=True), stats


def _tfidf(texts: list[str]) -> sp.csr_matrix:
    """Fit the TF-IDF representation used for near-duplicate comparison.

    ``min_df=1`` is deliberate: pruning words that appear in only one text would
    reduce short, unrelated messages to the few words they share (e.g. "the",
    "your"), making them look identical.
    """
    vec = TfidfVectorizer(
        ngram_range=(1, 2),
        min_df=1,
        sublinear_tf=True,
        dtype=np.float32,
        preprocessor=lambda t: re.sub(r"\d+", "0", t.casefold())[:NEAR_DUP_CHARS],
    )
    try:
        return vec.fit_transform(texts).tocsr()
    except ValueError:  # empty vocabulary (e.g. tiny or all-unique corpus)
        return sp.csr_matrix((len(texts), 1), dtype=np.float32)


def similar_pairs(
    texts: list[str], min_similarity: float, chunk: int = 1000
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """All pairs ``i < j`` with TF-IDF cosine similarity >= ``min_similarity``.

    Exact (not approximate); computed chunk by chunk with sparse products.

    Returns:
        Arrays ``(rows, cols, similarities)``.
    """
    n = len(texts)
    empty = (np.array([], dtype=int), np.array([], dtype=int), np.array([], dtype=np.float32))
    if n < 2:
        return empty
    x = _tfidf(texts)
    xt = x.T.tocsr()
    rows, cols, sims = [], [], []
    for start in range(0, n, chunk):
        s = (x[start:start + chunk] @ xt).tocoo()
        keep = (s.row + start < s.col) & (s.data >= min_similarity)
        rows.append(s.row[keep] + start)
        cols.append(s.col[keep])
        sims.append(s.data[keep])
    return np.concatenate(rows), np.concatenate(cols), np.concatenate(sims)


def _clusters(n: int, rows: np.ndarray, cols: np.ndarray) -> np.ndarray:
    """Cluster ids from similar-pair edges (connected components)."""
    graph = sp.coo_matrix((np.ones(len(rows)), (rows, cols)), shape=(n, n))
    return connected_components(graph, directed=False)[1]


def near_duplicate_sensitivity(
    texts: list[str], thresholds: tuple[float, ...] = SENSITIVITY_THRESHOLDS
) -> dict[float, int]:
    """How many rows would be removed at each similarity threshold."""
    lo = min(thresholds)
    rows, cols, sims = similar_pairs(texts, lo)
    out: dict[float, int] = {}
    for th in thresholds:
        keep = sims >= th
        labels = _clusters(len(texts), rows[keep], cols[keep])
        out[th] = len(texts) - int(labels.max() + 1) if len(texts) else 0
    return out


def remove_near_duplicates(
    df: pd.DataFrame, threshold: float = NEAR_DUP_THRESHOLD
) -> tuple[pd.DataFrame, dict[str, float | int]]:
    """Keep one row per cluster of near-identical texts.

    Rows are clustered by TF-IDF cosine similarity >= ``threshold``. In each
    cluster the first row survives, with real rows ahead of synthetic ones. A
    cluster containing both labels is dropped entirely (ambiguous).

    Returns:
        ``(frame, stats)`` with ``removed``, ``removed_real``, ``removed_synthetic``,
        ``clusters`` (clusters with more than one row), ``max_cluster`` and
        ``mixed_label_rows`` (rows lost to mixed-label clusters, included in ``removed``).
    """
    work = _prefer_real_first(df)
    n = len(work)
    rows, cols, _ = similar_pairs(work["text"].tolist(), threshold)
    cluster = _clusters(n, rows, cols) if n else np.array([], dtype=int)
    work["_cluster"] = cluster
    sizes = work.groupby("_cluster")["label"].transform("size")
    mixed = work.groupby("_cluster")["label"].transform("nunique") > 1
    dup = work.duplicated("_cluster", keep="first")
    drop = dup | mixed
    stats = {
        "threshold": threshold,
        "removed": int(drop.sum()),
        "removed_real": int((drop & ~work["is_synthetic"]).sum()),
        "removed_synthetic": int((drop & work["is_synthetic"]).sum()),
        "clusters": int((work.groupby("_cluster").size() > 1).sum()) if n else 0,
        "max_cluster": int(sizes.max()) if n else 0,
        "mixed_label_rows": int(mixed.sum()),
    }
    return work[~drop].drop(columns="_cluster").reset_index(drop=True), stats


def cross_near_duplicates(
    new_texts: list[str], reference_texts: list[str], threshold: float = NEAR_DUP_THRESHOLD, chunk: int = 1000
) -> tuple[np.ndarray, np.ndarray]:
    """Flag ``new_texts`` that are exact or near duplicates of any reference text.

    Returns:
        ``(is_duplicate, max_similarity)`` arrays aligned with ``new_texts``. Used
        both for the leakage audit and for deduplicating the hand-collected
        Indian test set against train/val/test.
    """
    n_new = len(new_texts)
    if n_new == 0 or not reference_texts:
        return np.zeros(n_new, dtype=bool), np.zeros(n_new, dtype=np.float32)
    x = _tfidf(list(reference_texts) + list(new_texts))
    ref, new = x[: len(reference_texts)], x[len(reference_texts):]
    ref_t = ref.T.tocsr()
    max_sim = np.zeros(n_new, dtype=np.float32)
    for start in range(0, n_new, chunk):
        block = (new[start:start + chunk] @ ref_t).tocsr()
        if block.nnz:
            max_sim[start:start + block.shape[0]] = block.max(axis=1).toarray().ravel()
    exact = {dedup_key(t) for t in reference_texts}
    is_exact = np.array([dedup_key(t) in exact for t in new_texts])
    return (max_sim >= threshold) | is_exact, max_sim


# --------------------------------------------------------------------------- #
# Splitting
# --------------------------------------------------------------------------- #
def _strata(df: pd.DataFrame) -> pd.Series:
    """Stratification key ``label|source``; rare strata are merged, never crash.

    Rare strata are merged locally so one tiny source does not coarsen everything:
    strata smaller than MIN_STRATUM_SIZE are pooled into ``label|other``; a pool that
    is still smaller than 2 rows joins the largest stratum with the same label.
    Only if some stratum is *still* too small does the key fall back to the label.
    """
    key = df["label"] + "|" + df["source"]
    small = key.map(key.value_counts()) < MIN_STRATUM_SIZE
    key = key.where(~small, df["label"] + "|other")
    counts = key.value_counts()
    for stratum in counts[counts < 2].index:
        label = stratum.split("|")[0]
        siblings = counts[[k for k in counts.index if k.startswith(f"{label}|") and k != stratum]]
        if not siblings.empty:
            key = key.replace(stratum, siblings.idxmax())
    if (key.map(key.value_counts()) < 2).any():
        key = df["label"].copy()
    return key


def split_dataset(
    df: pd.DataFrame,
    seed: int = DEFAULT_SEED,
    fractions: tuple[float, float, float] = SPLIT_FRACTIONS,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Stratified train/val/test split where the test set is 100% real data.

    Sizes are fractions of the *whole* dataset. The test set is drawn from real
    rows only (stratified by label and source). The remaining real rows plus all
    synthetic rows are then split into train and validation, so synthetic data
    appears in train and validation in the same proportion and never in test.

    Args:
        df: Deduplicated frame with ``label``, ``source`` and ``is_synthetic``.
        seed: Random seed.
        fractions: ``(train, val, test)``; must sum to 1.

    Returns:
        ``(train, val, test)``.

    Raises:
        ValueError: If fractions are invalid or there are too few real rows.
    """
    if not np.isclose(sum(fractions), 1.0):
        raise ValueError(f"fractions must sum to 1, got {fractions}")
    _, val_frac, test_frac = fractions
    n = len(df)
    n_test, n_val = round(test_frac * n), round(val_frac * n)
    real = df[~df["is_synthetic"]]
    if n_test < 1 or n_val < 1:
        raise ValueError(f"dataset too small to split: {n} rows -> test={n_test}, val={n_val}")
    if n_test >= len(real):
        raise ValueError(f"need more real rows: test={n_test}, real={len(real)}")

    real_rest, test = train_test_split(
        real, test_size=n_test, stratify=_strata(real), random_state=seed
    )
    rest = pd.concat([real_rest, df[df["is_synthetic"]]])
    train, val = train_test_split(
        rest, test_size=n_val, stratify=_strata(rest), random_state=seed
    )
    shuffled = [
        part.sample(frac=1.0, random_state=seed).reset_index(drop=True) for part in (train, val, test)
    ]
    return shuffled[0], shuffled[1], shuffled[2]


def check_split_integrity(train: pd.DataFrame, val: pd.DataFrame, test: pd.DataFrame) -> None:
    """Hard checks that must hold for any valid split.

    Raises:
        AssertionError: If the test set contains synthetic rows, or any id or
            exact (normalised) text appears in more than one split.
    """
    assert not test["is_synthetic"].any(), "synthetic rows found in the test set"
    parts = {"train": train, "val": val, "test": test}
    for a in parts:
        for b in parts:
            if a < b:
                assert not set(parts[a]["id"]) & set(parts[b]["id"]), f"id overlap {a}/{b}"
                keys_a = set(parts[a]["text"].map(dedup_key))
                keys_b = set(parts[b]["text"].map(dedup_key))
                assert not keys_a & keys_b, f"exact-text overlap {a}/{b}"


def trim_cross_split_leakage(
    train: pd.DataFrame,
    val: pd.DataFrame,
    test: pd.DataFrame,
    threshold: float = NEAR_DUP_THRESHOLD,
    max_rounds: int = 10,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict[str, int]]:
    """Drop held-out rows that still resemble rows in a split they must be disjoint from.

    Clustering ran on the full corpus, but removing rows shifts TF-IDF weights
    slightly, so a few pairs can sit just above the threshold when measured again
    after the split. This trims validation rows similar to train, and test rows
    similar to train or validation, using *exactly* the measurement
    :func:`leakage_audit` uses (each split pair compared on its own). It repeats
    until a full pass changes nothing, so the audit that follows reports zero
    by construction. Train is never trimmed.

    Returns:
        ``(train, val, test, trimmed)`` where ``trimmed`` counts rows dropped from
        ``val`` and ``test``.
    """
    trimmed = {"val": 0, "test": 0}
    for _ in range(max_rounds):
        changed = False
        for held_name, ref_name in (("val", "train"), ("test", "train"), ("test", "val")):
            held = val if held_name == "val" else test
            ref = {"train": train, "val": val}[ref_name]
            dup, _ = cross_near_duplicates(held["text"].tolist(), ref["text"].tolist(), threshold)
            if dup.any():
                held = held[~dup]
                trimmed[held_name] += int(dup.sum())
                changed = True
                if held_name == "val":
                    val = held
                else:
                    test = held
        if not changed:
            break
    return train, val.reset_index(drop=True), test.reset_index(drop=True), trimmed


def leakage_audit(
    train: pd.DataFrame, val: pd.DataFrame, test: pd.DataFrame, threshold: float = NEAR_DUP_THRESHOLD
) -> dict[str, dict[str, float | int]]:
    """Measure similarity across split boundaries (should be ~0 after dedup).

    For each pair (val vs train, test vs train, test vs val) reports the number
    of rows with a near-duplicate on the other side and the highest cosine
    similarity seen. TF-IDF statistics are refit here, so a handful of borderline
    pairs may appear even though clustering ran at the same threshold.
    """
    report: dict[str, dict[str, float | int]] = {}
    for name, (a, b) in {"val_vs_train": (val, train), "test_vs_train": (test, train), "test_vs_val": (test, val)}.items():
        dup, max_sim = cross_near_duplicates(a["text"].tolist(), b["text"].tolist(), threshold)
        report[name] = {
            "near_duplicate_rows": int(dup.sum()),
            "max_similarity": round(float(max_sim.max()), 4) if len(max_sim) else 0.0,
        }
    return report


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #
@dataclass
class PreprocessResult:
    """Outputs of :func:`run_preprocessing`."""

    train: pd.DataFrame
    val: pd.DataFrame
    test: pd.DataFrame
    deduplicated: pd.DataFrame
    report: dict


def run_preprocessing(
    input_path: Path = DEFAULT_INPUT,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    seed: int = DEFAULT_SEED,
    threshold: float = NEAR_DUP_THRESHOLD,
) -> PreprocessResult:
    """Run the full pipeline and write the results.

    Writes ``deduplicated.parquet``, ``train.parquet``, ``val.parquet``,
    ``test.parquet`` and ``split_report.json`` into ``output_dir``.
    """
    output_dir = Path(output_dir)
    df = pd.read_parquet(input_path)
    report: dict = {"input_rows": len(df), "seed": seed}

    df = preprocess_frame(df)
    df["id"] = df["text"].map(make_id)
    report["rows_after_cleaning"] = len(df)

    df, exact = remove_exact_duplicates(df)
    report["exact_duplicates"] = exact
    report["rows_after_exact_dedup"] = len(df)

    report["near_duplicate_sensitivity"] = {
        str(k): v for k, v in near_duplicate_sensitivity(df["text"].tolist()).items()
    }
    df, near = remove_near_duplicates(df, threshold)
    report["near_duplicates"] = near

    # The hand-collected real_indian_test set is evaluation-only. If it already exists,
    # nothing similar to it may enter train/val/test, whatever order the scripts run in.
    holdout_path = output_dir / "real_indian_test.parquet"
    report["holdout_overlap_removed"] = 0
    if holdout_path.exists():
        holdout_texts = pd.read_parquet(holdout_path, columns=["text"])["text"].tolist()
        overlap, _ = cross_near_duplicates(df["text"].tolist(), holdout_texts, threshold)
        report["holdout_overlap_removed"] = int(overlap.sum())
        df = df[~overlap].reset_index(drop=True)
    report["rows_after_dedup"] = len(df)

    train, val, test = split_dataset(df, seed)
    train, val, test, trimmed = trim_cross_split_leakage(train, val, test, threshold)
    report["leakage_trimmed"] = trimmed
    check_split_integrity(train, val, test)
    assert not test["is_synthetic"].any()
    report["leakage_audit"] = leakage_audit(train, val, test, threshold)

    ordered = [c for c in ["id", *COLUMNS, "urls", "text_raw"]]
    for name, part in (("deduplicated", df), ("train", train), ("val", val), ("test", test)):
        part[ordered].to_parquet(output_dir / f"{name}.parquet", index=False, engine="pyarrow")
    report["splits"] = {
        name: {
            "rows": len(part),
            "by_label": part["label"].value_counts().to_dict(),
            "synthetic": int(part["is_synthetic"].sum()),
            "by_source": part["source"].value_counts().to_dict(),
        }
        for name, part in (("train", train), ("val", val), ("test", test))
    }
    (output_dir / "split_report.json").write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    return PreprocessResult(train, val, test, df, report)


def format_report(report: dict) -> str:
    """Human-readable summary of a :func:`run_preprocessing` report."""
    ex, nd = report["exact_duplicates"], report["near_duplicates"]
    lines = [
        f"input rows:            {report['input_rows']:>8,}",
        f"after cleaning:        {report['rows_after_cleaning']:>8,}",
        f"exact duplicates:      {ex['removed']:>8,} removed (+{ex['conflict_rows']:,} label-conflict rows)",
        f"near duplicates:       {nd['removed']:>8,} removed at cosine >= {nd['threshold']} "
        f"({nd['removed_real']:,} real, {nd['removed_synthetic']:,} synthetic; "
        f"{nd['clusters']:,} clusters, largest {nd['max_cluster']:,}; {nd['mixed_label_rows']:,} mixed-label rows)",
        f"removed for overlap with real_indian_test: {report.get('holdout_overlap_removed', 0):,}",
        f"final rows:            {report['rows_after_dedup']:>8,}",
        "near-duplicate sensitivity (rows removed): "
        + ", ".join(f"{k}: {v:,}" for k, v in report["near_duplicate_sensitivity"].items()),
        "",
    ]
    for name, s in report["splits"].items():
        lines.append(f"{name:<6} {s['rows']:>7,} rows  labels={s['by_label']}  synthetic={s['synthetic']:,}")
    lines.append("")
    t = report.get("leakage_trimmed", {})
    lines.append(f"borderline rows trimmed after the split: val={t.get('val', 0)}, test={t.get('test', 0)}")
    for name, a in report["leakage_audit"].items():
        lines.append(f"leakage {name:<14} near-dup rows={a['near_duplicate_rows']}  max cosine={a['max_similarity']}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--threshold", type=float, default=NEAR_DUP_THRESHOLD)
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    result = run_preprocessing(args.input, args.output_dir, args.seed, args.threshold)
    print(format_report(result.report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
