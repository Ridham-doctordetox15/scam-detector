"""Exploratory-analysis helpers: statistics (pure, tested) and charts (saved as PNG).

The notebook ``notebooks/01_eda.ipynb`` calls these functions so it stays short
and so the logic is unit-tested. Charts follow one colour rule everywhere: **safe
is blue, scam is orange** (colours belong to the class, never to rank), on a
recessive grid with direct value labels. Neutral greys are used where colour would
suggest a class that is not being shown.

Charts are written to ``docs/figures/``.
"""
from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # headless: never needs a display
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from sklearn.feature_extraction.text import CountVectorizer  # noqa: E402

FIGURE_DIR = Path("docs/figures")

# Validated categorical slots 1 and 2 (see the dataviz palette): pass every colour gate.
SAFE = "#2a78d6"
SCAM = "#eb6834"
CLASS_COLORS = {"safe": SAFE, "scam": SCAM}
SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK_2 = "#52514e"
MUTED = "#898781"
GRID = "#e1e0d9"
BASELINE = "#c3c2b7"
LABELS = ("safe", "scam")


# --------------------------------------------------------------------------- #
# Statistics (pure functions)
# --------------------------------------------------------------------------- #
def class_counts(df: pd.DataFrame) -> pd.DataFrame:
    """Rows and share per label, in fixed order (safe, scam)."""
    counts = df["label"].value_counts().reindex(list(LABELS), fill_value=0)
    return pd.DataFrame({"rows": counts, "share": counts / max(len(df), 1)})


def scam_rate_by_source(df: pd.DataFrame) -> pd.DataFrame:
    """Per source: rows, scam rows, scam rate and share of synthetic rows.

    A strong spread in ``scam_rate`` means the source is a shortcut for the label
    (the *source confound*): a model can partly predict the label from the source's
    style alone.
    """
    g = df.groupby("source")
    out = pd.DataFrame(
        {
            "rows": g.size(),
            "scam_rows": g["label"].apply(lambda s: int((s == "scam").sum())),
            "synthetic_share": g["is_synthetic"].mean(),
        }
    )
    out["scam_rate"] = out["scam_rows"] / out["rows"]
    return out.sort_values("rows", ascending=False)


def text_lengths(df: pd.DataFrame) -> pd.Series:
    """Character length of the *original* text (``text_raw`` if present, else ``text``)."""
    col = "text_raw" if "text_raw" in df.columns else "text"
    return df[col].str.len()


def length_stats(df: pd.DataFrame) -> pd.DataFrame:
    """Median / mean / 95th percentile / max message length by source and label."""
    work = df.assign(chars=text_lengths(df))
    grouped = work.groupby(["source", "label"])["chars"]
    return grouped.agg(
        rows="size",
        median="median",
        mean="mean",
        p95=lambda s: s.quantile(0.95),
        max="max",
    ).round(1)


def language_counts(df: pd.DataFrame) -> pd.DataFrame:
    """Rows per language and label (columns: safe, scam, total), largest first."""
    table = pd.crosstab(df["language"], df["label"]).reindex(columns=list(LABELS), fill_value=0)
    table["total"] = table.sum(axis=1)
    return table.sort_values("total", ascending=False)


def top_words_by_class(
    df: pd.DataFrame, n: int = 15, min_df: int = 20, alpha: float = 0.5
) -> dict[str, pd.DataFrame]:
    """Most class-distinctive words by smoothed log-odds ratio of document frequency.

    Log-odds (rather than raw counts) surfaces words that *separate* the classes
    instead of words that are merely common. Masked tokens (``<URL>`` -> ``url`` etc.)
    are kept because "has a link / phone / OTP" is itself informative.

    Args:
        df: Frame with ``text`` and ``label``.
        n: Words returned per class.
        min_df: Ignore words in fewer than this many documents.
        alpha: Additive smoothing.

    Returns:
        ``{"scam": frame, "safe": frame}`` with columns ``word``, ``log_odds``,
        ``docs_scam``, ``docs_safe``, sorted by strength.
    """
    vec = CountVectorizer(
        lowercase=True, stop_words="english", token_pattern=r"(?u)\b[^\W\d_]{3,}\b",
        binary=True, min_df=min_df,
    )
    matrix = vec.fit_transform(df["text"])
    is_scam = (df["label"] == "scam").to_numpy()
    docs_scam = np.asarray(matrix[is_scam].sum(axis=0)).ravel()
    docs_safe = np.asarray(matrix[~is_scam].sum(axis=0)).ravel()
    n_scam, n_safe = int(is_scam.sum()), int((~is_scam).sum())
    log_odds = np.log((docs_scam + alpha) / (n_scam - docs_scam + alpha)) - np.log(
        (docs_safe + alpha) / (n_safe - docs_safe + alpha)
    )
    table = pd.DataFrame(
        {"word": vec.get_feature_names_out(), "log_odds": log_odds,
         "docs_scam": docs_scam, "docs_safe": docs_safe}
    )
    return {
        "scam": table.sort_values("log_odds", ascending=False).head(n).reset_index(drop=True),
        "safe": table.sort_values("log_odds", ascending=True).head(n).reset_index(drop=True),
    }


