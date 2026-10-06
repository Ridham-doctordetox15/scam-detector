"""Honest retrieval evaluation for the RAG knowledge base.

Runs both embedding-text variants (see :mod:`src.rag.rag_engine`) against the
evaluation set, reports top-1/top-3 hit rates split by origin (written vs
real messages neither author wrote the knowledge base from), sweeps a
no-confident-match similarity threshold, and writes a report into
``results.md`` between the ``phase6`` markers.

The variant and threshold are both chosen by looking at this same evaluation
set, so the reported numbers for *that specific choice* are slightly
optimistic - a limitation stated in the written report, not hidden.

Usage::

    python -m src.rag.evaluate --update-results results.md
"""
from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

from src.rag.rag_engine import (
    DEFAULT_MODEL_NAME,
    TEXT_VARIANTS,
    RAGEngine,
)
from src.rag.schema import DEFAULT_KB_PATH

logger = logging.getLogger(__name__)

DEFAULT_EVAL_SET_PATH = Path("data/knowledge_base/eval_set.json")
NO_MATCH = "no_match"
ORIGINS = ("written", "real")
THRESHOLD_CANDIDATES = [round(0.25 + 0.02 * i, 2) for i in range(23)]  # 0.25..0.69

START, END = "<!-- phase6:start -->", "<!-- phase6:end -->"


