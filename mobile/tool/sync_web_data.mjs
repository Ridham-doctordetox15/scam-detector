#!/usr/bin/env node
/**
 * Generates lib/generated/web_data.g.dart from the web app's single sources of truth:
 *   - web/src/i18n/en.ts and hi.ts      (interface text, reused verbatim)
 *   - web/src/lib/samples.json          (the text samples)
 *   - web/src/lib/patternNames.json     (knowledge-base pattern names + category)
 *
 * Usage (from mobile/):
 *   node tool/sync_web_data.mjs           write the Dart file
 *   node tool/sync_web_data.mjs --check   exit 1 if the Dart file is out of date (used by a test)
 *
 * The .ts dictionaries are plain object literals plus type-only lines, so the type lines are
 * stripped and the rest is evaluated as a JavaScript module. No TypeScript tooling needed.
 */
import { readFileSync, writeFileSync, mkdirSync, mkdtempSync, rmSync } from "node:fs";
import { spawnSync } from "node:child_process";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const mobile = resolve(here, "..");
const web = resolve(mobile, "..", "web", "src");
const outPath = resolve(mobile, "lib", "generated", "web_data.g.dart");

/** Load an i18n .ts file by stripping its type-only syntax and importing it as JS. */
async function loadDictionary(file, exportName) {
  let src = readFileSync(resolve(web, "i18n", file), "utf8");
  src = src
    .replace(/^import type .*$/gm, "")
    .replace(/^export type .*$/gm, "")
    .replace(new RegExp(`export const ${exportName}\\s*:\\s*\\w+\\s*=`), `export const ${exportName} =`);
  const mod = await import(`data:text/javascript;base64,${Buffer.from(src, "utf8").toString("base64")}`);
  return mod[exportName];
}

/** Flatten nested objects to dotted keys; arrays stay arrays of strings. */
function flatten(obj, prefix = "", out = {}) {
  for (const [key, value] of Object.entries(obj)) {
    const path = prefix ? `${prefix}.${key}` : key;
    if (typeof value === "string") out[path] = value;
    else if (Array.isArray(value)) {
      if (!value.every((v) => typeof v === "string")) throw new Error(`Non-string array at ${path}`);
      out[path] = value;
    } else if (value && typeof value === "object") flatten(value, path, out);
    else throw new Error(`Unsupported value at ${path}`);
  }
  return out;
}

/** A Dart single-quoted string literal (escapes \, ', $ and control characters). */
function dartString(s) {
  const body = s
    .replace(/\\/g, "\\\\")
    .replace(/'/g, "\\'")
    .replace(/\$/g, "\\$")
    .replace(/\n/g, "\\n")
    .replace(/\r/g, "\\r")
    .replace(/\t/g, "\\t");
  return `'${body}'`;
}

const dartValue = (v) => (Array.isArray(v) ? `<String>[${v.map(dartString).join(", ")}]` : dartString(v));

function dartMap(name, flat) {
  const lines = Object.keys(flat)
    .sort()
    .map((k) => `  ${dartString(k)}: ${dartValue(flat[k])},`);
  return `const Map<String, Object> ${name} = <String, Object>{\n${lines.join("\n")}\n};\n`;
}

async function generate() {
  const en = flatten(await loadDictionary("en.ts", "en"));
  const hi = flatten(await loadDictionary("hi.ts", "hi"));
  const enKeys = Object.keys(en).sort().join("|");
  const hiKeys = Object.keys(hi).sort().join("|");
  if (enKeys !== hiKeys) throw new Error("en.ts and hi.ts have different keys");

  const samples = JSON.parse(readFileSync(resolve(web, "lib", "samples.json"), "utf8")).text;
  const patterns = JSON.parse(readFileSync(resolve(web, "lib", "patternNames.json"), "utf8"));

  const sampleLines = samples
    .map(
      (s) =>
        `  TextSample(id: ${dartString(s.id)}, expectedScam: ${s.expected === "scam"}, ` +
        `titleKey: ${dartString(`samples.titles.${s.titleKey}`)}, text: ${dartString(s.text)}),`,
    )
    .join("\n");
  const patternLines = Object.keys(patterns)
    .sort()
    .map((id) => `  ${dartString(id)}: (name: ${dartString(patterns[id].name)}, scam: ${patterns[id].category === "scam"}),`)
    .join("\n");

  return `// GENERATED FILE - DO NOT EDIT BY HAND.
// Source: web/src/i18n/{en,hi}.ts, web/src/lib/samples.json, web/src/lib/patternNames.json
// Regenerate from mobile/: node tool/sync_web_data.mjs
// ignore_for_file: lines_longer_than_80_chars

/// A clickable sample message, shared with the web app.
class TextSample {
  const TextSample({required this.id, required this.expectedScam, required this.titleKey, required this.text});

  final String id;

  /// What the sample was written to be. The result shown is whatever the API returns.
  final bool expectedScam;

  /// Interface-text key of the sample's title.
  final String titleKey;
  final String text;
}

/// English interface text from the web app, flattened to dotted keys.
${dartMap("webEn", en)}
/// Hindi interface text from the web app, flattened to dotted keys.
${dartMap("webHi", hi)}
/// The web app's text samples, in the same order.
const List<TextSample> textSamples = <TextSample>[
${sampleLines}
];

/// Knowledge-base pattern id -> display name and whether it is a scam type (else genuine).
const Map<String, ({String name, bool scam})> patternNames = <String, ({String name, bool scam})>{
${patternLines}
};
`;
}

/** Runs `dart format` on the generated source, so `dart format .` never changes the file. */
function dartFormat(source) {
  const dir = mkdtempSync(join(tmpdir(), "web-data-"));
  const file = join(dir, "web_data.g.dart");
  try {
    writeFileSync(file, source, "utf8");
    // The project's analysis_options.yaml sets the page width; pass it explicitly for the temp file.
    const run = spawnSync("dart", ["format", "--page-width", "120", file], { shell: process.platform === "win32" });
    if (run.status !== 0) throw new Error(`dart format failed: ${run.stderr}`);
    return readFileSync(file, "utf8").replace(/\r\n/g, "\n");
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
}

const output = dartFormat(await generate());
if (process.argv.includes("--check")) {
  let current = "";
  try {
    current = readFileSync(outPath, "utf8");
  } catch {
    // missing file counts as out of date
  }
  if (current.replace(/\r\n/g, "\n") !== output) {
    console.error("lib/generated/web_data.g.dart is out of date. Run: node tool/sync_web_data.mjs");
    process.exit(1);
  }
  console.log("web_data.g.dart is up to date.");
} else {
  mkdirSync(dirname(outPath), { recursive: true });
  writeFileSync(outPath, output, "utf8");
  console.log(`Wrote ${outPath}`);
}
