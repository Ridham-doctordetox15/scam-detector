"""Clean raw OCR output from a chat/SMS screenshot into message text.

Input is the structure produced by :func:`src.ocr.ocr.group_lines`:
paragraphs (roughly one per message bubble) -> lines -> segments (one per
OCR box, left to right). Plain text can be cleaned too via
:func:`clean_ocr_text`.

Design rule: **never delete message content to remove UI noise.** Only whole
segments or whole lines that consist *entirely* of UI chrome (timestamps,
"Delivered", status-bar icons, "Type a message") are dropped. The word
"reply" inside "Reply STOP to unsubscribe" is content and survives. A time
is only dropped when it is its own OCR box at the end of a line (where chat
apps draw the bubble timestamp) or stands alone on a line - a time inside a
sentence ("meet at 10:30") is kept.
"""
from __future__ import annotations

import re

# ----------------------------- noise vocabulary ----------------------------- #
_TIME = r"\d{1,2}\s?[:.;]\s?\d{2}"
_AMPM = r"[ap]\.?\s?m\.?"
_TIME_RE = re.compile(rf"^{_TIME}(\s?{_AMPM})?$", re.IGNORECASE)
_DATE_RE = re.compile(r"^\d{1,2}[/\-.]\d{1,2}[/\-.]\d{2,4}$")
_PERCENT_RE = re.compile(r"^\d{1,3}\s?%$")
_YEAR_RE = re.compile(r"^(19|20)\d{2}$")
_DAY_OF_MONTH_RE = re.compile(r"^\d{1,2}(st|nd|rd|th)?$", re.IGNORECASE)

# Read-receipt ticks as rendered, plus common OCR misreads of them.
_TICK_CHARS = "✓✔√✅"
_TICK_TOKENS = {"vv", "v", "w", "vw", "wv", "//", "✓✓", "✔✔"}

_WEEKDAYS = {"monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
             "mon", "tue", "tues", "wed", "thu", "thur", "thurs", "fri", "sat", "sun"}
_MONTHS = {"january", "february", "march", "april", "may", "june", "july", "august", "september",
           "october", "november", "december", "jan", "feb", "mar", "apr", "jun", "jul", "aug", "sep",
           "sept", "oct", "nov", "dec"}
# Single tokens that are chrome when a line consists only of these (+ times/dates).
_STATUS_TOKENS = {"today", "yesterday", "am", "pm", "at", "delivered", "read", "seen", "sent", "edited",
                  "forwarded", "4g", "5g", "3g", "lte", "volte", "vo", "wifi", "wi-fi", "4g+", "lte+"}
# Whole-line UI phrases (compared after lowercasing and stripping punctuation).
_UI_PHRASES = {
    "reply", "forward", "copy", "delete", "send", "message", "text message", "sms", "sms/mms", "mms",
    "imessage", "type a message", "message…", "online", "typing", "typing…", "tap to load",
    "tap to retry", "not delivered", "sending", "chat", "rcs message", "text message • sms",
    "encrypted", "end-to-end encrypted",
}

_URL_TAIL_RE = re.compile(r"(https?://|www\.)\S*$", re.IGNORECASE)
_URL_CONT_RE = re.compile(r"^[\w\-./?=&%#~+:]+$")
_ANY_URL_RE = re.compile(r"(https?://|www\.)", re.IGNORECASE)
_TRAILING_TICKS_RE = re.compile(rf"\s*(?:[{_TICK_CHARS}]+|\b(?:vv|vw|wv)\b)\s*$", re.IGNORECASE)
_TRAILING_TIME_WITH_TICKS_RE = re.compile(
    rf"\s+{_TIME}(\s?{_AMPM})?\s*(?:[{_TICK_CHARS}]+|\b(?:vv|vw|wv)\b)\s*$", re.IGNORECASE
)


def _normalize(s: str) -> str:
    return re.sub(r"\s+", " ", s.strip().lower()).strip(" .,:;!-|•·")


