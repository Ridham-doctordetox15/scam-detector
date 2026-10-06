"""Tests for src.rag.rag_engine: indexing, retrieval, rebuild-on-change, no confident match.

Uses a fake, deterministic (hash-based bag-of-words) embed_fn throughout, so no
real model or network call ever happens in these tests.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Sequence

import pytest

from src.rag import rag_engine as R

_DIM = 64


def _fake_vector(text: str) -> list[float]:
    vec = [0.0] * _DIM
    for word in set(text.lower().split()):
        idx = int(hashlib.md5(word.encode("utf-8")).hexdigest(), 16) % _DIM
        vec[idx] += 1.0
    norm = sum(x * x for x in vec) ** 0.5 or 1.0
    return [x / norm for x in vec]


def make_counting_embed_fn():
    """A deterministic bag-of-hashed-words embed_fn that counts its calls."""
    calls = {"n": 0}

    def embed(texts: Sequence[str]) -> list[list[float]]:
        calls["n"] += 1
        return [_fake_vector(t) for t in texts]

    embed.calls = calls  # type: ignore[attr-defined]
    return embed


ENTRIES = [
    {
        "id": "sample_scam_a",
        "name": "Sample Scam A",
        "category": "scam",
        "how_it_works": "Explains a fake scenario about free money.",
        "typical_phrases": ["free money now", "claim your prize today"],
        "red_flags": ["urgency"],
        "what_to_do": "Do not respond.",
        "languages": ["en"],
        "source_notes": "test fixture",
    },
    {
        "id": "sample_scam_b",
        "name": "Sample Scam B",
        "category": "scam",
        "how_it_works": "Explains a fake kyc update scenario.",
        "typical_phrases": ["urgent kyc update required", "account will be blocked"],
        "red_flags": ["urgency"],
        "what_to_do": "Do not respond.",
        "languages": ["en"],
        "source_notes": "test fixture",
    },
    {
        "id": "sample_legit_c",
        "name": "Sample Legit C",
        "category": "legitimate",
        "how_it_works": "Explains a genuine otp delivery scenario.",
        "typical_phrases": ["your otp is 12345 do not share"],
        "red_flags": ["informational only"],
        "what_to_do": "No action needed.",
        "languages": ["en"],
        "source_notes": "test fixture",
    },
]


def _write_kb(path: Path, entries: list[dict]) -> None:
    path.write_text(json.dumps({"schema_version": 1, "entries": entries}), encoding="utf-8")


@pytest.fixture
def kb_path(tmp_path: Path) -> Path:
    path = tmp_path / "kb.json"
    _write_kb(path, ENTRIES)
    return path


@pytest.fixture
def persist_dir(tmp_path: Path) -> Path:
    return tmp_path / "chroma_store"


# ---------------------------- compose_document ---------------------------- #
def test_compose_document_phrases_variant_excludes_how_it_works() -> None:
    doc = R.compose_document(ENTRIES[0], R.TEXT_VARIANT_PHRASES)
    assert "Sample Scam A" in doc
    assert "free money now" in doc
    assert "fake scenario" not in doc


def test_compose_document_phrases_how_variant_includes_how_it_works() -> None:
    doc = R.compose_document(ENTRIES[0], R.TEXT_VARIANT_PHRASES_HOW)
    assert "fake scenario" in doc


def test_compose_document_rejects_unknown_variant() -> None:
    with pytest.raises(ValueError, match="text_variant"):
        R.compose_document(ENTRIES[0], "bogus")


# ---------------------------- build_index / retrieve ---------------------------- #
def test_build_index_returns_entry_count(kb_path: Path, persist_dir: Path) -> None:
    engine = R.RAGEngine(kb_path, persist_dir, embed_fn=make_counting_embed_fn())
    assert engine.build_index() == len(ENTRIES)


def test_retrieve_finds_the_right_entry_by_word_overlap(kb_path: Path, persist_dir: Path) -> None:
    engine = R.RAGEngine(kb_path, persist_dir, embed_fn=make_counting_embed_fn())
    engine.build_index()
    result = engine.retrieve("free money claim your prize now", top_k=3)
    assert result.matches
    assert result.matches[0].entry_id == "sample_scam_a"
    assert result.matches[0].category == "scam"


def test_retrieve_respects_top_k(kb_path: Path, persist_dir: Path) -> None:
    engine = R.RAGEngine(kb_path, persist_dir, embed_fn=make_counting_embed_fn())
    engine.build_index()
    result = engine.retrieve("urgent kyc update required account blocked", top_k=2)
    assert len(result.matches) == 2


def test_matches_are_sorted_by_similarity_descending(kb_path: Path, persist_dir: Path) -> None:
    engine = R.RAGEngine(kb_path, persist_dir, embed_fn=make_counting_embed_fn())
    engine.build_index()
    result = engine.retrieve("urgent kyc update required", top_k=3)
    sims = [m.similarity for m in result.matches]
    assert sims == sorted(sims, reverse=True)


def test_retrieve_builds_index_lazily_if_not_built(kb_path: Path, persist_dir: Path) -> None:
    engine = R.RAGEngine(kb_path, persist_dir, embed_fn=make_counting_embed_fn())
    result = engine.retrieve("free money now")  # no explicit build_index() call
    assert result.matches


# ---------------------------- rebuild-on-change ---------------------------- #
def test_second_build_index_call_does_not_re_embed_when_unchanged(kb_path: Path, persist_dir: Path) -> None:
    embed_fn = make_counting_embed_fn()
    engine = R.RAGEngine(kb_path, persist_dir, embed_fn=embed_fn)
    engine.build_index()
    calls_after_first = embed_fn.calls["n"]
    engine.build_index()
    assert embed_fn.calls["n"] == calls_after_first


def test_build_index_rebuilds_when_kb_content_changes(kb_path: Path, persist_dir: Path) -> None:
    embed_fn = make_counting_embed_fn()
    engine = R.RAGEngine(kb_path, persist_dir, embed_fn=embed_fn)
    engine.build_index()
    calls_after_first = embed_fn.calls["n"]

    modified = [dict(e) for e in ENTRIES]
    modified[0] = {**modified[0], "typical_phrases": ["completely new phrase here"]}
    _write_kb(kb_path, modified)

    engine.build_index()
    assert embed_fn.calls["n"] > calls_after_first


def test_build_index_rebuilds_on_force(kb_path: Path, persist_dir: Path) -> None:
    embed_fn = make_counting_embed_fn()
    engine = R.RAGEngine(kb_path, persist_dir, embed_fn=embed_fn)
    engine.build_index()
    calls_after_first = embed_fn.calls["n"]
    engine.build_index(force=True)
    assert embed_fn.calls["n"] > calls_after_first


def test_different_text_variant_triggers_its_own_rebuild(kb_path: Path, persist_dir: Path) -> None:
    embed_fn = make_counting_embed_fn()
    phrases_engine = R.RAGEngine(kb_path, persist_dir, text_variant=R.TEXT_VARIANT_PHRASES, embed_fn=embed_fn)
    phrases_engine.build_index()
    calls_after_first = embed_fn.calls["n"]

    how_engine = R.RAGEngine(kb_path, persist_dir, text_variant=R.TEXT_VARIANT_PHRASES_HOW, embed_fn=embed_fn)
    how_engine.build_index()
    assert embed_fn.calls["n"] > calls_after_first  # different variant => separate collection, separate embed


# ---------------------------- empty / unrelated input ---------------------------- #
def test_empty_knowledge_base_retrieve_returns_no_matches(tmp_path: Path) -> None:
    kb = tmp_path / "empty_kb.json"
    kb.write_text(json.dumps({"schema_version": 1, "entries": []}), encoding="utf-8")
    engine = R.RAGEngine(kb, tmp_path / "store", embed_fn=make_counting_embed_fn())
    # empty_frame-equivalent: build_index tolerates zero entries without raising
    assert engine.build_index() == 0
    result = engine.retrieve("anything at all")
    assert result.matches == []
    assert result.confident is False


def test_unrelated_query_is_not_confident(kb_path: Path, persist_dir: Path) -> None:
    engine = R.RAGEngine(
        kb_path, persist_dir, embed_fn=make_counting_embed_fn(), min_confident_similarity=0.5
    )
    engine.build_index()
    result = engine.retrieve("zzqx wobble flim splorch nonsense words")
    assert result.confident is False


def test_confident_true_when_similarity_meets_threshold(kb_path: Path, persist_dir: Path) -> None:
    engine = R.RAGEngine(
        kb_path, persist_dir, embed_fn=make_counting_embed_fn(), min_confident_similarity=0.5
    )
    engine.build_index()
    result = engine.retrieve("free money now claim your prize today")
    assert result.confident is True


def test_confident_false_below_custom_threshold(kb_path: Path, persist_dir: Path) -> None:
    engine = R.RAGEngine(
        kb_path, persist_dir, embed_fn=make_counting_embed_fn(), min_confident_similarity=0.999
    )
    engine.build_index()
    result = engine.retrieve("free money now claim your prize today")
    assert result.matches  # a match still exists...
    assert result.confident is False  # ...but doesn't clear an artificially high bar
