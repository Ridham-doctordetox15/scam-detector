"""Tests for the FastAPI backend (api/) with mocked models.

The real pipeline code runs (masking, URL analyzer, rules, template
explainer) but the classifier, RAG and OCR are fakes, API keys are removed
(template path, no network) and Supabase is a fake store or a mocked
httpx transport.
"""
from __future__ import annotations

import asyncio
import io
import json
import logging
import threading
import time
import uuid

import httpx
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from api.config import Settings
from api.feedback import FeedbackError, PredictionCache, PredictionRecord, SupabaseFeedbackStore
from api.logs import JsonFormatter, configure_logging
from api.main import create_app
from api.ratelimit import RateLimiter, client_key
from api.schemas import defang_url, ocr_quality
from api.services import Component, Services
from src.inference.predictor import Prediction
from src.ocr.ocr import OCRResult
from src.rag.rag_engine import RetrievalResult

SCAM = Prediction(scam_probability=0.97, is_scam=True, threshold=0.0)
SAFE = Prediction(scam_probability=0.03, is_scam=False, threshold=0.0)
SCAM_TEXT = "Dear customer your KYC is pending, account BLOCKED today. Update: http://sbi-kyc-verify.tk/update"


# ------------------------------------------------------------------ fakes
class FakePredictor:
    def __init__(self, prediction: Prediction = SCAM, delay_s: float = 0.0) -> None:
        self.prediction = prediction
        self.delay_s = delay_s
        self.calls = 0

    def predict(self, text: str) -> Prediction:
        self.calls += 1
        if self.delay_s:
            time.sleep(self.delay_s)
        return self.prediction


class FakeRag:
    def retrieve(self, query: str, top_k: int = 3) -> RetrievalResult:
        return RetrievalResult(query=query, matches=[], confident=False)


class FakeOCR:
    def __init__(self, text: str = SCAM_TEXT, confidence: float = 0.86, dark: bool = False) -> None:
        self.text, self.confidence, self.dark = text, confidence, dark
        self.languages = ("en", "hi")

    def read(self, image) -> OCRResult:
        return OCRResult(text=self.text, raw_text=self.text, mean_confidence=self.confidence, num_boxes=5,
                         languages=self.languages, inverted=self.dark)


class FakeStore:
    def __init__(self, fail: bool = False) -> None:
        self.rows: list[dict] = []
        self.fail = fail

    def save(self, row: dict) -> None:
        if self.fail:
            raise FeedbackError("feedback storage returned HTTP 500")
        self.rows.append(row)


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def make_services(settings: Settings, prediction: Prediction = SCAM, ocr: FakeOCR | None = None,
                  delay_s: float = 0.0, rag_ready: bool = True, ocr_ready: bool = True) -> Services:
    svc = Services(settings)
    svc.predictor = FakePredictor(prediction, delay_s)
    svc.classifier_model = "tfidf_svm"
    svc.components["classifier"] = Component(True, "tfidf_svm")
    svc.components["url_analyzer"] = Component(True, "rules ready")
    svc.rag_engine = FakeRag()
    svc.components["rag"] = Component(rag_ready, "index ready" if rag_ready else "failed to load (OSError)")
    svc.ocr_engine = ocr or FakeOCR()
    svc.components["ocr"] = Component(ocr_ready, "languages: en,hi" if ocr_ready else "failed to load (OSError)")
    return svc


def settings(**overrides) -> Settings:
    base = dict(load_models=False, warmup=False, verify_artifacts=False, rate_text_per_min=1000,
                rate_image_per_min=1000, rate_feedback_per_min=1000)
    base.update(overrides)
    return Settings(**base)


@pytest.fixture(autouse=True)
def _no_llm_keys(monkeypatch):
    for key in ("GROQ_API_KEY", "GEMINI_API_KEY"):
        monkeypatch.delenv(key, raising=False)


def build(s: Settings | None = None, store=None, clock=None, **svc_kwargs):
    s = s or settings()
    app = create_app(settings=s, services=make_services(s, **svc_kwargs), feedback_store=store,
                     clock=clock or time.monotonic)
    return TestClient(app), app


