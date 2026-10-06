"""Tests for src.pipeline: stage wiring, timings, classifier fallback, end-to-end masking.

Uses injected fake predictor/rag_engine/offline_lists throughout, and forces
the template fallback (no API keys) so these tests never touch the network.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from src import pipeline as PL
from src.inference.predictor import Prediction
from src.rag.rag_engine import RetrievalResult

NO_MATCH_RAG = RetrievalResult(query="x", matches=[], confident=False)


class FakePredictor:
    def __init__(self, prediction: Prediction) -> None:
        self._prediction = prediction
        self.calls: list[str] = []

    def predict(self, text: str) -> Prediction:
        self.calls.append(text)
        return self._prediction


class FakeRagEngine:
    def __init__(self, result: RetrievalResult) -> None:
        self._result = result
        self.queries: list[str] = []

    def retrieve(self, query: str, top_k: int = 3) -> RetrievalResult:
        self.queries.append(query)
        return self._result


SAFE_PREDICTION = Prediction(scam_probability=0.05, is_scam=False, threshold=0.0)
SCAM_PREDICTION = Prediction(scam_probability=0.95, is_scam=True, threshold=0.0)


def _analyze(text: str, prediction: Prediction = SAFE_PREDICTION, rag_result: RetrievalResult = NO_MATCH_RAG, **kw):
    predictor = FakePredictor(prediction)
    rag_engine = FakeRagEngine(rag_result)
    result = PL.analyze(
        text,
        predictor=predictor,
        classifier_model_name="fake_model",
        rag_engine=rag_engine,
        offline_lists=[],
        groq_api_key=None,
        gemini_api_key=None,
        **kw,
    )
    return result, predictor, rag_engine


# ---------------------------- stage wiring ---------------------------- #
def test_analyze_uses_injected_predictor_and_reports_its_name() -> None:
    result, predictor, _ = _analyze("hello there", SCAM_PREDICTION)
    assert result.classifier_model == "fake_model"
    assert result.prediction == SCAM_PREDICTION
    assert predictor.calls == ["hello there"]  # predictor gets the raw text, not pre-masked


def test_analyze_records_all_five_stage_timings_in_order() -> None:
    result, _, _ = _analyze("hello there")
    stages = [t.stage for t in result.timings]
    assert stages == ["mask", "classify", "analyze_urls", "retrieve_patterns", "explain"]
    assert all(t.seconds >= 0.0 for t in result.timings)


def test_analyze_extracts_urls_and_scores_them() -> None:
    result, _, _ = _analyze("check this out http://free-prize-claim.tk/win", SCAM_PREDICTION)
    assert result.urls == ["http://free-prize-claim.tk/win"]
    assert len(result.url_findings) == 1
    assert result.url_findings[0].risk_band in ("low", "medium", "high")


def test_analyze_with_no_urls_returns_empty_findings() -> None:
    result, _, _ = _analyze("just a plain message with no links")
    assert result.urls == []
    assert result.url_findings == []


def test_rag_engine_receives_masked_text_not_raw_text() -> None:
    result, _, rag_engine = _analyze("call 9876543210 about your kyc update")
    assert rag_engine.queries == [result.masked_text]
    assert "9876543210" not in rag_engine.queries[0]


# ---------------------------- end-to-end masking ---------------------------- #
def test_raw_phone_and_otp_never_reach_the_explainer(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict = {}

    def fake_explain(masked_text, is_scam, scam_probability, url_findings, rag_result, **kwargs):
        captured["masked_text"] = masked_text
        from src.llm.explainer import ExplainerOutput, ExplainResult
        output = ExplainerOutput(verdict="safe", risk_level="low", red_flags=[], explanation="ok", what_to_do=[], matched_pattern=None)
        return ExplainResult(output=output, path="template", elapsed_seconds=0.0)

    monkeypatch.setattr(PL, "explain", fake_explain)
    raw = "your otp is 384921, call 9876543210 to verify, visit http://bad-example.tk"
    _analyze(raw)
    assert "384921" not in captured["masked_text"]
    assert "9876543210" not in captured["masked_text"]
    assert "http://bad-example.tk" not in captured["masked_text"]
    assert "<OTP>" in captured["masked_text"] or "<PHONE>" in captured["masked_text"]


# ---------------------------- classifier loading / fallback ---------------------------- #
def test_get_default_predictor_raises_when_neither_model_exists(tmp_path: Path) -> None:
    PL._predictor_cache.clear()
    with pytest.raises(RuntimeError, match="No classifier model found"):
        PL.get_default_predictor(tmp_path / "no_tfidf", tmp_path / "no_onnx")


def test_get_default_predictor_falls_back_to_onnx_when_tfidf_missing(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    PL._predictor_cache.clear()
    sentinel = object()

    class FakeTfidfPredictor:
        @classmethod
        def load(cls, model_dir):
            raise FileNotFoundError("no tfidf here")

    class FakeScamPredictor:
        @classmethod
        def load(cls, model_dir):
            return sentinel

    monkeypatch.setattr(PL, "TfidfPredictor", FakeTfidfPredictor)
    monkeypatch.setattr(PL, "ScamPredictor", FakeScamPredictor)
    predictor, name = PL.get_default_predictor(tmp_path / "no_tfidf", tmp_path / "some_onnx")
    assert predictor is sentinel
    assert name == "onnx_distilbert"


def test_get_default_predictor_is_cached(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    PL._predictor_cache.clear()
    load_calls = {"n": 0}
    sentinel = object()

    class FakeTfidfPredictor:
        @classmethod
        def load(cls, model_dir):
            load_calls["n"] += 1
            return sentinel

    monkeypatch.setattr(PL, "TfidfPredictor", FakeTfidfPredictor)
    dirs = (tmp_path / "tfidf", tmp_path / "onnx")
    first, _ = PL.get_default_predictor(*dirs)
    second, _ = PL.get_default_predictor(*dirs)
    assert first is second
    assert load_calls["n"] == 1


# ---------------------------- analyze_image ---------------------------- #
from src.ocr.ocr import NoTextFoundError, OCRResult  # noqa: E402
from src.ocr.validate import InvalidImageError  # noqa: E402


class FakeOCREngine:
    def __init__(self, text: str) -> None:
        self.text = text
        self.images: list = []

    def read(self, image) -> OCRResult:
        self.images.append(image)
        return OCRResult(text=self.text, raw_text=self.text, mean_confidence=0.88, num_boxes=3, languages=("en", "hi"))


def _png_bytes(w: int = 120, h: int = 200) -> bytes:
    import io

    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (w, h), (255, 255, 255)).save(buf, format="PNG")
    return buf.getvalue()


def _analyze_image(ocr_text: str, prediction: Prediction = SCAM_PREDICTION, data: bytes | None = None, **kw):
    engine = FakeOCREngine(ocr_text)
    predictor = FakePredictor(prediction)
    result = PL.analyze_image(
        _png_bytes() if data is None else data,
        ocr_engine=engine,
        predictor=predictor,
        classifier_model_name="fake_model",
        rag_engine=FakeRagEngine(NO_MATCH_RAG),
        offline_lists=[],
        groq_api_key=None,
        gemini_api_key=None,
        **kw,
    )
    return result, engine, predictor


def test_analyze_image_runs_ocr_then_full_pipeline(monkeypatch) -> None:
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    text = "Your KYC is pending. Update now: http://sbi-kyc-verify.tk/update"
    result, engine, predictor = _analyze_image(text)
    assert engine.images[0].shape == (200, 120, 3)  # decoded, validated array reached OCR
    assert predictor.calls == [text]  # the cleaned OCR text is what gets classified
    assert result.ocr is not None and result.ocr.mean_confidence == 0.88
    assert result.text == text
    assert result.urls == ["http://sbi-kyc-verify.tk/update"]
    assert result.explain_result.output.verdict == "scam"
    assert [t.stage for t in result.timings] == [
        "validate", "ocr", "mask", "classify", "analyze_urls", "retrieve_patterns", "explain",
    ]


def test_analyze_image_rejects_invalid_upload_before_ocr() -> None:
    with pytest.raises(InvalidImageError) as exc:
        _analyze_image("unused", data=b"%PDF-1.7 not an image")
    assert exc.value.code == "unsupported_type"


def test_analyze_image_respects_size_limit_override() -> None:
    with pytest.raises(InvalidImageError) as exc:
        _analyze_image("unused", max_image_bytes=10)
    assert exc.value.code == "too_large"


@pytest.mark.parametrize("ocr_text", ["", "  ", "?!", "a."])
def test_analyze_image_with_no_text_raises_and_classifies_nothing(ocr_text: str) -> None:
    engine = FakeOCREngine(ocr_text)
    predictor = FakePredictor(SCAM_PREDICTION)
    with pytest.raises(NoTextFoundError):
        PL.analyze_image(_png_bytes(), ocr_engine=engine, predictor=predictor, classifier_model_name="x",
                         rag_engine=FakeRagEngine(NO_MATCH_RAG), offline_lists=[])
    assert predictor.calls == []


def test_text_analyze_leaves_ocr_unset() -> None:
    result, _, _ = _analyze("hello there")
    assert result.ocr is None
