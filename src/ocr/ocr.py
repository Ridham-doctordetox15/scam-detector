"""Screenshot OCR with EasyOCR (CPU), plus layout grouping and cleaning.

Flow for one image (already validated/decoded by :mod:`src.ocr.validate`):

1. **polarity** - dark-mode screenshots (light text on dark bubbles) are
   inverted to dark-on-light, which EasyOCR reads more reliably.
2. **detect + recognize** - EasyOCR returns word/phrase boxes with
   confidences (hybrid English + script recognition, see :class:`OCREngine`).
3. **group_lines** - boxes are grouped into visual lines (by vertical
   overlap) and lines into paragraphs (by vertical gap), roughly one
   paragraph per message bubble. Pure function, testable without EasyOCR.
4. **clean** - :mod:`src.ocr.clean` drops timestamps/UI chrome and fixes
   line breaks.

Languages come from ``OCR_LANGUAGES`` (comma-separated EasyOCR codes,
default ``en,hi``). EasyOCR restricts combinations: each non-Latin script
model only pairs with English (and same-script languages), e.g. ``hi``
works with ``en``/``mr``/``ne`` but not with ``ta``. An invalid combination
raises :class:`ValueError` when the reader is first loaded.

Models (313 MB for the default en+hi: CRAFT detector 83 MB, Devanagari
recognizer 215 MB, English recognizer 15 MB) are downloaded by EasyOCR to
``~/.EasyOCR/`` on first use; see :func:`download_models`.

OCR text is message content: it is never logged here.
"""
from __future__ import annotations

import os
import re
import statistics
import time
from dataclasses import dataclass, field
from typing import Any, Sequence

import numpy as np

from src.ocr.clean import clean_paragraphs

DEFAULT_LANGUAGES: tuple[str, ...] = ("en", "hi")
DEFAULT_MIN_CONFIDENCE = 0.2
# Mean luminance (0-255) below which an image is treated as dark mode.
DARK_MODE_LUMINANCE = 110.0
_LANG_CODE_RE = re.compile(r"^[a-z]{2,3}(_[a-z]{2,4})?$", re.IGNORECASE)

# (bbox as four (x, y) corners, text, confidence) - EasyOCR's readtext(detail=1) shape.
Detection = tuple[Sequence[Sequence[float]], str, float]


def downloads_enabled() -> bool:
    """Whether EasyOCR may download missing models (``EASYOCR_DOWNLOAD_ENABLED``, default on).

    Deployments set it to ``0`` after pre-fetching models at build time, so a
    missing model fails loudly at startup instead of downloading on a request.
    """
    return os.getenv("EASYOCR_DOWNLOAD_ENABLED", "1").strip().lower() not in {"0", "false", "no", "off"}


class NoTextFoundError(ValueError):
    """OCR found no usable message text in the image."""


@dataclass
class OCRResult:
    """OCR output for one image.

    Attributes:
        text: Cleaned message text (bubbles separated by blank lines) - what
            the pipeline analyzes.
        raw_text: Every kept OCR line before cleaning (for debugging only).
        mean_confidence: Mean EasyOCR confidence of the kept boxes (0-1),
            or 0.0 if none were kept.
        num_boxes: Boxes kept after the confidence filter.
        languages: EasyOCR language codes used.
        inverted: Whether the image was treated as dark mode and inverted.
        seconds: Wall-clock OCR time (readtext + grouping + cleaning).
    """

    text: str
    raw_text: str
    mean_confidence: float
    num_boxes: int
    languages: tuple[str, ...]
    inverted: bool = False
    seconds: float = 0.0
    paragraphs: list[list[list[str]]] = field(default_factory=list, repr=False)


def parse_languages(value: str | Sequence[str] | None = None) -> tuple[str, ...]:
    """Languages from an argument, else ``OCR_LANGUAGES``, else ``en,hi``.

    Raises:
        ValueError: A code is not shaped like an EasyOCR language code.
    """
    if value is None:
        value = os.getenv("OCR_LANGUAGES") or ",".join(DEFAULT_LANGUAGES)
    items = value.split(",") if isinstance(value, str) else list(value)
    langs = tuple(dict.fromkeys(s.strip().lower() for s in items if s and s.strip()))
    if not langs:
        return DEFAULT_LANGUAGES
    bad = [lang for lang in langs if not _LANG_CODE_RE.match(lang)]
    if bad:
        raise ValueError(f"Invalid OCR language code(s): {bad}. Use EasyOCR codes like 'en', 'hi', 'mr'.")
    return langs


# ------------------------------- layout -------------------------------- #
@dataclass
class _Box:
    text: str
    conf: float
    x0: float
    x1: float
    y0: float
    y1: float

    @property
    def yc(self) -> float:
        return (self.y0 + self.y1) / 2

    @property
    def h(self) -> float:
        return max(self.y1 - self.y0, 1.0)


def _to_box(det: Detection) -> _Box:
    pts, text, conf = det
    xs = [float(p[0]) for p in pts]
    ys = [float(p[1]) for p in pts]
    return _Box(str(text), float(conf), min(xs), max(xs), min(ys), max(ys))


