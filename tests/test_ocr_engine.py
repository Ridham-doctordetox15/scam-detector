"""Tests for src.ocr.ocr with a fake EasyOCR reader: grouping, dark mode, languages, confidence filter."""
from __future__ import annotations

import numpy as np
import pytest

from src.ocr import ocr as O
from src.ocr.ocr import OCREngine, group_lines, is_dark_mode, parse_languages


def _det(text: str, x0: float, y0: float, x1: float, y1: float, conf: float = 0.9):
    return ([[x0, y0], [x1, y0], [x1, y1], [x0, y1]], text, conf)


class FakeReader:
    """Mimics easyocr.Reader.readtext(image, detail=1, paragraph=False)."""

    def __init__(self, detections) -> None:
        self.detections = detections
        self.images: list[np.ndarray] = []
        self.kwargs: list[dict] = []

    def readtext(self, image, **kwargs):
        self.images.append(image)
        self.kwargs.append(kwargs)
        return self.detections


# ------------------------------ group_lines ------------------------------ #
def test_group_lines_orders_boxes_and_splits_bubbles() -> None:
    dets = [
        _det("world", 120, 100, 200, 126),         # same line as "hello", given out of order
        _det("hello", 20, 102, 110, 128),
        _det("second line", 20, 136, 180, 162),     # small gap -> same bubble
        _det("10:42 AM", 300, 168, 360, 184),       # timestamp row, still same bubble
        _det("new bubble", 20, 240, 170, 266),      # big gap -> new paragraph
    ]
    assert group_lines(dets) == [
        [["hello", "world"], ["second line"], ["10:42 AM"]],
        [["new bubble"]],
    ]


def test_group_lines_skips_blank_text_and_handles_empty() -> None:
    assert group_lines([]) == []
    assert group_lines([_det("  ", 0, 0, 10, 10)]) == []


def test_group_lines_with_slightly_misaligned_boxes() -> None:
    # Baselines differ by a few pixels (different font sizes) but centers overlap.
    dets = [_det("Is this real?", 20, 100, 200, 128), _det("10:39 AM", 260, 106, 330, 124)]
    assert group_lines(dets) == [[["Is this real?", "10:39 AM"]]]


# ------------------------------ dark mode ------------------------------ #
def test_is_dark_mode() -> None:
    assert is_dark_mode(np.full((10, 10, 3), 20, dtype=np.uint8))
    assert not is_dark_mode(np.full((10, 10, 3), 240, dtype=np.uint8))


def test_dark_image_is_inverted_and_passed_as_bgr() -> None:
    img = np.zeros((40, 40, 3), dtype=np.uint8)
    img[..., 0] = 30  # dark, red-tinted
    reader = FakeReader([_det("hi there", 0, 0, 30, 20)])
    result = OCREngine(("en",), reader=reader).read(img)
    assert result.inverted
    seen = reader.images[0]
    # inverted: red 30 -> 225; BGR order puts red last.
    assert seen[0, 0, 2] == 225 and seen[0, 0, 0] == 255
    assert reader.kwargs[0] == {"detail": 1, "paragraph": False}


def test_light_image_is_not_inverted() -> None:
    reader = FakeReader([])
    result = OCREngine(("en",), reader=reader).read(np.full((40, 40, 3), 250, dtype=np.uint8))
    assert not result.inverted
    assert result.text == "" and result.num_boxes == 0 and result.mean_confidence == 0.0


# ------------------------------ read ------------------------------ #
def test_read_filters_low_confidence_and_cleans() -> None:
    reader = FakeReader([
        _det("10:45", 20, 5, 70, 25),
        _det("VoLTE 4G 85%", 550, 5, 700, 25),
        _det("Your KYC is pending.", 20, 100, 300, 126),
        _det("Update now", 20, 134, 160, 160),
        _det("10:42 AM", 400, 166, 460, 182),
        _det("~~#@", 20, 300, 60, 320, conf=0.05),  # junk below min_confidence
        _det("Type a message", 30, 1200, 250, 1230),
    ])
    result = OCREngine(("en",), reader=reader).read(np.full((1280, 720, 3), 250, dtype=np.uint8))
    assert result.text == "Your KYC is pending. Update now"
    assert result.num_boxes == 6
    assert result.mean_confidence == pytest.approx(0.9)
    assert "Type a message" in result.raw_text and "~~#@" not in result.raw_text
    assert result.languages == ("en",)
    assert result.seconds >= 0


