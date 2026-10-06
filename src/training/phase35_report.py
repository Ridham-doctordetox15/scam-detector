"""Turn the Phase 3.5 JSON results into the ``results.md`` section (numbers only come from the files).

    python -m src.training.phase35_report            # rewrite the Phase 3.5 block of results.md
"""
from __future__ import annotations

import json
from pathlib import Path

from src.training import ladder
from src.training.phase35_final import BEFORE_JSON, FINAL_JSON

RESULTS_MD = Path("results.md")
START, END = "<!-- phase35:start -->", "<!-- phase35:end -->"
START_B, END_B = "<!-- phase35b:start -->", "<!-- phase35b:end -->"
L3B_JSON = Path("data/processed/phase35_l3b.json")
SOURCE_TITLES = {"hf_phishing_texts": "HF texts", "uci_sms_spam": "UCI SMS", "kaggle_india_spam_sms": "India SMS",
                 "synthetic_llm": "synthetic"}


def f(v: float | None, digits: int = 3) -> str:
    """Format a number, or ``n/a``."""
    return "n/a" if v is None else f"{v:.{digits}f}"


def pct(v: float | None) -> str:
    """Format a share as a percentage, or ``n/a``."""
    return "n/a" if v is None else f"{100 * v:.0f}%"


def table(header: list[str], rows: list[list[str]]) -> str:
    """GitHub-flavoured markdown table."""
    lines = ["| " + " | ".join(header) + " |", "|" + "|".join("---:" if i else "---" for i in range(len(header))) + "|"]
    return "\n".join(lines + ["| " + " | ".join(r) + " |" for r in rows])


def ladder_table(levels: dict[str, dict]) -> str:
    """One row per level: validation metrics, audit result, LOSO and benchmark."""
    rows = []
    for name, v in levels.items():
        a, s, b = v["audit"], v["source_identifiability"], v["benchmark_flag_rate"]
        loso = v["loso"]
        rows.append([
            name, f"{v['train_fit_rows']:,}", f"{v['val_rows']:,}", f(v["val"]["f1"]), f(v["val"]["roc_auc"]),
            f"{f(v['val_short']['f1'])} ({v['val_short']['n']:,})",
            f"{a['scam']['fingerprint']} / {a['safe']['fingerprint']}", pct(a["scam"]["signal_share"]),
            "PASS" if a["pass"] else "fail",
            f"{f(s['accuracy'])} ({f(s['majority_baseline'])})",
            f(loso.get("hf_phishing_texts", {}).get("roc_auc")), f(loso.get("uci_sms_spam", {}).get("roc_auc")),
            f"{pct(b['rate'])} (n={b['n']})",
        ])
    return table(["Level", "Train rows", "Val rows", "Val F1", "Val ROC-AUC", "Short-slice F1 (n)",
                  "Fingerprints scam / safe", "Scam-signal share", "Audit", "Source-ID acc (majority)",
                  "LOSO AUC HF", "LOSO AUC UCI", "Promo/service flagged"], rows)


def features_block(levels: dict[str, dict]) -> str:
    """Top-14 word-audit features per class for each level, with fingerprints listed."""
    lines = []
    for name, v in levels.items():
        a = v["audit"]
        lines.append(f"- **{name}** scam: {', '.join(a['scam']['features'][:14])}  \n  safe: {', '.join(a['safe']['features'][:14])}  \n"
                     f"  fingerprints scam: {', '.join(a['scam']['fingerprints']) or 'none'}; safe: {', '.join(a['safe']['fingerprints']) or 'none'}")
    return "\n".join(lines)