def is_time_like(segment: str) -> bool:
    """True if ``segment`` is only a clock time, optionally with am/pm and ticks."""
    s = segment.strip().rstrip(_TICK_CHARS).strip()
    s = re.sub(r"\s+(vv|vw|wv|w|v)$", "", s, flags=re.IGNORECASE)
    return bool(_TIME_RE.match(s))


def _is_noise_token(tok: str) -> bool:
    t = tok.strip(",.()[]|•·").lower()
    if not t:
        return True
    if t in _STATUS_TOKENS or t in _WEEKDAYS or t in _MONTHS or t in _TICK_TOKENS:
        return True
    if all(c in _TICK_CHARS for c in t):
        return True
    return bool(_TIME_RE.match(t) or _DATE_RE.match(t) or _PERCENT_RE.match(t) or _YEAR_RE.match(t))


def is_noise_line(line: str) -> bool:
    """True if a whole line is UI chrome (timestamp, status bar, "Delivered", ...).

    Conservative on purpose: a line survives unless *every* token is known
    noise. A lone number ("482913") is kept - it could be an OTP.
    """
    norm = _normalize(line)
    if not norm:
        return True
    if norm in _UI_PHRASES or norm.startswith("last seen"):
        return True
    if is_time_like(norm):
        return True
    # Merge "10:45 am" / "10 : 45" style splits before tokenizing.
    merged = re.sub(rf"({_TIME})\s?({_AMPM})", r"\1\2", norm, flags=re.IGNORECASE)
    tokens = merged.split()
    if not any(_is_noise_token(t) and not _DAY_OF_MONTH_RE.match(t) for t in tokens):
        return False  # nothing noise-like at all
    # A day-of-month number only counts as noise next to a month name ("3 Oct").
    has_month = any(t.strip(",.").lower() in _MONTHS for t in tokens)
    for t in tokens:
        if _is_noise_token(t):
            continue
        if has_month and _DAY_OF_MONTH_RE.match(t.strip(",.")):
            continue
        return False
    return True


def clean_line(line: str) -> str:
    """Strip read-receipt ticks, and a time glued to them, from the end of a line."""
    line = _TRAILING_TIME_WITH_TICKS_RE.sub("", line)
    line = _TRAILING_TICKS_RE.sub("", line)
    return line.strip()


_TLDS = "com|in|org|net|co|info|io|ly|tk|top|xyz|site|online|app|me|gov|link|live|club|shop"
_SPACED_DOT_RE = re.compile(rf"(\S+?)(\s+\.\s*|\.\s+)({_TLDS})(?=/|\s|$)")


def _join_spaced_domain(m: re.Match) -> str:
    """Rejoin "amazon-offer . com" only when it looks like a domain, not a sentence end."""
    name, _, tld = m.group(1), m.group(2), m.group(3)
    rest = m.string[m.end():m.end() + 1]
    looks_like_domain = "-" in name or any(c.isdigit() for c in name) or rest == "/"
    return f"{name}.{tld}" if looks_like_domain else m.group(0)


def fix_url_spacing(text: str) -> str:
    """Repair common OCR spacing errors inside URLs ("http: //", "www .", "site-x . com").

    A spaced dot before a TLD is only closed up when the left side looks like
    a domain (has a hyphen or digit) or a path follows - so "later. in the
    evening" is left alone. TLDs match lowercase only for the same reason.
    """
    text = re.sub(r"\b(https?)\s*:\s*/\s*/\s*", r"\1://", text, flags=re.IGNORECASE)
    text = re.sub(r"\bwww\s*\.\s*", "www.", text, flags=re.IGNORECASE)
    return _SPACED_DOT_RE.sub(_join_spaced_domain, text)