def group_lines(detections: Sequence[Detection], paragraph_gap: float = 0.75) -> list[list[list[str]]]:
    """Group OCR boxes into paragraphs -> lines -> segments (left to right).

    A box joins a line when its vertical center falls inside the line's
    vertical extent. A new paragraph starts when the gap between two lines
    exceeds ``paragraph_gap`` times the median line height - chat bubbles
    have more vertical space between them than lines inside a bubble.
    """
    boxes = sorted((_to_box(d) for d in detections if str(d[1]).strip()), key=lambda b: b.yc)
    if not boxes:
        return []

    lines: list[list[_Box]] = []
    for box in boxes:
        if lines:
            cur = lines[-1]
            y0 = min(b.y0 for b in cur)
            y1 = max(b.y1 for b in cur)
            if y0 <= box.yc <= y1:
                cur.append(box)
                continue
        lines.append([box])

    median_h = statistics.median(b.h for b in boxes)
    paragraphs: list[list[list[str]]] = []
    prev_bottom: float | None = None
    for line in lines:
        line.sort(key=lambda b: b.x0)
        top = min(b.y0 for b in line)
        if prev_bottom is None or top - prev_bottom > paragraph_gap * median_h:
            paragraphs.append([])
        paragraphs[-1].append([b.text for b in line])
        prev_bottom = max(b.y1 for b in line)
    return paragraphs


def is_dark_mode(image: np.ndarray, threshold: float = DARK_MODE_LUMINANCE) -> bool:
    """True if the image's mean luminance is below ``threshold`` (RGB uint8 input)."""
    rgb = image[..., :3].astype(np.float32)
    luminance = 0.299 * rgb[..., 0] + 0.587 * rgb[..., 1] + 0.114 * rgb[..., 2]
    return float(luminance.mean()) < threshold


# -------------------------------- engine -------------------------------- #
# Non-Latin-script EasyOCR languages. When one of these is combined with "en",
# the engine runs in hybrid mode (see OCREngine).
_NON_LATIN_LANGS = frozenset({
    "hi", "mr", "ne", "sa", "bh", "mai", "bho", "mah", "new", "gom", "bn", "as", "ta", "te", "kn",
    "ar", "fa", "ur", "ug", "ru", "uk", "be", "bg", "mn", "th", "ch_sim", "ch_tra", "ja", "ko",
})
# A script-model reading is preferred for a box only if it has at least this many
# non-Latin letters (so a Latin box misread with one stray Devanagari glyph isn't chosen).
MIN_SCRIPT_LETTERS = 2
# The (slow, ~5s) script model only re-reads boxes the English model is unsure
# about. Measured on rendered samples: Devanagari boxes got English confidence
# 0.02-0.32, clean Latin boxes mostly 0.55-1.0. A Devanagari box read by the
# English model with confidence >= this would lose its Hindi text - tunable.
SCRIPT_PASS_MAX_LATIN_CONF = 0.5


def script_letter_count(text: str) -> int:
    """Letters outside Latin/Latin-extended (e.g. Devanagari consonants). Digits and marks don't count."""
    return sum(c.isalpha() and ord(c) > 0x024F for c in text)


def _box_key(bbox: Sequence[Sequence[float]]) -> tuple[int, ...]:
    return tuple(int(round(float(v))) for pt in bbox for v in pt)


def _horizontal_key(box: Sequence[float], width: int, height: int) -> tuple[int, ...]:
    """Key of a detected ``[x0, x1, y0, y1]`` box as EasyOCR reports it after recognition
    (four corners, clipped to the image)."""
    x0, x1, y0, y1 = max(0, box[0]), min(box[1], width), max(0, box[2]), min(box[3], height)
    return _box_key([[x0, y0], [x1, y0], [x1, y1], [x0, y1]])


def merge_recognitions(latin: Sequence[Detection], script: Sequence[Detection]) -> list[Detection]:
    """Per box, keep the English model's reading unless the script model read real script letters.

    Both lists come from recognizing the *same* detected boxes, matched by
    box coordinates. Boxes only the Latin pass returned are kept as-is.
    """
    by_box = {_box_key(d[0]): d for d in script}
    merged: list[Detection] = []
    for det in latin:
        alt = by_box.get(_box_key(det[0]))
        merged.append(alt if alt is not None and script_letter_count(str(alt[1])) >= MIN_SCRIPT_LETTERS else det)
    return merged


