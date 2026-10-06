"""Static checks and helper-parity tests for notebooks/02_train_transformers.ipynb.

The notebook must be self-contained for Colab, so its metric helpers are copies of ``src/training/metrics.py``. These tests execute
the notebook's pure cells (marked ``# PURE``) and compare them with the source of truth, so the two cannot drift apart silently.
"""
import ast
import re
from pathlib import Path

import nbformat
import numpy as np
import pandas as pd
import pytest

from src.training import metrics as M

NOTEBOOK = Path(__file__).resolve().parent.parent / "notebooks" / "02_train_transformers.ipynb"


@pytest.fixture(scope="module")
def nb():
    return nbformat.read(NOTEBOOK, as_version=4)


@pytest.fixture(scope="module")
def helpers(nb):
    """Namespace produced by executing every ``# PURE`` cell."""
    ns: dict = {}
    for cell in nb.cells:
        if cell.cell_type == "code" and cell.source.startswith("# PURE"):
            exec(compile(cell.source, "<notebook pure cell>", "exec"), ns)
    return ns


def code(nb) -> str:
    return "\n".join(c.source for c in nb.cells if c.cell_type == "code")


# ------------------------------------------------------------------ static checks
def test_notebook_is_valid_and_has_no_outputs(nb):
    nbformat.validate(nb)
    assert all(not c.outputs for c in nb.cells if c.cell_type == "code")


def test_every_code_cell_parses(nb):
    for i, c in enumerate(nb.cells):
        if c.cell_type == "code":
            ast.parse(c.source, filename=f"cell {i}")


def test_safe_defaults(nb):
    src = code(nb)
    assert re.search(r"^SMOKE_TEST = False", src, re.M)
    assert re.search(r"^PUSH_TO_HUB = False", src, re.M)
    assert re.search(r'^HF_REPO_ID = ""', src, re.M)


def test_no_secrets_or_tokens(nb):
    src = code(nb) + "\n".join(c.source for c in nb.cells if c.cell_type == "markdown")
    assert not re.search(r"hf_[A-Za-z0-9]{20,}|gsk_[A-Za-z0-9]{20,}|AIza[0-9A-Za-z_\-]{20,}", src)
    assert 'userdata.get("HF_TOKEN")' in src


def test_raw_text_is_never_read(nb):
    reads = re.findall(r"""\[\s*["']text_raw["']\s*\]|\.text_raw\b""", code(nb))
    # the only mention is the guard that asserts the column is absent
    assert all("not in train.columns" in line for line in code(nb).splitlines() if "text_raw" in line)
    assert len(reads) <= 1


def test_hub_upload_is_guarded_and_private(nb):
    cell = next(c.source for c in nb.cells if c.cell_type == "code" and "upload_folder" in c.source)
    assert cell.lstrip().startswith("if PUSH_TO_HUB:")
    assert "private=True" in cell


def test_selection_is_written_before_test_is_scored(nb):
    cells = [c.source for c in nb.cells if c.cell_type == "code"]
    sel = next(i for i, s in enumerate(cells) if "selection.json" in s)
    score = next(i for i, s in enumerate(cells) if "test_predictions_" in s)
    assert sel < score


def test_test_predictions_are_cached_not_rescored(nb):
    cell = next(c.source for c in nb.cells if c.cell_type == "code" and "test_predictions_" in c.source)
    assert ".exists()" in cell


# ------------------------------------------------------------------ helper parity
def test_metrics_match_source_of_truth(helpers):
    rng = np.random.default_rng(0)
    for _ in range(20):
        y = rng.integers(0, 2, 300)
        s = np.clip(y * 0.3 + rng.normal(0.4, 0.25, 300), 0, 1)
        thr = float(rng.uniform(0.2, 0.8))
        mine, ref = helpers["metrics"](y, s, thr), M.binary_metrics(y, s, thr)
        for key, value in ref.items():
            assert mine[key] == pytest.approx(value, nan_ok=True), key


def test_metrics_undefined_values_are_nan_not_zero(helpers):
    m = helpers["metrics"]([0, 0, 0], [0.1, 0.9, 0.2], 0.5)
    assert np.isnan(m["precision"]) and np.isnan(m["f1"]) and np.isnan(m["roc_auc"])
    assert m["fpr"] == pytest.approx(1 / 3)


@pytest.mark.parametrize("target", [0.9, 0.95, 0.97, 0.99, 1.0])
def test_recall_first_threshold_meets_target_and_is_highest(helpers, target):
    rng = np.random.default_rng(1)
    y = rng.integers(0, 2, 500)
    s = np.clip(y * 0.4 + rng.normal(0.3, 0.2, 500), 0, 1)
    thr = helpers["recall_first_threshold"](y, s, target)
    n_pos = int(y.sum())
    need = int(np.ceil(target * n_pos - 1e-9))
    flagged = int(((s >= thr) & (y == 1)).sum())
    assert flagged >= need
    # "highest": the cut is the need-th highest scam score; raising it past that score flags too few scams
    cut = np.sort(s[y == 1])[::-1][need - 1]
    assert thr <= cut
    assert int(((s > cut) & (y == 1)).sum()) < need


