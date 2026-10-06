"""Offline phishing-URL blocklists (PhishTank, OpenPhish community feed).

Both lists are downloaded ahead of time (see ``refresh_phishtank.py`` and
``refresh_openphish.py``) and looked up locally - :mod:`src.url_analyzer.analyzer`
never fetches or visits a URL it is scoring. Either, both, or neither list may
be present on disk; a missing file degrades to an empty, always-``False``
list rather than raising, since a real API key/feed refresh is optional.
"""
from __future__ import annotations

import csv
import logging
from pathlib import Path
from urllib.parse import urlsplit

logger = logging.getLogger(__name__)

DEFAULT_PHISHTANK_PATH = Path("data/raw/phishtank/online-valid.csv")
DEFAULT_OPENPHISH_PATH = Path("data/raw/openphish/feed.txt")


def _normalize(url: str) -> str:
    """Lowercase scheme/host and drop a trailing slash, for tolerant matching."""
    parts = urlsplit(url.strip())
    path = parts.path.rstrip("/")
    return f"{parts.scheme.lower()}://{parts.netloc.lower()}{path}"


class OfflineURLList:
    """A named, in-memory set of known-bad URLs loaded from a local file."""

    def __init__(self, urls: set[str], source_name: str) -> None:
        self._urls = urls
        self.source_name = source_name

    def is_listed(self, url: str) -> bool:
        """Whether ``url`` (after normalisation) is in this list."""
        return _normalize(url) in self._urls

    def __len__(self) -> int:
        return len(self._urls)


def load_phishtank(path: Path | str = DEFAULT_PHISHTANK_PATH) -> OfflineURLList:
    """Load a PhishTank ``online-valid.csv`` export into an :class:`OfflineURLList`.

    Returns an empty list (with a logged warning) if ``path`` does not exist,
    so callers can always construct one without checking for the file first.
    """
    path = Path(path)
    if not path.exists():
        logger.warning("PhishTank list not found at %s; skipping this signal.", path)
        return OfflineURLList(set(), "PhishTank")
    urls: set[str] = set()
    with path.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            url = row.get("url")
            if url:
                urls.add(_normalize(url))
    logger.info("Loaded %d PhishTank URLs from %s", len(urls), path)
    return OfflineURLList(urls, "PhishTank")


def load_openphish(path: Path | str = DEFAULT_OPENPHISH_PATH) -> OfflineURLList:
    """Load an OpenPhish ``feed.txt`` export (one URL per line) into an :class:`OfflineURLList`.

    Returns an empty list (with a logged warning) if ``path`` does not exist.
    """
    path = Path(path)
    if not path.exists():
        logger.warning("OpenPhish list not found at %s; skipping this signal.", path)
        return OfflineURLList(set(), "OpenPhish")
    urls: set[str] = set()
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                urls.add(_normalize(line))
    logger.info("Loaded %d OpenPhish URLs from %s", len(urls), path)
    return OfflineURLList(urls, "OpenPhish")
