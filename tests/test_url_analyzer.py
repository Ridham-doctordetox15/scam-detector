"""Tests for src.url_analyzer: rule-based scoring, brand lookalikes, offline lists."""
from __future__ import annotations

from pathlib import Path

import pytest

from src.url_analyzer import analyzer as A
from src.url_analyzer import offline_lists as OL

LEGITIMATE_URLS = [
    "https://www.hdfcbank.com/personal/pay/cards/credit-cards",
    "https://sbi.co.in/web/personal-banking",
    "https://axisbank.com/",
    "https://www.paytm.com/offer/cashback",
    "https://www.amazon.in/gp/css/order-history",
    "https://track.delhivery.com/track/package/12345",
]


@pytest.mark.parametrize("url", LEGITIMATE_URLS)
def test_legitimate_urls_score_low_with_no_reasons(url: str) -> None:
    finding = A.analyze_url(url)
    assert finding.score == 0.0
    assert finding.reasons == []


# ---------------------------- individual signal checks ---------------------------- #
def test_ip_based_url_is_flagged() -> None:
    finding = A.analyze_url("http://192.168.10.55/login/verify.php")
    assert any("raw IP address" in r for r in finding.reasons)


def test_at_symbol_trick_is_flagged() -> None:
    finding = A.analyze_url("http://account-support@customer-verification-portal.net/kyc")
    assert any('"@"' in r for r in finding.reasons)


@pytest.mark.parametrize("url", [
    "https://hdfcbank-verify.tk/update-kyc",
    "https://hdfcbank-verify.com/update-kyc",  # non-suspicious TLD: proves it's not the TLD rule
    "https://sbi-kyc-update.com/verify",
    "https://paytm-secure-login.in/pay",
    "https://tata-capital-service.in/loan",
])
def test_combosquat_brand_is_flagged(url: str) -> None:
    finding = A.analyze_url(url)
    assert any("embeds the brand name" in r for r in finding.reasons)


def test_combosquat_on_com_does_not_rely_on_suspicious_tld() -> None:
    finding = A.analyze_url("https://hdfcbank-verify.com/update-kyc")
    assert not any("top-level domain" in r for r in finding.reasons)
    assert any("embeds the brand name" in r for r in finding.reasons)


def test_brand_as_subdomain_is_flagged() -> None:
    finding = A.analyze_url("http://hdfcbank.com.secure-login.xyz/reset")
    assert any("appears as a subdomain of a different site" in r for r in finding.reasons)


def test_single_char_lookalike_is_flagged() -> None:
    finding = A.analyze_url("https://hdfcbnk.com/login")
    assert any("closely resembles the brand" in r for r in finding.reasons)


def test_punycode_domain_is_flagged() -> None:
    finding = A.analyze_url("https://xn--hdfcbank-mtb.com/login")
    assert any("punycode" in r for r in finding.reasons)


def test_known_shortener_is_flagged() -> None:
    finding = A.analyze_url("https://bit.ly/3kyc-update")
    assert any("URL shortener" in r for r in finding.reasons)


def test_excessive_subdomains_is_flagged() -> None:
    finding = A.analyze_url("https://a.b.c.free-gift-claim.com/verify")
    assert any("high number of subdomains" in r for r in finding.reasons)


def test_very_long_url_is_flagged() -> None:
    long_url = "https://free-gift-claim-portal-verification.com/" + "a" * 40
    finding = A.analyze_url(long_url)
    assert any("Unusually long URL" in r for r in finding.reasons)


def test_missing_https_is_flagged() -> None:
    finding = A.analyze_url("http://paytm.com/pay")
    assert any("not HTTPS" in r for r in finding.reasons)


def test_bare_domain_with_no_scheme_is_parsed() -> None:
    """mask_urls (Phase 2) yields bare domains with no http(s):// prefix."""
    finding = A.analyze_url("sbi-kyc-update.com/verify")
    assert any("embeds the brand name" in r for r in finding.reasons)


# ---------------------------- suspicious keyword signal ---------------------------- #
def test_suspicious_keyword_in_path_is_flagged() -> None:
    finding = A.analyze_url("https://free-prize-portal.com/claim/bonus")
    assert any("suspicious keyword" in r and "claim" in r and "bonus" in r for r in finding.reasons)


def test_suspicious_keyword_weight_is_capped() -> None:
    # 6 distinct keywords across domain + path: verify, kyc, update (domain),
    # secure, login, account (path) - capped at 0.3, not 0.1 * 6 = 0.6.
    url = "https://totally-legit-verify-kyc-update.com/secure/login/account"
    finding = A.analyze_url(url)
    assert finding.score == pytest.approx(0.3)
    keyword_reasons = [r for r in finding.reasons if "suspicious keyword" in r]
    assert len(keyword_reasons) == 1
    for kw in ("verify", "kyc", "update", "secure", "login", "account"):
        assert kw in keyword_reasons[0]


@pytest.mark.parametrize("url", [
    "https://www.hdfcbank.com/personal/pay/cards/credit-cards",
    "http://paytm.com/pay",
])
def test_suspicious_keyword_does_not_fire_on_normal_paths(url: str) -> None:
    finding = A.analyze_url(url)
    assert not any("suspicious keyword" in r for r in finding.reasons)


def test_real_looking_brand_login_url_stays_low_risk_despite_keyword() -> None:
    """A genuine bank NetBanking login page legitimately has "login" in its path."""
    finding = A.analyze_url("https://netbanking.hdfcbank.com/corporate/login")
    assert any("suspicious keyword" in r and "login" in r for r in finding.reasons)
    assert not any("embeds the brand name" in r for r in finding.reasons)
    assert finding.risk_band == "low"
    assert finding.score < 0.3


