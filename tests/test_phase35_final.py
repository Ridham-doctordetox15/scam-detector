"""Tests for src.training.phase35_final (writing level frames and the Phase 4 export) and phase35_report."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from src.preprocessing import phase35 as p35
from src.training import phase35_final as fin
from src.training import phase35_report as rep
from tests.test_phase35 import frame, reference_frame, row


def test_write_level_separates_withheld_rows(tmp_path: Path) -> None:
    data = p35.build_level("L2a", reference_frame(), frame([row("airtel offer recharge now", "scam", p35.INDIA_SOURCE, "train", subtype="promo")]), {})
    sizes = fin.write_level(data, tmp_path)
    assert sizes["withheld_train"] == 2 and sizes["train"] == len(data.train) - 2
    assert pd.read_parquet(tmp_path / "withheld_train.parquet")["withheld"].all()
    assert not pd.read_parquet(tmp_path / "train.parquet")["withheld"].any()


def test_export_phase4_writes_policy_a_data_without_withholding(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    india = frame([row("airtel offer recharge now", "scam", p35.INDIA_SOURCE, "train", subtype="promo"),
                   row("stock tips for the group today", "safe", p35.INDIA_SOURCE, "test")])
    monkeypatch.setattr(p35, "load_reference", lambda *a, **k: reference_frame())
    monkeypatch.setattr(p35, "build_india_rows", lambda ref, *a, **k: (india, {}))
    monkeypatch.setattr(p35, "load_audit_actions", lambda *a, **k: {})
    sizes = fin.export_phase4("L3b", tmp_path)
    assert sizes["withheld_train"] == sizes["withheld_val"] == sizes["withheld_test"] == 0
    train = pd.read_parquet(tmp_path / "train.parquet")
    promo = train[train["text_raw"].str.contains("airtel")]
    assert promo["label"].tolist() == ["safe"] and promo["benchmark"].all()      # promotion relabelled safe, still tracked
    assert not pd.read_parquet(tmp_path / "test.parquet")["is_synthetic"].any()
    assert json.loads((tmp_path / "level_report.json").read_text())["level"] == "L3b"


def test_report_formatting_helpers() -> None:
    assert rep.f(None) == "n/a" and rep.f(0.12345) == "0.123" and rep.pct(0.876) == "88%" and rep.pct(None) == "n/a"
    assert rep.table(["a", "b"], [["1", "2"]]).splitlines()[1] == "|---|---:|"


def level_result(promo_rate: float) -> dict:
    audit = {"scam": {"fingerprint": 0, "signal_share": 0.33}, "safe": {"fingerprint": 8, "signal_share": 0.1}, "pass": False}
    return {"audit": audit, "val": {"f1": 0.95}, "val_short": {"f1": 0.9},
            "benchmark_flag_rate": {"rate": promo_rate, "n": 10, "by_source": {"uci_sms_spam": {"n": 5, "rate": promo_rate}}},
            "loso": {"hf_phishing_texts": {"roc_auc": 0.6}, "uci_sms_spam": {"roc_auc": 0.97}},
            "source_identifiability": {"accuracy": 0.9, "majority_baseline": 0.7},
            "single_class_shortcut_check": {"kaggle_india_spam_sms": {
                "n": 100, "scams": 1, "flag_rate_trained_on_source": 0.02, "flag_rate_source_held_out": 0.2,
                "by_group": {"promo_service": {"n": 30, "trained_on_source": 0.05, "source_held_out": 0.6},
                             "other": {"n": 70, "trained_on_source": 0.0, "source_held_out": 0.05}}}}}


def test_l3b_block_reports_the_shortcut_check_and_markers() -> None:
    block = rep.l3b_block(level_result(0.14), {"L3": level_result(0.75)})
    assert block.startswith(rep.START_B) and block.rstrip().endswith(rep.END_B)
    assert "75%" in block and "14%" in block and "6% vs 60%" not in block and "5% vs 60%" in block
    assert "India SMS" in block and "no AUC exists" in block and "Verdict" in block
