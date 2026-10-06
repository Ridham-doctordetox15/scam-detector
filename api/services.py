"""Model loading, readiness tracking and the analysis calls behind the endpoints.

Everything heavy is loaded **once**, at startup (:meth:`Services.load_all`),
never per request. Each component loads independently: a failure marks that
component not-ready (reported by ``/health``) instead of crashing the app,
so for example text analysis keeps working if OCR failed to load.

Readiness rules:

* classifier not ready -> status ``unavailable`` (nothing can be analyzed)
* RAG or OCR not ready -> status ``degraded`` (RAG falls back to "no
  pattern match"; ``/analyze/image`` returns 503)
* LLM keys absent is *not* degraded: the template explainer is a designed
  path, and verdicts never depend on the LLM anyway.
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass

from api import artifacts
from api.config import Settings
from api.logs import log_event
from src.rag.rag_engine import RetrievalResult

WARMUP_QUERY = "Your account will be blocked today, update KYC now"


class NoMatchRag:
    """Stand-in when the RAG index is unavailable: never a confident match."""

    def retrieve(self, query: str, top_k: int = 3) -> RetrievalResult:
        return RetrievalResult(query=query, matches=[], confident=False)


@dataclass
class Component:
    ready: bool = False
    detail: str = "not loaded"


class ServiceUnavailable(RuntimeError):
    """A required component is not ready."""

    def __init__(self, component: str) -> None:
        super().__init__(component)
        self.component = component


class Services:
    """Holds the loaded models. Tests construct it and assign fakes directly."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.predictor = None
        self.classifier_model = ""
        self.rag_engine = None
        self.offline_lists: list = []
        self.ocr_engine = None
        self.components: dict[str, Component] = {
            name: Component() for name in ("classifier", "url_analyzer", "rag", "ocr", "llm", "feedback")
        }
        self.refresh_config_status()

    # ------------------------------ loading ------------------------------ #
    def load_all(self) -> None:
        """Load every component (each isolated), then warm up. Logs readiness, never content."""
        for name, loader in (("classifier", self._load_classifier), ("url_analyzer", self._load_url_analyzer),
                             ("rag", self._load_rag), ("ocr", self._load_ocr)):
            start = time.perf_counter()
            try:
                loader()
            except Exception as exc:  # isolate: one broken component must not take down the API
                self.components[name] = Component(False, f"failed to load ({type(exc).__name__})")
                log_event("component_failed", level=40, component=name, exc_type=type(exc).__name__,
                          seconds=round(time.perf_counter() - start, 2))
            else:
                log_event("component_loaded", component=name, ready=True,
                          seconds=round(time.perf_counter() - start, 2))
        self.refresh_config_status()

    def _load_classifier(self) -> None:
        s = self.settings
        if s.use_onnx_classifier:
            from src.inference.predictor import ScamPredictor

            self.predictor = ScamPredictor.load(s.onnx_model_dir)
            self.classifier_model = "onnx_distilbert"
        else:
            from src.inference.tfidf_predictor import TfidfPredictor

            if s.verify_artifacts:
                artifacts.verify_all()  # a .joblib is a pickle: never load an unverified file
            self.predictor = TfidfPredictor.load(s.tfidf_model_dir)
            self.classifier_model = "tfidf_svm"
        self.components["classifier"] = Component(True, self.classifier_model)

    def _load_url_analyzer(self) -> None:
        from src.url_analyzer.offline_lists import load_openphish, load_phishtank

        self.offline_lists = [load_phishtank(), load_openphish()]
        counts = ", ".join(f"{lst.source_name}: {len(lst)} URLs" for lst in self.offline_lists)
        self.components["url_analyzer"] = Component(True, f"rules ready; offline lists - {counts}")

    def _load_rag(self) -> None:
        from src.rag.rag_engine import RAGEngine

        engine = RAGEngine(persist_dir=self.settings.chroma_dir)
        engine.build_index()  # no-op when the index hash matches (built at image build time)
        if self.settings.warmup:
            engine.retrieve(WARMUP_QUERY)
        self.rag_engine = engine
        self.components["rag"] = Component(True, "index ready")

    def _load_ocr(self) -> None:
        from src.ocr.ocr import get_default_ocr_engine

        engine = get_default_ocr_engine()
        engine.load()
        if self.settings.warmup:
            from src.ocr.sample_screenshots import SAMPLES, render, to_png_bytes
            from src.ocr.validate import load_image

            engine.read(load_image(to_png_bytes(render(SAMPLES[2]))))  # the safe sample
        self.ocr_engine = engine
        self.components["ocr"] = Component(True, f"languages: {','.join(engine.languages)}")

    def refresh_config_status(self) -> None:
        """LLM/feedback status from configuration (never exposes values)."""
        providers = [name for name, key in (("groq", "GROQ_API_KEY"), ("gemini", "GEMINI_API_KEY"))
                     if os.getenv(key, "").strip()]
        self.components["llm"] = Component(
            True, f"providers: {', '.join(providers)} + template fallback" if providers else "template fallback only"
        )
        self.components["feedback"] = Component(
            self.settings.feedback_configured,
            "supabase configured" if self.settings.feedback_configured else "not configured",
        )

    # ------------------------------ health ------------------------------ #
    def status(self) -> str:
        if not self.components["classifier"].ready:
            return "unavailable"
        if not (self.components["rag"].ready and self.components["ocr"].ready):
            return "degraded"
        return "ok"

    # ------------------------------ analysis ------------------------------ #
    def _common_kwargs(self) -> dict:
        if self.predictor is None or not self.components["classifier"].ready:
            raise ServiceUnavailable("classifier")
        return {
            "predictor": self.predictor,
            "classifier_model_name": self.classifier_model,
            "rag_engine": self.rag_engine if self.components["rag"].ready and self.rag_engine else NoMatchRag(),
            "offline_lists": self.offline_lists,
        }

    def analyze_text(self, text: str):
        from src.pipeline import analyze

        return analyze(text, **self._common_kwargs())

    def analyze_image(self, image_bytes: bytes):
        from src.pipeline import analyze_image

        if self.ocr_engine is None or not self.components["ocr"].ready:
            raise ServiceUnavailable("ocr")
        return analyze_image(image_bytes, ocr_engine=self.ocr_engine, max_image_bytes=self.settings.max_image_bytes,
                             **self._common_kwargs())
