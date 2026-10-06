"""Build (and, only when explicitly told to, upload) the audited synthetic dataset for Hugging Face.

The default is a **dry run**: it writes a release folder (data file, audit decisions, rubric and the
dataset card) and prints what would be uploaded, with no network access. Uploading needs both
``--upload`` and ``--yes`` and reads the write token from the ``HF_TOKEN`` environment variable
(``.env``); the token is never printed or written anywhere.

    python -m src.preprocessing.publish_synthetic                       # dry run
    python -m src.preprocessing.publish_synthetic --upload --yes        # upload (after review)
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
from pathlib import Path

import pandas as pd

from src.preprocessing import generate_synthetic as gs
from src.preprocessing import label_audit as la

DEFAULT_REPO = "Ridham115/indian-scam-sms-synthetic-audited"
AUDITED = la.AUDITED_PATH
RELEASE_DIR = Path("data/synthetic/hf_release")
CARD_PATH = Path("docs/synthetic_dataset_card.md")
RUBRIC_PATH = Path("docs/label_rubric.md")
COLUMNS = ["row_id", "text", "label", "original_label", "scam_type", "language", "generator", "topic", "audit_action"]
_TOKEN_PATTERNS = re.compile(r"gsk_[A-Za-z0-9]{10,}|hf_[A-Za-z0-9]{10,}|AIza[0-9A-Za-z_\-]{20,}|KGAT[_A-Za-z0-9]{10,}")


def release_frame(audited: pd.DataFrame) -> pd.DataFrame:
    """The columns that are published (no internal ``source``/``family`` bookkeeping)."""
    return audited[COLUMNS].reset_index(drop=True)


def collect_stats(audited: pd.DataFrame, raw_jsonl: Path = gs.DEFAULT_OUTPUT,
                  audit_dir: Path = la.AUDIT_DIR) -> dict:
    """Every number that appears in the dataset card, computed from the files."""
    records = gs.ProgressStore(raw_jsonl).read_records()
    frame = la.load_audit_frame(raw_jsonl)
    final = la.load_decisions(audit_dir / "decisions_final.csv")
    draft = {d.row_id: d.action for d in la.load_decisions(audit_dir / "decisions_draft.csv")}
    triage = pd.read_csv(audit_dir / "triage.csv")
    by_gen = audited.groupby(["generator", "label"]).size().unstack(fill_value=0)
    orig = {r: a for r, a in zip(frame["row_id"], frame["label"])}
    flips = [d for d in final if d.action == "flip"]
    return {
        "raw_batches": len(records),
        "raw_messages": sum(len(r["messages"]) for r in records),
        "kept_after_generator_filters": len(frame),
        "rows": len(audited),
        "label": audited["label"].value_counts().to_dict(),
        "original_label": audited["original_label"].value_counts().to_dict(),
        "by_generator": {g: {k: int(v) for k, v in row.items()} for g, row in by_gen.iterrows()},
        "by_language": audited["language"].value_counts().to_dict(),
        "by_topic": {t: {k: int(v) for k, v in row.items()} for t, row in audited.groupby("topic")["label"].value_counts().unstack(fill_value=0).iterrows()},
        "audit_action": audited["audit_action"].value_counts().to_dict(),
        "reviewed": len(final),
        "removed": sum(d.action == "remove" for d in final),
        "flipped": len(flips),
        "flipped_safe_to_scam": sum(orig[d.row_id] == "safe" for d in flips),
        "flipped_scam_to_safe": sum(orig[d.row_id] == "scam" for d in flips),
        "reviewed_in_draft": len(draft),
        "added_by_rule_scan": sum(d.row_id not in draft for d in final),
        "kept_in_draft_then_removed": sum(draft.get(d.row_id) == "keep" and d.action == "remove" for d in final),
        "triage_rows": int((triage["reasons"] != "control").sum()),
        "control_rows": int((triage["reasons"] == "control").sum()),
        "length_chars": {k: float(v) for k, v in audited["text"].str.len().describe().round(1).items()
                         if k in ("min", "50%", "mean", "max")},
    }


CARD = """---
license: cc-by-4.0
language:
- en
- hi
- ta
- te
- bn
- mr
pretty_name: Indian Scam SMS (synthetic, audited)
size_categories:
- 1K<n<10K
task_categories:
- text-classification
tags:
- scam-detection
- phishing
- sms
- code-mixed
- hinglish
- synthetic
configs:
- config_name: default
  data_files:
  - split: train
    path: data/synthetic_audited.csv
---

# Indian Scam SMS (synthetic, audited)

{rows:,} short messages that imitate SMS and WhatsApp scams and their **genuine look-alikes** in Indian
English, Hindi (Devanagari), Hinglish and four Roman-script code-mixed styles (Tamil, Telugu, Bengali,
Marathi with English). Every row was written by a large language model and then audited for label noise.
It exists to train and stress-test scam detectors on the *hard negatives* that public datasets lack:
real-looking bank, courier, bill and job messages that are **not** scams.

**This is synthetic data. Do not use it to estimate real-world accuracy.** Evaluate on real messages.

## Fields

