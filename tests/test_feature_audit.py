"""Tests for src.training.feature_audit."""
import numpy as np
import pandas as pd
import pytest

from src.training import feature_audit as FA


@pytest.mark.parametrize("name", [
    "word__enron", "word__enron com", "char__enr", "char__ enro", "char__nro", "word__2005", "word__2001",
    "char__ £", "word__£100", "char__ >", "word__gt", "word__wrote", "word__kaminski", "word__vince",
    "word__linguistics", "word__original message", "word__lor", "word__university", "word__forwarded",
])
def test_fingerprints_are_detected(name: str) -> None:
    assert FA.classify_feature(name) == "fingerprint"


@pytest.mark.parametrize("name", [
    "word__urgent", "word__click here", "word__otp", "word__kyc", "word__prize", "word__verify your",
    "word__free", "word__claim", "word__http", "word__account blocked", "word__jaldi", "word__customs",
    "word__pay", "word__lottery", "char__urge", "char__verif", "word__congratulations", "word__phone",
])
def test_signals_are_detected(name: str) -> None:
    assert FA.classify_feature(name) == "signal"


@pytest.mark.parametrize("name", ["char__ ! ", "char__ .", "char__!", "char__ , ", "char__..", "word__"])
def test_punctuation_only_features_are_format(name: str) -> None:
    assert FA.classify_feature(name) == "format"


@pytest.mark.parametrize("name", ["word__thanks", "word__meeting", "word__tomorrow", "word__ok", "word__hello"])
def test_ordinary_words_are_other(name: str) -> None:
    assert FA.classify_feature(name) == "other"


def test_free_is_a_signal_not_a_fingerprint_regression() -> None:
    """'free' is a substring of the long fingerprint word 'newsisfree'; it must stay a signal."""
    assert FA.classify_feature("word__free") == "signal"
    assert FA.classify_feature("char__free") == "signal"


def test_modern_years_are_not_fingerprints() -> None:
    assert FA.classify_feature("word__2024") == "other"
    assert FA.classify_feature("word__2025") == "other"
    assert FA.classify_feature("word__2004") == "fingerprint"


def test_fingerprint_wins_over_signal() -> None:
    assert FA.classify_feature("word__enron account") == "fingerprint"
    assert FA.classify_feature("word__forwarded message") == "fingerprint"


def test_short_char_ngrams_do_not_count_as_signals() -> None:
    assert FA.classify_feature("char__ur") == "other"
    assert FA.classify_feature("char__ot") == "other"


def _top(scam: list[str], safe: list[str]) -> pd.DataFrame:
    rows = [("scam", f, 1.0 - i / 100) for i, f in enumerate(scam)] + [("safe", f, -1.0 + i / 100) for i, f in enumerate(safe)]
    return pd.DataFrame(rows, columns=["class", "feature", "weight"])


def test_audit_counts_and_shares() -> None:
    a = FA.audit_top_features(_top(["word__urgent", "word__otp", "word__2005", "word__hello"],
                                   ["word__enron", "word__thanks"]), n=4)
    assert a["scam"]["signal"] == 2 and a["scam"]["fingerprint"] == 1 and a["scam"]["other"] == 1
    assert a["scam"]["signal_share"] == pytest.approx(0.5) and a["scam"]["fingerprints"] == ["2005"]
    assert a["safe"]["fingerprint"] == 1 and a["safe"]["n"] == 2
    assert a["scam"]["signals"] == ["urgent", "otp"]


def test_audit_respects_top_n() -> None:
    feats = [f"word__urgent{i}" for i in range(50)]
    a = FA.audit_top_features(_top(feats, ["word__meeting"] * 50), n=10)
    assert a["scam"]["n"] == 10 and a["safe"]["n"] == 10


def test_pass_rule() -> None:
    good = FA.audit_top_features(_top(["word__urgent", "word__otp", "word__click", "word__hello"], ["word__thanks"]), n=4)
    assert FA.passes(good)                                                # 75% signal, no fingerprints
    fp_scam = FA.audit_top_features(_top(["word__urgent", "word__otp", "word__click", "word__2005"], ["word__thanks"]), n=4)
    assert not FA.passes(fp_scam)
    fp_safe = FA.audit_top_features(_top(["word__urgent", "word__otp"], ["word__enron"]), n=4)
    assert not FA.passes(fp_safe)
    low_signal = FA.audit_top_features(_top(["word__hello", "word__thanks", "word__urgent"], ["word__meeting"]), n=4)
    assert not FA.passes(low_signal)                                      # 33% < 50%


def test_word_audit_model_finds_the_separating_words() -> None:
    rng = np.random.default_rng(0)
    scam_w, safe_w = ["urgent", "prize", "otp", "click"], ["meeting", "lunch", "report", "agenda"]
    texts, y = [], []
    for _ in range(300):
        s = rng.random() < 0.4
        texts.append(" ".join(rng.choice(scam_w if s else safe_w, 4)))
        y.append(int(s))
    vec, clf = FA.word_audit_model(texts, np.array(y))
    top = FA.top_features_of(vec, clf, n=4)
    a = FA.audit_top_features(top, n=4)
    assert a["scam"]["signal"] >= 3 and FA.passes(a)


def test_top_features_of_shape_and_order() -> None:
    rng = np.random.default_rng(1)
    texts = [" ".join(rng.choice(["alpha", "beta", "gamma", "delta"], 3)) for _ in range(100)]
    y = np.array([int("alpha" in t) for t in texts])
    vec, clf = FA.word_audit_model(texts, y)
    top = FA.top_features_of(vec, clf, n=3)
    assert len(top) == 6 and set(top["class"]) == {"scam", "safe"}
    assert top[top["class"] == "scam"]["weight"].is_monotonic_decreasing
    assert top[top["class"] == "safe"]["weight"].is_monotonic_increasing


def test_format_audit_mentions_verdict_and_fingerprints() -> None:
    a = FA.audit_top_features(_top(["word__urgent", "word__2005"], ["word__enron"]), n=2)
    text = FA.format_audit(a, "TITLE")
    assert "TITLE" in text and "PASS: False" in text and "2005" in text and "enron" in text
