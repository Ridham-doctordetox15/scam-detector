"""Tests for src.preprocessing.label_audit (no network access)."""
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.preprocessing import generate_synthetic as gs
from src.preprocessing import label_audit as LA


def make_frame(n: int = 40) -> pd.DataFrame:
    rows = []
    for i in range(n):
        scam = i % 2 == 0
        text = (f"urgent verify your kyc now click <URL> ref{i}" if scam else f"meeting agenda for friday number {i} thanks")
        rows.append({"text": text, "label": "scam" if scam else "safe", "scam_type": "fake_kyc" if scam else "none",
                     "language": "en", "source": "synthetic_llm", "is_synthetic": True,
                     "generator": "groq/m" if i % 4 in (0, 1) else "gemini/g", "topic": "fake_kyc" if scam else "everyday"})
    df = pd.DataFrame(rows)
    df["row_id"] = df["text"].map(LA.row_id)
    df["family"] = df["generator"].str.split("/").str[0]
    return df


class FakeJudge:
    """Judge that answers 'scam' when the message contains 'urgent', else 'safe' (optionally overridden)."""

    def __init__(self, name: str, overrides: dict[str, str] | None = None) -> None:
        self.name, self.model, self.calls, self.overrides = name, "m", 0, overrides or {}

    @property
    def generator_id(self) -> str:
        return f"{self.name}/{self.model}"

    def generate(self, prompt: str) -> str:
        self.calls += 1
        lines = [l for l in prompt.splitlines() if l[:1].isdigit() and ". " in l[:5]]
        verdicts = []
        for i, line in enumerate(lines):
            body = line.split(". ", 1)[1]
            v = next((val for key, val in self.overrides.items() if key in body), "scam" if "urgent" in body else "safe")
            verdicts.append({"i": i, "verdict": v})
        return json.dumps({"verdicts": verdicts})


def test_row_id_is_stable_and_short() -> None:
    assert LA.row_id("abc") == LA.row_id("abc") and len(LA.row_id("abc")) == 12 and LA.row_id("abc") != LA.row_id("abd")


def test_judge_family_is_the_other_provider() -> None:
    assert LA.judge_family("groq") == "gemini" and LA.judge_family("gemini") == "groq"


def test_judge_prompt_is_blind_and_numbered() -> None:
    p = LA.build_judge_prompt(["first message", "second message"])
    assert "0. first message" in p and "1. second message" in p and "RUBRIC" not in p
    assert "verdicts" in p and "unsure" in p
    assert "original label" not in p.lower()                  # the judge never sees the label


@pytest.mark.parametrize("raw", [
    '{"verdicts": [{"i": 0, "verdict": "scam"}, {"i": 1, "verdict": "SAFE"}]}',
    '```json\n{"verdicts": [{"i": 0, "verdict": "scam"}, {"i": 1, "verdict": "safe"}]}\n```',
    'Here you go: {"verdicts": [{"i": 0, "verdict": "scam"}, {"i": 1, "verdict": "safe"}]} done',
    '[{"i": 0, "verdict": "scam"}, {"i": 1, "verdict": "safe"}]',
])
def test_parse_verdicts_variants(raw: str) -> None:
    assert LA.parse_verdicts(raw, 2) == {0: "scam", 1: "safe"}


def test_parse_verdicts_skips_invalid_entries_and_rejects_garbage() -> None:
    out = LA.parse_verdicts('{"verdicts": [{"i": 0, "verdict": "maybe"}, {"i": 5, "verdict": "scam"}, {"i": 1, "verdict": "unsure"}]}', 2)
    assert out == {1: "unsure"}
    for bad in ("nothing", '{"other": 1}'):
        with pytest.raises(ValueError):
            LA.parse_verdicts(bad, 2)


