"""End-to-end analysis pipeline: classify, analyze URLs, retrieve patterns, explain.

Stage order for one message:

1. **mask** - :func:`src.preprocessing.preprocess.preprocess_text` (clean +
   mask URLs/OTPs/phones). The masked text and extracted URLs feed every
   later stage that shouldn't see raw PII.
2. **classify** - the deployed classifier (TF-IDF + Linear SVM by default,
   per results.md's Phase 4 deployment recommendation; falls back to the
   ONNX DistilBERT predictor if the TF-IDF artifact is missing, and vice
   versa - never crashes just because one model folder isn't present).
3. **analyze_urls** - :mod:`src.url_analyzer.analyzer` on the raw extracted
   URLs (never fetched, just parsed).
4. **retrieve_patterns** - :mod:`src.rag.rag_engine` on the masked text.
5. **explain** - :mod:`src.llm.explainer`, given the results of stages 2-4.
   The verdict/risk_level it returns are fixed by :mod:`src.llm.rules`, not
   by the LLM.

:func:`analyze_image` puts two stages in front for screenshots: **validate**
(:mod:`src.ocr.validate` - size, real file type, dimensions) and **ocr**
(:mod:`src.ocr.ocr` - EasyOCR + chrome/timestamp cleaning), then runs
:func:`analyze` on the recovered text.

Every stage's wall-clock time is recorded. A failure in URL analysis or RAG
retrieval degrades gracefully (empty findings / no confident match) rather
than aborting the message; the explainer itself never raises (see its own
docstring). Only a completely missing classifier model is a hard error -
that's a setup problem, not a per-message one.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path

from src.inference.predictor import Prediction, ScamPredictor
from src.inference.tfidf_predictor import TfidfPredictor
from src.llm.explainer import ExplainResult, explain
from src.ocr.ocr import NoTextFoundError, OCREngine, OCRResult, get_default_ocr_engine
from src.ocr.validate import load_image
from src.preprocessing.preprocess import preprocess_text
from src.rag.rag_engine import RAGEngine, RetrievalResult
from src.url_analyzer.analyzer import URLFinding, analyze_urls
from src.url_analyzer.offline_lists import OfflineURLList, load_openphish, load_phishtank

DEFAULT_TFIDF_MODEL_DIR = Path("models/baseline_phase4")
# No default location was established for the ONNX artifacts in Phase 4 (they
# stayed local/gitignored); this is a documented convention, easily overridden.
DEFAULT_ONNX_MODEL_DIR = Path("models/distilbert")

_predictor_cache: dict[str, tuple[object, str]] = {}
_rag_engine_cache: dict[str, RAGEngine] = {}
_offline_lists_cache: dict[str, list[OfflineURLList]] = {}


@dataclass
class StageTiming:
    stage: str
    seconds: float


@dataclass
class PipelineResult:
    """Everything produced for one message, plus per-stage timing."""

    text: str
    masked_text: str
    urls: list[str]
    classifier_model: str  # "tfidf_svm" or "onnx_distilbert"
    prediction: Prediction
    url_findings: list[URLFinding]
    rag_result: RetrievalResult
    explain_result: ExplainResult
    timings: list[StageTiming] = field(default_factory=list)
    ocr: OCRResult | None = None  # set only by analyze_image


def get_default_predictor(
    tfidf_model_dir: Path | str = DEFAULT_TFIDF_MODEL_DIR, onnx_model_dir: Path | str = DEFAULT_ONNX_MODEL_DIR
):
    """The deployed classifier: TF-IDF + Linear SVM primary, ONNX DistilBERT fallback.

    Cached after the first successful load.

    Raises:
        RuntimeError: If neither model folder is usable - a setup problem
            (no trained model available at all), not a per-message failure.
    """
    key = f"{tfidf_model_dir}|{onnx_model_dir}"
    if key not in _predictor_cache:
        try:
            _predictor_cache[key] = (TfidfPredictor.load(tfidf_model_dir), "tfidf_svm")
        except FileNotFoundError:
            try:
                _predictor_cache[key] = (ScamPredictor.load(onnx_model_dir), "onnx_distilbert")
            except FileNotFoundError:
                raise RuntimeError(
                    f"No classifier model found: neither {tfidf_model_dir} (TF-IDF, primary per "
                    f"results.md) nor {onnx_model_dir} (ONNX, fallback) has a usable model. "
                    "Run Phase 3/4 training first."
                ) from None
    return _predictor_cache[key]


def get_default_rag_engine() -> RAGEngine:
    """A cached :class:`RAGEngine` with the project's default knowledge base and settings."""
    if "default" not in _rag_engine_cache:
        engine = RAGEngine()
        engine.build_index()
        _rag_engine_cache["default"] = engine
    return _rag_engine_cache["default"]


