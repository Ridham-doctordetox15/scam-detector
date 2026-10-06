"""FastAPI backend: POST /analyze/text, POST /analyze/image, POST /feedback, GET /health.

Run (the app is built by a factory so importing this module has no side
effects - tests never load .env or models)::

    uvicorn api.main:create_app --factory --host 0.0.0.0 --port 7860 --workers 1 --no-access-log

Request flow: body-size check (middleware) -> rate limit -> input checks ->
analysis in a worker thread (bounded concurrency + timeout) -> response with
bands/reasons only (no probabilities) -> one privacy-safe JSON log line.
"""
from __future__ import annotations

import asyncio
import os
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from typing import Callable

from fastapi import FastAPI, File, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from api.config import Settings
from api.feedback import (
    FeedbackError,
    FeedbackStore,
    PredictionCache,
    PredictionRecord,
    SupabaseFeedbackStore,
    build_row,
)
from api.logs import configure_logging, log_event
from api.ratelimit import RateLimiter, client_key
from api.schemas import (
    AnalyzeResponse,
    AnalyzeTextRequest,
    ComponentHealth,
    ErrorResponse,
    FeedbackRequest,
    FeedbackResponse,
    HealthResponse,
    OCROut,
    URLFindingOut,
    defang_url,
    ocr_quality,
)
from api.services import ServiceUnavailable, Services
from src.ocr.ocr import NoTextFoundError
from src.ocr.validate import InvalidImageError

MULTIPART_OVERHEAD_BYTES = 64 * 1024

# InvalidImageError.code -> HTTP status
_IMAGE_ERROR_STATUS = {"too_large": 413, "unsupported_type": 415}

_ERROR_RESPONSES = {
    code: {"model": ErrorResponse}
    for code in (404, 411, 413, 415, 422, 429, 502, 503, 504)
}


class APIError(Exception):
    """An error returned to the client as ``{"error": {code, message, request_id}}``."""

    def __init__(self, status: int, code: str, message: str, headers: dict[str, str] | None = None) -> None:
        super().__init__(code)
        self.status = status
        self.code = code
        self.message = message
        self.headers = headers or {}


def _error_response(request: Request, status: int, code: str, message: str,
                    headers: dict[str, str] | None = None) -> JSONResponse:
    request_id = getattr(request.state, "request_id", "")
    if hasattr(request.state, "log"):
        request.state.log["error_code"] = code
    return JSONResponse(status_code=status, headers=headers,
                        content={"error": {"code": code, "message": message, "request_id": request_id}})


