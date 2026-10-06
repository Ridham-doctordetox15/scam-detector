# Project: AI Scam & Phishing Message Detector

## Goal
A system that analyzes SMS, WhatsApp, and email messages (text or screenshots)
and returns: scam risk score, red flags, plain-language explanation, and
safety advice. Must handle mixed-language messages (English mixed with Indian
regional languages, e.g., Hinglish). This is a portfolio project, so code
quality, evaluation rigor, and documentation matter as much as features.

## Hard Constraints
- ONLY free tools and free tiers. Never suggest or use paid services.
- Allowed: Python 3.10+, PyTorch, Hugging Face (Transformers, Datasets, Hub,
  Spaces), scikit-learn, MLflow (local), Google Colab/Kaggle for GPU training,
  sentence-transformers, ChromaDB, Groq or Google Gemini free API tier, Ollama,
  EasyOCR, FastAPI, Streamlit or Next.js, Flutter (Android only), Supabase free
  tier, GitHub + GitHub Actions, Vercel free tier.
- No iOS. No Google Play Store. APK is distributed via GitHub Releases.
- There is NO local GPU. Any model training must be written as a Colab/Kaggle
  notebook for me to run, not run locally.

## Architecture
1. Preprocessing: clean text, extract URLs, mask phone numbers/OTPs/URLs.
2. Classifier: baseline TF-IDF + Logistic Regression and Linear SVM, then
   fine-tuned DistilBERT and a multilingual model (XLM-RoBERTa or MuRIL),
   exported to quantized ONNX for CPU inference.
3. URL analyzer: rule-based features + PhishTank list lookup.
4. RAG: JSON knowledge base of scam patterns, embedded with
   paraphrase-multilingual-MiniLM-L12-v2, stored in ChromaDB, top-3 retrieval.
5. LLM explainer: combines classifier score + URL findings + RAG matches,
   returns strict JSON (verdict, risk_level, red_flags, explanation,
   what_to_do) in the user's language. The LLM explains but NEVER overrides
   the classifier. Template-based fallback when the API fails or rate-limits.
   User messages are untrusted data (prompt-injection safe).
6. OCR: EasyOCR for screenshots, fed into the same pipeline.
7. FastAPI backend: /analyze/text, /analyze/image, /feedback, /health. Rate
   limiting, input size limits, CORS, privacy-safe logging. Dockerized for a
   free Hugging Face Docker Space.
8. Web frontend: risk meter, red flags, explanation, advice, feedback buttons,
   clickable sample messages, About page with limitations.
9. Flutter Android app: paste text, screenshot picker, Android share-intent.
10. pytest tests, GitHub Actions CI, full README.

## Folder Structure
data/{raw,processed,synthetic}/, notebooks/, src/{preprocessing,training,
inference,rag,llm,ocr,url_analyzer}/, api/, web/, mobile/, tests/, docs/,
results.md, PROGRESS.md, requirements.txt, Dockerfile, README.md, .env.example

## Coding Rules
- Clean, modular, commented code with type hints and docstrings.
- Never hardcode secrets. Use .env (gitignored) and keep .env.example updated.
- Never commit data files over 50MB, model weights, or .env. Keep .gitignore updated.
- Write pytest tests for every module in src/ and api/.
- Prevent data leakage: deduplicate BEFORE splitting; evaluate on real
  (non-synthetic) test data only.
- Pin dependency versions in requirements.txt.

## How to Work With Me
- Work on ONE phase at a time. Never start the next phase on your own.
- Always plan first and wait for my approval before writing code.
- After building, run the code and tests yourself and fix failures.
- Clearly list any "YOU DO" steps I must do manually (accounts, API keys,
  running Colab notebooks, deployment clicks).
- Record every real metric in results.md. Never invent numbers.
- At the end of each phase: update PROGRESS.md, write a 3-4 line summary I can
  use in my README and interviews, and suggest a git commit message.
