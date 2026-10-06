"""Validate and decode an uploaded screenshot before OCR.

Uploaded bytes are untrusted. This module never trusts a filename or a
client-supplied content type: the format is sniffed from the file's magic
bytes, Pillow then fully decodes the image, and size/dimension limits guard
against oversized uploads and decompression bombs.

Every rejection raises :class:`InvalidImageError` with a machine-readable
``code`` so the API layer (Phase 9) can map it to a 4xx response without
parsing error strings.
"""
from __future__ import annotations

import io
import os
import warnings

import numpy as np
from PIL import Image, ImageOps

DEFAULT_MAX_IMAGE_MB = 5.0
MAX_PIXELS = 25_000_000  # ~25 MP; a 1080x2400 phone screenshot is ~2.6 MP
MIN_SIDE_PX = 32
# Longest side after downscaling. Keeps CPU OCR time reasonable while staying
# well above the resolution EasyOCR needs for phone-sized text.
MAX_SIDE_PX = 3000

# Magic-byte signatures -> format name. Only these formats are accepted.
_SIGNATURES: list[tuple[bytes, str]] = [
    (b"\x89PNG\r\n\x1a\n", "PNG"),
    (b"\xff\xd8\xff", "JPEG"),
]


class InvalidImageError(ValueError):
    """The uploaded bytes are not an acceptable image.

    Attributes:
        code: One of ``empty``, ``too_large``, ``unsupported_type``,
            ``corrupt``, ``too_many_pixels``, ``too_small``.
    """

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def max_image_bytes() -> int:
    """Upload size limit in bytes, from ``OCR_MAX_IMAGE_MB`` (default 5 MB)."""
    raw = os.getenv("OCR_MAX_IMAGE_MB")
    try:
        mb = float(raw) if raw else DEFAULT_MAX_IMAGE_MB
    except ValueError:
        mb = DEFAULT_MAX_IMAGE_MB
    if mb <= 0:
        mb = DEFAULT_MAX_IMAGE_MB
    return int(mb * 1024 * 1024)


def sniff_format(data: bytes) -> str | None:
    """Return ``"PNG"``, ``"JPEG"`` or ``"WEBP"`` from magic bytes, else ``None``."""
    for signature, name in _SIGNATURES:
        if data.startswith(signature):
            return name
    # WebP: "RIFF" <4-byte size> "WEBP"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "WEBP"
    return None


def load_image(image_bytes: bytes, max_bytes: int | None = None) -> np.ndarray:
    """Validate ``image_bytes`` and return an upright RGB ``uint8`` array (H, W, 3).

    Args:
        image_bytes: Raw uploaded file content.
        max_bytes: Size limit override; defaults to :func:`max_image_bytes`.

    Raises:
        InvalidImageError: On any validation failure (see its ``code``).
    """
    if not image_bytes:
        raise InvalidImageError("empty", "The uploaded file is empty.")
    limit = max_bytes if max_bytes is not None else max_image_bytes()
    if len(image_bytes) > limit:
        raise InvalidImageError(
            "too_large", f"Image is {len(image_bytes) / 1_048_576:.1f} MB; the limit is {limit / 1_048_576:.1f} MB."
        )

    fmt = sniff_format(image_bytes)
    if fmt is None:
        raise InvalidImageError("unsupported_type", "Only PNG, JPEG and WebP images are supported.")

    # Header-only open first: dimensions are known before any pixel data is
    # decoded, so a decompression bomb is rejected cheaply.
    try:
        with Image.open(io.BytesIO(image_bytes)) as probe:
            if probe.format != fmt:
                raise InvalidImageError("unsupported_type", "File content does not match a supported image format.")
            width, height = probe.size
    except InvalidImageError:
        raise
    except Exception as exc:  # PIL raises many types for malformed input
        raise InvalidImageError("corrupt", "The image could not be read.") from exc

    if width * height > MAX_PIXELS:
        raise InvalidImageError("too_many_pixels", f"Image is {width}x{height}; the limit is {MAX_PIXELS:,} pixels.")
    if min(width, height) < MIN_SIDE_PX:
        raise InvalidImageError("too_small", f"Image is {width}x{height}; each side must be at least {MIN_SIDE_PX}px.")

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(image_bytes)) as img:
                img.load()  # full decode: truncated/corrupt data fails here
                img = ImageOps.exif_transpose(img)
                img = img.convert("RGB")
    except Exception as exc:
        raise InvalidImageError("corrupt", "The image could not be decoded.") from exc

    longest = max(img.size)
    if longest > MAX_SIDE_PX:
        scale = MAX_SIDE_PX / longest
        img = img.resize((max(1, round(img.width * scale)), max(1, round(img.height * scale))), Image.LANCZOS)
    return np.asarray(img, dtype=np.uint8)
