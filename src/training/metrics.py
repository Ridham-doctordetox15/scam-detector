"""Evaluation helpers for the baselines: metrics, threshold tuning, breakdowns, charts.

Conventions used everywhere in Phase 3:

* ``scam`` is the **positive** class (label 1); ``safe`` is 0.
* A classifier produces a real-valued *score* (``decision_function``: higher = more
  scam-like). A message is flagged as scam when ``score >= threshold``; the default
  threshold is 0.0 and a tuned one is chosen on validation data only.
* Charts follow the project palette: a single blue ramp for confusion matrices, and
  neutral grey / aqua / violet for model variants (colour never means a class there).
"""
from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # headless
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.colors import LinearSegmentedColormap  # noqa: E402
from sklearn.metrics import average_precision_score, precision_recall_curve, roc_auc_score  # noqa: E402

from src.preprocessing.eda import (  # noqa: E402
    BASELINE,
    INK,
    INK_2,
    MUTED,
    SURFACE,
    _new_figure,
    _save,
    _style_axes,
    _title,
)

LABEL_NAMES = ("safe", "scam")
DEFAULT_THRESHOLD = 0.0
# Sequential blue ramp, light -> dark (steps 100, 250, 400, 550, 700 of the palette).
_BLUE_RAMP = ["#cde2fb", "#86b6ef", "#3987e5", "#1c5cab", "#0d366b"]
# Model-variant colours (validated slots): reference grey, aqua, violet.
VARIANT_COLORS = {"in-distribution": INK_2, "leave-one-source-out": "#1baf7a", "source-balanced (LOSO)": "#4a3aa7"}


def labels_to_binary(labels: pd.Series | list[str]) -> np.ndarray:
    """Map ``scam`` -> 1 and ``safe`` -> 0."""
    return (pd.Series(labels).to_numpy() == "scam").astype(int)


# --------------------------------------------------------------------------- #
# Metrics
# --------------------------------------------------------------------------- #
def confusion_counts(y_true: np.ndarray, y_pred: np.ndarray) -> np.ndarray:
    """2x2 matrix ``[[TN, FP], [FN, TP]]`` (rows = actual safe/scam, columns = predicted)."""
    y_true, y_pred = np.asarray(y_true).astype(int), np.asarray(y_pred).astype(int)
    tn = int(((y_true == 0) & (y_pred == 0)).sum())
    fp = int(((y_true == 0) & (y_pred == 1)).sum())
    fn = int(((y_true == 1) & (y_pred == 0)).sum())
    tp = int(((y_true == 1) & (y_pred == 1)).sum())
    return np.array([[tn, fp], [fn, tp]])


def _ratio(num: float, den: float) -> float:
    return float(num / den) if den else float("nan")


def binary_metrics(
    y_true: np.ndarray, scores: np.ndarray, threshold: float = DEFAULT_THRESHOLD
) -> dict[str, float]:
    """Precision, recall, F1, accuracy, FPR, AUCs and confusion counts for ``scam``.

    Undefined values (for example precision with no predicted positives, or AUC with
    a single class present) are returned as NaN rather than silently 0.

    Args:
        y_true: 0/1 labels.
        scores: Real-valued scores; ``score >= threshold`` is predicted scam.
        threshold: Decision threshold.
    """
    y_true = np.asarray(y_true).astype(int)
    scores = np.asarray(scores, dtype=float)
    y_pred = (scores >= threshold).astype(int)
    (tn, fp), (fn, tp) = confusion_counts(y_true, y_pred)
    precision, recall = _ratio(tp, tp + fp), _ratio(tp, tp + fn)
    f1 = _ratio(2 * precision * recall, precision + recall) if tp else (0.0 if (tp + fp + fn) else float("nan"))
    if y_true.sum() == 0:       # no scam rows at all: precision and F1 are meaningless, not zero
        precision = f1 = float("nan")
    both = len(np.unique(y_true)) == 2
    return {
        "n": int(len(y_true)),
        "n_scam": int(y_true.sum()),
        "threshold": float(threshold),
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "accuracy": _ratio(tp + tn, len(y_true)),
        "fpr": _ratio(fp, fp + tn),
        "roc_auc": float(roc_auc_score(y_true, scores)) if both else float("nan"),
        "pr_auc": float(average_precision_score(y_true, scores)) if both else float("nan"),
        "tn": int(tn), "fp": int(fp), "fn": int(fn), "tp": int(tp),
    }


