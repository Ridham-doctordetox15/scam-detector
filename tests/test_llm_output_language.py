"""Output-language tests for the explainer (en / hi / hinglish), with mocked LLM responses.

Regression for the Phase 9 finding: "Bhai kal 1 baje lunch pe milte hain,
office ke paas wale cafe mein?" was answered in English because the
explainer's own, smaller word list matched only "hain".
"""
from __future__ import annotations

import json

import pytest

from src.llm import explainer as X
from src.llm.language import LONG_TEXT_WORDS, detect_language
from src.llm.templates import summary_sentence
from src.preprocessing.language import HINGLISH_MARKERS, HINGLISH_MARKERS_EXTRA
from src.preprocessing.language import detect_language as phase2_tag
from src.rag.rag_engine import RetrievalResult
from tests.test_llm_explainer import groq_response, make_groq_client_factory

NO_MATCH = RetrievalResult(query="x", matches=[], confident=False)

HINGLISH_SAFE = "Bhai kal 1 baje lunch pe milte hain, office ke paas wale cafe mein?"
HINGLISH_SCAM = "Aapka SBI khata band ho jayega, turant KYC update karo is link se: <URL>"
HINDI_SCAM = "आपका बैंक खाता बंद हो जाएगा। तुरंत KYC अपडेट करें: <URL>"
ENGLISH_SCAM = "Dear customer, your KYC is pending and your account will be blocked today. Update: <URL>"


# ------------------------------------------------------------------ detection
@pytest.mark.parametrize("text, expected", [
    (HINGLISH_SAFE, "hinglish"),                     # the regression
    (HINGLISH_SCAM, "hinglish"),
    ("Wallet 3 lakh limit ke liye verification pending, jaldi karo", "hinglish"),
    ("Mujhe kal paise wapas chahiye", "hinglish"),
    (HINDI_SCAM, "hi"),
    (ENGLISH_SCAM, "en"),
    ("Hi, are we still on for lunch tomorrow at 1pm?", "en"),
    ("Namaste, your Amazon order is out for delivery", "en"),        # one Hindi greeting only
    ("Please call me about the पूजा booking tomorrow evening at the hall", "en"),  # one Devanagari word
    ("Yo bhai, your PhonePe account is on hold", "en"),              # a single marker is not enough
])
def test_detect_output_language(text: str, expected: str) -> None:
    assert detect_language(text) == expected


def test_long_english_text_needs_three_markers() -> None:
    filler = " ".join(["the meeting agenda covers budgets"] * 15)  # > LONG_TEXT_WORDS words
    assert len(filler.split()) > LONG_TEXT_WORDS
    assert detect_language(f"{filler} ke ki") == "en"             # 2 markers by chance in a long email
    assert detect_language(f"{filler} ke ki aapka") == "hinglish"  # 3 distinct markers
    assert detect_language("ke ki short note") == "hinglish"       # short text: 2 suffice


def test_phase2_data_tags_are_unchanged_by_the_extension() -> None:
    # The Phase 1-2 tagger keeps its original marker list (reproducible data tags).
    only_extended = "Mujhe kal paise wapas chahiye"  # Phase 2 list matches only "paise"
    assert phase2_tag(only_extended) == "en"
    assert detect_language(only_extended) == "hinglish"
    # Words that collide with English (or are too common in real English) stay out.
    assert not (HINGLISH_MARKERS_EXTRA | HINGLISH_MARKERS) & {"se", "ya", "pe", "lag", "ji", "haan", "to", "me",
                                                              "main", "par", "is", "hi", "band", "mat"}


# ------------------------------------------------------------------ prompt
@pytest.mark.parametrize("text, language_name, script_fragment", [
    (ENGLISH_SCAM, "English", "plain, simple English"),
    (HINDI_SCAM, "Hindi (Devanagari script)", "Use Devanagari script"),
    (HINGLISH_SAFE, "Hinglish", "do NOT use Devanagari script and do NOT reply in pure English"),
])
def test_prompt_requests_language_for_every_text_field(text, language_name, script_fragment) -> None:
    lang = detect_language(text)
    verdict = X.compute_verdict(False, 0.1, None)
    prompt = X.build_prompt(text, False, 0.1, [], NO_MATCH, lang, verdict)
    assert f'"red_flags": a list of short strings, written in {language_name}' in prompt
    assert f"written in {language_name}" in prompt.split('"explanation"')[1]
    assert f"what_to_do" in prompt and f"OUTPUT LANGUAGE: write every text value" in prompt
    assert script_fragment in prompt
    assert "Keep brand names, amounts and the <URL>/<PHONE>/<OTP> tokens unchanged" in prompt


