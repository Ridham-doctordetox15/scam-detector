"""Corpus-artifact reduction (Phase 3.5).

The public email corpora leave fingerprints that let a model recognise *where a message came
from* instead of *whether it is a scam*: quote markers (``>``), reply and forward boilerplate,
Enron names, 1990s-2000s years, the pound sign, web-crawl rows, and pre-tokenised spacing
(" . ", " , "). This module removes or neutralises them.

Design rules:

* **Conservative:** normalisation removes *markers*, never message content. Quoted text stays,
  only the ``>`` is dropped; a forwarded body stays, only the "forwarded by X on <date>" line
  goes. A test checks that scam-signal words survive every transformation.
* **Configurable levels** so each step can be evaluated on its own (the Phase 3.5 ablation
  ladder). Nothing here reads a label, so the same function is safe to apply at inference time.
* **Rows to drop are decided by tokens, never by label.** Dropping only Enron *safe* rows would
  leave ``enron`` present only in a few scam rows, flipping the fingerprint into a "scam"
  signal. Rows are therefore dropped by content regardless of label.

Not addressed here (documented for Phase 4): 69% of the HF text is entirely lowercase versus
1.7% of UCI SMS. The TF-IDF baselines lowercase everything anyway, but a cased transformer
could still exploit it, so Phase 4 should use an uncased model or lowercase all inputs.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, replace

import pandas as pd

CURRENCY_TOKEN = "<CUR>"
YEAR_TOKEN = "<YEAR>"

# ----------------------------------------------------------------------------------- #
# Text transformations
# ----------------------------------------------------------------------------------- #
_QUOTE_LINE_START = re.compile(r"(?m)^[ \t]*(?:>[ \t]*)+")
_QUOTE_AFTER_WROTE = re.compile(r"(?i)(wrote\s*:)\s*>+")
_QUOTE_STANDALONE = re.compile(r"(?<=\s)>+(?=\s)")
_REPLY_ATTRIBUTION = re.compile(r"(?i)\bon\b[^\n>]{0,90}?\bwrote\s*:?")
_ORIGINAL_MESSAGE = re.compile(r"(?i)(?:-\s?){2,}\s*original message\s*(?:-\s?){2,}")
_FORWARDED_BY = re.compile(
    r"(?i)(?:-\s?){3,}\s*forwarded by\b[^\n]{0,90}?\bon\s+\d{1,2}\s?/\s?\d{1,2}\s?/\s?\d{2,4}"
    r"(?:\s+\d{1,2}\s?:\s?\d{2}(?:\s?[ap]m)?)?(?:\s*(?:-\s?){3,})?"
)
_FORWARDED_BY_PLAIN = re.compile(
    r"(?i)\bforwarded by\b[^\n]{0,90}?\bon\s+\d{1,2}\s?/\s?\d{1,2}\s?/\s?\d{2,4}(?:\s+\d{1,2}\s?:\s?\d{2}(?:\s?[ap]m)?)?"
)
_DASH_RUN = re.compile(r"(?:-\s?){5,}")
_YEAR = re.compile(r"\b(?:199\d|200\d|2010)\b")
_CURRENCY = re.compile(r"(?i)(?:£|€|₹|\$|\brs\.?\s?|\binr\s?)(?=\d)")
_SPACE_BEFORE_PUNCT = re.compile(r"[ \t]+([.,;:!?])(?=\s|$)")


def strip_quote_markers(text: str) -> str:
    """Remove ``>`` reply-quote markers (line-start, after "wrote:", and standalone) but keep the text."""
    text = _QUOTE_LINE_START.sub("", text)
    text = _QUOTE_AFTER_WROTE.sub(r"\1", text)
    return _QUOTE_STANDALONE.sub("", text)


def strip_reply_boilerplate(text: str) -> str:
    """Remove "On <date>, <name> wrote:", "-----original message-----", "forwarded by ... on <date>" and dash rulers."""
    text = _REPLY_ATTRIBUTION.sub(" ", text)
    text = _ORIGINAL_MESSAGE.sub(" ", text)
    text = _FORWARDED_BY.sub(" ", text)
    text = _FORWARDED_BY_PLAIN.sub(" ", text)
    return _DASH_RUN.sub(" ", text)


def mask_years(text: str) -> str:
    """Replace years 1990-2010 (the age of the public corpora) with ``<YEAR>``; recent years are kept."""
    return _YEAR.sub(YEAR_TOKEN, text)


def normalize_currency(text: str) -> str:
    """Replace a currency symbol/abbreviation directly before a number with ``<CUR>`` (the amount stays)."""
    return _CURRENCY.sub(CURRENCY_TOKEN + " ", text)


def fix_tokenized_spacing(text: str) -> str:
    """Undo pre-tokenised punctuation spacing: ``"hello ."`` -> ``"hello."``."""
    return _SPACE_BEFORE_PUNCT.sub(r"\1", text)


# ----------------------------------------------------------------------------------- #
# Row filters
# ----------------------------------------------------------------------------------- #
_WEB_CRAWL = re.compile(r"\A\s*URL:\s*https?://")
_PIPELINE_NOTICE = re.compile(r"(?i)hourahead|schedule crawler")
_ENRON_INTERNAL = re.compile(
    r"(?i)\benron\b|\benronxgate\b|\bhpl\b|/\s*ect\b|\bect\b|/\s*hou\s*/|\bkaminski\b|\bvince j\b"
)


def is_web_crawl_row(text: str) -> bool:
    """A scraped news/blog feed item ("URL: http... Date: ..."), not a message."""
    return bool(_WEB_CRAWL.search(text)) and "Date:" in text


def is_pipeline_notice(text: str) -> bool:
    """An automated pipeline notice ("hourahead failure", "schedule crawler") from the Enron corpus."""
    return bool(_PIPELINE_NOTICE.search(text))


def is_enron_internal(text: str) -> bool:
    """Contains Enron-internal markers (company name, Enron division tags, well-known employees)."""
    return bool(_ENRON_INTERNAL.search(text))


# ----------------------------------------------------------------------------------- #
# Configuration and application
# ----------------------------------------------------------------------------------- #
@dataclass(frozen=True)
class NormalizeConfig:
    """Which artifact-reduction steps to apply."""

    strip_quote_markers: bool = False
    strip_reply_boilerplate: bool = False
    mask_years: bool = False
    normalize_currency: bool = False
    fix_spacing: bool = False
    drop_web_crawl: bool = False
    drop_pipeline_notices: bool = False
    drop_enron_internal: bool = False

    @property
    def transforms_text(self) -> bool:
        return any((self.strip_quote_markers, self.strip_reply_boilerplate, self.mask_years,
                    self.normalize_currency, self.fix_spacing))

    @property
    def drops_rows(self) -> bool:
        return any((self.drop_web_crawl, self.drop_pipeline_notices, self.drop_enron_internal))


NONE = NormalizeConfig()
# Ablation ladder levels (see results.md): A = text normalisation, B1 = drop non-messages,
# B2 = also drop Enron-internal email.
LEVEL_A = NormalizeConfig(strip_quote_markers=True, strip_reply_boilerplate=True, mask_years=True,
                          normalize_currency=True, fix_spacing=True)
LEVEL_A_B1 = replace(LEVEL_A, drop_web_crawl=True, drop_pipeline_notices=True)
LEVEL_A_B1_B2 = replace(LEVEL_A_B1, drop_enron_internal=True)


def normalize_text(text: str, cfg: NormalizeConfig) -> str:
    """Apply the enabled text transformations to one message (whitespace is tidied afterwards)."""
    if not cfg.transforms_text:
        return text
    if cfg.strip_reply_boilerplate:          # first: attribution lines contain '>' after "wrote:"
        text = strip_reply_boilerplate(text)
    if cfg.strip_quote_markers:
        text = strip_quote_markers(text)
    if cfg.mask_years:
        text = mask_years(text)
    if cfg.normalize_currency:
        text = normalize_currency(text)
    if cfg.fix_spacing:
        text = fix_tokenized_spacing(text)
    return re.sub(r"[ \t]{2,}", " ", text).strip()


def drop_reason(text: str, cfg: NormalizeConfig) -> str | None:
    """Why ``text`` should be dropped under ``cfg`` (``web_crawl``, ``pipeline_notice``, ``enron_internal``) or ``None``."""
    if cfg.drop_web_crawl and is_web_crawl_row(text):
        return "web_crawl"
    if cfg.drop_pipeline_notices and is_pipeline_notice(text):
        return "pipeline_notice"
    if cfg.drop_enron_internal and is_enron_internal(text):
        return "enron_internal"
    return None


def filter_rows(df: pd.DataFrame, cfg: NormalizeConfig, column: str = "text") -> tuple[pd.DataFrame, dict]:
    """Drop rows per ``cfg`` (by content, regardless of label).

    Returns:
        ``(kept_frame, dropped)`` where ``dropped`` maps each reason to ``{"total": n, <label>: n, ...}``.
    """
    if not cfg.drops_rows:
        return df.copy(), {}
    reasons = df[column].map(lambda t: drop_reason(str(t), cfg))
    dropped: dict[str, dict[str, int]] = {}
    for reason in sorted(reasons.dropna().unique()):
        part = df[reasons == reason]
        counts = {k: int(v) for k, v in part["label"].value_counts().items()} if "label" in df.columns else {}
        dropped[reason] = {"total": len(part), **counts}
    return df[reasons.isna()].copy(), dropped


def normalize_frame(df: pd.DataFrame, cfg: NormalizeConfig, column: str = "text") -> tuple[pd.DataFrame, dict]:
    """Drop rows per ``cfg`` and normalise the text column.

    Returns:
        ``(frame, report)`` where ``report`` has ``dropped`` (count per reason, split by label),
        ``changed`` (rows whose text changed) and ``rows_in`` / ``rows_out``.
    """
    kept, dropped = filter_rows(df, cfg, column)
    before = kept[column].astype(str)
    kept[column] = before.map(lambda t: normalize_text(t, cfg))
    report = {"rows_in": len(df), "rows_out": len(kept), "dropped": dropped, "changed": int((kept[column] != before).sum())}
    return kept.reset_index(drop=True), report