def best_f1_threshold(y_true: np.ndarray, scores: np.ndarray) -> tuple[float, float]:
    """Threshold that maximises scam-class F1, and that F1.

    Picks the highest threshold among ties. The optimum is the score of some message
    (flagged when ``score >= threshold``); the value returned is the midpoint between that
    score and the next lower distinct score, which classifies every training point
    identically but does not sit exactly on a data point. With a single class present there
    is nothing to tune, so the default threshold is returned.
    """
    y_true = np.asarray(y_true).astype(int)
    scores = np.asarray(scores, dtype=float)
    if len(np.unique(y_true)) < 2:
        return DEFAULT_THRESHOLD, float("nan")
    precision, recall, thresholds = precision_recall_curve(y_true, scores)
    denom = precision[:-1] + recall[:-1]
    f1 = np.divide(2 * precision[:-1] * recall[:-1], denom, out=np.zeros_like(denom), where=denom > 0)
    best = int(np.flatnonzero(f1 == f1.max())[-1])       # highest threshold among ties
    t = float(thresholds[best])
    lower = scores[scores < t]
    return ((t + float(lower.max())) / 2 if len(lower) else t), float(f1[best])


def recall_first_threshold(y_true: np.ndarray, scores: np.ndarray, recall_target: float = 0.97) -> float:
    """Highest threshold that still flags at least ``recall_target`` of the scam rows.

    Used in Phase 4 (recall first). The cut is the k-th highest scam score with ``k = ceil(target * n_scam)``; the value
    returned is the midpoint between it and the next lower distinct score, so it flags exactly the same rows but does not sit
    on a data point. The Colab notebook carries a copy of this function; ``tests/test_phase4_notebook.py`` keeps them equal.

    Raises:
        ValueError: If there is no scam row.
    """
    y_true = np.asarray(y_true).astype(int)
    scores = np.asarray(scores, dtype=float)
    pos = np.sort(scores[y_true == 1])[::-1]
    if len(pos) == 0:
        raise ValueError("need at least one scam row to choose a threshold")
    k = min(max(int(np.ceil(recall_target * len(pos) - 1e-9)), 1), len(pos))
    t = float(pos[k - 1])
    lower = scores[scores < t]
    return float((t + lower.max()) / 2) if len(lower) else t


# --------------------------------------------------------------------------- #
# Breakdowns
# --------------------------------------------------------------------------- #
def group_metrics(
    df: pd.DataFrame, scores: np.ndarray, by: str, threshold: float = DEFAULT_THRESHOLD, min_rows: int = 1
) -> pd.DataFrame:
    """Per-group metrics table (one row per value of column ``by``).

    ``df`` needs ``label`` (``scam``/``safe``). Groups with a single class report NaN for
    the metrics that are undefined there (for example precision when no scam exists).

    Returns:
        Frame indexed by group with ``n``, ``n_scam``, precision, recall, F1, FPR and AUCs.
    """
    y = labels_to_binary(df["label"])
    scores = np.asarray(scores, dtype=float)
    rows = {}
    for group, idx in df.groupby(by, sort=True).indices.items():
        if len(idx) >= min_rows:
            rows[group] = binary_metrics(y[idx], scores[idx], threshold)
    cols = ["n", "n_scam", "precision", "recall", "f1", "fpr", "roc_auc", "pr_auc", "tp", "fp", "fn", "tn"]
    table = pd.DataFrame.from_dict(rows, orient="index")
    return table[cols] if not table.empty else pd.DataFrame(columns=cols)


