"""Tests for src.training.metrics."""
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.training import metrics as M


def test_labels_to_binary() -> None:
    assert M.labels_to_binary(["scam", "safe", "scam"]).tolist() == [1, 0, 1]
    assert M.labels_to_binary(pd.Series(["safe"])).tolist() == [0]


def test_confusion_counts_layout() -> None:
    cm = M.confusion_counts(np.array([0, 0, 0, 1, 1, 1, 1]), np.array([0, 1, 1, 0, 0, 1, 1]))
    assert cm.tolist() == [[1, 2], [2, 2]]        # [[TN, FP], [FN, TP]]


def test_binary_metrics_known_values() -> None:
    y = np.array([1, 1, 1, 1, 0, 0, 0, 0, 0, 0])
    s = np.array([0.9, 0.8, 0.7, 0.1, 0.6, 0.2, 0.1, 0.0, -0.1, -0.2])
    m = M.binary_metrics(y, s, threshold=0.5)        # predicted scam: scores >= 0.5
    assert (m["tp"], m["fp"], m["fn"], m["tn"]) == (3, 1, 1, 5)
    assert m["precision"] == pytest.approx(0.75) and m["recall"] == pytest.approx(0.75)
    assert m["f1"] == pytest.approx(0.75) and m["accuracy"] == pytest.approx(0.8)
    assert m["fpr"] == pytest.approx(1 / 6)
    assert m["roc_auc"] == pytest.approx(0.8958333, abs=1e-6)       # 21.5 of 24 scam/safe pairs ordered
    assert 0.8 < m["pr_auc"] <= 1.0
    assert m["n"] == 10 and m["n_scam"] == 4 and m["threshold"] == 0.5


def test_threshold_is_inclusive() -> None:
    m = M.binary_metrics(np.array([1, 0]), np.array([0.5, 0.4]), threshold=0.5)
    assert m["tp"] == 1 and m["fp"] == 0


def test_undefined_metrics_are_nan_not_zero() -> None:
    m = M.binary_metrics(np.array([0, 0, 1]), np.array([-1.0, -2.0, -3.0]), threshold=0.0)   # nothing flagged
    assert np.isnan(m["precision"]) and m["recall"] == 0.0 and m["f1"] == 0.0
    only_safe = M.binary_metrics(np.array([0, 0, 0]), np.array([0.1, -0.1, -0.2]), threshold=0.0)
    assert np.isnan(only_safe["recall"]) and np.isnan(only_safe["roc_auc"]) and np.isnan(only_safe["pr_auc"])
    assert np.isnan(only_safe["precision"]) and np.isnan(only_safe["f1"])     # no scam rows: undefined, not 0
    assert only_safe["fpr"] == pytest.approx(1 / 3)


def test_perfect_and_worst_classifiers() -> None:
    y = np.array([0, 0, 1, 1])
    perfect = M.binary_metrics(y, np.array([-2.0, -1.0, 1.0, 2.0]))
    assert perfect["f1"] == 1.0 and perfect["roc_auc"] == 1.0 and perfect["accuracy"] == 1.0
    worst = M.binary_metrics(y, np.array([2.0, 1.0, -1.0, -2.0]))
    assert worst["f1"] == 0.0 and worst["roc_auc"] == 0.0


def test_best_f1_threshold_separates_perfectly_separable_scores() -> None:
    y = np.array([0, 0, 0, 1, 1, 1])
    s = np.array([-3.0, -2.0, -1.0, 1.0, 2.0, 3.0])
    threshold, f1 = M.best_f1_threshold(y, s)
    assert f1 == pytest.approx(1.0) and threshold == pytest.approx(0.0)     # midway between -1 and 1
    assert M.binary_metrics(y, s, threshold)["f1"] == 1.0


def test_best_f1_threshold_beats_the_default_when_scores_are_shifted() -> None:
    rng = np.random.default_rng(0)
    y = np.array([0] * 200 + [1] * 200)
    s = np.concatenate([rng.normal(2.0, 0.5, 200), rng.normal(4.0, 0.5, 200)])   # everything > 0
    threshold, f1 = M.best_f1_threshold(y, s)
    assert 2.5 < threshold < 3.9
    assert f1 > M.binary_metrics(y, s, 0.0)["f1"]


def test_best_f1_threshold_single_class_returns_default() -> None:
    assert M.best_f1_threshold(np.array([0, 0, 0]), np.array([1.0, 2.0, 3.0]))[0] == M.DEFAULT_THRESHOLD
    assert M.best_f1_threshold(np.array([1, 1]), np.array([1.0, 2.0]))[0] == M.DEFAULT_THRESHOLD


def test_best_f1_threshold_handles_tied_scores() -> None:
    threshold, f1 = M.best_f1_threshold(np.array([0, 1, 0, 1]), np.array([1.0, 1.0, 1.0, 1.0]))
    assert np.isfinite(threshold) and 0 <= f1 <= 1


def test_group_metrics_by_column() -> None:
    df = pd.DataFrame({
        "label": ["scam", "safe", "scam", "safe", "safe", "safe"],
        "lang": ["a", "a", "a", "a", "b", "b"],
    })
    scores = np.array([1.0, -1.0, -1.0, 1.0, -1.0, -1.0])
    t = M.group_metrics(df, scores, "lang", threshold=0.0)
    assert t.loc["a", "n"] == 4 and t.loc["a", "n_scam"] == 2
    assert t.loc["a", "precision"] == pytest.approx(0.5) and t.loc["a", "recall"] == pytest.approx(0.5)
    assert t.loc["b", "n_scam"] == 0 and np.isnan(t.loc["b", "recall"]) and t.loc["b", "fpr"] == 0.0
    assert np.isnan(t.loc["b", "precision"]) and np.isnan(t.loc["b", "f1"])   # safe-only group: undefined


def test_group_metrics_min_rows_and_empty() -> None:
    df = pd.DataFrame({"label": ["scam", "safe", "safe"], "g": ["x", "y", "y"]})
    t = M.group_metrics(df, np.array([1.0, -1.0, -1.0]), "g", min_rows=2)
    assert t.index.tolist() == ["y"]
    empty = M.group_metrics(df.iloc[0:0], np.array([]), "g")
    assert empty.empty and "f1" in empty.columns


def assert_png(path: Path) -> None:
    assert path.exists() and path.stat().st_size > 2_000
    assert path.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"


def test_confusion_matrix_plot(tmp_path: Path) -> None:
    out = M.plot_confusion_matrix(np.array([[900, 20], [30, 250]]), tmp_path / "sub" / "cm.png", "Title", "sub")
    assert_png(out)


def test_confusion_matrix_plot_handles_empty_row(tmp_path: Path) -> None:
    assert_png(M.plot_confusion_matrix(np.array([[10, 0], [0, 0]]), tmp_path / "cm.png", "Title"))


def test_loso_plot(tmp_path: Path) -> None:
    table = pd.DataFrame({
        "source": ["a", "a", "a", "b", "b", "b"],
        "variant": ["in-distribution", "leave-one-source-out", "source-balanced (LOSO)"] * 2,
        "roc_auc": [0.99, 0.7, 0.72, 0.98, 0.9, np.nan],
    })
    assert_png(M.plot_loso_comparison(table, tmp_path / "loso.png", "roc_auc", "T", "S"))


def test_variant_colors_are_distinct() -> None:
    assert len(set(M.VARIANT_COLORS.values())) == len(M.VARIANT_COLORS)
