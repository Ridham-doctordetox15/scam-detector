"""Tests for src.preprocessing.generate_synthetic (no network access)."""
import json
from pathlib import Path

import pytest

from src.preprocessing import generate_synthetic as gs
from src.preprocessing.schema import COLUMNS, SYNTHETIC_SCAM_TYPES


# ------------------------------- fakes ------------------------------------- #
class FakeResponse:
    def __init__(self, status: int = 200, payload: dict | None = None, text: str = "",
                 headers: dict | None = None) -> None:
        self.status_code = status
        self._payload = payload
        self.text = text or (json.dumps(payload) if payload is not None else "")
        self.headers = headers or {}

    def json(self) -> dict:
        if self._payload is None:
            raise ValueError("no json")
        return self._payload


class FakeSession:
    """Returns scripted responses in order; records every request."""

    def __init__(self, responses: list) -> None:
        self.responses = list(responses)
        self.requests: list[dict] = []

    def post(self, url: str, headers: dict, json: dict, timeout: int):  # noqa: A002
        self.requests.append({"url": url, "headers": headers, "json": json})
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def groq_ok(messages: list[str]) -> FakeResponse:
    content = json.dumps({"messages": messages})
    return FakeResponse(200, {"choices": [{"message": {"content": content}}]})


def make_groq(responses: list, sleeps: list[float]) -> gs.GroqClient:
    return gs.GroqClient(
        "test-key", min_interval_s=0.0, session=FakeSession(responses), sleep=sleeps.append
    )


# ------------------------------- plan/prompt ------------------------------- #
def test_plan_size_and_uniqueness() -> None:
    plan = gs.build_plan()
    # 13 batches per topic-language-weight sum x (7 scam + 7 safe + 1 everyday)
    assert len(plan) == sum(gs.LANGUAGE_WEIGHTS.values()) * 15 == 195
    assert len({b.key for b in plan}) == len(plan)


def test_plan_is_balanced_and_covers_all_types_and_languages() -> None:
    plan = gs.build_plan()
    scam = [b for b in plan if b.label == "scam"]
    safe = [b for b in plan if b.label == "safe"]
    assert len(scam) == 91 and len(safe) == 104
    assert {b.topic for b in scam} == set(SYNTHETIC_SCAM_TYPES)
    assert {b.language for b in plan} == set(gs.LANGUAGE_WEIGHTS)
    assert all(b.scam_type == "none" for b in safe)
    assert {b.topic for b in safe} == set(SYNTHETIC_SCAM_TYPES) | {gs.EVERYDAY_TOPIC}
    assert not any(b.label == "scam" and b.topic == gs.EVERYDAY_TOPIC for b in plan)


def test_plan_is_deterministic_and_seed_dependent() -> None:
    assert gs.build_plan(seed=1) == gs.build_plan(seed=1)
    assert gs.build_plan(seed=1) != gs.build_plan(seed=2)


def test_plan_scale() -> None:
    assert len(gs.build_plan(scale=2)) == 2 * 195
    assert len(gs.build_plan(scale=0.1)) < 195


def test_prompt_contains_requirements_and_differs_by_batch() -> None:
    a = gs.build_prompt(gs.BatchSpec("scam", "lottery", "hinglish", 0), 10)
    b = gs.build_prompt(gs.BatchSpec("safe", "lottery", "hinglish", 0), 10)
    assert "exactly 10" in a and "Hinglish" in a and "lottery" in a.lower()
    assert "GENUINE" in b and "GENUINE" not in a
    assert '{"messages"' in a
    assert a == gs.build_prompt(gs.BatchSpec("scam", "lottery", "hinglish", 0), 10)  # reproducible


# ------------------------------- parsing ----------------------------------- #
@pytest.mark.parametrize(
    "raw",
    [
        '{"messages": ["one", "two"]}',
        '["one", "two"]',
        '```json\n{"messages": ["one", "two"]}\n```',
        'Sure! Here you go: {"messages": ["one", "two"]} Hope that helps.',
        '{"messages": [{"text": "one"}, {"message": "two"}, 5, "  "]}',
    ],
)
def test_parse_messages_variants(raw: str) -> None:
    assert gs.parse_messages(raw) == ["one", "two"]


