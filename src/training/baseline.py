"""Phase 3 baselines: TF-IDF + Logistic Regression and TF-IDF + Linear SVM.

Protocol (the order matters, and each rule is enforced by a test):

1. **Train** on the train split only. Features are fitted on train text only.
2. **Tune** on the *real* validation rows only (synthetic validation rows are scored
   separately as "diagnostic only"). The grid covers the feature set, ``C`` and class
   weighting; the decision threshold is tuned for scam-class F1 on the same rows.
   The tuning functions are never given the test split.
3. **Test once per model** on the real test set, with the frozen configuration.
4. **Confound checks**: per-source metrics, leave-one-source-out (LOSO) evaluation, and
   one mitigation experiment (source x class balanced sample weights).
5. If ``data/processed/real_indian_test.parquet`` exists, score it once as well.

Only the masked ``text`` column is ever read (never ``text_raw``). Every run, parameter
and metric is logged to a local MLflow SQLite store; test metrics are logged only on the
final runs, never on tuning trials.

Usage::

    python -m src.training.baseline                  # full grid, writes results.md tables
    python -m src.training.baseline --fast           # tiny grid for a smoke test
    mlflow ui --backend-store-uri sqlite:///mlflow.db
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import time
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Callable, Iterable

import joblib
import mlflow
import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import FeatureUnion
from sklearn.svm import LinearSVC

from src.training import metrics as M

logger = logging.getLogger(__name__)

DEFAULT_PROCESSED_DIR = Path("data/processed")
DEFAULT_MODEL_DIR = Path("models/baseline")
DEFAULT_FIGURE_DIR = Path("docs/figures")
DEFAULT_TRACKING_URI = "sqlite:///mlflow.db"
DEFAULT_ARTIFACT_ROOT = Path("mlruns")
EXPERIMENT_NAME = "baseline"
RESULTS_JSON = "baseline_results.json"
HOLDOUT_FILE = "real_indian_test.parquet"

MAX_CHARS = 2_000               # only the start of each message is used
SEED = 42
MODELS = ("logreg", "svm")
MODEL_TITLES = {"logreg": "TF-IDF + Logistic Regression", "svm": "TF-IDF + Linear SVM"}
FIGURE_STEM = {"logreg": "lr", "svm": "svm"}
FEATURE_KINDS = ("word", "char", "word+char")
# The first run's logreg optimum sat on the grid edge (C=100, validation F1 still rising),
# so the grid was extended to 1000 and the whole protocol re-run. SVM peaked at C=1 (interior).
C_GRIDS: dict[str, tuple[float, ...]] = {"logreg": (0.1, 1.0, 10.0, 100.0, 1000.0), "svm": (0.01, 0.1, 1.0, 10.0)}
CLASS_WEIGHTS: tuple[str | None, ...] = (None, "balanced")
SYNTHETIC_SOURCE = "synthetic_llm"
MARKER_START, MARKER_END = "<!-- baseline:start -->", "<!-- baseline:end -->"


# --------------------------------------------------------------------------- #
# Data
# --------------------------------------------------------------------------- #
@dataclass
class Splits:
    """The three splits produced by ``preprocess.py``."""

    train: pd.DataFrame
    val: pd.DataFrame
    test: pd.DataFrame

    @property
    def val_real(self) -> pd.DataFrame:
        """Validation rows that are real data: the only rows used to select models."""
        return self.val[~self.val["is_synthetic"]]

    @property
    def val_synthetic(self) -> pd.DataFrame:
        """Synthetic validation rows: reported as diagnostic only."""
        return self.val[self.val["is_synthetic"]]


def load_splits(processed_dir: Path = DEFAULT_PROCESSED_DIR) -> Splits:
    """Load train/val/test and check the invariants the protocol relies on.

    Raises:
        FileNotFoundError: If the parquet files are missing (run ``preprocess`` first).
        ValueError: If the test set contains synthetic rows.
    """
    processed_dir = Path(processed_dir)
    parts = {n: pd.read_parquet(processed_dir / f"{n}.parquet") for n in ("train", "val", "test")}
    if parts["test"]["is_synthetic"].any():
        raise ValueError("the test set must be 100% real data")
    return Splits(**parts)


def texts_of(df: pd.DataFrame) -> list[str]:
    """Model input: the masked ``text`` column truncated to :data:`MAX_CHARS`.

    This is the *only* place text is read, so ``text_raw`` can never leak into a model.
    """
    return df["text"].astype(str).str.slice(0, MAX_CHARS).tolist()


# --------------------------------------------------------------------------- #
# Features and classifiers
# --------------------------------------------------------------------------- #
def build_vectorizer(kind: str):
    """TF-IDF feature extractor for ``kind`` in :data:`FEATURE_KINDS` (unfitted).

    * ``word``: word 1-2-grams (captures phrases such as "claim your").
    * ``char``: character 2-5-grams inside word boundaries (robust to the spelling
      variation of romanized Hinglish and to obfuscated words).
    * ``word+char``: both, concatenated.
    """

    def word() -> TfidfVectorizer:
        return TfidfVectorizer(analyzer="word", ngram_range=(1, 2), min_df=2, sublinear_tf=True, dtype=np.float32)

    def char() -> TfidfVectorizer:
        return TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 5), min_df=3, sublinear_tf=True, dtype=np.float32)

    if kind == "word":
        return word()
    if kind == "char":
        return char()
    if kind == "word+char":
        return FeatureUnion([("word", word()), ("char", char())])
    raise ValueError(f"unknown feature kind: {kind!r}")


@dataclass(frozen=True)
class Config:
    """One point of the hyperparameter grid."""

    feature_kind: str
    C: float
    class_weight: str | None

    def as_params(self) -> dict[str, str | float]:
        return {"features": self.feature_kind, "C": self.C, "class_weight": str(self.class_weight)}

    def short(self) -> str:
        return f"{self.feature_kind}, C={self.C:g}, class_weight={self.class_weight}"


def make_classifier(model: str, cfg: Config, seed: int = SEED):
    """Linear classifier for ``model`` (``logreg`` or ``svm``) with ``cfg``'s C and class weight."""
    if model == "logreg":
        return LogisticRegression(solver="liblinear", C=cfg.C, class_weight=cfg.class_weight,
                                  random_state=seed, max_iter=1000)
    if model == "svm":
        return LinearSVC(C=cfg.C, class_weight=cfg.class_weight, random_state=seed, max_iter=5000)
    raise ValueError(f"unknown model: {model!r}")


