"""Tests for src.training.phase4_baseline on tiny synthetic frames (no real data, no MLflow)."""
from __future__ import annotations

from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import pytest

from src.training import baseline as B
from src.training import metrics as M
from src.training import phase4_baseline as P4

SCAM = ["win a free prize now click link", "your account is blocked verify now", "urgent claim your reward today",
        "free entry win cash prize", "verify your bank account immediately", "click here to claim free gift"]
SAFE = ["see you at lunch tomorrow", "meeting moved to friday afternoon", "can you send the report please",
        "happy birthday hope you have a great day", "the train leaves at noon", "thanks for the notes yesterday"]


def make_split(name: str, n: int, seed: int) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows = []
    for i in range(n):
        scam = i % 3 == 0
        text = f"{rng.choice(SCAM if scam else SAFE)} {i}"
        promo = (not scam) and i % 5 == 0
        rows.append({"id": f"{name}{i}", "label": "scam" if scam else "safe", "source": "uci_sms_spam" if i % 2 else "hf_phishing_texts",
                     "is_synthetic": False, "text": text, "text_raw": text, "benchmark": promo,
                     "language": "en", "scam_type": "none", "subtype": "promo" if promo else "unspecified"})
    return pd.DataFrame(rows)


@pytest.fixture()
def fitted_dir(tmp_path: Path) -> tuple[Path, Path]:
    data, models = tmp_path / "data", tmp_path / "models"
    data.mkdir()
    models.mkdir()
    for name, n, seed in (("train", 120, 0), ("val", 60, 1), ("test", 60, 2)):
        make_split(name, n, seed).to_parquet(data / f"{name}.parquet", index=False)
    train = pd.read_parquet(data / "train.parquet")
    cfg = B.Config("word", 1.0, None)
    for model in B.MODELS:
        fitted = B.fit_model(model, cfg, train)
        joblib.dump({"vectorizer": fitted.vectorizer, "clf": fitted.clf, "config": cfg.as_params(), "threshold": 0.1,
                     "max_chars": B.MAX_CHARS}, models / f"{model}.joblib")
    return data, models


def test_recall_first_operating_point_meets_target_on_validation(fitted_dir: tuple[Path, Path]) -> None:
    data, models = fitted_dir
    out = P4.extras(models, data, recall_target=0.9)
    for model in B.MODELS:
        rec = out["models"][model]
        assert rec["val_real_at_recall_first"]["recall"] >= 0.9 - 1e-9
        assert rec["thresholds"]["recall_first"] == pytest.approx(
            M.recall_first_threshold(M.labels_to_binary(pd.read_parquet(data / "val.parquet")["label"]),
                                     P4.load_fitted(model, models).scores(pd.read_parquet(data / "val.parquet")), 0.9))


def test_extras_report_both_operating_points_slices_and_benchmark(fitted_dir: tuple[Path, Path]) -> None:
    data, models = fitted_dir
    out = P4.extras(models, data)
    rec = out["models"]["logreg"]
    for point in ("f1_tuned", "recall_first"):
        r = rec[point]
        assert r["overall"]["n"] == 60 and r["short"]["n"] == 60          # every text is short here
        assert r["benchmark"]["n"] == int(pd.read_parquet(data / "test.parquet")["benchmark"].sum())
        assert 0.0 <= r["benchmark"]["flag_rate"] <= 1.0
        assert set(r["by_source"]) == {"uci_sms_spam", "hf_phishing_texts"}


def test_lower_threshold_flags_at_least_as_many_promotions(fitted_dir: tuple[Path, Path]) -> None:
    data, models = fitted_dir
    splits = B.load_splits(data)
    fitted = P4.load_fitted("svm", models)
    strict = P4.operating_point_report(fitted, splits, 1.0)["benchmark"]["flag_rate"]
    loose = P4.operating_point_report(fitted, splits, -1.0)["benchmark"]["flag_rate"]
    assert loose >= strict


def test_test_scores_are_written_per_row_without_text(fitted_dir: tuple[Path, Path]) -> None:
    data, models = fitted_dir
    P4.extras(models, data)
    scores = pd.read_csv(models / "test_scores_logreg.csv")
    assert list(scores.columns) == ["id", "label", "source", "score"]
    assert scores["id"].tolist() == pd.read_parquet(data / "test.parquet")["id"].tolist()
