"""Lightweight language tagging for real (non-synthetic) messages.

Uses only the standard library. The tagger is a *heuristic*, not a language
identifier:

* Unicode script decides native-script text (Devanagari, Tamil, ...).
* A small list of very common romanized-Hindi words tags likely Hinglish.

Limits (document these wherever results are reported):

* ``hi`` means "Devanagari script". Marathi, Nepali and Sanskrit share the
  script and are also tagged ``hi``.
* ``hinglish_guess`` needs at least :data:`HINGLISH_MIN_HITS` distinct marker
  words. Very short Hinglish messages, or Hinglish that avoids these words,
  are tagged ``en``. English text that quotes Hindi words can be a false
  positive.
* Other romanized Indian languages (Tanglish, Benglish, ...) are not detected
  and fall into ``en``.
* Real English-language corpora in this project are overwhelmingly English, so
  ``en`` is the expected outcome for them.
"""
from __future__ import annotations

import re
import unicodedata

# Unicode ranges of Indic scripts -> language tag.
_SCRIPT_RANGES: dict[str, tuple[int, int]] = {
    "hi": (0x0900, 0x097F),   # Devanagari
    "bn": (0x0980, 0x09FF),   # Bengali
    "pa": (0x0A00, 0x0A7F),   # Gurmukhi
    "gu": (0x0A80, 0x0AFF),   # Gujarati
    "or": (0x0B00, 0x0B7F),   # Odia
    "ta": (0x0B80, 0x0BFF),   # Tamil
    "te": (0x0C00, 0x0C7F),   # Telugu
    "kn": (0x0C80, 0x0CFF),   # Kannada
    "ml": (0x0D00, 0x0D7F),   # Malayalam
}

# Share of alphabetic characters that must be in one Indic script for the
# message to be tagged with that script's language.
INDIC_SCRIPT_THRESHOLD = 0.2

# Romanized-Hindi words that are (almost) never English words. Deliberately
# excludes English collisions such as "to", "me", "main", "par", "ho", "is",
# "hi", "mat", "band", "lie", "ji".
HINGLISH_MARKERS: frozenset[str] = frozenset(
    """
    hai hain tha thi hoga hogi honge raha rahi rahe rahega
    kya kyun kyu kaise kab kahan kaun kitna kitne
    aap aapka aapke aapki apna apni apka apke tum tumhara hum humara mera meri mere
    nahi nahin
    karo kro kijiye kijie kare karein kiya kiye karna karenge
    jayega jaayega jayegi gaya gayi gaye
    abhi turant jaldi aaj
    liye wala wale wali sath saath mein
    aur lekin magar isliye kyunki kyonki
    yeh woh isko usko unko
    bhi toh
    paisa paise rupaye rupay
    bhai dost
    kripya dhanyavaad shukriya
    milega milegi
    chalu
    """.split()
)

# Additional markers used only for choosing the explainer's OUTPUT language (added
# 2026-09-30). Kept separate so the Phase 1-2 data tags above stay reproducible.
# Each word was checked against 21,145 real English messages (train/val/test): all
# occur in 0-1 of them, except ke/ki/ka/ko/hua/hui (6-18 each, ~0.07%). Those are safe
# because a message needs HINGLISH_MIN_HITS *distinct* markers. Deliberately left out:
# se (219 messages), ya (110), pe (35), lag (17), ji (10), haan (6).
HINGLISH_MARKERS_EXTRA: frozenset[str] = frozenset(
    """
    ke ki ka ko hua hui
    baje milte milenge atka bharo karke batao chahiye sakte sakta wapas paas
    yahan wahan kuch sab bahut accha acha theek thik
    mujhe tujhe tera teri tere hamare unka unki uska uski raho
    dijiye bataiye bhejiye sirf zaroor jarur lagta yaar
    """.split()
)
HINGLISH_MARKERS_EXTENDED: frozenset[str] = HINGLISH_MARKERS | HINGLISH_MARKERS_EXTRA

# Minimum number of *distinct* marker words for a "hinglish_guess" tag.
HINGLISH_MIN_HITS = 2

_WORD_RE = re.compile(r"[a-z]+")


def _letters(text: str) -> list[str]:
    """Alphabetic characters plus combining marks.

    ``str.isalpha`` is False for Indic vowel signs (e.g. Devanagari matras), which
    would undercount native-script text, so category-M characters are included.
    """
    return [c for c in text if c.isalpha() or unicodedata.category(c).startswith("M")]


def _indic_language(text: str) -> str | None:
    """Return the Indic-script language tag if the script dominates enough."""
    letters = _letters(text)
    if not letters:
        return None
    counts: dict[str, int] = {}
    for ch in letters:
        cp = ord(ch)
        for tag, (lo, hi) in _SCRIPT_RANGES.items():
            if lo <= cp <= hi:
                counts[tag] = counts.get(tag, 0) + 1
                break
    if not counts:
        return None
    tag, n = max(counts.items(), key=lambda kv: kv[1])
    return tag if n / len(letters) >= INDIC_SCRIPT_THRESHOLD else None


def is_likely_hinglish(text: str, markers: frozenset[str] = HINGLISH_MARKERS,
                       long_text_words: int | None = None) -> bool:
    """True if ``text`` contains enough distinct romanized-Hindi marker words.

    With ``long_text_words`` set, texts longer than that many words need one more
    distinct marker: in long English emails two short markers co-occur by chance.
    """
    words = _WORD_RE.findall(text.lower())
    needed = HINGLISH_MIN_HITS + (1 if long_text_words is not None and len(words) > long_text_words else 0)
    return len(set(words) & markers) >= needed


def detect_language(text: str, markers: frozenset[str] = HINGLISH_MARKERS,
                    long_text_words: int | None = None) -> str:
    """Tag ``text`` as an Indic-script code, ``hinglish_guess``, ``other`` or ``en``.

    ``markers`` defaults to the Phase 1-2 list (reproducible data tags); the
    explainer passes :data:`HINGLISH_MARKERS_EXTENDED`. See the module
    docstring for the limits of this heuristic.
    """
    tag = _indic_language(text)
    if tag is not None:
        return tag
    letters = _letters(text)
    if letters and sum(c.isascii() for c in letters) / len(letters) < 0.5:
        return "other"  # mostly non-Latin, non-Indic script (e.g. Cyrillic, CJK)
    if is_likely_hinglish(text, markers, long_text_words):
        return "hinglish_guess"
    return "en"
