"""Phase 3.5 ablation ladder: measure what each data-quality step does, on validation data only.

Each level (see ``src/preprocessing/phase35.py``) is scored with the *same* fixed classifier, so
differences come from the data, not from tuning. **The test split is never read here**: every
function takes train and validation frames only. The chosen level is evaluated on test once,
afterwards, by the full Phase 3 protocol (``baseline.run_baseline``).

Per level we report, on real validation rows that are not withheld:

* validation F1 / ROC-AUC / PR-AUC (threshold tuned on those rows, as in Phase 3),
* the same on the **short-message slice** (at most :data:`SHORT_CHARS` characters of raw text),
* leave-one-source-out ROC-AUC (train without a source, score that source's validation rows),
* **source identifiability**: how well a word model can tell the sources apart from the text alone
  (accuracy and its excess over always guessing the largest source),
* the **feature audit** of a word-only logistic model (``feature_audit.py``),
* the scam-flag rate on *legitimate promotions and service notices* in validation (the false-positive
  benchmark; under the old definition these rows were labelled scam, so the rate is not an error there).

Selection rule (written down before any level was run)
------------------------------------------------------
1. Only levels on the cumulative path L0, L1, L2a, L3, L4, L5 are eligible (L2b is a contrast).
2. A level is a *success* if it PASSES the feature audit: zero corpus fingerprints in the top-30
   features of both classes, and a scam-signal share of at least 50% in the scam class.
3. The chosen level is the **first** (least invasive) successful level on the path.
4. If none succeeds, the chosen level is the one with the fewest fingerprints across both classes
   (ties: higher scam-signal share, then the less invasive level), and the phase is reported as
   *not meeting its success criterion*, with the remaining fingerprints handed to Phase 4.
Validation F1 is reported but not used to select: the levels change the labels and rows, so their
validation sets differ and F1 is not comparable across them.
"""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.feature_extraction.text import TfidfVectorizer

from src.preprocessing import phase35 as p35
from src.training import feature_audit as fa
from src.training import metrics as M
from src.training.baseline import Config, fit_model, texts_of

logger = logging.getLogger(__name__)

SHORT_CHARS = 300
CLASSIFIER = Config("word+char", 1000.0, None)      # Phase 3's selected logistic regression
LOSO_MIN_POSITIVES = 20                              # skip a held-out source with fewer validation scams
SOURCE_ID_TRAIN_CAP = 8_000
SEED = 42
RESULTS_PATH = Path("data/processed/phase35_ladder.json")


def training_rows(train: pd.DataFrame) -> pd.DataFrame:
    """Training rows: everything except rows withheld by the scam-definition policy."""
    return train[~train["withheld"]]


def selection_rows(val: pd.DataFrame) -> pd.DataFrame:
    """Real validation rows that are not withheld: the only rows a level is scored on."""
    return val[~val["is_synthetic"] & ~val["withheld"]]


def short_slice(df: pd.DataFrame, chars: int = SHORT_CHARS) -> pd.DataFrame:
    """Rows whose *raw* text is at most ``chars`` characters."""
    return df[df["text_raw"].astype(str).str.len() <= chars]


def _metrics(y: np.ndarray, scores: np.ndarray, threshold: float) -> dict[str, float | int | None]:
    m = M.binary_metrics(y, scores, threshold)
    keep = ("precision", "recall", "f1", "fpr", "roc_auc", "pr_auc")
    return {**{k: (float(m[k]) if np.isfinite(m[k]) else None) for k in keep},
            "n": int(len(y)), "scams": int(y.sum())}


def audit_level(train_fit: pd.DataFrame, seed: int = SEED) -> dict:
    """Feature audit of the word-only audit model trained on ``train_fit``."""
    vec, clf = fa.word_audit_model(texts_of(train_fit), M.labels_to_binary(train_fit["label"]), seed)
    audit = fa.audit_top_features(fa.top_features_of(vec, clf))
    return {"pass": fa.passes(audit),
            **{cls: {k: audit[cls][k] for k in ("signal", "fingerprint", "format", "other", "signal_share",
                                                  "fingerprints", "signals", "features")} for cls in ("scam", "safe")}}


def source_identifiability(train_fit: pd.DataFrame, val_sel: pd.DataFrame, seed: int = SEED) -> dict:
    """How well text alone identifies the (real) source: accuracy, majority baseline and excess."""
    real_train = train_fit[~train_fit["is_synthetic"]]
    if len(real_train) > SOURCE_ID_TRAIN_CAP:
        real_train = real_train.sample(SOURCE_ID_TRAIN_CAP, random_state=seed)
    sources = sorted(real_train["source"].unique())
    if len(sources) < 2 or val_sel.empty:
        return {"accuracy": None, "majority_baseline": None, "excess": None, "sources": sources}
    vec = TfidfVectorizer(analyzer="word", ngram_range=(1, 2), min_df=2, sublinear_tf=True, dtype=np.float32)
    clf = LogisticRegression(C=10.0, random_state=seed, max_iter=500)            # multinomial: 2 or more sources
    clf.fit(vec.fit_transform(texts_of(real_train)), real_train["source"])
    val_known = val_sel[val_sel["source"].isin(sources)]
    acc = float((clf.predict(vec.transform(texts_of(val_known))) == val_known["source"]).mean())
    base = float(val_known["source"].value_counts(normalize=True).max())
    return {"accuracy": acc, "majority_baseline": base, "excess": acc - base, "sources": sources}


