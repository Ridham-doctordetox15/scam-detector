"""Tests for src.training.baseline: protocol rules, tuning, LOSO, MLflow logging, results.md."""
import inspect
import json
from dataclasses import replace
from pathlib import Path

import mlflow
import numpy as np
import pandas as pd
import pytest

from src.training import baseline as B
from src.training import metrics as M

SCAM_WORDS = "prize claim urgent verify blocked winner lottery fee refund kyc suspended".split()
SAFE_WORDS = "meeting lunch report agenda tomorrow thanks schedule invoice dinner weekend notes".split()
FILLER = {
    "uci_sms_spam": "ok cool hey txt mob".split(),
    "hf_phishing_texts": "regards enterprise quarterly attached forwarded".split(),
    "synthetic_llm": "aapka bhai kripya abhi jaldi".split(),
}


def make_frame(n_per_source: dict[str, int], seed: int, synthetic_sources=("synthetic_llm",),
               garbage_raw: bool = False, with_raw: bool = True) -> pd.DataFrame:
    """Tiny separable corpus: scam vs safe words, plus source-specific filler words."""
    rng = np.random.default_rng(seed)
    rows = []
    for source, n in n_per_source.items():
        for i in range(n):
            scam = bool(rng.random() < 0.4)
            words = list(rng.choice(SCAM_WORDS if scam else SAFE_WORDS, 4)) + list(rng.choice(FILLER[source], 2))
            if rng.random() < 0.12:                      # label noise so nothing is perfectly separable
                words += list(rng.choice(SAFE_WORDS if scam else SCAM_WORDS, 2))
            rng.shuffle(words)
            text = " ".join(words) + (" <URL>" if scam and rng.random() < 0.5 else "")
            rows.append({
                "id": f"{source}-{seed}-{i}", "text": text, "label": "scam" if scam else "safe",
                "scam_type": "lottery" if scam else "none",
                "language": "hinglish" if source in synthetic_sources else "en",
                "source": source, "is_synthetic": source in synthetic_sources, "generator": None, "urls": [],
            })
    df = pd.DataFrame(rows)
    if with_raw:
        df["text_raw"] = ["GARBAGE " * 5 if garbage_raw else t for t in df["text"]]
    return df


def write_splits(directory: Path, garbage_raw: bool = False, flip_test: bool = False,
                 flip_val_synthetic: bool = False, with_raw: bool = True) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    kw = dict(garbage_raw=garbage_raw, with_raw=with_raw)
    train = make_frame({"uci_sms_spam": 160, "hf_phishing_texts": 160, "synthetic_llm": 80}, 1, **kw)
    val = make_frame({"uci_sms_spam": 50, "hf_phishing_texts": 50, "synthetic_llm": 30}, 2, **kw)
    test = make_frame({"uci_sms_spam": 60, "hf_phishing_texts": 60}, 3, **kw)
    if flip_test:
        test["label"] = test["label"].map({"scam": "safe", "safe": "scam"})
    if flip_val_synthetic:
        m = val["is_synthetic"]
        val.loc[m, "label"] = val.loc[m, "label"].map({"scam": "safe", "safe": "scam"})
    for name, df in (("train", train), ("val", val), ("test", test)):
        df.to_parquet(directory / f"{name}.parquet", index=False)


FAST = dict(feature_kinds=("word",), c_grids={"logreg": (1.0, 10.0), "svm": (0.1, 1.0)}, class_weights=(None, "balanced"))


def run(tmp: Path, name: str = "run", **write_kw) -> dict:
    proc = tmp / name / "processed"
    write_splits(proc, **write_kw)
    return B.run_baseline(
        proc, tmp / name / "models", tmp / name / "figs", f"sqlite:///{(tmp / name / 'mlflow.db').as_posix()}",
        tmp / name / "mlruns", say=lambda s: None, **FAST)


@pytest.fixture(scope="module")
def pipeline(tmp_path_factory: pytest.TempPathFactory) -> tuple[dict, Path]:
    tmp = tmp_path_factory.mktemp("baseline")
    return run(tmp), tmp / "run"