# --------------------------------------------------------------------------- #
# Charts
# --------------------------------------------------------------------------- #
def plot_confusion_matrix(
    cm: np.ndarray, path: Path, title: str, subtitle: str | None = None
) -> Path:
    """Heat-map of a 2x2 confusion matrix (single blue ramp).

    Colour encodes the *row share* (how the actual class was split), so both classes are
    readable despite imbalance; each cell also prints its count and row percentage.
    """
    cm = np.asarray(cm)
    row_share = cm / np.maximum(cm.sum(axis=1, keepdims=True), 1)
    cmap = LinearSegmentedColormap.from_list("blue", _BLUE_RAMP)
    fig, ax = _new_figure(5.6, 5.0)
    ax.imshow(row_share, cmap=cmap, vmin=0, vmax=1)
    for i in range(2):
        for j in range(2):
            dark = row_share[i, j] > 0.5
            ax.text(j, i, f"{int(cm[i, j]):,}\n{row_share[i, j]:.1%}", ha="center", va="center",
                    fontsize=14, color=SURFACE if dark else INK, fontweight="bold")
    ax.set_xticks([0, 1], [f"predicted\n{n}" for n in LABEL_NAMES], fontsize=10.5, color=INK_2)
    ax.set_yticks([0, 1], [f"actual\n{n}" for n in LABEL_NAMES], fontsize=10.5, color=INK_2)
    ax.xaxis.tick_top()
    ax.tick_params(length=0)
    for side in ax.spines.values():
        side.set_visible(False)
    ax.set_xticks(np.arange(-0.5, 2, 1), minor=True)
    ax.set_yticks(np.arange(-0.5, 2, 1), minor=True)
    ax.grid(which="minor", color=SURFACE, linewidth=4)
    ax.tick_params(which="minor", length=0)
    fig.subplots_adjust(top=0.72)
    _title(fig, title, subtitle)
    return _save(fig, path)


def plot_loso_comparison(table: pd.DataFrame, path: Path, metric: str = "roc_auc",
                         title: str = "Leave-one-source-out", subtitle: str | None = None) -> Path:
    """Grouped bars: ``metric`` per held-out source for each evaluation variant.

    ``table`` needs columns ``source``, ``variant`` (keys of :data:`VARIANT_COLORS`) and
    ``metric``. Every bar carries its value (the aqua series is below 3:1 contrast).
    """
    sources = list(dict.fromkeys(table["source"]))
    variants = [v for v in VARIANT_COLORS if v in set(table["variant"])]
    fig, ax = _new_figure(9.5, 4.8)
    width = 0.8 / max(len(variants), 1)
    x = np.arange(len(sources))
    for k, variant in enumerate(variants):
        vals = [float(table[(table["source"] == s) & (table["variant"] == variant)][metric].iloc[0])
                if ((table["source"] == s) & (table["variant"] == variant)).any() else np.nan for s in sources]
        pos = x + (k - (len(variants) - 1) / 2) * width
        ax.bar(pos, vals, width=width - 0.04, color=VARIANT_COLORS[variant], edgecolor=SURFACE, linewidth=1.5,
               label=variant)
        for p, v in zip(pos, vals):
            if not np.isnan(v):
                ax.text(p, v + 0.008, f"{v:.3f}", ha="center", va="bottom", fontsize=8.5, color=INK)
    ax.set_xticks(x, sources, fontsize=10, color=INK_2)
    ax.set_ylim(0, 1.08)
    ax.set_ylabel(metric.replace("_", " ").upper(), color=MUTED, fontsize=9)
    _style_axes(ax)
    # Legend above the plot area so it can never sit on top of the bars.
    leg = ax.legend(frameon=False, fontsize=9, loc="lower left", bbox_to_anchor=(0.0, 1.0), ncols=len(variants))
    for text in leg.get_texts():
        text.set_color(INK_2)
    ax.axhline(0.5, color=BASELINE, linewidth=1, linestyle=(0, (4, 3)))
    ax.text(len(sources) - 0.5, 0.51, "chance", ha="right", va="bottom", fontsize=8.5, color=MUTED)
    fig.subplots_adjust(top=0.76)
    _title(fig, title, subtitle)
    return _save(fig, path)