def masked_token_rates(df: pd.DataFrame) -> pd.DataFrame:
    """Share of messages containing ``<URL>``, ``<PHONE>`` and ``<OTP>``, by label."""
    rows = {
        token: df.groupby("label")["text"].apply(lambda s, t=token: s.str.contains(t, regex=False).mean())
        for token in ("<URL>", "<PHONE>", "<OTP>")
    }
    return pd.DataFrame(rows).reindex(list(LABELS))


# --------------------------------------------------------------------------- #
# Chart helpers
# --------------------------------------------------------------------------- #
def _style_axes(ax: plt.Axes, grid_axis: str = "y") -> None:
    """Recessive chrome: no top/right spines, hairline grid on one axis only."""
    ax.set_facecolor(SURFACE)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(BASELINE)
    ax.tick_params(colors=MUTED, labelsize=9, length=0)
    ax.grid(axis=grid_axis, color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)


def _new_figure(width: float = 9.0, height: float = 4.8, **kw) -> tuple[plt.Figure, np.ndarray | plt.Axes]:
    plt.rcParams["font.family"] = ["Segoe UI", "DejaVu Sans"]
    fig, axes = plt.subplots(figsize=(width, height), facecolor=SURFACE, **kw)
    return fig, axes


def _title(fig: plt.Figure, title: str, subtitle: str | None = None) -> None:
    fig.text(0.01, 0.985, title, ha="left", va="top", fontsize=13, fontweight="bold", color=INK)
    if subtitle:
        fig.text(0.01, 0.925, subtitle, ha="left", va="top", fontsize=9.5, color=INK_2)


def _save(fig: plt.Figure, path: Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=150, facecolor=SURFACE, bbox_inches="tight")
    plt.close(fig)
    return path


def _legend_by_label(ax: plt.Axes, loc: str = "upper right") -> None:
    handles = [plt.Line2D([], [], marker="s", linestyle="", color=CLASS_COLORS[k], markersize=9, label=k)
               for k in LABELS]
    leg = ax.legend(handles=handles, loc=loc, frameon=False, fontsize=9, handletextpad=0.3)
    for text in leg.get_texts():
        text.set_color(INK_2)


# --------------------------------------------------------------------------- #
# Charts
# --------------------------------------------------------------------------- #
def plot_class_balance(df: pd.DataFrame, path: Path = FIGURE_DIR / "class_balance.png") -> Path:
    """Bar chart of safe vs scam row counts with counts and shares labelled."""
    counts = class_counts(df)
    fig, ax = _new_figure(6.4, 4.2)
    bars = ax.bar(list(LABELS), counts["rows"], width=0.5, color=[CLASS_COLORS[k] for k in LABELS],
                  edgecolor=SURFACE, linewidth=2)
    for bar, (_, r) in zip(bars, counts.iterrows()):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height(), f"{int(r['rows']):,}\n{r['share']:.1%}",
                ha="center", va="bottom", fontsize=10, color=INK)
    ax.set_ylim(0, counts["rows"].max() * 1.18)
    ax.set_ylabel("messages", color=MUTED, fontsize=9)
    ax.yaxis.set_major_formatter(lambda v, _: f"{int(v):,}")
    _style_axes(ax)
    ax.tick_params(axis="x", labelsize=11, colors=INK_2)
    _title(fig, "Class balance", f"{len(df):,} deduplicated messages")
    return _save(fig, path)


