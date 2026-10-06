"""Tests for src.rag.evaluate: hit-rate computation, threshold sweep, eval-set validation.

Pure-function tests only - no model, no ChromaDB, no network.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.rag import evaluate as E


def _record(entry_id: str, top_ids: list[str], similarity: float, origin: str = "written") -> dict:
    return {
        "expected_pattern_id": entry_id,
        "top_ids": top_ids,
        "top1_similarity": similarity,
        "origin": origin,
    }


# ---------------------------- _hit_rates ---------------------------- #
def test_hit_rates_top1_and_top3() -> None:
    records = [
        _record("a", ["a", "b", "c"], 0.9),   # top-1 hit
        _record("b", ["c", "b", "a"], 0.8),   # top-3 hit, not top-1
        _record("c", ["a", "b", "d"], 0.7),   # miss entirely
    ]
    rates = E._hit_rates(records)
    assert rates["n"] == 3
    assert rates["top1"] == pytest.approx(1 / 3)
    assert rates["top3"] == pytest.approx(2 / 3)


def test_hit_rates_excludes_no_match_rows() -> None:
    records = [
        _record("a", ["a"], 0.9),
        _record(E.NO_MATCH, ["a", "b"], 0.9),
    ]
    rates = E._hit_rates(records)
    assert rates["n"] == 1


def test_hit_rates_filters_by_origin() -> None:
    records = [
        _record("a", ["a"], 0.9, origin="written"),
        _record("b", ["x"], 0.9, origin="real"),
    ]
    written = E._hit_rates(records, origin="written")
    real = E._hit_rates(records, origin="real")
    assert written["n"] == 1 and written["top1"] == 1.0
    assert real["n"] == 1 and real["top1"] == 0.0


def test_hit_rates_empty_returns_none() -> None:
    rates = E._hit_rates([])
    assert rates == {"n": 0, "top1": None, "top3": None}


# ---------------------------- _sweep_threshold ---------------------------- #
def test_sweep_threshold_separates_clean_distributions() -> None:
    records = (
        [_record("a", ["a"], 0.9) for _ in range(5)]
        + [_record(E.NO_MATCH, [], 0.1) for _ in range(5)]
    )
    threshold, detail = E._sweep_threshold(records)
    assert detail["matched_confident_rate"] == 1.0
    assert detail["no_match_decline_rate"] == 1.0
    assert 0.1 < threshold < 0.9


def test_sweep_threshold_balances_despite_class_imbalance() -> None:
    """A large matched group must not let the sweep ignore a tiny no_match group."""
    records = (
        [_record("a", ["a"], 0.6) for _ in range(50)]
        + [_record(E.NO_MATCH, [], 0.55) for _ in range(2)]
    )
    threshold, detail = E._sweep_threshold(records)
    # picking a threshold just above 0.55 sacrifices no matched rows (all at 0.6)
    # but correctly declines both no_match rows - the balanced sweep should find it.
    assert detail["no_match_decline_rate"] == 1.0
    assert detail["matched_confident_rate"] == 1.0


def test_sweep_threshold_with_no_no_match_rows() -> None:
    records = [_record("a", ["a"], 0.6) for _ in range(3)]
    threshold, detail = E._sweep_threshold(records)
    assert detail["no_match_decline_rate"] is None
    assert detail["matched_confident_rate"] is not None


# ---------------------------- load_eval_set ---------------------------- #
def _minimal_entry(**overrides) -> dict:
    base = {
        "text": "sample message",
        "language": "en",
        "label": "scam",
        "expected_pattern_id": "fake_kyc_update",
        "origin": "written",
    }
    base.update(overrides)
    return base


def test_load_eval_set_valid(tmp_path: Path) -> None:
    path = tmp_path / "eval.json"
    path.write_text(json.dumps({"schema_version": 1, "entries": [_minimal_entry()]}), encoding="utf-8")
    entries = E.load_eval_set(path)
    assert len(entries) == 1


def test_load_eval_set_missing_key_raises(tmp_path: Path) -> None:
    entry = _minimal_entry()
    del entry["label"]
    path = tmp_path / "eval.json"
    path.write_text(json.dumps({"schema_version": 1, "entries": [entry]}), encoding="utf-8")
    with pytest.raises(ValueError, match="missing keys"):
        E.load_eval_set(path)


def test_load_eval_set_bad_origin_raises(tmp_path: Path) -> None:
    path = tmp_path / "eval.json"
    path.write_text(
        json.dumps({"schema_version": 1, "entries": [_minimal_entry(origin="synthetic")]}), encoding="utf-8"
    )
    with pytest.raises(ValueError, match="origin"):
        E.load_eval_set(path)


def test_real_eval_set_file_is_valid() -> None:
    entries = E.load_eval_set(E.DEFAULT_EVAL_SET_PATH)
    assert len(entries) >= 40
    origins = {e["origin"] for e in entries}
    assert origins == set(E.ORIGINS)
    assert sum(1 for e in entries if e["origin"] == "real") >= 15
    assert sum(1 for e in entries if e["expected_pattern_id"] == E.NO_MATCH) >= 1


# ---------------------------- report formatting ---------------------------- #
def test_fmt_handles_none() -> None:
    assert E._fmt(None) == "n/a"
    assert E._fmt(0.5) == "50%"
