"""Download and parse the UCI SMS Spam Collection.

Source: https://archive.ics.uci.edu/dataset/228/sms+spam+collection
The archive holds one tab-separated file (``label<TAB>text``) with ``ham`` /
``spam`` labels. Note that "spam" here is mostly promotional/premium-rate SMS,
which is broader than (and different from) fraud.
"""
from __future__ import annotations

import io
import logging
import zipfile
from pathlib import Path

import pandas as pd
import requests

from src.preprocessing.uci_spam import uci_spam_subtype
from src.preprocessing.schema import (
    LABEL_SAFE,
    LABEL_SCAM,
    SCAM_TYPE_GENERIC_SPAM,
    SCAM_TYPE_NONE,
    SCAM_TYPE_UNKNOWN,
    SUBTYPE_UNSPECIFIED,
    make_frame,
    validate_frame,
)

logger = logging.getLogger(__name__)

UCI_URL = "https://archive.ics.uci.edu/static/public/228/sms+spam+collection.zip"
DATA_FILENAME = "SMSSpamCollection"
SOURCE_NAME = "uci_sms_spam"


def download_uci(raw_dir: Path, url: str = UCI_URL, force: bool = False) -> Path:
    """Download and extract the UCI archive into ``raw_dir``.

    Args:
        raw_dir: Destination folder (created if missing).
        url: Archive URL (overridable for tests).
        force: Re-download even if the data file already exists.

    Returns:
        Path to the extracted ``SMSSpamCollection`` file.

    Raises:
        requests.HTTPError: If the download fails.
        zipfile.BadZipFile: If the response is not a valid zip archive.
    """
    raw_dir = Path(raw_dir)
    target = raw_dir / DATA_FILENAME
    if target.exists() and not force:
        logger.info("UCI SMS data already present: %s", target)
        return target
    raw_dir.mkdir(parents=True, exist_ok=True)
    resp = requests.get(url, timeout=60)
    resp.raise_for_status()
    with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
        target.write_bytes(zf.read(DATA_FILENAME))
    logger.info("Downloaded UCI SMS data to %s", target)
    return target


def parse_uci(path: Path) -> pd.DataFrame:
    """Parse the tab-separated UCI file into the shared schema.

    Lines that do not have exactly a known label and non-empty text are skipped.
    """
    texts: list[str] = []
    labels: list[str] = []
    types: list[str] = []
    subtypes: list[str] = []
    with open(path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            label, sep, text = line.rstrip("\r\n").partition("\t")
            text = text.strip()
            if not sep or not text or label not in ("ham", "spam"):
                continue
            is_spam = label == "spam"
            subtype = uci_spam_subtype(text) if is_spam else SUBTYPE_UNSPECIFIED
            texts.append(text)
            labels.append(LABEL_SCAM if is_spam else LABEL_SAFE)
            subtypes.append(subtype)
            # fake prize / call-back lures are a kind of fraud; the rest is generic (promotional) spam
            types.append(SCAM_TYPE_NONE if not is_spam else (SCAM_TYPE_UNKNOWN if subtype == "fraud" else SCAM_TYPE_GENERIC_SPAM))
    # Language is tagged later by the combine step (heuristic, see language.py).
    return validate_frame(
        make_frame(texts, labels, source=SOURCE_NAME, scam_type=types, language="en", subtype=subtypes),
        SOURCE_NAME,
    )


def load_uci(raw_dir: Path, download: bool = True) -> pd.DataFrame:
    """Load the UCI SMS Spam Collection, downloading it first if needed."""
    raw_dir = Path(raw_dir)
    path = download_uci(raw_dir) if download else raw_dir / DATA_FILENAME
    return parse_uci(path)