@pytest.mark.parametrize("raw", ["", "not json", '{"messages": []}', '{"other": 1}', '{"messages": [1, 2]}'])
def test_parse_messages_rejects_unusable(raw: str) -> None:
    with pytest.raises(ValueError):
        gs.parse_messages(raw)


# ------------------------------- clients ----------------------------------- #
def test_groq_request_shape_and_extraction() -> None:
    sleeps: list[float] = []
    client = make_groq([groq_ok(["hi there"])], sleeps)
    assert json.loads(client.generate("PROMPT")) == {"messages": ["hi there"]}
    req = client.session.requests[0]
    assert req["headers"]["Authorization"] == "Bearer test-key"
    assert req["json"]["messages"][0]["content"] == "PROMPT"
    assert req["json"]["response_format"] == {"type": "json_object"}
    assert req["json"]["reasoning_effort"] == "low"      # gpt-oss default model
    assert client.generator_id == "groq/openai/gpt-oss-120b"


def test_gemini_request_shape_and_extraction() -> None:
    payload = {"candidates": [{"content": {"parts": [
        {"text": "hidden", "thought": True}, {"text": '{"messages": ["x"]}'}]}}]}
    session = FakeSession([FakeResponse(200, payload)])
    client = gs.GeminiClient("gem-key", min_interval_s=0, session=session, sleep=lambda s: None)
    assert client.generate("P") == '{"messages": ["x"]}'
    req = session.requests[0]
    assert req["headers"] == {"x-goog-api-key": "gem-key"}   # key in header, not URL
    assert "gem-key" not in req["url"]
    assert req["json"]["generationConfig"]["responseMimeType"] == "application/json"


def test_retries_429_with_retry_after_then_succeeds() -> None:
    sleeps: list[float] = []
    client = make_groq(
        [FakeResponse(429, {}, headers={"Retry-After": "7"}), groq_ok(["ok msg"])], sleeps
    )
    client.generate("p")
    assert len(client.session.requests) == 2
    assert max(sleeps) >= 7          # honours Retry-After


def test_retries_5xx_network_and_malformed_bodies() -> None:
    sleeps: list[float] = []
    import requests

    client = make_groq(
        [FakeResponse(503, {}), requests.Timeout(), FakeResponse(200, {"unexpected": 1}), groq_ok(["fine"])],
        sleeps,
    )
    assert "fine" in client.generate("p")
    assert len(client.session.requests) == 4
    assert len(sleeps) == 3


def test_backoff_grows() -> None:
    client = make_groq([], [])
    waits = [client._backoff(a, None) for a in range(4)]
    assert waits[0] < waits[3]
    assert all(w <= 75 for w in waits)      # capped (60 + jitter)


def test_daily_quota_raises_quota_exhausted() -> None:
    body = "Rate limit reached ... on tokens per day (TPD): Limit 100000"
    client = make_groq([FakeResponse(429, text=body)], [])
    with pytest.raises(gs.QuotaExhausted):
        client.generate("p")
    assert len(client.session.requests) == 1       # no pointless retries


def test_long_retry_after_is_treated_as_quota() -> None:
    client = make_groq([FakeResponse(429, {}, headers={"Retry-After": "3600"})], [])
    with pytest.raises(gs.QuotaExhausted):
        client.generate("p")


def test_gemini_retry_delay_in_body_is_parsed() -> None:
    resp = FakeResponse(429, text='{"error": {"details": [{"retryDelay": "34s"}]}}')
    assert gs.LLMClient._retry_after_seconds(resp) == 34.0


def test_client_error_is_not_retried() -> None:
    client = make_groq([FakeResponse(401, text="invalid api key")], [])
    with pytest.raises(gs.APIError, match="401"):
        client.generate("p")
    assert len(client.session.requests) == 1


def test_gives_up_after_max_retries() -> None:
    sleeps: list[float] = []
    client = make_groq([FakeResponse(500, {}) for _ in range(6)], sleeps)
    with pytest.raises(gs.TransientError):
        client.generate("p")
    assert len(client.session.requests) == client.max_retries + 1


