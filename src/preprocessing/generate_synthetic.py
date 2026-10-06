"""Generate synthetic mixed-language scam/safe messages with free LLM APIs.

Why synthetic data: the public corpora are English and Western-centric. This
script produces Hinglish and other code-mixed Indian-language messages for
seven scam types, plus *safe* counterparts (genuine bank/courier/bill/job
messages and everyday chat) so a classifier cannot learn "mixed language =
scam" or "contains a link = scam".

Every generated row is marked ``is_synthetic=True`` and records which
provider/model wrote it in the ``generator`` column. Synthetic rows must never
be used for evaluation (see CLAUDE.md).

Robustness features:

* Two providers (Groq, Gemini) share the work round-robin to dilute any one
  model's writing style.
* Client-side rate limiting, retries with exponential backoff + jitter,
  ``Retry-After`` support, and a distinct ``QuotaExhausted`` for daily quotas.
* Resumable: each finished batch is appended to a JSONL file as one line;
  re-running skips completed batches.

Usage::

    python -m src.preprocessing.generate_synthetic --dry-run
    python -m src.preprocessing.generate_synthetic --limit-batches 8
    python -m src.preprocessing.generate_synthetic --show-samples 10
    python -m src.preprocessing.generate_synthetic            # full run (resumable)
"""
from __future__ import annotations

import argparse
import json
import logging
import math
import os
import random
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

import pandas as pd
import requests

from src.preprocessing.language import detect_language
from src.preprocessing.schema import (
    LABEL_SAFE,
    LABEL_SCAM,
    SCAM_TYPE_NONE,
    SYNTHETIC_SCAM_TYPES,
    make_frame,
    validate_frame,
)

logger = logging.getLogger(__name__)

SOURCE_NAME = "synthetic_llm"
DEFAULT_OUTPUT = Path("data/synthetic/synthetic_raw.jsonl")
DEFAULT_BATCH_SIZE = 10
EVERYDAY_TOPIC = "everyday"
MIN_TEXT_CHARS = 15
MAX_TEXT_CHARS = 700
# A batch returning fewer than this share of the requested messages is treated
# as failed (and retried on the next run) instead of being recorded as done.
MIN_YIELD_FRACTION = 0.5

# Number of batches per (topic, language). Hinglish is weighted highest because
# it is the most common code-mixed style in Indian SMS/WhatsApp scams.
# 195 batches x 10 messages ~= 1,950 rows at scale=1.
LANGUAGE_WEIGHTS: dict[str, int] = {
    "hinglish": 5,
    "hi": 2,
    "en": 2,
    "ta_en": 1,
    "te_en": 1,
    "bn_en": 1,
    "mr_en": 1,
}

# Regional code-mixed styles are routed to Gemini only: in the pilot, Groq's
# gpt-oss-120b wrote plain English for these while Gemini wrote convincing text.
GEMINI_ONLY_LANGUAGES: frozenset[str] = frozenset({"ta_en", "te_en", "bn_en", "mr_en"})

# Romanized marker words that a genuine regional code-mixed message contains and
# plain English does not. A message also passes if it is mostly in native script.
REGIONAL_MARKERS: dict[str, frozenset[str]] = {
    "ta_en": frozenset(
        """enna illa irukku irukkum romba pannunga panni pannu vaanga vanga seri sollunga
        ungal unga ungaluku unakku ennoda ippo inga epdi eppadi nalla aana kudunga poitu
        vandhu theriyuma panam venum vendam nandri vanakkam
        iruku konjam naalaiku inniki ippove anuppunga varum vandhuduchu enakku avanga pannanum pannalaam neenga nenga udane seekiram""".split()
    ),
    "te_en": frozenset(
        """ela undi unnaru meeru naaku cheyandi cheyyandi chesaru kada ledu ledhu ippudu
        ekkada enti cheppandi kavali vachindi ravali baaga dhanyavadalu namaskaram ayindi
        unnadi avunu ledandi emaindi
        meeku meeka nunchi avuthundi avutundi avthundi ayyindi vellandi chusukovachu konchem ivvandi intiki intlo eeroju repu undandi vasthundi vastunnadu chesukondi chesthunnaru kottagane manchi chesindi kosam""".split()
    ),
    "bn_en": frozenset(
        """ache achhe nei apnar apnake apni korun korte koro kore hobe hoyeche holo ekhon
        jonno dhonnobad bhalo dorkar pathan dekhun niye tomar amar amake kotha taka
        nomoskar achen korbo
        ekhoni shudhu sudhu jodi kintu thakbe thakle jeno debe deben paben pabe korben korlei taratari sathe theke""".split()
    ),
    "mr_en": frozenset(
        """aahe ahe ahet tumhi tumchya tumcha tumchi kara karun mala tula tumhala kay kasa
        kase aata zala zhala pahije milale bhetle bhetla aani sanga kadhi kuthe asel nako
        majha majhya aapla dhanyavad namaskar
        laukar madhye kadun sathi saathi ghya pathva pathwa udya milel milnar honar hoil krupaya fakt lagech mhanun tyala""".split()
    ),
}
# Native script that also satisfies each regional style (Marathi uses Devanagari).
_REGIONAL_SCRIPT = {"ta_en": "ta", "te_en": "te", "bn_en": "bn", "mr_en": "hi"}

# Values LLMs reach for when asked for "fake" numbers; a classifier could latch
# onto them, so messages containing them are dropped.
_PLACEHOLDER_RE = re.compile(
    r"(?<!\d)(?:123456|1234567|12345678|12345|1234|654321|987654|000000|111111|222222|"
    r"123123|112233|98765[\s-]?43210|9876543210)(?!\d)|\b(?:abcde|abc123|xyz123|xxxx+)\b",
    re.IGNORECASE,
)

