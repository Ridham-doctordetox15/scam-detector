"""Evaluate OCR + cleaning + verdict on the generated sample screenshots.

Usage::

    python -m src.ocr.evaluate

For each sample in :mod:`src.ocr.sample_screenshots` (plus the Devanagari
one when a font is available) this reports:

* **CER** - character error rate of the cleaned OCR text against the ground
  truth (Levenshtein distance / ground-truth length, whitespace-normalized).
* **keyword recall** - share of the sample's key phrases found (case-insensitive).
* **URL** - whether the message link was recovered exactly.
* **chrome leaked** - UI strings (timestamps, "Delivered", input hint, status
  bar) still present after cleaning. Should be 0.
* OCR confidence and time, and the end-to-end verdict vs. the intended label
  (real classifier + URL rules; template explainer, no API calls).

These images are generated and clean - an upper bound, not a real-world
estimate (see ``check_real_screenshots`` for real phone screenshots).
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from rapidfuzz.distance import Levenshtein

from src.ocr.sample_screenshots import SAMPLES, SampleScreenshot, devanagari_sample, render, to_png_bytes


def _norm_ws(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def char_error_rate(hypothesis: str, reference: str) -> float:
    """Levenshtein distance / reference length, after collapsing whitespace."""
    ref = _norm_ws(reference)
    if not ref:
        return 0.0 if not _norm_ws(hypothesis) else 1.0
    return Levenshtein.distance(_norm_ws(hypothesis), ref) / len(ref)


def keyword_recall(text: str, keywords: tuple[str, ...]) -> float:
    """Share of ``keywords`` present in ``text`` (case-insensitive, whitespace-normalized)."""
    if not keywords:
        return 1.0
    hay = _norm_ws(text).lower()
    return sum(_norm_ws(k).lower() in hay for k in keywords) / len(keywords)


def leaked_chrome(text: str, chrome: tuple[str, ...]) -> list[str]:
    """Chrome strings still present in ``text`` (case-insensitive, whole-word)."""
    return [c for c in chrome if re.search(rf"(?<!\w){re.escape(c)}(?!\w)", text, re.IGNORECASE)]


@dataclass
class SampleEval:
    name: str
    theme: str
    cer: float
    keyword_recall: float
    url_ok: bool | None
    leaked: list[str]
    ocr_confidence: float
    ocr_seconds: float
    expected: str
    verdict: str
    risk_level: str
    text: str


def evaluate_sample(sample: SampleScreenshot, analyze_image_fn) -> SampleEval:
    """Run the full image pipeline on one rendered sample and score it."""
    result = analyze_image_fn(to_png_bytes(render(sample)), groq_api_key="", gemini_api_key="")
    ocr = result.ocr
    assert ocr is not None
    out = result.explain_result.output
    return SampleEval(
        name=sample.name,
        theme=sample.theme.name,
        cer=char_error_rate(ocr.text, sample.ground_truth),
        keyword_recall=keyword_recall(ocr.text, sample.keywords),
        url_ok=None if sample.url is None else sample.url in result.urls,
        leaked=leaked_chrome(ocr.text, sample.chrome),
        ocr_confidence=ocr.mean_confidence,
        ocr_seconds=ocr.seconds,
        expected=sample.expected_label,
        verdict=out.verdict,
        risk_level=out.risk_level,
        text=ocr.text,
    )


def format_table(rows: list[SampleEval]) -> str:
    """Markdown table of results (samples are synthetic, so text is not sensitive)."""
    out = ["| Sample | Theme | CER | Keyword recall | URL exact | Chrome leaked | OCR conf. | OCR s | "
           "Expected | Verdict / risk |",
           "|---|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        url = "-" if r.url_ok is None else ("yes" if r.url_ok else "NO")
        out.append(f"| {r.name} | {r.theme} | {r.cer:.3f} | {r.keyword_recall:.2f} | {url} | "
                   f"{len(r.leaked)}{' ' + str(r.leaked) if r.leaked else ''} | {r.ocr_confidence:.2f} | "
                   f"{r.ocr_seconds:.1f} | {r.expected} | {r.verdict} / {r.risk_level} |")
    return "\n".join(out)


def _utf8_stdout() -> None:
    """Print Devanagari etc. on Windows consoles (cp1252) instead of crashing."""
    import sys

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def main() -> None:
    _utf8_stdout()
    import time

    from src.ocr.ocr import get_default_ocr_engine
    from src.pipeline import analyze_image

    # Load models first so per-image OCR times are warm (steady-state) numbers.
    start = time.perf_counter()
    get_default_ocr_engine().load()
    print(f"OCR model load: {time.perf_counter() - start:.1f}s")

    samples = list(SAMPLES)
    if (hi := devanagari_sample()) is not None:
        samples.append(hi)
    rows = []
    for s in samples:
        row = evaluate_sample(s, analyze_image)
        rows.append(row)
        print(f"\n=== {s.name} ===")
        for line in row.text.splitlines():
            print(f"  | {line}")
    print()
    print(format_table(rows))


if __name__ == "__main__":
    main()