def png_bytes(w: int = 200, h: int = 300) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (w, h), (250, 250, 250)).save(buf, format="PNG")
    return buf.getvalue()


def _walk_keys(obj) -> set[str]:
    if isinstance(obj, dict):
        return set(obj) | set().union(*(_walk_keys(v) for v in obj.values())) if obj else set()
    if isinstance(obj, list):
        return set().union(*(_walk_keys(v) for v in obj)) if obj else set()
    return set()


# ------------------------------------------------------------------ /analyze/text
def test_analyze_text_scam_response_shape() -> None:
    client, _ = build()
    r = client.post("/analyze/text", json={"text": SCAM_TEXT})
    assert r.status_code == 200
    body = r.json()
    assert body["verdict"] == "scam" and body["risk_level"] == "high"
    assert body["input_type"] == "text" and body["explainer_path"] == "template"
    assert body["classifier_model"] == "tfidf_svm"
    uuid.UUID(body["prediction_id"])
    assert body["red_flags"] and body["what_to_do"] and body["explanation"]
    assert body["url_findings"][0]["url_defanged"] == "hxxp://sbi-kyc-verify[.]tk/update"
    assert body["url_findings"][0]["risk_band"] in {"low", "medium", "high"}
    assert set(body["timings_ms"]) == {"mask", "classify", "analyze_urls", "retrieve_patterns", "explain"}
    assert body["ocr"] is None and body["disclaimer"]
    assert r.headers["X-Request-ID"]


def test_responses_never_contain_probabilities_or_scores() -> None:
    client, _ = build()
    body = client.post("/analyze/text", json={"text": SCAM_TEXT}).json()
    keys = _walk_keys(body)
    assert not {k for k in keys if "prob" in k or "score" in k or "confidence" in k or "margin" in k}
    assert "0.97" not in json.dumps(body)


def test_analyze_text_safe() -> None:
    client, _ = build(prediction=SAFE)
    body = client.post("/analyze/text", json={"text": "Lunch at 1pm tomorrow?"}).json()
    assert body["verdict"] == "safe" and body["risk_level"] == "low" and body["url_findings"] == []


@pytest.mark.parametrize("payload, code", [
    ({"text": ""}, "empty_text"),
    ({"text": "   \n "}, "empty_text"),
    ({"text": "x" * 5001}, "text_too_long"),
    ({}, "invalid_request"),
    ({"text": 123}, "invalid_request"),
    ({"text": "hi", "extra": 1}, "invalid_request"),
])
def test_analyze_text_input_errors(payload: dict, code: str) -> None:
    client, _ = build()
    r = client.post("/analyze/text", json=payload)
    assert r.status_code == 422
    assert r.json()["error"]["code"] == code
    assert r.json()["error"]["request_id"] == r.headers["X-Request-ID"]


def test_validation_error_does_not_echo_input() -> None:
    client, _ = build()
    r = client.post("/analyze/text", json={"text": ["SECRET-ECHO-CHECK"]})
    assert r.status_code == 422 and "SECRET-ECHO-CHECK" not in r.text


