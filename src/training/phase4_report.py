"""Write the Phase 4 section of ``results.md`` from real run outputs (nothing is typed by hand).

Inputs (all produced by real runs):

* ``phase4_results.json`` and ``test_predictions_<model>.csv`` from the Colab notebook (downloaded from Drive);
* ``models/baseline_phase4/phase4_baseline.json`` and ``test_scores_<model>.csv`` from ``src.training.phase4_baseline``.

    python -m src.training.phase4_report --colab-dir path/to/outputs --update-results results.md

The comparison is paired: both systems are scored on the same test rows (matched by id), and differences carry a paired bootstrap
95% interval. This module reports numbers; interpretation is written by hand afterwards, outside the generated markers.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from src.training import metrics as M

START, END = "<!-- phase4:start -->", "<!-- phase4:end -->"
BASE_START, BASE_END = "<!-- phase4-baseline:start -->", "<!-- phase4-baseline:end -->"
BASELINE_JSON = Path("models/baseline_phase4/phase4_baseline.json")
BASELINE_DIR = BASELINE_JSON.parent
ERROR_DOC = Path("docs/error_analysis_phase4.md")
BASELINE_TITLES = {"logreg": "TF-IDF + Logistic Regression", "svm": "TF-IDF + Linear SVM"}


def f(v: float | None, digits: int = 4) -> str:
    """Format a number, ``n/a`` for None / NaN."""
    return "n/a" if v is None or (isinstance(v, float) and not np.isfinite(v)) else f"{v:.{digits}f}"


def pct(v: float | None) -> str:
    return "n/a" if v is None or (isinstance(v, float) and not np.isfinite(v)) else f"{100 * v:.0f}%"


def table(header: list[str], rows: list[list[str]]) -> str:
    """GitHub markdown table with numeric-looking columns right-aligned."""
    align = ["---:" if i and all(_numeric(r[i]) for r in rows) else "---" for i in range(len(header))]
    lines = ["| " + " | ".join(header) + " |", "|" + "|".join(align) + "|"]
    return "\n".join(lines + ["| " + " | ".join(r) + " |" for r in rows])


def _numeric(text: str) -> bool:
    t = text.replace("%", "").replace("/", "").replace(",", "").replace(" ", "").replace("-", "").replace(".", "")
    return text == "n/a" or t.isdigit()


# --------------------------------------------------------------------------- #
# Paired comparison
# --------------------------------------------------------------------------- #
def paired_bootstrap(y: np.ndarray, score_a: np.ndarray, thr_a: float, score_b: np.ndarray, thr_b: float,
                     n_boot: int = 1000, seed: int = 42) -> dict[str, dict[str, float]]:
    """Difference ``A - B`` in F1, recall and ROC-AUC on the same rows, with a 95% percentile bootstrap interval.

    Returns per metric: ``diff`` (point estimate), ``lo`` / ``hi`` and ``p_a_better`` (share of resamples where A > B).
    """
    y, score_a, score_b = np.asarray(y).astype(int), np.asarray(score_a, float), np.asarray(score_b, float)
    if not (len(y) == len(score_a) == len(score_b)):
        raise ValueError("y and both score arrays must have the same length")
    rng = np.random.default_rng(seed)
    keys = ("f1", "recall", "roc_auc")
    draws = {k: [] for k in keys}
    for _ in range(n_boot):
        idx = rng.integers(0, len(y), len(y))
        a, b = M.binary_metrics(y[idx], score_a[idx], thr_a), M.binary_metrics(y[idx], score_b[idx], thr_b)
        for k in keys:
            draws[k].append(a[k] - b[k])
    point_a, point_b = M.binary_metrics(y, score_a, thr_a), M.binary_metrics(y, score_b, thr_b)
    out = {}
    for k in keys:
        d = np.asarray(draws[k], float)
        out[k] = {"diff": float(point_a[k] - point_b[k]), "lo": float(np.nanpercentile(d, 2.5)),
                  "hi": float(np.nanpercentile(d, 97.5)), "p_a_better": float(np.nanmean(d > 0))}
    return out


# --------------------------------------------------------------------------- #
# Sections
# --------------------------------------------------------------------------- #
def _records(obj) -> list[dict]:
    return obj if isinstance(obj, list) else []


def main_table(colab: dict, base: dict) -> str:
    """Real test set, all systems side by side. Baselines appear at both operating points."""
    rows = []
    for key, point in (("logreg", "recall_first"), ("svm", "recall_first"), ("logreg", "f1_tuned"), ("svm", "f1_tuned")):
        r = base["extras"]["models"][key][point]
        label = f"{BASELINE_TITLES[key]} ({'recall-first threshold' if point == 'recall_first' else 'F1-tuned threshold, Phase 3.5 protocol'})"
        o = r["overall"]
        rows.append([label, f(r["threshold"], 3), f(o["precision"]), f(o["recall"]), f(o["f1"]), f(o["roc_auc"]), f(o["pr_auc"]),
                     f"{o['fp']} / {o['fn']}", f(r["short"]["f1"]), pct(r["benchmark"]["flag_rate"])])
    for key, ev in colab["evaluation"].items():
        o = ev["overall"]
        rows.append([f"**{colab['models'][key]['hf_name']}** (recall-first threshold)", f(ev["threshold"], 3), f(o["precision"]),
                     f(o["recall"]), f(o["f1"]), f(o["roc_auc"]), f(o["pr_auc"]), f"{o['fp']} / {o['fn']}", f(ev["short"]["f1"]),
                     pct(ev["benchmark"]["flag_rate"])])
    return table(["System", "Threshold", "Precision", "Recall", "F1", "ROC-AUC", "PR-AUC", "FP / FN", "Short-message F1", "Promo/service flagged"], rows)


def ci_table(colab: dict) -> str:
    rows = []
    for key, ev in colab["evaluation"].items():
        ci = ev["ci95"]
        rows.append([colab["models"][key]["hf_name"]] + [f"{f(ev['overall'][m])} ({f(ci[m][0])} to {f(ci[m][1])})" for m in
                                                          ("precision", "recall", "f1", "roc_auc")])
    return table(["Model", "Precision (95% CI)", "Recall (95% CI)", "F1 (95% CI)", "ROC-AUC (95% CI)"], rows)


def paired_table(colab: dict, base: dict, colab_dir: Path, baseline_dir: Path, n_boot: int) -> str:
    """Each transformer vs each baseline at its recall-first threshold, on the same rows."""
    rows = []
    for key, ev in colab["evaluation"].items():
        pred = pd.read_csv(Path(colab_dir) / f"test_predictions_{key}.csv")
        for bkey in ("logreg", "svm"):
            other = pd.read_csv(Path(baseline_dir) / f"test_scores_{bkey}.csv")
            merged = pred.merge(other[["id", "score"]], on="id", how="inner")
            if len(merged) != len(pred) or len(merged) != len(other):
                raise ValueError(f"id sets differ between transformer {key} and baseline {bkey}")
            y = (merged["label"].to_numpy() == "scam").astype(int)
            thr_b = base["extras"]["models"][bkey]["thresholds"]["recall_first"]
            res = paired_bootstrap(y, merged["prob"].to_numpy(), ev["threshold"], merged["score"].to_numpy(), thr_b, n_boot)
            rows.append([f"{colab['models'][key]['hf_name']} minus {BASELINE_TITLES[bkey]}"] +
                         [f"{res[m]['diff']:+.4f} ({res[m]['lo']:+.4f} to {res[m]['hi']:+.4f})" for m in ("f1", "recall", "roc_auc")])
    return table(["Comparison (paired, same test rows)", "dF1 (95% CI)", "dRecall (95% CI)", "dROC-AUC (95% CI)"], rows)


def source_table(colab: dict, base: dict) -> str:
    rows = []
    for bkey in ("logreg", "svm"):
        for src, m in base["extras"]["models"][bkey]["recall_first"]["by_source"].items():
            rows.append([BASELINE_TITLES[bkey] + " (recall-first)", src, f"{int(m['n'])}", f"{int(m['n_scam'])}", f(m["precision"]),
                         f(m["recall"]), f(m["f1"]), f(m["fpr"])])
    for key, ev in colab["evaluation"].items():
        for rec in _records(ev["by_source"]):
            rows.append([colab["models"][key]["hf_name"], rec["index"], f"{int(rec['n'])}", f"{int(rec['n_scam'])}", f(rec["precision"]),
                         f(rec["recall"]), f(rec["f1"]), f(rec["fpr"])])
    return table(["System", "Source", "Rows", "Scam rows", "Precision", "Recall", "F1", "FPR"], rows)


def loso_table(colab: dict, base: dict) -> str:
    """Leave-one-source-out: transformer vs baseline on the same held-out rows (baseline uses its F1-tuned threshold, as in Phase 3)."""
    rows = []
    for r in base["protocol"]["loso"]:
        if r["variant"] != "leave-one-source-out":
            continue
        rows.append([BASELINE_TITLES[r["model"]], r["held_out"] + (" (diagnostic only)" if r["diagnostic_only"] else ""), f"{r['eval_rows']}",
                     "n/a", f(r["roc_auc"]), f(r["pr_auc"]), f(r["f1"])])
    in_dist = {(r["model"], r["held_out"]): r["roc_auc"] for r in base["protocol"]["loso"] if r["variant"] == "in-distribution"}
    for row in rows:
        key = next(k for k, t in BASELINE_TITLES.items() if t == row[0])
        row[3] = f(in_dist.get((key, row[1].replace(" (diagnostic only)", ""))))
    for r in colab.get("loso", []):
        rows.append([colab["models"][r["model"]]["hf_name"], r["held_out"] + (" (diagnostic only)" if r["diagnostic_only"] else ""),
                     f"{r['n']}", f(r["in_distribution"]["roc_auc"]), f(r["loso"]["roc_auc"]), f(r["loso"]["pr_auc"]), f(r["loso"]["f1"])])
    return table(["System", "Held-out source", "Rows", "ROC-AUC trained on it", "ROC-AUC never seen", "PR-AUC never seen",
                  "F1 never seen (in-distribution threshold)"], rows)


def tradeoff_table(colab: dict) -> str:
    rows = []
    for key, st in colab["models"].items():
        for op in st["operating_points"]:
            rows.append([st["hf_name"], f(op["recall_target"], 2), f(op["threshold"], 4), f(op["precision"]), f(op["fpr"]), f"{op['fp']} / {op['fn']}",
                         pct(op.get("promo_flag_rate"))])
    return table(["Model", "Recall target", "Threshold", "Precision", "FPR", "FP / FN", "Promo/service flagged"], rows)


def export_table(colab: dict) -> str:
    ex = colab["export"]
    rows = [["ONNX fp32", f(ex["size_mb"]["fp32_onnx"], 1), f(ex["fp32_onnx"]["f1"]), f(ex["fp32_onnx"]["roc_auc"]),
            f(ex["latency_batch1"]["fp32"]["median_ms"], 1), f(ex["latency_batch1"]["fp32"]["p95_ms"], 1),
            f(ex["throughput_seconds_per_1000_msgs"]["fp32"], 1)],
            ["ONNX int8 (dynamic)", f(ex["size_mb"]["int8_onnx"], 1), f(ex["int8_onnx"]["f1"]), f(ex["int8_onnx"]["roc_auc"]),
             f(ex["latency_batch1"]["int8"]["median_ms"], 1), f(ex["latency_batch1"]["int8"]["p95_ms"], 1),
             f(ex["throughput_seconds_per_1000_msgs"]["int8"], 1)]]
    return table(["Graph", "Size (MB)", "Test F1", "Test ROC-AUC", "Median ms (1 msg)", "p95 ms", "Seconds per 1000 msgs (batch 32)"], rows)


def synthetic_and_indian(colab: dict) -> str:
    lines = []
    for key, ev in colab["evaluation"].items():
        d = ev.get("synthetic_val_diagnostic_only") or {}
        o = d.get("overall")
        if o:
            lines.append(f"- {colab['models'][key]['hf_name']}, **diagnostic only**, {o['n']} synthetic validation rows: precision {f(o['precision'])}, "
                         f"recall {f(o['recall'])}, F1 {f(o['f1'])}, FPR {f(o['fpr'])}.")
        if ev.get("real_indian"):
            r = ev["real_indian"]["overall"]
            lines.append(f"- {colab['models'][key]['hf_name']}, real Indian test set ({r['n']} rows): precision {f(r['precision'])}, recall {f(r['recall'])}, F1 {f(r['f1'])}.")
    if colab["data"]["real_indian_test_rows"] is None:
        lines.append("- Real Indian test set: **not built**, so there is no real Hinglish result.")
    return "\n".join(lines)


def error_doc(colab: dict) -> str:
    """Markdown for ``docs/error_analysis_phase4.md``: the 30 sampled test errors, grouped."""
    lines = ["# Phase 4 error analysis (selected model, real test set)", "",
             "Post-hoc: these errors were read after the final score. Nothing was changed because of them. Text is the masked model input.", ""]
    groups: dict[tuple[str, str], list[dict]] = {}
    for e in colab["error_analysis"]:
        groups.setdefault((e["kind"], e["pattern"]), []).append(e)
    for (kind, pattern), items in sorted(groups.items()):
        lines += [f"## {kind}: {pattern} ({len(items)})", ""]
        lines += [f"- `{e['source']}`, p={e['prob']:.3f}: {e['text']}" for e in items]
        lines.append("")
    return "\n".join(lines)


def build_section(colab: dict, base: dict, colab_dir: Path, baseline_dir: Path = BASELINE_DIR, n_boot: int = 1000) -> str:
    """The generated block for results.md (between the phase4 markers)."""
    cfg, data = colab["config"], colab["data"]
    thr = ", ".join(f"{colab['models'][k]['hf_name']} {f(v['threshold'], 4)}" for k, v in colab["evaluation"].items())
    mit = colab["mitigation"]
    fired = [k for k, v in mit["fired"].items() if v]
    return "\n".join([
        START,
        "## Transformer fine-tuning (Phase 4)",
        "",
        f"Data configuration L3b (L3 normalisation + policy A). Train {data['train_rows']:,} / validation {data['val_rows']:,} "
        f"({data['val_real_rows']:,} real + {data['val_synthetic_rows']:,} synthetic) / test {data['test_rows']:,} rows "
        f"(real only, {100 * data['test_scam_rate']:.1f}% scam, {data['test_benchmark_rows']} legitimate promotion/service rows). "
        f"Trained on Colab ({cfg['device']}, torch {cfg['torch']}, transformers {cfg['transformers']}), seed {cfg['seed']}, "
        f"max {cfg['max_epochs']} epochs with early stopping (patience {cfg['patience']}) on real-validation PR-AUC, class-weighted loss, "
        f"max length {cfg['max_length']}. Decision threshold = highest threshold with recall >= {cfg['recall_target']} on real validation "
        f"scams: {thr}. Model exported: **{colab['export']['model_name']}** (chosen by real-validation PR-AUC before the test set was scored).",
        "",
        "### Real test set, all systems (scam = positive)",
        "",
        "Baselines were re-run on the same L3b data (`src/training/phase4_baseline.py`), so this is like for like. The Phase 3.5 numbers in the "
        "section above belong to L3 (policy D) on a different test set and are **not** comparable. Recall-first rows use the same "
        f"rule and target as the transformers.",
        "",
        main_table(colab, base),
        "",
        "95% bootstrap intervals for the transformers:",
        "",
        ci_table(colab),
        "",
        "Paired difference on the same test rows (positive = transformer better):",
        "",
        paired_table(colab, base, colab_dir, baseline_dir, n_boot),
        "",
        "### By source (recall-first threshold)",
        "",
        source_table(colab, base),
        "",
        "### Leave-one-source-out",
        "",
        "Each model is retrained without the source and scored on it. Baseline: Phase 3 protocol (its F1-tuned in-distribution threshold). "
        f"Transformers: at most {cfg['loso_max_epochs']} epochs per run, in-distribution recall-first threshold. Synthetic rows are validation rows "
        "(the test set has none) and are diagnostic only.",
        "",
        loso_table(colab, base),
        "",
        f"Mitigation trigger (HF LOSO ROC-AUC below {mit['trigger']['loso_auc_below']} or gap above {mit['trigger']['gap_above']}): "
        + (f"**fired** for {', '.join(fired)}; a source-adversarial proposal is waiting for the owner's decision, and nothing was run."
           if fired else "not fired for any model that ran LOSO."),
        "",
        "### Recall-first trade-off (real validation rows only; not used to pick anything but the 0.97 row)",
        "",
        tradeoff_table(colab),
        "",
        "### Diagnostic and unbuilt sets",
        "",
        synthetic_and_indian(colab),
        "",
        "### ONNX export (selected model; latency from the Colab CPU, not deployment hardware)",
        "",
        export_table(colab),
        "",
        f"int8 vs fp32 on the full test set at the same threshold: label agreement {f(colab['export']['int8_vs_fp32']['label_agreement'], 4)}, "
        f"max probability difference {f(colab['export']['int8_vs_fp32']['max_abs_prob_diff'], 4)}. Standalone tokenizer matched the HF tokenizer on "
        f"{colab['export']['tokenizer_parity_rows_checked']} rows. Error analysis: `docs/error_analysis_phase4.md`.",
        END,
        "",
    ])


def baseline_section(base: dict) -> str:
    """Block for the TF-IDF baselines re-run on L3b (available before any transformer result exists)."""
    sizes = base["protocol"]["sizes"]
    rows = []
    for key in ("logreg", "svm"):
        for point, name in (("f1_tuned", "F1-tuned threshold (Phase 3.5 protocol)"), ("recall_first", "recall-first threshold (recall >= "
                                                                                                    f"{base['extras']['recall_target']} on real validation)")):
            r = base["extras"]["models"][key][point]
            o = r["overall"]
            rows.append([BASELINE_TITLES[key], name, f(r["threshold"], 3), f(o["precision"]), f(o["recall"]), f(o["f1"]), f(o["roc_auc"]),
                         f(o["pr_auc"]), f"{o['fp']} / {o['fn']}", f(r["short"]["f1"]), pct(r["benchmark"]["flag_rate"])])
    src_rows = []
    for key in ("logreg", "svm"):
        for src, m in base["extras"]["models"][key]["recall_first"]["by_source"].items():
            src_rows.append([BASELINE_TITLES[key], src, f"{int(m['n'])}", f"{int(m['n_scam'])}", f(m["precision"]), f(m["recall"]), f(m["f1"]), f(m["fpr"])])
    val = {k: base["extras"]["models"][k]["val_real_at_recall_first"]["recall"] for k in ("logreg", "svm")}
    tst = {k: base["extras"]["models"][k]["recall_first"]["overall"]["recall"] for k in ("logreg", "svm")}
    loso = [r for r in base["protocol"]["loso"] if r["variant"] in ("in-distribution", "leave-one-source-out")]
    loso_rows = [[BASELINE_TITLES[r["model"]], r["held_out"] + (" (diagnostic only)" if r["diagnostic_only"] else ""), r["variant"], f"{r['eval_rows']}",
                  f(r["roc_auc"]), f(r["pr_auc"]), f(r["f1"])] for r in loso]
    return "\n".join([
        BASE_START,
        "## Baselines re-run on the Phase 4 data configuration (L3b)",
        "",
        "Run by `python -m src.training.phase4_baseline` (unchanged Phase 3 protocol on `data/processed_phase4/`: tuning on real validation rows, "
        f"test scored once per model). Train {sizes['train']:,} / validation {sizes['val_real']:,} real + {sizes['val_synthetic']:,} synthetic / "
        f"test {sizes['test']:,} (real only). This is the like-for-like baseline for the transformers: the Phase 3.5 numbers earlier in this file belong "
        "to L3 (policy D) on a different test set. \"Promo/service flagged\" is the share of the 153 held-out legitimate promotion and service-notice "
        "test rows (labelled `safe` under policy A) that the model calls scam. Short = raw text of at most 300 characters.",
        "",
        table(["Model", "Operating point", "Threshold", "Precision", "Recall", "F1", "ROC-AUC", "PR-AUC", "FP / FN", "Short-message F1", "Promo/service flagged"], rows),
        "",
        f"Threshold transfer: the recall-first rule keeps recall >= {base['extras']['recall_target']} on validation by construction (logreg "
        f"{f(val['logreg'])}, SVM {f(val['svm'])}), but on the test set recall is {f(tst['logreg'])} (logreg) and {f(tst['svm'])} (SVM): "
        "a threshold chosen on validation does not hold its recall on new data.",
        "",
        "By source, recall-first threshold:",
        "",
        table(["Model", "Source", "Rows", "Scam rows", "Precision", "Recall", "F1", "FPR"], src_rows),
        "",
        "Leave-one-source-out (train without the source, score it; F1 uses the F1-tuned in-distribution threshold). The India SMS source has no "
        "scam rows in test, so it cannot be evaluated this way:",
        "",
        table(["Model", "Held-out source", "Variant", "Rows", "ROC-AUC", "PR-AUC", "F1"], loso_rows),
        BASE_END,
        "",
    ])


def update_results_md(path: Path, block: str, start: str = START, end: str = END) -> None:
    """Replace the block between the markers, or append it if there is none."""
    text = Path(path).read_text(encoding="utf-8")
    if start in text and end in text:
        head, rest = text.split(start, 1)
        _, tail = rest.split(end, 1)
        new = head.rstrip("\n") + "\n\n" + block.rstrip("\n") + "\n" + tail
    else:
        new = text.rstrip("\n") + "\n\n" + block
    Path(path).write_text(new, encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    """Build the section from the downloaded Colab outputs and the local baseline run."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-only", action="store_true", help="write only the L3b baseline block (no Colab results needed)")
    parser.add_argument("--colab-dir", type=Path, help="folder with phase4_results.json and test_predictions_*.csv")
    parser.add_argument("--baseline-json", type=Path, default=BASELINE_JSON)
    parser.add_argument("--update-results", type=Path, help="results.md to update in place")
    parser.add_argument("--boot", type=int, default=1000)
    args = parser.parse_args(argv)
    if args.baseline_only:
        base = json.loads(args.baseline_json.read_text(encoding="utf-8"))
        block = baseline_section(base)
        if args.update_results:
            update_results_md(args.update_results, block, BASE_START, BASE_END)
            print("updated", args.update_results)
        else:
            print(block)
        return 0
    if args.colab_dir is None:
        parser.error("--colab-dir is required unless --baseline-only is given")
    colab = json.loads((args.colab_dir / "phase4_results.json").read_text(encoding="utf-8"))
    if colab.get("smoke_test"):
        raise SystemExit("phase4_results.json comes from a SMOKE_TEST run; refusing to write it into results.md")
    base = json.loads(args.baseline_json.read_text(encoding="utf-8"))
    block = build_section(colab, base, args.colab_dir, args.baseline_json.parent, args.boot)
    if args.update_results:
        update_results_md(args.update_results, block)
        ERROR_DOC.write_text(error_doc(colab), encoding="utf-8")
        print("updated", args.update_results, "and", ERROR_DOC)
    else:
        print(block)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
