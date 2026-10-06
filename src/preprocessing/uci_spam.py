"""Promo / fraud / service tagging for the UCI SMS "spam" class.

UCI "spam" means *unsolicited or commercial*, which is broader than *scam*. A manual read of all
546 unique UCI spam rows (Phase 3.5) found roughly one third fraud (fake prize/award lures and
"call this number" pretexts), about 55% promotions (ringtones, chat lines, phone-upgrade deals,
competitions) and about 10% service or personal messages that are not spam at all. This module
tags every spam row so the project's scam definition (``docs/label_rubric.md``) can be applied
deliberately.

The rule started from a 100-row manual sample and was extended after every row the rule called
``fraud`` and every row it did not were read by hand, so it reproduces that full manual review
(see ``tests/test_uci_spam.py`` for regression examples taken from it). It is a rule of thumb for
*this* corpus, not a general classifier.
"""
from __future__ import annotations

import re

_PRIZE_WORDS = (
    r"(?:£|\bcash\b|\bprize\b|\baward|\bholiday|\bbonus\b|\bvoucher|\bgift\b|\btrip\b|\bflights?\b|\btickets?\b|"
    r"\b\d{3,},?\d* ?pounds\b)"
)
# 1. an assertion that the reader has won / been chosen or awarded something of value
_WON = re.compile(
    r"(?:\b(?:u|you)(?: have| 've|'ve)? ?(?:just )?won(?!')\b|\byou are (?:chosen|selected)\b|\bhave been (?:awarded|selected)\b|"
    r"\bawarded\b|\bselected (?:2|to)(?: a)? receive|\bchosen to receive\b|\bwon (?:a|the|this)\b|"
    r"\bwon(?!')\b.{0,30}" + _PRIZE_WORDS + r"|randomly picked you|computer has (?:selected|picked)|"
    r"reward is waiting|selected to stay)",
    re.IGNORECASE,
)
# 2. collect-your-prize mechanics
_CLAIM = re.compile(
    r"(?:\bawaits? collection\b|\bawait collection\b|\burgent collection\b|\bunclaimed\b|\bcall (?:b4|before)\b|"
    r"\bto claim,? ?(?:call|txt|text|ring|speak)|\bclaim (?:code|number|now)\b|\bcan claim\b.{0,40}" + _PRIZE_WORDS +
    r"|\bclaim\b.{0,30}" + _PRIZE_WORDS + r"|final notice to collect|prize will go to another|"
    r"claim your.{0,30}passes|claim ur med holiday|stamped self|"
    r"either .{0,30}cash.{0,30}voucher.{0,40}call now|entitled to \d[\d,]* pounds)",
    re.IGNORECASE,
)
# 3. pretexts that make the reader call a premium number
_PRETEXT = re.compile(
    r"(?:important (?:customer service )?(?:announcement|message|information)|customer service ann\w*|"
    r"new voicemail|\bmissed call\b|you have 1 new message.{0,20}call|"
    r"attempt to (?:contact|reach).{0,60}\bcall\b|final contact attempt|urgent.{0,40}\bcall\b|\bcall\b.{0,25}immediately|"
    r"secret admirer|somebody you know|someon\w* you know|know that fancies you|someone shy|"
    r"entitled to.{0,40}compensation|compensation for the accident|"
    r"retrieve your messages|your lucky day|"
    r"dating service.{0,60}(?:fancy you|contact you|entered your)|"
    r"(?:awaiting your collection|message awaiting)|"
    r"you are guaranteed.{0,60}(?:prize|phone|ipod|cash)|"
    r"\br yours\b|are yours!? ?call|billed your mobile.{0,40}mistake|"
    r"un-?redeemed|your \d{4} account statement|"
    r"congrats!?.{0,60}(?:is|are) (?:yours?|your)|"
    r"guaranteed.{0,50}(?:prize|proze|nokia|ipod|cash|phone)|(?:prize|proze|nokia|ipod).{0,40}guaranteed|"
    r"explosive pick|strong-?buy|nasdaq symbol|to listen to email call|call freephone \d{4} \d{3} \d{4} now)",
    re.IGNORECASE,
)
_SERVICE = re.compile(
    r"(?:thanks for your .{0,20}order|\bwelcome!|has been resent|resent as previous attempt|hope you enjoyed your new content|"
    r"subscription has been renewed|your subs has now expired|thanks for your subscription|"
    r"you will (?:rec[ie]+ve|be receiving) (?:your|this week)|renewal pin|topped up|outbid by|monthly password|"
    r"you(?:'ve| have) been (?:charged|billed)|sorry! u can not unsubscribe|not downloaded the content|"
    r"thanks for using the auction subscription|sorry, a service you ordered|recpt \d/\d|you have ordered a ringtone)",
    re.IGNORECASE,
)
# Anything that looks commercial. A "spam" row without any of these is probably an ordinary message.
_COMMERCIAL = re.compile(
    r"(?:£|\d+ ?p\b|ppm|\btxt\b|\btext\b.{0,20}\bto\b|\breply\b|\bcall\b|www\.|\.co\b|\.com|\bstop\b|\bfree\b|\bclub\b|\boffer\b|"
    r"\btones?\b|\bcongrat|\burgent|\bprize\b|\bwin\b|\bclaim\b|\d{5})",
    re.IGNORECASE,
)
_SUBSCRIPTION = re.compile(
    r"(?:£ ?\d+(?:\.\d+)? ?sub|\bsub\b|subscri|/wk|per ?wk|/mnth|a month|unsub)", re.IGNORECASE
)
# Rows read by hand that the rules cannot separate from fraud, or that are ordinary messages the
# source mislabelled. Keys are message prefixes (whitespace-normalised, case-folded).
_REVIEWED_SUBTYPES: dict[str, str] = {
    "call from 08702490080 - tells u 2 call": "service",      # a warning *about* a prize scam
    "phony £350 award": "service",                            # someone forwarding a scam and calling it phony
    "you have won a guaranteed 32000 award": "service",       # forwarded prize scam with "what do u think???"
    "hi ya babe x u 4goten bout me": "service",               # "scammers getting smart" warning
    "88066 from 88066 lost": "service",                       # personal message about a charge
    "from 88066 lost": "service",
    "asked 3mobile if 0870 chatlines": "service",             # personal complaint
    "bought one ringtone and now getting": "service",         # personal complaint
    "tbs/persolvo": "service",                                # business chatter
    "money i have won wining number": "service",              # chat
    "sunshine hols. to claim ur med holiday": "fraud",        # prize-claim lure that also prints "Unsub Stop"
}


def uci_spam_subtype(text: str) -> str:
    """Tag a UCI *spam*-labelled message as ``fraud``, ``promo`` or ``service``.

    * ``fraud``: says the reader has won/been awarded something, describes collecting it, or uses
      a pretext (voicemail, missed call, "customer service announcement", compensation, secret
      admirer, "someone you know") to make them call a number.
    * ``service``: a transactional notice, or a message with no commercial markers at all
      (ordinary chat that the source mislabelled).
    * ``promo``: everything else (ringtones, chat lines, phone deals, competitions, discount
      vouchers with a disclosed subscription price).
    """
    normalised = " ".join(text.split()).casefold()
    for prefix, subtype in _REVIEWED_SUBTYPES.items():
        if normalised.startswith(prefix):
            return subtype
    if _WON.search(text) or _PRETEXT.search(text):
        return "fraud"
    if _CLAIM.search(text) and not _SUBSCRIPTION.search(text):   # "claim ur vouchers ... £3 Sub" is a promo
        return "fraud"
    if _SERVICE.search(text) or not _COMMERCIAL.search(text):
        return "service"
    return "promo"
