import names from "./patternNames.json";

export type PatternCategory = "scam" | "legitimate";

export interface PatternInfo {
  name: string;
  /** null when the id is not in the synced list (e.g. a newer backend). */
  category: PatternCategory | null;
}

const PATTERNS = names as Record<string, { name: string; category: PatternCategory }>;

/**
 * Human-readable name and category for a knowledge-base pattern id (synced from
 * data/knowledge_base/scam_patterns.json by scripts/sync-patterns.mjs). Unknown ids are
 * prettified instead of hidden, so a newer backend still shows something sensible.
 */
export function patternInfo(id: string): PatternInfo {
  const known = Object.prototype.hasOwnProperty.call(PATTERNS, id) ? PATTERNS[id] : undefined;
  if (known) return { name: known.name, category: known.category };
  const words = id.replace(/[_-]+/g, " ").trim();
  return { name: words ? words.charAt(0).toUpperCase() + words.slice(1) : id, category: null };
}
