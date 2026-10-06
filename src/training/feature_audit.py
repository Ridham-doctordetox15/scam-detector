"""Feature audit: do a model's top features look like scam signals or corpus fingerprints?

Phase 3.5 success criterion, fixed *before* any cleaning experiment was run:

* **Fingerprints** are tokens that identify a *corpus* rather than a scam: Enron names,
  email quote/forward boilerplate, years from the 1990s-2000s, the UK pound sign, mailing-list
  vocabulary, Singaporean SMS slang, web-crawl markers.
* **Signals** are terms a consumer would recognise as scam cues: urgency and threats, KYC and
  account verification, OTP/credentials, prizes, links and contact prompts, fees and money.

A configuration PASSES when the top-:data:`TOP_N` features of the *word-only audit model*

1. contain **zero** fingerprints for both classes, and
2. have a scam-class signal share of at least :data:`MIN_SCAM_SIGNAL_SHARE`.

The lexicon and blocklist below are deliberately conservative. They were revised exactly once
after first looking at the Phase 3 features (to fix a substring bug that mislabelled "free" as a
fingerprint, and to add HTML-quote/reply boilerplate and link cues) and were frozen before any
Phase 3.5 ablation ran. Change them only with a written reason in results.md.

Amendment 1 (2026-09-26, before any ablation result): added ``cur``, the token that the
currency normaliser (``normalize.py``) writes in place of ``rs``/``inr``/currency symbols, which
were already signals; without it a cleaned model would lose credit for money words it still
uses.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression

TOP_N = 30
MIN_SCAM_SIGNAL_SHARE = 0.50
AUDIT_C = 10.0     # word-only audit model: TF-IDF word 1-2-grams + Logistic Regression

# --------------------------------------------------------------------------- #
# Scam-signal lexicon (English + romanized Hindi/Hinglish + masked-token names)
# --------------------------------------------------------------------------- #
SIGNAL_TERMS: frozenset[str] = frozenset(
    """
    urgent urgently immediately immediate asap expire expires expired expiring deadline hurry
    jaldi turant abhi warna varna otherwise suspend suspended suspension block blocked
    deactivate deactivated disconnect disconnected disconnection terminate terminated freeze
    frozen penalty legal arrest warrant cancel cancelled action required
    kyc pan aadhaar aadhar verify verification verified update confirm validate authenticate
    account bank banking upi wallet paytm phonepe gpay sbi hdfc icici axis kotak
    otp pin password passcode cvv code login credentials details
    prize winner won win lottery lucky draw reward cashback gift congratulations congrats claim
    free offer bonus jackpot kbc voucher coupon scratch selected
    click link url http https www bit ly visit call phone whatsapp telegram download install app apk
    reply register apply txt sms
    cur
    fee fees charge charges payment pay refund tax customs deposit amount rs rupees inr loan credit
    emi processing advance earn income salary invest profit guaranteed
    parcel courier delivery package bill electricity dues job
    kripya jeeta jeete inaam paisa rupaye khata band
    """.split()
)
# Word stems of length >= 5 that count as signals when a token starts with them.
SIGNAL_STEMS: tuple[str, ...] = (
    "verif", "suspen", "expir", "urgen", "immedi", "congrat", "guarant", "authent", "blocked",
    "disconn", "deactiv", "cancell", "penalt", "reward", "lotter",
)

# --------------------------------------------------------------------------- #
# Corpus-fingerprint blocklist
# --------------------------------------------------------------------------- #
FINGERPRINT_TERMS: frozenset[str] = frozenset(
    """
    enron enronxgate hpl ect hou ees kaminski vince daren houston stinson crenshaw
    forwarded original message cc wrote gt lt amp nbsp university
    linguist linguists linguistics grammar semantics discourse theoretical syntax phonology
    lexical corpus conference workshop redhat linux
    newsisfree livejournal
    lor wat dun liao leh lar mah cos
    nab visa
    """.split()
)
# Long fingerprint words also match as substrings (char n-grams such as "enr", "nro").
FINGERPRINT_LONG_WORDS: tuple[str, ...] = ("enron", "kaminski", "enronxgate", "linguist")
_YEAR_RE = re.compile(r"\b(?:199\d|200\d|2010)\b")
_FINGERPRINT_CHARS = (">", "£", "£")

_PREFIX_RE = re.compile(r"^(?:word|char)__")


@dataclass(frozen=True)
class FeatureClass:
    """Category of one model feature."""

    name: str        # the cleaned feature text
    category: str    # signal | fingerprint | format | other


def clean_feature_name(name: str) -> str:
    """Drop the ``word__`` / ``char__`` prefix (kept spaces are trimmed) and lowercase."""
    return _PREFIX_RE.sub("", name).strip().lower()


def classify_feature(name: str) -> str:
    """Return ``fingerprint``, ``signal``, ``format`` or ``other`` for one feature.

    Order matters: a fingerprint wins over a signal (a feature such as "forwarded message" is
    email boilerplate even though "message" is harmless), and punctuation-only n-grams are
    ``format``. Character n-grams are treated as their text; short n-grams (< 4 letters) never
    count as signals, to avoid crediting accidental substrings.
    """
    text = clean_feature_name(name)
    if not text:
        return "format"
    tokens = re.findall(r"[a-z0-9£>]+", text)
    if any(ch in text for ch in _FINGERPRINT_CHARS) or _YEAR_RE.search(text):
        return "fingerprint"
    if any(t in FINGERPRINT_TERMS for t in tokens):
        return "fingerprint"
    alpha = re.sub(r"[^a-z]", "", text)
    is_signal_word = alpha in SIGNAL_TERMS
    if len(alpha) >= 3 and not is_signal_word and any(alpha in w for w in FINGERPRINT_LONG_WORDS):
        return "fingerprint"
    if not re.search(r"[a-z0-9]", text):
        return "format"
    if any(t in SIGNAL_TERMS or (len(t) >= 5 and t.startswith(SIGNAL_STEMS)) for t in tokens):
        return "signal"
    if len(alpha) >= 4 and " " not in text and any(alpha in w for w in SIGNAL_TERMS if len(w) >= 5):
        return "signal"       # a character n-gram inside a signal word, e.g. "urge" in "urgent"
    return "other"


def classify_features(names: list[str]) -> list[FeatureClass]:
    """:func:`classify_feature` over many names."""
    return [FeatureClass(clean_feature_name(n), classify_feature(n)) for n in names]


# --------------------------------------------------------------------------- #
# Audit
# --------------------------------------------------------------------------- #
def audit_top_features(top: pd.DataFrame, n: int = TOP_N) -> dict[str, dict]:
    """Summarise a top-feature table (columns ``class``, ``feature``, ``weight``).

    Returns:
        ``{"scam": {...}, "safe": {...}}`` with counts of each category among the top-``n``
        features, the signal share, the fingerprints found and the features themselves.
    """
    out: dict[str, dict] = {}
    for cls in ("scam", "safe"):
        part = top[top["class"] == cls].head(n)
        cats = classify_features(part["feature"].tolist())
        counts = {c: sum(f.category == c for f in cats) for c in ("signal", "fingerprint", "format", "other")}
        out[cls] = {
            "n": len(part), **counts,
            "signal_share": counts["signal"] / max(len(part), 1),
            "fingerprints": [f.name for f in cats if f.category == "fingerprint"],
            "signals": [f.name for f in cats if f.category == "signal"],
            "features": [f.name for f in cats],
        }
    return out


def passes(audit: dict[str, dict]) -> bool:
    """The pre-registered pass rule (see the module docstring)."""
    return (audit["scam"]["fingerprint"] == 0 and audit["safe"]["fingerprint"] == 0
            and audit["scam"]["signal_share"] >= MIN_SCAM_SIGNAL_SHARE)


def word_audit_model(train_texts: list[str], y_train: np.ndarray, seed: int = 42):
    """Interpretable audit model: TF-IDF word 1-2-grams + Logistic Regression (balanced)."""
    vec = TfidfVectorizer(analyzer="word", ngram_range=(1, 2), min_df=2, sublinear_tf=True, dtype=np.float32)
    x = vec.fit_transform(train_texts)
    clf = LogisticRegression(solver="liblinear", C=AUDIT_C, class_weight="balanced", random_state=seed, max_iter=1000)
    return vec, clf.fit(x, y_train)


def top_features_of(vectorizer, clf, n: int = TOP_N) -> pd.DataFrame:
    """Top-``n`` highest-weight features per class for a linear model."""
    names = np.asarray(vectorizer.get_feature_names_out())
    coef = np.asarray(clf.coef_).ravel()
    order = np.argsort(coef)
    rows = [("scam", names[i], float(coef[i])) for i in order[::-1][:n]]
    rows += [("safe", names[i], float(coef[i])) for i in order[:n]]
    return pd.DataFrame(rows, columns=["class", "feature", "weight"])


def format_audit(audit: dict[str, dict], title: str) -> str:
    """One-paragraph text summary of an audit."""
    lines = [title]
    for cls in ("scam", "safe"):
        a = audit[cls]
        lines.append(f"  {cls}: signal {a['signal']}/{a['n']} ({a['signal_share']:.0%}), "
                     f"fingerprint {a['fingerprint']}, format {a['format']}, other {a['other']}")
        if a["fingerprints"]:
            lines.append(f"    fingerprints: {', '.join(a['fingerprints'][:12])}")
    lines.append(f"  PASS: {passes(audit)}")
    return "\n".join(lines)