def test_throttle_spaces_calls() -> None:
    sleeps: list[float] = []
    now = [100.0]
    client = gs.GroqClient(
        "k", min_interval_s=5.0, session=FakeSession([groq_ok(["a"]), groq_ok(["b"])]),
        sleep=sleeps.append, clock=lambda: now[0],
    )
    client.generate("p")
    assert sleeps == []           # first call is immediate
    now[0] += 2.0
    client.generate("p")
    assert sleeps == [pytest.approx(3.0)]


def test_build_clients_reads_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("dotenv.load_dotenv", lambda *a, **k: None)
    monkeypatch.setenv("GROQ_API_KEY", "g")
    monkeypatch.setenv("GEMINI_API_KEY", "m")
    monkeypatch.delenv("GROQ_MODEL", raising=False)
    monkeypatch.delenv("GEMINI_MODELS", raising=False)
    both = gs.build_clients("both")
    # one Groq client plus one Gemini client per default Gemini model (separate quotas)
    assert [c.name for c in both] == ["groq"] + ["gemini"] * len(gs.DEFAULT_GEMINI_MODELS)
    assert [c.model for c in both if c.name == "gemini"] == list(gs.DEFAULT_GEMINI_MODELS)
    assert [c.name for c in gs.build_clients("gemini")] == ["gemini"] * len(gs.DEFAULT_GEMINI_MODELS)
    custom = gs.build_clients("gemini", gemini_models="model-a, model-b")
    assert [c.model for c in custom] == ["model-a", "model-b"]
    monkeypatch.setenv("GEMINI_MODELS", "env-model")
    assert [c.model for c in gs.build_clients("gemini")] == ["env-model"]
    monkeypatch.delenv("GEMINI_API_KEY")
    assert [c.name for c in gs.build_clients("both")] == ["groq"]


# ------------------------------- run loop ---------------------------------- #
class StubClient:
    """Duck-typed client returning canned messages or raising a scripted error."""

    def __init__(self, name: str, error: Exception | None = None, model: str = "m") -> None:
        self.name, self.model, self.error, self.calls = name, model, error, 0

    @property
    def generator_id(self) -> str:
        return f"{self.name}/{self.model}"

    def generate(self, prompt: str) -> str:
        self.calls += 1
        if self.error:
            raise self.error
        # 5 of the default 10 requested: exactly the minimum accepted yield. Each message
        # carries one marker word per regional language so the style check passes anywhere.
        return json.dumps(
            {"messages": [f"{self.generator_id} message {self.calls} #{i} enna ela ache aahe" for i in range(5)]}
        )


def small_plan(n: int = 6) -> list[gs.BatchSpec]:
    """First ``n`` batches that any provider may write (i.e. not Gemini-only)."""
    return [b for b in gs.build_plan() if b.language not in gs.GEMINI_ONLY_LANGUAGES][:n]


def test_run_balances_providers_within_each_label(tmp_path: Path) -> None:
    store = gs.ProgressStore(tmp_path / "s.jsonl")
    a, b = StubClient("groq"), StubClient("gemini")
    stats = gs.run_generation(gs.build_plan()[:40], [a, b], store, on_progress=lambda s: None)
    assert stats["done"] == 40 and stats["remaining"] == 0
    # Least-loaded selection per label: Groq compensates for the Gemini-only regional
    # batches, so each label ends up close to 50/50 between the two providers.
    recs = store.read_records()
    for label in ("scam", "safe"):
        groq = sum(r["provider"] == "groq" for r in recs if r["label"] == label)
        gem = sum(r["provider"] == "gemini" for r in recs if r["label"] == label)
        assert groq > 0 and gem > 0
        assert abs(groq - gem) <= 2


def test_regional_styles_only_go_to_gemini(tmp_path: Path) -> None:
    store = gs.ProgressStore(tmp_path / "s.jsonl")
    gs.run_generation(gs.build_plan(), [StubClient("groq"), StubClient("gemini")], store,
                      limit_batches=80, on_progress=lambda s: None)
    recs = store.read_records()
    regional = [r for r in recs if r["language"] in gs.GEMINI_ONLY_LANGUAGES]
    assert regional and all(r["provider"] == "gemini" for r in regional)
    assert any(r["provider"] == "groq" for r in recs)          # others still use Groq