# ------------------------------ languages ------------------------------ #
def test_parse_languages_default_and_env(monkeypatch) -> None:
    monkeypatch.delenv("OCR_LANGUAGES", raising=False)
    assert parse_languages() == ("en", "hi")
    monkeypatch.setenv("OCR_LANGUAGES", " EN, hi ,mr,en ")
    assert parse_languages() == ("en", "hi", "mr")
    monkeypatch.setenv("OCR_LANGUAGES", "")
    assert parse_languages() == ("en", "hi")


def test_parse_languages_argument_forms() -> None:
    assert parse_languages("en") == ("en",)
    assert parse_languages(["hi", "en"]) == ("hi", "en")
    assert parse_languages("ch_sim,en") == ("ch_sim", "en")
    assert parse_languages(" , ") == ("en", "hi")


@pytest.mark.parametrize("bad", ["english", "e n", "12", "en;hi", "hi/"])
def test_parse_languages_rejects_malformed_codes(bad: str) -> None:
    with pytest.raises(ValueError, match="Invalid OCR language"):
        parse_languages(bad)


def test_incompatible_language_combination_raises_clear_error(monkeypatch) -> None:
    easyocr = pytest.importorskip("easyocr")

    def fake_reader(langs, **kwargs):  # what EasyOCR does for e.g. hi+ta, without loading models
        raise ValueError("Devanagari is only compatible with English")

    monkeypatch.setattr(easyocr, "Reader", fake_reader)
    with pytest.raises(ValueError, match="Unsupported OCR language combination.*OCR_LANGUAGES"):
        _ = OCREngine(("hi", "ta")).reader


def test_default_engine_is_cached_per_language_set(monkeypatch) -> None:
    monkeypatch.setattr(O, "_engine_cache", {})
    a = O.get_default_ocr_engine("en,hi")
    assert O.get_default_ocr_engine(["en", "hi"]) is a
    assert O.get_default_ocr_engine("en") is not a


# ------------------------------ hybrid mode ------------------------------ #
from src.ocr.ocr import merge_recognitions, script_letter_count  # noqa: E402

BOX_A = [[20, 100], [300, 100], [300, 126], [20, 126]]
BOX_B = [[20, 140], [300, 140], [300, 166], [20, 166]]
BOX_C = [[20, 180], [300, 180], [300, 206], [20, 206]]


def test_script_letter_count() -> None:
    assert script_letter_count("आपका खाता") == 5  # आ प क ख त; the ा vowel signs are marks, not letters
    assert script_letter_count("within २४ hours") == 0  # Devanagari digits are not letters
    assert script_letter_count("café naïve") == 0  # Latin-extended is still Latin


def test_merge_prefers_latin_unless_script_letters_present() -> None:
    latin = [(BOX_A, "within 24 hours", 0.8), (BOX_B, "Aapka khata", 0.3), (BOX_C, "VK-BNKALR", 1.0)]
    script = [(BOX_A, "within २४ hours", 0.7), (BOX_B, "आपका खाता", 0.9), (BOX_C, "VKBNKALR", 0.8)]
    assert merge_recognitions(latin, script) == [
        (BOX_A, "within 24 hours", 0.8),
        (BOX_B, "आपका खाता", 0.9),
        (BOX_C, "VK-BNKALR", 1.0),
    ]


def test_merge_matches_by_box_not_position_and_keeps_unmatched() -> None:
    latin = [(BOX_A, "hello", 0.9), (BOX_B, "xyz", 0.2)]
    script = [(BOX_B, "तुरंत KYC", 0.8)]
    assert merge_recognitions(latin, script) == [(BOX_A, "hello", 0.9), (BOX_B, "तुरंत KYC", 0.8)]


def _horizontal(box) -> list:
    return [box[0][0], box[1][0], box[0][1], box[2][1]]  # EasyOCR's [x0, x1, y0, y1]


class FakeLatinReader:
    def __init__(self, boxes, texts, confs=None) -> None:
        self.boxes, self.texts = boxes, texts
        self.confs = confs or [0.9] * len(boxes)
        self.detect_calls = 0

    def detect(self, image):
        self.detect_calls += 1
        return [[_horizontal(b) for b in self.boxes]], [[]]

    def recognize(self, grey, horizontal, free, **kwargs):
        assert grey.ndim == 2 and kwargs == {"detail": 1, "paragraph": False}
        return list(zip(self.boxes, self.texts, self.confs))


