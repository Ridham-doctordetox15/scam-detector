"""Schema and validation for the scam-pattern knowledge base.

Follows the same style as :mod:`src.preprocessing.schema`: explicit required
keys, frozensets of allowed enum values, and a validator that raises a
descriptive :class:`ValueError` per problem rather than a stack trace.
"""
from __future__ import annotations

import json
from pathlib import Path

REQUIRED_KEYS: frozenset[str] = frozenset({
    "id", "name", "category", "how_it_works", "typical_phrases",
    "red_flags", "what_to_do", "languages", "source_notes",
})
LIST_KEYS: frozenset[str] = frozenset({"typical_phrases", "red_flags", "languages"})
STRING_KEYS: frozenset[str] = frozenset({"id", "name", "category", "how_it_works", "what_to_do", "source_notes"})

CATEGORY_SCAM = "scam"
CATEGORY_LEGITIMATE = "legitimate"
CATEGORIES: frozenset[str] = frozenset({CATEGORY_SCAM, CATEGORY_LEGITIMATE})

# Same code set as docs/labeling_guidelines.md, so KB entries and the real
# Indian test set describe language the same way.
ALLOWED_LANGUAGES: frozenset[str] = frozenset({
    "en", "hi", "hinglish",
    "ta_en", "te_en", "bn_en", "mr_en", "gu_en", "kn_en", "ml_en", "pa_en",
    "ta", "te", "bn", "mr", "gu", "kn", "ml", "pa",
    "other",
})

DEFAULT_KB_PATH = Path("data/knowledge_base/scam_patterns.json")


def validate_entry(entry: dict, index: int) -> None:
    """Check one entry. Raises ``ValueError`` describing the first problem found."""
    where = f"entry {index}" + (f" ({entry.get('id')!r})" if isinstance(entry, dict) and entry.get("id") else "")
    if not isinstance(entry, dict):
        raise ValueError(f"{where}: not an object")

    missing = REQUIRED_KEYS - entry.keys()
    if missing:
        raise ValueError(f"{where}: missing keys {sorted(missing)}")
    extra = entry.keys() - REQUIRED_KEYS
    if extra:
        raise ValueError(f"{where}: unexpected keys {sorted(extra)}")

    for key in STRING_KEYS:
        value = entry[key]
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{where}: {key!r} must be a non-empty string")

    for key in LIST_KEYS:
        value = entry[key]
        if not isinstance(value, list) or not value:
            raise ValueError(f"{where}: {key!r} must be a non-empty list")
        if not all(isinstance(v, str) and v.strip() for v in value):
            raise ValueError(f"{where}: {key!r} must contain only non-empty strings")

    if entry["category"] not in CATEGORIES:
        raise ValueError(f"{where}: category {entry['category']!r} not in {sorted(CATEGORIES)}")

    bad_languages = set(entry["languages"]) - ALLOWED_LANGUAGES
    if bad_languages:
        raise ValueError(f"{where}: invalid languages {sorted(bad_languages)}")

    if not entry["id"].replace("_", "").isalnum() or entry["id"] != entry["id"].lower():
        raise ValueError(f"{where}: id {entry['id']!r} must be lowercase snake_case")


def validate_knowledge_base(entries: list[dict]) -> list[dict]:
    """Validate every entry and check ``id`` uniqueness across the whole list.

    An empty list is valid (describes zero patterns); :mod:`src.rag.rag_engine`
    is expected to handle that gracefully rather than treating it as an error.

    Returns:
        The same list, to allow call chaining.

    Raises:
        ValueError: on any per-entry problem, a duplicate id, or a non-list input.
    """
    if not isinstance(entries, list):
        raise ValueError("knowledge base must be a list of entries")
    seen: set[str] = set()
    for i, entry in enumerate(entries):
        validate_entry(entry, i)
        entry_id = entry["id"]
        if entry_id in seen:
            raise ValueError(f"duplicate id {entry_id!r}")
        seen.add(entry_id)
    return entries


def load_knowledge_base(path: Path | str = DEFAULT_KB_PATH) -> list[dict]:
    """Load and validate the knowledge base JSON file at ``path``."""
    path = Path(path)
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or "entries" not in data:
        raise ValueError(f"{path}: expected a JSON object with an 'entries' list")
    return validate_knowledge_base(data["entries"])


if __name__ == "__main__":
    import sys

    kb_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_KB_PATH
    entries = load_knowledge_base(kb_path)
    print(f"{kb_path}: {len(entries)} entries OK "
          f"({sum(1 for e in entries if e['category'] == CATEGORY_SCAM)} scam, "
          f"{sum(1 for e in entries if e['category'] == CATEGORY_LEGITIMATE)} legitimate)")