def source_class_weights(df: pd.DataFrame) -> np.ndarray:
    """Sample weights giving every (source, label) cell the same total weight.

    This is the confound mitigation: no source can dominate a class, and within a
    source the classes are balanced, so the source itself carries less information
    about the label. Weights are scaled to average 1.
    """
    cell = df["source"].astype(str) + "|" + df["label"].astype(str)
    weights = 1.0 / cell.map(cell.value_counts()).to_numpy(dtype=float)
    return weights * len(weights) / weights.sum()


@dataclass
class FittedModel:
    """A vectorizer + classifier pair with a decision threshold."""

    model: str
    cfg: Config
    vectorizer: object
    clf: object
    threshold: float = M.DEFAULT_THRESHOLD

    def scores(self, df: pd.DataFrame) -> np.ndarray:
        """Real-valued scam scores (``decision_function``) for the rows of ``df``."""
        return np.asarray(self.clf.decision_function(self.vectorizer.transform(texts_of(df))))


def fit_model(
    model: str, cfg: Config, train: pd.DataFrame, seed: int = SEED, sample_weight: np.ndarray | None = None
) -> FittedModel:
    """Fit features and classifier on ``train`` only."""
    vectorizer = build_vectorizer(cfg.feature_kind)
    x_train = vectorizer.fit_transform(texts_of(train))
    clf = make_classifier(model, cfg, seed)
    clf.fit(x_train, M.labels_to_binary(train["label"]), sample_weight=sample_weight)
    return FittedModel(model, cfg, vectorizer, clf)


# --------------------------------------------------------------------------- #
# Tuning (sees train and real validation rows only)
# --------------------------------------------------------------------------- #
@dataclass
class Trial:
    """Result of one grid point on the real validation rows."""

    model: str
    cfg: Config
    threshold: float
    val: dict[str, float]            # metrics at the tuned threshold
    val_default: dict[str, float]    # metrics at the default threshold
    seconds: float

    def sort_key(self) -> tuple:
        """Higher F1, then higher PR-AUC, then smaller C, then feature order."""
        f1 = self.val["f1"] if np.isfinite(self.val["f1"]) else -1.0
        pr = self.val["pr_auc"] if np.isfinite(self.val["pr_auc"]) else -1.0
        return (-f1, -pr, self.cfg.C, FEATURE_KINDS.index(self.cfg.feature_kind))


def select_best(trials: Iterable[Trial]) -> Trial:
    """Best trial by :meth:`Trial.sort_key` (deterministic tie-breaking)."""
    return sorted(trials, key=Trial.sort_key)[0]