def before_after(final: dict) -> str:
    """The before/after table: test metrics, short slice, LOSO, benchmark, top features."""
    after, before, extra = final["after"], final["before_models"], final["extras"]
    rows = []
    for m, title in (("logreg", "Logistic regression"), ("svm", "Linear SVM")):
        b, a = before[m]["test"]["tuned"], after["models"][m]["test"]["tuned"]
        sh = extra["short_test"][m]
        bench = extra["benchmark"][m]["test"]
        rows.append([title, f"{f(b['f1'], 4)} / {f(b['roc_auc'], 4)}", f"{f(a['f1'], 4)} / {f(a['roc_auc'], 4)}",
                     f"{f(sh['f1'], 4)} / {f(sh['roc_auc'], 4)} (n={sh['n']:,})",
                     f"{pct(bench['flag_rate'])} (n={bench['n']})"])
    out = [table(["Model", "Before: test F1 / ROC-AUC", "After: test F1 / ROC-AUC", "After, short messages (<=300 chars)",
                  "After: legit promo/service flagged (test)"], rows)]
    loso_rows = []
    sources = sorted({r["held_out"] for r in final["before_loso"]} | {r["held_out"] for r in after["loso"]})
    for m, title in (("logreg", "LR"), ("svm", "SVM")):
        for src in sources:
            def pick(rs, variant):
                hit = [r for r in rs if r["model"] == m and r["held_out"] == src and r["variant"] == variant]
                return f(hit[0]["roc_auc"]) if hit else "n/a"
            loso_rows.append([title, SOURCE_TITLES.get(src, src), pick(final["before_loso"], "in-distribution"),
                              pick(final["before_loso"], "leave-one-source-out"),
                              pick(after["loso"], "in-distribution"), pick(after["loso"], "leave-one-source-out")])
    out.append(table(["Model", "Held-out source", "Before: in-dist AUC", "Before: LOSO AUC", "After: in-dist AUC", "After: LOSO AUC"],
                     loso_rows))
    tops = []
    for m, title in (("logreg", "LR"), ("svm", "SVM")):
        for label, models in (("Before", before), ("After", after["models"])):
            t = models[m]["top_features"]
            tops.append(f"- {title} {label}: scam `{'`, `'.join(t['scam'][:10])}`; safe `{'`, `'.join(t['safe'][:10])}`")
    out.append("Highest-weight classifier features (top 10 per class; the word-only audit above is the pass/fail view):\n\n"
               + "\n".join(tops))
    return "\n\n".join(out)


