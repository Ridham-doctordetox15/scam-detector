"""Entry point for the FREE route: a Gradio-SDK Hugging Face Space on ZeroGPU hardware.

Why this exists: free Hugging Face accounts can no longer create Docker Spaces
(PRO is required), but accounts in good standing (verified email, older than
30 days) can host up to 2 Gradio-SDK Spaces on ZeroGPU for free. A Gradio-SDK
Space runs ``python app.py`` and exposes port 7860 - so this file simply
serves the *same* FastAPI app as the Docker image. The API is CPU-only and
never requests a GPU.

Differences from the Docker route (documented trade-offs):

* No build step: models are downloaded when the process starts
  (``api.prefetch``), so every cold start after the Space sleeps re-downloads
  ~0.8 GB before the API answers. The Docker route downloads at build time.
* ZeroGPU's CPU/RAM for non-GPU work is not documented - check ``/health``
  and the startup logs after deploying.
* Untested on real ZeroGPU hardware at the time of writing (it needs a
  30-day-old account); the FastAPI app itself is the same one tested locally.
"""
from __future__ import annotations

import os
import sys

# `spaces` must be imported before torch. ZeroGPU expects at least one @spaces.GPU
# function at startup; this one is never called (the whole API runs on CPU).
try:
    import spaces

    @spaces.GPU(duration=1)
    def _gpu_placeholder() -> None:
        """Never called - satisfies ZeroGPU's startup check. All inference runs on CPU."""
        return None
except ImportError:  # running outside Hugging Face
    pass

os.environ.setdefault("TRUSTED_PROXY_HOPS", "1")
os.environ.setdefault("LOAD_DOTENV", "0")
os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")


def main() -> None:
    from api.prefetch import run

    # Runtime prefetch (no Docker build step on this route). HF_TOKEN and MODEL_REPO_ID
    # come from the Space's secrets/variables.
    if run(["model", "ocr", "rag", "openphish"]) != 0:
        print("[app] a required download failed - see the [prefetch] lines above", flush=True)
        sys.exit(1)
    os.environ["EASYOCR_DOWNLOAD_ENABLED"] = "0"

    import uvicorn

    uvicorn.run("api.main:create_app", factory=True, host="0.0.0.0", port=int(os.getenv("PORT", "7860")),
                workers=1, access_log=False, timeout_keep_alive=30)


if __name__ == "__main__":
    main()