# ------------------------------- data and features -------------------------- #
def test_texts_of_reads_only_the_masked_text_and_truncates() -> None:
    df = pd.DataFrame({"text": ["a" * (B.MAX_CHARS + 500), "short"]})          # no text_raw column at all
    out = B.texts_of(df)
    assert len(out[0]) == B.MAX_CHARS and out[1] == "short"


def test_load_splits_rejects_synthetic_rows_in_test(tmp_path: Path) -> None:
    write_splits(tmp_path)
    test = pd.read_parquet(tmp_path / "test.parquet")
    test.loc[0, "is_synthetic"] = True
    test.to_parquet(tmp_path / "test.parquet", index=False)
    with pytest.raises(ValueError, match="100% real"):
        B.load_splits(tmp_path)


def test_splits_val_real_and_synthetic_partition_validation(tmp_path: Path) -> None:
    write_splits(tmp_path)
    s = B.load_splits(tmp_path)
    assert len(s.val_real) + len(s.val_synthetic) == len(s.val)
    assert not s.val_real["is_synthetic"].any() and s.val_synthetic["is_synthetic"].all()


@pytest.mark.parametrize("kind", B.FEATURE_KINDS)
def test_vectorizers_build_and_fit(kind: str) -> None:
    train = make_frame({"uci_sms_spam": 60}, 0)
    x = B.build_vectorizer(kind).fit_transform(B.texts_of(train))
    assert x.shape[0] == 60 and x.shape[1] > 10


def test_word_plus_char_is_the_concatenation() -> None:
    texts = B.texts_of(make_frame({"uci_sms_spam": 60}, 0))
    w = B.build_vectorizer("word").fit_transform(texts).shape[1]
    c = B.build_vectorizer("char").fit_transform(texts).shape[1]
    assert B.build_vectorizer("word+char").fit_transform(texts).shape[1] == w + c


def test_unknown_feature_kind_or_model_raises() -> None:
    with pytest.raises(ValueError):
        B.build_vectorizer("nope")
    with pytest.raises(ValueError):
        B.make_classifier("nope", B.Config("word", 1.0, None))


def test_features_are_fitted_on_train_only() -> None:
    train = pd.DataFrame({"text": ["alpha beta gamma", "alpha beta delta", "alpha gamma delta"], "label": ["scam", "safe", "safe"],
                          "source": "s", "is_synthetic": False})
    fitted = B.fit_model("logreg", B.Config("word", 1.0, None), train)
    vocab = set(fitted.vectorizer.get_feature_names_out())
    assert "alpha" in vocab
    val_only = pd.DataFrame({"text": ["zzzunseen alpha"]})
    assert "zzzunseen" not in vocab
    assert fitted.scores(val_only).shape == (1,)             # unseen words are simply ignored


def test_make_classifier_types() -> None:
    from sklearn.linear_model import LogisticRegression
    from sklearn.svm import LinearSVC
    assert isinstance(B.make_classifier("logreg", B.Config("word", 1.0, None)), LogisticRegression)
    assert isinstance(B.make_classifier("svm", B.Config("word", 0.1, "balanced")), LinearSVC)


def test_source_class_weights_balance_every_cell() -> None:
    df = pd.DataFrame({"source": ["a"] * 6 + ["b"] * 3 + ["b"], "label": ["safe"] * 5 + ["scam"] + ["safe"] * 2 + ["scam"] * 2})
    w = B.source_class_weights(df)
    assert w.mean() == pytest.approx(1.0)
    cells = (df["source"] + "|" + df["label"])
    totals = pd.Series(w).groupby(cells.to_numpy()).sum()
    assert totals.nunique() == 1 or np.allclose(totals, totals.iloc[0])          # equal total weight per cell


# ---------------------------------- tuning ---------------------------------- #
def test_default_grids_are_not_edge_optimised() -> None:
    """The first logreg optimum sat on the grid edge (C=100); the grid now extends past it."""
    assert 1000.0 in B.C_GRIDS["logreg"] and max(B.C_GRIDS["svm"]) >= 10.0
    assert set(B.C_GRIDS) == set(B.MODELS) and set(B.FEATURE_KINDS) == {"word", "char", "word+char"}