# ------------------------------------------------------------------ mocked LLM round trips
LLM_OUTPUTS = {
    "en": {
        "verdict": "scam", "risk_level": "high",
        "red_flags": ["Threat to block the account", "Link to update KYC"],
        "explanation": "This message pretends to be your bank and pushes you to update KYC through a link.",
        "what_to_do": ["Do not click the link.", "Call your bank on its official number."],
        "matched_pattern": None,
    },
    "hi": {
        "verdict": "scam", "risk_level": "high",
        "red_flags": ["खाता बंद करने की धमकी", "KYC अपडेट के लिए लिंक"],
        "explanation": "यह संदेश बैंक होने का दिखावा करता है और लिंक से KYC अपडेट करने का दबाव डालता है।",
        "what_to_do": ["लिंक पर क्लिक न करें।", "बैंक के आधिकारिक नंबर पर कॉल करें।"],
        "matched_pattern": None,
    },
    "hinglish": {
        "verdict": "safe", "risk_level": "low",
        "red_flags": [],
        "explanation": "Yeh ek normal personal message hai, dost lunch ke liye mil rahe hain. Koi link ya paise ki maang nahi hai.",
        "what_to_do": ["Koi khaas action ki zaroorat nahi.", "Anjaan links par phir bhi dhyan rakhein."],
        "matched_pattern": None,
    },
}


@pytest.mark.parametrize("text, lang, is_scam, prob", [
    (ENGLISH_SCAM, "en", True, 0.97),
    (HINDI_SCAM, "hi", True, 0.97),
    (HINGLISH_SAFE, "hinglish", False, 0.05),
])
def test_explain_returns_llm_text_in_the_message_language(monkeypatch, text, lang, is_scam, prob) -> None:
    session = make_groq_client_factory(monkeypatch, [groq_response(LLM_OUTPUTS[lang])])
    result = X.explain(text, is_scam, prob, [], NO_MATCH, groq_api_key="k", gemini_api_key="")
    assert result.path == "groq"
    out = result.output
    expected = LLM_OUTPUTS[lang]
    # The language-specific prose survives validation + sanitization unchanged.
    assert out.explanation == expected["explanation"]
    assert out.red_flags == expected["red_flags"] and out.what_to_do == expected["what_to_do"]
    assert detect_language(" ".join([out.explanation, *out.what_to_do])) == lang
    # And the request actually asked for that language.
    sent = json.dumps(session.requests[0]["json"], ensure_ascii=False)
    assert X.LANGUAGE_NAMES[lang].split(" (")[0] in sent


def test_hinglish_regression_prompt_is_not_english(monkeypatch) -> None:
    session = make_groq_client_factory(monkeypatch, [groq_response(LLM_OUTPUTS["hinglish"])])
    X.explain(HINGLISH_SAFE, False, 0.05, [], NO_MATCH, groq_api_key="k", gemini_api_key="")
    sent = json.dumps(session.requests[0]["json"], ensure_ascii=False)
    assert "written in Hinglish" in sent and "written in English" not in sent


# ------------------------------------------------------------------ template fallback (no LLM)
@pytest.mark.parametrize("text, lang", [(ENGLISH_SCAM, "en"), (HINDI_SCAM, "hi"), (HINGLISH_SCAM, "hinglish")])
def test_template_fallback_summary_uses_the_message_language(text, lang) -> None:
    result = X.explain(text, True, 0.97, [], NO_MATCH, groq_api_key="", gemini_api_key="")
    assert result.path == "template"
    assert result.output.explanation.startswith(summary_sentence(lang, "scam", None))


def test_template_summaries_differ_by_language() -> None:
    en, hi, hl = (summary_sentence(lang, "scam", None) for lang in ("en", "hi", "hinglish"))
    assert len({en, hi, hl}) == 3
    assert any("ऀ" <= c <= "ॿ" for c in hi)
    assert not any("ऀ" <= c <= "ॿ" for c in hl) and detect_language(hl) == "hinglish"


@pytest.mark.parametrize("text, lang", [(ENGLISH_SCAM, "en"), (HINDI_SCAM, "hi"), (HINGLISH_SAFE, "hinglish")])
def test_explain_result_carries_language_on_both_paths(monkeypatch, text, lang) -> None:
    assert X.explain(text, True, 0.97, [], NO_MATCH, groq_api_key="", gemini_api_key="").language == lang
    make_groq_client_factory(monkeypatch, [groq_response(LLM_OUTPUTS[lang])])
    assert X.explain(text, True, 0.97, [], NO_MATCH, groq_api_key="k", gemini_api_key="").language == lang
