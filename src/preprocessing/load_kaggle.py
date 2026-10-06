"""Load phishing-email datasets from Kaggle through a small registry.

Adding a dataset means adding one :class:`KaggleSpec` to :data:`KAGGLE_SPECS`;
no loader code changes are needed. Credentials come from the environment
(``KAGGLE_API_TOKEN`` in ``.env``) - see ``.env.example``.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import pandas as pd

from src.preprocessing.india_sms import repair_mojibake, spam_subtype
from src.preprocessing.schema import (
    LABEL_SAFE,
    LABEL_SCAM,
    SCAM_TYPE_GENERIC_SPAM,
    SCAM_TYPE_UNKNOWN,
    SUBTYPE_UNSPECIFIED,
    make_frame,
    validate_frame,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class KaggleSpec:
    """Describes how to turn one Kaggle CSV into the shared schema."""

    slug: str                 # "owner/dataset-name"
    filename: str             # CSV inside the downloaded archive
    text_col: str
    label_col: str
    label_map: dict[str, str] = field(default_factory=dict)  # raw label -> scam/safe
    source: str = ""          # short name stored in the ``source`` column
    # Optional per-row subtype for scam rows (promo / fraud / service); None keeps "unspecified".
    subtype_fn: Callable[[str], str] | None = None
    repair_text: bool = False  # undo mojibake in the text column

    @property
    def dirname(self) -> str:
        """Folder name under ``data/raw/kaggle`` for this dataset."""
        return self.slug.replace("/", "_")


KAGGLE_SPECS: dict[str, KaggleSpec] = {
    "subhajournal_phishingemails": KaggleSpec(
        slug="subhajournal/phishingemails",
        filename="Phishing_Email.csv",
        text_col="Email Text",
        label_col="Email Type",
        label_map={"Phishing Email": LABEL_SCAM, "Safe Email": LABEL_SAFE},
        source="kaggle_subhajournal_phishingemails",
    ),
    # Phase 3.5: real Indian SMS. A spot check showed spam = ~90% brand promotions, ham = stock-group
    # chat (see src/preprocessing/india_sms.py); rows carry a promo/fraud/service subtype.
    "junioralive_india_spam_sms": KaggleSpec(
        slug="junioralive/india-spam-sms-classification",
        filename="spam_ham_india.csv",
        text_col="Msg",
        label_col="Label",
        label_map={"spam": LABEL_SCAM, "ham": LABEL_SAFE},
        source="kaggle_india_spam_sms",
        subtype_fn=spam_subtype,
        repair_text=True,
    ),
}


def download_kaggle(spec: KaggleSpec, raw_dir: Path) -> Path:
    """Download and unzip ``spec`` into ``raw_dir / spec.dirname``.

    Requires Kaggle credentials in the environment. Skipped if the CSV is
    already present.

    Returns:
        Path to the dataset's CSV file.
    """
    dest = Path(raw_dir) / spec.dirname
    csv_path = dest / spec.filename
    if csv_path.exists():
        logger.info("Kaggle data already present: %s", csv_path)
        return csv_path
    from dotenv import load_dotenv

    load_dotenv()  # must happen before importing kaggle, which authenticates on import
    import kaggle  # noqa: PLC0415  (lazy import: needs credentials at import time)

    dest.mkdir(parents=True, exist_ok=True)
    kaggle.api.authenticate()
    kaggle.api.dataset_download_files(spec.slug, path=str(dest), unzip=True, quiet=True)
    if not csv_path.exists():
        raise FileNotFoundError(f"{spec.filename} not found in downloaded {spec.slug}")
    return csv_path


def parse_kaggle(path: Path, spec: KaggleSpec) -> pd.DataFrame:
    """Parse a Kaggle CSV into the shared schema using ``spec``.

    Rows with missing text, or a label not in ``spec.label_map``, are skipped.
    """
    df = pd.read_csv(path, usecols=[spec.text_col, spec.label_col])
    df = df.dropna(subset=[spec.text_col, spec.label_col])
    df = df[df[spec.text_col].astype(str).str.strip() != ""]  # blank bodies exist in real data
    df["_label"] = df[spec.label_col].astype(str).str.strip().map(spec.label_map)
    df = df.dropna(subset=["_label"])
    texts = df[spec.text_col].astype(str).tolist()
    if spec.repair_text:
        texts = [repair_mojibake(t) for t in texts]
    labels = df["_label"].tolist()
    kwargs: dict = {}
    if spec.subtype_fn is not None:
        subtypes = [spec.subtype_fn(t) if lab == LABEL_SCAM else SUBTYPE_UNSPECIFIED for t, lab in zip(texts, labels)]
        kwargs["subtype"] = subtypes
        # Fraud rows are a different kind of scam than generic promotional spam.
        kwargs["scam_type"] = [
            "none" if lab == LABEL_SAFE else (SCAM_TYPE_UNKNOWN if sub == "fraud" else SCAM_TYPE_GENERIC_SPAM)
            for lab, sub in zip(labels, subtypes)
        ]
    return validate_frame(
        make_frame(texts, labels, source=spec.source, language="en", **kwargs),
        spec.source,
    )


def load_kaggle(
    spec: KaggleSpec, raw_dir: Path, download: bool = True
) -> pd.DataFrame:
    """Load one Kaggle dataset, downloading it first if needed."""
    raw_dir = Path(raw_dir)
    path = (
        download_kaggle(spec, raw_dir) if download else raw_dir / spec.dirname / spec.filename
    )
    return parse_kaggle(path, spec)
