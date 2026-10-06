"""Curated list of brand names commonly impersonated in Indian phishing/scam URLs.

Not exhaustive - it exists to catch the brands that show up repeatedly in Indian
SMS/WhatsApp/email scams (banks, UPI/payment apps, couriers, e-commerce) plus a
few global brands. Extend :data:`BRANDS` as new impersonation patterns are seen.

Each :class:`Brand` carries the token(s) an attacker might embed in a lookalike
domain (``names`` - often more than one spelling is seen, e.g. both ``"hdfc"``
and ``"hdfcbank"``) and the domains that are genuinely that brand's.
:mod:`src.url_analyzer.analyzer` matches these on whole label boundaries (after
splitting a domain on ``.``/``-``/``_``), never as a raw substring - so a short
name like ``"axis"`` matches the label ``"axis"`` in ``axis-kyc-update.com``
but not the unrelated word ``"taxis"``, because ``"axis" != "taxis"`` even
though one contains the other.
"""
from __future__ import annotations

from dataclasses import dataclass

SHORT_TOKEN_LENGTH = 4


@dataclass(frozen=True)
class Brand:
    """One brand's name token(s) and its genuine domains."""

    names: tuple[str, ...]
    legit_domains: tuple[str, ...]

    @property
    def display_name(self) -> str:
        """The longest/most readable alias, used in human-facing reason strings."""
        return max(self.names, key=len)

    @property
    def short_token(self) -> bool:
        """Whether any alias is short enough to need whole-label (not substring) matching."""
        return any(len(n) <= SHORT_TOKEN_LENGTH for n in self.names)


BRANDS: tuple[Brand, ...] = (
    # --- Indian banks (aliases cover both the short form and the full brand
    # word attackers embed, e.g. "axis" and "axisbank") ---
    Brand(("sbi",), ("sbi.co.in", "onlinesbi.sbi", "onlinesbi.com")),
    Brand(("hdfc", "hdfcbank"), ("hdfcbank.com",)),
    Brand(("icici", "icicibank"), ("icicibank.com",)),
    Brand(("axis", "axisbank"), ("axisbank.com",)),
    Brand(("pnb", "pnbindia"), ("pnbindia.in", "netpnb.com")),
    Brand(("kotak",), ("kotak.com",)),
    Brand(("bankofbaroda",), ("bankofbaroda.in",)),
    Brand(("canara", "canarabank"), ("canarabank.com",)),
    Brand(("unionbank", "unionbankofindia"), ("unionbankofindia.co.in",)),
    Brand(("indianbank",), ("indianbank.in",)),
    Brand(("idbi", "idbibank"), ("idbibank.in",)),
    Brand(("yesbank",), ("yesbank.in",)),
    Brand(("tatacapital",), ("tatacapital.com",)),
    # --- Payment apps / UPI ---
    Brand(("paytm",), ("paytm.com",)),
    Brand(("phonepe",), ("phonepe.com",)),
    Brand(("googlepay",), ("pay.google.com",)),
    Brand(("gpay",), ("pay.google.com",)),
    Brand(("bhim",), ("bhimupi.org.in",)),
    Brand(("mobikwik",), ("mobikwik.com",)),
    Brand(("cred",), ("cred.club",)),
    Brand(("razorpay",), ("razorpay.com",)),
    # --- Couriers / logistics ---
    Brand(("indiapost",), ("indiapost.gov.in",)),
    Brand(("speedpost",), ("indiapost.gov.in",)),
    Brand(("dhl",), ("dhl.com",)),
    Brand(("fedex",), ("fedex.com",)),
    Brand(("bluedart",), ("bluedart.com",)),
    Brand(("delhivery",), ("delhivery.com",)),
    Brand(("dtdc",), ("dtdc.in",)),
    Brand(("ecomexpress",), ("ecomexpress.in",)),
    # --- E-commerce ---
    Brand(("amazon",), ("amazon.in", "amazon.com")),
    Brand(("flipkart",), ("flipkart.com",)),
    Brand(("meesho",), ("meesho.com",)),
    Brand(("myntra",), ("myntra.com",)),
    Brand(("snapdeal",), ("snapdeal.com",)),
    # --- Government / utility (common in Indian scam themes) ---
    Brand(("uidai",), ("uidai.gov.in",)),
    Brand(("incometax",), ("incometax.gov.in",)),
    Brand(("irctc",), ("irctc.co.in",)),
    # --- Global brands seen in Indian phishing ---
    Brand(("microsoft",), ("microsoft.com", "live.com", "outlook.com")),
    Brand(("apple",), ("apple.com", "icloud.com")),
    Brand(("netflix",), ("netflix.com",)),
    Brand(("whatsapp",), ("whatsapp.com",)),
    Brand(("google",), ("google.com",)),
    Brand(("facebook",), ("facebook.com",)),
    Brand(("instagram",), ("instagram.com",)),
)