# ------------------------------ OCR char fixes ------------------------------ #
_DEVANAGARI_DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")
_VISARGA_AFTER_ASCII_RE = re.compile(r"(?<=[A-Za-z0-9])ः")
_PIPE_AFTER_DEVANAGARI_RE = re.compile(r"(?<=[ऀ-ॣ])\s?\|")
# "I"/"l" misread for "1": only when touching a digit ("Rs I000", "I2 hours") or
# directly before "pm" ("Ipm"). Deliberately not "am": "I am" must survive.
_ONE_BEFORE_DIGIT_RE = re.compile(r"(?<![A-Za-z])[Il](?=\d)")
_ONE_AFTER_DIGIT_RE = re.compile(r"(?<=\d)[Il](?![A-Za-z])")
_ONE_BEFORE_PM_RE = re.compile(r"(?<![A-Za-z])[Il](?=pm\b)")


def normalize_ocr_chars(text: str) -> str:
    """Undo systematic script confusions of a Devanagari OCR model.

    * Devanagari digits -> ASCII. Indian SMS/WhatsApp overwhelmingly use
      ASCII digits (even in Hindi text), the Devanagari model emits its own
      digits for them, and downstream OTP/phone masking expects ASCII.
    * Visarga "ः" right after a Latin letter/digit -> ":" (misread colon, e.g.
      "httpः"). A visarga inside a Devanagari word is left alone.
    * "|" right after Devanagari -> danda "।" (misread sentence end).
    * "I"/"l" touching a digit, or right before "pm" -> "1" ("Ipm" -> "1pm").
    """
    text = text.translate(_DEVANAGARI_DIGITS)
    text = _VISARGA_AFTER_ASCII_RE.sub(":", text)
    text = _PIPE_AFTER_DEVANAGARI_RE.sub("।", text)
    return re.sub(r"\S+", lambda m: _fix_misread_one(m.group(0)), text)


def _fix_misread_one(token: str) -> str:
    """Apply the I/l -> 1 fixes to one token, never inside URL-like tokens
    (short-link paths such as "bit.ly/l2abc" are case-sensitive codes)."""
    if "/" in token or "\\" in token or "www." in token.lower() or ":" in token.rstrip(":"):
        return token
    for pattern in (_ONE_BEFORE_DIGIT_RE, _ONE_AFTER_DIGIT_RE, _ONE_BEFORE_PM_RE):
        token = pattern.sub("1", token)
    return token


# The OCR models read "/" as "l", "I", "1" or "|" and sometimes drop ":" or ".".
_SLASH_LIKE = r"[/\\lI1|]"
# Case-insensitivity is scoped to the scheme/TLD with (?i:...): the slash-lookalike
# class must stay case-sensitive, or [lI1|] would also swallow a lowercase "i".
_SCHEME_RE = re.compile(rf"\b((?i:https?))\s*[:;.,]?[il]?\s*{_SLASH_LIKE}{{1,2}}\s*(?=[A-Za-z0-9])")
_URL_TOKEN_RE = re.compile(r"https?://[^\s]+", re.IGNORECASE)
_HOST_SPACE_TLD_RE = re.compile(rf"((?i:https?)://[\w\-]+)\s+((?i:{_TLDS}))(?={_SLASH_LIKE}|\s|$)")
_TLD_SLASH_RE = re.compile(rf"^((?i:https?)://[\w\-.]*\.(?i:{_TLDS}))[lI1|]([\w\-?=&%#~+]+)$")


def _repair_url_token(token: str) -> str:
    """"http://sbi-kyc-verify.tklupdate" -> "http://sbi-kyc-verify.tk/update".

    Only when the rest after the TLD contains no further dot - otherwise it may
    be a longer, valid host ("http://shop.colab.in" must not become "shop.co/ab.in").
    """
    if "/" in token[len("https://"):]:
        return token  # already has a path separator after the scheme
    m = _TLD_SLASH_RE.match(token)
    return f"{m.group(1)}/{m.group(2)}" if m else token