def test_regional_batches_wait_when_no_gemini_available(tmp_path: Path) -> None:
    store = gs.ProgressStore(tmp_path / "s.jsonl")
    plan = gs.build_plan()
    stats = gs.run_generation(plan, [StubClient("groq")], store, on_progress=lambda s: None)
    n_regional = sum(b.language in gs.GEMINI_ONLY_LANGUAGES for b in plan)
    assert stats["unroutable"] == n_regional
    assert stats["done"] == len(plan) - n_regional
    assert all(r["language"] not in gs.GEMINI_ONLY_LANGUAGES for r in store.read_records())


def test_multiple_gemini_models_share_load(tmp_path: Path) -> None:
    store = gs.ProgressStore(tmp_path / "s.jsonl")
    g1, g2 = StubClient("gemini", model="flash"), StubClient("gemini", model="lite")
    gs.run_generation(gs.build_plan(), [g1, g2], store, limit_batches=30, on_progress=lambda s: None)
    assert abs(g1.calls - g2.calls) <= 2 and g1.calls > 0 and g2.calls > 0


def test_style_mismatch_batches_are_rejected(tmp_path: Path) -> None:
    class PlainEnglish(StubClient):
        def generate(self, prompt: str) -> str:
            return json.dumps({"messages": [f"Your parcel number {i} is waiting at the depot" for i in range(10)]})

    plan = [b for b in gs.build_plan() if b.language == "ta_en"][:2]
    store = gs.ProgressStore(tmp_path / "s.jsonl")
    stats = gs.run_generation(plan, [PlainEnglish("gemini")], store, on_progress=lambda s: None)
    assert stats["done"] == 0 and stats["failed"] == 2
    assert store.done_keys() == set()


def test_summarize_store_reports_actual_split(tmp_path: Path) -> None:
    store = gs.ProgressStore(tmp_path / "s.jsonl")
    assert "No batches" in gs.summarize_store(store)
    gs.run_generation(gs.build_plan()[:10], [StubClient("groq"), StubClient("gemini")], store,
                      on_progress=lambda s: None)
    text = gs.summarize_store(store)
    assert "groq/m" in text and "gemini/m" in text and "scam=" in text and "%" in text


def test_run_is_resumable(tmp_path: Path) -> None:
    store = gs.ProgressStore(tmp_path / "s.jsonl")
    plan = small_plan(6)
    gs.run_generation(plan, [StubClient("groq")], store, limit_batches=2, on_progress=lambda s: None)
    assert len(store.done_keys()) == 2
    client = StubClient("groq")
    stats = gs.run_generation(plan, [client], store, on_progress=lambda s: None)
    assert stats["skipped"] == 2 and stats["done"] == 4 and client.calls == 4
    stats = gs.run_generation(plan, [client], store, on_progress=lambda s: None)
    assert stats["done"] == 0 and client.calls == 4         # nothing left to do


def test_run_disables_provider_on_quota_and_continues(tmp_path: Path) -> None:
    store = gs.ProgressStore(tmp_path / "s.jsonl")
    dead = StubClient("groq", error=gs.QuotaExhausted("daily"))
    alive = StubClient("gemini")
    stats = gs.run_generation(small_plan(4), [dead, alive], store, on_progress=lambda s: None)
    assert dead.calls <= 1                          # disabled after first quota error
    assert stats["done"] == 4                       # the batch that hit quota is retried on gemini
    assert {r["provider"] for r in store.read_records()} == {"gemini"}
    assert stats["remaining"] == 0


def test_run_stops_when_no_provider_left(tmp_path: Path) -> None:
    store = gs.ProgressStore(tmp_path / "s.jsonl")
    msgs: list[str] = []
    stats = gs.run_generation(
        small_plan(3), [StubClient("groq", error=gs.QuotaExhausted("x"))], store, on_progress=msgs.append
    )
    assert stats["done"] == 0 and any("No healthy providers" in m for m in msgs)