def test_judging_uses_the_other_family_and_is_resumable(tmp_path: Path) -> None:
    frame = make_frame(40)
    groq, gemini = FakeJudge("groq"), FakeJudge("gemini")
    out = LA.judge_rows(frame, [groq, gemini], tmp_path / "j.jsonl", batch_size=10, say=lambda s: None)
    assert set(out) == set(frame["row_id"]) and groq.calls > 0 and gemini.calls > 0
    by = frame.set_index("row_id")
    assert all(out[r]["judge"].startswith("gemini") for r in by.index[by.family == "groq"])
    assert all(out[r]["judge"].startswith("groq") for r in by.index[by.family == "gemini"])
    calls = groq.calls + gemini.calls
    LA.judge_rows(frame, [groq, gemini], tmp_path / "j.jsonl", batch_size=10, say=lambda s: None)
    assert groq.calls + gemini.calls == calls                  # nothing left to judge on the second run


def test_judging_without_the_needed_provider_leaves_rows_unjudged(tmp_path: Path) -> None:
    frame = make_frame(20)
    msgs: list[str] = []
    out = LA.judge_rows(frame, [FakeJudge("groq")], tmp_path / "j.jsonl", say=msgs.append)
    assert set(out) == set(frame[frame.family == "gemini"]["row_id"]) and any("unjudged" in m for m in msgs)


def test_failed_judge_batches_are_skipped_not_recorded(tmp_path: Path) -> None:
    class Broken(FakeJudge):
        def generate(self, prompt: str) -> str:
            return "not json"

    out = LA.judge_rows(make_frame(20), [Broken("groq"), Broken("gemini")], tmp_path / "j.jsonl", say=lambda s: None)
    assert out == {}


def test_oof_scores_separate_the_classes() -> None:
    frame = make_frame(60)
    s = LA.oof_scores(frame)
    assert s[(frame.label == "scam").to_numpy()].mean() > 0 > s[(frame.label == "safe").to_numpy()].mean()


def test_rule_flag_needs_safe_label_urgency_and_link() -> None:
    assert LA.rule_flag("Pay now or service band ho jayega <URL>", "safe")
    assert LA.rule_flag("Urgent: call <PHONE> immediately", "safe")
    assert not LA.rule_flag("Pay now or service band ho jayega <URL>", "scam")     # only safe rows
    assert not LA.rule_flag("Your bill is due, thanks <URL>", "safe")               # no urgency
    assert not LA.rule_flag("Urgent meeting tomorrow", "safe")                       # no link/phone
    # raw (unmasked) links and phone numbers count too
    assert LA.rule_flag("Pay immediately or your connection will be cut: http://pay-now.example.com/x", "safe")
    assert LA.rule_flag("Turant call karo 9354718206 warna band ho jayega", "safe")
    assert LA.rule_flag("Last date today, pay at bit.ly/abc123", "safe")


def test_build_triage_flags_disagreements_and_adds_control() -> None:
    frame = make_frame(40)
    ids = frame["row_id"].tolist()
    judgements = {r: {"verdict": "scam" if l == "scam" else "safe", "judge": "x/y"} for r, l in zip(ids, frame["label"])}
    judgements[ids[1]] = {"verdict": "scam", "judge": "x/y"}              # safe row judged scam
    judgements[ids[2]] = {"verdict": "unsure", "judge": "x/y"}            # scam row judged unsure
    oof = np.where(frame["label"] == "scam", 3.0, -3.0)
    oof[3] = 2.0                                                          # safe row the model calls scam
    t = LA.build_triage(frame, judgements, oof, control_size=5)
    flagged = t[t.reasons != "control"]
    assert set(flagged.row_id) == {ids[1], ids[2], ids[3]}
    assert "judge" in flagged.set_index("row_id").loc[ids[1], "reasons"]
    assert "oof" in flagged.set_index("row_id").loc[ids[3], "reasons"]
    control = t[t.reasons == "control"]
    assert len(control) == 5 and not set(control.row_id) & set(flagged.row_id)


def test_build_triage_handles_unjudged_rows() -> None:
    frame = make_frame(10)
    t = LA.build_triage(frame, {}, np.where(frame["label"] == "scam", 1.0, -1.0), control_size=3)
    assert (t["judge"] == "unjudged").all() and (t["reasons"] == "control").all()