def test_tuning_function_cannot_receive_test_data() -> None:
    params = set(inspect.signature(B.tune).parameters)
    assert not any("test" in p for p in params)
    assert {"train", "val_real"} <= params


def test_tune_returns_full_sorted_grid() -> None:
    train = make_frame({"uci_sms_spam": 120, "hf_phishing_texts": 120}, 1)
    val = make_frame({"uci_sms_spam": 60, "hf_phishing_texts": 60}, 2)
    seen = []
    trials = B.tune("svm", train, val, ("word",), (0.1, 1.0), (None, "balanced"), on_trial=seen.append)
    assert len(trials) == len(seen) == 4
    assert [t.sort_key() for t in trials] == sorted(t.sort_key() for t in trials)
    assert trials[0].val["f1"] >= trials[-1].val["f1"]
    assert all(t.threshold == t.val["threshold"] for t in trials)


def _trial(f1: float, pr: float, c: float, kind: str = "word") -> B.Trial:
    m = {"f1": f1, "pr_auc": pr}
    return B.Trial("svm", B.Config(kind, c, None), 0.0, m, m, 0.0)


def test_select_best_prefers_f1_then_pr_auc_then_smaller_c() -> None:
    assert B.select_best([_trial(0.90, 0.9, 1), _trial(0.95, 0.5, 10)]).cfg.C == 10
    assert B.select_best([_trial(0.95, 0.9, 10), _trial(0.95, 0.8, 1)]).cfg.C == 10
    assert B.select_best([_trial(0.95, 0.9, 10), _trial(0.95, 0.9, 1)]).cfg.C == 1
    assert B.select_best([_trial(0.95, 0.9, 1, "char"), _trial(0.95, 0.9, 1, "word")]).cfg.feature_kind == "word"


def test_nan_scores_never_win_selection() -> None:
    assert B.select_best([_trial(float("nan"), float("nan"), 1), _trial(0.5, 0.5, 10)]).cfg.C == 10


def test_tune_threshold_uses_the_given_validation_rows() -> None:
    train = make_frame({"uci_sms_spam": 120}, 1)
    val = make_frame({"uci_sms_spam": 80}, 2)
    fitted = B.fit_model("logreg", B.Config("word", 1.0, None), train)
    tuned = B.tune_threshold(fitted, val)
    expected, _ = M.best_f1_threshold(M.labels_to_binary(val["label"]), fitted.scores(val))
    assert tuned.threshold == pytest.approx(expected) and fitted.threshold == M.DEFAULT_THRESHOLD


def test_evaluate_and_breakdowns() -> None:
    train = make_frame({"uci_sms_spam": 120, "hf_phishing_texts": 120}, 1)
    test = make_frame({"uci_sms_spam": 60, "hf_phishing_texts": 60}, 3)
    fitted = B.tune_threshold(B.fit_model("svm", B.Config("word", 1.0, None), train), test)
    ev = B.evaluate(fitted, test)
    assert set(ev) == {"tuned", "default"} and ev["tuned"]["f1"] >= ev["default"]["f1"] - 1e-9
    by = B.breakdowns(fitted, test, ("source", "language", "missing_column"))
    assert set(by) == {"source", "language"} and set(by["source"].index) == {"uci_sms_spam", "hf_phishing_texts"}


def test_top_features_lists_both_classes() -> None:
    train = make_frame({"uci_sms_spam": 200}, 1)
    fitted = B.fit_model("logreg", B.Config("word", 10.0, None), train)
    feats = B.top_features(fitted, n=5)
    assert set(feats["class"]) == {"scam", "safe"} and len(feats) == 10
    assert set(feats[feats["class"] == "scam"]["feature"]) & set(SCAM_WORDS)
    assert set(feats[feats["class"] == "safe"]["feature"]) & set(SAFE_WORDS)
    scam_w = feats[feats["class"] == "scam"]["weight"]
    assert (scam_w > 0).all() and (feats[feats["class"] == "safe"]["weight"] < 0).all()