def test_run_skips_unparseable_batches_without_recording(tmp_path: Path) -> None:
    class Garbage(StubClient):
        def generate(self, prompt: str) -> str:
            return "definitely not json"

    store = gs.ProgressStore(tmp_path / "s.jsonl")
    stats = gs.run_generation(
        small_plan(3), [Garbage("groq")], store, max_consecutive_failures=2, on_progress=lambda s: None
    )
    assert stats["done"] == 0 and stats["failed"] == 2      # provider dropped after 2 in a row
    assert store.done_keys() == set()


def test_run_rejects_low_yield_batches(tmp_path: Path) -> None:
    class OneMessage(StubClient):
        def generate(self, prompt: str) -> str:
            return json.dumps({"messages": ["just one message here"]})

    store = gs.ProgressStore(tmp_path / "s.jsonl")
    stats = gs.run_generation(
        small_plan(2), [OneMessage("groq")], store, batch_size=10, on_progress=lambda s: None
    )
    assert stats["done"] == 0 and stats["failed"] == 2
    assert store.done_keys() == set()          # will be retried on the next run


def test_run_disables_provider_on_fatal_api_error(tmp_path: Path) -> None:
    store = gs.ProgressStore(tmp_path / "s.jsonl")
    bad = StubClient("groq", error=gs.APIError("401"))
    stats = gs.run_generation(small_plan(3), [bad], store, on_progress=lambda s: None)
    assert bad.calls == 1 and stats["done"] == 0


def test_progress_store_ignores_truncated_last_line(tmp_path: Path) -> None:
    path = tmp_path / "s.jsonl"
    store = gs.ProgressStore(path)
    store.append({"key": "a", "messages": ["x"]})
    with open(path, "a", encoding="utf-8") as fh:
        fh.write('{"key": "b", "mess')       # crash mid-write
    assert store.done_keys() == {"a"}


# --------------------------- schema conversion ----------------------------- #
def _record(**overrides) -> dict:
    rec = {"key": "k", "label": "scam", "topic": "lottery", "scam_type": "lottery",
           "language": "hinglish", "provider": "groq", "model": "m", "messages": []}
    rec.update(overrides)
    return rec


def test_load_synthetic_builds_schema_frame(tmp_path: Path) -> None:
    store = gs.ProgressStore(tmp_path / "s.jsonl")
    store.append(_record(messages=["Aapka lottery jeeta hai, kya aap claim karo abhi"]))
    store.append(_record(key="k2", label="safe", topic="everyday", scam_type="none",
                         provider="gemini", model="g", language="en",
                         messages=["Are we meeting at the office tomorrow?"]))
    df = gs.load_synthetic(tmp_path / "s.jsonl")
    assert list(df.columns) == COLUMNS
    assert df["is_synthetic"].all()
    assert df["source"].unique().tolist() == ["synthetic_llm"]
    assert sorted(df["generator"]) == ["gemini/g", "groq/m"]
    assert df.set_index("label")["scam_type"].to_dict() == {"scam": "lottery", "safe": "none"}


def test_load_synthetic_filters_bad_rows(tmp_path: Path) -> None:
    store = gs.ProgressStore(tmp_path / "s.jsonl")
    good = "Aapka account band ho jayega, kya aap abhi verify karo"
    store.append(_record(messages=[
        good,
        good.upper(),                       # duplicate (case-insensitive)
        "short",                            # too short
        "x" * 800,                          # too long
        "आपका खाता बंद हो जाएगा आज ही",     # Devanagari but labelled hinglish
        "Aapka OTP 123456 hai, kya aap abhi verify karo",     # placeholder-looking number
    ]))
    store.append(_record(key="k2", language="ta_en",
                         messages=["Your parcel is held, pay the fee at once please",   # plain English
                                   "Unga parcel hold la irukku, seri pannunga fee kudunga"]))
    df = gs.load_synthetic(tmp_path / "s.jsonl")
    assert df["text"].tolist() == [good, "Unga parcel hold la irukku, seri pannunga fee kudunga"]