| Field | Meaning |
|---|---|
| `row_id` | 12-character SHA-1 prefix of the original generated text (stable key for the audit) |
| `text` | The message |
| `label` | `scam` or `safe` after the audit |
| `original_label` | The label the generator was asked for, before the audit |
| `scam_type` | `fake_kyc`, `lottery`, `courier_customs`, `job_offer`, `electricity_bill`, `loan_offer`, `fake_bank_otp`, `unknown` (a row flipped to scam) or `none` |
| `language` | Requested style: `hinglish`, `en`, `hi`, `ta_en`, `te_en`, `bn_en`, `mr_en` |
| `generator` | `provider/model` that wrote the row |
| `topic` | The category the generator was asked to write (for `safe` rows, the genuine counterpart of a scam type, or `everyday`) |
| `audit_action` | `keep`, `flip` (label changed) or `unreviewed` (see below) |

## Composition

- **Labels:** {label_scam:,} scam, {label_safe:,} safe.
- **Generators:** {generators}.
- **Languages:** {languages}.
- **Topics (scam / safe):** {topics}.
- **Length:** median {median:.0f} characters (min {min_len:.0f}, max {max_len:.0f}).

## How it was made

1. **Generation.** Prompts asked for batches of 10 messages of one *(label, topic, language)*. Scam batches
   cover seven scam types; safe batches ask for the genuine counterpart (for example a real bank OTP
   alert or an electricity-bill reminder) or ordinary everyday messages. Regional code-mixed styles were
   routed to Gemini only, because a pilot showed Groq's model wrote plain English for them. Prompts forbid
   placeholder-looking numbers and require invented phone numbers and domains in scam rows.
   {raw_batches} batches produced {raw_messages:,} messages.
2. **Generator-side filters.** Length outside 15-700 characters, placeholder-looking numbers, script or
   style mismatch (for example Hinglish written in Devanagari) and exact duplicates removed
   {filtered_out:,} messages, leaving {kept:,}.
3. **Label-noise audit.** LLMs often make "genuine" messages read like scams (and the reverse), so every
   row was screened by three automatic signals: a blind judge from the *other* provider (the judge never
   saw the requested label), an out-of-fold TF-IDF classifier that disagreed with the label, and a rule that
   flags "safe" messages combining urgency with a link or phone number. {triage_rows} flagged rows and
   {control_rows} random unflagged control rows were then read one by one against the written rubric
   (`label_rubric.md`) and marked **keep**, **flip** or **remove** (ambiguous: dropped).
4. **Hard-negative rules.** A safe message must not link a bank, government or retailer domain that does not
   fit the message (for example a loan offer on `uidai.gov.in`) and must not tell the reader to act on an OTP
   (enter, use, verify or keep one ready, or hand it to a courier). These rules were written down after
   review of a 30-row sample and then applied to *every* safe row by a script
   (`safe_rule_violations` in the code repository); {added_by_rule_scan} further rows were removed or
   flipped that way.
5. **Result.** {reviewed} rows were reviewed by hand or by a rule, {removed} were removed and {flipped}
   were flipped ({flip_safe_scam} safe to scam, {flip_scam_safe} scam to safe). The original label of
   every row is kept in `original_label`.

## Quality and known problems

- **Who labelled.** The audit decisions were made by an AI assistant (Claude) following the rubric, not by
  human annotators. The dataset author was shown a 30-row sample without the assistant's decisions, but
  examined only two of those rows closely (most answers were defaults given without close reading) and then
  ruled on the disputed cases. The human check was therefore **partial, not a full blind check**, and
  **no agreement rate is reported**; none should be inferred.
- **Most rows were not read.** {unreviewed:,} of {rows:,} rows are `unreviewed`: no signal flagged them and
  nobody read them; only the hard-negative rules were applied to them. In the first review pass none of the
  100 random control rows needed a label change, which suggests but does not prove that label noise among the
  unflagged rows is small. That pass predates the hard-negative rules, which later removed
  {rule_removed_kept} rows the pass had kept. Expect some mislabelled rows.
- **Shortcuts.** Scam rows use invented domains and phone numbers, safe rows use real official domains.
  A model can learn "known brand domain means safe", which fails against real phishing on look-alike
  domains. Language style, topic and sentence templates also correlate with the label.
- **Language quality.** Regional code-mixed text was written by models and not checked by native
  speakers. Marathi, Bengali, Tamil and Telugu rows may be unnatural.
- **Not real traffic.** Real scams are messier, shorter or longer, and change over time.

## Intended use

Training and stress-testing scam or phishing classifiers as a *supplement* to real data, studying
hard negatives, and evaluating label-noise methods. Not for evaluating deployed systems, and not for
producing convincing scams: phone numbers and domains are invented, and nothing here is a template
for real-world fraud.

## License and terms

The dataset is released under **CC BY 4.0**. The messages were generated with third-party model APIs
(Groq-hosted `openai/gpt-oss-120b` and Google Gemini models, see `generator` per row). Those providers'
terms apply to their outputs and may restrict some uses, for example using Gemini outputs to develop
models that compete with Gemini. **CC BY 4.0 does not override those terms; you are responsible for
checking them for your use.** Filter on `generator` if you need to exclude one provider's rows.

