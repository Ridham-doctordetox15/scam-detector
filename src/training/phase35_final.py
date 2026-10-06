"""Run the full Phase 3 protocol once on the level chosen by the ablation ladder.

Only the level picked by ``ladder.choose_level`` is run here, and it is run once: this is the only place
the Phase 3.5 test split is scored. Rows withheld by the scam-definition policy (legitimate promotions and
service notices) are not part of training, tuning or the headline test metrics; they are scored separately
as a false-positive benchmark.

    python -m src.training.phase35_final            # uses the level chosen in data/processed/phase35_ladder.json
"""
from __future__ import annotations

import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from src.preprocessing import phase35 as p35
from src.training import baseline as B
from src.training import feature_audit as fa
from src.training import ladder
from src.training import metrics as M

OUT_DIR = Path("data/processed_p35")
MODEL_DIR = Path("models/baseline_p35")
FIGURE_DIR = Path("docs/figures/phase35")
LADDER_JSON = ladder.RESULTS_PATH
BEFORE_JSON = Path("data/processed/phase3_reference/baseline_results.json")
FINAL_JSON = OUT_DIR / "phase35_final.json"
EXPERIMENT = "baseline_phase35"
PHASE4_DIR = Path("data/processed_phase4")
PHASE4_LEVEL = "L3b"          # L3 normalisation + policy A: the owner's Phase 4 data configuration


def write_level(data: p35.LevelData, out_dir: Path) -> dict[str, int]:
    """Write train/val/test without withheld rows, plus the withheld rows as separate benchmark files."""
    out_dir.mkdir(parents=True, exist_ok=True)
    sizes = {}
    for name, frame in data.frames().items():
        keep = frame[~frame["withheld"]].reset_index(drop=True)
        keep.to_parquet(out_dir / f"{name}.parquet", index=False)
        frame[frame["withheld"]].reset_index(drop=True).to_parquet(out_dir / f"withheld_{name}.parquet", index=False)
        sizes[name] = len(keep)
        sizes[f"withheld_{name}"] = int(frame["withheld"].sum())
    return sizes


def extras(results: dict, model_dir: Path, out_dir: Path) -> dict:
    """Short-message test slice, false-positive benchmark and feature audit of the saved final models."""
    test = pd.read_parquet(out_dir / "test.parquet")
    short = ladder.short_slice(test)
    y_short = M.labels_to_binary(short["label"])
    train = pd.read_parquet(out_dir / "train.parquet")
    out: dict = {"short_test": {}, "benchmark": {}, "classifier_audit": {}, "n_short_test": len(short)}
    for model in B.MODELS:
        art = joblib.load(model_dir / f"{model}.joblib")
        cfg = B.Config(art["config"]["features"], float(art["config"]["C"]),
                       None if art["config"]["class_weight"] == "None" else art["config"]["class_weight"])
        fitted = B.FittedModel(model, cfg, art["vectorizer"], art["clf"], art["threshold"])
        scores = fitted.scores(short)
        m = M.binary_metrics(y_short, scores, fitted.threshold)
        out["short_test"][model] = {k: float(m[k]) for k in ("precision", "recall", "f1", "fpr", "roc_auc", "pr_auc")} | {
            "n": len(short), "scams": int(y_short.sum())}
        bench = {}
        for split in ("val", "test"):
            w = pd.read_parquet(out_dir / f"withheld_{split}.parquet")
            w = w[~w["is_synthetic"]]
            flagged = fitted.scores(w) > fitted.threshold if len(w) else np.array([], dtype=bool)
            bench[split] = {"n": len(w), "flag_rate": float(flagged.mean()) if len(w) else None,
                            "by_source": {s: {"n": int((w["source"] == s).sum()),
                                              "flag_rate": float(flagged[(w["source"] == s).to_numpy()].mean())}
                                          for s in sorted(w["source"].unique())}}
        out["benchmark"][model] = bench
        top = B.top_features(fitted, 30)
        out["classifier_audit"][model] = {
            c: {k: v for k, v in fa.audit_top_features(top)[c].items() if k != "features"} for c in ("scam", "safe")}
    out["word_audit"] = ladder.audit_level(train)
    return out


def export_phase4(level: str = PHASE4_LEVEL, out_dir: Path = PHASE4_DIR) -> dict[str, int]:
    """Write the Phase 4 data configuration (train/val/test parquet) without scoring anything.

    Policy A relabels legitimate promotions and service notices ``safe`` and keeps them, so nothing is withheld.
    """
    reference = p35.load_reference()
    india, _ = p35.build_india_rows(reference)
    data = p35.build_level(level, reference, india, p35.load_audit_actions())
    assert not any(frame["withheld"].any() for frame in data.frames().values()), "policy A must not withhold rows"
    assert not data.test["is_synthetic"].any()
    sizes = write_level(data, out_dir)
    (Path(out_dir) / "level_report.json").write_text(json.dumps({"level": level, "sizes": sizes, "report": data.report,
                                                                 "describe": p35.describe(data)}, indent=1, default=str),
                                                    encoding="utf-8")
    return sizes


def main(argv: list[str] | None = None) -> int:
    """Run the chosen level end to end and write ``phase35_final.json`` (or, with ``--export-phase4``, only write the Phase 4 data)."""
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--export-phase4", action="store_true", help=f"write {PHASE4_LEVEL} splits to {PHASE4_DIR}; no scoring")
    if parser.parse_args(argv).export_phase4:
        print("phase 4 data:", export_phase4())
        return 0
    ladder_results = json.loads(LADDER_JSON.read_text(encoding="utf-8"))["levels"]
    choice = ladder.choose_level(ladder_results)
    level = choice["chosen"]
    print(f"chosen level: {level} ({choice['reason']}); criterion met: {choice['criterion_met']}")
    reference = p35.load_reference()
    india, _ = p35.build_india_rows(reference)
    data = p35.build_level(level, reference, india, p35.load_audit_actions())
    sizes = write_level(data, OUT_DIR)
    print("written:", sizes)
    B.EXPERIMENT_NAME = EXPERIMENT
    results = B.run_baseline(processed_dir=OUT_DIR, model_dir=MODEL_DIR, figure_dir=FIGURE_DIR)
    extra = extras(results, MODEL_DIR, OUT_DIR)
    before = json.loads(BEFORE_JSON.read_text(encoding="utf-8"))
    final = {"choice": choice, "level": level, "sizes": sizes, "after": results, "extras": extra,
             "before_models": before["models"], "before_loso": before["loso"], "before_sizes": before["sizes"],
             "build_report": data.report}
    FINAL_JSON.write_text(json.dumps(final, indent=1, default=str), encoding="utf-8")
    print("wrote", FINAL_JSON)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
