"""Regression tests for src.preprocessing.uci_spam, using real rows read during the manual review."""
from pathlib import Path

import pytest

from src.preprocessing import load_uci
from src.preprocessing.uci_spam import uci_spam_subtype

FRAUD = [
    "WINNER!! As a valued network customer you have been selected to receivea £900 prize reward! To claim call 09061701461. Claim code KL341.",
    "URGENT! Your Mobile No. was awarded a £2000 Bonus Caller Prize on 5/9/03 This is our final try to contact U! Call from Landline 09064019788",
    "Todays Voda numbers ending with 7634 are selected to a receive a £350 reward. If you have a match please call 08712300220",
    "Urgent! Please call 09061213237 from landline. £5000 cash or a luxury 4* Canary Islands Holiday await collection. T&Cs SAE",
    "You have 1 new voicemail. Please call 08719181503",
    "You have 1 new message. Please call 08718738034.",
    "You have an important customer service announcement from PREMIER. Call FREEPHONE 0800 542 0578 now!",
    "Customer service annoncement. You have a New Years delivery waiting for you. Please call 07046744435 now to arrange delivery",
    "U have a secret admirer. REVEAL who thinks U R So special. Call 09065174042. To opt out Reply REVEAL STOP.",
    "Someonone you know is trying to contact you via our dating service! To find out who it could be call from your mobile",
    "We know someone who you know that fancies you. Call 09058097218 to find out who. POBox 6, LS15HB 150p",
    "FREEMSG: Our records indicate you may be entitled to 3750 pounds for the Accident you had. To claim for free reply with CLAIM",
    "PRIVATE! Your 2003 Account Statement for 07815296484 shows 800 un-redeemed S.I.M. points. Call 08718738001 Identifier Code 41782",
    "A £400 XMAS REWARD IS WAITING FOR YOU! Our computer has randomly picked you from our loyal mobile customers to receive",
    "BIG BROTHER ALERT! The computer has selected u for 10k cash or #150 voucher. Call 09064018838. NTT PO Box CRO1327 18+",
    "Latest Nokia Mobile or iPOD MP3 Player +£400 proze GUARANTEED! Reply with: WIN to 83355 now! Norcorp Ltd.£1,50/Mtmsgrcvd18+",
    "Congrats! Nokia 3650 video camera phone is your Call 09066382422 Calls cost 150ppm Ave call 3mins vary from mobiles 16+",
    "U've been selected to stay in 1 of 250 top British hotels - FOR NOTHING! Holiday valued at £350! Dial 08712300220 to claim",
    "okmail: Dear Dave this is your final notice to collect your 4* Tenerife Holiday or #5000 CASH award! Call 09061",
    "(Bank of Granite issues Strong-Buy) EXPLOSIVE PICK FOR OUR MEMBERS *****UP OVER 300% *********** Nasdaq Symbol CDGT",
    "Sunshine Hols. To claim ur med holiday send a stamped self address envelope to Drinks on Us UK, PO Box 113, Bray, Wicklow, Eire. Quiz Starts Saturday! Unsub Stop",
]
PROMO = [
    "Ur ringtone service has changed! 25 Free credits! Go to club4mobiles.com to choose content now! Stop? txt CLUB STOP to 87070. 150p/wk",
    "Last chance 2 claim ur £150 worth of discount vouchers-Text YES to 85023 now!SavaMob-member offers mobile T Cs 08717898035. £3.00 Sub. 16 . Remove txt X or STOP",
    "Dear Voucher Holder, To claim this weeks offer, at you PC please go to http://www.e-tlp.co.uk/expressoffer Ts&Cs apply.",
    "Dear U've been invited to XCHAT. This is our final attempt to contact u! Txt CHAT to 86688 150p/Msgrcvd 18 yrs",
    "You won't believe it but it's true. It's Incredible Txts! Reply G now to learn truly amazing things that",
    "FREE entry into our £250 weekly comp just send the word ENTER to 84128 NOW. 18 T&C www.textcomp.com cust care 08712405020.",
    "Win a £100 High Street prize if u know who the new Duchess of Cornwall will be? Txt her first name to 82277.unsub STOP £1.50",
    "Double your mins & txts on Orange or 1/2 price linerental - Motorola and SonyEricsson with B/Tooth FREE. Call MobileUpd8 on 08000839402",
    "Hi babe its Jordan, how r u? Im home from abroad and lonely, text me back if u wanna chat xxSP visionsms.com Text stop to stop 150p/text",
    "Loan for any purpose £500 - £75,000. Homeowners + Tenants welcome. Have you been previously refused? Call Free 0800 1956669",
]
SERVICE = [
    "Thanks for your ringtone order, ref number R836. Your mobile will be charged £4.50. Should your tone not arrive please call customer services",
    "Ur TONEXS subscription has been renewed and you have been charged £4.50. You can choose 10 more polys this month.",
    "Monthly password for wap. mobsi.com is 391784. Use your wap phone not PC.",
    "Latest News! Police station toilet stolen, cops have nothing to go on!",
    "Do you realize that in about 40 years, we'll have thousands of old ladies running around with tattoos?",
    "88066 FROM 88066 LOST 3POUND HELP",
    "Phony £350 award - Todays Voda numbers ending XXXX are selected to receive a £350 award. If you have a match please call 08712300220",
    "Call from 08702490080 - tells u 2 call 09066358152 to claim £5000 prize. U have 2 enter all ur mobile & personal details @ the prompts. Careful!",
    "Hi ya babe x u 4goten bout me?' scammers getting smart..Though this is a regular vodafone no, if you respond you will get a premium call",
]


@pytest.mark.parametrize("text", FRAUD)
def test_fraud_lures(text: str) -> None:
    assert uci_spam_subtype(text) == "fraud"


@pytest.mark.parametrize("text", PROMO)
def test_promotions(text: str) -> None:
    assert uci_spam_subtype(text) == "promo"


@pytest.mark.parametrize("text", SERVICE)
def test_service_and_personal_messages(text: str) -> None:
    assert uci_spam_subtype(text) == "service"


def test_wont_is_not_won() -> None:
    assert uci_spam_subtype("You won't believe the deals, reply YES to 80000 now! 150p/wk") == "promo"


def test_reviewed_prefix_match_ignores_case_and_whitespace() -> None:
    assert uci_spam_subtype("  PHONY   £350   award - Todays Voda numbers") == "service"


def test_uci_loader_adds_subtypes_and_scam_types(tmp_path: Path) -> None:
    (tmp_path / "SMSSpamCollection").write_text(
        "ham\tSee you at lunch\n"
        "spam\tYOU HAVE WON a £1000 prize! Call 09061701461 to claim\n"
        "spam\tFREE ringtone! Text TONE to 87131 now 150p/wk\n"
        "spam\tLatest News! Police station toilet stolen\n", encoding="utf-8")
    df = load_uci.parse_uci(tmp_path / "SMSSpamCollection")
    assert df["subtype"].tolist() == ["unspecified", "fraud", "promo", "service"]
    assert df["scam_type"].tolist() == ["none", "unknown", "generic_spam", "generic_spam"]
    assert df["label"].tolist() == ["safe", "scam", "scam", "scam"]        # binary label unchanged for now
