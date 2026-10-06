"""Real-EasyOCR tests on the 4 generated screenshots (incl. dark mode) + optional Devanagari.

Skipped automatically when EasyOCR or its downloaded models (313 MB, see
``python -m src.ocr.ocr``) are not available, so CI never downloads them.
The end-to-end verdict test also needs the trained TF-IDF model
(``models/baseline_phase4``, gitignored) and is skipped without it.

Thresholds are deliberately looser than what these clean images currently
achieve (see results.md) so minor EasyOCR version differences don't break
CI-less local runs, while still catching real regressions in cleaning.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from src.ocr.evaluate import char_error_rate, keyword_recall, leaked_chrome
from src.ocr.sample_screenshots import SAMPLES, SampleScreenshot, devanagari_sample, render, to_png_bytes


def _models_present() -> bool:
    try:
        import easyocr  # noqa: F401
    except ImportError:
        return False
    model_dir = Path(os.environ.get("EASYOCR_MODULE_PATH", Path.home() / ".EasyOCR")) / "model"
    return all((model_dir / f).exists() for f in ("craft_mlt_25k.pth", "english_g2.pth", "devanagari.pth"))


pytestmark = pytest.mark.skipif(not _models_present(), reason="EasyOCR or its en+hi models are not installed")

TFIDF_DIR = Path("models/baseline_phase4")


@pytest.fixture(scope="module")
def engine():
    from src.ocr.ocr import OCREngine

    return OCREngine(("en", "hi"))


@pytest.fixture(scope="module")
def ocr_results(engine):
    from src.ocr.validate import load_image

    return {s.name: engine.read(load_image(to_png_bytes(render(s)))) for s in SAMPLES}


@pytest.mark.parametrize("sample", SAMPLES, ids=lambda s: s.name)
def test_ocr_recovers_message_text(sample: SampleScreenshot, ocr_results) -> None:
    result = ocr_results[sample.name]
    assert keyword_recall(result.text, sample.keywords) == 1.0, result.text
    assert char_error_rate(result.text, sample.ground_truth) <= 0.05, result.text
    assert result.mean_confidence >= 0.5


@pytest.mark.parametrize("sample", SAMPLES, ids=lambda s: s.name)
def test_ocr_cleaning_removes_all_chrome(sample: SampleScreenshot, ocr_results) -> None:
    text = ocr_results[sample.name].text
    assert leaked_chrome(text, sample.chrome) == [], text


@pytest.mark.parametrize("sample", [s for s in SAMPLES if s.url], ids=lambda s: s.name)
def test_ocr_recovers_url_exactly(sample: SampleScreenshot, ocr_results) -> None:
    from src.preprocessing.preprocess import preprocess_text

    _, urls = preprocess_text(ocr_results[sample.name].text)
    assert sample.url in urls, ocr_results[sample.name].text


def test_dark_mode_sample_is_detected_and_inverted(ocr_results) -> None:
    dark = [s for s in SAMPLES if s.theme.name == "whatsapp_dark"]
    assert dark and all(ocr_results[s.name].inverted for s in dark)
    assert not any(ocr_results[s.name].inverted for s in SAMPLES if s.theme.name != "whatsapp_dark")


@pytest.mark.skipif(not (TFIDF_DIR / "svm.joblib").exists(), reason="trained TF-IDF model not available")
@pytest.mark.parametrize("sample", SAMPLES, ids=lambda s: s.name)
def test_end_to_end_verdict_matches_expected_label(sample: SampleScreenshot, engine) -> None:
    from src.pipeline import analyze_image, get_default_predictor
    from src.rag.rag_engine import RetrievalResult

    class NoMatchRag:  # verdict doesn't depend on RAG; keep this test fast
        def retrieve(self, query: str, top_k: int = 3) -> RetrievalResult:
            return RetrievalResult(query=query, matches=[], confident=False)

    predictor, name = get_default_predictor()
    result = analyze_image(
        to_png_bytes(render(sample)), ocr_engine=engine, predictor=predictor, classifier_model_name=name,
        rag_engine=NoMatchRag(), offline_lists=[], groq_api_key="", gemini_api_key="",
    )
    assert result.explain_result.output.verdict == sample.expected_label, result.ocr.text if result.ocr else ""


def test_devanagari_sample_when_font_available(engine) -> None:
    from src.ocr.validate import load_image

    sample = devanagari_sample()
    if sample is None:
        pytest.skip("no Devanagari font installed")
    text = engine.read(load_image(to_png_bytes(render(sample)))).text
    assert "KYC" in text
    devanagari_chars = sum("ऀ" <= c <= "ॿ" for c in text)
    assert devanagari_chars >= 20, text
    assert char_error_rate(text, sample.ground_truth) <= 0.25, text
