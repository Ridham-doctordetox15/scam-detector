"""Download PhishTank's verified-phishing CSV for offline lookup.

Requires a free PhishTank account and application key (``PHISHTANK_APP_KEY``
in ``.env`` - see ``.env.example``). PhishTank registration has at times been
closed to new signups; if so, use :mod:`src.url_analyzer.refresh_openphish`
instead, which needs no key. The analyzer works with either, both, or
neither list present.

Usage::

    python -m src.url_analyzer.refresh_phishtank
"""
from __future__ import annotations

import argparse
import logging
import os
from pathlib import Path

import requests

logger = logging.getLogger(__name__)

PHISHTANK_URL = "https://data.phishtank.com/data/{app_key}/online-valid.csv"
DEFAULT_OUTPUT = Path("data/raw/phishtank/online-valid.csv")


def refresh_phishtank(output_path: Path | str = DEFAULT_OUTPUT, timeout: int = 60) -> Path:
    """Download the PhishTank CSV to ``output_path`` using the app key from the environment.

    Raises:
        RuntimeError: if ``PHISHTANK_APP_KEY`` is not set.
    """
    app_key = os.getenv("PHISHTANK_APP_KEY")
    if not app_key:
        raise RuntimeError(
            "PHISHTANK_APP_KEY is not set in the environment. Register a free account "
            "at phishtank.org, add the key to .env, or use refresh_openphish.py instead."
        )
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    url = PHISHTANK_URL.format(app_key=app_key)
    response = requests.get(url, timeout=timeout, headers={"User-Agent": "scam-detector/1.0"})
    response.raise_for_status()
    output_path.write_bytes(response.content)
    logger.info("Wrote PhishTank data to %s (%d bytes)", output_path, len(response.content))
    return output_path


def _main() -> None:
    from dotenv import load_dotenv

    load_dotenv()
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    refresh_phishtank(args.output)


if __name__ == "__main__":
    _main()
