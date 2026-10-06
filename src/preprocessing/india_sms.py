"""Helpers for the Kaggle ``junioralive/india-spam-sms-classification`` dataset.

A 100-row manual spot check (Phase 3.5) showed that this dataset is *not* "scam vs safe":

* Its **spam** class is ~90% legitimate brand promotions (Airtel, Vi, Lenskart, Pantaloons,
  credit-card offers), ~8% service notices or personal messages that are not spam at all, and
  only ~2% fraud (a fake lottery in the sample: promo:fraud about 54:1).
* Its **ham** class is WhatsApp group chat about stock trading and office chatter, with
  occasional mojibake.

The binary label is kept as the source gives it (spam -> scam) for now, but every spam row gets
a ``subtype`` so the effect can be measured and later handled deliberately.
"""
from __future__ import annotations

import re

_FRAUD_RE = re.compile(
    r"\b(crore|lottery|winning fund|kbc|kyc|aadhaar|aadhar|arrest|customs|"
    r"share (?:your )?otp|(?:account|sim|number)\s+(?:will be|has been|is going to be|is)\s+"
    r"(?:blocked|suspended|frozen|disconnected|deactivated))\b",
    re.IGNORECASE,
)
_SHARE_OTP_RE = re.compile(r"(?<!not )(?<!n't )\bshare (?:your |the )?otp\b", re.IGNORECASE)
_SERVICE_RE = re.compile(
    r"\byour otp\b|\botp (?:for|is)\b|do not share|missed call|data quota|as on \d|to cancel a vas|"
    r"sms stop to|credited to your (?:a/c|account)|debited",
    re.IGNORECASE,
)
# Manually reviewed rows the regex mis-tags (the 5 rows it called "fraud" were read one by one;
# only the fake-lottery message is real fraud). Keys are message prefixes, whitespace-normalised and case-folded.
_REVIEWED_PREFIXES: dict[str, str] = {
    "dear , prize pool- 5,00,00,000": "promo",        # Junglee Rummy gaming ad
    "dear employee, get rs. 250 cash": "promo",       # Refyne salary-advance app promo
    "uidai recommends updating proof": "service",     # genuine UIDAI notice
    "beware of fake calls claiming t": "service",     # DoT anti-fraud awareness message
}
def repair_mojibake(text: str, max_rounds: int = 2) -> str:
    """Undo UTF-8 text that was decoded as Latin-1 (once or twice), e.g. an emoji shown as ``Ã°Â...``.

    Each round re-encodes as Latin-1 and decodes as UTF-8. Text that is already clean (or whose
    accented letters do not form valid UTF-8, like "café") fails that round and is returned
    unchanged, so repair is lossless.
    """
    current = text
    for _ in range(max_rounds):
        if not any("" <= ch <= "ÿ" for ch in current):
            break
        try:
            repaired = current.encode("latin-1").decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            break
        if repaired == current:
            break
        current = repaired
    return current


def spam_subtype(text: str) -> str:
    """Heuristic subtype of a *spam*-labelled message: ``fraud``, ``service`` or ``promo``.

    ``fraud`` needs a strong fraud cue (lottery/crore, KYC, arrest, customs, "account will be
    blocked", "share your OTP") and no service-notice cue; ``service`` marks transactional
    notices (OTPs, missed calls, usage alerts); everything else is a ``promo``. This is a
    rule-of-thumb validated on a 60-row manual sample (59/60 agreement), plus manual overrides for
    the few rows it mis-tags; not ground truth.
    """
    normalised = " ".join(text.split()).casefold()
    for prefix, subtype in _REVIEWED_PREFIXES.items():
        if normalised.startswith(prefix):
            return subtype
    if _SHARE_OTP_RE.search(text):          # asking for the OTP is fraud even though "your OTP" is a service cue
        return "fraud"
    service = bool(_SERVICE_RE.search(text))
    if _FRAUD_RE.search(text) and not service:
        return "fraud"
    return "service" if service else "promo"
