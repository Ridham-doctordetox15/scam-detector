"""Tests for src.inference.tfidf_predictor, using a tiny real (not faked) TF-IDF + LinearSVC model."""
from __future__ import annotations

from pathlib import Path

import joblib
import numpy as np
import pytest
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.svm import LinearSVC

from src.inference import tfidf_predictor as T

SCAM_TEXTS = [
    "your kyc will expire today click here to update or account blocked",
    "urgent otp verification required share code now to avoid suspension",
    "congratulations you have won a cash prize call now to claim",
] * 5
SAFE_TEXTS = [
    "hey are we still meeting for lunch tomorrow",
    "your order has been delivered thank you for shopping",
    "reminder your appointment is at 4pm today",
] * 5


def _fit_and_save(tmp_path: Path, model_name: str = "svm") -> tuple[Path, float]:
    texts = SCAM_TEXTS + SAFE_TEXTS
    labels = [1] * len(SCAM_TEXTS) + [0] * len(SAFE_TEXTS)
    vectorizer = TfidfVectorizer(analyzer="word", ngram_range=(1, 2), min_df=1)
    x = vectorizer.fit_transform(texts)
    clf = LinearSVC(random_state=42)
    clf.fit(x, labels)
    threshold = 0.0  # LinearSVC's own decision boundary
    joblib.dump({"vectorizer": vectorizer, "clf": clf, "config": {}, "threshold": threshold, "max_chars": 2000},
                tmp_path / f"{model_name}.joblib")
    return tmp_path, threshold


# ---------------------------- sigmoid ---------------------------- #
@pytest.mark.parametrize("x, expected", [(0.0, 0.5)])
def test_sigmoid_at_zero(x: float, expected: float) -> None:
    assert T.sigmoid(x) == pytest.approx(expected)


def test_sigmoid_is_monotonic_and_bounded() -> None:
    xs = [-10, -1, 0, 1, 10]
    ys = [T.sigmoid(x) for x in xs]
    assert ys == sorted(ys)
    assert all(0.0 < y < 1.0 for y in ys)


def test_sigmoid_handles_large_negative_without_overflow() -> None:
    assert T.sigmoid(-1000.0) == pytest.approx(0.0, abs=1e-9)
    assert T.sigmoid(1000.0) == pytest.approx(1.0, abs=1e-9)


# ---------------------------- load ---------------------------- #
def test_load_missing_model_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        T.TfidfPredictor.load(tmp_path, "svm")


def test_load_reads_saved_artifact(tmp_path: Path) -> None:
    model_dir, threshold = _fit_and_save(tmp_path)
    predictor = T.TfidfPredictor.load(model_dir, "svm")
    assert predictor.threshold == threshold


# ---------------------------- prepare ---------------------------- #
def test_prepare_rejects_non_string(tmp_path: Path) -> None:
    predictor = T.TfidfPredictor.load(_fit_and_save(tmp_path)[0])
    with pytest.raises(ValueError, match="string"):
        predictor.prepare(12345)  # type: ignore[arg-type]


def test_prepare_rejects_empty_after_cleaning(tmp_path: Path) -> None:
    predictor = T.TfidfPredictor.load(_fit_and_save(tmp_path)[0])
    with pytest.raises(ValueError, match="empty"):
        predictor.prepare("   ")


def test_prepare_masks_urls_and_phones(tmp_path: Path) -> None:
    predictor = T.TfidfPredictor.load(_fit_and_save(tmp_path)[0])
    prepared = predictor.prepare("visit http://example.com or call 9876543210")
    assert "example.com" not in prepared
    assert "9876543210" not in prepared


def test_prepare_truncates_to_max_chars(tmp_path: Path) -> None:
    predictor = T.TfidfPredictor.load(_fit_and_save(tmp_path)[0])
    prepared = predictor.prepare("a" * (T.MAX_CHARS + 500))
    assert len(prepared) <= T.MAX_CHARS


# ---------------------------- predict / predict_proba ---------------------------- #
def test_predict_flags_scam_like_text(tmp_path: Path) -> None:
    predictor = T.TfidfPredictor.load(_fit_and_save(tmp_path)[0])
    result = predictor.predict("your kyc will expire today click here to update or account blocked")
    assert result.is_scam is True
    assert 0.0 <= result.scam_probability <= 1.0


def test_predict_does_not_flag_safe_text(tmp_path: Path) -> None:
    predictor = T.TfidfPredictor.load(_fit_and_save(tmp_path)[0])
    result = predictor.predict("hey are we still meeting for lunch tomorrow")
    assert result.is_scam is False


def test_predict_proba_rejects_bare_string(tmp_path: Path) -> None:
    predictor = T.TfidfPredictor.load(_fit_and_save(tmp_path)[0])
    with pytest.raises(TypeError):
        predictor.predict_proba("not a list")  # type: ignore[arg-type]


def test_predict_proba_preserves_order(tmp_path: Path) -> None:
    predictor = T.TfidfPredictor.load(_fit_and_save(tmp_path)[0])
    texts = [
        "your kyc will expire today click here to update or account blocked",
        "hey are we still meeting for lunch tomorrow",
    ]
    probs = predictor.predict_proba(texts)
    assert len(probs) == 2
    assert probs[0] > probs[1]  # scam-like text scores higher than safe-like text


def test_is_scam_uses_raw_margin_not_sigmoid(tmp_path: Path) -> None:
    """At the exact threshold, is_scam is decided by the raw margin, sigmoid(0)=0.5 either way."""
    predictor = T.TfidfPredictor.load(_fit_and_save(tmp_path)[0])
    prepared = predictor.prepare("hey are we still meeting for lunch tomorrow")
    margin = float(predictor._margins([prepared])[0])
    result = predictor.predict("hey are we still meeting for lunch tomorrow")
    assert result.is_scam == (margin >= predictor.threshold)