def tune(
    model: str,
    train: pd.DataFrame,
    val_real: pd.DataFrame,
    feature_kinds: Iterable[str] = FEATURE_KINDS,
    c_grid: Iterable[float] | None = None,
    class_weights: Iterable[str | None] = CLASS_WEIGHTS,
    seed: int = SEED,
    on_trial: Callable[[Trial], None] | None = None,
) -> list[Trial]:
    """Grid-search ``model`` using **only** ``train`` and ``val_real``.

    The test split is deliberately not a parameter, so it cannot influence selection.
    Features are fitted once per feature kind (on train text only) and shared by all
    ``C`` / class-weight combinations.

    Returns:
        All trials, best first.
    """
    c_grid = tuple(c_grid if c_grid is not None else C_GRIDS[model])
    y_train, y_val = M.labels_to_binary(train["label"]), M.labels_to_binary(val_real["label"])
    val_texts, train_texts = texts_of(val_real), texts_of(train)
    trials: list[Trial] = []
    for kind in feature_kinds:
        vectorizer = build_vectorizer(kind)
        x_train = vectorizer.fit_transform(train_texts)          # fitted on train only
        x_val = vectorizer.transform(val_texts)
        for c in c_grid:
            for cw in class_weights:
                cfg = Config(kind, float(c), cw)
                t0 = time.perf_counter()
                clf = make_classifier(model, cfg, seed).fit(x_train, y_train)
                scores = clf.decision_function(x_val)
                threshold, _ = M.best_f1_threshold(y_val, scores)
                trial = Trial(model, cfg, threshold, M.binary_metrics(y_val, scores, threshold),
                              M.binary_metrics(y_val, scores, M.DEFAULT_THRESHOLD), time.perf_counter() - t0)
                trials.append(trial)
                if on_trial:
                    on_trial(trial)
    return sorted(trials, key=Trial.sort_key)


def tune_threshold(fitted: FittedModel, val_real: pd.DataFrame) -> FittedModel:
    """Set ``fitted.threshold`` to the F1-optimal value on the real validation rows."""
    threshold, _ = M.best_f1_threshold(M.labels_to_binary(val_real["label"]), fitted.scores(val_real))
    return replace(fitted, threshold=threshold)


# --------------------------------------------------------------------------- #
# Evaluation
# --------------------------------------------------------------------------- #
def evaluate(fitted: FittedModel, df: pd.DataFrame) -> dict[str, dict]:
    """Overall metrics at the tuned and default thresholds for the rows of ``df``."""
    scores, y = fitted.scores(df), M.labels_to_binary(df["label"])
    return {
        "tuned": M.binary_metrics(y, scores, fitted.threshold),
        "default": M.binary_metrics(y, scores, M.DEFAULT_THRESHOLD),
    }


def breakdowns(fitted: FittedModel, df: pd.DataFrame, columns: Iterable[str]) -> dict[str, pd.DataFrame]:
    """Per-group tables (at the tuned threshold) for each column in ``columns``."""
    scores = fitted.scores(df)
    return {c: M.group_metrics(df, scores, c, fitted.threshold) for c in columns if c in df.columns}


def top_features(fitted: FittedModel, n: int = 20) -> pd.DataFrame:
    """Highest-weight features for each class (largest positive = scam, negative = safe)."""
    names = np.asarray(fitted.vectorizer.get_feature_names_out())
    coef = np.asarray(fitted.clf.coef_).ravel()
    order = np.argsort(coef)
    rows = [("scam", names[i], float(coef[i])) for i in order[::-1][:n]]
    rows += [("safe", names[i], float(coef[i])) for i in order[:n]]
    return pd.DataFrame(rows, columns=["class", "feature", "weight"])


def loso_training_frame(train: pd.DataFrame, held_out: str) -> pd.DataFrame:
    """Training rows from every source except ``held_out``."""
    out = train[train["source"] != held_out]
    if out.empty or out["label"].nunique() < 2:
        raise ValueError(f"nothing left to train on after holding out {held_out!r}")
    return out


def loso_eval_frame(splits: Splits, held_out: str) -> pd.DataFrame:
    """Rows a model trained without ``held_out`` is scored on.

    Real sources use their *test* rows; the synthetic source has no test rows (the test
    set is 100% real), so its synthetic validation rows are used (diagnostic only).
    """
    frame = splits.val_synthetic if held_out == SYNTHETIC_SOURCE else splits.test
    return frame[frame["source"] == held_out]


# --------------------------------------------------------------------------- #
# MLflow helpers
# --------------------------------------------------------------------------- #
_METRIC_KEYS = ("precision", "recall", "f1", "accuracy", "fpr", "roc_auc", "pr_auc",
                "tp", "fp", "fn", "tn", "threshold", "n")


def init_mlflow(tracking_uri: str = DEFAULT_TRACKING_URI, artifact_root: Path = DEFAULT_ARTIFACT_ROOT) -> None:
    """Point MLflow at the local SQLite store and create the experiment if needed.

    (The plain-file backend is refused by MLflow 3.x, so SQLite is used; both the
    database and ``mlruns/`` artifacts are gitignored.)
    """
    mlflow.set_tracking_uri(tracking_uri)
    if mlflow.get_experiment_by_name(EXPERIMENT_NAME) is None:
        mlflow.create_experiment(EXPERIMENT_NAME, artifact_location=Path(artifact_root).resolve().as_uri())
    mlflow.set_experiment(EXPERIMENT_NAME)