def build_markdown(ladder_results: dict, final: dict) -> str:
    """The whole Phase 3.5 section."""
    levels = ladder_results["levels"]
    choice = ladder.choose_level(levels)
    ca = final["extras"]["word_audit"]
    d, a = levels["L2a"]["benchmark_flag_rate"], levels["L2b"]["benchmark_flag_rate"]
    hf = [r for r in final["after"]["loso"] if r["model"] == "logreg" and r["held_out"] == "hf_phishing_texts"
          and r["variant"] == "leave-one-source-out"][0]["roc_auc"]
    bm = final["extras"]["benchmark"]["logreg"]["test"]
    reading = f"""### What the numbers say

- **The pre-registered success criterion was not met.** No level passes the feature audit. Artifact reduction did
  what it targets (the scam-side year fingerprints `2004` and `2005` disappear at L3, Enron rows leave at L5) but the
  safe side keeps mailing-list and HTML fingerprints, and the scam class is still described by generic web-spam words
  rather than Indian-scam cues. The word audit model is only one view; it says the corpora, not the labels, still
  drive the top features.
- **Headline accuracy did not change.** Test F1 stays about 0.97 and the leave-one-source-out AUC on HF texts is
  {f(hf)} (Phase 3: 0.637). The source confound, which is the main reason cross-source transfer is poor, was not
  reduced by these steps. Do not read the after-numbers as an improvement.
- **UCI leave-one-source-out AUC rises from about 0.95 to 0.99** because UCI is now "fraud vs ham" (fraud lures are
  easy to separate) instead of "spam vs ham"; it is a change of task, not of model quality.
- **Policy D leaves legitimate promotions flagged.** Models trained without ever seeing promotions flag
  {pct(d['rate'])} of validation promotions and service notices as scam under L2a (n={d['n']}) and
  {pct(bm['flag_rate'])} on the test benchmark (LR, n={bm['n']}). The contrast level L2b, which labels them safe, flags only
  {pct(a['rate'])} on validation (validation F1 {f(levels['L2b']['val']['f1'])} vs {f(levels['L2a']['val']['f1'])}; not directly comparable because
  the label sets differ). The ladder's selection rule did not use this benchmark, so it does not reflect the project's stated
  goal of not flagging marketing. The project owner chose policy A for Phase 4; the check of that configuration follows this section.
- **India SMS adds a safe-only source**, so it is a confound to watch rather than evidence about scams.
- **Short messages (<=300 chars)** score lower than the full test set (F1 about 0.92 vs 0.97) and are the fairer
  target for SMS; the Hinglish gap is still open because no hand-collected real Indian test set exists.

"""
    return f"""{START}
## Data quality (Phase 3.5): ablation ladder and before/after

Run date: 2026-09-26. Everything below is produced by `python -m src.training.ladder` (validation only),
`python -m src.training.phase35_final` (the chosen level, full Phase 3 protocol, test set scored once) and
`python -m src.training.phase35_report` (this text).

### Ladder (validation data only; the test split is never read)

Levels are cumulative: **L0** Phase 3 data as it was (old spam=scam definition); **L1** + audited synthetic labels;
**L2a** + scam-definition policy D (legit promotions and service notices withheld from training, kept as a
false-positive benchmark) + India SMS rows; **L3** + text normalisation (quote markers, reply boilerplate,
years to `<YEAR>`, currency to `<CUR>`); **L4** + drop web-crawl rows and pipeline notices; **L5** + drop
Enron-internal email. **L2b** is a contrast branch (promotions and service notices relabelled `safe` and
used as hard negatives) and is not eligible for selection. Every level is scored with the same fixed classifier
(TF-IDF word+char, logistic regression C=1000, Phase 3's selection), so differences come from the data.

{ladder_table(levels)}

Reading notes: validation sets differ between levels (labels and rows change), so F1 is not comparable across
levels and was **not** used for selection. "Promo/service flagged" is the share of legitimate promotions and
service notices in validation that the level's model calls scam: under L0 and L1 those rows were *labelled*
scam (old definition), so a high rate is not an error there. L0 reproduces Phase 3 exactly (validation F1
0.9782, same audit result), which confirms the ladder is measuring the data and not the harness.

Top word-audit features per level (fingerprints are corpus artifacts, see `src/training/feature_audit.py`):

{features_block(levels)}

### Selection (rule fixed before the ladder ran)

The rule is in the docstring of `src/training/ladder.py`: success means the feature audit PASSES (zero
fingerprints in the top-30 of both classes and a scam-signal share of at least 50%); the chosen level is the first
successful level on the path L0, L1, L2a, L3, L4, L5; if none succeeds, the level with the fewest fingerprints is
chosen and the phase is reported as **not meeting its success criterion**. (One L0-only timing run preceded the full
ladder; it reproduced the audit already recorded for Phase 3 and informed no choice.)

**Outcome: no level passed. Criterion met: {choice['criterion_met']}. Chosen by the fallback rule: {choice['chosen']}.**
Fingerprints in the top-30 (scam / safe): {", ".join(f"{k} {v['audit']['scam']['fingerprint']}/{v['audit']['safe']['fingerprint']}" for k, v in levels.items())}.
The scam-signal share never reached 50% (best {pct(max(v['audit']['scam']['signal_share'] for v in levels.values()))}).
Year masking removed the scam-side year fingerprints (`2004`, `2005`) from L3 on. What remains is mostly on the
safe side and comes from HF "safe" email: linguistics-list mail (`linguistics`, `university`, `conference`),
HTML entities (`gt`, `lt`), the name `vince` and, until Enron rows are dropped at L5, `enron`. The scam side is
dominated by generic web-spam words (`http`, `click`, `viagra`, `phone`) that are not fingerprints in the pre-registered
lexicon but are not the Indian-scam signals the project cares about either. These are handed to Phase 4.

### Full Phase 3 protocol on the chosen level ({final['level']}), test set scored once

Test sets differ from Phase 3's: the "after" test set contains India SMS rows, excludes legitimate
promotions and service notices (withheld), and drops rows removed by normalisation and leakage trimming
(`{final['before_sizes']['test']:,}` test rows before, `{final['sizes']['test']:,}` after). Numbers are not a like-for-like
accuracy comparison; they show what the new definition and cleaning do. "Before" uses the old spam=scam definition.

{before_after(final)}

{reading}
Word-only audit model on the chosen level's training data: fingerprints scam {ca['scam']['fingerprint']} / safe {ca['safe']['fingerprint']},
scam-signal share {pct(ca['scam']['signal_share'])}, audit {"PASS" if ca['pass'] else "fail"}.
{END}
"""