def test_apply_decisions_flips_removes_and_preserves_original() -> None:
    frame = make_frame(10)
    a, b, c, d = frame["row_id"].iloc[[0, 1, 2, 3]]
    out = LA.apply_decisions(frame, [LA.Decision(a, "flip", "reads safe"), LA.Decision(b, "flip", "reads scam"),
                                     LA.Decision(c, "remove", "ambiguous"), LA.Decision(d, "keep", "fine")])
    assert len(out) == 9 and c not in set(out.row_id)
    r = out.set_index("row_id")
    assert r.loc[a, "label"] == "safe" and r.loc[a, "original_label"] == "scam" and r.loc[a, "scam_type"] == "none"
    assert r.loc[b, "label"] == "scam" and r.loc[b, "original_label"] == "safe"
    assert r.loc[b, "scam_type"] == "unknown"                              # 'everyday' topic is not a scam type
    assert r.loc[d, "audit_action"] == "keep" and r.loc[d, "label"] == frame.set_index("row_id").loc[d, "label"]
    assert (out["audit_action"] == "unreviewed").sum() == 6


def test_flipped_safe_row_takes_its_scam_topic() -> None:
    frame = make_frame(4)
    frame.loc[1, "topic"] = "lottery"
    out = LA.apply_decisions(frame, [LA.Decision(frame["row_id"].iloc[1], "flip", "scam")])
    assert out.set_index("row_id").loc[frame["row_id"].iloc[1], "scam_type"] == "lottery"


def test_decision_validation() -> None:
    frame = make_frame(4)
    rid = frame["row_id"].iloc[0]
    with pytest.raises(ValueError, match="unknown action"):
        LA.apply_decisions(frame, [LA.Decision(rid, "delete", "x")])
    with pytest.raises(ValueError, match="unknown row_id"):
        LA.apply_decisions(frame, [LA.Decision("nope", "keep", "x")])
    with pytest.raises(ValueError, match="duplicate"):
        LA.apply_decisions(frame, [LA.Decision(rid, "keep", "x"), LA.Decision(rid, "flip", "y")])


def test_summarize_decisions() -> None:
    frame = make_frame(10)
    ids = frame["row_id"].tolist()
    s = LA.summarize_decisions(frame, [LA.Decision(ids[0], "flip", "x"), LA.Decision(ids[1], "remove", "x"),
                                       LA.Decision(ids[2], "keep", "x")])
    assert s["rows"] == 10 and s["reviewed"] == 3 and s["by_action"] == {"keep": 1, "flip": 1, "remove": 1, "unreviewed": 7}
    assert s["by_original_label"]["scam"]["flip"] == 1 and s["by_original_label"]["safe"]["remove"] == 1


def test_decisions_round_trip(tmp_path: Path) -> None:
    ds = [LA.Decision("a1", "flip", "why, with comma"), LA.Decision("b2", "keep", "")]
    LA.save_decisions(ds, tmp_path / "d" / "dec.csv")
    assert LA.load_decisions(tmp_path / "d" / "dec.csv") == ds


def test_review_sample_is_blind_stratified_and_scorable(tmp_path: Path) -> None:
    frame = make_frame(40)
    ids = frame["row_id"].tolist()
    decisions = ([LA.Decision(i, "flip", "f") for i in ids[:12]] + [LA.Decision(i, "remove", "r") for i in ids[12:24]]
                 + [LA.Decision(i, "keep", "k") for i in ids[24:40]])
    review_path, key_path = LA.export_review_sample(frame, decisions, tmp_path, n=30, seed=1)
    review = pd.read_csv(review_path, dtype=str, keep_default_na=False)
    assert len(review) == 30 and list(review.columns) == ["row_id", "text", "original_label", "my_decision", "notes"]
    assert (review["my_decision"] == "").all()                              # blank for the human
    assert "assistant" not in " ".join(review.columns).lower()              # assistant decisions not leaked
    key = pd.read_csv(key_path, dtype=str).set_index("row_id")
    counts = key.loc[review.row_id, "assistant_decision"].value_counts().to_dict()
    assert counts == {"flip": 10, "remove": 10, "keep": 10}
    assert review["row_id"].is_unique
    # human answers: agree on all but two
    answers = key.loc[review.row_id, "assistant_decision"].tolist()
    answers[0] = "keep" if answers[0] != "keep" else "flip"
    answers[1] = "remove" if answers[1] != "remove" else "flip"
    review["my_decision"] = [a.upper() if i > 2 else a for i, a in enumerate(answers)]
    review.to_csv(review_path, index=False)
    res = LA.agreement(review_path, key_path)
    assert res["answered"] == 30 and res["agree"] == 28 and res["agreement"] == pytest.approx(28 / 30)
    assert len(res["disagreements"]) == 2