LANGUAGE_STYLES: dict[str, str] = {
    "hinglish": (
        "Hinglish: Hindi written in Roman/Latin script mixed with English words, "
        "exactly how Indians type on SMS and WhatsApp (e.g. 'aapka account band ho jayega')."
    ),
    "hi": (
        "Hindi written in Devanagari script, with some English words/brand names "
        "left in Latin script."
    ),
    "en": "Indian English as used in Indian SMS/WhatsApp messages.",
    "ta_en": "Tamil-English code-mixed ('Tanglish'): Tamil written mostly in Roman script mixed with English.",
    "te_en": "Telugu-English code-mixed: Telugu written mostly in Roman script mixed with English.",
    "bn_en": "Bengali-English code-mixed: Bengali written mostly in Roman script mixed with English.",
    "mr_en": "Marathi-English code-mixed: Marathi written mostly in Roman script mixed with English.",
}

# topic -> (scam description, genuine/safe counterpart description)
TOPIC_DESCRIPTIONS: dict[str, tuple[str, str]] = {
    "fake_kyc": (
        "A fraudulent message claiming the recipient's bank/wallet/SIM account will be blocked "
        "or suspended unless they update KYC/PAN/Aadhaar right now via a link or phone number.",
        "A GENUINE bank/wallet message reminding the customer to complete KYC at a branch or in "
        "the official app, or confirming KYC was updated. It never asks for credentials via a link.",
    ),
    "lottery": (
        "A fraudulent lottery / KBC / lucky-draw / prize message telling the recipient they won "
        "a large amount and must pay a fee or share personal details to claim it.",
        "A GENUINE promotional or transactional message from a known retailer, telecom or app "
        "(cashback credited, coupon, genuine contest terms), or friends casually chatting about "
        "lotteries or offers.",
    ),
    "courier_customs": (
        "A fraudulent message saying a parcel is held at customs / delivery failed / address "
        "incomplete and asking for a small fee or details through a link.",
        "A GENUINE courier or e-commerce update (out for delivery, delivered, tracking ID, "
        "an expected time window) from a known carrier or marketplace. It never demands payment via a link "
        "and never mentions an OTP.",
    ),
    "job_offer": (
        "A fraudulent job message: work-from-home / part-time / 'like and earn' tasks, high pay "
        "for little work, a registration or deposit fee, or contact via Telegram/WhatsApp.",
        "A GENUINE recruiter or HR message: interview scheduling, document checklist for joining, "
        "offer-letter follow-up, or a company notice. No upfront fees.",
    ),
    "electricity_bill": (
        "A fraudulent message saying electricity will be disconnected tonight unless the recipient "
        "pays a pending bill, calls an 'officer', or installs an app.",
        "A GENUINE electricity board/discom message: bill generated, due-date reminder, payment "
        "received, or scheduled-maintenance notice.",
    ),
    "loan_offer": (
        "A fraudulent instant-loan message: pre-approved loan with no documents, an upfront "
        "processing fee, or pressure to install a loan app.",
        "A GENUINE bank/NBFC message: EMI due reminder, loan statement, EMI debited, or an "
        "in-app pre-approved offer with no upfront fee.",
    ),
    "fake_bank_otp": (
        "A fraudulent message that pushes the recipient to share an OTP, or claims a debit "
        "happened and to call/click to cancel, or asks to 'verify' the account with an OTP.",
        "A GENUINE bank/UPI/e-commerce OTP notification ('Your OTP is ... Do not share this OTP with "
        "anyone'), debit/credit alerts without an OTP, and login notifications. It never tells the "
        "reader to act on the OTP.",
    ),
}

SAFE_LINK_RULE = (
    "Links: at most 2 of the messages may contain a link, and only to the official domain of the very "
    "organisation the message says it is from, and only for something that organisation really does "
    "(a bank's own domain in a message from that bank, amazon.in for an Amazon order, the discom's own "
    "domain for its own bill). Never put a bank, government (e.g. uidai.gov.in, which is only for "
    "Aadhaar/UIDAI messages) or retailer domain in a message from or about a different organisation, "
    "never use a look-alike or misspelled domain, and never link a lottery, prize, job offer or "
    "friend's message to a bank or government domain. If unsure, leave the link out. Never include real "
    "personal phone numbers."
)
SAFE_OTP_RULE = (
    "OTPs: a message may show an OTP only as a plain notification such as 'Your OTP is 482915. Do not "
    "share it with anyone.' It must never tell the reader to enter, use, verify or confirm anything "
    "with an OTP, to keep one ready, or to give one to anyone (including a delivery agent). Delivery "
    "and courier messages must not mention any OTP or PIN."
)

EVERYDAY_DESCRIPTION = (
    "Ordinary personal or work messages between real people or from services: family and friends "
    "chatting, meeting plans, festival wishes, office coordination, doctor/salon appointment "
    "reminders, recharge confirmations, and similar. Nothing suspicious."
)

_SENDER_HINTS = [
    "a short one-line SMS",
    "a longer 3-4 sentence message",
    "a message with an ID or reference number",
    "a message with emojis, as people send on WhatsApp",
    "a message written in a hurry with casual spelling",
    "a formal message with a sign-off",
]