def log_metrics(prefix: str, metrics: dict[str, float]) -> None:
    """Log the finite metrics in ``metrics`` as ``<prefix>_<name>``."""
    mlflow.log_metrics({f"{prefix}_{k}": float(v) for k, v in metrics.items()
                        if k in _METRIC_KEYS and np.isfinite(v)})


def _safe_name(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", text).strip("_")


def _log_table(table: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    table.to_csv(path)
    mlflow.log_artifact(str(path))


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #
def _table_records(table: pd.DataFrame) -> dict:
    """DataFrame -> JSON-friendly ``{group: {metric: value}}`` (NaN -> None)."""
    return json.loads(table.replace({np.nan: None}).to_json(orient="index"))


def _metric_summary(m: dict[str, float]) -> dict[str, float | None]:
    return {k: (None if (isinstance(v, float) and not np.isfinite(v)) else v) for k, v in m.items()}


def make_loso_figures(results: dict, figure_dir: Path) -> dict[str, str]:
    """Draw one leave-one-source-out ROC-AUC chart per model from a results dict.

    Works on the saved JSON too, so charts can be redrawn without re-running the models.
    The synthetic source is labelled "(diagnostic)" on the axis.
    """
    frame = pd.DataFrame(results.get("loso", []))
    paths: dict[str, str] = {}
    if frame.empty:
        return paths
    frame["source"] = [f"{h} (diagnostic)" if d else h for h, d in zip(frame["held_out"], frame["diagnostic_only"])]
    for model in MODELS:
        part = frame[frame["model"] == model]
        if part.empty:
            continue
        path = M.plot_loso_comparison(
            part, Path(figure_dir) / f"loso_roc_auc_{FIGURE_STEM[model]}.png", "roc_auc",
            f"{MODEL_TITLES[model]}: leave-one-source-out",
            "ROC-AUC on the held-out source; dashed line = chance (0.5). Synthetic rows are diagnostic only")
        paths[model] = str(path)
        if model in results.get("models", {}):
            results["models"][model]["loso_figure"] = str(path)
    return paths


def run_baseline(
    processed_dir: Path = DEFAULT_PROCESSED_DIR,
    model_dir: Path = DEFAULT_MODEL_DIR,
    figure_dir: Path = DEFAULT_FIGURE_DIR,
    tracking_uri: str = DEFAULT_TRACKING_URI,
    artifact_root: Path = DEFAULT_ARTIFACT_ROOT,
    seed: int = SEED,
    feature_kinds: Iterable[str] = FEATURE_KINDS,
    c_grids: dict[str, Iterable[float]] | None = None,
    class_weights: Iterable[str | None] = CLASS_WEIGHTS,
    run_loso: bool = True,
    say: Callable[[str], None] = print,
) -> dict:
    """Run the full Phase 3 protocol and return a JSON-serialisable results dict.

    Writes confusion-matrix and LOSO charts to ``figure_dir``, models and per-group CSVs
    to ``model_dir``, and logs everything to MLflow.
    """
    processed_dir, model_dir, figure_dir = Path(processed_dir), Path(model_dir), Path(figure_dir)
    c_grids = {m: tuple((c_grids or {}).get(m, C_GRIDS[m])) for m in MODELS}
    feature_kinds, class_weights = tuple(feature_kinds), tuple(class_weights)
    splits = load_splits(processed_dir)
    init_mlflow(tracking_uri, artifact_root)
    report_dir = model_dir / "reports"
    holdout_path = processed_dir / HOLDOUT_FILE
    holdout = pd.read_parquet(holdout_path) if holdout_path.exists() else None

    results: dict = {
        "seed": seed, "max_chars": MAX_CHARS, "feature_kinds": list(feature_kinds),
        "sizes": {"train": len(splits.train), "val_real": len(splits.val_real),
                  "val_synthetic": len(splits.val_synthetic), "test": len(splits.test),
                  "real_indian_test": None if holdout is None else len(holdout)},
        "models": {}, "variants": {}, "loso": [],
    }
    finals: dict[str, FittedModel] = {}

    # ---- 1. tune + final evaluation for each model family ------------------------------
    for model in MODELS:
        title = MODEL_TITLES[model]
        say(f"\n=== {title}: tuning on {len(splits.val_real):,} real validation rows ===")
        with mlflow.start_run(run_name=f"{model}-tune") as parent:
            mlflow.set_tags({"phase": "3", "model": model, "stage": "tune+final"})
            mlflow.log_params({"seed": seed, "max_chars": MAX_CHARS, "train_rows": len(splits.train),
                               "val_real_rows": len(splits.val_real), "grid_c": list(c_grids[model]),
                               "grid_features": list(feature_kinds), "grid_class_weight": [str(c) for c in class_weights]})

            def log_trial(t: Trial, model: str = model) -> None:
                # Validation-only metrics: test metrics are never logged on tuning trials.
                with mlflow.start_run(run_name=t.cfg.short(), nested=True):
                    mlflow.set_tags({"stage": "trial", "model": model})
                    mlflow.log_params(t.cfg.as_params())
                    log_metrics("val_real", t.val)
                    log_metrics("val_real_default_thr", t.val_default)
                    mlflow.log_metric("fit_seconds", t.seconds)
                say(f"  {t.cfg.short():<38} val F1={t.val['f1']:.4f}  PR-AUC={t.val['pr_auc']:.4f}  ({t.seconds:.1f}s)")

            trials = tune(model, splits.train, splits.val_real, feature_kinds, c_grids[model], class_weights,
                          seed, on_trial=log_trial)
            best = trials[0]
            say(f"  -> best: {best.cfg.short()}  val F1={best.val['f1']:.4f}  threshold={best.threshold:.3f}")

            final = fit_model(model, best.cfg, splits.train, seed)
            final = replace(final, threshold=best.threshold)
            finals[model] = final
            mlflow.log_params({f"best_{k}": v for k, v in best.cfg.as_params().items()})
            mlflow.log_param("best_threshold", round(best.threshold, 6))
            log_metrics("val_real", best.val)

            tuning_table = pd.DataFrame([{**t.cfg.as_params(), "threshold": t.threshold,
                                          "val_f1": t.val["f1"], "val_precision": t.val["precision"],
                                          "val_recall": t.val["recall"], "val_pr_auc": t.val["pr_auc"],
                                          "val_roc_auc": t.val["roc_auc"], "val_f1_default_thr": t.val_default["f1"],
                                          "seconds": t.seconds} for t in trials])
            _log_table(tuning_table.rename_axis("rank"), report_dir / f"{model}_tuning.csv")

            # Test set: scored once for this model, with everything frozen.
            test_eval = evaluate(final, splits.test)
            log_metrics("test", test_eval["tuned"])
            log_metrics("test_default_thr", test_eval["default"])
            test_by = breakdowns(final, splits.test, ("source", "language", "scam_type"))
            val_syn_eval = evaluate(final, splits.val_synthetic)
            log_metrics("val_synthetic_diag", val_syn_eval["tuned"])
            syn_by = breakdowns(final, splits.val_synthetic, ("language", "scam_type", "source"))
            for name, table in {**{f"test_by_{k}": v for k, v in test_by.items()},
                                **{f"val_synthetic_by_{k}": v for k, v in syn_by.items()}}.items():
                _log_table(table, report_dir / f"{model}_{name}.csv")
            features = top_features(final)
            _log_table(features.set_index("class"), report_dir / f"{model}_top_features.csv")

            cm = np.array([[test_eval["tuned"]["tn"], test_eval["tuned"]["fp"]],
                           [test_eval["tuned"]["fn"], test_eval["tuned"]["tp"]]])
            fig_path = M.plot_confusion_matrix(
                cm, figure_dir / f"confusion_{FIGURE_STEM[model]}_test.png",
                f"{title}: real test set",
                f"{len(splits.test):,} messages, threshold {final.threshold:.3f}, {best.cfg.short()}")
            mlflow.log_artifact(str(fig_path))

            holdout_res = None
            if holdout is not None:
                h_eval = evaluate(final, holdout)
                log_metrics("real_indian", h_eval["tuned"])
                h_by = breakdowns(final, holdout, ("language", "scam_type", "channel"))
                for k, v in h_by.items():
                    _log_table(v, report_dir / f"{model}_real_indian_by_{k}.csv")
                holdout_res = {"overall": {k: _metric_summary(v) for k, v in h_eval.items()},
                               "by": {k: _table_records(v) for k, v in h_by.items()}}

            model_dir.mkdir(parents=True, exist_ok=True)
            joblib.dump({"vectorizer": final.vectorizer, "clf": final.clf, "config": best.cfg.as_params(),
                         "threshold": final.threshold, "max_chars": MAX_CHARS}, model_dir / f"{model}.joblib")
            mlflow.log_dict({"config": best.cfg.as_params(), "threshold": final.threshold, "seed": seed},
                            f"{model}_config.json")

            results["models"][model] = {
                "title": title, "run_id": parent.info.run_id, "best": best.cfg.as_params(),
                "threshold": best.threshold, "n_trials": len(trials),
                "top_trials": [{**t.cfg.as_params(), "val_f1": t.val["f1"], "val_pr_auc": t.val["pr_auc"]}
                               for t in trials[:5]],
                "val_real": _metric_summary(best.val),
                "val_real_default": _metric_summary(best.val_default),
                "val_synthetic_diag": {k: _metric_summary(v) for k, v in val_syn_eval.items()},
                "test": {k: _metric_summary(v) for k, v in test_eval.items()},
                "test_by": {k: _table_records(v) for k, v in test_by.items()},
                "val_synthetic_by": {k: _table_records(v) for k, v in syn_by.items()},
                "top_features": {c: features[features["class"] == c]["feature"].tolist()[:12]
                                 for c in ("scam", "safe")},
                "real_indian": holdout_res,
            }
            say(f"  test: P={test_eval['tuned']['precision']:.4f} R={test_eval['tuned']['recall']:.4f} "
                f"F1={test_eval['tuned']['f1']:.4f} ROC-AUC={test_eval['tuned']['roc_auc']:.4f}")

    # ---- 2. mitigation experiment: source x class balanced sample weights -------------------
    say("\n=== Mitigation experiment: source x class balanced sample weights ===")
    weights_train = source_class_weights(splits.train)
    balanced: dict[str, FittedModel] = {}
    for model in MODELS:
        best_cfg = finals[model].cfg
        cfg = replace(best_cfg, class_weight=None)          # the sample weights do the balancing
        with mlflow.start_run(run_name=f"{model}-source-balanced"):
            mlflow.set_tags({"phase": "3", "model": model, "stage": "mitigation"})
            mlflow.log_params({**cfg.as_params(), "sample_weight": "source_x_class_balanced", "seed": seed})
            fitted = tune_threshold(fit_model(model, cfg, splits.train, seed, weights_train), splits.val_real)
            balanced[model] = fitted
            val_eval = evaluate(fitted, splits.val_real)
            test_eval = evaluate(fitted, splits.test)
            log_metrics("val_real", val_eval["tuned"])
            log_metrics("test", test_eval["tuned"])
            log_metrics("test_default_thr", test_eval["default"])
            by_source = breakdowns(fitted, splits.test, ("source",))["source"]
            _log_table(by_source, report_dir / f"{model}_balanced_test_by_source.csv")
            results["variants"][model] = {
                "config": cfg.as_params(), "threshold": fitted.threshold,
                "val_real": _metric_summary(val_eval["tuned"]),
                "test": {k: _metric_summary(v) for k, v in test_eval.items()},
                "test_by_source": _table_records(by_source),
            }
            say(f"  {MODEL_TITLES[model]} (balanced): val F1={val_eval['tuned']['f1']:.4f}  "
                f"test F1={test_eval['tuned']['f1']:.4f}  ROC-AUC={test_eval['tuned']['roc_auc']:.4f}")

    # ---- 3. leave-one-source-out -----------------------------------------------------------
    if run_loso:
        say("\n=== Leave-one-source-out (hyperparameters frozen from tuning) ===")
        for held_out in sorted(splits.train["source"].unique()):
            eval_df = loso_eval_frame(splits, held_out)
            if eval_df.empty or eval_df["label"].nunique() < 2:
                say(f"  skipping {held_out}: no evaluable rows")
                continue
            sub = loso_training_frame(splits.train, held_out)
            y_eval = M.labels_to_binary(eval_df["label"])
            for model in MODELS:
                cfg = finals[model].cfg
                with mlflow.start_run(run_name=f"{model}-loso-{_safe_name(held_out)}"):
                    mlflow.set_tags({"phase": "3", "model": model, "stage": "loso", "held_out": held_out})
                    mlflow.log_params({**cfg.as_params(), "held_out_source": held_out, "train_rows": len(sub)})
                    standard = fit_model(model, cfg, sub, seed)
                    mitig = fit_model(model, replace(cfg, class_weight=None), sub, seed, source_class_weights(sub))
                    rows = {
                        "in-distribution": M.binary_metrics(y_eval, finals[model].scores(eval_df), finals[model].threshold),
                        "leave-one-source-out": M.binary_metrics(y_eval, standard.scores(eval_df), finals[model].threshold),
                        "source-balanced (LOSO)": M.binary_metrics(y_eval, mitig.scores(eval_df), balanced[model].threshold),
                    }
                    for variant, m in rows.items():
                        log_metrics(_safe_name(variant), m)
                        results["loso"].append({"model": model, "held_out": held_out, "variant": variant,
                                                "eval_rows": int(len(eval_df)),
                                                "diagnostic_only": held_out == SYNTHETIC_SOURCE,
                                                **{k: (None if not np.isfinite(v) else v) for k, v in m.items()
                                                   if k in _METRIC_KEYS}})
                    say(f"  {MODEL_TITLES[model]:<32} held out {held_out:<20} ROC-AUC "
                        + " | ".join(f"{v.split(' ')[0]} {m['roc_auc']:.3f}" for v, m in rows.items()))

        make_loso_figures(results, figure_dir)

    processed_dir.mkdir(parents=True, exist_ok=True)
    (processed_dir / RESULTS_JSON).write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")
    return results


# --------------------------------------------------------------------------- #
# results.md
# --------------------------------------------------------------------------- #
def _f(v: float | None, digits: int = 4) -> str:
    return "n/a" if v is None or (isinstance(v, float) and not np.isfinite(v)) else f"{v:.{digits}f}"


def _md_table(header: list[str], rows: list[list[str]]) -> str:
    lines = ["| " + " | ".join(header) + " |", "|" + "|".join(["---"] * len(header)) + "|"]
    lines += ["| " + " | ".join(r) + " |" for r in rows]
    return "\n".join(lines)


def format_results_markdown(res: dict) -> str:
    """Markdown tables (comparison, per-source, LOSO, diagnostics) built from a results dict.

    Every number comes from ``res``; nothing is typed by hand.
    """
    sizes = res["sizes"]
    out = [f"_Generated by `python -m src.training.baseline` (seed {res['seed']}, first {res['max_chars']:,} "
           f"characters of the masked text). Selection used {sizes['val_real']:,} real validation rows; "
           f"the {sizes['test']:,}-row real test set was scored once per model._", ""]

    # comparison table
    rows = []
    for model in MODELS:
        m = res["models"][model]
        t = m["test"]["tuned"]
        rows.append([m["title"], f"{m['best']['features']}, C={m['best']['C']:g}, cw={m['best']['class_weight']}",
                     _f(m["val_real"]["f1"]), _f(t["precision"]), _f(t["recall"]), _f(t["f1"]),
                     _f(t["roc_auc"]), _f(t["pr_auc"]), f"{t['fp']:,} / {t['fn']:,}",
                     _f(m["test"]["default"]["f1"])])
    for model in MODELS:
        v = res["variants"][model]
        t = v["test"]["tuned"]
        rows.append([f"{MODEL_TITLES[model]} + source-balanced weights (experiment)",
                     f"{v['config']['features']}, C={v['config']['C']:g}, sample weights",
                     _f(v["val_real"]["f1"]), _f(t["precision"]), _f(t["recall"]), _f(t["f1"]),
                     _f(t["roc_auc"]), _f(t["pr_auc"]), f"{t['fp']:,} / {t['fn']:,}", _f(v["test"]["default"]["f1"])])
    out += ["#### Comparison on the real test set (scam = positive class)", "",
            _md_table(["Model", "Selected configuration", "Val F1 (real)", "Test precision", "Test recall",
                       "Test F1", "Test ROC-AUC", "Test PR-AUC", "FP / FN", "Test F1 @ default thr"], rows), ""]

    # confusion counts
    conf_rows = []
    for model in MODELS:
        t = res["models"][model]["test"]["tuned"]
        conf_rows.append([res["models"][model]["title"], f"{t['tn']:,}", f"{t['fp']:,}", f"{t['fn']:,}", f"{t['tp']:,}",
                          _f(res["models"][model]["threshold"], 3)])
    out += ["#### Confusion matrices (test set)", "",
            _md_table(["Model", "TN (safe->safe)", "FP (safe->scam)", "FN (scam->safe)", "TP (scam->scam)", "Threshold"],
                      conf_rows), ""]

    # per-source
    src_rows = []
    for model in MODELS:
        by = res["models"][model]["test_by"].get("source", {})
        for src, g in by.items():
            src_rows.append([res["models"][model]["title"], src, f"{g['n']:,}", f"{g['n_scam']:,}", _f(g["precision"]),
                             _f(g["recall"]), _f(g["f1"]), _f(g["fpr"]), _f(g["roc_auc"])])
    out += ["#### Test set by source", "",
            _md_table(["Model", "Source", "Rows", "Scam rows", "Precision", "Recall", "F1", "False-positive rate", "ROC-AUC"],
                      src_rows), ""]

    # per language / scam type on test (degenerate) + diagnostics on synthetic val
    for key, title in (("language", "language"), ("scam_type", "scam type")):
        rows_k = []
        for model in MODELS:
            for grp, g in res["models"][model]["test_by"].get(key, {}).items():
                rows_k.append([res["models"][model]["title"], grp, f"{g['n']:,}", f"{g['n_scam']:,}",
                               _f(g["precision"]), _f(g["recall"]), _f(g["f1"]), _f(g["fpr"])])
        out += [f"#### Test set by {title} (real data; nearly degenerate, see note)", "",
                _md_table(["Model", title.capitalize(), "Rows", "Scam rows", "Precision", "Recall", "F1", "FPR"], rows_k), ""]

    out += ["#### Diagnostic only: synthetic validation rows (never a real-data result)", ""]
    for key, title in (("language", "language"), ("scam_type", "scam type")):
        rows_k = []
        for model in MODELS:
            for grp, g in res["models"][model]["val_synthetic_by"].get(key, {}).items():
                rows_k.append([res["models"][model]["title"], grp, f"{g['n']:,}", f"{g['n_scam']:,}",
                               _f(g["precision"]), _f(g["recall"]), _f(g["f1"]), _f(g["fpr"])])
        out += [f"By {title}:", "", _md_table(["Model", title.capitalize(), "Rows", "Scam rows", "Precision", "Recall",
                                                "F1", "FPR"], rows_k), ""]

    # LOSO
    if res["loso"]:
        rows_l = []
        for r in res["loso"]:
            rows_l.append([MODEL_TITLES[r["model"]], r["held_out"] + (" (diagnostic)" if r["diagnostic_only"] else ""),
                           r["variant"], f"{r['eval_rows']:,}", _f(r["roc_auc"]), _f(r["pr_auc"]), _f(r["f1"]),
                           _f(r["precision"]), _f(r["recall"])])
        out += ["#### Leave-one-source-out (train without the source, score on it; hyperparameters frozen)", "",
                "F1 / precision / recall use the threshold tuned in-distribution (source-balanced rows use their own "
                "tuned threshold). ROC-AUC and PR-AUC do not depend on a threshold.", "",
                _md_table(["Model", "Held-out source", "Variant", "Rows", "ROC-AUC", "PR-AUC", "F1", "Precision",
                           "Recall"], rows_l), ""]

    # top features
    feat_rows = [[res["models"][m]["title"], ", ".join(res["models"][m]["top_features"]["scam"]),
                  ", ".join(res["models"][m]["top_features"]["safe"])] for m in MODELS]
    out += ["#### Highest-weight features", "",
            _md_table(["Model", "Scam", "Safe"], feat_rows), ""]

    # top trials
    for model in MODELS:
        m = res["models"][model]
        out += [f"Top tuning trials, {m['title']} ({m['n_trials']} trials on real validation rows):", "",
                _md_table(["Features", "C", "Class weight", "Val F1", "Val PR-AUC"],
                          [[t["features"], f"{t['C']:g}", t["class_weight"], _f(t["val_f1"]), _f(t["val_pr_auc"])]
                           for t in m["top_trials"]]), ""]

    if sizes.get("real_indian_test"):
        rows_h = []
        for model in MODELS:
            h = res["models"][model]["real_indian"]
            t = h["overall"]["tuned"]
            rows_h.append([res["models"][model]["title"], f"{t['n']:,}", _f(t["precision"]), _f(t["recall"]),
                           _f(t["f1"]), _f(t["roc_auc"])])
        out += ["#### Hand-collected real Indian test set (evaluation-only)", "",
                _md_table(["Model", "Rows", "Precision", "Recall", "F1", "ROC-AUC"], rows_h), ""]
    else:
        out += ["_Hand-collected real Indian test set: not built yet, so no Hinglish result exists._", ""]
    return "\n".join(out)


def update_results_md(path: Path, markdown: str) -> None:
    """Replace the block between the baseline markers in ``path`` (append it if absent)."""
    path = Path(path)
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    block = f"{MARKER_START}\n{markdown.strip()}\n{MARKER_END}"
    if MARKER_START in text and MARKER_END in text:
        head, rest = text.split(MARKER_START, 1)
        _, tail = rest.split(MARKER_END, 1)
        text = head + block + tail
    else:
        text = text.rstrip() + "\n\n" + block + "\n"
    path.write_text(text, encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--processed-dir", type=Path, default=DEFAULT_PROCESSED_DIR)
    parser.add_argument("--model-dir", type=Path, default=DEFAULT_MODEL_DIR)
    parser.add_argument("--figure-dir", type=Path, default=DEFAULT_FIGURE_DIR)
    parser.add_argument("--tracking-uri", default=DEFAULT_TRACKING_URI)
    parser.add_argument("--seed", type=int, default=SEED)
    parser.add_argument("--fast", action="store_true", help="word features, two C values: a quick smoke test")
    parser.add_argument("--no-loso", action="store_true", help="skip the leave-one-source-out evaluation")
    parser.add_argument("--artifact-root", type=Path, default=DEFAULT_ARTIFACT_ROOT)
    parser.add_argument("--replot", action="store_true",
                        help="only redraw the LOSO charts from the saved results JSON (no training)")
    parser.add_argument("--update-results", type=Path, default=None, metavar="RESULTS_MD",
                        help="rewrite the baseline block of this markdown file (e.g. results.md)")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")

    if args.replot:
        saved = json.loads((args.processed_dir / RESULTS_JSON).read_text(encoding="utf-8"))
        for path in make_loso_figures(saved, args.figure_dir).values():
            print("wrote", path)
        return 0

    kwargs: dict = {}
    if args.fast:
        kwargs = {"feature_kinds": ("word",), "c_grids": {"logreg": (1.0, 10.0), "svm": (0.1, 1.0)}}
    result = run_baseline(args.processed_dir, args.model_dir, args.figure_dir, args.tracking_uri,
                          args.artifact_root, seed=args.seed, run_loso=not args.no_loso, **kwargs)
    if args.update_results:
        update_results_md(args.update_results, format_results_markdown(result))
        print(f"\nUpdated {args.update_results}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
