"""Manual check: run :func:`src.pipeline.analyze_image` on real phone screenshots.

Usage::

    python -m src.ocr.check_real_screenshots [folder] [--llm]

Reads every PNG/JPEG/WebP in ``folder`` (default ``data/real_screenshots/``,
gitignored) and prints, per image: the cleaned OCR text, OCR confidence,
verdict/risk level, classifier confidence and stage timings, followed by a
summary table *without* message text (safe to paste into results.md).

Name files ``scam_*.png`` / ``safe_*.png`` to have the expected label shown
next to the verdict in the summary.

Privacy: OCR text is printed to this terminal only - never logged, never
written to disk. By default the LLM explainer is skipped (template fallback),
so the screenshot text is not sent to any external API either; the verdict
comes from the classifier + URL rules and is identical either way. Pass
``--llm`` to also try Groq/Gemini for the explanation text.
"""
from __future__ import annotations

import argparse
import time
from dataclasses import dataclass
from pathlib import Path

from src.ocr.ocr import NoTextFoundError
from src.ocr.validate import InvalidImageError

DEFAULT_FOLDER = Path("data/real_screenshots")
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}


@dataclass
class CheckRow:
    """Summary of one image (no message text)."""

    file: str
    expected: str | None
    verdict: str
    risk_level: str
    classifier_confidence: float | None
    ocr_confidence: float | None
    ocr_seconds: float | None
    total_seconds: float


def expected_label(filename: str) -> str | None:
    """``"scam"``/``"safe"`` from a ``scam_``/``safe_`` filename prefix, else ``None``."""
    lower = filename.lower()
    for label in ("scam", "safe"):
        if lower.startswith(label):
            return label
    return None


def list_images(folder: Path) -> list[Path]:
    """Image files directly inside ``folder``, sorted by name."""
    if not folder.is_dir():
        return []
    return sorted(p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in IMAGE_SUFFIXES)


def check_image(path: Path, analyze_fn, use_llm: bool = False) -> CheckRow:
    """Analyze one image and print its details. Never raises for a bad image."""
    print(f"\n=== {path.name} ===")
    kwargs = {} if use_llm else {"groq_api_key": "", "gemini_api_key": ""}
    start = time.perf_counter()
    try:
        result = analyze_fn(path.read_bytes(), **kwargs)
    except (InvalidImageError, NoTextFoundError) as exc:
        code = getattr(exc, "code", "no_text")
        print(f"  rejected ({code}): {exc}")
        return CheckRow(path.name, expected_label(path.name), f"rejected:{code}", "-", None, None, None,
                        time.perf_counter() - start)
    total = time.perf_counter() - start
    ocr = result.ocr
    out = result.explain_result.output
    print("  OCR text:")
    for line in (ocr.text if ocr else "").splitlines():
        print(f"    | {line}")
    if ocr:
        print(f"  OCR: {ocr.num_boxes} boxes, mean confidence {ocr.mean_confidence:.2f}, dark mode: {ocr.inverted}")
    print(f"  verdict: {out.verdict} / {out.risk_level} (classifier confidence "
          f"{result.prediction.scam_probability:.2f}, explanation via {result.explain_result.path})")
    print(f"  timings: {[(t.stage, round(t.seconds, 2)) for t in result.timings]}  total {total:.2f}s")
    ocr_s = next((t.seconds for t in result.timings if t.stage == "ocr"), None)
    return CheckRow(path.name, expected_label(path.name), out.verdict, out.risk_level,
                    result.prediction.scam_probability, ocr.mean_confidence if ocr else None, ocr_s, total)


def format_summary(rows: list[CheckRow]) -> str:
    """Markdown table of the rows - contains no message text."""
    def f(v: float | None, digits: int = 2) -> str:
        return "-" if v is None else f"{v:.{digits}f}"

    out = ["| File | Expected | Verdict | Risk | Classifier conf. | OCR conf. | OCR s | Total s |",
           "|---|---|---|---|---|---|---|---|"]
    for r in rows:
        out.append(f"| {r.file} | {r.expected or '-'} | {r.verdict} | {r.risk_level} | "
                   f"{f(r.classifier_confidence)} | {f(r.ocr_confidence)} | {f(r.ocr_seconds, 1)} | "
                   f"{f(r.total_seconds, 1)} |")
    return "\n".join(out)


def _utf8_stdout() -> None:
    """Print Devanagari etc. on Windows consoles (cp1252) instead of crashing."""
    import sys

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run analyze_image on real screenshots (manual check).")
    parser.add_argument("folder", nargs="?", default=str(DEFAULT_FOLDER))
    parser.add_argument("--llm", action="store_true", help="Also call Groq/Gemini for the explanation text.")
    args = parser.parse_args(argv)
    _utf8_stdout()

    images = list_images(Path(args.folder))
    if not images:
        print(f"No PNG/JPEG/WebP images found in {args.folder}. See {DEFAULT_FOLDER}/README.md.")
        return 1

    if args.llm:
        from dotenv import load_dotenv

        load_dotenv()
    from src.pipeline import analyze_image  # heavy import (models) only once there's work to do

    rows = [check_image(p, analyze_image, use_llm=args.llm) for p in images]
    print("\nSummary (no message text - safe to paste into results.md):\n")
    print(format_summary(rows))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