@dataclass(frozen=True)
class BatchSpec:
    """One LLM call: ``batch_size`` messages of one (label, topic, language)."""

    label: str      # scam | safe
    topic: str      # a scam type, or "everyday" (safe only)
    language: str   # key of LANGUAGE_STYLES
    batch_no: int

    @property
    def key(self) -> str:
        """Stable identifier used for resume bookkeeping."""
        return f"{self.label}|{self.topic}|{self.language}|{self.batch_no}"

    @property
    def scam_type(self) -> str:
        """Value for the ``scam_type`` column (``none`` for safe messages)."""
        return self.topic if self.label == LABEL_SCAM else SCAM_TYPE_NONE


def build_plan(scale: float = 1.0, seed: int = 42) -> list[BatchSpec]:
    """Build the full, deterministically shuffled list of batches.

    Shuffling means ``--limit-batches N`` yields a representative sample of
    labels, topics and languages rather than only the first topic.

    Args:
        scale: Multiplier on the per-language batch counts (min 1 when > 0).
        seed: Shuffle seed.
    """
    plan: list[BatchSpec] = []
    for language, weight in LANGUAGE_WEIGHTS.items():
        n = max(1, round(weight * scale)) if scale > 0 else 0
        for i in range(n):
            for topic in SYNTHETIC_SCAM_TYPES:
                plan.append(BatchSpec(LABEL_SCAM, topic, language, i))
                plan.append(BatchSpec(LABEL_SAFE, topic, language, i))
            plan.append(BatchSpec(LABEL_SAFE, EVERYDAY_TOPIC, language, i))
    random.Random(seed).shuffle(plan)
    return plan


def build_prompt(spec: BatchSpec, batch_size: int, seed: int = 0) -> str:
    """Build the generation prompt for ``spec``.

    Per-batch hints (message length/format, whether to include links and
    numbers) are drawn from an RNG seeded by the batch key so batches differ
    from each other yet stay reproducible.
    """
    rng = random.Random(f"{seed}:{spec.key}")
    style = LANGUAGE_STYLES[spec.language]
    if spec.topic == EVERYDAY_TOPIC:
        what = EVERYDAY_DESCRIPTION
    else:
        scam_desc, safe_desc = TOPIC_DESCRIPTIONS[spec.topic]
        what = scam_desc if spec.label == LABEL_SCAM else safe_desc
    hints = rng.sample(_SENDER_HINTS, k=3)

    if spec.label == LABEL_SCAM:
        link_rule = (
            "About 3 of the messages should contain a fake-looking URL or shortlink and about 2 "
            "a phone number. Use only invented domains and invented numbers, never real ones."
        )
    else:
        link_rule = SAFE_LINK_RULE + " " + SAFE_OTP_RULE
    regional_rule = ""
    if spec.language in REGIONAL_MARKERS:
        regional_rule = (
            "Every message MUST genuinely contain several real words of the regional language "
            "(not just English with a regional name).\n"
        )
    return (
        "You are helping build a labelled training dataset for a defensive scam-detection "
        "classifier that protects people in India. Write realistic example messages.\n\n"
        f"Write exactly {batch_size} different messages.\n"
        f"Category: {what}\n"
        f"Language style: {style}\n"
        f"{regional_rule}"
        f"Variety: vary sender names, amounts, tone and wording. Include {hints[0]}, "
        f"{hints[1]} and {hints[2]} among them. Do not start more than two messages with the "
        "same words, and vary the structure (some with a greeting, some without, some with "
        "urgent capitals, some plain).\n"
        "Numbers: never use placeholder-looking values such as 123456, 1234, 000000, 111111, "
        "987654, 98765 43210 or 9876543210. Use random-looking OTPs, reference IDs, account "
        "digits and phone numbers (10 digits starting with 6-9, no repeated or ascending "
        "patterns).\n"
        f"{link_rule}\n"
        "Make them read like real messages people actually receive: no explanations, no "
        "placeholders like [NAME], no numbering, no labels inside the message text.\n\n"
        'Respond with ONLY a JSON object of the form {"messages": ["...", "..."]}.'
    )


_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)


def parse_messages(raw: str) -> list[str]:
    """Extract a list of message strings from a model response.

    Accepts ``{"messages": [...]}`` or a bare JSON list, with or without
    markdown code fences; list items may be strings or ``{"text": ...}`` dicts.

    Raises:
        ValueError: If no usable message list can be found.
    """
    cleaned = _FENCE_RE.sub("", raw.strip())
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        # Salvage the outermost JSON object/array embedded in surrounding prose.
        match = re.search(r"(\{.*\}|\[.*\])", cleaned, re.DOTALL)
        if not match:
            raise ValueError("response contains no JSON") from None
        try:
            data = json.loads(match.group(1))
        except json.JSONDecodeError as exc:
            raise ValueError(f"unparseable JSON: {exc}") from exc
    if isinstance(data, dict):
        data = data.get("messages")
    if not isinstance(data, list):
        raise ValueError("JSON has no 'messages' list")
    out: list[str] = []
    for item in data:
        if isinstance(item, dict):
            item = item.get("text") or item.get("message")
        if isinstance(item, str) and item.strip():
            out.append(item.strip())
    if not out:
        raise ValueError("no non-empty messages in response")
    return out


# --------------------------------------------------------------------------- #
# LLM clients
# --------------------------------------------------------------------------- #
class APIError(Exception):
    """Non-retryable API failure (bad key, bad request, unknown model...)."""


class QuotaExhausted(Exception):
    """A daily/long-window quota is used up; stop using this provider for now."""


class TransientError(Exception):
    """A retryable failure (429/5xx/timeouts/malformed body) that ran out of retries."""


_RETRY_DELAY_RE = re.compile(r'"retryDelay"\s*:\s*"(\d+(?:\.\d+)?)s"')


