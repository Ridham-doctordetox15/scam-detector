"""Deterministic, no-LLM fallback content (used when both providers fail).

Scope, as agreed for this phase: the localized verdict summary sentence is
fully translated (en/hi/hinglish), but the dynamic detail lines - URL-analyzer
reasons (:mod:`src.url_analyzer.analyzer`) and knowledge-base
red_flags/what_to_do (:mod:`src.rag.schema`) - stay in English, since both are
authored in English and full translation would need either a translation
dependency or a hand-written phrase table per language per possible flag.
Only the LLM path (the common case, when a provider is reachable) fully
localizes everything.
"""
from __future__ import annotations

from src.llm.language import Language
from src.llm.rules import Verdict

# {language: {verdict: sentence}}. ``{pattern}`` is filled with the matched
# knowledge-base entry's name when there is a confident RAG match.
_SUMMARY_WITH_PATTERN: dict[Language, dict[Verdict, str]] = {
    "en": {
        "scam": "This message shows signs of a {pattern} scam.",
        "suspicious": "This message has some suspicious signs resembling a {pattern} scam.",
        "safe": "This message matches a known legitimate pattern: {pattern}.",
    },
    "hi": {
        "scam": "यह संदेश {pattern} जैसे घोटाले जैसा लगता है।",
        "suspicious": "इस संदेश में {pattern} जैसे घोटाले के कुछ संदिग्ध संकेत हैं।",
        "safe": "यह संदेश एक ज्ञात सुरक्षित पैटर्न से मेल खाता है: {pattern}।",
    },
    "hinglish": {
        "scam": "Yeh message {pattern} scam jaisa lagta hai.",
        "suspicious": "Iss message mein {pattern} scam jaise kuch suspicious signs hain.",
        "safe": "Yeh message ek jaana-pehchana safe pattern jaisa hai: {pattern}.",
    },
}

_SUMMARY_NO_PATTERN: dict[Language, dict[Verdict, str]] = {
    "en": {
        "scam": "This message shows signs of being a scam.",
        "suspicious": "This message has some suspicious signs and should be treated with caution.",
        "safe": "This message does not show signs of being a scam.",
    },
    "hi": {
        "scam": "यह संदेश एक घोटाला लग रहा है।",
        "suspicious": "इस संदेश में कुछ संदिग्ध संकेत हैं, सावधान रहें।",
        "safe": "यह संदेश घोटाला नहीं लगता।",
    },
    "hinglish": {
        "scam": "Yeh message scam jaisa lagta hai.",
        "suspicious": "Iss message mein kuch suspicious signs hain, savdhaan rahein.",
        "safe": "Yeh message scam jaisa nahi lagta.",
    },
}

_GENERIC_ADVICE: dict[Verdict, list[str]] = {
    "scam": [
        "Do not click any links, call any numbers, or share OTPs/PINs/bank details.",
        "Do not send any money.",
        "Verify independently through the official app or website, never through this message.",
        "Block the sender and report it if possible.",
    ],
    "suspicious": [
        "Do not click any links or share personal/financial details yet.",
        "Verify the sender independently through an official app, website, or phone number you already trust.",
    ],
    "safe": [
        "No action needed. If anything about the sender or request still feels off, verify independently.",
    ],
}


def summary_sentence(language: Language, verdict: Verdict, pattern_name: str | None) -> str:
    """The localized one-line verdict summary for the template fallback."""
    table = _SUMMARY_WITH_PATTERN if pattern_name else _SUMMARY_NO_PATTERN
    sentence = table[language][verdict]
    return sentence.format(pattern=pattern_name) if pattern_name else sentence


def generic_advice(verdict: Verdict) -> list[str]:
    """English-language fallback advice when there's no matched knowledge-base entry."""
    return list(_GENERIC_ADVICE[verdict])
