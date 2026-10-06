"""Rule-based URL risk scoring.

Scores a URL from 0 (no red flags) to 1 (strong evidence of phishing) using
only properties of the URL string itself, plus optional offline blocklists
(:mod:`src.url_analyzer.offline_lists`). **No URL is ever fetched or visited**
- every check below is a pure string/structure inspection, which is required
because live-visiting a suspicious link could trigger tracking, malware, or
confirm to an attacker that the link was clicked.

Usage::

    python -m src.url_analyzer.analyzer

Suggested risk bands (documented judgment calls, not tuned against labelled
data - Phase 7's LLM explainer can use :func:`risk_band` or these thresholds
directly when deciding how strongly to word its advice):

- **low** (score < 0.3): informational only, e.g. a single weak signal
  (missing HTTPS, or one suspicious keyword) on an otherwise ordinary URL.
- **medium** (0.3 <= score < 0.6): one strong signal (IP-based host, ``@``
  trick, brand lookalike) or several weak ones stacked together.
- **high** (score >= 0.6): multiple strong signals, a confirmed brand
  impersonation plus a suspicious TLD, or a confirmed offline-blocklist match.
"""
from __future__ import annotations

import ipaddress
import logging
import re
from dataclasses import dataclass, field
from urllib.parse import urlsplit

import tldextract
from rapidfuzz.distance import Levenshtein

from src.url_analyzer.brands import BRANDS, Brand
from src.url_analyzer.offline_lists import OfflineURLList

logger = logging.getLogger(__name__)

# tldextract normally fetches a fresh public-suffix list on first use; pinning
# suffix_list_urls=() makes it use its bundled snapshot only, so this module
# never makes a network call.
_EXTRACT = tldextract.TLDExtract(suffix_list_urls=())

_SUSPICIOUS_TLDS = frozenset({
    "tk", "ml", "ga", "cf", "gq", "xyz", "top", "click", "work", "info", "club",
})
_SHORTENER_DOMAINS = frozenset({
    "bit.ly", "tinyurl.com", "t.co", "goo.gl", "ow.ly", "is.gd", "buff.ly",
    "cutt.ly", "rb.gy", "tiny.cc", "shorturl.at", "rebrand.ly", "shorte.st",
})
_MAX_URL_LENGTH = 75
_MAX_SUBDOMAIN_LABELS = 2  # more than this is "excessive"
_LOOKALIKE_MAX_DISTANCE = 2
_LOOKALIKE_MIN_NAME_LENGTH = 5  # below this, only exact-label combosquat applies

# Words that turn up disproportionately often in scam domains/paths (urgency,
# credential/KYC requests, fake rewards). A modest, capped signal on its own -
# plenty of legitimate pages use "login" or "account" - not a strong one.
_SUSPICIOUS_KEYWORDS = frozenset({
    "verify", "kyc", "update", "login", "secure", "account", "claim", "gift",
    "reward", "prize", "bonus", "refund", "blocked", "suspend", "urgent", "immediately",
})
_WEIGHT_SUSPICIOUS_KEYWORD_PER = 0.1
_MAX_SUSPICIOUS_KEYWORD_WEIGHT = 0.3

_LABEL_SPLIT_RE = re.compile(r"[.\-_]+")
_WORD_SPLIT_RE = re.compile(r"[^a-z0-9]+")

_RISK_BAND_LOW_MAX = 0.3
_RISK_BAND_MEDIUM_MAX = 0.6

# Weights, summed then clamped to [0, 1]. Not learned - documented judgment calls
# for a rule-based module (see the Phase 5 plan).
_WEIGHT_OFFLINE_LIST_MATCH = 0.9
_WEIGHT_IP_BASED = 0.35
_WEIGHT_PUNYCODE = 0.35
_WEIGHT_COMBOSQUAT = 0.4
_WEIGHT_BRAND_AS_SUBDOMAIN = 0.4
_WEIGHT_LOOKALIKE = 0.4
_WEIGHT_AT_SYMBOL = 0.3
_WEIGHT_SHORTENER = 0.2
_WEIGHT_SUSPICIOUS_TLD = 0.15
_WEIGHT_EXCESSIVE_SUBDOMAINS = 0.15
_WEIGHT_VERY_LONG = 0.1
_WEIGHT_MISSING_HTTPS = 0.1


def risk_band(score: float) -> str:
    """Map a 0-1 score to "low"/"medium"/"high" (see the module docstring)."""
    if score < _RISK_BAND_LOW_MAX:
        return "low"
    if score < _RISK_BAND_MEDIUM_MAX:
        return "medium"
    return "high"