def test_load_synthetic_empty_when_no_file(tmp_path: Path) -> None:
    df = gs.load_synthetic(tmp_path / "missing.jsonl")
    assert df.empty and list(df.columns) == COLUMNS


def test_language_matches() -> None:
    assert gs.language_matches("आपका खाता बंद हो जाएगा", "hi")
    assert not gs.language_matches("Aapka account band ho jayega", "hi")
    assert gs.language_matches("Your parcel is held at customs", "en")
    assert not gs.language_matches("आपका खाता बंद हो जाएगा", "hinglish")
    # regional styles must not be plain English
    assert not gs.language_matches("Your parcel is held at customs", "ta_en")
    assert gs.language_matches("Unga parcel customs la irukku, seri pannunga", "ta_en")
    assert gs.language_matches("உங்கள் பார்சல் தடுக்கப்பட்டது", "ta_en")           # native script
    assert gs.language_matches("तुमचा parcel customs मध्ये आहे", "mr_en")          # Devanagari
    assert not gs.language_matches("Aapka parcel customs mein hai", "bn_en")      # Hinglish != Bengali
    assert gs.language_matches("Apnar account block hobe, korun verify", "bn_en")


@pytest.mark.parametrize("text", [
    # genuine Telugu-English written by Gemini that an earlier, shorter marker list rejected
    "Meeka Amazon package ready ayyindi, eeroju evening kalla reach avuthundi.",
    "Myntra order dispatched! Ee tracking link nunchi status chusukovachu.",
    "Express delivery update: Delivery person local route lo unnadu, konchem response ivvandi.",
])
def test_regional_style_accepts_genuine_telugu_english(text: str) -> None:
    assert gs.regional_style_ok(text, "te_en")


def test_regional_style_ok_only_applies_to_regional_languages() -> None:
    assert gs.regional_style_ok("plain english text", "en")
    assert gs.regional_style_ok("plain english text", "hinglish")
    assert not gs.regional_style_ok("plain english text", "te_en")
    assert gs.regional_style_ok("meeru ela unnaru", "te_en")


@pytest.mark.parametrize("text", [
    "Your OTP is 123456", "OTP 112233 bhejein", "call 9876543210", "call 98765 43210",
    "call 98765-43210", "ref XYZ123", "link fastcash.in/abcde", "code 000000", "pin 1234",
    "call 9988776655 now", "call 99887 76655", "call 9999988888", "call 8080808080",
])
def test_placeholder_numbers_detected(text: str) -> None:
    assert gs.has_placeholder_numbers(text)


@pytest.mark.parametrize("text", [
    "Your OTP is 482915", "Call 9354718206", "Ref PRZ-2023-00123", "Rs 12,345 debited",
    "Order 51234567 shipped", "Txn ID 4839201",
    "Call 9354718206", "Call 98204 71635", "Call 7392058146", "Pay Rs 10000 today",
])
def test_realistic_numbers_not_flagged(text: str) -> None:
    assert not gs.has_placeholder_numbers(text)


def test_prompt_forbids_placeholders_and_requires_regional_words() -> None:
    p = gs.build_prompt(gs.BatchSpec("scam", "fake_bank_otp", "ta_en", 0), 10)
    assert "123456" in p and "never use placeholder" in p
    assert "MUST genuinely contain" in p
    hinglish = gs.build_prompt(gs.BatchSpec("scam", "fake_bank_otp", "hinglish", 0), 10)
    assert "MUST genuinely contain" not in hinglish
    assert "more than two messages" in hinglish


def test_pick_samples_mixes_labels_and_languages(tmp_path: Path) -> None:
    store = gs.ProgressStore(tmp_path / "s.jsonl")
    for i, lang in enumerate(["hinglish", "en", "ta_en"]):
        for label in ("scam", "safe"):
            store.append(_record(
                key=f"{label}{i}", label=label, language=lang,
                scam_type="lottery" if label == "scam" else "none",
                messages=[f"Sample {label} message number {j} in {lang} here enna" for j in range(4)],
            ))
    df = gs.load_synthetic(tmp_path / "s.jsonl")
    picked = gs.pick_samples(df, 6, seed=1)
    assert len(picked) == 6
    assert picked["label"].value_counts().to_dict() == {"scam": 3, "safe": 3}
    assert picked["language"].nunique() == 3