class LLMClient:
    """Base class: rate limiting + retry policy shared by all providers.

    Subclasses implement :meth:`_send` (one HTTP request) and
    :meth:`_extract_text` (pull text out of a successful response).
    """

    name = "base"
    #: 429 waits longer than this are treated as quota exhaustion, not a blip.
    max_retry_wait_s = 120.0

    def __init__(
        self,
        api_key: str,
        model: str,
        min_interval_s: float,
        max_retries: int = 5,
        session: requests.Session | None = None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.min_interval_s = min_interval_s
        self.max_retries = max_retries
        self.session = session or requests.Session()
        self._sleep = sleep
        self._clock = clock
        self._last_call: float | None = None

    @property
    def generator_id(self) -> str:
        """``provider/model`` string stored in the ``generator`` column."""
        return f"{self.name}/{self.model}"

    # -- to implement ---------------------------------------------------- #
    def _send(self, prompt: str) -> requests.Response:  # pragma: no cover
        raise NotImplementedError

    def _extract_text(self, payload: dict) -> str:  # pragma: no cover
        raise NotImplementedError

    # -- shared ---------------------------------------------------------- #
    def _throttle(self) -> None:
        """Sleep so consecutive calls are at least ``min_interval_s`` apart."""
        if self._last_call is not None:
            wait = self.min_interval_s - (self._clock() - self._last_call)
            if wait > 0:
                self._sleep(wait)
        self._last_call = self._clock()

    @staticmethod
    def _retry_after_seconds(resp: requests.Response) -> float | None:
        """Server-suggested wait from ``Retry-After`` or Gemini's ``retryDelay``."""
        header = resp.headers.get("Retry-After")
        if header:
            try:
                return float(header)
            except ValueError:
                pass
        match = _RETRY_DELAY_RE.search(resp.text or "")
        return float(match.group(1)) if match else None

    @staticmethod
    def _looks_like_daily_quota(body: str) -> bool:
        low = body.lower()
        return any(s in low for s in ("perday", "per day", "daily", "requests per day", "tokens per day"))

    def _backoff(self, attempt: int, server_wait: float | None) -> float:
        """Exponential backoff with jitter; never shorter than the server hint."""
        base = min(2.0 ** attempt * 2.0, 60.0)
        wait = base + random.uniform(0, base / 4)
        return max(wait, server_wait or 0.0)

    def generate(self, prompt: str) -> str:
        """Send ``prompt`` and return the model's text, with retries.

        Raises:
            QuotaExhausted: Daily quota exceeded (or wait too long to be worth it).
            APIError: Non-retryable client error (400/401/403/404...).
            TransientError: Retries exhausted on 429/5xx/timeouts/bad payloads.
        """
        last_problem = "unknown"
        for attempt in range(self.max_retries + 1):
            self._throttle()
            try:
                resp = self._send(prompt)
            except (requests.Timeout, requests.ConnectionError) as exc:
                last_problem = f"network error: {type(exc).__name__}"
                self._sleep(self._backoff(attempt, None))
                continue

            if resp.status_code == 200:
                try:
                    return self._extract_text(resp.json())
                except (ValueError, KeyError, IndexError, TypeError) as exc:
                    last_problem = f"malformed response: {type(exc).__name__}"
                    self._sleep(self._backoff(attempt, None))
                    continue

            if resp.status_code == 429:
                hint = self._retry_after_seconds(resp)
                if self._looks_like_daily_quota(resp.text or "") or (
                    hint is not None and hint > self.max_retry_wait_s
                ):
                    raise QuotaExhausted(f"{self.name}: rate limit needs a long wait ({hint}s)")
                last_problem = "HTTP 429"
                self._sleep(self._backoff(attempt, hint))
                continue

            if resp.status_code >= 500:
                last_problem = f"HTTP {resp.status_code}"
                self._sleep(self._backoff(attempt, self._retry_after_seconds(resp)))
                continue

            # Other 4xx: retrying will not help. Truncate body; never log headers/keys.
            raise APIError(f"{self.name}: HTTP {resp.status_code}: {(resp.text or '')[:300]}")

        raise TransientError(f"{self.name}: gave up after retries ({last_problem})")


class GroqClient(LLMClient):
    """Groq's OpenAI-compatible chat-completions endpoint."""

    name = "groq"
    URL = "https://api.groq.com/openai/v1/chat/completions"
    DEFAULT_MODEL = "openai/gpt-oss-120b"

    def __init__(self, api_key: str, model: str | None = None, min_interval_s: float = 4.0, **kw):
        super().__init__(api_key, model or self.DEFAULT_MODEL, min_interval_s, **kw)

    def _send(self, prompt: str) -> requests.Response:
        body: dict = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 1.0,
            "max_completion_tokens": 4096,
            "response_format": {"type": "json_object"},
        }
        if self.model.startswith("openai/gpt-oss"):
            body["reasoning_effort"] = "low"  # keep hidden reasoning cheap
        return self.session.post(
            self.URL,
            headers={"Authorization": f"Bearer {self.api_key}"},
            json=body,
            timeout=90,
        )

    def _extract_text(self, payload: dict) -> str:
        return payload["choices"][0]["message"]["content"]