class OCREngine:
    """Lazy, CPU-only EasyOCR wrapper.

    **Hybrid mode** (default ``en,hi``): EasyOCR's Devanagari recognizer
    misreads Latin text in ways that break this pipeline - digits come out
    as Devanagari digits ("२४ hours"), and hyphens/dots/colons in links are
    dropped ("http://sbi-kyc-verify.tk" -> "httpillsbi kyc verify tk"). So
    when ``en`` is combined with a non-Latin-script language, text boxes are
    detected once and read by the English model; boxes it is unsure about
    (confidence < :data:`SCRIPT_PASS_MAX_LATIN_CONF`) are re-read by the
    script model, whose reading is kept only if it contains real script
    letters (:func:`merge_recognitions`). With only Latin languages a single
    reader is used.

    Args:
        languages: EasyOCR codes; defaults to :func:`parse_languages`.
        reader: The main reader (all ``languages``). Tests inject a fake with
            ``readtext`` (single mode) or ``recognize`` (hybrid mode).
        latin_reader: The English reader used for detection + Latin
            recognition in hybrid mode (tests inject a fake with ``detect``
            and ``recognize``).
        min_confidence: Boxes below this confidence are discarded as noise.
    """

    def __init__(
        self,
        languages: str | Sequence[str] | None = None,
        reader: Any = None,
        latin_reader: Any = None,
        min_confidence: float = DEFAULT_MIN_CONFIDENCE,
    ) -> None:
        self.languages = parse_languages(languages)
        self.min_confidence = min_confidence
        self.hybrid = "en" in self.languages and any(lang in _NON_LATIN_LANGS for lang in self.languages)
        self._reader = reader
        self._latin_reader = latin_reader

    @staticmethod
    def _make_reader(languages: Sequence[str], detector: bool = True) -> Any:
        import easyocr  # heavy import (torch): deferred until OCR is actually used

        try:
            return easyocr.Reader(list(languages), gpu=False, verbose=False, detector=detector,
                                  download_enabled=downloads_enabled())
        except ValueError as exc:
            raise ValueError(
                f"Unsupported OCR language combination {list(languages)}: {exc} "
                "Set OCR_LANGUAGES to a compatible set, e.g. 'en,hi'."
            ) from exc

    @property
    def reader(self) -> Any:
        """The main reader (all languages), created and models downloaded on first access.

        In hybrid mode it is recognition-only (``detector=False``): the
        English reader's detector is shared, so CRAFT is loaded once.
        """
        if self._reader is None:
            self._reader = self._make_reader(self.languages, detector=not self.hybrid)
        return self._reader

    @property
    def latin_reader(self) -> Any:
        """The English reader (detection + Latin recognition); hybrid mode only."""
        if self._latin_reader is None:
            self._latin_reader = self._make_reader(["en"])
        return self._latin_reader

    def load(self) -> None:
        """Load every model this engine needs (downloading if missing)."""
        _ = self.reader
        if self.hybrid:
            _ = self.latin_reader

    def _recognize(self, bgr: np.ndarray) -> list[Detection]:
        if not self.hybrid:
            return self.reader.readtext(bgr, detail=1, paragraph=False)
        import cv2  # installed with easyocr (opencv-python-headless)

        horizontal, free = self.latin_reader.detect(bgr)
        horizontal, free = horizontal[0], free[0]
        if not horizontal and not free:
            return []
        grey = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
        latin = self.latin_reader.recognize(grey, horizontal, free, detail=1, paragraph=False)
        # Script pass only for uncertain boxes (plus any rotated "free" boxes, which are rare).
        uncertain = {_box_key(d[0]) for d in latin if float(d[2]) < SCRIPT_PASS_MAX_LATIN_CONF}
        height, width = grey.shape[:2]
        horizontal_sub = [b for b in horizontal if _horizontal_key(b, width, height) in uncertain]
        if not horizontal_sub and not free:
            return list(latin)
        script = self.reader.recognize(grey, horizontal_sub, free, detail=1, paragraph=False)
        return merge_recognitions(latin, script)

    def read(self, image: np.ndarray) -> OCRResult:
        """Run OCR on an RGB ``uint8`` image and return cleaned text."""
        start = time.perf_counter()
        inverted = is_dark_mode(image)
        work = 255 - image if inverted else image
        # EasyOCR treats 3-channel arrays as BGR (OpenCV convention).
        bgr = np.ascontiguousarray(work[..., ::-1])
        detections = self._recognize(bgr)
        kept = [d for d in detections if float(d[2]) >= self.min_confidence]
        paragraphs = group_lines(kept)
        raw_text = "\n\n".join("\n".join(" ".join(segs) for segs in para) for para in paragraphs)
        return OCRResult(
            text=clean_paragraphs(paragraphs),
            raw_text=raw_text,
            mean_confidence=float(np.mean([float(d[2]) for d in kept])) if kept else 0.0,
            num_boxes=len(kept),
            languages=self.languages,
            inverted=inverted,
            seconds=time.perf_counter() - start,
            paragraphs=paragraphs,
        )


_engine_cache: dict[tuple[str, ...], OCREngine] = {}


def get_default_ocr_engine(languages: str | Sequence[str] | None = None) -> OCREngine:
    """A cached :class:`OCREngine` per language set (the readers load once per process)."""
    langs = parse_languages(languages)
    if langs not in _engine_cache:
        _engine_cache[langs] = OCREngine(langs)
    return _engine_cache[langs]


def download_models(languages: str | Sequence[str] | None = None) -> None:
    """Download and load EasyOCR models now (e.g. at Docker build time) instead of at first request."""
    OCREngine(languages).load()


if __name__ == "__main__":
    download_models()
    print(f"EasyOCR models ready for languages: {list(parse_languages())}")
