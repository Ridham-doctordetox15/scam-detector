---
title: Scam Message Detector API
emoji: 🛡️
colorFrom: indigo
colorTo: red
sdk: docker
app_port: 7860
pinned: false
short_description: Checks SMS/WhatsApp/email text or screenshots for scams
---

# Scam & Phishing Message Detector - API

FastAPI backend for an AI scam and phishing message detector for SMS, WhatsApp and email.
It handles English, Hindi and Hinglish, as text or screenshots. This is a portfolio project.

- `POST /analyze/text` with `{"text": "..."}`
- `POST /analyze/image` with a multipart `file` (PNG, JPEG or WebP, up to 5 MB)
- `POST /feedback` with `{"prediction_id": "...", "user_verdict": "correct" | "incorrect"}`
- `GET /health`: which components are ready
- `GET /docs`: interactive API docs

Each response returns a verdict (safe, suspicious or scam), a risk band, red flags, an explanation
and advice. It never returns a probability. Message text, screenshot text and IP addresses are
never logged. Feedback stores only the prediction id, your answer and the (non-text) predicted
labels.

**Limitations:** this is an automated assessment and it can be wrong. See the project README for
the evaluation results and known limitations.
