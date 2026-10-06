"""Tests for src.ocr.validate: size/type/dimension checks on untrusted image bytes."""
from __future__ import annotations

import io

import numpy as np
import pytest
from PIL import Image

from src.ocr import validate as V
from src.ocr.validate import InvalidImageError, load_image, max_image_bytes, sniff_format


def _encode(img: Image.Image, fmt: str, **kw) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format=fmt, **kw)
    return buf.getvalue()


def _img(w: int = 200, h: int = 120, color=(10, 200, 30)) -> Image.Image:
    return Image.new("RGB", (w, h), color)


# ------------------------------ happy paths ------------------------------ #
@pytest.mark.parametrize("fmt", ["PNG", "JPEG", "WEBP"])
def test_supported_formats_decode_to_rgb_array(fmt: str) -> None:
    arr = load_image(_encode(_img(), fmt))
    assert arr.shape == (120, 200, 3)
    assert arr.dtype == np.uint8


def test_rgba_and_grayscale_are_converted_to_rgb() -> None:
    assert load_image(_encode(Image.new("RGBA", (64, 64), (1, 2, 3, 128)), "PNG")).shape == (64, 64, 3)
    assert load_image(_encode(Image.new("L", (64, 64), 128), "PNG")).shape == (64, 64, 3)


def test_exif_orientation_is_applied() -> None:
    img = _img(200, 100)
    exif = Image.Exif()
    exif[0x0112] = 6  # rotate 90 degrees clockwise on display
    arr = load_image(_encode(img, "JPEG", exif=exif.tobytes()))
    assert arr.shape[:2] == (200, 100)  # now portrait


def test_very_large_image_is_downscaled(monkeypatch) -> None:
    monkeypatch.setattr(V, "MAX_SIDE_PX", 500)
    arr = load_image(_encode(_img(1000, 400), "PNG"))
    assert max(arr.shape[:2]) == 500
    assert arr.shape[:2] == (200, 500)


# ------------------------------ rejections ------------------------------ #
def _code(data: bytes, **kw) -> str:
    with pytest.raises(InvalidImageError) as exc:
        load_image(data, **kw)
    return exc.value.code


def test_empty_is_rejected() -> None:
    assert _code(b"") == "empty"


def test_too_large_is_rejected_before_decoding() -> None:
    assert _code(b"\x89PNG\r\n\x1a\n" + b"0" * 2000, max_bytes=1000) == "too_large"


def test_non_image_renamed_png_is_rejected() -> None:
    assert _code(b"%PDF-1.7 this is not an image at all") == "unsupported_type"
    assert _code(b"<svg xmlns='http://www.w3.org/2000/svg'></svg>") == "unsupported_type"


def test_unsupported_real_image_format_is_rejected() -> None:
    assert _code(_encode(_img(), "GIF")) == "unsupported_type"
    assert _code(_encode(_img(), "BMP")) == "unsupported_type"


def test_png_signature_with_garbage_is_corrupt() -> None:
    assert _code(b"\x89PNG\r\n\x1a\n" + b"garbage" * 20) == "corrupt"


def test_truncated_jpeg_is_corrupt() -> None:
    noisy = Image.fromarray(np.random.default_rng(0).integers(0, 255, (300, 300, 3), dtype=np.uint8))
    data = _encode(noisy, "JPEG")
    assert _code(data[: len(data) // 2]) == "corrupt"


def test_decompression_bomb_is_rejected_from_header(monkeypatch) -> None:
    monkeypatch.setattr(V, "MAX_PIXELS", 100 * 100)
    assert _code(_encode(_img(200, 200), "PNG")) == "too_many_pixels"


def test_tiny_image_is_rejected() -> None:
    assert _code(_encode(_img(20, 400), "PNG")) == "too_small"


def test_error_is_a_value_error_with_message() -> None:
    with pytest.raises(ValueError, match="PNG, JPEG and WebP"):
        load_image(b"not an image")


# ------------------------------ helpers ------------------------------ #
def test_sniff_format() -> None:
    assert sniff_format(_encode(_img(), "PNG")) == "PNG"
    assert sniff_format(_encode(_img(), "JPEG")) == "JPEG"
    assert sniff_format(_encode(_img(), "WEBP")) == "WEBP"
    assert sniff_format(b"RIFF\x00\x00\x00\x00WAVE") is None
    assert sniff_format(b"") is None


def test_max_image_bytes_from_env(monkeypatch) -> None:
    monkeypatch.delenv("OCR_MAX_IMAGE_MB", raising=False)
    assert max_image_bytes() == 5 * 1024 * 1024
    monkeypatch.setenv("OCR_MAX_IMAGE_MB", "2")
    assert max_image_bytes() == 2 * 1024 * 1024
    for bad in ("abc", "-1", "0"):
        monkeypatch.setenv("OCR_MAX_IMAGE_MB", bad)
        assert max_image_bytes() == 5 * 1024 * 1024


def test_env_limit_is_used_by_default(monkeypatch) -> None:
    monkeypatch.setenv("OCR_MAX_IMAGE_MB", "0.001")  # ~1 KB
    data = _encode(Image.fromarray(np.random.default_rng(1).integers(0, 255, (64, 64, 3), dtype=np.uint8)), "PNG")
    assert len(data) > 1100
    assert _code(data) == "too_large"