def evaluate_level(data: p35.LevelData, seed: int = SEED, cfg: Config = CLASSIFIER, say=print) -> dict:
    """All ladder metrics for one level, using ``data.train`` and ``data.val`` only."""
    t0 = time.perf_counter()
    train_fit, val_sel = training_rows(data.train), selection_rows(data.val)
    y_val = M.labels_to_binary(val_sel["label"])
    fitted = fit_model("logreg", cfg, train_fit, seed)
    scores = fitted.scores(val_sel)
    threshold, _ = M.best_f1_threshold(y_val, scores)
    out: dict = {
        "level": data.level.name, "description": data.level.description,
        "rows": p35.describe(data),
        "train_fit_rows": len(train_fit), "val_rows": len(val_sel),
        "threshold": float(threshold),
        "val": _metrics(y_val, scores, threshold),
    }
    short = short_slice(val_sel)
    out["val_short"] = _metrics(M.labels_to_binary(short["label"]), fitted.scores(short), threshold) if len(short) else None

    bench = data.val[data.val["benchmark"] & ~data.val["is_synthetic"]]
    flagged = fitted.scores(bench) > threshold if len(bench) else np.array([], dtype=bool)
    out["benchmark_flag_rate"] = {
        "n": int(len(bench)), "rate": float(flagged.mean()) if len(bench) else None,
        "by_source": {s: {"n": int((bench["source"] == s).sum()), "rate": float(flagged[(bench["source"] == s).to_numpy()].mean())}
                      for s in sorted(bench["source"].unique())},
    }
    out["audit"] = audit_level(train_fit, seed)
    out["source_identifiability"] = source_identifiability(train_fit, val_sel, seed)

    loso = {}
    for source in sorted(val_sel["source"].unique()):
        held = val_sel[val_sel["source"] == source]
        if held["label"].eq("scam").sum() < LOSO_MIN_POSITIVES or held["label"].eq("safe").sum() < LOSO_MIN_POSITIVES:
            continue
        rest = train_fit[train_fit["source"] != source]
        if rest["label"].nunique() < 2:
            continue
        m = fit_model("logreg", cfg, rest, seed)
        loso[source] = _metrics(M.labels_to_binary(held["label"]), m.scores(held), threshold)
    out["loso"] = loso

    # A source with (almost) no scams has no AUC. To catch a "this source means safe" shortcut we compare how
    # often its rows are flagged by a model that trained on it with one that never saw it.
    shortcut = {}
    for source in sorted(val_sel["source"].unique()):
        held = val_sel[val_sel["source"] == source]
        if source in loso or held["label"].eq("scam").sum() >= LOSO_MIN_POSITIVES:
            continue
        rest = train_fit[train_fit["source"] != source]
        if rest["label"].nunique() < 2:
            continue
        in_flag = fitted.scores(held) > threshold
        out_flag = fit_model("logreg", cfg, rest, seed).scores(held) > threshold
        legit = held["benchmark"].to_numpy()
        groups = {"promo_service": legit, "other": ~legit}
        shortcut[source] = {
            "n": int(len(held)), "scams": int(held["label"].eq("scam").sum()),
            "flag_rate_trained_on_source": float(in_flag.mean()), "flag_rate_source_held_out": float(out_flag.mean()),
            "by_group": {g: {"n": int(mask.sum()),
                             "trained_on_source": float(in_flag[mask].mean()) if mask.any() else None,
                             "source_held_out": float(out_flag[mask].mean()) if mask.any() else None}
                         for g, mask in groups.items()},
        }
    out["single_class_shortcut_check"] = shortcut
    out["seconds"] = round(time.perf_counter() - t0, 1)
    say(f"  {data.level.name}: val F1={out['val']['f1']:.4f} ROC-AUC={out['val']['roc_auc']:.4f} | "
        f"audit pass={out['audit']['pass']} (fp scam/safe {out['audit']['scam']['fingerprint']}/{out['audit']['safe']['fingerprint']}, "
        f"signal share {out['audit']['scam']['signal_share']:.0%}) | {out['seconds']}s")
    return out


def choose_level(results: dict[str, dict], path: tuple[str, ...] = p35.LADDER_ORDER) -> dict:
    """Apply the pre-registered selection rule (see the module docstring)."""
    evaluated = [name for name in path if name in results]
    for name in evaluated:
        if results[name]["audit"]["pass"]:
            return {"chosen": name, "criterion_met": True, "reason": "first level on the path that passes the feature audit"}

    def key(name: str) -> tuple:
        a = results[name]["audit"]
        return (a["scam"]["fingerprint"] + a["safe"]["fingerprint"], -a["scam"]["signal_share"], evaluated.index(name))

    best = min(evaluated, key=key)
    return {"chosen": best, "criterion_met": False,
            "reason": "no level passes the audit; chose the one with the fewest fingerprints (then highest scam-signal share)"}


def run_ladder(levels: tuple[str, ...], out_path: Path = RESULTS_PATH, say=print) -> dict:
    """Build and score each level in ``levels``; write and return the results."""
    reference = p35.load_reference()
    actions = p35.load_audit_actions()
    india, india_report = p35.build_india_rows(reference)
    say(f"India rows: {india_report}")
    results: dict[str, dict] = {}
    for name in levels:
        data = p35.build_level(name, reference, india, actions)
        results[name] = evaluate_level(data, say=say)
        results[name]["build_report"] = data.report
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps({"india": india_report, "levels": results}, indent=1, default=str), encoding="utf-8")
    return results


def main(argv: list[str] | None = None) -> int:
    """CLI: ``python -m src.training.ladder [L0 L1 ...]`` (default: every level)."""
    import argparse

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("levels", nargs="*", default=list(p35.LEVELS))
    parser.add_argument("--out", type=Path, default=RESULTS_PATH)
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.WARNING)
    results = run_ladder(tuple(args.levels), args.out)
    if any(name in results for name in p35.LADDER_ORDER):
        print(json.dumps(choose_level(results), indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
