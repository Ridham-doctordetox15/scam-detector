"""Phase 3.5 baseline (TF-IDF + LR / SVM) re-run on the Phase 4 data configuration (L3b).

The recorded Phase 3.5 test numbers belong to L3 (policy D) on a different test set, so they cannot be compared with a transformer
trained on L3b. This module runs the unchanged Phase 3 protocol (``baseline.run_baseline``) on ``data/processed_phase4/``, then adds
what the transformer notebook reports: the same **recall-first threshold** (chosen on real validation rows), the short-message slice,
the false-positive rate on held-out legitimate promotions and service notices, and per-row test scores for paired comparison.

    python -m src.training.phase4_baseline

The L3b test split is scored by this run (once per model, as in Phase 3) and by the transformers; nothing was tuned on it.
"""
from __future__ import annotations

import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from src.training import baseline as B
from src.training import ladder
from src.training import metrics as M

PHASE4_DIR = Path("data/processed_phase4")
MODEL_DIR = Path("models/baseline_phase4")
FIGURE_DIR = Path("docs/figures/phase4")
OUT_JSON = MODEL_DIR / "phase4_baseline.json"
EXPERIMENT = "baseline_phase4"
RECALL_TARGET = 0.97                     # must equal RECALL_TARGET in the Colab notebook
KEEP = ("precision", "recall", "f1", "fpr", "roc_auc", "pr_auc", "tp", "fp", "fn", "tn", "n", "n_scam", "threshold")


def _summary(m: dict) -> dict:
    return {k: (None if (isinstance(m[k], float) and not np.isfinite(m[k])) else m[k]) for k in KEEP}


def load_fitted(model: str, model_dir: Path) -> B.FittedModel:
    """Rebuild a saved baseline (vectorizer, classifier, tuned threshold)."""
    art = joblib.load(Path(model_dir) / f"{model}.joblib")
    cfg = B.Config(art["config"]["features"], float(art["config"]["C"]),
                   None if art["config"]["class_weight"] == "None" else art["config"]["class_weight"])
    return B.FittedModel(model, cfg, art["vectorizer"], art["clf"], art["threshold"])


def operating_point_report(fitted: B.FittedModel, splits: B.Splits, threshold: float) -> dict:
    """Test metrics at ``threshold``: overall, short slice, per source, and the legitimate-promotion flag rate."""
    test = splits.test
    scores = fitted.scores(test)
    y = M.labels_to_binary(test["label"])
    short = ladder.short_slice(test)
    y_short = M.labels_to_binary(short["label"])
    bench = test["benchmark"].to_numpy().astype(bool)
    flagged = scores >= threshold
    by_source = {s: {"n": int(m), "flag_rate": float(flagged[bench & (test["source"] == s).to_numpy()].mean())}
                 for s in sorted(test.loc[bench, "source"].unique())
                 for m in [int((bench & (test["source"] == s).to_numpy()).sum())]}
    return {
        "threshold": float(threshold),
        "overall": _summary(M.binary_metrics(y, scores, threshold)),
        "short": _summary(M.binary_metrics(y_short, fitted.scores(short), threshold)),
        "by_source": {k: {m: (None if not np.isfinite(v) else float(v)) for m, v in row.items()}
                      for k, row in M.group_metrics(test, scores, "source", threshold).to_dict(orient="index").items()},
        "benchmark": {"n": int(bench.sum()), "flag_rate": float(flagged[bench].mean()) if bench.any() else None,
                      "by_source": by_source},
    }


def extras(model_dir: Path = MODEL_DIR, data_dir: Path = PHASE4_DIR, recall_target: float = RECALL_TARGET) -> dict:
    """Recall-first operating point next to the F1-tuned one, for each saved baseline; writes per-row test scores."""
    splits = B.load_splits(data_dir)
    val_real = splits.val_real
    y_val = M.labels_to_binary(val_real["label"])
    out: dict = {"recall_target": recall_target, "models": {}}
    for model in B.MODELS:
        fitted = load_fitted(model, model_dir)
        thr_rf = M.recall_first_threshold(y_val, fitted.scores(val_real), recall_target)
        out["models"][model] = {
            "title": B.MODEL_TITLES[model],
            "f1_tuned": operating_point_report(fitted, splits, fitted.threshold),
            "recall_first": operating_point_report(fitted, splits, thr_rf),
            "val_real_at_recall_first": _summary(M.binary_metrics(y_val, fitted.scores(val_real), thr_rf)),
        }
        scores = pd.DataFrame({"id": splits.test["id"].to_numpy(), "label": splits.test["label"].to_numpy(),
                               "source": splits.test["source"].to_numpy(), "score": fitted.scores(splits.test)})
        scores.to_csv(Path(model_dir) / f"test_scores_{model}.csv", index=False)
        out["models"][model]["thresholds"] = {"f1_tuned": fitted.threshold, "recall_first": thr_rf}
    return out


def main() -> int:
    """Run the baseline protocol on L3b and write ``models/baseline_phase4/phase4_baseline.json``."""
    B.EXPERIMENT_NAME = EXPERIMENT
    results = B.run_baseline(processed_dir=PHASE4_DIR, model_dir=MODEL_DIR, figure_dir=FIGURE_DIR)
    final = {"protocol": results, "extras": extras()}
    OUT_JSON.write_text(json.dumps(final, indent=1, default=str), encoding="utf-8")
    print("wrote", OUT_JSON)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
