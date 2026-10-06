# Deploying the API and the web app

The backend runs on two routes, both serving the same FastAPI app (`api.main:create_app`):

| | **A. Free: Gradio-SDK Space on ZeroGPU** | **B. Docker Space (CPU Basic)** |
|---|---|---|
| Cost | Free | Needs Hugging Face **PRO ($9/month)** to create |
| Who can use it | Accounts **older than 30 days** with a **verified email**; at most 2 ZeroGPU Spaces | Any PRO account |
| Entry point | `deploy/hf_space_gradio/app.py` | `Dockerfile` |
| When models download | At every process start (about 0.8 GB, a few minutes after each sleep) | Once, at image build time |
| Hardware | ZeroGPU host; its CPU and RAM for non-GPU work are **not documented** | 2 vCPU, 16 GB RAM, 50 GB disk |
| Tested | App tested locally; **not yet run on real ZeroGPU** | App tested locally; image not built locally (no Docker here) |

Free accounts can no longer create Docker Spaces. On 2026-09-30 the HF docs said: *"Gradio and Docker
Spaces run on compute and require a paid plan to create: PRO for personal accounts ... Free personal
accounts in good standing can still host up to 2 Gradio Spaces running on ZeroGPU."* Re-check this on
<https://huggingface.co/docs/hub/spaces-overview> before you start, because the policy may change.

If your account is **younger than 30 days**, route A isn't available yet. Do steps 1-2 now
(Supabase and the model repo), run the API locally in the meantime (step 5), and come back to
step 3A once the account is old enough.

---

## 1. Supabase feedback table (YOU DO, once)

1. Sign in at <https://supabase.com> and click **New project** (Free plan). Pick the region closest to
   your users (e.g. Mumbai). Store the database password in a password manager; the app never needs it.
2. Open **SQL Editor**, then **New query**, paste all of [`docs/supabase_feedback.sql`](supabase_feedback.sql),
   and click **Run**. **Table Editor** should now show a `feedback` table with RLS enabled.
3. Open **Project Settings**, then **API Keys**:
   - Copy the **Project URL** (`https://<ref>.supabase.co`). This is `SUPABASE_URL`. The REST URL
     (`https://<ref>.supabase.co/rest/v1`) also works; the app strips the suffix.
   - Create or copy a **Secret key** (`sb_secret_...`). This is `SUPABASE_KEY`. **Don't use the
     publishable/anon key.** The table has no RLS policies on purpose, so a publishable key is
     refused and `/feedback` returns `502 feedback_storage_error`. That fails safe, but feedback
     won't be saved.
4. Locally, put both in `.env` (your `.env` may already contain a `SUPABASE_KEY`; make sure it's the
   secret key). Never put the secret key in any frontend or mobile app.
5. Free projects **pause after about 1 week without activity**. While a project is paused, `/feedback`
   returns 502. Restore it from the Supabase dashboard.

## 2. Private model repo (YOU DO, once, and again after retraining)

The only trained artifact the API loads is `models/baseline_phase4/svm.joblib` (about 11 MB). Its
SHA-256 is pinned in `api/artifacts.lock.json`, and the app refuses to load a file that doesn't match.

```powershell
.venv\Scripts\hf auth login                  # paste a WRITE token from huggingface.co/settings/tokens
.venv\Scripts\hf repos create scam-detector-models --repo-type model --private
.venv\Scripts\hf upload <your-username>/scam-detector-models models\baseline_phase4\svm.joblib svm.joblib --repo-type model
```

Then create a **separate, read-only token for the Space**: go to <https://huggingface.co/settings/tokens>,
choose **Create new token**, then **Fine-grained**, and give it *Read access to contents of selected
repos* for `<your-username>/scam-detector-models` only. If the Space ever leaks it, the damage is
limited to reading that one private repo.

If you retrain the model, update the hash in `api/artifacts.lock.json` (see the comment in the file)
and upload again.

## 3A. Free route: Gradio-SDK Space on ZeroGPU (YOU DO)

1. Go to <https://huggingface.co/new-space>. Set Owner = you, Space name = e.g. `scam-detector-api`,
   **SDK = Gradio** (any template), **Hardware = ZeroGPU**, Visibility = Public. Create it.
   - If ZeroGPU isn't offered, your account isn't eligible yet (see the 30-day condition above).