@dataclass
class URLFinding:
    """The risk score and human-readable reasons for one URL."""

    url: str
    score: float = 0.0
    reasons: list[str] = field(default_factory=list)

    def _add(self, weight: float, reason: str) -> None:
        self.score += weight
        self.reasons.append(reason)

    @property
    def risk_band(self) -> str:
        """This finding's suggested "low"/"medium"/"high" band. See :func:`risk_band`."""
        return risk_band(self.score)


def _parse(url: str) -> tuple[str, str, str]:
    """Split ``url`` into (scheme, netloc, path), tolerating a missing scheme.

    ``mask_urls`` (Phase 2) extracts bare domains like ``"sbi.co.in"`` with no
    ``http(s)://`` prefix, so a plain :func:`urlsplit` would misparse them as
    a relative path with no host. Treating the URL as scheme-relative fixes
    that without guessing (and never fetching) anything.
    """
    raw = url.strip()
    parsed = urlsplit(raw if "://" in raw else "//" + raw)
    return parsed.scheme, parsed.netloc, parsed.path


def _host_only(netloc: str) -> str:
    """Strip a ``user:pass@`` prefix and a ``:port`` suffix from ``netloc``."""
    host = netloc.rsplit("@", 1)[-1]
    if host.startswith("["):  # IPv6 literal, e.g. [::1]:8080
        return host.split("]")[0].lstrip("[")
    return host.split(":", 1)[0]


def _labels(text: str) -> list[str]:
    """Split ``text`` into lowercase alnum labels on ``.``, ``-`` and ``_``."""
    return [t for t in _LABEL_SPLIT_RE.split(text.lower()) if t]


def _word_tokens(text: str) -> set[str]:
    """Split ``text`` into lowercase alnum words on any non-alphanumeric run.

    Broader than :func:`_labels` (also splits on ``/``, ``?``, ``=``, ``&``, ...)
    so it works on a URL path, not just a domain.
    """
    return {t for t in _WORD_SPLIT_RE.split(text.lower()) if t}


def _suspicious_keywords(subdomain: str, domain: str, path: str) -> list[str]:
    """Distinct suspicious keywords found as whole tokens in the domain or path."""
    tokens = _word_tokens(subdomain) | _word_tokens(domain) | _word_tokens(path)
    return sorted(tokens & _SUSPICIOUS_KEYWORDS)


def _is_ip_based(host: str) -> bool:
    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        return False


def _has_punycode_label(netloc: str) -> bool:
    return any(label.startswith("xn--") for label in netloc.lower().split("."))


def _ngram_tokens(labels: list[str]) -> set[str]:
    """Single labels plus adjacent-pair concatenations (no separator re-inserted).

    Catches two-word brand names split by a hyphen, e.g. ``["tata", "capital",
    "service"]`` -> includes ``"tatacapital"``, without ever comparing raw
    substrings across unrelated label boundaries.
    """
    tokens = set(labels)
    tokens.update(labels[i] + labels[i + 1] for i in range(len(labels) - 1))
    return tokens


def _combosquat_brand(subdomain: str, domain: str, suffix: str, brands: tuple[Brand, ...]) -> Brand | None:
    """A brand token appears as a whole label, but the registered domain isn't the brand's."""
    registered = f"{domain}.{suffix}" if suffix else domain
    tokens = _ngram_tokens(_labels(subdomain)) | _ngram_tokens(_labels(domain))
    for brand in brands:
        if registered in brand.legit_domains:
            continue  # this *is* the brand's own domain, not an impersonation
        if tokens & set(brand.names):
            return brand
    return None


def _brand_as_subdomain(subdomain: str, domain: str, suffix: str, brands: tuple[Brand, ...]) -> Brand | None:
    """A brand's real domain is demoted to a subdomain of a different registered domain."""
    if not subdomain:
        return None
    registered = f"{domain}.{suffix}" if suffix else domain
    padded_subdomain = f".{subdomain.lower()}."
    for brand in brands:
        for legit in brand.legit_domains:
            if registered == legit:
                continue  # this *is* the brand's own domain, not an impersonation
            if f".{legit}." in padded_subdomain:
                return brand
    return None


def _lookalike_brand(domain: str, brands: tuple[Brand, ...]) -> Brand | None:
    """A domain token within a small edit distance of a brand name, but not equal to it."""
    for brand in brands:
        for name in brand.names:
            if len(name) < _LOOKALIKE_MIN_NAME_LENGTH:
                continue  # too short - fuzzy matching would false-positive constantly
            if domain == name:
                continue
            if Levenshtein.distance(domain, name) <= _LOOKALIKE_MAX_DISTANCE:
                return brand
    return None


