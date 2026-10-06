// Record REAL API responses for every sample into src/demo/recorded.json (demo mode data).
//
// Usage (the API must be running locally with its normal .env, so explanations come from the
// real LLM path):
//   python -m uvicorn api.main:create_app --factory --port 7860 --workers 1 --no-access-log
//   node scripts/record-demo.mjs [http://127.0.0.1:7860]
//
// Nothing here is invented: each entry is exactly what the API returned. prediction_ids are kept
// but unusable (the server forgets them), so the UI hides feedback in demo mode.
import { readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const root = join(here, "..");
const apiUrl = (process.argv[2] ?? "http://127.0.0.1:7860").replace(/\/+$/, "");
const samples = JSON.parse(readFileSync(join(root, "src", "lib", "samples.json"), "utf-8"));

async function post(path, init) {
  const res = await fetch(`${apiUrl}${path}`, { method: "POST", ...init });
  const body = await res.json();
  if (!res.ok) throw new Error(`${path} -> HTTP ${res.status}: ${JSON.stringify(body.error ?? body)}`);
  return body;
}

const health = await (await fetch(`${apiUrl}/health`)).json();
if (health.status !== "ok") throw new Error(`API not fully ready: ${JSON.stringify(health)}`);
if (!health.components.llm.detail.includes("groq") && !health.components.llm.detail.includes("gemini")) {
  console.warn("WARNING: no LLM provider configured - recordings will use the template explainer.");
}

const responses = {};
for (const s of samples.text) {
  responses[s.id] = await post("/analyze/text", {
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text: s.text }),
  });
  console.log(`${s.id}: ${responses[s.id].verdict}/${responses[s.id].risk_level} via ${responses[s.id].explainer_path}`);
}
for (const s of samples.image) {
  const bytes = readFileSync(join(root, "public", s.file));
  const form = new FormData();
  form.append("file", new Blob([bytes], { type: "image/png" }), s.file.split("/").pop());
  responses[s.id] = await post("/analyze/image", { body: form });
  console.log(`${s.id}: ${responses[s.id].verdict}/${responses[s.id].risk_level} via ${responses[s.id].explainer_path}`);
}

const out = {
  recorded_at: new Date().toISOString(),
  note: "Real responses from the project API (local run) for the built-in samples only. Recorded by web/scripts/record-demo.mjs.",
  responses,
};
writeFileSync(join(root, "src", "demo", "recorded.json"), `${JSON.stringify(out, null, 2)}\n`, "utf-8");
console.log(`Saved ${Object.keys(responses).length} responses.`);