2. On the new Space, open **Files**, then `README.md`, and note the `sdk_version:` value Hugging Face wrote.
3. In **Settings**, then **Variables and secrets**, add:

   | Type | Name | Value |
   |---|---|---|
   | Secret | `HF_TOKEN` | the fine-grained read token from step 2 |
   | Secret | `GROQ_API_KEY` | your Groq key (optional: without it the template explainer is used) |
   | Secret | `GEMINI_API_KEY` | your Gemini key (optional fallback) |
   | Secret | `SUPABASE_URL` | from step 1 (not sensitive, but keeping it a secret is fine) |
   | Secret | `SUPABASE_KEY` | the **secret** key from step 1 |
   | Variable | `MODEL_REPO_ID` | `<your-username>/scam-detector-models` |
   | Variable | `MODEL_REPO_REVISION` | optional: a commit hash of the model repo, for reproducible deploys |
   | Variable | `CORS_ORIGINS` | the web app's exact origin, e.g. `https://scam-checker.vercel.app` (see [Web frontend](#web-frontend)) |

4. Stage and upload (from the project folder, in PowerShell):

   ```powershell
   .venv\Scripts\python -m api.stage_space --target gradio --sdk-version <value from step 2>
   .venv\Scripts\hf upload <your-username>/scam-detector-api build\hf_space_gradio . --repo-type space --commit-message "Deploy API"
   ```

   `stage_space` copies an allowlist of files only (code, knowledge base, lock file, README) and runs
   the secret scanner on them. `.env`, data and models never leave your machine.
5. Watch the **Logs** tab. Expect `[prefetch] model/ocr/rag/openphish` lines, then JSON
   `component_loaded` events and `startup_complete`. The first start takes several minutes.
   - If the build fails on a dependency conflict (the Gradio SDK pins its own FastAPI/pydantic, and
     this route is untested), copy the log for me.

## 3B. Docker route (only with HF PRO)

1. At <https://huggingface.co/new-space>, choose **SDK = Docker** (Blank) and **Hardware = CPU basic**.
2. Add the same secrets and variables as in 3A. `HF_TOKEN` is used at **build** time through
   `RUN --mount=type=secret,id=HF_TOKEN` (it's mounted as a file for that one step and never stored
   in the image). `MODEL_REPO_ID` is passed as a build argument.
3. Stage and upload:

   ```powershell
   .venv\Scripts\python -m api.stage_space --target docker
   .venv\Scripts\hf upload <your-username>/scam-detector-api build\hf_space_docker . --repo-type space --commit-message "Deploy API"
   ```

4. The build log shows `pip install`, then `[prefetch] ...`. The image is about 2.4 GB (estimate).
   At runtime, downloads are disabled (`HF_HUB_OFFLINE=1`, `EASYOCR_DOWNLOAD_ENABLED=0`).

## 4. Check the deployment (YOU DO)

Replace `<space-url>` with `https://<your-username>-scam-detector-api.hf.space`, and run from the
project folder:

```powershell
curl.exe -s <space-url>/health
curl.exe -s -X POST <space-url>/analyze/text -H "Content-Type: application/json" --data-binary "@docs/api_examples/text_scam.json"
curl.exe -s -X POST <space-url>/analyze/image -F "file=@docs/api_examples/whatsapp_dark_parcel_scam_en.png;type=image/png"
# Feedback: paste a prediction_id from the analyze response into a file first:
Set-Content -Encoding ascii fb.json '{"prediction_id": "<id>", "user_verdict": "correct"}'
curl.exe -s -X POST <space-url>/feedback -H "Content-Type: application/json" --data-binary "@fb.json"
Remove-Item fb.json
```

What to expect:
- `/health` returns `"status": "ok"`, with `llm` showing your providers and `feedback` ready.
- The scam text returns `scam`/`high`.
- The image returns `scam`/`high` with `ocr.dark_mode: true`.
- Feedback returns HTTP 201, and a row appears in Supabase's **Table Editor**.

A prediction id is forgotten after 24 hours **and whenever the Space restarts or sleeps**. Feedback
for an old id returns `404 unknown_prediction`, which is by design.

## 5. Run locally (no Space needed)

```powershell
.venv\Scripts\python -m api.prefetch                # model (already present) + OCR + RAG + OpenPhish
.venv\Scripts\python -m uvicorn api.main:create_app --factory --port 7860 --workers 1 --no-access-log
```

