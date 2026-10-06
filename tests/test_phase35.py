"""Tests for src.preprocessing.phase35 (levels of the ablation ladder)."""
from __future__ import annotations

import pandas as pd
import pytest

from src.preprocessing import label_audit as la
from src.preprocessing import normalize as nz
from src.preprocessing import phase35 as p35
from src.preprocessing.preprocess import make_id


def row(text: str, label: str, source: str, split: str, synthetic: bool = False, subtype: str = "unspecified") -> dict:
    return {"id": make_id(text), "text": text, "text_raw": text, "label": label, "original_label": label,
            "scam_type": "none" if label == "safe" else "unknown", "language": "en", "source": source,
            "is_synthetic": synthetic, "generator": "", "urls": [], "split": split, "subtype": subtype}


def frame(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows)


# ------------------------------- policy ------------------------------------ #
def legit_frame() -> pd.DataFrame:
    return frame([
        row("win a prize call now", "scam", p35.UCI_SOURCE, "train", subtype="fraud"),
        row("ringtone offer reply stop", "scam", p35.UCI_SOURCE, "train", subtype="promo"),
        row("your data quota is low", "scam", p35.INDIA_SOURCE, "val", subtype="service"),
        row("see you at lunch", "safe", p35.UCI_SOURCE, "test"),
        row("hdfc kyc update link", "scam", "hf_phishing_texts", "train"),
    ])


def test_policy_d_withholds_promo_and_service_but_keeps_labels() -> None:
    out = p35.apply_policy(legit_frame(), "D")
    assert out["withheld"].tolist() == [False, True, True, False, False]
    assert out["benchmark"].tolist() == out["withheld"].tolist()
    assert out["label"].tolist() == legit_frame()["label"].tolist()


def test_policy_a_relabels_promo_and_service_safe() -> None:
    out = p35.apply_policy(legit_frame(), "A")
    assert out["label"].tolist() == ["scam", "safe", "safe", "safe", "scam"]
    assert out["scam_type"].iloc[1] == "none" and not out["withheld"].any()
    assert out["benchmark"].sum() == 2                    # still measurable as a benchmark


def test_policy_old_changes_nothing_but_marks_the_benchmark() -> None:
    out = p35.apply_policy(legit_frame(), "old")
    assert out["label"].tolist() == legit_frame()["label"].tolist() and not out["withheld"].any()
    assert out["benchmark"].sum() == 2


def test_policy_rejects_unknown_name() -> None:
    with pytest.raises(ValueError):
        p35.apply_policy(legit_frame(), "Z")


# -------------------------------- audit ------------------------------------ #
def test_apply_audit_flips_and_removes_synthetic_rows_only() -> None:
    texts = ["synthetic keep", "synthetic flip to scam", "synthetic remove", "synthetic scam to safe"]
    df = frame([row(texts[0], "safe", "synthetic_llm", "train", True),
                row(texts[1], "safe", "synthetic_llm", "train", True),
                row(texts[2], "scam", "synthetic_llm", "val", True, "fraud"),
                row(texts[3], "scam", "synthetic_llm", "train", True, "fraud"),
                row("real row that shares no id", "safe", "hf_phishing_texts", "train")])
    actions = {la.row_id(texts[0]): "keep", la.row_id(texts[1]): "flip", la.row_id(texts[2]): "remove",
               la.row_id(texts[3]): "flip"}
    out, report = p35.apply_audit(df, actions)
    assert report["flip"] == 2 and report["remove"] == 1 and report["keep"] == 1
    by_text = out.set_index("text")
    assert texts[2] not in by_text.index and len(out) == 4
    assert by_text.loc[texts[1], ["label", "scam_type", "subtype"]].tolist() == ["scam", "unknown", "fraud"]
    assert by_text.loc[texts[3], ["label", "scam_type", "subtype"]].tolist() == ["safe", "none", "unspecified"]
    assert by_text.loc[texts[0], "label"] == "safe" and by_text.loc["real row that shares no id", "label"] == "safe"
    assert by_text["original_label"].loc[texts[1]] == "safe"          # the original label is preserved


# -------------------------------- splits ----------------------------------- #
def test_assign_splits_sizes_and_rare_strata() -> None:
    labels = ["safe"] * 200 + ["scam"] * 98 + ["scam"] * 1
    subtypes = ["unspecified"] * 200 + ["promo"] * 98 + ["fraud"]
    df = pd.DataFrame({"label": labels, "subtype": subtypes, "source": "s"})
    out = p35.assign_splits(df, seed=1)
    counts = pd.Series(out).value_counts()
    assert set(out) == {"train", "val", "test"} and len(out) == 299
    assert abs(counts["val"] / 299 - 0.15) < 0.03 and abs(counts["test"] / 299 - 0.15) < 0.03
    assert (out == p35.assign_splits(df, seed=1)).all()                 # deterministic