def plot_scam_rate_by_source(df: pd.DataFrame, path: Path = FIGURE_DIR / "scam_rate_by_source.png") -> Path:
    """Horizontal bars of the scam rate per source: the source-confound check."""
    rates = scam_rate_by_source(df).sort_values("scam_rate")
    fig, ax = _new_figure(9, 1.4 + 0.7 * len(rates))
    y = np.arange(len(rates))
    ax.barh(y, rates["scam_rate"], height=0.5, color=SCAM, edgecolor=SURFACE, linewidth=2)
    overall = (df["label"] == "scam").mean()
    ax.axvline(overall, color=INK_2, linewidth=1.2, linestyle=(0, (4, 3)))
    ax.text(overall, len(rates) - 0.35, f" overall {overall:.0%}", color=INK_2, fontsize=9, va="bottom")
    for yi, (name, r) in zip(y, rates.iterrows()):
        ax.text(r["scam_rate"] + 0.01, yi, f"{r['scam_rate']:.0%}  (n={int(r['rows']):,})", va="center",
                fontsize=9.5, color=INK)
    ax.set_yticks(y, rates.index, color=INK_2, fontsize=10)
    ax.set_xlim(0, min(1.0, max(rates["scam_rate"].max() * 1.35, overall * 1.5)))
    ax.xaxis.set_major_formatter(lambda v, _: f"{v:.0%}")
    _style_axes(ax, "x")
    fig.subplots_adjust(top=0.78)
    _title(fig, "Scam rate differs a lot between sources",
           "A wide spread means the source itself hints at the label (source confound)")
    return _save(fig, path)


def plot_length_distribution(df: pd.DataFrame, path: Path = FIGURE_DIR / "length_distribution.png") -> Path:
    """Length histograms (log10 characters), one panel per source, classes overlaid."""
    sources = scam_rate_by_source(df).index.tolist()
    fig, axes = _new_figure(3.2 * len(sources), 3.9, ncols=len(sources), sharey=False)
    axes = np.atleast_1d(axes)
    chars = text_lengths(df).clip(lower=1)
    bins = np.linspace(np.log10(chars.min()), np.log10(max(chars.max(), 10)), 36)
    for ax, source in zip(axes, sources):
        mask_src = df["source"] == source
        for label in LABELS:
            values = np.log10(chars[mask_src & (df["label"] == label)])
            if len(values):
                ax.hist(values, bins=bins, density=True, histtype="step", linewidth=2, color=CLASS_COLORS[label])
                ax.axvline(values.median(), color=CLASS_COLORS[label], linewidth=1, linestyle=(0, (3, 3)))
        ax.set_title(f"{source}\nn={int(mask_src.sum()):,}", fontsize=9.5, color=INK_2, loc="left")
        ax.set_xticks([1, 2, 3, 4], ["10", "100", "1k", "10k"])
        ax.set_yticks([])
        _style_axes(ax, "y")
        ax.grid(False)
    axes[0].set_ylabel("density", color=MUTED, fontsize=9)
    _legend_by_label(axes[-1])
    fig.subplots_adjust(top=0.72, wspace=0.12)
    _title(fig, "Message length by source and class", "Characters, log scale; dashed line = class median")
    return _save(fig, path)


def plot_top_words(words: dict[str, pd.DataFrame], path: Path = FIGURE_DIR / "top_words.png",
                   subtitle: str = "Smoothed log-odds of document frequency") -> Path:
    """Two panels of the most class-distinctive words (scam left, safe right)."""
    fig, axes = _new_figure(11, 5.6, ncols=2)
    for ax, label in zip(axes, ("scam", "safe")):
        table = words[label].iloc[::-1]
        ax.barh(table["word"], table["log_odds"].abs(), height=0.62, color=CLASS_COLORS[label],
                edgecolor=SURFACE, linewidth=1.5)
        ax.set_title(f"more typical of {label}", fontsize=10.5, color=INK_2, loc="left")
        ax.tick_params(axis="y", labelsize=9.5, colors=INK_2)
        ax.set_xlabel("|log-odds|", color=MUTED, fontsize=9)
        _style_axes(ax, "x")
    fig.subplots_adjust(top=0.8, wspace=0.35)
    _title(fig, "Most class-distinctive words", subtitle)
    return _save(fig, path)