# ----------------------------------- LOSO ----------------------------------- #
def test_loso_training_frame_excludes_the_held_out_source() -> None:
    train = make_frame({"uci_sms_spam": 40, "hf_phishing_texts": 40, "synthetic_llm": 40}, 1)
    sub = B.loso_training_frame(train, "hf_phishing_texts")
    assert "hf_phishing_texts" not in set(sub["source"]) and len(sub) == 80


def test_loso_training_frame_raises_when_nothing_is_left() -> None:
    train = make_frame({"uci_sms_spam": 40}, 1)
    with pytest.raises(ValueError, match="nothing left"):
        B.loso_training_frame(train, "uci_sms_spam")


def test_loso_eval_frame_uses_test_for_real_and_synthetic_validation_for_synthetic(tmp_path: Path) -> None:
    write_splits(tmp_path)
    s = B.load_splits(tmp_path)
    real = B.loso_eval_frame(s, "uci_sms_spam")
    assert set(real["source"]) == {"uci_sms_spam"} and not real["is_synthetic"].any() and len(real) == 60
    synth = B.loso_eval_frame(s, "synthetic_llm")
    assert synth["is_synthetic"].all() and len(synth) == len(s.val_synthetic)


# ------------------------------ end-to-end pipeline ------------------------- #
def test_pipeline_result_structure(pipeline: tuple[dict, Path]) -> None:
    res, _ = pipeline
    assert set(res["models"]) == {"logreg", "svm"} and set(res["variants"]) == {"logreg", "svm"}
    for m in res["models"].values():
        assert m["n_trials"] == 4 and m["best"]["features"] == "word"
        assert 0.5 < m["test"]["tuned"]["roc_auc"] <= 1.0
        assert {"source", "language", "scam_type"} == set(m["test_by"])
        assert m["real_indian"] is None
    assert res["sizes"]["val_real"] == 100 and res["sizes"]["val_synthetic"] == 30 and res["sizes"]["test"] == 120


def test_pipeline_writes_models_figures_and_json(pipeline: tuple[dict, Path]) -> None:
    _, root = pipeline
    for name in ("logreg", "svm"):
        assert (root / "models" / f"{name}.joblib").exists()
    for f in ("confusion_lr_test.png", "confusion_svm_test.png", "loso_roc_auc_lr.png", "loso_roc_auc_svm.png"):
        p = root / "figs" / f
        assert p.exists() and p.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n", f
    saved = json.loads((root / "processed" / B.RESULTS_JSON).read_text(encoding="utf-8"))
    assert saved["models"]["svm"]["best"] == pipeline[0]["models"]["svm"]["best"]


def test_saved_model_reproduces_the_reported_predictions(pipeline: tuple[dict, Path]) -> None:
    import joblib

    res, root = pipeline
    bundle = joblib.load(root / "models" / "svm.joblib")
    test = pd.read_parquet(root / "processed" / "test.parquet")
    scores = bundle["clf"].decision_function(bundle["vectorizer"].transform(B.texts_of(test)))
    m = M.binary_metrics(M.labels_to_binary(test["label"]), scores, bundle["threshold"])
    assert m["f1"] == pytest.approx(res["models"]["svm"]["test"]["tuned"]["f1"])


def test_loso_results_cover_each_source_and_variant(pipeline: tuple[dict, Path]) -> None:
    res, _ = pipeline
    rows = pd.DataFrame(res["loso"])
    assert set(rows["held_out"]) == {"uci_sms_spam", "hf_phishing_texts", "synthetic_llm"}
    assert set(rows["variant"]) == {"in-distribution", "leave-one-source-out", "source-balanced (LOSO)"}
    assert len(rows) == 2 * 3 * 3
    assert rows[rows["held_out"] == "synthetic_llm"]["diagnostic_only"].all()
    assert not rows[rows["held_out"] != "synthetic_llm"]["diagnostic_only"].any()


