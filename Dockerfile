# syntax=docker/dockerfile:1
# Scam & Phishing Message Detector API - CPU image for a Hugging Face Docker Space
# (or any Docker host). Everything is downloaded at BUILD time; at runtime the app
# is offline except for the Groq/Gemini explainer and Supabase feedback calls.
#
# Build-time inputs (on Hugging Face these come from the Space settings):
#   secret   HF_TOKEN            read access to the private model repo (never stored in the image)
#   variable MODEL_REPO_ID       e.g. your-username/scam-detector-models
#   variable MODEL_REPO_REVISION optional, default "main" (pin a commit hash for reproducible builds)
# Local build:
#   docker build --secret id=HF_TOKEN,env=HF_TOKEN --build-arg MODEL_REPO_ID=you/scam-detector-models -t scam-api .
#   docker run -p 7860:7860 --env-file .env scam-api

FROM python:3.11-slim

ARG MODEL_REPO_ID=""
ARG MODEL_REPO_REVISION="main"

# libglib2.0-0: required by opencv-python-headless (EasyOCR).
RUN apt-get update \
    && apt-get install -y --no-install-recommends libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Hugging Face runs containers as UID 1000; create that user before any COPY/download.
RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    HF_HOME=/home/user/app/.cache/huggingface \
    EASYOCR_MODULE_PATH=/home/user/app/.cache/easyocr \
    ANONYMIZED_TELEMETRY=False
WORKDIR /home/user/app

# Dependencies first (cached layer while only code changes).
COPY --chown=user requirements-api.txt .
RUN pip install --user --no-cache-dir -r requirements-api.txt \
        --extra-index-url https://download.pytorch.org/whl/cpu

# Application code and the (git-tracked) knowledge base. Nothing else from the repo.
COPY --chown=user src/ src/
COPY --chown=user api/ api/
COPY --chown=user data/knowledge_base/scam_patterns.json data/knowledge_base/scam_patterns.json

# Build-time downloads: model (hash-verified), EasyOCR, embedding model + Chroma index, OpenPhish.
# The token is mounted as a file for this one step only - it never becomes an ENV or a layer.
RUN --mount=type=secret,id=HF_TOKEN,mode=0444,required=true \
    HF_TOKEN_FILE=/run/secrets/HF_TOKEN \
    MODEL_REPO_ID="$MODEL_REPO_ID" \
    MODEL_REPO_REVISION="$MODEL_REPO_REVISION" \
    python -m api.prefetch

# Runtime: never download models (a missing one fails at startup, not on a request),
# one proxy hop in front (Hugging Face), no .env file in the image.
ENV HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1 \
    EASYOCR_DOWNLOAD_ENABLED=0 \
    TRUSTED_PROXY_HOPS=1 \
    LOAD_DOTENV=0

EXPOSE 7860
# One worker: every worker would load its own copy of every model.
CMD ["uvicorn", "api.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "7860", \
     "--workers", "1", "--no-access-log", "--timeout-keep-alive", "30"]