def test_review_csv_with_a_spreadsheet_generic_header_row_is_read(tmp_path: Path) -> None:
    nl = chr(13) + chr(10)
    body = nl.join(["row_id,text,original_label,my_decision,notes", "a,t,safe,KEEP,", "b,u,scam,Flip,check"]) + nl
    generic = chr(0xFEFF) + "Column1,Column2,Column3,Column4,Column5" + nl
    (tmp_path / "r.csv").write_text(generic + body, encoding="utf-8")
    pd.DataFrame({"row_id": ["a", "b"], "assistant_decision": ["keep", "remove"], "assistant_reason": "r"}).to_csv(tmp_path / "k.csv", index=False)
    frame = LA.read_review_csv(tmp_path / "r.csv")
    assert list(frame.columns) == ["row_id", "text", "original_label", "my_decision", "notes"] and len(frame) == 2
    res = LA.agreement(tmp_path / "r.csv", tmp_path / "k.csv")
    assert res["answered"] == 2 and res["agree"] == 1 and res["disagreements"][0]["row_id"] == "b"
    plain = pd.DataFrame({"row_id": ["a"], "text": "t", "original_label": "safe", "my_decision": "keep", "notes": ""})
    plain.to_csv(tmp_path / "p.csv", index=False)
    assert list(LA.read_review_csv(tmp_path / "p.csv").columns)[0] == "row_id"


def test_agreement_ignores_blank_and_invalid_answers(tmp_path: Path) -> None:
    review = pd.DataFrame({"row_id": ["a", "b", "c"], "text": "t", "original_label": "safe",
                           "my_decision": ["keep", "", "maybe"], "notes": ""})
    key = pd.DataFrame({"row_id": ["a", "b", "c"], "assistant_decision": ["keep", "flip", "remove"], "assistant_reason": "r"})
    review.to_csv(tmp_path / "r.csv", index=False)
    key.to_csv(tmp_path / "k.csv", index=False)
    res = LA.agreement(tmp_path / "r.csv", tmp_path / "k.csv")
    assert res["answered"] == 1 and res["agreement"] == 1.0


def test_load_audit_frame_adds_ids_topics_and_family(tmp_path: Path) -> None:
    store = gs.ProgressStore(tmp_path / "s.jsonl")
    store.append({"key": "k1", "label": "scam", "topic": "lottery", "scam_type": "lottery", "language": "hinglish",
                  "provider": "groq", "model": "m",
                  "messages": ["Aapne lottery jeeti hai kya aap abhi claim karo, fee bharein"]})
    store.append({"key": "k2", "label": "safe", "topic": "everyday", "scam_type": "none", "language": "en",
                  "provider": "gemini", "model": "g", "messages": ["Are we meeting at the office tomorrow morning?"]})
    df = LA.load_audit_frame(tmp_path / "s.jsonl")
    assert set(df.family) == {"groq", "gemini"} and set(df.topic) == {"lottery", "everyday"}
    assert df.row_id.is_unique and df.row_id.map(len).eq(12).all()


def test_merge_overrides_replaces_and_adds() -> None:
    draft = [LA.Decision("a", "flip", "d"), LA.Decision("b", "keep", "d")]
    final = LA.merge_overrides(draft, [LA.Decision("a", "remove", "owner"), LA.Decision("c", "flip", "new")])
    assert {d.row_id: d.action for d in final} == {"a": "remove", "b": "keep", "c": "flip"}
    assert [d for d in final if d.row_id == "a"][0].reason == "owner"


def test_shipped_overrides_are_valid_decisions() -> None:
    overrides = LA.load_decisions(LA.OVERRIDES_PATH)
    assert overrides and all(d.action in LA.DECISIONS for d in overrides)
    assert len({d.row_id for d in overrides}) == len(overrides)