def get_default_offline_lists() -> list[OfflineURLList]:
    """PhishTank/OpenPhish lists if present on disk; empty (never missing/erroring) otherwise."""
    if "default" not in _offline_lists_cache:
        _offline_lists_cache["default"] = [load_phishtank(), load_openphish()]
    return _offline_lists_cache["default"]


def analyze(
    text: str,
    *,
    predictor=None,
    classifier_model_name: str | None = None,
    rag_engine: RAGEngine | None = None,
    offline_lists: list[OfflineURLList] | None = None,
    groq_api_key: str | None = None,
    gemini_api_key: str | None = None,
    groq_model: str | None = None,
    gemini_model: str | None = None,
    budget_seconds: float | None = None,
) -> PipelineResult:
    """Run the full pipeline on one message. Only the classifier-loading step can raise."""
    timings: list[StageTiming] = []

    def _timed(stage: str, fn, *args, **kwargs):
        start = time.perf_counter()
        result = fn(*args, **kwargs)
        timings.append(StageTiming(stage, time.perf_counter() - start))
        return result

    if predictor is None:
        predictor, classifier_model_name = get_default_predictor()
    if rag_engine is None:
        rag_engine = get_default_rag_engine()
    if offline_lists is None:
        offline_lists = get_default_offline_lists()

    masked_text, urls = _timed("mask", preprocess_text, text)
    prediction: Prediction = _timed("classify", predictor.predict, text)
    url_findings: list[URLFinding] = _timed("analyze_urls", analyze_urls, urls, offline_lists)
    rag_result: RetrievalResult = _timed("retrieve_patterns", rag_engine.retrieve, masked_text)

    explain_kwargs: dict = {"groq_api_key": groq_api_key, "gemini_api_key": gemini_api_key,
                            "groq_model": groq_model, "gemini_model": gemini_model}
    if budget_seconds is not None:
        explain_kwargs["budget_seconds"] = budget_seconds
    explain_result: ExplainResult = _timed(
        "explain", explain, masked_text, prediction.is_scam, prediction.scam_probability, url_findings, rag_result,
        **explain_kwargs,
    )

    return PipelineResult(
        text=text,
        masked_text=masked_text,
        urls=urls,
        classifier_model=classifier_model_name,
        prediction=prediction,
        url_findings=url_findings,
        rag_result=rag_result,
        explain_result=explain_result,
        timings=timings,
    )


# Fewer letters/digits than this after cleaning means OCR found nothing to analyze.
MIN_OCR_ALNUM_CHARS = 3


