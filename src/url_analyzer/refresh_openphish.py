"""Download OpenPhish's free community feed for offline lookup.

No account or API key required. The feed is a plain-text list of URLs (one
per line), updated roughly every 12 hours. Per OpenPhish's terms of use
(https://openphish.com/terms.html), it may be used for personal/research
purposes like this project, but not redistributed or used commercially -
this script only downloads it for local, offline lookup.

Usage::

    python -m src.url_analyzer.refresh_openphish
"""
from __future__ import annotations

import argparse
import logging
from pathlib import Path

import requests

logger = logging.getLogger(__name__)

OPENPHISH_URL = "https://openphish.com/feed.txt"
DEFAULT_OUTPUT = Path("data/raw/openphish/feed.txt")


def refresh_openphish(output_path: Path | str = DEFAULT_OUTPUT, timeout: int = 60) -> Path:
    """Download the OpenPhish community feed to ``output_path``."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    response = requests.get(OPENPHISH_URL, timeout=timeout, headers={"User-Agent": "scam-detector/1.0"})
    response.raise_for_status()
    output_path.write_bytes(response.content)
    logger.info("Wrote OpenPhish feed to %s (%d bytes)", output_path, len(response.content))
    return output_path


def _main() -> None:
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    refresh_openphish(args.output)


if __name__ == "__main__":
    _main()