def test_recall_first_threshold_matches_source_of_truth(helpers):
    rng = np.random.default_rng(5)
    for target in (0.9, 0.97, 0.99):
        y = rng.integers(0, 2, 400)
        s = np.round(np.clip(y * 0.4 + rng.normal(0.3, 0.2, 400), 0, 1), 2)      # rounding creates ties
        assert helpers["recall_first_threshold"](y, s, target) == M.recall_first_threshold(y, s, target)


def test_recall_first_threshold_needs_scam_rows(helpers):
    with pytest.raises(ValueError):
        helpers["recall_first_threshold"]([0, 0], [0.1, 0.2], 0.9)


def test_operating_points_trade_recall_for_precision(helpers):
    rng = np.random.default_rng(2)
    y = rng.integers(0, 2, 800)
    s = np.clip(y * 0.35 + rng.normal(0.35, 0.2, 800), 0, 1)
    rows = helpers["operating_points"](y, s, (0.9, 0.95, 0.99), benchmark_mask=rng.integers(0, 2, 800).astype(bool))
    thresholds = [r["threshold"] for r in rows]
    assert thresholds == sorted(thresholds, reverse=True)
    assert all("promo_flag_rate" in r for r in rows)


def test_train_batches_cover_every_row_once_with_fixed_count(helpers):
    lengths = np.random.default_rng(3).integers(5, 200, 1037)
    for seed in (0, 1):
        batches = helpers["train_batches"](lengths, 32, np.random.default_rng(seed))
        flat = np.concatenate(batches)
        assert sorted(flat) == list(range(1037))
        assert len(batches) == int(np.ceil(1037 / 32))
        assert max(len(b) for b in batches) <= 32


def test_bootstrap_interval_contains_point_estimate(helpers):
    rng = np.random.default_rng(4)
    y = rng.integers(0, 2, 400)
    s = np.clip(y * 0.4 + rng.normal(0.3, 0.2, 400), 0, 1)
    ci = helpers["bootstrap_ci"](y, s, 0.5, n_boot=200, seed=0)
    point = helpers["metrics"](y, s, 0.5)
    for key, (lo, hi) in ci.items():
        assert lo <= point[key] <= hi, key


def test_group_table_counts(helpers):
    df = pd.DataFrame({"label": ["scam", "safe", "scam", "safe"], "source": ["a", "a", "b", "b"]})
    t = helpers["group_table"](df, [0.9, 0.1, 0.2, 0.3], "source", 0.5)
    assert t.loc["a", "recall"] == 1.0 and t.loc["b", "recall"] == 0.0 and t["n"].sum() == 4


def test_error_group_rules(helpers):
    g = helpers["error_group"]
    base = {"text": "hello", "source": "uci_sms_spam", "benchmark": False, "raw_chars": 100}
    assert g({**base, "benchmark": True}).startswith("legitimate")
    assert g({**base, "source": "hf_phishing_texts", "raw_chars": 5000}) == "long email"
    assert g({**base, "text": "click <URL> now"}) == "short message with a link"
    assert g(base) == "short message, no link"
    assert g({**base, "raw_chars": 600}) == "medium message"


def test_clean_json_removes_nan_and_numpy(helpers):
    out = helpers["clean_json"]({"a": np.float64("nan"), "b": np.int64(3), "c": [np.float32(1.5)], "d": np.bool_(True)})
    assert out == {"a": None, "b": 3, "c": [1.5], "d": True}


def _fake_results():
    m = {"precision": 0.9, "recall": 0.97, "f1": 0.93, "roc_auc": 0.99, "pr_auc": 0.98, "fpr": 0.02, "n": 100, "fp": 2, "fn": 1}
    ci = {k: [0.8, 0.95] for k in ("precision", "recall", "f1", "roc_auc")}
    return {
        "config": {"recall_target": 0.97, "learning_rate": 2e-5, "patience": 2, "max_length": 256, "seed": 42},
        "data": {"train_rows": 10, "val_rows": 5, "test_rows": 4, "real_indian_test_rows": None},
        "selection": {"best_key": "x"},
        "models": {"x": {"threshold": 0.31, "train": {"epochs_run": 3}}},
        "evaluation": {"x": {"overall": m, "short": {**m, "n": 50}, "ci95": ci, "benchmark": {"flag_rate": 0.1, "n": 20}}},
        "loso": [{"model": "x", "held_out": "hf_phishing_texts", "diagnostic_only": False, "n": 50,
                  "in_distribution": {"roc_auc": 0.99}, "loso": {"roc_auc": 0.7, "f1": 0.5}}],
        "export": {"model_name": "base/model", "size_mb": {"int8_onnx": 60.0, "fp32_onnx": 250.0},
                   "fp32_onnx": {"f1": 0.93}, "int8_onnx": {"f1": 0.92}, "int8_vs_fp32": {"label_agreement": 0.998},
                   "latency_batch1": {"fp32": {"median_ms": 20.0}, "int8": {"median_ms": 9.0}}, "cpu": "test cpu", "cpu_count": 2},
    }


def test_model_card_states_measured_values_and_limitations(helpers):
    card = helpers["build_model_card"](_fake_results())
    assert "0.3100" in card                      # threshold
    assert "No real Hinglish" in card             # the honest limitation when no Indian set exists
    assert "never seen" in card and "0.700" in card
    assert "Intended use" in card and "Limitations" in card
    res = _fake_results()
    res["data"]["real_indian_test_rows"] = 120
    assert "No real Hinglish" not in helpers["build_model_card"](res)