class GeminiClient(LLMClient):
    """Google Gemini ``generateContent`` REST endpoint (key sent as a header)."""

    name = "gemini"
    URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    DEFAULT_MODEL = "gemini-3.8-flash"  # 2.5-flash is closed to new API users

    def __init__(self, api_key: str, model: str | None = None, min_interval_s: float = 7.0, **kw):
        super().__init__(api_key, model or self.DEFAULT_MODEL, min_interval_s, **kw)

    def _send(self, prompt: str) -> requests.Response:
        gen_cfg: dict = {
            "temperature": 1.0,
            "maxOutputTokens": 8192,  # headroom in case the model spends tokens thinking
            "responseMimeType": "application/json",
        }
        if "2.5-flash" in self.model:
            gen_cfg["thinkingConfig"] = {"thinkingBudget": 0}
        return self.session.post(
            self.URL.format(model=self.model),
            headers={"x-goog-api-key": self.api_key},
            json={"contents": [{"parts": [{"text": prompt}]}], "generationConfig": gen_cfg},
            timeout=90,
        )

    def _extract_text(self, payload: dict) -> str:
        parts = payload["candidates"][0]["content"]["parts"]
        text = "".join(p.get("text", "") for p in parts if not p.get("thought"))
        if not text.strip():
            raise ValueError("empty candidate text")
        return text


DEFAULT_GEMINI_MODELS: tuple[str, ...] = (
    "gemini-3.8-flash",
    "gemini-3.5-flash-lite",
    "gemini-3.7-flash",
)


def build_clients(
    provider: str = "both",
    groq_model: str | None = None,
    gemini_models: str | None = None,
) -> list[LLMClient]:
    """Create clients for the requested provider(s) whose API key is set.

    One Groq client and one Gemini client *per Gemini model* are created: each
    Gemini model has its own free-tier quota (``gemini-3.8-flash`` allows only 20
    requests/day), and mixing models also dilutes any single model's style.

    Reads ``GROQ_API_KEY`` / ``GEMINI_API_KEY`` (and optional ``GROQ_MODEL`` /
    ``GEMINI_MODELS``, a comma-separated list) from the environment, loading
    ``.env`` first.
    """
    from dotenv import load_dotenv

    load_dotenv()
    clients: list[LLMClient] = []
    if provider in ("both", "groq") and os.getenv("GROQ_API_KEY"):
        clients.append(
            GroqClient(os.environ["GROQ_API_KEY"], groq_model or os.getenv("GROQ_MODEL") or None)
        )
    if provider in ("both", "gemini") and os.getenv("GEMINI_API_KEY"):
        raw = gemini_models or os.getenv("GEMINI_MODELS") or ",".join(DEFAULT_GEMINI_MODELS)
        for model in (m.strip() for m in raw.split(",")):
            if model:
                clients.append(GeminiClient(os.environ["GEMINI_API_KEY"], model))
    return clients


# --------------------------------------------------------------------------- #
# Resumable storage
# --------------------------------------------------------------------------- #
class ProgressStore:
    """Append-only JSONL log with one line per completed batch."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)

    def read_records(self) -> list[dict]:
        """All complete records; a truncated last line (crash mid-write) is ignored."""
        if not self.path.exists():
            return []
        records: list[dict] = []
        with open(self.path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    logger.warning("Ignoring corrupt line in %s", self.path)
        return records

    def done_keys(self) -> set[str]:
        """Keys of batches that are already finished."""
        return {r["key"] for r in self.read_records() if "key" in r}

    def append(self, record: dict) -> None:
        """Durably append one record."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
            fh.flush()
            os.fsync(fh.fileno())


def _eligible_clients(spec: BatchSpec, healthy: list[LLMClient]) -> list[LLMClient]:
    """Clients allowed to write ``spec`` (regional styles are Gemini-only)."""
    if spec.language in GEMINI_ONLY_LANGUAGES:
        return [c for c in healthy if c.name == "gemini"]
    return healthy


def _pick_client(
    spec: BatchSpec, healthy: list[LLMClient], counts: dict[tuple[str, str], int]
) -> LLMClient | None:
    """Choose the least-loaded eligible provider *for this label*, then its least-used model.

    Balancing per label keeps every provider's scam/safe mix similar, so a
    classifier cannot learn "written by model X" as a proxy for the label. It
    also steers the overall split toward 50/50 even when some batches are
    forced onto one provider.
    """
    eligible = _eligible_clients(spec, healthy)
    if not eligible:
        return None

    def family_load(name: str) -> int:
        return sum(
            n for (label, gen), n in counts.items() if label == spec.label and gen.split("/")[0] == name
        )

    family = min({c.name for c in eligible}, key=lambda n: (family_load(n), n))
    members = [c for c in eligible if c.name == family]
    return min(members, key=lambda c: (counts.get((spec.label, c.generator_id), 0), c.generator_id))