def analyze_url(url: str, offline_lists: list[OfflineURLList] | None = None) -> URLFinding:
    """Score a single URL. Never fetches or visits ``url``."""
    finding = URLFinding(url=url)
    scheme, netloc, path = _parse(url)
    host = _host_only(netloc)
    extracted = _EXTRACT(f"//{host}")
    subdomain, domain, suffix = extracted.subdomain, extracted.domain, extracted.suffix

    for offline_list in offline_lists or []:
        if offline_list.is_listed(url):
            finding._add(_WEIGHT_OFFLINE_LIST_MATCH, f"Listed in {offline_list.source_name} as a known phishing URL")

    is_ip = _is_ip_based(host)
    if is_ip:
        finding._add(_WEIGHT_IP_BASED, f"URL uses a raw IP address ({host}) instead of a domain name")

    if _has_punycode_label(host):
        finding._add(_WEIGHT_PUNYCODE, "Domain uses punycode (xn--), a possible homoglyph/lookalike-character attack")

    # Domain-name-shaped checks are meaningless (and can misfire, e.g. an IP's
    # octets look like "excessive subdomains") once the host is a raw IP.
    if not is_ip:
        if (brand := _combosquat_brand(subdomain, domain, suffix, BRANDS)) is not None:
            name = brand.display_name
            finding._add(_WEIGHT_COMBOSQUAT, f"Domain embeds the brand name \"{name}\" but is not {name}'s real domain")

        if (brand := _brand_as_subdomain(subdomain, domain, suffix, BRANDS)) is not None:
            finding._add(_WEIGHT_BRAND_AS_SUBDOMAIN, f"\"{brand.display_name}\"'s real domain appears as a subdomain of a different site")

        if (brand := _lookalike_brand(domain, BRANDS)) is not None:
            finding._add(_WEIGHT_LOOKALIKE, f"Domain \"{domain}\" closely resembles the brand \"{brand.display_name}\" (possible typo-squat)")

        registered_domain = f"{domain}.{suffix}" if suffix else domain
        if registered_domain in _SHORTENER_DOMAINS:
            finding._add(_WEIGHT_SHORTENER, f"Uses a URL shortener ({registered_domain}); real destination is hidden")

        if suffix.split(".")[-1] in _SUSPICIOUS_TLDS:
            finding._add(_WEIGHT_SUSPICIOUS_TLD, f"Uses a top-level domain often abused for phishing (.{suffix})")

        if len([l for l in subdomain.split(".") if l]) > _MAX_SUBDOMAIN_LABELS:
            finding._add(_WEIGHT_EXCESSIVE_SUBDOMAINS, "URL has an unusually high number of subdomains")

    keywords = _suspicious_keywords("" if is_ip else subdomain, "" if is_ip else domain, path)
    if keywords:
        weight = min(_MAX_SUSPICIOUS_KEYWORD_WEIGHT, _WEIGHT_SUSPICIOUS_KEYWORD_PER * len(keywords))
        finding._add(weight, f"URL contains suspicious keyword(s): {', '.join(keywords)}")

    if "@" in netloc:
        finding._add(_WEIGHT_AT_SYMBOL, "URL contains \"@\", which can hide the real destination after a fake-looking address")

    if len(url) > _MAX_URL_LENGTH:
        finding._add(_WEIGHT_VERY_LONG, f"Unusually long URL ({len(url)} characters)")

    if scheme.lower() != "https":
        finding._add(_WEIGHT_MISSING_HTTPS, "Connection is not HTTPS")

    finding.score = min(1.0, finding.score)
    return finding


def analyze_urls(urls: list[str], offline_lists: list[OfflineURLList] | None = None) -> list[URLFinding]:
    """Score each URL in ``urls`` independently. See :func:`analyze_url`."""
    return [analyze_url(url, offline_lists) for url in urls]


_DEMO_URLS = [
    "https://www.hdfcbank.com/personal/pay/cards/credit-cards",  # clean, legitimate
    "http://192.168.10.55/login/verify.php",                     # IP-based
    "http://account-support@customer-verification-portal.net/kyc",  # @ trick
    "https://hdfcbank-verify.tk/update-kyc",                      # combosquat + suspicious TLD
    "http://hdfcbank.com.secure-login.xyz/reset",                 # brand-as-subdomain
    "https://xn--hdfcbank-mtb.com/login",                         # punycode
    "https://bit.ly/3kyc-update",                                 # shortener
    "https://a.b.c.free-gift-claim.com/verify",                   # excessive subdomains
    "https://account-security-update-required-immediately-verification.com/verify/account/details/now",  # very long
    "http://paytm.com/pay",                                       # legit brand, plain http (missing https)
]


def _print_demo() -> None:
    logging.basicConfig(level=logging.WARNING)
    for url in _DEMO_URLS:
        finding = analyze_url(url)
        print(f"\nURL: {url}")
        print(f"  score: {finding.score:.2f}  risk band: {finding.risk_band}")
        for reason in finding.reasons:
            print(f"  - {reason}")
        if not finding.reasons:
            print("  - no red flags found")


if __name__ == "__main__":
    _print_demo()
