"""Shared schema for the combined scam/safe dataset.

Every data loader returns a DataFrame with exactly :data:`COLUMNS`; the merge
step calls :func:`validate_frame` so a malformed source fails loudly instead of
silently corrupting ``combined.parquet``.
"""
from __future__ import annotations

import pandas as pd

# Column order of combined.parquet. ``generator`` records "provider/model" for
# synthetic rows and is null for real data. ``subtype`` says *what kind* of message a row is
# when that is known: ``fraud`` (deceptive, aims at money/credentials), ``promo`` (legitimate
# commercial promotion labelled spam by its source), ``service`` (transactional notice or
# personal message that a source labelled spam), else ``unspecified``. It never changes the
# binary ``label``.
COLUMNS: list[str] = [
    "text",
    "label",
    "scam_type",
    "language",
    "source",
    "is_synthetic",
    "generator",
    "subtype",
]

SUBTYPE_UNSPECIFIED = "unspecified"
SUBTYPES: frozenset[str] = frozenset({SUBTYPE_UNSPECIFIED, "fraud", "promo", "service"})

LABEL_SCAM = "scam"
LABEL_SAFE = "safe"
LABELS: frozenset[str] = frozenset({LABEL_SCAM, LABEL_SAFE})

# Scam categories targeted by the synthetic generator.
SYNTHETIC_SCAM_TYPES: tuple[str, ...] = (
    "fake_kyc",
    "lottery",
    "courier_customs",
    "job_offer",
    "electricity_bill",
    "loan_offer",
    "fake_bank_otp",
)
# Real datasets rarely say *what kind* of scam a message is.
SCAM_TYPE_GENERIC_SPAM = "generic_spam"  # promotional spam (UCI SMS)
SCAM_TYPE_UNKNOWN = "unknown"            # scam/phishing of unspecified type
SCAM_TYPE_NONE = "none"                  # safe messages
SCAM_TYPES: frozenset[str] = frozenset(
    {*SYNTHETIC_SCAM_TYPES, SCAM_TYPE_GENERIC_SPAM, SCAM_TYPE_UNKNOWN, SCAM_TYPE_NONE}
)


def empty_frame() -> pd.DataFrame:
    """Return an empty DataFrame with the combined-dataset columns."""
    return pd.DataFrame({c: pd.Series(dtype=object) for c in COLUMNS}).astype(
        {"is_synthetic": bool}
    )


def make_frame(
    texts: list[str],
    labels: list[str],
    *,
    source: str,
    scam_type: str | list[str] | None = None,
    language: str | list[str] = "en",
    is_synthetic: bool = False,
    generator: str | list[str | None] | None = None,
    subtype: str | list[str] = SUBTYPE_UNSPECIFIED,
) -> pd.DataFrame:
    """Build a schema-conformant DataFrame from parallel lists.

    ``scam_type`` may be a single value or a per-row list. If omitted it
    defaults to ``unknown`` for scam rows and ``none`` for safe rows.
    """
    n = len(texts)
    if scam_type is None:
        scam_type = [
            SCAM_TYPE_UNKNOWN if lab == LABEL_SCAM else SCAM_TYPE_NONE for lab in labels
        ]
    elif isinstance(scam_type, str):
        scam_type = [scam_type] * n
    if isinstance(language, str):
        language = [language] * n
    if generator is None or isinstance(generator, str):
        generator = [generator] * n
    if isinstance(subtype, str):
        subtype = [subtype] * n
    df = pd.DataFrame(
        {
            "text": texts,
            "label": labels,
            "scam_type": scam_type,
            "language": language,
            "source": [source] * n,
            "is_synthetic": [is_synthetic] * n,
            "generator": generator,
            "subtype": subtype,
        }
    )
    return df[COLUMNS].astype({"is_synthetic": bool})


def validate_frame(df: pd.DataFrame, name: str = "frame") -> pd.DataFrame:
    """Check that ``df`` follows the combined-dataset schema.

    Raises:
        ValueError: On missing/extra columns, empty text, or unknown
            label/scam_type values.

    Returns:
        The same DataFrame, to allow call chaining.
    """
    if list(df.columns) != COLUMNS:
        raise ValueError(f"{name}: columns {list(df.columns)} != expected {COLUMNS}")
    if df.empty:
        return df
    if df["text"].isna().any() or (df["text"].astype(str).str.strip() == "").any():
        raise ValueError(f"{name}: empty or null text")
    bad_labels = set(df["label"].unique()) - LABELS
    if bad_labels:
        raise ValueError(f"{name}: invalid labels {sorted(bad_labels)}")
    bad_types = set(df["scam_type"].unique()) - SCAM_TYPES
    if bad_types:
        raise ValueError(f"{name}: invalid scam_type values {sorted(bad_types)}")
    if df["source"].isna().any() or df["language"].isna().any():
        raise ValueError(f"{name}: null source or language")
    bad_subtypes = set(df["subtype"].unique()) - SUBTYPES
    if bad_subtypes:
        raise ValueError(f"{name}: invalid subtype values {sorted(bad_subtypes)}")
    return df