def run_generation(
    plan: list[BatchSpec],
    clients: list[LLMClient],
    store: ProgressStore,
    batch_size: int = DEFAULT_BATCH_SIZE,
    limit_batches: int | None = None,
    seed: int = 0,
    max_consecutive_failures: int = 5,
    on_progress: Callable[[str], None] = print,
) -> dict[str, int]:
    """Generate all pending batches across the healthy providers.

    Provider choice per batch: regional code-mixed styles go to Gemini models only;
    otherwise the provider with the fewest messages *of that label* so far
    (counting earlier runs) is used, so both providers write a similar
    scam/safe mix and the overall split trends to 50/50.

    A batch that hits a quota is retried on another client; a batch that fails
    for other reasons (bad JSON, too few messages, style mismatch, exhausted
    retries) is left unrecorded and retried on the next run.

    Args:
        plan: Batches to produce (already-finished ones are skipped).
        clients: Available clients (one per provider/model).
        store: Progress log.
        batch_size: Messages requested per call.
        limit_batches: Stop after this many *new* batches (for live smoke tests).
        seed: Prompt-variation seed.
        max_consecutive_failures: A client failing this many times in a row is
            dropped for the rest of the run.
        on_progress: Callback for status lines.

    Returns:
        Counters: ``done`` (new batches), ``skipped`` (already done), ``failed``,
        ``messages`` (new messages), ``unroutable`` (no eligible client this run)
        and ``remaining``.
    """
    records = store.read_records()
    done = {r["key"] for r in records if "key" in r}
    counts: dict[tuple[str, str], int] = {}
    for r in records:
        k = (r["label"], f"{r['provider']}/{r['model']}")
        counts[k] = counts.get(k, 0) + len(r["messages"])

    pending = [b for b in plan if b.key not in done]
    stats = {"done": 0, "skipped": len(plan) - len(pending), "failed": 0, "messages": 0, "unroutable": 0}
    healthy = list(clients)
    fail_streak: dict[str, int] = {c.generator_id: 0 for c in clients}

    for spec in pending:
        if limit_batches is not None and stats["done"] >= limit_batches:
            break
        recorded = False
        while not recorded:
            if not healthy:
                on_progress("No healthy providers left; stopping. Re-run later to resume.")
                stats["remaining"] = len(pending) - stats["done"]
                return stats
            client = _pick_client(spec, healthy, counts)
            if client is None:
                stats["unroutable"] += 1  # e.g. regional style but no Gemini model available
                break
            try:
                raw = client.generate(build_prompt(spec, batch_size, seed))
                messages = parse_messages(raw)
                if len(messages) < math.ceil(batch_size * MIN_YIELD_FRACTION):
                    raise ValueError(f"only {len(messages)}/{batch_size} messages returned")
                if spec.label == LABEL_SAFE:
                    messages = [m for m in messages if not safe_rule_violations(m)]
                    if len(messages) < math.ceil(batch_size * MIN_YIELD_FRACTION):
                        raise ValueError("too many safe messages broke the link/OTP rules")
                ok = sum(regional_style_ok(m, spec.language) for m in messages)
                if ok < math.ceil(len(messages) * MIN_YIELD_FRACTION):
                    raise ValueError(f"style mismatch: {ok}/{len(messages)} look like {spec.language}")
            except QuotaExhausted as exc:
                on_progress(f"Quota exhausted, disabling {client.generator_id} for this run: {exc}")
                healthy.remove(client)
                continue  # retry the same batch on another client
            except APIError as exc:
                on_progress(f"Fatal API error, disabling {client.generator_id}: {exc}")
                healthy.remove(client)
                continue
            except (TransientError, ValueError) as exc:
                stats["failed"] += 1
                fail_streak[client.generator_id] += 1
                on_progress(f"Batch failed ({spec.key} via {client.generator_id}): {exc}")
                if fail_streak[client.generator_id] >= max_consecutive_failures:
                    on_progress(f"Disabling {client.generator_id}: {max_consecutive_failures} failures in a row")
                    healthy.remove(client)
                break  # leave unrecorded; retried on the next run

            fail_streak[client.generator_id] = 0
            store.append(
                {
                    "key": spec.key,
                    "label": spec.label,
                    "topic": spec.topic,
                    "scam_type": spec.scam_type,
                    "language": spec.language,
                    "batch_no": spec.batch_no,
                    "provider": client.name,
                    "model": client.model,
                    "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    "messages": messages,
                }
            )
            gk = (spec.label, client.generator_id)
            counts[gk] = counts.get(gk, 0) + len(messages)
            stats["done"] += 1
            stats["messages"] += len(messages)
            recorded = True
            on_progress(
                f"[{stats['done'] + stats['skipped']}/{len(plan)}] {spec.key} "
                f"via {client.generator_id}: {len(messages)} messages"
            )
    stats["remaining"] = len(pending) - stats["done"]
    return stats


def summarize_store(store: ProgressStore) -> str:
    """Messages generated so far, per provider/model and label (the *actual* split)."""
    counts: dict[tuple[str, str], int] = {}
    for r in store.read_records():
        k = (f"{r['provider']}/{r['model']}", r["label"])
        counts[k] = counts.get(k, 0) + len(r["messages"])
    if not counts:
        return "No batches generated yet."
    total = sum(counts.values())
    lines = [f"Generated so far: {total:,} messages"]
    for gen in sorted({g for g, _ in counts}):
        scam, safe = counts.get((gen, LABEL_SCAM), 0), counts.get((gen, LABEL_SAFE), 0)
        lines.append(f"  {gen:<40} scam={scam:>5,}  safe={safe:>5,}  ({(scam + safe) / total:.0%})")
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Loading generated data into the shared schema
# --------------------------------------------------------------------------- #
def regional_style_ok(text: str, language: str) -> bool:
    """True unless ``language`` is a regional code-mixed style and ``text`` is plain English.

    A regional message passes if it is mostly in the native script or contains at
    least one romanized marker word of that language (see :data:`REGIONAL_MARKERS`).
    """
    if language not in REGIONAL_MARKERS:
        return True
    if detect_language(text) == _REGIONAL_SCRIPT[language]:
        return True
    return bool(set(re.findall(r"[a-z]+", text.lower())) & REGIONAL_MARKERS[language])


_MOBILE_RE = re.compile(r"(?<!\d)[6-9](?:[\s-]?\d){9}(?!\d)")
_DOUBLED_PAIRS_RE = re.compile(r"(\d)\1(\d)\2(\d)\3")   # e.g. 998877


def has_placeholder_numbers(text: str) -> bool:
    """True if the message contains obviously fake values.

    Catches the literal placeholders in :data:`_PLACEHOLDER_RE` (``123456``,
    ``98765 43210``, ...) and low-entropy 10-digit mobile numbers such as
    ``9988776655`` (at most four distinct digits, or three doubled pairs in a row).
    """
    if _PLACEHOLDER_RE.search(text):
        return True
    for match in _MOBILE_RE.finditer(text):
        digits = re.sub(r"\D", "", match.group(0))
        if len(set(digits)) <= 4 or _DOUBLED_PAIRS_RE.search(digits):
            return True
    return False