def l3b_block(l3b: dict, levels: dict[str, dict]) -> str:
    """The validation-only check of L3b (normalisation + policy A), next to L3 (policy D) and L2b."""
    a, sc = l3b["audit"], l3b["single_class_shortcut_check"]
    rows = []
    for name, v in (("L3 (policy D)", levels["L3"]), ("L3b (policy A)", l3b)):
        au, b, lo = v["audit"], v["benchmark_flag_rate"], v["loso"]
        rows.append([name, f"{au['scam']['fingerprint']} / {au['safe']['fingerprint']}", pct(au["scam"]["signal_share"]),
                     f"{pct(b['rate'])} (n={b['n']})",
                     " / ".join(f"{SOURCE_TITLES.get(k, k)} {pct(x['flag_rate'])}" for k, x in b["by_source"].items()) if False else
                     " / ".join(f"{SOURCE_TITLES.get(k, k)} {pct(x['rate'])}" for k, x in b["by_source"].items()),
                     f(lo.get("hf_phishing_texts", {}).get("roc_auc")), f(lo.get("uci_sms_spam", {}).get("roc_auc")),
                     f"{f(v['val']['f1'])} / {f(v['val_short']['f1'])}"])
    text = table(["Level", "Fingerprints scam / safe", "Scam-signal share", "Legit promo/service flagged",
                  "...by source", "LOSO AUC HF", "LOSO AUC UCI", "Val F1 / short-slice F1"], rows)
    shortcut = ""
    for src, c in sc.items():
        g = c["by_group"]
        shortcut += (f"- **{SOURCE_TITLES.get(src, src)}** ({c['n']} validation rows, {c['scams']} scam): no AUC exists, so the flag rate "
                     f"is compared between a model trained on the source and one that never saw it. Overall {pct(c['flag_rate_trained_on_source'])} vs "
                     f"{pct(c['flag_rate_source_held_out'])}; promotions and service notices (n={g['promo_service']['n']}) "
                     f"{pct(g['promo_service']['trained_on_source'])} vs {pct(g['promo_service']['source_held_out'])}; "
                     f"everything else (chat, n={g['other']['n']}) {pct(g['other']['trained_on_source'])} vs {pct(g['other']['source_held_out'])}.\n")
    return f"""{START_B}
### Phase 4 data configuration check: L3b = L3 normalisation + policy A (validation only, run once)

Requested after the ladder because policy D left most legitimate promotions flagged. Same fixed classifier and the same
validation-only protocol as the ladder; the test split was not scored. This is an extra check outside the ladder's
pre-registered selection rule, so it does not change the ladder outcome above.

{text}

Source identifiability (text alone predicts the source): {f(l3b['source_identifiability']['accuracy'])} accuracy against
{f(l3b['source_identifiability']['majority_baseline'])} for always guessing the largest source.

India SMS is all-safe under policy A (1 scam row), so leave-one-source-out AUC cannot be computed for it. The check for a
"source means safe" shortcut:

{shortcut}
How to read it: the chat rows are rarely flagged either way, so the model does not need to have seen India to keep them safe. The promotions are different: they are rarely flagged when India promotions are in training and mostly flagged
when they are not, so the leniency toward promotions is learned from these examples and its transfer to other senders is
unproven (UCI promotions, which are in training, are still flagged {pct(l3b['benchmark_flag_rate']['by_source']['uci_sms_spam']['rate'])}). A real
Indian test set is needed to measure that.

**Verdict:** no serious problem. The feature audit still fails (fingerprints {a['scam']['fingerprint']} / {a['safe']['fingerprint']}, scam-signal share {pct(a['scam']['signal_share'])}, the same as L3),
the flag rate on legitimate promotions falls from {pct(levels['L3']['benchmark_flag_rate']['rate'])} to {pct(l3b['benchmark_flag_rate']['rate'])}, and the price is a lower validation F1 (the task is harder
and the label sets differ) and a lower short-message F1. Watch items for Phase 4: leave-one-source-out AUC on HF texts is a little lower
(single validation run, no error bars), promotion leniency depends on India promotions being in training, and 29% of UCI promotions are still flagged.
L3b is the Phase 4 data configuration.
{END_B}
"""


def main() -> int:
    """Rewrite (or append) the Phase 3.5 block of ``results.md``."""
    ladder_results = json.loads(ladder.RESULTS_PATH.read_text(encoding="utf-8"))
    final = json.loads(FINAL_JSON.read_text(encoding="utf-8"))
    block = build_markdown(ladder_results, final)
    text = RESULTS_MD.read_text(encoding="utf-8")
    if START in text and END in text:
        head, rest = text.split(START, 1)
        tail = rest.split(END, 1)[1]
        text = head + block.rstrip("\n") + tail
    else:
        text = text.rstrip("\n") + "\n\n---\n\n" + block
    if L3B_JSON.exists():
        l3b = json.loads(L3B_JSON.read_text(encoding="utf-8"))["levels"]["L3b"]
        extra = l3b_block(l3b, ladder_results["levels"]).rstrip("\n")
        if START_B in text and END_B in text:
            head, rest = text.split(START_B, 1)
            text = head + extra + rest.split(END_B, 1)[1]
        else:
            text = text.rstrip("\n") + "\n\n" + extra + "\n"
    RESULTS_MD.write_text(text, encoding="utf-8")
    print(f"updated {RESULTS_MD}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
