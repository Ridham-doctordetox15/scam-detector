"""Download everything the API needs *before* it serves traffic.

Docker: run once at image build time (``RUN --mount=type=secret,id=HF_TOKEN
... python -m api.prefetch``), so no model is ever downloaded on a user's
request. Gradio/ZeroGPU route (no Docker build step): run at process start by
``app.py`` before the server launches.

Steps (each reports what it did; required steps fail the build):

1. **model** (required): the TF-IDF + SVM bundle from the private HF model
   repo ``MODEL_REPO_ID`` (revision ``MODEL_REPO_REVISION``, default
   ``main``), verified against ``api/artifacts.lock.json``. Skipped if the
   file is already present with the right hash (local development).
2. **ocr** (required): EasyOCR detector + English + Devanagari models (313 MB).
3. **rag** (required): the multilingual MiniLM embedding model, and the
   Chroma index built from ``data/knowledge_base/scam_patterns.json``.
4. **openphish** (best effort): a snapshot of the free OpenPhish feed. Its
   age is the image's build date - rebuild to refresh it.
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

from api import artifacts


def fetch_model() -> str:
    try:
        artifacts.verify_all()
        return "already present, hash verified"
    except artifacts.ArtifactError:
        pass
    repo_id = os.getenv("MODEL_REPO_ID", "").strip()
    if not repo_id:
        raise artifacts.ArtifactError("MODEL_REPO_ID is not set (the private HF model repo holding svm.joblib)")
    revision = os.getenv("MODEL_REPO_REVISION", "").strip() or "main"
    artifacts.fetch_all(repo_id, revision=revision, token=artifacts.read_token())
    return f"downloaded from {repo_id}@{revision}, hash verified"


def fetch_ocr() -> str:
    from src.ocr.ocr import download_models, parse_languages

    download_models()
    return f"EasyOCR models ready for {','.join(parse_languages())}"


def fetch_rag(chroma_dir: Path) -> str:
    from src.rag.rag_engine import RAGEngine

    engine = RAGEngine(persist_dir=chroma_dir)
    engine.build_index()
    engine.retrieve("test query")  # proves the embedding model loads offline later
    return f"embedding model cached, index built in {chroma_dir}"


def fetch_openphish() -> str:
    from src.url_analyzer.refresh_openphish import refresh_openphish

    path = refresh_openphish()
    return f"snapshot saved to {path}"


def run(steps: list[str], chroma_dir: Path = Path("chroma_db")) -> int:
    """Run the named steps in order. Returns a process exit code (0 = all required steps OK)."""
    table = {
        "model": (fetch_model, True),
        "ocr": (fetch_ocr, True),
        "rag": (lambda: fetch_rag(chroma_dir), True),
        "openphish": (fetch_openphish, False),
    }
    failed_required = False
    for name in steps:
        fn, required = table[name]
        start = time.perf_counter()
        try:
            detail = fn()
            print(f"[prefetch] {name}: OK - {detail} ({time.perf_counter() - start:.1f}s)", flush=True)
        except Exception as exc:  # report the type and our own message; never a token
            level = "FAILED" if required else "skipped (optional)"
            print(f"[prefetch] {name}: {level} - {type(exc).__name__}: {exc}", flush=True)
            failed_required |= required
    return 1 if failed_required else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Pre-download models and data for the API.")
    parser.add_argument("--steps", default="model,ocr,rag,openphish",
                        help="Comma-separated subset of: model, ocr, rag, openphish.")
    parser.add_argument("--chroma-dir", type=Path, default=Path(os.getenv("CHROMA_DIR") or "chroma_db"))
    args = parser.parse_args(argv)
    steps = [s.strip() for s in args.steps.split(",") if s.strip()]
    unknown = set(steps) - {"model", "ocr", "rag", "openphish"}
    if unknown:
        parser.error(f"unknown step(s): {sorted(unknown)}")
    return run(steps, args.chroma_dir)


if __name__ == "__main__":
    sys.exit(main())