def language_matches(text: str, language: str) -> bool:
    """Cheap sanity check that a message is in the requested script/style.

    Catches common generation errors: Hinglish written in Devanagari, "Hindi" in
    Latin script, Indian English in native script, and regional code-mixed
    styles that came out as plain English.
    """
    detected = detect_language(text)
    if language == "hi":
        return detected == "hi"
    if language == "hinglish":
        return detected != "hi"
    if language == "en":
        return detected in ("en", "hinglish_guess")
    return regional_style_ok(text, language)


# --------------------------------------------------------------------------- #
# Hard-negative rules for "safe" messages (Phase 3.5 audit)
# --------------------------------------------------------------------------- #
# A safe message must not link a bank, government or retailer domain in a context that domain does
# not serve, and must not tell the reader to act on an OTP. Otherwise a classifier learns that
# mismatched domains and OTP requests are safe.
BANK_DOMAINS: dict[str, str] = {   # official domain -> name that should appear in the message
    "hdfcbank.com": r"hdfc", "icicibank.com": r"icici", "axisbank.com": r"axis", "sbi.co.in": r"\bsbi\b",
    "sbicard.com": r"\bsbi\b", "kotak.com": r"kotak", "tatacapital.com": r"tata", "indusind.com": r"indusind",
}
RETAIL_DOMAINS = ("amazon.in", "flipkart.com", "myntra.com", "swiggy.com", "snapdeal.com", "nykaa.com", "paytm.com")
UTILITY_AND_OTHER_DOMAINS = (
    "bsesdelhi.com", "bses.co.in", "bescom.org", "mahadiscom.in", "tatapower.com", "tnebnet.org", "bsnl.co.in",
    "airtel.in", "jio.com", "vodafone.in", "bluedart.com", "delhivery.com", "phonepe.com", "paypal.com",
    "mi.com", "wipro.com", "zoom.us", "meet.google.com", "payu.in", "ecomexpress.in",
)
_BANKING_WORDS = re.compile(
    r"\b(?:bank|a/c|account|loan|emi|credit card|debit|credit|statement|kyc|upi|netbanking|card|salary)\b", re.IGNORECASE
)
_NOT_BANKING = re.compile(
    r"\b(?:hr|hiring|onboarding|career|careers|interview|joining|recruit\w*|candidate|lottery|lucky draw|prize|jackpot|"
    r"electricity|power|discom|phone bill|broadband)\b|बिजली|लॉटरी", re.IGNORECASE
)
_NOT_RETAIL = re.compile(
    r"\b(?:loan|credit card|pre-approved|careers?|jobs?|interview|onboarding|offer letter|joining)\b", re.IGNORECASE
)
_LINK_DOMAIN_RE = re.compile(r"https?://(?:www\.)?([a-z0-9-]+(?:\.[a-z0-9-]+)+)", re.IGNORECASE)
_URL_RE = re.compile(r"https?://\S+")
_INSTITUTION_TOKENS = re.compile(r"tneb|tangedco|hdfc|icici|\bsbi|axis|kotak|uidai|paytm|phonepe|bses|bescom|tata", re.IGNORECASE)
_WARNING_RE = re.compile(
    r"(?:do not|don'?t|never|na |mat |nahi)\W+(?:\w+\W+){0,3}?(?:share|disclose|tell|give)[^.!?]*|"
    r"(?:share|disclose)\s+(?:korben\s+)?(?:na|naka|mat)\b[^.!?]*|(?:शेयर|किसी को)[^.।!?]{0,30}(?:न|नहीं)[^.।!?]*|"
    r"\bno otp needed\b|\bwithout (?:an? )?otp\b|सुरक्षित रखें|keep (?:it|this|the code)? ?(?:safe|secret|private)",
    re.IGNORECASE,
)
_OTP_TERM = r"(?:otp|pin|verification code|confirmation code)"
_OTP_ACT_RE = re.compile(
    _OTP_TERM + r"[^\w.!?।]+(?:\w+[^\w.!?।]+){0,6}?(?:enter|verify|confirm|ready|handover|hand over|deben|dena|cheppandi|tayar|tayaar|"
    r"रखें|रखिए|उपयोग|दर्ज|बताएं)|"
    r"(?:use|enter|verify|confirm|keep|share|give|tell|present|provide|send)[^\w.!?।]+(?:\w+[^\w.!?।]+){0,5}?" + _OTP_TERM + "|"
    r"(?:otp|पिन)[^.!?]{0,40}(?:उपयोग|दर्ज|रखें|उपलब्ध रहें)",
    re.IGNORECASE,
)


def _is_or_under(domain: str, official: str) -> bool:
    """True if ``domain`` is ``official`` or one of its subdomains."""
    return domain == official or domain.endswith("." + official)


