"""Load the text subset of the Hugging Face ``ealvaradob/phishing-dataset``.

The repo ships a legacy loading script that ``datasets>=4`` refuses to run, so
the raw ``texts.json`` file (SMS + email, ~52 MB) is fetched directly with
``huggingface_hub``. The URL (``urls.json``) and HTML (``webs.json``) subsets
are intentionally skipped; the URL analyzer (Phase 5) has its own data needs.

Labels in the source: ``1`` = phishing, ``0`` = benign. No scam sub-type is
provided, so scam rows get ``scam_type="unknown"``.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

import pandas as pd

from src.preprocessing.schema import LABEL_SAFE, LABEL_SCAM, make_frame, validate_frame

logger = logging.getLogger(__name__)

REPO_ID = "ealvaradob/phishing-dataset"
DATA_FILENAME = "texts.json"
SOURCE_NAME = "hf_phishing_texts"


def download_hf_phishing(raw_dir: Path, token: str | None = None) -> Path:
    """Fetch ``texts.json`` into ``raw_dir`` (skipped if already cached).

    Args:
        raw_dir: Destination folder.
        token: Optional Hugging Face token (the dataset is public).

    Returns:
        Local path of ``texts.json``.
    """
    from huggingface_hub import hf_hub_download  # lazy: keeps import cheap for tests

    raw_dir = Path(raw_dir)
    raw_dir.mkdir(parents=True, exist_ok=True)
    path = hf_hub_download(
        repo_id=REPO_ID,
        filename=DATA_FILENAME,
        repo_type="dataset",
        local_dir=str(raw_dir),
        token=token,
    )
    return Path(path)


def parse_hf_phishing(path: Path) -> pd.DataFrame:
    """Parse ``texts.json`` (a list of ``{"text", "label"}`` dicts) into the schema.

    Records with a missing/non-string text or a label other than 0/1 are skipped.
    """
    with open(path, encoding="utf-8") as fh:
        records = json.load(fh)
    texts: list[str] = []
    labels: list[str] = []
    for rec in records:
        text, label = rec.get("text"), rec.get("label")
        if not isinstance(text, str) or not text.strip() or label not in (0, 1):
            continue
        texts.append(text)
        labels.append(LABEL_SCAM if label == 1 else LABEL_SAFE)
    return validate_frame(
        make_frame(texts, labels, source=SOURCE_NAME, language="en"), SOURCE_NAME
    )


def load_hf_phishing(
    raw_dir: Path, download: bool = True, token: str | None = None
) -> pd.DataFrame:
    """Load the phishing text subset, downloading it first if needed."""
    raw_dir = Path(raw_dir)
    path = download_hf_phishing(raw_dir, token) if download else raw_dir / DATA_FILENAME
    return parse_hf_phishing(path)