def plot_language_distribution(df: pd.DataFrame, path: Path = FIGURE_DIR / "language_distribution.png") -> Path:
    """Grouped horizontal bars of rows per language and class (log scale)."""
    table = language_counts(df).iloc[::-1]
    fig, ax = _new_figure(9, 1.6 + 0.62 * len(table))
    y = np.arange(len(table))
    h = 0.36
    for offset, label in ((+h / 2, "scam"), (-h / 2, "safe")):
        values = table[label].to_numpy()
        ax.barh(y + offset, np.where(values > 0, values, np.nan), height=h - 0.04, color=CLASS_COLORS[label],
                edgecolor=SURFACE, linewidth=1.5)
        for yi, v in zip(y + offset, values):
            if v > 0:
                ax.text(v * 1.12, yi, f"{int(v):,}", va="center", fontsize=8.5, color=INK_2)
    ax.set_xscale("log")
    ax.set_xlim(0.8, table[list(LABELS)].to_numpy().max() * 12)
    ax.set_yticks(y, table.index, color=INK_2, fontsize=10)
    _style_axes(ax, "x")
    _legend_by_label(ax, "lower right")
    fig.subplots_adjust(top=0.82)
    _title(fig, "Language distribution", "Rows per language (log scale). Real data is almost all English; code-mixed text is mostly synthetic")
    return _save(fig, path)


def plot_real_vs_synthetic(splits: dict[str, pd.DataFrame], path: Path = FIGURE_DIR / "real_vs_synthetic.png") -> Path:
    """Stacked bars per split: real rows (solid) vs synthetic rows (hatched)."""
    names = list(splits)
    real = np.array([int((~splits[n]["is_synthetic"]).sum()) for n in names])
    synth = np.array([int(splits[n]["is_synthetic"].sum()) for n in names])
    fig, ax = _new_figure(7.4, 4.4)
    x = np.arange(len(names))
    ax.bar(x, real, width=0.5, color=INK_2, edgecolor=SURFACE, linewidth=2, label="real")
    ax.bar(x, synth, width=0.5, bottom=real, color=BASELINE, edgecolor=INK_2, hatch="///", linewidth=0.8, label="synthetic")
    for xi, r, s in zip(x, real, synth):
        ax.text(xi, r + s, f"{r + s:,}", ha="center", va="bottom", fontsize=10, color=INK)
    # The real/synthetic breakdown lives in the axis labels: thin synthetic segments cannot hold text.
    ax.set_xticks(x, [f"{n}\n{r:,} real | {s:,} synthetic" for n, r, s in zip(names, real, synth)],
                  fontsize=10, color=INK_2)
    ax.set_ylim(0, (real + synth).max() * 1.15)
    ax.yaxis.set_major_formatter(lambda v, _: f"{int(v):,}")
    _style_axes(ax)
    fig.subplots_adjust(top=0.84)
    _title(fig, "Real vs synthetic rows per split", "Synthetic data is allowed in train/validation only; the test set is 100% real")
    return _save(fig, path)


def plot_dedup_funnel(report: dict, path: Path = FIGURE_DIR / "dedup_funnel.png") -> Path:
    """Row counts after each preprocessing stage, with the number removed at each step."""
    stages = [
        ("combined input", report["input_rows"]),
        ("after cleaning", report["rows_after_cleaning"]),
        ("after exact dedup", report["rows_after_exact_dedup"]),
        ("after near-dup dedup", report["rows_after_exact_dedup"] - report["near_duplicates"]["removed"]),
        ("final (after holdout check)", report["rows_after_dedup"]),
    ]
    fig, ax = _new_figure(9, 4.2)
    y = np.arange(len(stages))[::-1]
    values = [v for _, v in stages]
    ax.barh(y, values, height=0.55, color=INK_2, edgecolor=SURFACE, linewidth=2)
    for yi, (name, v), prev in zip(y, stages, [None] + values[:-1]):
        delta = f"   (-{prev - v:,})" if prev is not None and prev > v else ""
        ax.text(v + max(values) * 0.01, yi, f"{v:,}{delta}", va="center", fontsize=9.5, color=INK)
    ax.set_yticks(y, [n for n, _ in stages], color=INK_2, fontsize=10)
    ax.set_xlim(0, max(values) * 1.25)
    ax.xaxis.set_major_formatter(lambda v, _: f"{int(v):,}")
    _style_axes(ax, "x")
    fig.subplots_adjust(top=0.82)
    _title(fig, "Rows after each preprocessing stage",
           f"Near-duplicates: TF-IDF cosine >= {report['near_duplicates']['threshold']}, deduplicated before splitting")
    return _save(fig, path)