def safe_rule_violations(text: str) -> list[str]:
    """Names of the hard-negative rules a *safe* message breaks (empty list = compliant).

    * ``domain_mismatch``: a link whose domain does not fit the message (``uidai.gov.in`` without
      Aadhaar/UIDAI in the text; a bank domain in an HR, prize or utility message, or with neither
      the bank's name nor any banking wording; a retailer domain in a loan, job or prize message).
    * ``lookalike_domain``: a domain containing an institution's name that is not its official domain.
    * ``otp_action``: tells the reader to enter/verify/confirm/keep ready/give an OTP, or to use one
      to receive a delivery. A plain "Your OTP is 482915. Do not share it." notification is allowed.
    """
    out: list[str] = []
    bare = _URL_RE.sub(" ", text)
    for match in _LINK_DOMAIN_RE.finditer(text):
        domain = match.group(1).lower().rstrip(".")
        if _is_or_under(domain, "uidai.gov.in"):
            if not re.search(r"uidai|aadhaar|aadhar|आधार", bare, re.IGNORECASE):
                out.append("domain_mismatch")
        elif any(_is_or_under(domain, bank) for bank in BANK_DOMAINS):
            bank = next(b for b in BANK_DOMAINS if _is_or_under(domain, b))
            named = re.search(BANK_DOMAINS[bank], bare, re.IGNORECASE)
            if _NOT_BANKING.search(bare) or not (named or _BANKING_WORDS.search(bare)):
                out.append("domain_mismatch")
        elif any(_is_or_under(domain, r) for r in RETAIL_DOMAINS):
            if _NOT_RETAIL.search(bare):
                out.append("domain_mismatch")
        elif not any(_is_or_under(domain, u) for u in UTILITY_AND_OTHER_DOMAINS) and _INSTITUTION_TOKENS.search(domain):
            out.append("lookalike_domain")
    if _OTP_ACT_RE.search(_WARNING_RE.sub(" ", text)):
        out.append("otp_action")
    return sorted(set(out))

def load_synthetic(path: Path = DEFAULT_OUTPUT) -> pd.DataFrame:
    """Read the JSONL progress file into a schema-conformant DataFrame.

    Filters applied (counts are logged): length limits, script/style mismatch
    (:func:`language_matches`) and exact duplicates within the synthetic set.
    Returns an empty schema frame if nothing has been generated yet.
    """
    from src.preprocessing.schema import empty_frame

    records = ProgressStore(path).read_records()
    rows: list[tuple[str, str, str, str, str]] = []
    seen: set[str] = set()
    dropped = {"length": 0, "placeholder": 0, "language": 0, "duplicate": 0}
    for rec in records:
        gen = f"{rec['provider']}/{rec['model']}"
        for text in rec["messages"]:
            if not MIN_TEXT_CHARS <= len(text) <= MAX_TEXT_CHARS:
                dropped["length"] += 1
            elif has_placeholder_numbers(text):
                dropped["placeholder"] += 1
            elif not language_matches(text, rec["language"]):
                dropped["language"] += 1
            elif text.casefold() in seen:
                dropped["duplicate"] += 1
            else:
                seen.add(text.casefold())
                rows.append((text, rec["label"], rec["scam_type"], rec["language"], gen))
    logger.info("Synthetic rows kept=%d dropped=%s", len(rows), dropped)
    if not rows:
        return empty_frame()
    texts, labels, types, langs, gens = (list(col) for col in zip(*rows))
    return validate_frame(
        make_frame(
            texts,
            labels,
            source=SOURCE_NAME,
            scam_type=types,
            language=langs,
            is_synthetic=True,
            generator=gens,
            subtype=["fraud" if lab == LABEL_SCAM else "unspecified" for lab in labels],
        ),
        SOURCE_NAME,
    )


def pick_samples(df: pd.DataFrame, n: int = 10, seed: int = 0) -> pd.DataFrame:
    """Pick ``n`` rows for eyeballing: half scam, half safe, spread over languages."""
    rng = random.Random(seed)
    chosen: list[int] = []
    for label, quota in ((LABEL_SCAM, (n + 1) // 2), (LABEL_SAFE, n // 2)):
        part = df[df["label"] == label]
        by_lang = {lang: list(g.index) for lang, g in part.groupby("language")}
        for idxs in by_lang.values():
            rng.shuffle(idxs)
        langs = list(by_lang)
        rng.shuffle(langs)
        picked = 0
        while picked < quota and any(by_lang.values()):
            for lang in langs:
                if picked >= quota:
                    break
                if by_lang[lang]:
                    chosen.append(by_lang[lang].pop())
                    picked += 1
    return df.loc[chosen]


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--provider", choices=["both", "groq", "gemini"], default="both")
    parser.add_argument("--groq-model", default=None)
    parser.add_argument("--gemini-models", default=None, help="comma-separated Gemini model names")
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)
    parser.add_argument("--scale", type=float, default=1.0, help="multiplier on the number of batches")
    parser.add_argument("--limit-batches", type=int, default=None, help="stop after N new batches")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--dry-run", action="store_true", help="print the plan and exit")
    parser.add_argument("--show-samples", type=int, default=0, metavar="N", help="print N samples and exit")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    if args.show_samples:
        df = load_synthetic(args.output)
        if df.empty:
            print("No synthetic data yet.")
            return 1
        for _, row in pick_samples(df, args.show_samples, args.seed).iterrows():
            print(f"[{row['label']}/{row['scam_type']}/{row['language']}/{row['generator']}]")
            print(f"  {row['text']}\n")
        return 0

    plan = build_plan(args.scale, args.seed)
    store = ProgressStore(args.output)
    if args.dry_run:
        done = store.done_keys()
        print(f"{len(plan)} batches planned (~{len(plan) * args.batch_size} messages), "
              f"{sum(b.key in done for b in plan)} already done.")
        return 0

    clients = build_clients(args.provider, args.groq_model, args.gemini_models)
    if not clients:
        print("No API keys found. Set GROQ_API_KEY and/or GEMINI_API_KEY in .env.")
        return 2
    print("Providers: " + ", ".join(c.generator_id for c in clients))
    stats = run_generation(plan, clients, store, args.batch_size, args.limit_batches, args.seed)
    print(f"Done: {stats}")
    print(summarize_store(store))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
