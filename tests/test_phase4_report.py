"""Tests for src.training.phase4_report using small fake run outputs."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.training import phase4_report as R


def test_formatting_helpers() -> None:
    assert R.f(None) == "n/a" and R.f(float("nan")) == "n/a" and R.f(0.12345) == "0.1235"
    assert R.pct(0.876) == "88%" and R.pct(None) == "n/a"
    t = R.table(["a", "b"], [["x", "1"], ["y", "2"]])
    assert t.splitlines()[1] == "|---|---:|"


def test_paired_bootstrap_detects_a_clearly_better_system() -> None:
    rng = np.random.default_rng(0)
    y = rng.integers(0, 2, 600)
    good = np.clip(y * 0.7 + rng.normal(0.15, 0.1, 600), 0, 1)
    bad = np.clip(y * 0.1 + rng.normal(0.4, 0.25, 600), 0, 1)
    res = R.paired_bootstrap(y, good, 0.5, bad, 0.5, n_boot=200)
    assert res["roc_auc"]["diff"] > 0.2 and res["roc_auc"]["lo"] > 0 and res["roc_auc"]["p_a_better"] == 1.0


def test_paired_bootstrap_of_a_system_with_itself_is_zero() -> None:
    rng = np.random.default_rng(1)
    y = rng.integers(0, 2, 300)
    s = rng.random(300)
    res = R.paired_bootstrap(y, s, 0.5, s, 0.5, n_boot=100)
    assert all(v["diff"] == 0 and v["lo"] == 0 and v["hi"] == 0 for v in res.values())


def test_paired_bootstrap_rejects_length_mismatch() -> None:
    with pytest.raises(ValueError):
        R.paired_bootstrap(np.array([0, 1]), np.array([0.1, 0.9]), 0.5, np.array([0.1]), 0.5)


def _m(f1=0.9):
    return {"precision": 0.9, "recall": 0.97, "f1": f1, "roc_auc": 0.99, "pr_auc": 0.98, "fpr": 0.02, "n": 40, "n_scam": 12,
            "fp": 3, "fn": 1, "tp": 11, "tn": 25, "threshold": 0.3}


def _op(thr):
    return {"threshold": thr, "overall": _m(), "short": _m(0.85), "benchmark": {"n": 5, "flag_rate": 0.2, "by_source": {}},
            "by_source": {"uci_sms_spam": {"n": 20, "n_scam": 6, "precision": 0.9, "recall": 0.9, "f1": 0.9, "fpr": 0.05}}}


@pytest.fixture()
def run_outputs(tmp_path: Path):
    ids = [f"t{i}" for i in range(40)]
    rng = np.random.default_rng(3)
    labels = np.where(np.arange(40) % 3 == 0, "scam", "safe")
    y = (labels == "scam").astype(int)
    prob = np.clip(y * 0.6 + rng.normal(0.2, 0.15, 40), 0, 1)
    (tmp_path / "colab").mkdir()
    (tmp_path / "base").mkdir()
    pd.DataFrame({"id": ids, "label": labels, "source": "uci_sms_spam", "prob": prob}).to_csv(tmp_path / "colab/test_predictions_distilbert.csv", index=False)
    for m in ("logreg", "svm"):
        pd.DataFrame({"id": ids, "label": labels, "source": "uci_sms_spam", "score": rng.normal(y * 0.5, 1)}).to_csv(
            tmp_path / f"base/test_scores_{m}.csv", index=False)
    ev = {"threshold": 0.3, "overall": _m(), "short": _m(0.8), "ci95": {k: [0.8, 0.95] for k in ("precision", "recall", "f1", "roc_auc")},
          "by_source": [{"index": "uci_sms_spam", "n": 40, "n_scam": 14, "precision": 0.9, "recall": 0.9, "f1": 0.9, "fpr": 0.05}],
          "benchmark": {"n": 5, "flag_rate": 0.2},
          "synthetic_val_diagnostic_only": {"overall": _m()}, "real_indian": None}
    colab = {"smoke_test": False,
             "config": {"device": "cuda", "torch": "x", "transformers": "y", "seed": 42, "max_epochs": 6, "patience": 2, "max_length": 256,
                        "recall_target": 0.97, "loso_max_epochs": 3},
             "data": {"train_rows": 100, "val_rows": 50, "val_real_rows": 40, "val_synthetic_rows": 10, "test_rows": 40,
                      "test_scam_rate": 0.33, "test_benchmark_rows": 5, "real_indian_test_rows": None},
             "models": {"distilbert": {"hf_name": "distilbert-base-uncased", "threshold": 0.3,
                                       "operating_points": [{"recall_target": 0.97, "threshold": 0.3, "precision": 0.9, "fpr": 0.02, "fp": 3, "fn": 1,
                                                             "promo_flag_rate": 0.1}]}},
             "evaluation": {"distilbert": ev},
             "loso": [{"model": "distilbert", "held_out": "hf_phishing_texts", "diagnostic_only": False, "n": 20,
                       "in_distribution": {"roc_auc": 0.99}, "loso": {"roc_auc": 0.7, "pr_auc": 0.6, "f1": 0.5}}],
             "mitigation": {"trigger": {"loso_auc_below": 0.75, "gap_above": 0.15}, "fired": {"distilbert": True}},
             "export": {"model_name": "distilbert-base-uncased", "size_mb": {"fp32_onnx": 250.0, "int8_onnx": 65.0},
                        "fp32_onnx": _m(), "int8_onnx": _m(), "int8_vs_fp32": {"label_agreement": 0.99, "max_abs_prob_diff": 0.01},
                        "latency_batch1": {"fp32": {"median_ms": 20, "p95_ms": 30}, "int8": {"median_ms": 9, "p95_ms": 14}},
                        "throughput_seconds_per_1000_msgs": {"fp32": 8.0, "int8": 4.0}, "tokenizer_parity_rows_checked": 200},
             "error_analysis": [{"kind": "false negative (missed scam)", "pattern": "short message, no link", "source": "uci_sms_spam",
                                 "prob": 0.2, "text": "example text"}]}
    base = {"protocol": {"loso": [
        {"model": "logreg", "held_out": "hf_phishing_texts", "variant": "in-distribution", "eval_rows": 20, "roc_auc": 0.99, "pr_auc": 0.9, "f1": 0.9,
         "diagnostic_only": False},
        {"model": "logreg", "held_out": "hf_phishing_texts", "variant": "leave-one-source-out", "eval_rows": 20, "roc_auc": 0.6, "pr_auc": 0.5,
         "f1": 0.4, "diagnostic_only": False}]},
        "extras": {"models": {m: {"f1_tuned": _op(0.0), "recall_first": _op(-0.3), "thresholds": {"f1_tuned": 0.0, "recall_first": -0.3}}
                              for m in ("logreg", "svm")}}}
    return colab, base, tmp_path / "colab", tmp_path / "base"


def test_build_section_has_markers_tables_and_honest_labels(run_outputs) -> None:
    colab, base, cdir, bdir = run_outputs
    block = R.build_section(colab, base, cdir, bdir, n_boot=50)
    assert block.startswith(R.START) and block.rstrip().endswith(R.END)
    for needle in ("Paired difference", "Leave-one-source-out", "diagnostic only", "Real Indian test set: **not built**",
                   "**fired** for distilbert", "ONNX int8", "**not** comparable", "recall-first threshold"):
        assert needle in block, needle
    assert "TF-IDF + Linear SVM" in block and "distilbert-base-uncased" in block


def test_paired_table_rejects_mismatched_ids(run_outputs) -> None:
    colab, base, cdir, bdir = run_outputs
    scores = pd.read_csv(bdir / "test_scores_svm.csv").iloc[:-1]
    scores.to_csv(bdir / "test_scores_svm.csv", index=False)
    with pytest.raises(ValueError, match="id sets differ"):
        R.paired_table(colab, base, cdir, bdir, 20)


def test_update_results_md_replaces_block_and_keeps_the_rest(tmp_path: Path) -> None:
    path = tmp_path / "results.md"
    path.write_text("# Results\nintro\n", encoding="utf-8")
    R.update_results_md(path, f"{R.START}\nold\n{R.END}\n")
    R.update_results_md(path, f"{R.START}\nnew\n{R.END}\n")
    text = path.read_text(encoding="utf-8")
    assert text.count(R.START) == 1 and "new" in text and "old" not in text and text.startswith("# Results\nintro")


def test_error_doc_groups_by_pattern(run_outputs) -> None:
    colab, *_ = run_outputs
    doc = R.error_doc(colab)
    assert "(missed scam): short message, no link (1)" in doc and "Nothing was changed" in doc


def test_main_refuses_smoke_test_results(run_outputs, tmp_path: Path) -> None:
    colab, base, cdir, bdir = run_outputs
    colab["smoke_test"] = True
    (cdir / "phase4_results.json").write_text(json.dumps(colab), encoding="utf-8")
    (bdir / "phase4_baseline.json").write_text(json.dumps(base), encoding="utf-8")
    with pytest.raises(SystemExit, match="SMOKE_TEST"):
        R.main(["--colab-dir", str(cdir), "--baseline-json", str(bdir / "phase4_baseline.json")])


def test_baseline_section_reports_both_operating_points_and_threshold_transfer(run_outputs) -> None:
    _, base, _, _ = run_outputs
    base["protocol"]["sizes"] = {"train": 100, "val_real": 40, "val_synthetic": 10, "test": 40}
    for m in base["extras"]["models"].values():
        m["val_real_at_recall_first"] = {"recall": 0.97}
    base["extras"]["recall_target"] = 0.97
    block = R.baseline_section(base)
    assert block.startswith(R.BASE_START) and block.rstrip().endswith(R.BASE_END)
    for needle in ("F1-tuned threshold", "recall-first threshold", "Threshold transfer", "no scam rows in test", "different test set"):
        assert needle in block, needle