def test_loso_figures_can_be_redrawn_from_saved_json(pipeline: tuple[dict, Path], tmp_path: Path, capsys) -> None:
    res, root = pipeline
    out = B.make_loso_figures(json.loads(json.dumps(res)), tmp_path / "again")
    assert set(out) == {"logreg", "svm"}
    for p in out.values():
        assert Path(p).read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
    assert B.make_loso_figures({"loso": []}, tmp_path / "none") == {}
    assert B.main(["--replot", "--processed-dir", str(root / "processed"), "--figure-dir", str(tmp_path / "cli")]) == 0
    assert (tmp_path / "cli" / "loso_roc_auc_lr.png").exists() and "wrote" in capsys.readouterr().out


def test_mlflow_runs_parameters_and_metrics_are_logged(pipeline: tuple[dict, Path]) -> None:
    _, root = pipeline
    mlflow.set_tracking_uri(f"sqlite:///{(root / 'mlflow.db').as_posix()}")
    exp = mlflow.get_experiment_by_name(B.EXPERIMENT_NAME)
    runs = mlflow.search_runs([exp.experiment_id])
    stages = runs["tags.stage"].value_counts().to_dict()
    assert stages["trial"] == 8 and stages["tune+final"] == 2 and stages["mitigation"] == 2 and stages["loso"] == 6
    parent = runs[runs["tags.stage"] == "tune+final"].iloc[0]
    assert parent["params.best_features"] == "word" and not np.isnan(parent["metrics.test_f1"])
    assert not np.isnan(parent["metrics.val_real_f1"]) and not np.isnan(parent["metrics.val_synthetic_diag_f1"])
    assert Path(root / "mlruns").exists()


def test_test_metrics_are_never_logged_on_tuning_trials(pipeline: tuple[dict, Path]) -> None:
    _, root = pipeline
    mlflow.set_tracking_uri(f"sqlite:///{(root / 'mlflow.db').as_posix()}")
    exp = mlflow.get_experiment_by_name(B.EXPERIMENT_NAME)
    trials = mlflow.search_runs([exp.experiment_id], filter_string="tags.stage = 'trial'")
    assert len(trials) == 8
    leaked = [c for c in trials.columns if c.startswith("metrics.test") and trials[c].notna().any()]
    assert leaked == []
    assert trials["metrics.val_real_f1"].notna().all() and trials["params.C"].notna().all()


def test_mlflow_database_lives_under_the_chosen_uri_only(pipeline: tuple[dict, Path]) -> None:
    _, root = pipeline
    assert (root / "mlflow.db").exists()


# -------------------------- protocol guarantees (poisoning) ------------------ #
def test_selection_does_not_depend_on_test_labels_or_synthetic_validation(tmp_path: Path) -> None:
    base = run(tmp_path, "base")
    test_flipped = run(tmp_path, "flip_test", flip_test=True)
    syn_flipped = run(tmp_path, "flip_syn", flip_val_synthetic=True)
    for model in B.MODELS:
        assert test_flipped["models"][model]["best"] == base["models"][model]["best"]
        assert test_flipped["models"][model]["threshold"] == base["models"][model]["threshold"]
        assert syn_flipped["models"][model]["best"] == base["models"][model]["best"]
        assert syn_flipped["models"][model]["threshold"] == base["models"][model]["threshold"]
        # ...but the reported numbers do respond to the data they are computed on
        assert test_flipped["models"][model]["test"]["tuned"]["f1"] != base["models"][model]["test"]["tuned"]["f1"]
        assert (syn_flipped["models"][model]["val_synthetic_diag"]["tuned"]["f1"]
                != base["models"][model]["val_synthetic_diag"]["tuned"]["f1"])


def test_text_raw_is_never_used(tmp_path: Path) -> None:
    base = run(tmp_path, "base")
    garbage = run(tmp_path, "garbage", garbage_raw=True)
    no_raw = run(tmp_path, "noraw", with_raw=False)
    for other in (garbage, no_raw):
        for model in B.MODELS:
            assert other["models"][model]["best"] == base["models"][model]["best"]
            assert other["models"][model]["test"]["tuned"]["f1"] == base["models"][model]["test"]["tuned"]["f1"]