# ------------------------------- levels ------------------------------------ #
def reference_frame() -> pd.DataFrame:
    rows = []
    for i in range(30):
        split = "train" if i < 20 else "val" if i < 25 else "test"
        rows.append(row(f"account {i} blocked verify kyc now click link{i}", "scam", "hf_phishing_texts", split))
        rows.append(row(f"meeting notes number {i} attached for the team tomorrow morning", "safe", "hf_phishing_texts", split))
    rows.append(row("lucky draw prize call 0800 now", "scam", p35.UCI_SOURCE, "train", subtype="fraud"))
    rows.append(row("free ringtone reply stop 87131", "scam", p35.UCI_SOURCE, "train", subtype="promo"))
    return frame(rows)


def test_build_level_l0_returns_reference_splits_unchanged() -> None:
    ref = reference_frame()
    data = p35.build_level("L0", ref, None, {})
    assert (len(data.train), len(data.val), len(data.test)) == (42, 10, 10)
    assert not data.train["withheld"].any() and data.train["benchmark"].sum() == 1


def test_build_level_l2a_adds_india_and_withholds_legit_rows() -> None:
    ref = reference_frame()
    india = frame([row("airtel offer recharge now", "scam", p35.INDIA_SOURCE, "train", subtype="promo"),
                   row("stock tips for the group today", "safe", p35.INDIA_SOURCE, "test")])
    data = p35.build_level("L2a", ref, india, {})
    assert len(data.train) == 43 and len(data.test) == 11
    assert data.train["withheld"].sum() == 2                     # UCI promo + India promo
    assert set(data.train["source"]) >= {p35.INDIA_SOURCE}


def test_build_level_requires_india_rows_when_the_level_needs_them() -> None:
    with pytest.raises(ValueError):
        p35.build_level("L2a", reference_frame(), None, {})


def test_renormalize_drops_rows_masks_years_and_keeps_splits_disjoint() -> None:
    rows = [row(f"linguistics conference {2000 + i % 5} paper number {i} deadline extended for abstracts", "safe",
                "hf_phishing_texts", "train") for i in range(6)]
    rows += [row("URL: http://example.com/x Date: 2005-01-01 crawled page about pills", "scam", "hf_phishing_texts", "train"),
             row("verify your account now 2003 offer expires", "scam", "hf_phishing_texts", "val"),
             row("meeting at noon tomorrow please confirm attendance", "safe", "hf_phishing_texts", "test")]
    df = p35.apply_policy(frame(rows), "old")
    out, stats = p35.renormalize(df, nz.LEVEL_A_B1)
    assert stats["dropped_by_rule"]["web_crawl"]["total"] == 1
    assert not out["text"].str.contains("2003").any() and out["text"].str.contains("<YEAR>").any()
    assert not out["text_raw"].str.startswith("URL:").any()
    assert out["text_raw"].str.contains("2003").any()                      # the original stays in text_raw
    parts = {n: set(out.loc[out["split"] == n, "id"]) for n in p35.SPLIT_NAMES}
    assert not (parts["train"] & parts["val"]) and not (parts["train"] & parts["test"])


def test_levels_are_cumulative_and_l2b_is_a_contrast() -> None:
    assert p35.LADDER_ORDER == ("L0", "L1", "L2a", "L3", "L4", "L5") and "L2b" in p35.LEVELS
    assert p35.LEVELS["L2a"].policy == "D" and p35.LEVELS["L2b"].policy == "A"
    for name in ("L3", "L4", "L5"):
        assert p35.LEVELS[name].policy == "D" and p35.LEVELS[name].india and p35.LEVELS[name].audit
    assert p35.LEVELS["L4"].normalize.drop_web_crawl and not p35.LEVELS["L4"].normalize.drop_enron_internal
    assert p35.LEVELS["L5"].normalize.drop_enron_internal


def test_describe_counts() -> None:
    data = p35.build_level("L0", reference_frame(), None, {})
    d = p35.describe(data)
    assert d["train"]["rows"] == 42 and d["train"]["benchmark"] == 1 and d["test"]["by_label"]["scam"] == 5


def test_load_reference_tags_uci_subtypes_and_keeps_original_label(tmp_path) -> None:
    ref = reference_frame().drop(columns=["split", "subtype", "original_label"])
    ref.loc[ref["source"] == p35.UCI_SOURCE, "text_raw"] = [
        "URGENT! You have won a £1000 prize. Call 09061701461 to claim", "FREE ringtone! Text TONE to 87131 now 150p/wk"]
    for name, part in {"train": ref.iloc[[i for i in range(len(ref)) if i % 3 == 0]],
                       "val": ref.iloc[[i for i in range(len(ref)) if i % 3 == 1]],
                       "test": ref.iloc[[i for i in range(len(ref)) if i % 3 == 2]]}.items():
        part.to_parquet(tmp_path / f"{name}.parquet", index=False)
    loaded = p35.load_reference(tmp_path)
    uci = loaded[loaded["source"] == p35.UCI_SOURCE].set_index("text_raw")["subtype"]
    assert set(uci) == {"fraud", "promo"} and len(loaded) == len(ref)
    assert set(loaded["split"]) == {"train", "val", "test"} and (loaded["label"] == loaded["original_label"]).all()


def test_l3b_is_policy_a_with_normalisation_and_is_off_the_ladder_path() -> None:
    lvl = p35.LEVELS["L3b"]
    assert lvl.policy == "A" and lvl.india and lvl.audit and lvl.normalize == nz.LEVEL_A
    assert "L3b" not in p35.LADDER_ORDER
