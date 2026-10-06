"""Tests for src.rag.schema: knowledge-base entry validation."""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from src.rag import schema as S

VALID_ENTRY = {
    "id": "sample_pattern",
    "name": "Sample Pattern",
    "category": "scam",
    "how_it_works": "It works by doing something deceptive.",
    "typical_phrases": ["do this now", "urgent action required"],
    "red_flags": ["urgency", "unknown sender"],
    "what_to_do": "Do not respond.",
    "languages": ["en", "hinglish"],
    "source_notes": "Original text written for tests.",
}


def _entry(**overrides) -> dict:
    entry = copy.deepcopy(VALID_ENTRY)
    entry.update(overrides)
    return entry


def test_valid_entry_passes() -> None:
    S.validate_entry(_entry(), 0)


def test_valid_knowledge_base_passes() -> None:
    entries = [_entry(id="a"), _entry(id="b", category="legitimate")]
    assert S.validate_knowledge_base(entries) == entries


@pytest.mark.parametrize("missing_key", sorted(S.REQUIRED_KEYS))
def test_missing_key_raises(missing_key: str) -> None:
    entry = _entry()
    del entry[missing_key]
    with pytest.raises(ValueError, match="missing keys"):
        S.validate_entry(entry, 0)


def test_unexpected_key_raises() -> None:
    with pytest.raises(ValueError, match="unexpected keys"):
        S.validate_entry(_entry(extra_field="oops"), 0)


def test_bad_category_raises() -> None:
    with pytest.raises(ValueError, match="category"):
        S.validate_entry(_entry(category="not_a_category"), 0)


@pytest.mark.parametrize("key", ["id", "name", "how_it_works", "what_to_do", "source_notes"])
def test_blank_string_field_raises(key: str) -> None:
    with pytest.raises(ValueError, match="non-empty string"):
        S.validate_entry(_entry(**{key: "   "}), 0)


@pytest.mark.parametrize("key", ["typical_phrases", "red_flags", "languages"])
def test_empty_list_field_raises(key: str) -> None:
    with pytest.raises(ValueError, match="non-empty list"):
        S.validate_entry(_entry(**{key: []}), 0)


def test_list_with_blank_string_raises() -> None:
    with pytest.raises(ValueError, match="non-empty strings"):
        S.validate_entry(_entry(typical_phrases=["ok", "  "]), 0)


def test_invalid_language_raises() -> None:
    with pytest.raises(ValueError, match="invalid languages"):
        S.validate_entry(_entry(languages=["en", "klingon"]), 0)


@pytest.mark.parametrize("bad_id", ["Sample-Pattern", "sample pattern", "Sample_Pattern", "sample-pattern"])
def test_non_snake_case_id_raises(bad_id: str) -> None:
    with pytest.raises(ValueError, match="snake_case"):
        S.validate_entry(_entry(id=bad_id), 0)


def test_duplicate_id_raises() -> None:
    entries = [_entry(id="dup"), _entry(id="dup", category="legitimate")]
    with pytest.raises(ValueError, match="duplicate id"):
        S.validate_knowledge_base(entries)


def test_non_list_knowledge_base_raises() -> None:
    with pytest.raises(ValueError, match="must be a list"):
        S.validate_knowledge_base({})  # type: ignore[arg-type]


def test_empty_knowledge_base_is_valid() -> None:
    """An empty knowledge base is a degenerate but valid state - the RAG engine
    (not the schema) is responsible for handling zero entries gracefully."""
    assert S.validate_knowledge_base([]) == []


def test_load_knowledge_base_from_file(tmp_path: Path) -> None:
    kb_path = tmp_path / "kb.json"
    kb_path.write_text(json.dumps({"schema_version": 1, "entries": [_entry()]}), encoding="utf-8")
    entries = S.load_knowledge_base(kb_path)
    assert len(entries) == 1
    assert entries[0]["id"] == "sample_pattern"


def test_load_knowledge_base_without_entries_key_raises(tmp_path: Path) -> None:
    kb_path = tmp_path / "kb.json"
    kb_path.write_text(json.dumps([_entry()]), encoding="utf-8")
    with pytest.raises(ValueError, match="entries"):
        S.load_knowledge_base(kb_path)


def test_real_knowledge_base_file_is_valid() -> None:
    entries = S.load_knowledge_base(S.DEFAULT_KB_PATH)
    assert len(entries) >= 25
    ids = [e["id"] for e in entries]
    assert len(ids) == len(set(ids))
    categories = {e["category"] for e in entries}
    assert categories == S.CATEGORIES
