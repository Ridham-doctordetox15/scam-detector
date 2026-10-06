"""Tests for src.training.ladder (validation-only ablation metrics and the selection rule)."""
from __future__ import annotations

import inspect

import numpy as np
import pandas as pd

from src.preprocessing import normalize as nz
from src.preprocessing import phase35 as p35
from src.training import ladder
from src.training.baseline import Config


def toy_frame(n: int, seed: int, split: str) -> pd.DataFrame:
    """Two real sources plus synthetic rows, with separable vocab so a model can learn something."""
    rng = np.random.default_rng(seed)
    scam_words = ["urgent", "verify", "kyc", "prize", "click", "otp", "blocked", "claim"]
    safe_words = ["meeting", "lunch", "report", "thanks", "tomorrow", "invoice", "family", "notes"]
    rows = []
    for i in range(n):
        scam = rng.random() < 0.4
        words = rng.choice(scam_words if scam else safe_words, 4)
        source = ["hf_phishing_texts", "uci_sms_spam", "synthetic_llm"][i % 3]
        text = " ".join(words) + f" ref{i}"
        rows.append({"id": f"{split}{i}", "text": text, "text_raw": text, "label": "scam" if scam else "safe",
                     "original_label": "scam" if scam else "safe", "scam_type": "unknown", "language": "en",
                     "source": source, "is_synthetic": source == "synthetic_llm", "generator": "", "urls": [],
                     "split": split, "subtype": "unspecified", "withheld": False, "benchmark": False})
    return pd.DataFrame(rows)


def toy_level() -> p35.LevelData:
    train, val, test = toy_frame(900, 1, "train"), toy_frame(450, 2, "val"), toy_frame(30, 3, "test")
    val.loc[val.index[val["source"] == "hf_phishing_texts"][:6], ["benchmark", "withheld"]] = True   # six legit promotions
    return p35.LevelData(p35.LEVELS["L2a"], train, val, test)


def test_selection_and_training_rows_exclude_withheld_and_synthetic() -> None:
    data = toy_level()
    assert data.val["withheld"].sum() == 6
    sel = ladder.selection_rows(data.val)
    assert not sel["is_synthetic"].any() and not sel["withheld"].any()
    data.train.loc[data.train.index[:5], "withheld"] = True
    assert len(ladder.training_rows(data.train)) == len(data.train) - 5


def test_source_identifiability_handles_three_or_more_sources() -> None:
    rng = np.random.default_rng(0)
    vocab = {"a": ["alpha", "apple", "amber"], "b": ["bravo", "berry", "blue"], "c": ["charlie", "cherry", "cyan"]}
    rows = [{"text": " ".join(rng.choice(vocab[s], 3)) + f" x{i}", "source": s, "is_synthetic": False}
            for i in range(120) for s in vocab]
    df = pd.DataFrame(rows)
    out = ladder.source_identifiability(df.iloc[:270], df.iloc[270:])
    assert out["accuracy"] > 0.95 and out["excess"] > 0.5 and out["sources"] == ["a", "b", "c"]


def test_short_slice_uses_raw_text_length() -> None:
    df = pd.DataFrame({"text_raw": ["a" * 300, "b" * 301, "c"]})
    assert ladder.short_slice(df)["text_raw"].str.len().tolist() == [300, 1]


def test_evaluate_level_reports_every_metric_and_ignores_the_test_split() -> None:
    data = toy_level()
    data.test["text"] = "poison"                                    # a touched test split must change nothing
    out = ladder.evaluate_level(data, cfg=Config("word", 1.0, None), say=lambda s: None)
    assert out["val"]["f1"] > 0.9 and out["val"]["roc_auc"] > 0.9
    assert out["val_short"]["n"] == out["val"]["n"]                  # every toy text is short
    assert out["benchmark_flag_rate"]["n"] == 6 and 0.0 <= out["benchmark_flag_rate"]["rate"] <= 1.0
    assert set(out["loso"]) == {"hf_phishing_texts", "uci_sms_spam"}
    assert set(out["audit"]) >= {"pass", "scam", "safe"} and out["source_identifiability"]["accuracy"] is not None
    clean = toy_level()
    again = ladder.evaluate_level(clean, cfg=Config("word", 1.0, None), say=lambda s: None)
    assert again["val"] == out["val"]


def test_ladder_module_never_touches_the_test_split() -> None:
    source = inspect.getsource(ladder)
    for banned in ("data.test", "splits.test", "test.parquet", "load_splits"):
        assert banned not in source


def audit(scam_fp: int, safe_fp: int, share: float) -> dict:
    return {"pass": scam_fp == 0 and safe_fp == 0 and share >= 0.5,
            "scam": {"fingerprint": scam_fp, "signal_share": share}, "safe": {"fingerprint": safe_fp, "signal_share": 0.1}}


def test_choose_first_passing_level_on_the_path() -> None:
    results = {"L0": {"audit": audit(2, 10, 0.33)}, "L1": {"audit": audit(2, 6, 0.4)},
               "L2a": {"audit": audit(0, 0, 0.6)}, "L3": {"audit": audit(0, 0, 0.9)}}
    choice = ladder.choose_level(results)
    assert choice["chosen"] == "L2a" and choice["criterion_met"]


def test_choose_ignores_the_contrast_branch() -> None:
    results = {"L0": {"audit": audit(2, 10, 0.33)}, "L2b": {"audit": audit(0, 0, 0.9)}}
    choice = ladder.choose_level(results)
    assert choice["chosen"] == "L0" and not choice["criterion_met"]


def test_choose_falls_back_to_fewest_fingerprints_then_signal_share() -> None:
    results = {"L0": {"audit": audit(2, 10, 0.33)}, "L1": {"audit": audit(1, 3, 0.30)},
               "L2a": {"audit": audit(2, 2, 0.45)}, "L3": {"audit": audit(1, 3, 0.40)}}
    choice = ladder.choose_level(results)
    assert choice["chosen"] == "L2a" and not choice["criterion_met"]       # 4 fingerprints ties L1/L3; highest share wins


def test_single_class_source_gets_a_shortcut_check_instead_of_an_auc() -> None:
    data = toy_level()
    rng = np.random.default_rng(5)
    extra = []
    for split, n in (("train", 120), ("val", 60)):
        for i in range(n):
            text = " ".join(rng.choice(["meeting", "lunch", "report", "airtel", "offer"], 4)) + f" in{split}{i}"
            extra.append({"id": f"in{split}{i}", "text": text, "text_raw": text, "label": "safe", "original_label": "scam" if i % 3 == 0 else "safe",
                          "scam_type": "none", "language": "en", "source": p35.INDIA_SOURCE, "is_synthetic": False,
                          "generator": "", "urls": [], "split": split, "subtype": "promo" if i % 3 == 0 else "unspecified",
                          "withheld": False, "benchmark": i % 3 == 0})
    data.train = pd.concat([data.train, pd.DataFrame([r for r in extra if r["split"] == "train"])], ignore_index=True)
    data.val = pd.concat([data.val, pd.DataFrame([r for r in extra if r["split"] == "val"])], ignore_index=True)
    out = ladder.evaluate_level(data, cfg=Config("word", 1.0, None), say=lambda s: None)
    assert p35.INDIA_SOURCE not in out["loso"]
    check = out["single_class_shortcut_check"][p35.INDIA_SOURCE]
    assert check["n"] == 60 and check["scams"] == 0
    assert check["by_group"]["promo_service"]["n"] == 20 and check["by_group"]["other"]["n"] == 40
    for key in ("flag_rate_trained_on_source", "flag_rate_source_held_out"):
        assert 0.0 <= check[key] <= 1.0