def test_runs_are_deterministic(tmp_path: Path) -> None:
    a, b = run(tmp_path, "a"), run(tmp_path, "b")
    for model in B.MODELS:
        assert a["models"][model]["test"]["tuned"] == b["models"][model]["test"]["tuned"]
        assert a["models"][model]["val_real"] == b["models"][model]["val_real"]


def test_real_indian_holdout_is_scored_when_present(tmp_path: Path) -> None:
    proc = tmp_path / "h" / "processed"
    write_splits(proc)
    hold = make_frame({"uci_sms_spam": 40}, 9, synthetic_sources=())
    hold["language"] = np.where(np.arange(len(hold)) % 2 == 0, "hinglish", "hi")
    hold["channel"], hold["collected_from"] = "sms", "own inbox"
    hold.to_parquet(proc / B.HOLDOUT_FILE, index=False)
    res = B.run_baseline(proc, tmp_path / "h" / "m", tmp_path / "h" / "f",
                         f"sqlite:///{(tmp_path / 'h' / 'mlflow.db').as_posix()}", tmp_path / "h" / "mlruns",
                         say=lambda s: None, run_loso=False, **FAST)
    assert res["sizes"]["real_indian_test"] == 40
    for model in B.MODELS:
        h = res["models"][model]["real_indian"]
        assert h["overall"]["tuned"]["n"] == 40 and set(h["by"]["language"]) == {"hinglish", "hi"}
    assert res["loso"] == []


# ------------------------------------ results.md ----------------------------- #
def test_markdown_contains_every_reported_number(pipeline: tuple[dict, Path]) -> None:
    res, _ = pipeline
    md = B.format_results_markdown(res)
    for heading in ("Comparison on the real test set", "Confusion matrices", "Test set by source",
                    "Test set by language", "Test set by scam type", "Diagnostic only", "Leave-one-source-out",
                    "Highest-weight features", "not built yet"):
        assert heading in md, heading
    for model in B.MODELS:
        t = res["models"][model]["test"]["tuned"]
        assert f"{t['f1']:.4f}" in md and f"{t['roc_auc']:.4f}" in md and f"{t['tp']:,}" in md
        assert res["models"][model]["title"] in md
    assert "source-balanced" in md


def test_update_results_md_replaces_only_the_marked_block(tmp_path: Path) -> None:
    path = tmp_path / "results.md"
    path.write_text("# Results\n\nkeep this\n\n" + B.MARKER_START + "\nOLD\n" + B.MARKER_END + "\n\nand this\n", encoding="utf-8")
    B.update_results_md(path, "NEW TABLE")
    text = path.read_text(encoding="utf-8")
    assert "NEW TABLE" in text and "OLD" not in text and "keep this" in text and "and this" in text
    B.update_results_md(path, "NEWER")
    again = path.read_text(encoding="utf-8")
    assert again.count(B.MARKER_START) == 1 and "NEWER" in again and "NEW TABLE" not in again


def test_update_results_md_appends_when_markers_absent(tmp_path: Path) -> None:
    path = tmp_path / "r.md"
    path.write_text("# Results\n", encoding="utf-8")
    B.update_results_md(path, "TABLE")
    assert path.read_text(encoding="utf-8").startswith("# Results") and B.MARKER_START in path.read_text(encoding="utf-8")
    B.update_results_md(tmp_path / "new.md", "X")                      # file that does not exist yet
    assert (tmp_path / "new.md").exists()


def test_cli_fast_run_updates_results_md(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    proc = tmp_path / "processed"
    write_splits(proc)
    results = tmp_path / "results.md"
    results.write_text("# Results\n", encoding="utf-8")
    code = B.main(["--fast", "--processed-dir", str(proc), "--model-dir", str(tmp_path / "m"),
                   "--figure-dir", str(tmp_path / "f"), "--tracking-uri", f"sqlite:///{(tmp_path / 'ml.db').as_posix()}",
                   "--artifact-root", str(tmp_path / "mlruns"), "--update-results", str(results)])
    assert code == 0
    assert "Comparison on the real test set" in results.read_text(encoding="utf-8")
    assert "Leave-one-source-out" in capsys.readouterr().out