def load_eval_set(path: Path | str = DEFAULT_EVAL_SET_PATH) -> list[dict]:
    """Load and lightly validate the retrieval evaluation set."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    entries = data["entries"]
    required = {"text", "language", "label", "expected_pattern_id", "origin"}
    for i, e in enumerate(entries):
        missing = required - e.keys()
        if missing:
            raise ValueError(f"eval entry {i}: missing keys {sorted(missing)}")
        if e["origin"] not in ORIGINS:
            raise ValueError(f"eval entry {i}: origin must be one of {ORIGINS}")
    return entries


def _run_raw(engine: RAGEngine, eval_entries: list[dict], top_k: int = 3) -> list[dict]:
    """Retrieve for every eval entry, ignoring the engine's confidence gate.

    Returns one record per eval entry with the raw top-k entry ids and the
    top-1 similarity, so hit rates and the threshold sweep can both be
    computed from the same retrieval pass.
    """
    records = []
    for entry in eval_entries:
        result = engine.retrieve(entry["text"], top_k=top_k)
        top_ids = [m.entry_id for m in result.matches]
        top1_similarity = result.matches[0].similarity if result.matches else 0.0
        records.append({**entry, "top_ids": top_ids, "top1_similarity": top1_similarity})
    return records


def _hit_rates(records: list[dict], origin: str | None = None) -> dict:
    """Top-1/top-3 hit rate over matched (non no_match) rows, optionally filtered by origin."""
    rows = [r for r in records if r["expected_pattern_id"] != NO_MATCH]
    if origin is not None:
        rows = [r for r in rows if r["origin"] == origin]
    n = len(rows)
    if n == 0:
        return {"n": 0, "top1": None, "top3": None}
    top1 = sum(1 for r in rows if r["top_ids"] and r["top_ids"][0] == r["expected_pattern_id"]) / n
    top3 = sum(1 for r in rows if r["expected_pattern_id"] in r["top_ids"]) / n
    return {"n": n, "top1": top1, "top3": top3}


def _sweep_threshold(records: list[dict]) -> tuple[float, dict]:
    """Pick the threshold that best separates matched rows from no_match rows.

    Scored as the *average* of matched_confident_rate and no_match_decline_rate,
    not their combined count - there are far more matched rows (57) than
    no_match rows (3) in this eval set, and an unweighted count would let the
    threshold ignore no_match entirely (maximise trivially by staying low).
    Ties broken toward the higher threshold (more conservative about forcing
    a pattern onto an unrelated message). With only 3 no_match examples this
    is a coarse estimate - stated as a limitation in the written report, not
    hidden.
    """
    matched = [r for r in records if r["expected_pattern_id"] != NO_MATCH]
    no_match = [r for r in records if r["expected_pattern_id"] == NO_MATCH]
    best_threshold, best_score, best_detail = THRESHOLD_CANDIDATES[0], -1.0, {}
    for t in THRESHOLD_CANDIDATES:
        matched_rate = sum(1 for r in matched if r["top1_similarity"] >= t) / len(matched) if matched else None
        no_match_rate = sum(1 for r in no_match if r["top1_similarity"] < t) / len(no_match) if no_match else None
        score = sum(x for x in (matched_rate, no_match_rate) if x is not None) / max(
            1, sum(1 for x in (matched_rate, no_match_rate) if x is not None)
        )
        if score >= best_score:
            best_score = score
            best_threshold = t
            best_detail = {
                "score": score,
                "matched_confident_rate": matched_rate,
                "no_match_decline_rate": no_match_rate,
            }
    return best_threshold, best_detail


def evaluate_variant(
    kb_path: Path, persist_dir: Path, text_variant: str, eval_entries: list[dict], embed_fn=None
) -> dict:
    """Run one embedding-text variant over the whole eval set."""
    engine = RAGEngine(kb_path, persist_dir, text_variant=text_variant, embed_fn=embed_fn)
    engine.build_index()
    records = _run_raw(engine, eval_entries)
    threshold, threshold_detail = _sweep_threshold(records)
    return {
        "text_variant": text_variant,
        "overall": _hit_rates(records),
        "written": _hit_rates(records, "written"),
        "real": _hit_rates(records, "real"),
        "chosen_threshold": threshold,
        "threshold_detail": threshold_detail,
    }


def _fmt(x: float | None) -> str:
    return "n/a" if x is None else f"{x:.0%}"


def _table(header: list[str], rows: list[list[str]]) -> str:
    lines = ["| " + " | ".join(header) + " |", "|" + "|".join("---" for _ in header) + "|"]
    return "\n".join(lines + ["| " + " | ".join(r) + " |" for r in rows])


def report_section(results: dict) -> str:
    """The generated block for results.md (between the phase6 markers)."""
    variants = results["variants"]
    winner = results["winner"]

    hit_rows = []
    for v in variants:
        for origin_label, key in [("Overall", "overall"), ("Written", "written"), ("Real", "real")]:
            hr = v[key]
            hit_rows.append([v["text_variant"], origin_label, str(hr["n"]), _fmt(hr["top1"]), _fmt(hr["top3"])])

    threshold_rows = [
        [v["text_variant"], f"{v['chosen_threshold']:.2f}",
         _fmt(v["threshold_detail"]["matched_confident_rate"]),
         _fmt(v["threshold_detail"]["no_match_decline_rate"])]
        for v in variants
    ]

    return "\n".join([
        START,
        f"**Run date:** {results['run_date']}  ",
        f"**Model:** `{results['model_name']}`  ",
        f"**Eval set:** `{results['eval_set_path']}` "
        f"({results['n_written']} written messages the entries were not built from, "
        f"{results['n_real']} real messages from existing project datasets that neither author wrote, "
        f"{results['n_no_match']} labelled `no_match`)",
        "",
        "Top-1/top-3 hit rate = fraction of *matched* rows (excludes `no_match` rows) where the "
        "expected pattern id is the top retrieved result / within the top 3:",
        "",
        _table(["Text variant", "Split", "n", "Top-1 hit rate", "Top-3 hit rate"], hit_rows),
        "",
        f"**Chosen embedding text variant: `{winner}`** "
        f"(higher combined written+real top-1/top-3 hit rate on this eval set).",
        "",
        "No-confident-match threshold, swept over the same eval set and picked to best separate matched "
        "rows (should be confident) from `no_match` rows (should not be), scoring the *average* of the two "
        "rates below so the much larger matched group can't dominate the choice - \"matched confident rate\" "
        "is how often a real pattern's top-1 similarity clears the threshold, \"no_match decline rate\" is "
        f"how often an unrelated message's top-1 similarity correctly falls below it. Only "
        f"{results['n_no_match']} `no_match` examples exist in this eval set, so this threshold is a coarse "
        "estimate, not a tuned one - the similarity distributions of matched and unrelated messages overlap "
        "substantially for this model on short text, and a larger no_match set (a natural next step for "
        "expanding this eval set) would sharpen it:",
        "",
        _table(["Text variant", "Chosen threshold", "Matched confident rate", "No_match decline rate"], threshold_rows),
        "",
        f"**`RAGEngine` default: `text_variant=\"{winner}\"`, `min_confident_similarity={results['final_threshold']:.2f}`.**",
        "",
        "**Overlap risk (stated honestly):** both the knowledge base's `typical_phrases` and the 40 "
        "\"written\" evaluation messages were authored by the same person with the same general "
        "knowledge of these scam patterns, using deliberately different wording - this is not an "
        "independent, blind evaluation like the real Indian test set from earlier phases. The 20 "
        "\"real\" messages (drawn from UCI SMS and the India SMS dataset, never used to write the "
        "knowledge base) are the closer approximation to a genuine generalisation test, and their "
        "hit rate is reported separately for exactly that reason. The embedding-text variant and the "
        "no-confident-match threshold were both selected by looking at this same eval set, so the "
        "final numbers for the chosen configuration are slightly optimistic, not a blind test.",
        END,
        "",
    ])


def update_results_md(path: Path, block: str) -> None:
    """Replace the block between the phase6 markers, or append it if there is none."""
    text = Path(path).read_text(encoding="utf-8")
    if START in text and END in text:
        head, rest = text.split(START, 1)
        _, tail = rest.split(END, 1)
        new = head.rstrip("\n") + "\n\n" + block.rstrip("\n") + "\n" + tail
    else:
        new = text.rstrip("\n") + "\n\n" + block
    Path(path).write_text(new, encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    import datetime

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kb-path", type=Path, default=DEFAULT_KB_PATH)
    parser.add_argument("--eval-set", type=Path, default=DEFAULT_EVAL_SET_PATH)
    parser.add_argument("--persist-dir", type=Path, default=Path("chroma_db"))
    parser.add_argument("--update-results", type=Path, help="results.md to update in place")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.WARNING)
    eval_entries = load_eval_set(args.eval_set)

    from src.rag.rag_engine import _default_embed_fn

    shared_embed_fn = _default_embed_fn(DEFAULT_MODEL_NAME)  # load the model once, share across variants

    variant_results = [
        evaluate_variant(args.kb_path, args.persist_dir, variant, eval_entries, embed_fn=shared_embed_fn)
        for variant in TEXT_VARIANTS
    ]

    def combined_score(v: dict) -> float:
        rates = [v["overall"]["top1"] or 0.0, v["overall"]["top3"] or 0.0]
        return sum(rates) / len(rates)

    winner_result = max(variant_results, key=combined_score)
    winner = winner_result["text_variant"]

    results = {
        "run_date": datetime.date.today().isoformat(),
        "model_name": DEFAULT_MODEL_NAME,
        "eval_set_path": Path(args.eval_set).as_posix(),
        "n_written": sum(1 for e in eval_entries if e["origin"] == "written"),
        "n_real": sum(1 for e in eval_entries if e["origin"] == "real"),
        "n_no_match": sum(1 for e in eval_entries if e["expected_pattern_id"] == NO_MATCH),
        "variants": variant_results,
        "winner": winner,
        "final_threshold": winner_result["chosen_threshold"],
    }

    block = report_section(results)
    print(block)
    if args.update_results:
        update_results_md(args.update_results, block)
        print(f"\nUpdated {args.update_results}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