# ------------------------- hard-negative rules for safe rows ----------------- #
@pytest.mark.parametrize("text", [
    "Your OTP is 482915. Do not share it with anyone. - HDFC Bank",
    "Your OTP for UPI payment is 592831. Use within 5 minutes. Do not share this OTP with anyone.",
    "HDFC Bank: KYC is mandatory for A/C xx7319. Kindly login to official NetBanking or visit the nearest branch.",
    "Your Amazon order #123X is out for delivery today. Track at https://www.amazon.in/track",
    "Dear HDFC customer, your loan statement is ready: https://www.hdfcbank.com/loans",
    "Aapka Amazon Pay KYC pending hai. Update via https://www.amazon.in/kyc",
    "Bill Rs 1450 generated. Pay via https://pay.bses.co.in/5F8D2C9A",
    "Aadhaar update request processed. Details at https://uidai.gov.in",
    "ICICI Bank: kono OTP ba PIN share korben na. Branch e visit korun.",
    "Discount code SAVE20 ka use kar sakte ho.",
])
def test_safe_rules_accept_genuine_messages(text: str) -> None:
    assert gs.safe_rule_violations(text) == []


@pytest.mark.parametrize("text,rule", [
    ("Your pre-approved home loan offer is active. View at https://uidai.gov.in/loanoffer", "domain_mismatch"),
    ("Kal ki lottery ka prize link: https://uidai.gov.in/lottery", "domain_mismatch"),
    ("Onboarding checklist: https://www.hdfcbank.com/employee/onboarding", "domain_mismatch"),
    ("Pre-approved credit card offer, apply at https://www.amazon.in/creditoffer", "domain_mismatch"),
    ("Pay your bill at https://www.tnebltd.gov.in", "lookalike_domain"),
    ("Pay at https://www.tatapower.gov.in/pay", "lookalike_domain"),
    ("Use OTP 839274 to receive the package.", "otp_action"),
    ("Please keep OTP 941572 ready. Regards, DHL India", "otp_action"),
    ("Delivery boy asle 5819 OTP ta deben.", "otp_action"),
    ("Secure login ke liye OTP 849302 enter karein.", "otp_action"),
    ("Verify delivery with OTP 658301 at the doorstep.", "otp_action"),
])
def test_safe_rules_flag_violations(text: str, rule: str) -> None:
    assert rule in gs.safe_rule_violations(text)


def test_safe_prompt_states_link_and_otp_rules_but_scam_prompt_does_not() -> None:
    safe = gs.build_prompt(gs.BatchSpec("safe", "courier_customs", "hinglish", 0), 10)
    scam = gs.build_prompt(gs.BatchSpec("scam", "courier_customs", "hinglish", 0), 10)
    assert "official domain of the very organisation" in safe and "look-alike" in safe
    assert "never tell the reader to enter" in safe and "must not mention any OTP" in safe
    assert "e.g. hdfcbank.com, amazon.in, uidai.gov.in" not in safe     # the old wording that caused mismatches
    assert "official domain of the very organisation" not in scam


def test_run_drops_safe_messages_that_break_the_rules(tmp_path: Path) -> None:
    class BadSafe(StubClient):
        def generate(self, prompt: str) -> str:
            self.calls += 1
            msgs = [f"Pay via https://uidai.gov.in/pay?{i} enna ela ache aahe" for i in range(3)]
            msgs += [f"Plain ok message {i} enna ela ache aahe" for i in range(6)]
            return json.dumps({"messages": msgs})

    plan = [b for b in small_plan(40) if b.label == "safe"][:1]
    store = gs.ProgressStore(tmp_path / "s.jsonl")
    gs.run_generation(plan, [BadSafe("groq")], store, on_progress=lambda s: None)
    (rec,) = store.read_records()
    assert len(rec["messages"]) == 6 and all("uidai" not in m for m in rec["messages"])
