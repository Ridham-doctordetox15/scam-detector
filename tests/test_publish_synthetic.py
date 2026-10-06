"""Tests for src.preprocessing.publish_synthetic (dry run by default; never uploads in tests)."""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from src.preprocessing import publish_synthetic as ps

STATS = {
    "rows": 100, "label": {"scam": 55, "safe": 45}, "raw_batches": 12, "raw_messages": 120,
    "kept_after_generator_filters": 110, "triage_rows": 20, "control_rows": 10, "added_by_rule_scan": 4,
    "reviewed": 34, "removed": 6, "flipped": 3, "flipped_safe_to_scam": 2, "flipped_scam_to_safe": 1,
    "kept_in_draft_then_removed": 2, "audit_action": {"unreviewed": 66, "keep": 31, "flip": 3},
    "by_generator": {"groq/m": {"scam": 30, "safe": 20}, "gemini/m": {"scam": 25, "safe": 25}},
    "by_language": {"hinglish": 60, "en": 40}, "by_topic": {"lottery": {"scam": 10, "safe": 8}},
    "length_chars": {"min": 20.0, "50%": 130.0, "mean": 140.0, "max": 400.0},
}


def test_card_renders_every_number_and_no_placeholders() -> None:
    card = ps.render_card(STATS)
    assert "{" not in card.replace("{{", "")            # no unfilled placeholders
    assert card.startswith("---\nlicense: cc-by-4.0")
    assert "100 short messages" in card and "55 scam, 45 safe" in card
    assert "`groq/m` (50 rows)" in card and "median 130 characters" in card
    assert "12 batches produced 120 messages" in card and "10 messages, leaving 110" in " ".join(card.split())
    assert "partial, not a full blind check" in " ".join(card.split()) and "no agreement rate is reported" in " ".join(card.split())                    # the partial-review caveat must stay
    assert "CC BY 4.0 does not override those terms" in card


def test_release_frame_hides_internal_columns() -> None:
    df = pd.DataFrame({c: ["x"] for c in [*ps.COLUMNS, "source", "family", "is_synthetic", "subtype"]})
    assert list(ps.release_frame(df).columns) == ps.COLUMNS


def test_secret_scan_flags_token_like_strings(tmp_path: Path) -> None:
    (tmp_path / "ok.txt").write_text("nothing to see", encoding="utf-8")
    assert ps.scan_for_secrets(tmp_path) == []
    (tmp_path / "bad.txt").write_text("token = hf_" + "a" * 30, encoding="utf-8")
    assert [Path(p).name for p in ps.scan_for_secrets(tmp_path)] == ["bad.txt"]


def test_upload_needs_a_token_and_a_clean_folder(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HF_TOKEN", raising=False)
    with pytest.raises(RuntimeError, match="HF_TOKEN"):
        ps.upload(tmp_path, "user/repo")
    monkeypatch.setenv("HF_TOKEN", "present")
    (tmp_path / "leak.txt").write_text("gsk_" + "b" * 30, encoding="utf-8")
    with pytest.raises(RuntimeError, match="secret-like"):
        ps.upload(tmp_path, "user/repo")


def test_main_is_a_dry_run_unless_told_otherwise(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    monkeypatch.setattr(ps, "RELEASE_DIR", tmp_path)
    monkeypatch.setattr(ps, "build_release", lambda: STATS | {"rows": 100})
    monkeypatch.setattr(ps, "upload", lambda *a, **k: pytest.fail("a dry run must never upload"))
    (tmp_path / "README.md").write_text("card", encoding="utf-8")
    assert ps.main([]) == 0
    assert ps.main(["--upload"]) == 0                    # --upload alone is not enough
    assert "DRY RUN" in capsys.readouterr().out
