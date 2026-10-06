"""Output-language choice for the explainer: ``"en"``, ``"hi"`` or ``"hinglish"``.

A thin mapping over the project's single language heuristic,
:func:`src.preprocessing.language.detect_language` (the Phase 2 tagger). It is
a heuristic, not a language-ID model:

* ``hi``: Devanagari makes up at least 20% of the letters (so an English
  message that quotes one Hindi word stays English). Marathi/Nepali share the
  script and are also answered in Hindi.
* ``hinglish``: at least 2 *distinct* romanized-Hindi marker words from a
  curated list that excludes English collisions ("to", "me", "main", "par"...).
  The explainer uses the extended list (Phase 2 markers + common connectives
  such as "ke", "liye", "baje", checked against 21k real English messages).
* ``en``: everything else.

Until 2026-09-30 the explainer used its own, much smaller word list (36
words, any single Devanagari character meant Hindi), which missed common
Hinglish such as "Bhai kal 1 baje lunch pe milte hain, office ke paas wale
cafe mein?" (only "hain" matched) and answered it in English. Keeping one
detector avoids that drift. Measured before/after numbers are in results.md.

Known limitation (documented in the README): code-mixed Tamil/Telugu/
Bengali/Marathi-English (``ta_en``/``te_en``/``bn_en``/``mr_en``) and
native-script Tamil/Bengali/... messages get English output - the explainer
only writes English, Hindi and Hinglish.
"""
from __future__ import annotations

from typing import Literal

from src.preprocessing.language import HINGLISH_MARKERS_EXTENDED
from src.preprocessing.language import detect_language as _tag_language

Language = Literal["en", "hi", "hinglish"]

_TAG_TO_LANGUAGE: dict[str, Language] = {"hi": "hi", "hinglish_guess": "hinglish"}


# Messages longer than this need 3 distinct markers instead of 2 (long English emails
# otherwise co-occur two short markers by chance). Hinglish SMS/WhatsApp are short:
# the 90th percentile in the synthetic set is 30 words.
LONG_TEXT_WORDS = 60


def detect_language(text: str) -> Language:
    """Detect the output language for a message: ``"en"``, ``"hi"``, or ``"hinglish"``."""
    tag = _tag_language(text, HINGLISH_MARKERS_EXTENDED, long_text_words=LONG_TEXT_WORDS)
    return _TAG_TO_LANGUAGE.get(tag, "en")


LANGUAGE_NAMES: dict[Language, str] = {
    "en": "English",
    "hi": "Hindi (Devanagari script)",
    "hinglish": "Hinglish (Hindi words written in Latin script, as commonly typed in SMS/WhatsApp)",
}