## Citation

If you use this dataset, please link the repository and the AI Scam & Phishing Message Detector
project that produced it.
"""


def render_card(stats: dict) -> str:
    """Fill the card template with real numbers from :func:`collect_stats`."""
    gens = "; ".join(f"`{g}` ({v.get('scam', 0) + v.get('safe', 0):,} rows)" for g, v in stats["by_generator"].items())
    langs = ", ".join(f"`{k}` {v:,}" for k, v in stats["by_language"].items())
    topics = ", ".join(f"`{t}` {v.get('scam', 0)} / {v.get('safe', 0)}" for t, v in stats["by_topic"].items())
    return CARD.format(
        rows=stats["rows"], label_scam=stats["label"].get("scam", 0), label_safe=stats["label"].get("safe", 0),
        generators=gens, languages=langs, topics=topics,
        median=stats["length_chars"]["50%"], min_len=stats["length_chars"]["min"], max_len=stats["length_chars"]["max"],
        raw_batches=stats["raw_batches"], raw_messages=stats["raw_messages"], kept=stats["kept_after_generator_filters"],
        filtered_out=stats["raw_messages"] - stats["kept_after_generator_filters"],
        triage_rows=stats["triage_rows"], control_rows=stats["control_rows"],
        added_by_rule_scan=stats["added_by_rule_scan"], reviewed=stats["reviewed"], removed=stats["removed"],
        flipped=stats["flipped"], flip_safe_scam=stats["flipped_safe_to_scam"], flip_scam_safe=stats["flipped_scam_to_safe"],
        unreviewed=stats["audit_action"].get("unreviewed", 0), rule_removed_kept=stats["kept_in_draft_then_removed"],
    )


def build_release(release_dir: Path = RELEASE_DIR, audited_path: Path = AUDITED, card_path: Path = CARD_PATH) -> dict:
    """Write the release folder and the card; return the stats. No network access."""
    audited = pd.read_parquet(audited_path)
    stats = collect_stats(audited)
    release_dir = Path(release_dir)
    if release_dir.exists():
        shutil.rmtree(release_dir)
    (release_dir / "data").mkdir(parents=True)
    release_frame(audited).to_csv(release_dir / "data" / "synthetic_audited.csv", index=False, encoding="utf-8")
    shutil.copy(la.AUDIT_DIR / "decisions_final.csv", release_dir / "audit_decisions.csv")
    shutil.copy(RUBRIC_PATH, release_dir / "label_rubric.md")
    card = render_card(stats)
    (release_dir / "README.md").write_text(card, encoding="utf-8")
    card_path.parent.mkdir(parents=True, exist_ok=True)
    card_path.write_text(card, encoding="utf-8")
    (release_dir / "stats.json").write_text(json.dumps(stats, indent=1, default=str), encoding="utf-8")
    return stats


def scan_for_secrets(release_dir: Path) -> list[str]:
    """Files in the release folder that contain something that looks like an API key or token."""
    return [str(p) for p in Path(release_dir).rglob("*")
            if p.is_file() and _TOKEN_PATTERNS.search(p.read_text(encoding="utf-8", errors="ignore"))]


def upload(release_dir: Path, repo_id: str) -> str:
    """Upload the release folder to an existing dataset repo. Needs ``HF_TOKEN``; returns the repo URL."""
    token = os.getenv("HF_TOKEN")
    if not token:
        raise RuntimeError("HF_TOKEN is not set (put a write-scoped token in .env)")
    leaked = scan_for_secrets(release_dir)
    if leaked:
        raise RuntimeError(f"refusing to upload: secret-like strings found in {leaked}")
    from huggingface_hub import HfApi

    api = HfApi(token=token)
    api.upload_folder(folder_path=str(release_dir), repo_id=repo_id, repo_type="dataset",
                      commit_message="Add audited synthetic Indian scam SMS dataset")
    return f"https://huggingface.co/datasets/{repo_id}"


def main(argv: list[str] | None = None) -> int:
    """CLI (dry run by default)."""
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--repo", default=DEFAULT_REPO)
    parser.add_argument("--upload", action="store_true", help="really upload (also needs --yes)")
    parser.add_argument("--yes", action="store_true", help="confirm the upload")
    args = parser.parse_args(argv)
    stats = build_release()
    files = sorted(str(p.relative_to(RELEASE_DIR)) for p in RELEASE_DIR.rglob("*") if p.is_file())
    print(f"release folder: {RELEASE_DIR}  ({stats['rows']:,} rows)\nfiles: {files}\ncard: {CARD_PATH}")
    leaked = scan_for_secrets(RELEASE_DIR)
    print("secret scan:", "clean" if not leaked else f"FOUND in {leaked}")
    if not (args.upload and args.yes):
        print("DRY RUN: nothing was uploaded. Add --upload --yes to publish after reviewing the card.")
        return 1 if leaked else 0
    from dotenv import load_dotenv

    load_dotenv()
    print("uploaded:", upload(RELEASE_DIR, args.repo))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
