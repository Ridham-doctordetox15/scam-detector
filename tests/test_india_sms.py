"""Tests for src.preprocessing.india_sms and the India entry of the Kaggle loader."""
from pathlib import Path

import pandas as pd
import pytest

from src.preprocessing import load_kaggle
from src.preprocessing.india_sms import repair_mojibake, spam_subtype


def test_mojibake_is_repaired_once_and_twice() -> None:
    once = "café".encode("utf-8").decode("latin-1")            # "cafÃ©" (one round)
    assert repair_mojibake(once) == "café"
    twice = "\U0001F44D Yes".encode("utf-8").decode("latin-1").encode("utf-8").decode("latin-1")
    assert repair_mojibake(twice) == "\U0001F44D Yes"


@pytest.mark.parametrize("text", ["plain text", "Rs 500 cashback", "आपका खाता", "café is fine", ""])
def test_clean_text_is_left_alone(text: str) -> None:
    assert repair_mojibake(text) == text


def test_unrepairable_text_is_returned_unchanged() -> None:
    weird = "Ã stray Â bytes Ãx"
    assert repair_mojibake(weird) == weird


@pytest.mark.parametrize("text, expected", [
    ("YOUR WINNING FUND 1 CRORE RUPEES AND iPHONE 15 PROMAX WILL BE ARRIING INDIA", "fraud"),
    ("Your KYC will expire, share your OTP to continue", "fraud"),
    ("Your account will be blocked today, click the link", "fraud"),
    ("Dear Digi Yatri, Your OTP for Digi Yatra App is 779357 Have a seamless journey", "service"),
    ("Dear Customer, You have a missed call from +911244451660", "service"),
    ("50% Daily Data quota used as on 27-Aug-24 16:52 Hrs", "service"),
    ("To cancel a VAS subscription, SMS STOP to or call 155223", "service"),
    ("FLAT Rs40 CASHBACK on Bill Payments. Download Airtel Thanks App. Click i.airtel.in/walletB", "promo"),
    ("Buy1 Get1 FREE with Lenskart Gold Membership this Valentine", "promo"),
    ("Apply for your Olyv loan within 3 days and get 50% off processing fees!", "promo"),
    ("Hurry! Limited Period Offer. Apply Now for Flipkart Axis Bank Credit Card", "promo"),
])
def test_subtype_heuristic(text: str, expected: str) -> None:
    assert spam_subtype(text) == expected


def test_manually_reviewed_rows_override_the_regex() -> None:
    assert spam_subtype("Dear , Prize Pool- 5,00,00,000 (5 Crore). Rs.8850 welcome bonus. Grand Finale") == "promo"
    assert spam_subtype("UIDAI recommends updating Proof of Identity & Address documents in your Aadhaar") == "service"
    assert spam_subtype("Beware of fake calls claiming that your registered mobile number will be blocked.") == "service"
    assert spam_subtype("  DEAR employee,  get Rs. 250 cashback on KYC completion within 3 days") == "promo"


def test_india_spec_is_registered_with_subtypes() -> None:
    spec = load_kaggle.KAGGLE_SPECS["junioralive_india_spam_sms"]
    assert spec.slug == "junioralive/india-spam-sms-classification" and spec.repair_text and spec.subtype_fn is spam_subtype
    assert spec.label_map == {"spam": "scam", "ham": "safe"}


def test_parse_india_csv_maps_labels_subtypes_and_repairs_text(tmp_path: Path) -> None:
    spec = load_kaggle.KAGGLE_SPECS["junioralive_india_spam_sms"]
    mojibake = "\U0001F44D Yes the market is up".encode("utf-8").decode("latin-1").encode("utf-8").decode("latin-1")
    csv = tmp_path / spec.filename
    pd.DataFrame({
        "Msg": ["Click i.airtel.in/x for FREE 5GB", "YOUR WINNING FUND 1 CRORE RUPEES", "Your OTP for Digi Yatra is 123456",
                mojibake, "  ", None],
        "Label": ["spam", "spam", "spam", "ham", "ham", "ham"],
    }).to_csv(csv, index=False)
    df = load_kaggle.parse_kaggle(csv, spec)
    assert len(df) == 4                                            # blank and null rows dropped
    assert df["label"].tolist() == ["scam", "scam", "scam", "safe"]
    assert df["subtype"].tolist() == ["promo", "fraud", "service", "unspecified"]      # safe rows stay unspecified
    assert df["scam_type"].tolist() == ["generic_spam", "unknown", "generic_spam", "none"]
    assert "\U0001F44D" in df["text"].iloc[3] and set(df["source"]) == {"kaggle_india_spam_sms"}