class FakeScriptReader:
    """Returns its reading only for the boxes it is asked to recognize (like EasyOCR)."""

    def __init__(self, boxes, texts) -> None:
        self.readings = {tuple(_horizontal(b)): (b, t) for b, t in zip(boxes, texts)}
        self.horizontal_seen = None

    def recognize(self, grey, horizontal, free, **kwargs):
        self.horizontal_seen = horizontal
        return [(*self.readings[tuple(h)], 0.8) for h in horizontal]

    def readtext(self, *a, **k):  # must never be used in hybrid mode
        raise AssertionError("hybrid mode must not call readtext")


def test_hybrid_engine_rereads_only_uncertain_boxes_and_merges() -> None:
    latin = FakeLatinReader([BOX_A, BOX_B], ["Your KYC: http://x-y.tk/a", "319351 &d5 W1a1"], confs=[0.9, 0.02])
    script = FakeScriptReader([BOX_A, BOX_B], ["Your KYCः httpllx y tkla", "आपका खाता बंद"])
    engine = OCREngine(("en", "hi"), reader=script, latin_reader=latin)
    assert engine.hybrid
    result = engine.read(np.full((300, 400, 3), 250, dtype=np.uint8))
    assert latin.detect_calls == 1
    assert script.horizontal_seen == [[20, 300, 140, 166]]  # only the uncertain box, from the shared detection
    assert result.text == "Your KYC: http://x-y.tk/a आपका खाता बंद"


def test_hybrid_engine_skips_script_pass_when_latin_is_confident() -> None:
    latin = FakeLatinReader([BOX_A], ["Hi there"], confs=[0.95])
    script = FakeScriptReader([BOX_A], ["unused"])
    result = OCREngine(("en", "hi"), reader=script, latin_reader=latin).read(np.full((300, 400, 3), 250, np.uint8))
    assert script.horizontal_seen is None
    assert result.text == "Hi there"


def test_uncertain_latin_box_keeps_latin_reading_if_script_has_no_letters() -> None:
    latin = FakeLatinReader([BOX_A], ["http:lIsbi-kyc-verify.tklupdate"], confs=[0.41])
    script = FakeScriptReader([BOX_A], ["httpillsbi kyc verify tklupdate"])
    result = OCREngine(("en", "hi"), reader=script, latin_reader=latin).read(np.full((300, 400, 3), 250, np.uint8))
    assert script.horizontal_seen == [[20, 300, 100, 126]]
    assert result.text == "http://sbi-kyc-verify.tk/update"


def test_horizontal_key_matches_clipped_recognition_bbox() -> None:
    from src.ocr.ocr import _box_key, _horizontal_key

    assert _horizontal_key([-3, 500, 10, 40], 400, 300) == _box_key([[0, 10], [400, 10], [400, 40], [0, 40]])


def test_hybrid_engine_with_no_detections() -> None:
    engine = OCREngine(("en", "hi"), reader=FakeScriptReader([], []), latin_reader=FakeLatinReader([], []))
    assert engine.read(np.full((100, 100, 3), 250, dtype=np.uint8)).text == ""


@pytest.mark.parametrize("langs, hybrid", [
    (("en", "hi"), True), (("en", "mr", "hi"), True), (("en",), False), (("hi",), False), (("en", "fr"), False),
])
def test_hybrid_mode_selection(langs, hybrid) -> None:
    assert OCREngine(langs).hybrid is hybrid


def test_hybrid_readers_are_built_with_shared_detector(monkeypatch) -> None:
    easyocr = pytest.importorskip("easyocr")
    calls = []
    monkeypatch.setattr(easyocr, "Reader", lambda langs, **kw: calls.append((langs, kw["detector"])) or object())
    OCREngine(("en", "hi")).load()
    assert calls == [(["en", "hi"], False), (["en"], True)]
    calls.clear()
    OCREngine(("en",)).load()
    assert calls == [(["en"], True)]


def test_downloads_enabled_env(monkeypatch) -> None:
    from src.ocr.ocr import downloads_enabled

    monkeypatch.delenv("EASYOCR_DOWNLOAD_ENABLED", raising=False)
    assert downloads_enabled()
    for off in ("0", "false", "No", "off"):
        monkeypatch.setenv("EASYOCR_DOWNLOAD_ENABLED", off)
        assert not downloads_enabled()


def test_reader_receives_download_flag(monkeypatch) -> None:
    easyocr = pytest.importorskip("easyocr")
    seen = []
    monkeypatch.setattr(easyocr, "Reader", lambda langs, **kw: seen.append(kw["download_enabled"]) or object())
    monkeypatch.setenv("EASYOCR_DOWNLOAD_ENABLED", "0")
    OCREngine(("en",)).load()
    assert seen == [False]
