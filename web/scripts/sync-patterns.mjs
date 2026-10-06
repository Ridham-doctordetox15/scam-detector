// Copy knowledge-base pattern names and categories (id -> {name, category}) into
// src/lib/patternNames.json so the static site can show "Fake KYC Update / Account Block Threat"
// instead of "fake_kyc_update", and say whether the closest pattern is a scam or a genuine type.
// Run after editing data/knowledge_base/scam_patterns.json:  node scripts/sync-patterns.mjs
import { readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const kbPath = join(here, "..", "..", "data", "knowledge_base", "scam_patterns.json");
const outPath = join(here, "..", "src", "lib", "patternNames.json");

const kb = JSON.parse(readFileSync(kbPath, "utf-8"));
const entries = Array.isArray(kb) ? kb : kb.entries;
if (!Array.isArray(entries)) throw new Error("Could not find the list of patterns in the knowledge base");

const names = Object.fromEntries(
  entries
    .map((e) => [e.id, { name: e.name, category: e.category === "scam" ? "scam" : "legitimate" }])
    .sort(([a], [b]) => a.localeCompare(b)),
);
writeFileSync(outPath, `${JSON.stringify(names, null, 2)}\n`, "utf-8");
console.log(`Wrote ${Object.keys(names).length} patterns to ${outPath}`);