Then use the curl commands from step 4 with `http://127.0.0.1:7860`. With Docker Desktop (free for
personal use) you can also build the image locally:

```powershell
$env:HF_TOKEN = "<read token>"   # current shell only
docker build --secret id=HF_TOKEN,env=HF_TOKEN --build-arg MODEL_REPO_ID=<you>/scam-detector-models -t scam-api .
docker run -p 7860:7860 --env-file .env scam-api
```

---

# Web frontend

The site in `web/` is a static export (`npm run build` writes plain files to `web/out/`). It has no
server code and no secrets, so any free static host works. **Until the API is hosted, deploy it
without `NEXT_PUBLIC_API_URL`.** It then runs in demo mode and says so plainly: "Demo mode: the live
backend is not hosted yet".

Build-time settings (public values only; changing one needs a rebuild):

| Variable | Value |
|---|---|
| `NEXT_PUBLIC_API_URL` | API origin, no path and no trailing slash, e.g. `https://you-scam-api.hf.space`. **Leave unset until the backend is hosted.** |
| `NEXT_PUBLIC_BASE_PATH` | Only for GitHub Pages project sites: `/<repo-name>` |
| `NEXT_PUBLIC_REPO_URL` | Optional: `https://github.com/<you>/<repo>` (About page link) |

Check a build locally before deploying: `cd web; npm ci; npm test; npm run build; npm run check-build`.
`check-build` confirms that every page carries the CSP with the expected API origin, that fonts are
self-hosted, that the samples are present, and that nothing resembling a key is in the bundle.

## W1. Vercel (recommended, YOU DO)

1. Sign in at <https://vercel.com> with GitHub (Hobby plan, free) and push this repo to GitHub.
2. **Add New → Project**, then import the repo.
3. Set **Root Directory** to `web`. The framework is detected as Next.js. Keep the default build
   command (`next build`); Vercel handles `output: "export"` itself.
4. Environment variables: leave `NEXT_PUBLIC_API_URL` **unset** for now. Optionally set
   `NEXT_PUBLIC_REPO_URL`.
5. Deploy. Open the site: it should show the demo banner, and every sample should show a
   "Recorded demo result".

## W2. Static Hugging Face Space (alternative, YOU DO)

Static Spaces only serve files, so they should be free and shouldn't need the 30-day account age.
**Check that "Static" is offered on the Space creation page for your account first.**

1. Create a Space and choose the **Static** SDK, with blank as the template.
2. Build locally: `cd web; npm ci; npm run build` (with `$env:NEXT_PUBLIC_API_URL` set only once
   the API is hosted).
3. Upload the built files to the Space root: `hf upload <you>/<space> web\out . --repo-type space`.
   The Space's own `README.md` (which holds `sdk: static`) is not in `out/`, so it is kept.
4. The site's origin is `https://<you>-<space>.static.hf.space`. Check the exact address in the
   Space's "Embed this Space" menu.

## W3. GitHub Pages (alternative)

Project sites live under a sub-path, so build with `NEXT_PUBLIC_BASE_PATH=/<repo-name>`. Publish
`web/out/` with the official "Deploy static content to Pages" workflow (its `path` set to `web/out`).
`web/public/.nojekyll` is included so Pages serves the `_next/` folder.

## W4. Going live later (YOU DO, once the API is hosted)

1. On the API host, set `CORS_ORIGINS` to the site's **exact** origin, e.g.
   `https://scam-checker.vercel.app` (comma-separate several; no trailing slash; no wildcards).
   Restart the API.
2. On the static host, set `NEXT_PUBLIC_API_URL` to the API origin and rebuild/redeploy. On Vercel:
   **Settings → Environment Variables**, then **Deployments → Redeploy**.
3. Open the site. The demo banner should be gone and the text box enabled. Check a message, a
   screenshot and the feedback buttons.
4. If the banner says "the server is unreachable", open the browser console:
   - A CORS error means `CORS_ORIGINS` doesn't match the site's origin exactly.
   - A Content-Security-Policy error means the build used a different `NEXT_PUBLIC_API_URL`.
   - A free Space that is asleep wakes on the first request. Use "Try the live server again" after
     a minute.

Vercel preview deployments have their own origins. Add one to `CORS_ORIGINS` only if you need it.