def test_ip_based_url_keyword_check_ignores_garbage_domain_parse() -> None:
    """An IP host has no meaningful "domain" - only the path should be scanned."""
    finding = A.analyze_url("http://192.168.10.55/kyc/update")
    keyword_reasons = [r for r in finding.reasons if "suspicious keyword" in r]
    assert len(keyword_reasons) == 1
    assert "kyc" in keyword_reasons[0] and "update" in keyword_reasons[0]


# ---------------------------- risk bands ---------------------------- #
@pytest.mark.parametrize("score, expected", [
    (0.0, "low"),
    (0.29, "low"),
    (0.3, "medium"),
    (0.59, "medium"),
    (0.6, "high"),
    (1.0, "high"),
])
def test_risk_band_thresholds(score: float, expected: str) -> None:
    assert A.risk_band(score) == expected


def test_finding_risk_band_property_matches_score() -> None:
    finding = A.analyze_url("https://www.hdfcbank.com/personal/pay/cards/credit-cards")
    assert finding.risk_band == "low"


# ---------------------------- false-positive guards ---------------------------- #
@pytest.mark.parametrize("url", [
    "https://taxis-booking.com/ride",
    "https://praxis-clinic.org/appointments",
])
def test_short_brand_token_does_not_match_inside_unrelated_words(url: str) -> None:
    finding = A.analyze_url(url)
    assert not any("embeds the brand name" in r for r in finding.reasons)


def test_ip_url_is_not_also_flagged_for_excessive_subdomains() -> None:
    finding = A.analyze_url("http://192.168.10.55/login")
    assert not any("subdomains" in r for r in finding.reasons)


# ---------------------------- score behaviour ---------------------------- #
def test_score_is_clamped_to_one() -> None:
    finding = A.analyze_url("http://hdfcbank.com.secure-login.xyz/reset")
    assert 0.0 <= finding.score <= 1.0


def test_analyze_urls_scores_each_independently() -> None:
    findings = A.analyze_urls(["https://paytm.com/pay", "http://192.168.10.55/login"])
    assert len(findings) == 2
    assert findings[0].score < findings[1].score


# ---------------------------- offline lists ---------------------------- #
def test_offline_list_match_is_flagged() -> None:
    listed = OL.OfflineURLList({"http://evil-phish.example/login"}, "PhishTank")
    finding = A.analyze_url("http://evil-phish.example/login", offline_lists=[listed])
    assert any("Listed in PhishTank" in r for r in finding.reasons)
    assert finding.score >= 0.9


def test_offline_list_no_match_does_not_flag() -> None:
    listed = OL.OfflineURLList({"http://evil-phish.example/login"}, "PhishTank")
    finding = A.analyze_url("https://paytm.com/pay", offline_lists=[listed])
    assert not any("Listed in" in r for r in finding.reasons)


def test_load_phishtank_from_csv(tmp_path: Path) -> None:
    csv_path = tmp_path / "online-valid.csv"
    csv_path.write_text(
        "phish_id,url,phish_detail_url\n"
        "1,http://evil-phish.example/login,http://phishtank.org/1\n",
        encoding="utf-8",
    )
    phishtank = OL.load_phishtank(csv_path)
    assert phishtank.is_listed("http://evil-phish.example/login")
    assert phishtank.is_listed("http://evil-phish.example/login/")  # trailing slash tolerant
    assert not phishtank.is_listed("https://paytm.com/pay")


def test_load_phishtank_missing_file_returns_empty_list(tmp_path: Path) -> None:
    phishtank = OL.load_phishtank(tmp_path / "does-not-exist.csv")
    assert len(phishtank) == 0
    assert not phishtank.is_listed("http://evil-phish.example/login")


def test_load_openphish_from_txt(tmp_path: Path) -> None:
    txt_path = tmp_path / "feed.txt"
    txt_path.write_text("http://evil-phish.example/login\nhttp://other-bad.example/x\n", encoding="utf-8")
    openphish = OL.load_openphish(txt_path)
    assert openphish.is_listed("http://evil-phish.example/login")
    assert not openphish.is_listed("https://paytm.com/pay")


def test_load_openphish_missing_file_returns_empty_list(tmp_path: Path) -> None:
    openphish = OL.load_openphish(tmp_path / "does-not-exist.txt")
    assert len(openphish) == 0


# ---------------------------- refresh scripts (no real network calls) ---------------------------- #
def test_refresh_phishtank_raises_without_app_key(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from src.url_analyzer import refresh_phishtank as RP

    monkeypatch.delenv("PHISHTANK_APP_KEY", raising=False)
    with pytest.raises(RuntimeError, match="PHISHTANK_APP_KEY"):
        RP.refresh_phishtank(tmp_path / "online-valid.csv")


def test_refresh_phishtank_writes_response_body(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from src.url_analyzer import refresh_phishtank as RP

    class FakeResponse:
        content = b"phish_id,url\n1,http://evil.example/x\n"

        def raise_for_status(self) -> None:
            pass

    monkeypatch.setenv("PHISHTANK_APP_KEY", "fake-key")
    monkeypatch.setattr(RP.requests, "get", lambda *a, **kw: FakeResponse())
    output = tmp_path / "online-valid.csv"
    result_path = RP.refresh_phishtank(output)
    assert result_path == output
    assert output.read_bytes() == FakeResponse.content


def test_refresh_openphish_writes_response_body(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from src.url_analyzer import refresh_openphish as RO

    class FakeResponse:
        content = b"http://evil.example/x\n"

        def raise_for_status(self) -> None:
            pass

    monkeypatch.setattr(RO.requests, "get", lambda *a, **kw: FakeResponse())
    output = tmp_path / "feed.txt"
    result_path = RO.refresh_openphish(output)
    assert result_path == output
    assert output.read_bytes() == FakeResponse.content
