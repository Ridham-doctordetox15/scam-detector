// Verify the static export in out/ after `npm run build`:
//   - every page exists and carries the Content-Security-Policy meta tag with the expected API origin
//   - fonts are self-hosted (no request to Google at runtime)
//   - nothing that looks like a secret ended up in the bundle
//   - the sample screenshots and the demo recording are included
// Usage: npm run build && npm run check-build      (exits 1 on any failure)
import { existsSync, readdirSync, readFileSync, statSync } from "node:fs";
import { dirname, join, relative } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const out = join(root, "out");
const expectedApi = (process.env.NEXT_PUBLIC_API_URL ?? "").trim().replace(/\/+$/, "");
const failures = [];
const fail = (msg) => failures.push(msg);

function walk(dir) {
  return readdirSync(dir).flatMap((name) => {
    const p = join(dir, name);
    return statSync(p).isDirectory() ? walk(p) : [p];
  });
}

if (!existsSync(out)) {
  console.error("out/ not found - run `npm run build` first.");
  process.exit(1);
}
const files = walk(out);
const textFiles = files.filter((f) => /\.(html|js|css|txt|json)$/.test(f));

// 1. Pages and CSP.
for (const page of ["index.html", "about/index.html", "404.html"]) {
  const path = join(out, page);
  if (!existsSync(path)) {
    fail(`missing page: ${page}`);
    continue;
  }
  const html = readFileSync(path, "utf-8");
  const rawCsp = html.match(/<meta http-equiv="Content-Security-Policy" content="([^"]+)"/i)?.[1];
  // React escapes quotes in attributes (&#x27;); browsers decode them before applying the policy.
  const csp = rawCsp?.replace(/&#x27;|&#39;/g, "'").replace(/&quot;/g, '"').replace(/&amp;/g, "&");
  if (!csp) fail(`${page}: no Content-Security-Policy meta tag`);
  else {
    const connect = csp.split(";").map((d) => d.trim()).find((d) => d.startsWith("connect-src"));
    const want = ["connect-src", "'self'", expectedApi].filter(Boolean).join(" ");
    if (connect !== want) fail(`${page}: expected "${want}", got "${connect}"`);
    for (const d of ["object-src 'none'", "form-action 'none'"]) if (!csp.includes(d)) fail(`${page}: CSP lacks ${d}`);
  }
  if (!/<html lang="en"/.test(html)) fail(`${page}: <html lang="en"> missing`);
}

// 2. Fonts are served from this site only.
for (const f of textFiles) {
  const text = readFileSync(f, "utf-8");
  if (/fonts\.(googleapis|gstatic)\.com/.test(text)) fail(`${relative(out, f)} references Google Fonts at runtime`);
}
const fontFiles = files.filter((f) => f.endsWith(".woff2"));
if (fontFiles.length === 0) fail("no self-hosted .woff2 font files found");

// 3. No secrets. Patterns for the providers this project uses, plus generic JWTs.
const SECRET_PATTERNS = [
  [/gsk_[A-Za-z0-9]{20,}/, "Groq key"],
  [/AIza[0-9A-Za-z_-]{30,}/, "Google API key"],
  [/sb_secret_[A-Za-z0-9_-]{10,}/, "Supabase secret key"],
  [/sb_publishable_[A-Za-z0-9_-]{10,}/, "Supabase key"],
  [/hf_[A-Za-z0-9]{30,}/, "Hugging Face token"],
  [/eyJ[A-Za-z0-9_-]{15,}\.eyJ[A-Za-z0-9_-]{15,}\.[A-Za-z0-9_-]{10,}/, "JWT"],
  [/(GROQ|GEMINI|SUPABASE)_[A-Z_]*KEY/, "secret variable name"],
  [/supabase\.co/, "Supabase URL (the site must talk only to our API)"],
];
for (const f of textFiles) {
  const text = readFileSync(f, "utf-8");
  for (const [re, label] of SECRET_PATTERNS) if (re.test(text)) fail(`${relative(out, f)} contains something like a ${label}`);
}

// 4. Samples and demo recording.
const samples = JSON.parse(readFileSync(join(root, "src", "lib", "samples.json"), "utf-8"));
for (const s of samples.image) if (!existsSync(join(out, s.file))) fail(`missing sample screenshot ${s.file}`);
const recorded = JSON.parse(readFileSync(join(root, "src", "demo", "recorded.json"), "utf-8"));
const js = textFiles.filter((f) => f.endsWith(".js")).map((f) => readFileSync(f, "utf-8")).join("\n");
if (!js.includes(recorded.recorded_at)) fail("demo recording not found in the JS bundle");

if (failures.length) {
  console.error(`Build check FAILED (${failures.length}):`);
  for (const f of failures) console.error(`  - ${f}`);
  process.exit(1);
}
console.log(
  `Build check passed: ${files.length} files, CSP connect-src = 'self'${expectedApi ? ` ${expectedApi}` : " (demo-only build)"}, ` +
    `${fontFiles.length} self-hosted font files, no secrets, ${samples.image.length} sample screenshots.`,
);