def create_app(
    settings: Settings | None = None,
    services: Services | None = None,
    feedback_store: FeedbackStore | None = None,
    clock: Callable[[], float] = time.monotonic,
    configure_logs: bool | None = None,
) -> FastAPI:
    """Build the app. With no arguments: settings from the environment (plus ``.env`` unless
    ``LOAD_DOTENV=0``), models loaded at startup, JSON logs to stdout."""
    production = settings is None
    if production:
        if os.getenv("LOAD_DOTENV", "1") != "0":
            from dotenv import load_dotenv

            load_dotenv()  # values go straight into the environment; never printed
        settings = Settings.from_env()
    if configure_logs if configure_logs is not None else production:
        configure_logging()

    services = services or Services(settings)
    if feedback_store is None and settings.feedback_configured:
        feedback_store = SupabaseFeedbackStore(settings.supabase_url, settings.supabase_key,
                                               settings.supabase_table, settings.supabase_timeout_s)
    cache = PredictionCache(settings.prediction_cache_ttl_s, settings.prediction_cache_max, clock=clock)
    limiter = RateLimiter({"text": settings.rate_text_per_min, "image": settings.rate_image_per_min,
                           "feedback": settings.rate_feedback_per_min}, clock=clock)
    analysis_slots = threading.BoundedSemaphore(settings.max_concurrent_analyses)
    ocr_slots = threading.BoundedSemaphore(settings.max_concurrent_ocr)
    executor = ThreadPoolExecutor(max_workers=settings.max_concurrent_analyses + 1, thread_name_prefix="analysis")

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if settings.load_models:
            start = time.perf_counter()
            await run_in_threadpool(services.load_all)
            log_event("startup_complete", seconds=round(time.perf_counter() - start, 1))
        yield
        executor.shutdown(wait=False, cancel_futures=True)

    app = FastAPI(
        title="Scam & Phishing Message Detector API",
        version="1.0.0",
        description="Checks SMS/WhatsApp/email text or screenshots for scam signs. "
                    "Returns a verdict, risk band, red flags, explanation and advice - never a probability.",
        lifespan=lifespan,
    )
    app.state.services = services
    app.state.settings = settings
    app.state.prediction_cache = cache
    app.state.rate_limiter = limiter

    # ------------------------------ middleware ------------------------------ #
    def _body_limit(path: str) -> int:
        if path == "/analyze/image":
            return settings.max_image_bytes + MULTIPART_OVERHEAD_BYTES
        return settings.max_json_body_bytes

    @app.middleware("http")
    async def observe(request: Request, call_next):
        request.state.request_id = uuid.uuid4().hex[:16]
        request.state.log = {}
        start = time.perf_counter()
        response = None
        if request.method == "POST":
            length = request.headers.get("content-length")
            if length is None:
                response = _error_response(request, 411, "length_required", "A Content-Length header is required.")
            elif not length.isdigit() or int(length) > _body_limit(request.url.path):
                response = _error_response(request, 413, "body_too_large", "The request body is too large.")
        if response is None:
            try:
                response = await call_next(request)
            except Exception as exc:  # last resort: log the type only (messages can contain user data)
                log_event("unhandled_error", level=40, request_id=request.state.request_id,
                          exc_type=type(exc).__name__)
                response = _error_response(request, 500, "internal_error", "Something went wrong. Please retry.")
        response.headers["X-Request-ID"] = request.state.request_id
        route = request.scope.get("route")
        log_event("request", request_id=request.state.request_id, method=request.method,
                  route=getattr(route, "path", "unmatched"), status=response.status_code,
                  duration_ms=round((time.perf_counter() - start) * 1000, 1), **request.state.log)
        return response

    if settings.cors_origins:  # added last = outermost, so error responses get CORS headers too
        app.add_middleware(CORSMiddleware, allow_origins=list(settings.cors_origins), allow_credentials=False,
                           allow_methods=["GET", "POST"], allow_headers=["Content-Type"],
                           expose_headers=["X-Request-ID", "Retry-After"], max_age=600)

    # ---------------------------- error handlers ---------------------------- #
    @app.exception_handler(APIError)
    async def _api_error(request: Request, exc: APIError):
        return _error_response(request, exc.status, exc.code, exc.message, exc.headers)

    @app.exception_handler(RequestValidationError)
    async def _validation_error(request: Request, exc: RequestValidationError):
        # Never echo the submitted values back (FastAPI's default includes the input).
        fields = sorted({".".join(str(p) for p in e.get("loc", ()) if p != "body") or "body" for e in exc.errors()})
        return _error_response(request, 422, "invalid_request", f"Invalid or missing field(s): {', '.join(fields)}.")

    # ------------------------------ helpers ------------------------------ #
    def _rate_limit(request: Request, bucket: str) -> None:
        client = client_key(request.client.host if request.client else None,
                            request.headers.get("x-forwarded-for"), settings.trusted_proxy_hops)
        retry_after = limiter.check(bucket, client)
        if retry_after is not None:
            seconds = max(1, int(retry_after + 0.999))
            request.state.log.update(limit_bucket=bucket, retry_after_s=seconds)
            raise APIError(429, "rate_limited", f"Too many requests. Please retry in {seconds} seconds.",
                           {"Retry-After": str(seconds)})

    async def _run_limited(fn, timeout_s: float, slots: list[threading.BoundedSemaphore]):
        """Run blocking ``fn`` in a worker thread, holding ``slots`` until the thread finishes.

        Slots are released by the worker thread itself when it ends - not when
        the request times out, and independent of any event loop. A timed-out
        analysis therefore still occupies its slot, so a flood of slow requests
        can't pile up unbounded threads.
        """
        acquired: list[threading.BoundedSemaphore] = []
        for slot in slots:
            if not await run_in_threadpool(slot.acquire, True, settings.queue_wait_s):
                for held in acquired:
                    held.release()
                raise APIError(503, "busy", "The service is busy. Please retry in a few seconds.")
            acquired.append(slot)

        def job():
            try:
                return fn()
            finally:
                for held in acquired:
                    held.release()

        future = asyncio.get_running_loop().run_in_executor(executor, job)
        try:
            return await asyncio.wait_for(asyncio.shield(future), timeout_s)
        except asyncio.TimeoutError:
            raise APIError(504, "timeout", "The analysis took too long. Please retry.") from None
        except ServiceUnavailable as exc:
            raise APIError(503, f"{exc.component}_unavailable",
                           f"The {exc.component} component is not available right now.") from None
        except InvalidImageError as exc:
            raise APIError(_IMAGE_ERROR_STATUS.get(exc.code, 422), exc.code, str(exc)) from None
        except NoTextFoundError:
            raise APIError(422, "no_text_found", "No readable message text was found in the image.") from None

    def _build_response(request: Request, result, input_type: str) -> AnalyzeResponse:
        out = result.explain_result.output
        prediction_id = uuid.uuid4()
        cache.put(str(prediction_id), PredictionRecord(
            predicted_verdict=out.verdict, predicted_risk_level=out.risk_level, input_type=input_type,
            classifier_model=result.classifier_model, explainer_path=result.explain_result.path,
            matched_pattern=out.matched_pattern,
        ))
        timings_ms = {t.stage: round(t.seconds * 1000, 1) for t in result.timings}
        request.state.log.update(verdict=out.verdict, risk_level=out.risk_level,
                                 explainer_path=result.explain_result.path,
                                 classifier_model=result.classifier_model, timings_ms=timings_ms)
        ocr = None
        if result.ocr is not None:
            ocr = OCROut(extracted_text=result.ocr.text, quality=ocr_quality(result.ocr.mean_confidence),
                         dark_mode=result.ocr.inverted)
        return AnalyzeResponse(
            prediction_id=prediction_id,
            input_type=input_type,
            verdict=out.verdict,
            risk_level=out.risk_level,
            red_flags=out.red_flags,
            explanation=out.explanation,
            what_to_do=out.what_to_do,
            matched_pattern=out.matched_pattern,
            url_findings=[URLFindingOut(url_defanged=defang_url(f.url), risk_band=f.risk_band, reasons=f.reasons)
                          for f in result.url_findings],
            explainer_path=result.explain_result.path,
            language=result.explain_result.language,
            classifier_model=result.classifier_model,
            timings_ms=timings_ms,
            ocr=ocr,
        )

    # ------------------------------ endpoints ------------------------------ #
    @app.get("/", include_in_schema=False)
    async def root():
        return {"name": app.title, "docs": "/docs", "health": "/health",
                "endpoints": ["POST /analyze/text", "POST /analyze/image", "POST /feedback", "GET /health"]}

    @app.get("/health", response_model=HealthResponse, responses={503: {"model": HealthResponse}})
    async def health():
        status = services.status()
        body = HealthResponse(status=status, components={
            name: ComponentHealth(ready=c.ready, detail=c.detail) for name, c in services.components.items()
        })
        return JSONResponse(status_code=503 if status == "unavailable" else 200, content=body.model_dump())

    @app.post("/analyze/text", response_model=AnalyzeResponse, responses=_ERROR_RESPONSES)
    async def analyze_text(body: AnalyzeTextRequest, request: Request):
        _rate_limit(request, "text")
        text = body.text
        request.state.log.update(input_type="text", input_chars=len(text))
        if not text.strip():
            raise APIError(422, "empty_text", "The text is empty.")
        if len(text) > settings.max_text_chars:
            raise APIError(422, "text_too_long", f"The text is longer than {settings.max_text_chars} characters.")
        result = await _run_limited(lambda: services.analyze_text(text), settings.text_timeout_s, [analysis_slots])
        return _build_response(request, result, "text")

    @app.post("/analyze/image", response_model=AnalyzeResponse, responses=_ERROR_RESPONSES)
    async def analyze_image(request: Request, file: UploadFile = File(description="PNG, JPEG or WebP screenshot")):
        _rate_limit(request, "image")
        data = await file.read(settings.max_image_bytes + 1)  # the filename is never used or logged
        await file.close()
        request.state.log.update(input_type="image", image_bytes=len(data))
        if len(data) > settings.max_image_bytes:
            raise APIError(413, "too_large", f"The image is larger than {settings.max_image_bytes // 1_048_576} MB.")
        result = await _run_limited(lambda: services.analyze_image(data), settings.image_timeout_s,
                                    [ocr_slots, analysis_slots])
        request.state.log["input_chars"] = len(result.text)
        return _build_response(request, result, "image")

    @app.post("/feedback", response_model=FeedbackResponse, status_code=201, responses=_ERROR_RESPONSES)
    async def feedback(body: FeedbackRequest, request: Request):
        _rate_limit(request, "feedback")
        if feedback_store is None:
            raise APIError(503, "feedback_not_configured", "Feedback storage is not configured on this server.")
        record = cache.get(str(body.prediction_id))
        request.state.log["prediction_known"] = record is not None
        if record is None:
            raise APIError(404, "unknown_prediction",
                           "Unknown or expired prediction_id. Predictions are remembered for 24 hours and are "
                           "forgotten whenever the server restarts.")
        row = build_row(str(body.prediction_id), body.user_verdict, record)
        try:
            await asyncio.wait_for(run_in_threadpool(feedback_store.save, row), settings.supabase_timeout_s + 1)
        except (FeedbackError, asyncio.TimeoutError) as exc:
            request.state.log["exc_type"] = type(exc).__name__
            raise APIError(502, "feedback_storage_error", "Could not save feedback right now. Please retry.") from None
        return FeedbackResponse(prediction_id=body.prediction_id)

    return app
