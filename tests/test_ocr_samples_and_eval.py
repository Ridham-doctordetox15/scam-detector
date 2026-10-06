"""Tests for src.ocr.sample_screenshots (rendering) and src.ocr.evaluate (metrics), no EasyOCR needed."""
from __future__ import annotations

import io

import numpy as np
import pytest
from PIL import Image

from src.ocr import sample_screenshots as S
from src.ocr.evaluate import char_error_rate, format_table, keyword_recall, leaked_chrome, SampleEval
from src.ocr.validate import load_image


def test_there_are_four_samples_including_dark_mode() -> None:
    assert len(S.SAMPLES) == 4
    themes = {s.theme.name for s in S.SAMPLES}
    assert "whatsapp_dark" in themes and "sms_light" in themes and "whatsapp_light" in themes
    assert {s.expected_label for s in S.SAMPLES} == {"scam", "safe"}
    assert len({s.name for s in S.SAMPLES}) == 4


@pytest.mark.parametrize("sample", S.SAMPLES, ids=lambda s: s.name)
def test_sample_renders_and_passes_validation(sample: S.SampleScreenshot) -> None:
    img = S.render(sample)
    assert img.size == (S.WIDTH, S.HEIGHT) and img.mode == "RGB"
    arr = load_image(S.to_png_bytes(img))
    assert arr.shape == (S.HEIGHT, S.WIDTH, 3)


def test_rendering_is_deterministic() -> None:
    sample = S.SAMPLES[0]
    assert S.to_png_bytes(S.render(sample)) == S.to_png_bytes(S.render(sample))


def test_dark_sample_is_actually_dark() -> None:
    from src.ocr.ocr import is_dark_mode

    dark = next(s for s in S.SAMPLES if s.theme is S.WHATSAPP_DARK)
    light = next(s for s in S.SAMPLES if s.theme is S.SMS_LIGHT)
    assert is_dark_mode(np.asarray(S.render(dark)))
    assert not is_dark_mode(np.asarray(S.render(light)))


@pytest.mark.parametrize("sample", S.SAMPLES, ids=lambda s: s.name)
def test_ground_truth_contains_keywords_url_but_no_chrome(sample: S.SampleScreenshot) -> None:
    gt = sample.ground_truth
    assert gt.startswith(sample.contact)
    assert keyword_recall(gt, sample.keywords) == 1.0
    if sample.url:
        assert sample.url in gt
    assert leaked_chrome(gt, tuple(c for c in sample.chrome if c != "Today")) == []


def test_wrap_hard_breaks_overlong_tokens() -> None:
    font = S._font(S.BODY_SIZE)
    lines = S._wrap("go " + "x" * 200, font, 300)
    assert all(font.getlength(ln) <= 300 for ln in lines)
    assert "".join(lines).replace("go", "", 1) == "x" * 200


def test_write_samples(tmp_path) -> None:
    paths = S.write_samples(tmp_path / "shots")
    assert len(paths) >= 4
    for p in paths:
        with Image.open(p) as im:
            assert im.size == (S.WIDTH, S.HEIGHT)


def test_devanagari_sample_matches_font_availability() -> None:
    sample = S.devanagari_sample()
    if S.find_devanagari_font() is None:
        assert sample is None
    else:
        assert sample is not None and sample.font_path
        assert S.render(sample).size == (S.WIDTH, S.HEIGHT)


# ------------------------------ metrics ------------------------------ #
def test_char_error_rate() -> None:
    assert char_error_rate("hello world", "hello world") == 0.0
    assert char_error_rate("hello  \n world", "hello world") == 0.0  # whitespace-normalized
    assert char_error_rate("hallo world", "hello world") == pytest.approx(1 / 11)
    assert char_error_rate("", "abcd") == 1.0
    assert char_error_rate("", "") == 0.0
    assert char_error_rate("x", "") == 1.0


def test_keyword_recall() -> None:
    assert keyword_recall("Your KYC is  pending", ("kyc", "is pending", "blocked")) == pytest.approx(2 / 3)
    assert keyword_recall("anything", ()) == 1.0


def test_leaked_chrome_is_whole_word() -> None:
    assert leaked_chrome("msg Delivered", ("Delivered", "Read")) == ["Delivered"]
    assert leaked_chrome("already read it", ("Read",)) == ["Read"]
    assert leaked_chrome("Undelivered parcel", ("Delivered",)) == []
    assert leaked_chrome("at 10:42 AM", ("10:42 AM",)) == ["10:42 AM"]


def test_format_table() -> None:
    row = SampleEval("n", "t", 0.01234, 1.0, True, [], 0.9, 2.5, "scam", "scam", "high", "text")
    table = format_table([row])
    assert "| n | t | 0.012 | 1.00 | yes | 0 | 0.90 | 2.5 | scam | scam / high |" in table
    assert "text" not in table.splitlines()[-1].split("|")[1]