def repair_ocr_urls(text: str) -> str:
    """Heuristically repair URLs mangled by OCR, so the URL analyzer can still see them.

    Fixes, in order: a mangled scheme separator ("http:lI", "http:ll",
    "httpill", "http: /") -> "http://"; a space where the dot before a known
    TLD was dropped, only for a host with no dot yet ("http://indiapost-redeliver
    top/pay"); and a "/" misread as "l" right after the TLD ("verify.tklupdate").
    Tokens that don't start with http(s) are never touched.
    """
    text = _SCHEME_RE.sub(lambda m: m.group(1).lower() + "://", text)
    text = _HOST_SPACE_TLD_RE.sub(lambda m: f"{m.group(1)}.{m.group(2).lower()}", text)
    return _URL_TOKEN_RE.sub(lambda m: _repair_url_token(m.group(0)), text)


def _should_glue(prev: str, nxt: str) -> bool:
    """Join two lines with no space: a URL wrapped across lines, or a line ending in '-'."""
    if not prev or not nxt:
        return False
    first = nxt.split()[0]
    if _ANY_URL_RE.match(first):
        return False  # the next line starts a new URL
    if _URL_TAIL_RE.search(prev) and _URL_CONT_RE.match(first):
        # Continuation of a URL: previous line ends mid-URL, or next token looks like a URL part.
        return prev[-1] in "/-._?=&%#~+" or any(c in first for c in "./")
    return prev.endswith("-") and prev[-2:-1].isalnum() and first[:1].isalnum()


def join_lines(lines: list[str]) -> str:
    """Join the visual lines of one bubble into a single line of text.

    Chat apps wrap at spaces, so lines are joined with a space - except a URL
    wrapped mid-link or a line ending with a hyphen, which are glued (the
    hyphen is kept: chat apps don't hyphenate, so a trailing '-' is real).
    """
    out = ""
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if not out:
            out = line
        elif _should_glue(out, line):
            out += line
        else:
            out += " " + line
    return out


def clean_paragraphs(paragraphs: list[list[list[str]]]) -> str:
    """Clean grouped OCR output (paragraphs -> lines -> segments) into message text.

    Returns bubbles separated by a blank line; empty string if nothing survives.
    """
    bubbles: list[str] = []
    for para in paragraphs:
        kept_lines: list[str] = []
        for segments in para:
            segs = [normalize_ocr_chars(s.strip()) for s in segments if s and s.strip()]
            # A time box at the end of a line is the bubble timestamp.
            while segs and (is_time_like(segs[-1]) or is_noise_line(segs[-1]) and len(segs) > 1
                            and _is_trailing_chrome(segs[-1])):
                segs.pop()
            # Scheme repair before joining, so a wrapped URL is recognized as one.
            line = repair_ocr_urls(clean_line(" ".join(segs)))
            if line and not is_noise_line(line):
                kept_lines.append(line)
        text = repair_ocr_urls(fix_url_spacing(join_lines(kept_lines)))
        text = re.sub(r"[ \t]+", " ", text).strip()
        if text:
            bubbles.append(text)
    return "\n\n".join(bubbles)


def _is_trailing_chrome(segment: str) -> bool:
    """Trailing boxes that are receipts/ticks rather than words (e.g. "Delivered", "✓✓").

    "read"/"sent" are not included: as a separate trailing box they could
    still be the last word of a sentence. They are removed only as whole lines.
    """
    norm = _normalize(segment)
    return norm in {"delivered", "seen"} or all(
        _is_noise_token(t) and not t.isalpha() or t in _TICK_TOKENS for t in norm.split()
    )


def clean_ocr_text(text: str) -> str:
    """Clean plain OCR text: blank lines separate bubbles, each line is one segment."""
    paragraphs = [[[ln] for ln in block.splitlines()] for block in re.split(r"\n\s*\n", text)]
    return clean_paragraphs(paragraphs)