def test_malformed_json_is_422_not_500() -> None:
    client, _ = build()
    r = client.post("/analyze/text", content=b"{not json", headers={"Content-Type": "application/json"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "invalid_request"


def test_text_length_limit_is_configurable() -> None:
    client, _ = build(settings(max_text_chars=10))
    assert client.post("/analyze/text", json={"text": "x" * 10}).status_code == 200
    assert client.post("/analyze/text", json={"text": "x" * 11}).json()["error"]["code"] == "text_too_long"


def test_oversized_json_body_rejected_before_parsing() -> None:
    client, app = build(settings(max_json_body_bytes=1000))
    r = client.post("/analyze/text", json={"text": "x" * 2000})
    assert r.status_code == 413 and r.json()["error"]["code"] == "body_too_large"
    assert app.state.services.predictor.calls == 0


def test_missing_content_length_is_411() -> None:
    client, _ = build()

    def gen():
        yield b'{"text": "hi"}'

    r = client.post("/analyze/text", content=gen(), headers={"Content-Type": "application/json"})
    assert r.status_code == 411 and r.json()["error"]["code"] == "length_required"


def test_classifier_not_ready_returns_503() -> None:
    client, app = build()
    app.state.services.components["classifier"] = Component(False, "failed to load (FileNotFoundError)")
    r = client.post("/analyze/text", json={"text": "hello"})
    assert r.status_code == 503 and r.json()["error"]["code"] == "classifier_unavailable"


def test_rag_not_ready_degrades_to_no_match() -> None:
    client, app = build(rag_ready=False)
    app.state.services.rag_engine = None
    r = client.post("/analyze/text", json={"text": SCAM_TEXT})
    assert r.status_code == 200 and r.json()["matched_pattern"] is None


# ------------------------------------------------------------------ /analyze/image
def test_analyze_image_success() -> None:
    client, _ = build(ocr=FakeOCR(confidence=0.86, dark=True))
    r = client.post("/analyze/image", files={"file": ("shot.png", png_bytes(), "image/png")})
    assert r.status_code == 200
    body = r.json()
    assert body["input_type"] == "image" and body["verdict"] == "scam"
    assert body["ocr"] == {"extracted_text": SCAM_TEXT, "quality": "good", "dark_mode": True}
    assert list(body["timings_ms"])[:2] == ["validate", "ocr"]


@pytest.mark.parametrize("data, status, code", [
    (b"%PDF-1.7 not an image", 415, "unsupported_type"),
    (b"\x89PNG\r\n\x1a\n" + b"garbage" * 20, 422, "corrupt"),
    (b"", 422, "empty"),
])
def test_analyze_image_invalid_files(data: bytes, status: int, code: str) -> None:
    client, _ = build()
    r = client.post("/analyze/image", files={"file": ("x.png", data, "image/png")})
    assert r.status_code == status and r.json()["error"]["code"] == code


def test_analyze_image_too_large() -> None:
    client, _ = build(settings(max_image_bytes=1000))
    r = client.post("/analyze/image", files={"file": ("x.png", png_bytes(600, 600) + b"0" * 2000, "image/png")})
    assert r.status_code == 413 and r.json()["error"]["code"] in {"too_large", "body_too_large"}


def test_analyze_image_too_large_but_within_multipart_overhead() -> None:
    client, _ = build(settings(max_image_bytes=1000))
    r = client.post("/analyze/image", files={"file": ("x.png", b"\x89PNG\r\n\x1a\n" + b"0" * 1500, "image/png")})
    assert r.status_code == 413 and r.json()["error"]["code"] == "too_large"


def test_analyze_image_no_text_found() -> None:
    client, app = build(ocr=FakeOCR(text=""))
    r = client.post("/analyze/image", files={"file": ("x.png", png_bytes(), "image/png")})
    assert r.status_code == 422 and r.json()["error"]["code"] == "no_text_found"
    assert app.state.services.predictor.calls == 0


def test_analyze_image_missing_file_field() -> None:
    client, _ = build()
    r = client.post("/analyze/image", data={"not_file": "x"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "invalid_request"


def test_analyze_image_when_ocr_not_ready_but_text_still_works() -> None:
    client, _ = build(ocr_ready=False)
    r = client.post("/analyze/image", files={"file": ("x.png", png_bytes(), "image/png")})
    assert r.status_code == 503 and r.json()["error"]["code"] == "ocr_unavailable"
    assert client.post("/analyze/text", json={"text": "hello"}).status_code == 200


@pytest.mark.parametrize("conf, band", [(0.9, "good"), (0.75, "good"), (0.6, "fair"), (0.3, "poor")])
def test_ocr_quality_bands(conf: float, band: str) -> None:
    assert ocr_quality(conf) == band


# ------------------------------------------------------------------ /health
def test_health_ok_and_components() -> None:
    client, _ = build()
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert set(body["components"]) == {"classifier", "url_analyzer", "rag", "ocr", "llm", "feedback"}
    assert body["components"]["llm"]["detail"] == "template fallback only"
    assert body["components"]["feedback"] == {"ready": False, "detail": "not configured"}


def test_health_degraded_and_unavailable() -> None:
    client, app = build(ocr_ready=False)
    assert client.get("/health").json()["status"] == "degraded"
    app.state.services.components["classifier"] = Component(False, "failed to load (ArtifactError)")
    r = client.get("/health")
    assert r.status_code == 503 and r.json()["status"] == "unavailable"


def test_health_reports_llm_providers_without_values(monkeypatch) -> None:
    monkeypatch.setenv("GROQ_API_KEY", "gsk_" + "Z" * 20)  # secret-scan: allow
    client, _ = build()
    body = client.get("/health").json()
    assert body["components"]["llm"]["detail"] == "providers: groq + template fallback"
    assert "Z" * 20 not in json.dumps(body)


def test_root_lists_endpoints() -> None:
    client, _ = build()
    assert "POST /analyze/text" in client.get("/").json()["endpoints"]


# ------------------------------------------------------------------ /feedback
def test_feedback_saves_non_text_row() -> None:
    store = FakeStore()
    client, _ = build(settings(supabase_url="https://x.supabase.co", supabase_key="k"), store=store)
    pid = client.post("/analyze/text", json={"text": SCAM_TEXT}).json()["prediction_id"]
    r = client.post("/feedback", json={"prediction_id": pid, "user_verdict": "incorrect"})
    assert r.status_code == 201 and r.json() == {"status": "saved", "prediction_id": pid}
    assert store.rows == [{
        "prediction_id": pid, "user_verdict": "incorrect", "predicted_verdict": "scam",
        "predicted_risk_level": "high", "input_type": "text", "classifier_model": "tfidf_svm",
        "explainer_path": "template", "matched_pattern": None,
    }]
    assert "KYC" not in json.dumps(store.rows) and "sbi-kyc" not in json.dumps(store.rows)


def test_feedback_unknown_prediction_is_404() -> None:
    client, _ = build(store=FakeStore())
    r = client.post("/feedback", json={"prediction_id": str(uuid.uuid4()), "user_verdict": "correct"})
    assert r.status_code == 404 and r.json()["error"]["code"] == "unknown_prediction"
    assert "restarts" in r.json()["error"]["message"]


def test_feedback_expired_prediction_is_404() -> None:
    clock = Clock()
    client, _ = build(settings(prediction_cache_ttl_s=60), store=FakeStore(), clock=clock)
    pid = client.post("/analyze/text", json={"text": SCAM_TEXT}).json()["prediction_id"]
    clock.now += 61
    assert client.post("/feedback", json={"prediction_id": pid, "user_verdict": "correct"}).status_code == 404


def test_feedback_not_configured_is_503() -> None:
    client, _ = build()
    pid = client.post("/analyze/text", json={"text": SCAM_TEXT}).json()["prediction_id"]
    r = client.post("/feedback", json={"prediction_id": pid, "user_verdict": "correct"})
    assert r.status_code == 503 and r.json()["error"]["code"] == "feedback_not_configured"


def test_feedback_storage_failure_is_502() -> None:
    client, _ = build(store=FakeStore(fail=True))
    pid = client.post("/analyze/text", json={"text": SCAM_TEXT}).json()["prediction_id"]
    r = client.post("/feedback", json={"prediction_id": pid, "user_verdict": "correct"})
    assert r.status_code == 502 and r.json()["error"]["code"] == "feedback_storage_error"


@pytest.mark.parametrize("payload", [
    {"prediction_id": "not-a-uuid", "user_verdict": "correct"},
    {"prediction_id": str(uuid.uuid4()), "user_verdict": "maybe"},
    {"prediction_id": str(uuid.uuid4()), "user_verdict": "correct", "text": "no text allowed"},
])
def test_feedback_validation(payload: dict) -> None:
    client, _ = build(store=FakeStore())
    r = client.post("/feedback", json=payload)
    assert r.status_code == 422 and r.json()["error"]["code"] == "invalid_request"


# ------------------------------------------------------------------ Supabase store (mocked HTTP)
def _record() -> PredictionRecord:
    return PredictionRecord("scam", "high", "text", "tfidf_svm", "template", None)


def test_supabase_store_request_shape_secret_key() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(201)

    store = SupabaseFeedbackStore("https://abc.supabase.co/", "sb_secret_" + "x" * 20,  # secret-scan: allow
                                  transport=httpx.MockTransport(handler))
    store.save({"prediction_id": "p", "user_verdict": "correct"})
    req = seen[0]
    assert str(req.url) == "https://abc.supabase.co/rest/v1/feedback?on_conflict=prediction_id"
    assert req.headers["apikey"].startswith("sb_secret_")
    assert "authorization" not in req.headers
    assert "merge-duplicates" in req.headers["prefer"]
    assert json.loads(req.content) == {"prediction_id": "p", "user_verdict": "correct"}
    assert "sb_secret" not in repr(store)


def test_supabase_store_legacy_jwt_adds_bearer() -> None:
    seen = []
    store = SupabaseFeedbackStore("https://abc.supabase.co", "eyJ" + "a" * 30,
                                  transport=httpx.MockTransport(lambda r: seen.append(r) or httpx.Response(201)))
    store.save({})
    assert seen[0].headers["authorization"].startswith("Bearer eyJ")


@pytest.mark.parametrize("handler", [
    lambda r: httpx.Response(401, json={"message": "Invalid API key"}),
    lambda r: httpx.Response(500),
])
def test_supabase_store_http_errors(handler) -> None:
    store = SupabaseFeedbackStore("https://abc.supabase.co", "k", transport=httpx.MockTransport(handler))
    with pytest.raises(FeedbackError, match="HTTP"):
        store.save({})


def test_supabase_store_network_error_message_has_no_key() -> None:
    def boom(request):
        raise httpx.ConnectError("connection refused")

    store = SupabaseFeedbackStore("https://abc.supabase.co", "sb_secret_TOPSECRET",  # secret-scan: allow
                                  transport=httpx.MockTransport(boom))
    with pytest.raises(FeedbackError) as exc:
        store.save({})
    assert "TOPSECRET" not in str(exc.value) and "ConnectError" in str(exc.value)


def test_settings_repr_hides_supabase_key() -> None:
    assert "TOPSECRET" not in repr(Settings(supabase_key="TOPSECRET"))


# ------------------------------------------------------------------ rate limiting
def test_rate_limit_per_bucket_with_retry_after() -> None:
    clock = Clock()
    client, _ = build(settings(rate_text_per_min=2, rate_image_per_min=1), clock=clock)
    assert client.post("/analyze/text", json={"text": "a"}).status_code == 200
    assert client.post("/analyze/text", json={"text": "b"}).status_code == 200
    r = client.post("/analyze/text", json={"text": "c"})
    assert r.status_code == 429 and r.json()["error"]["code"] == "rate_limited"
    assert r.headers["Retry-After"] == "60"
    # Other buckets are independent.
    assert client.post("/analyze/image", files={"file": ("x.png", png_bytes(), "image/png")}).status_code == 200
    # The window slides.
    clock.now += 60.5
    assert client.post("/analyze/text", json={"text": "d"}).status_code == 200


def test_rate_limit_uses_forwarded_for_behind_trusted_proxy() -> None:
    client, _ = build(settings(rate_text_per_min=1, trusted_proxy_hops=1), clock=Clock())
    assert client.post("/analyze/text", json={"text": "a"}, headers={"X-Forwarded-For": "1.1.1.1"}).status_code == 200
    assert client.post("/analyze/text", json={"text": "a"}, headers={"X-Forwarded-For": "2.2.2.2"}).status_code == 200
    # Spoofed left-most entries don't create a new identity: the proxy-appended one counts.
    r = client.post("/analyze/text", json={"text": "a"}, headers={"X-Forwarded-For": "9.9.9.9, 1.1.1.1"})
    assert r.status_code == 429


def test_rate_limiter_unit() -> None:
    clock = Clock()
    rl = RateLimiter({"a": 2, "off": 0}, window_s=10, clock=clock, max_clients=2)
    assert rl.check("a", "c1") is None and rl.check("a", "c1") is None
    assert rl.check("a", "c1") == pytest.approx(10)
    clock.now += 4
    assert rl.check("a", "c1") == pytest.approx(6)
    assert all(rl.check("off", "c1") is None for _ in range(100))
    rl.check("a", "c2"), rl.check("a", "c3")
    assert rl.tracked_clients() == 2  # bounded


@pytest.mark.parametrize("peer, xff, hops, expected", [
    ("10.0.0.1", None, 0, "10.0.0.1"),
    ("10.0.0.1", "1.2.3.4", 0, "10.0.0.1"),  # XFF ignored without trusted proxies
    ("10.0.0.1", "1.2.3.4", 1, "1.2.3.4"),
    ("10.0.0.1", "6.6.6.6, 1.2.3.4", 1, "1.2.3.4"),
    ("10.0.0.1", "1.2.3.4, 172.16.0.9", 2, "1.2.3.4"),
    ("10.0.0.1", "1.2.3.4", 2, "10.0.0.1"),  # fewer entries than hops: fall back to peer
    (None, None, 0, "unknown"),
])
def test_client_key(peer, xff, hops, expected) -> None:
    assert client_key(peer, xff, hops) == expected


# ------------------------------------------------------------------ timeouts & concurrency
def test_analysis_timeout_returns_504() -> None:
    client, _ = build(settings(text_timeout_s=0.2), delay_s=1.0)
    r = client.post("/analyze/text", json={"text": "slow"})
    assert r.status_code == 504 and r.json()["error"]["code"] == "timeout"


def test_busy_when_all_slots_taken() -> None:
    s = settings(max_concurrent_analyses=1, queue_wait_s=0.1, text_timeout_s=5)
    app = create_app(settings=s, services=make_services(s, delay_s=0.6))

    async def scenario():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://t") as ac:
            return await asyncio.gather(ac.post("/analyze/text", json={"text": "one"}),
                                        ac.post("/analyze/text", json={"text": "two"}))

    statuses = sorted(r.status_code for r in asyncio.run(scenario()))
    assert statuses == [200, 503]


def test_timed_out_analysis_keeps_its_slot_until_the_thread_finishes() -> None:
    s = settings(max_concurrent_analyses=1, queue_wait_s=0.05, text_timeout_s=0.1)
    client, _ = build(s, delay_s=0.5)
    assert client.post("/analyze/text", json={"text": "a"}).status_code == 504
    assert client.post("/analyze/text", json={"text": "b"}).json()["error"]["code"] == "busy"
    time.sleep(0.6)
    assert client.post("/analyze/text", json={"text": "c"}).status_code == 504  # slot free again (still slow)


def test_unhandled_exception_is_500_with_type_only_logged(caplog) -> None:
    client, app = build()

    class Boom:
        def predict(self, text):
            raise RuntimeError(f"model exploded on {text}")

    app.state.services.predictor = Boom()
    with caplog.at_level(logging.DEBUG):
        r = client.post("/analyze/text", json={"text": "LEAKY-SENTINEL-TEXT"})
    assert r.status_code == 500 and r.json()["error"]["code"] == "internal_error"
    assert "LEAKY-SENTINEL-TEXT" not in r.text and "LEAKY-SENTINEL-TEXT" not in caplog.text


# ------------------------------------------------------------------ CORS
def test_cors_allowed_origin_only() -> None:
    client, _ = build(settings(cors_origins=("https://scam-check.example",)))
    ok = client.options("/analyze/text", headers={"Origin": "https://scam-check.example",
                                                  "Access-Control-Request-Method": "POST"})
    assert ok.headers.get("access-control-allow-origin") == "https://scam-check.example"
    bad = client.post("/analyze/text", json={"text": "hi"}, headers={"Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in bad.headers


def test_no_cors_by_default() -> None:
    client, _ = build()
    r = client.post("/analyze/text", json={"text": "hi"}, headers={"Origin": "https://any.example"})
    assert "access-control-allow-origin" not in r.headers


# ------------------------------------------------------------------ privacy of logs
SENTINELS = ["ZEBRA-SENTINEL-7731", "sentinel-leak-check.tk", "9876543210", "OCR-ONLY-SENTINEL",
             "priya_sharma_private", "LEAKY-FILENAME"]


def test_logs_never_contain_message_text_ocr_text_urls_or_filenames(caplog) -> None:
    stream = io.StringIO()
    handler = configure_logging(stream=stream, level=logging.DEBUG)
    try:
        store = FakeStore()
        s = settings(supabase_url="https://x.supabase.co", supabase_key="k", max_text_chars=200)
        client, app = build(s, store=store,
                            ocr=FakeOCR(text="OCR-ONLY-SENTINEL pay now http://sentinel-leak-check.tk/pay"))
        with caplog.at_level(logging.DEBUG):
            text = "ZEBRA-SENTINEL-7731 call 9876543210 or visit http://sentinel-leak-check.tk/login"
            pid = client.post("/analyze/text", json={"text": text}).json()["prediction_id"]
            client.post("/analyze/image", files={"file": ("priya_sharma_private-LEAKY-FILENAME.png",
                                                          png_bytes(), "image/png")})
            client.post("/feedback", json={"prediction_id": pid, "user_verdict": "correct"})
            client.post("/analyze/text", json={"text": "ZEBRA-SENTINEL-7731" * 50})  # too long
            client.post("/analyze/text", json={"text": ["ZEBRA-SENTINEL-7731"]})      # invalid
            client.post("/analyze/image", files={"file": ("LEAKY-FILENAME.png", b"ZEBRA-SENTINEL-7731", "image/png")})
            client.post("/analyze/text", json={"text": "hi"}, headers={"X-Forwarded-For": "203.0.113.77",
                                                                       "User-Agent": "LEAKY-UA"})
        output = stream.getvalue() + caplog.text
    finally:
        logging.getLogger().removeHandler(handler)

    assert '"event": "request"' in output  # logging actually happened
    for sentinel in SENTINELS + ["203.0.113.77", "LEAKY-UA", "testclient"]:
        assert sentinel not in output, f"{sentinel!r} leaked into logs"
    # Every JSON line parses and API lines only carry allowlisted fields.
    for line in stream.getvalue().splitlines():
        record = json.loads(line)
        if record["logger"] == "api":
            assert "message" not in record


def test_request_log_line_fields(caplog) -> None:
    stream = io.StringIO()
    handler = configure_logging(stream=stream)
    try:
        client, _ = build()
        client.post("/analyze/text", json={"text": SCAM_TEXT})
    finally:
        logging.getLogger().removeHandler(handler)
    lines = [json.loads(line) for line in stream.getvalue().splitlines()]
    req = next(line for line in lines if line.get("event") == "request")
    assert req["route"] == "/analyze/text" and req["status"] == 200 and req["method"] == "POST"
    assert req["verdict"] == "scam" and req["risk_level"] == "high" and req["input_chars"] == len(SCAM_TEXT)
    assert req["explainer_path"] == "template" and "classify" in req["timings_ms"]


def test_unmatched_route_is_not_logged_verbatim() -> None:
    stream = io.StringIO()
    handler = configure_logging(stream=stream)
    try:
        client, _ = build()
        assert client.get("/secret-path-ZEBRA").status_code == 404
    finally:
        logging.getLogger().removeHandler(handler)
    assert "ZEBRA" not in stream.getvalue() and '"route": "unmatched"' in stream.getvalue()


def test_json_formatter_drops_non_allowlisted_extras() -> None:
    record = logging.LogRecord("api", logging.INFO, __file__, 1, "request", None, None)
    record.text = "SHOULD-NOT-APPEAR"
    record.status = 200
    out = json.loads(JsonFormatter().format(record))
    assert out["status"] == 200 and "text" not in out and "SHOULD-NOT-APPEAR" not in json.dumps(out)


# ------------------------------------------------------------------ helpers
@pytest.mark.parametrize("url, defanged", [
    ("http://sbi-kyc-verify.tk/update", "hxxp://sbi-kyc-verify[.]tk/update"),
    ("https://www.myvi.in/offers?a=1.2", "hxxps://www[.]myvi[.]in/offers?a=1.2"),
    ("www.paytm-kyc.top", "www[.]paytm-kyc[.]top"),
    ("HTTP://X.CO", "hxxp://X[.]CO"),
])
def test_defang_url(url: str, defanged: str) -> None:
    assert defang_url(url) == defanged


def test_prediction_cache_bounds_and_ttl() -> None:
    clock = Clock()
    cache = PredictionCache(ttl_s=10, max_items=2, clock=clock)
    for i in range(3):
        cache.put(str(i), _record())
    assert cache.get("0") is None and cache.get("2") is not None and len(cache) == 2
    clock.now += 11
    assert cache.get("2") is None


def test_settings_from_env() -> None:
    s = Settings.from_env({
        "CORS_ORIGINS": "https://a.example/, https://b.example", "RATE_LIMIT_TEXT_PER_MIN": "5",
        "TRUSTED_PROXY_HOPS": "1", "USE_ONNX_CLASSIFIER": "true", "MAX_TEXT_CHARS": "abc",
        "SUPABASE_URL": "https://x.supabase.co/", "SUPABASE_KEY": " k ", "TEXT_TIMEOUT_S": "-3",
    })
    assert s.cors_origins == ("https://a.example", "https://b.example")
    assert s.rate_text_per_min == 5 and s.trusted_proxy_hops == 1 and s.use_onnx_classifier
    assert s.max_text_chars == 5000 and s.text_timeout_s == 25.0  # invalid values fall back
    assert s.supabase_url == "https://x.supabase.co" and s.feedback_configured
    assert not Settings.from_env({}).feedback_configured and Settings.from_env({}).cors_origins == ()


def test_thread_safety_of_rate_limiter() -> None:
    rl = RateLimiter({"a": 500})
    results = []

    def worker():
        results.extend(rl.check("a", "same") for _ in range(100))

    threads = [threading.Thread(target=worker) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sum(r is None for r in results) == 500


@pytest.mark.parametrize("raw", ["https://abc.supabase.co", "https://abc.supabase.co/", "https://abc.supabase.co/rest/v1",
                                 " https://abc.supabase.co/rest/v1/ "])
def test_supabase_url_accepts_base_or_rest_url(raw: str) -> None:
    s = Settings.from_env({"SUPABASE_URL": raw, "SUPABASE_KEY": "k"})
    assert s.supabase_url == "https://abc.supabase.co"
    store = SupabaseFeedbackStore(s.supabase_url, "k")
    assert store.endpoint == "https://abc.supabase.co/rest/v1/feedback"


# ------------------------------------------------------------------ response language field
@pytest.mark.parametrize("text, language", [
    (SCAM_TEXT, "en"),
    ("आपका बैंक खाता बंद हो जाएगा। तुरंत KYC अपडेट करें।", "hi"),
    ("Aapka SBI khata band ho jayega, turant KYC update karo", "hinglish"),
    ("Bhai kal 1 baje lunch pe milte hain, office ke paas wale cafe mein?", "hinglish"),
])
def test_analyze_text_reports_output_language(text: str, language: str) -> None:
    client, _ = build()
    body = client.post("/analyze/text", json={"text": text}).json()
    assert body["language"] == language


def test_analyze_image_reports_output_language_of_extracted_text() -> None:
    client, _ = build(ocr=FakeOCR(text="आपका बैंक खाता बंद हो जाएगा। तुरंत KYC अपडेट करें।"))
    body = client.post("/analyze/image", files={"file": ("x.png", png_bytes(), "image/png")}).json()
    assert body["language"] == "hi"


def test_language_field_is_documented_in_openapi() -> None:
    client, _ = build()
    schema = client.get("/openapi.json").json()["components"]["schemas"]["AnalyzeResponse"]
    assert schema["properties"]["language"]["enum"] == ["en", "hi", "hinglish"]
    assert "language" in schema["required"]
