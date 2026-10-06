"""Label-noise audit for the synthetic messages.

The synthetic "safe" class contains hard negatives (genuine bank OTPs, courier updates, bill
reminders) that an LLM often makes look like scams, and some "scam" rows read as genuine.
This module finds candidates for review from four independent signals, and applies the
reviewer's decisions:

1. **Cross-family LLM judge**: every message is judged *blind* (the judge never sees the
   original label) by a model from the *other* provider than the one that wrote it.
2. **Out-of-fold classifier**: a TF-IDF model trained on the other folds disagrees with the label.
3. **Rule flag**: a "safe" message that combines urgency/threat wording with a link or phone.
4. **Random control sample**: rows *outside* the triage set, reviewed too, to estimate how much
   noise the triage misses.

Decisions are ``keep``, ``flip`` (change the label) or ``remove`` (ambiguous: drop the row).
The original label is always preserved in the audit record.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import StratifiedKFold, cross_val_predict
from sklearn.pipeline import make_pipeline, make_union

from src.preprocessing import generate_synthetic as gs
from src.preprocessing.preprocess import mask_text

logger = logging.getLogger(__name__)

AUDIT_DIR = Path("data/synthetic/audit")
OVERRIDES_PATH = Path("docs/synthetic_audit_overrides.csv")
AUDITED_PATH = Path("data/synthetic/audited.parquet")
JUDGE_BATCH = 20
CONTROL_SIZE = 100
DECISIONS = ("keep", "flip", "remove")

RUBRIC = """A message is a SCAM if it tries to obtain money, an OTP/PIN/password, personal or bank details,
an app installation or a click, through deception or pressure: a fake prize or lottery, a fake
authority (bank, police, customs, courier, electricity board), a threat (account blocked, power cut,
arrest), an unsolicited job or loan needing a fee, or a request to "verify" or "update" details via a
link or phone number.
A message is SAFE if it is informational or personal and asks for none of that: a genuine OTP or
transaction alert (including "do not share this OTP"), a delivery or bill notice without a payment
link or threat, an interview or meeting message, ordinary chat.
Use "unsure" only if a careful reader could reasonably go either way."""

_URGENCY_RE = re.compile(
    r"turant|jaldi|urgent|immediately|abhi|aaj hi|warna|varna|otherwise|expire|blocked|suspend|"
    r"band ho|cut ho|last date|within 24|asap|penalty|disconnect",
    re.IGNORECASE,
)


def row_id(text: str) -> str:
    """Stable 12-hex-character id of a raw message (used to key audit decisions)."""
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:12]


# --------------------------------------------------------------------------- #
# Loading
# --------------------------------------------------------------------------- #
def load_audit_frame(raw_jsonl: Path = gs.DEFAULT_OUTPUT) -> pd.DataFrame:
    """Kept synthetic rows (after the generator's own filters) with ``row_id`` and ``topic``.

    ``topic`` is the category the generator was *asked* to write (for safe rows: the scam type
    whose genuine counterpart was requested, or ``everyday``); it is context for the reviewer.
    """
    frame = gs.load_synthetic(raw_jsonl)
    topics = {}
    for rec in gs.ProgressStore(raw_jsonl).read_records():
        for msg in rec["messages"]:
            topics.setdefault(msg.casefold(), rec.get("topic", ""))
    frame = frame.copy()
    frame["row_id"] = frame["text"].map(row_id)
    frame["topic"] = frame["text"].map(lambda t: topics.get(t.casefold(), ""))
    frame["family"] = frame["generator"].str.split("/").str[0]        # groq | gemini
    return frame.reset_index(drop=True)


# --------------------------------------------------------------------------- #
# Signal 1: cross-family blind LLM judge
# --------------------------------------------------------------------------- #
def judge_family(writer_family: str) -> str:
    """The provider that judges messages written by ``writer_family`` (always the other one)."""
    return "gemini" if writer_family == "groq" else "groq"


def build_judge_prompt(texts: list[str]) -> str:
    """Prompt asking for a blind verdict on each message (no original label is shown)."""
    numbered = "\n".join(f"{i}. {t}" for i, t in enumerate(texts))
    return (
        "You are auditing a dataset for a scam-detection classifier that protects people in India. "
        "Judge each message on its own, using this rubric.\n\n"
        f"{RUBRIC}\n\n"
        f"Messages (masked tokens like <URL>, <PHONE>, <OTP> stand for removed values):\n{numbered}\n\n"
        'Respond with ONLY a JSON object: {"verdicts": [{"i": 0, "verdict": "scam"}, ...]} with one entry '
        'per message and verdict one of "scam", "safe", "unsure".'
    )


def parse_verdicts(raw: str, n: int) -> dict[int, str]:
    """Parse a judge reply into ``{index: verdict}`` (invalid entries are skipped)."""
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip(), flags=re.IGNORECASE)
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            raise ValueError("no JSON in judge reply") from None
        data = json.loads(match.group(0))
    items = data.get("verdicts") if isinstance(data, dict) else data
    if not isinstance(items, list):
        raise ValueError("judge reply has no verdict list")
    out: dict[int, str] = {}
    for item in items:
        if isinstance(item, dict) and isinstance(item.get("i"), int) and 0 <= item["i"] < n:
            verdict = str(item.get("verdict", "")).strip().lower()
            if verdict in ("scam", "safe", "unsure"):
                out[item["i"]] = verdict
    return out


def judge_rows(
    frame: pd.DataFrame,
    clients: list,
    store_path: Path,
    batch_size: int = JUDGE_BATCH,
    say: Callable[[str], None] = print,
) -> dict[str, dict[str, str]]:
    """Judge every row with a client from the other provider; resumable.

    Args:
        frame: Output of :func:`load_audit_frame`.
        clients: LLM clients (objects with ``name``, ``generator_id`` and ``generate``).
        store_path: JSONL file of finished judgements (one line per batch).

    Returns:
        ``{row_id: {"verdict": ..., "judge": ...}}`` for all rows judged so far.
    """
    store = gs.ProgressStore(store_path)
    done = {rid for rec in store.read_records() for rid in rec["row_ids"]}
    by_family = {c.name: [x for x in clients if x.name == c.name] for c in clients}
    for family in ("groq", "gemini"):
        pending = frame[(frame["family"] == family) & ~frame["row_id"].isin(done)]
        judges = by_family.get(judge_family(family), [])
        if pending.empty or not judges:
            if not pending.empty:
                say(f"no {judge_family(family)} client available; {len(pending)} rows unjudged")
            continue
        for start in range(0, len(pending), batch_size):
            chunk = pending.iloc[start:start + batch_size]
            client = judges[(start // batch_size) % len(judges)]
            try:
                verdicts = parse_verdicts(client.generate(build_judge_prompt(chunk["text"].tolist())), len(chunk))
            except (gs.TransientError, gs.QuotaExhausted, gs.APIError, ValueError) as exc:
                say(f"judge batch failed ({client.generator_id}): {exc}")
                continue
            ids = chunk["row_id"].tolist()
            store.append({"row_ids": [ids[i] for i in verdicts], "verdicts": [verdicts[i] for i in verdicts],
                          "judge": client.generator_id})
            say(f"judged {family}-written rows {start + len(chunk)}/{len(pending)} via {client.generator_id}")
    out: dict[str, dict[str, str]] = {}
    for rec in store.read_records():
        for rid, verdict in zip(rec["row_ids"], rec["verdicts"]):
            out[rid] = {"verdict": verdict, "judge": rec["judge"]}
    return out


# --------------------------------------------------------------------------- #
# Signals 2 and 3: out-of-fold classifier and rule flag
# --------------------------------------------------------------------------- #
def oof_scores(frame: pd.DataFrame, folds: int = 5, seed: int = 0) -> np.ndarray:
    """Out-of-fold decision scores (positive = model thinks scam) using only ``frame`` itself."""
    y = (frame["label"] == "scam").astype(int).to_numpy()
    model = make_pipeline(
        make_union(TfidfVectorizer(ngram_range=(1, 2), min_df=2, sublinear_tf=True),
                   TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 5), min_df=3, sublinear_tf=True)),
        LogisticRegression(C=10, solver="liblinear", max_iter=1000),
    )
    return cross_val_predict(model, frame["text"], y, cv=StratifiedKFold(folds, shuffle=True, random_state=seed),
                             method="decision_function")


def rule_flag(text: str, label: str) -> bool:
    """A *safe* message that combines urgency/threat wording with a link or phone number.

    Works on raw text (real-looking links and numbers) as well as already-masked text: the
    project's own masker turns them into ``<URL>`` / ``<PHONE>`` first.
    """
    if label != "safe" or not _URGENCY_RE.search(text):
        return False
    masked, _ = mask_text(text)
    return bool(re.search(r"<URL>|<PHONE>", masked))


# --------------------------------------------------------------------------- #
# Triage
# --------------------------------------------------------------------------- #
def build_triage(
    frame: pd.DataFrame, judgements: dict[str, dict[str, str]], oof: np.ndarray,
    control_size: int = CONTROL_SIZE, seed: int = 0,
) -> pd.DataFrame:
    """Rows to review, with the reasons they were flagged, plus a random control sample.

    Columns added: ``oof``, ``judge`` (verdict), ``judge_model``, ``reasons`` (comma-separated
    from ``oof``, ``rule``, ``judge``, ``control``). A row is flagged if the out-of-fold model
    disagrees with its label, the rule fires, or the judge says the opposite class or ``unsure``.
    """
    df = frame.copy()
    df["oof"] = oof
    df["judge"] = df["row_id"].map(lambda r: judgements.get(r, {}).get("verdict", "unjudged"))
    df["judge_model"] = df["row_id"].map(lambda r: judgements.get(r, {}).get("judge", ""))
    scam = df["label"] == "scam"
    flags = pd.DataFrame({
        "oof": (scam & (df["oof"] < 0)) | (~scam & (df["oof"] > 0)),
        "rule": [rule_flag(t, l) for t, l in zip(df["text"], df["label"])],
        "judge": df["judge"].isin(["unsure"]) | (scam & (df["judge"] == "safe")) | (~scam & (df["judge"] == "scam")),
    })
    df["reasons"] = flags.apply(lambda r: ",".join(k for k, v in r.items() if v), axis=1)
    flagged = df[df["reasons"] != ""]
    rest = df[df["reasons"] == ""]
    control = rest.sample(min(control_size, len(rest)), random_state=seed).assign(reasons="control")
    return pd.concat([flagged, control]).sort_values(["reasons", "row_id"]).reset_index(drop=True)


# --------------------------------------------------------------------------- #
# Decisions
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Decision:
    """One reviewer decision."""

    row_id: str
    action: str        # keep | flip | remove
    reason: str


def validate_decisions(decisions: list[Decision], known_ids: set[str]) -> None:
    """Raise ``ValueError`` on unknown actions or ids, or duplicate ids."""
    seen: set[str] = set()
    for d in decisions:
        if d.action not in DECISIONS:
            raise ValueError(f"unknown action {d.action!r} for {d.row_id}")
        if d.row_id not in known_ids:
            raise ValueError(f"unknown row_id {d.row_id}")
        if d.row_id in seen:
            raise ValueError(f"duplicate decision for {d.row_id}")
        seen.add(d.row_id)


def apply_decisions(frame: pd.DataFrame, decisions: list[Decision]) -> pd.DataFrame:
    """Return the audited frame: flipped labels applied, removed rows dropped.

    Adds ``original_label`` and ``audit_action`` (``unreviewed`` for rows never reviewed).
    A flipped row gets a consistent ``scam_type``: ``unknown`` when it becomes scam (its
    original scam type is unreliable), ``none`` when it becomes safe.
    """
    validate_decisions(decisions, set(frame["row_id"]))
    by_id = {d.row_id: d for d in decisions}
    out = frame.copy()
    out["original_label"] = out["label"]
    out["audit_action"] = out["row_id"].map(lambda r: by_id[r].action if r in by_id else "unreviewed")
    flip = out["audit_action"] == "flip"
    out.loc[flip, "label"] = out.loc[flip, "original_label"].map({"scam": "safe", "safe": "scam"})
    out.loc[flip & (out["label"] == "safe"), "scam_type"] = "none"
    # A safe row flipped to scam keeps the topic it was written about when it is a known scam type.
    to_scam = flip & (out["label"] == "scam")
    out.loc[to_scam, "scam_type"] = [t if t in gs.SYNTHETIC_SCAM_TYPES else "unknown" for t in out.loc[to_scam, "topic"]]
    return out[out["audit_action"] != "remove"].reset_index(drop=True)


def summarize_decisions(frame: pd.DataFrame, decisions: list[Decision]) -> dict:
    """Counts of keep/flip/remove overall and by original label, plus how many rows were reviewed."""
    by_id = {d.row_id: d.action for d in decisions}
    tab = frame.assign(action=frame["row_id"].map(by_id).fillna("unreviewed"))
    counts = tab.groupby(["label", "action"]).size().unstack(fill_value=0)
    return {
        "rows": len(frame), "reviewed": len(decisions),
        "by_action": {a: int((tab["action"] == a).sum()) for a in (*DECISIONS, "unreviewed")},
        "by_original_label": {lab: {a: int(counts.loc[lab, a]) if a in counts.columns else 0 for a in counts.columns}
                              for lab in counts.index},
    }


# --------------------------------------------------------------------------- #
# Blind review sample for the human spot check
# --------------------------------------------------------------------------- #
def export_review_sample(
    frame: pd.DataFrame, decisions: list[Decision], directory: Path, n: int = 30, seed: int = 0,
) -> tuple[Path, Path]:
    """Write a *blind* CSV for the human reviewer and a separate key with the assistant's decisions.

    The CSV shows only ``row_id``, ``text``, ``original_label`` and empty ``my_decision`` /
    ``notes`` columns. Sampling is random, stratified by decision so that flips and removals are
    represented (up to ``n // 3`` each, the rest filled from ``keep``).

    Returns:
        ``(review_csv_path, key_csv_path)``.
    """
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    known = frame.set_index("row_id")
    rng = np.random.default_rng(seed)
    picked: list[Decision] = []
    per = n // 3
    for action in ("flip", "remove", "keep"):
        pool = [d for d in decisions if d.action == action]
        take = min(per if action != "keep" else n - len(picked), len(pool))
        picked += [pool[i] for i in rng.choice(len(pool), size=take, replace=False)] if take else []
    leftover = [d for d in decisions if d not in picked]
    if len(picked) < n and leftover:
        picked += [leftover[i] for i in rng.choice(len(leftover), size=min(n - len(picked), len(leftover)), replace=False)]
    order = rng.permutation(len(picked))
    picked = [picked[i] for i in order]
    review = pd.DataFrame({
        "row_id": [d.row_id for d in picked],
        "text": [known.loc[d.row_id, "text"] for d in picked],
        "original_label": [known.loc[d.row_id, "label"] for d in picked],
        "my_decision": "", "notes": "",
    })
    key = pd.DataFrame({"row_id": review["row_id"], "assistant_decision": [d.action for d in picked],
                        "assistant_reason": [d.reason for d in picked]})
    review_path, key_path = directory / "review_sample_30.csv", directory / "review_sample_30_key.csv"
    review.to_csv(review_path, index=False, encoding="utf-8-sig")
    key.to_csv(key_path, index=False, encoding="utf-8")
    return review_path, key_path


def read_review_csv(path: Path) -> pd.DataFrame:
    """Read a review CSV, tolerating a spreadsheet-added generic header row and a UTF-8 BOM.

    Spreadsheet tools sometimes prepend ``Column1,Column2,...`` above the real header; that row
    is skipped so the columns keep their names.
    """
    frame = pd.read_csv(path, dtype=str, keep_default_na=False, encoding="utf-8-sig")
    if list(frame.columns)[:2] == ["Column1", "Column2"]:
        frame = pd.read_csv(path, dtype=str, keep_default_na=False, encoding="utf-8-sig", skiprows=1)
    return frame


def agreement(review_csv: Path, key_csv: Path) -> dict:
    """Compare the human ``my_decision`` column with the assistant's decisions.

    Accepts ``keep``, ``flip`` and ``remove`` (case-insensitive). Rows left blank are ignored, and
    ``answered`` reports how many rows had a valid answer.
    """
    review, key = read_review_csv(review_csv), pd.read_csv(key_csv, dtype=str)
    merged = review.merge(key, on="row_id")
    merged["mine"] = merged["my_decision"].str.strip().str.lower()
    answered = merged[merged["mine"].isin(DECISIONS)]
    same = answered["mine"] == answered["assistant_decision"]
    return {"answered": len(answered), "agree": int(same.sum()),
            "agreement": float(same.mean()) if len(answered) else float("nan"),
            "disagreements": answered[~same][["row_id", "text", "original_label", "mine", "assistant_decision",
                                              "assistant_reason"]].to_dict("records")}


def merge_overrides(draft: list[Decision], overrides: list[Decision]) -> list[Decision]:
    """Final decisions: the draft, with each override replacing (or adding to) the draft row.

    Overrides record the owner's rulings from the spot check and the same rules applied to
    the rest of the draft; rows the draft never reviewed can be added this way.
    """
    merged = {d.row_id: d for d in draft}
    merged.update({d.row_id: d for d in overrides})
    return list(merged.values())


def save_decisions(decisions: list[Decision], path: Path) -> None:
    """Persist decisions as CSV (``row_id, action, reason``)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([d.__dict__ for d in decisions]).to_csv(path, index=False, encoding="utf-8")


def load_decisions(path: Path) -> list[Decision]:
    """Read decisions written by :func:`save_decisions`."""
    return [Decision(r.row_id, r.action, r.reason) for r in pd.read_csv(path, dtype=str, keep_default_na=False).itertuples()]


def main(argv: list[str] | None = None) -> int:
    """CLI: ``judge`` (blind LLM judging), ``triage`` (build the review list) or ``finalize`` (apply decisions)."""
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["judge", "triage", "finalize"])
    parser.add_argument("--raw", type=Path, default=gs.DEFAULT_OUTPUT)
    parser.add_argument("--audit-dir", type=Path, default=AUDIT_DIR)
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.WARNING)
    frame = load_audit_frame(args.raw)
    if args.action == "finalize":
        final = merge_overrides(load_decisions(args.audit_dir / "decisions_draft.csv"), load_decisions(OVERRIDES_PATH))
        save_decisions(final, args.audit_dir / "decisions_final.csv")
        audited = apply_decisions(frame, final)
        AUDITED_PATH.parent.mkdir(parents=True, exist_ok=True)
        audited.to_parquet(AUDITED_PATH, index=False)
        print(json.dumps(summarize_decisions(frame, final), indent=1))
        print(f"audited rows: {len(audited)} -> {AUDITED_PATH}")
        return 0
    judge_path = args.audit_dir / "judge.jsonl"
    if args.action == "judge":
        clients = gs.build_clients("both")
        if not clients:
            print("No API keys found. Set GROQ_API_KEY and/or GEMINI_API_KEY in .env.")
            return 2
        judgements = judge_rows(frame, clients, judge_path)
        print(f"judged {len(judgements)} of {len(frame)} rows")
        return 0
    store = gs.ProgressStore(judge_path)
    judgements = {rid: {"verdict": v, "judge": rec["judge"]}
                  for rec in store.read_records() for rid, v in zip(rec["row_ids"], rec["verdicts"])}
    triage = build_triage(frame, judgements, oof_scores(frame, seed=args.seed), seed=args.seed)
    args.audit_dir.mkdir(parents=True, exist_ok=True)
    triage.to_csv(args.audit_dir / "triage.csv", index=False, encoding="utf-8")
    print(f"triage rows: {len(triage)} ({(triage.reasons != 'control').sum()} flagged + {(triage.reasons == 'control').sum()} control)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
