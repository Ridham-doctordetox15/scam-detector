---
title: Scam Message Detector API
emoji: 🛡️
colorFrom: indigo
colorTo: red
sdk: gradio
sdk_version: {SDK_VERSION}
python_version: "3.12"
app_file: app.py
pinned: false
short_description: Checks SMS/WhatsApp/email text or screenshots for scams
---

# Scam & Phishing Message Detector - API (free ZeroGPU route)

This Space runs the same FastAPI backend as the Docker version, launched from `app.py`. It uses
CPU only and never requests the GPU. Models are downloaded when the Space starts, so the first
start after a sleep takes a few minutes.

- `POST /analyze/text` with `{"text": "..."}`
- `POST /analyze/image` with a multipart `file` (PNG, JPEG or WebP, up to 5 MB)
- `POST /feedback` with `{"prediction_id": "...", "user_verdict": "correct" | "incorrect"}`
- `GET /health` and `GET /docs`

Each response returns a verdict (safe, suspicious or scam), a risk band, red flags, an explanation
and advice. It never returns a probability. Message text, screenshot text and IP addresses are
never logged.