def analyze_image(
    image_bytes: bytes,
    *,
    ocr_engine: OCREngine | None = None,
    max_image_bytes: int | None = None,
    **analyze_kwargs,
) -> PipelineResult:
    """Validate a screenshot, OCR it, then run :func:`analyze` on the cleaned text.

    Args:
        image_bytes: Raw uploaded file content (untrusted).
        ocr_engine: Injected engine (tests); defaults to the cached
            :func:`get_default_ocr_engine` (``OCR_LANGUAGES``, default en+hi).
        max_image_bytes: Upload size limit override (default ``OCR_MAX_IMAGE_MB``).
        **analyze_kwargs: Passed through to :func:`analyze`.

    Returns:
        The usual :class:`PipelineResult`, with ``ocr`` set and ``validate``/
        ``ocr`` prepended to ``timings``.

    Raises:
        InvalidImageError: The upload is not an acceptable image (see its ``code``).
        NoTextFoundError: OCR found no usable text - nothing is classified.
    """
    start = time.perf_counter()
    image = load_image(image_bytes, max_bytes=max_image_bytes)
    validate_s = time.perf_counter() - start

    engine = ocr_engine if ocr_engine is not None else get_default_ocr_engine()
    start = time.perf_counter()
    ocr_result = engine.read(image)
    ocr_s = time.perf_counter() - start

    if sum(c.isalnum() for c in ocr_result.text) < MIN_OCR_ALNUM_CHARS:
        raise NoTextFoundError("No readable message text was found in the image.")

    result = analyze(ocr_result.text, **analyze_kwargs)
    result.ocr = ocr_result
    result.timings = [StageTiming("validate", validate_s), StageTiming("ocr", ocr_s), *result.timings]
    return result


_DEMO_MESSAGES = [
    # scam, English, with link
    "Dear customer, your KYC is not updated. Your account will be BLOCKED within 24 hours. "
    "Update immediately: http://sbi-kyc-verify.tk/update",
    # scam, Hinglish, with link
    "Aapka parcel customs mein atka hua hai, chhota sa clearance fee bharo isi link par: "
    "http://courier-customs-fee.top/pay",
    # scam, English, no link
    "This is regarding a suspicious transaction attempt on your card. To block it immediately, "
    "please read out the verification code that was just sent to your phone.",
    # scam, Hinglish, no link
    "Aapka number lucky draw mein select hua hai, 10 lakh rupaye jeetne ke liye turant apna bank "
    "details bhejein is number par.",
    # safe, English, no link
    "Hi, are we still on for lunch tomorrow at 1pm?",
    # safe, Hinglish, with link
    "Vi ke naye recharge plan par paiye extra data aur cashback, abhi click karein: "
    "https://www.myvi.in/offers",
]


def _print_result(result: PipelineResult) -> None:
    print(f"  classifier: {result.classifier_model}, is_scam={result.prediction.is_scam}, "
          f"confidence={result.prediction.scam_probability:.2f}")
    print(f"  verdict: {result.explain_result.output.verdict} / {result.explain_result.output.risk_level} "
          f"(via {result.explain_result.path})")
    print(f"  explanation: {result.explain_result.output.explanation}")
    print(f"  what_to_do: {result.explain_result.output.what_to_do}")
    print(f"  matched_pattern: {result.explain_result.output.matched_pattern}")
    print(f"  timings: {[(t.stage, round(t.seconds, 3)) for t in result.timings]}")


def _print_demo() -> None:
    for text in _DEMO_MESSAGES:
        result = analyze(text)
        print(f"\nMessage: {text}")
        _print_result(result)


def _print_image_demo(path: str) -> None:
    result = analyze_image(Path(path).read_bytes())
    assert result.ocr is not None
    print(f"\nImage: {path}")
    print(f"  OCR text ({result.ocr.num_boxes} boxes, mean confidence {result.ocr.mean_confidence:.2f}, "
          f"dark mode: {result.ocr.inverted}):")
    for line in result.ocr.text.splitlines():
        print(f"    | {line}")
    _print_result(result)



if __name__ == "__main__":
    import argparse
    import logging
    import sys

    from dotenv import load_dotenv

    load_dotenv()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # Devanagari on Windows consoles
    logging.basicConfig(level=logging.WARNING)
    parser = argparse.ArgumentParser(description="Run the analysis pipeline demo.")
    parser.add_argument("--image", help="Analyze this screenshot instead of the built-in text demo messages.")
    args = parser.parse_args()
    if args.image:
        _print_image_demo(args.image)
    else:
        _print_demo()
