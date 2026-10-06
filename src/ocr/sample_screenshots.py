"""Programmatically rendered phone screenshots for OCR tests, evaluation and demos.

Each sample imitates an Android SMS or WhatsApp-style chat: a status bar
(time, "VoLTE 4G", battery %), a header with the contact name, a "Today"
date chip, message bubbles with timestamps and read receipts ("Delivered",
tick marks), and an input bar ("Type a message"). The ground-truth message
text is kept alongside, so OCR quality can be measured (character error
rate) and cleaning can be checked (no chrome left in the output).

These are deliberately *easier* than real screenshots: one clean bundled
font, no emoji, no avatars, no compression artefacts. Results on them are an
upper bound - see ``data/real_screenshots/`` for the manual real-image check.

Latin-script samples use Pillow's bundled font, so they render identically
on every OS (CI included). The optional Devanagari sample needs a system
font (e.g. Nirmala UI on Windows) and is ``None`` when none is found.
"""
from __future__ import annotations

import io
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

WIDTH, HEIGHT = 720, 1280
BODY_SIZE, SMALL_SIZE, HEADER_SIZE = 26, 17, 28
PAD = 14
MAX_BUBBLE_W = int(WIDTH * 0.72)

_DEVANAGARI_FONT_CANDIDATES = [
    Path("C:/Windows/Fonts/Nirmala.ttc"),
    Path("C:/Windows/Fonts/Nirmala.ttf"),
    Path("C:/Windows/Fonts/mangal.ttf"),
    Path("/usr/share/fonts/truetype/noto/NotoSansDevanagari-Regular.ttf"),
    Path("/usr/share/fonts/truetype/lohit-devanagari/Lohit-Devanagari.ttf"),
    Path("/System/Library/Fonts/Supplemental/Devanagari Sangam MN.ttc"),
]

RGB = tuple[int, int, int]


@dataclass(frozen=True)
class Theme:
    """Colours for one chat app look."""

    name: str
    bg: RGB
    status_fg: RGB
    header_bg: RGB
    header_fg: RGB
    incoming: RGB
    outgoing: RGB
    text: RGB
    meta: RGB
    chip_bg: RGB
    input_bg: RGB
    input_fg: RGB
    ticks: RGB


SMS_LIGHT = Theme("sms_light", (255, 255, 255), (60, 60, 60), (245, 245, 245), (20, 20, 20), (233, 233, 235),
                  (208, 228, 255), (20, 20, 20), (110, 110, 110), (238, 238, 238), (240, 240, 240), (130, 130, 130),
                  (110, 110, 110))
WHATSAPP_LIGHT = Theme("whatsapp_light", (236, 229, 221), (255, 255, 255), (0, 128, 105), (255, 255, 255),
                       (255, 255, 255), (220, 248, 198), (17, 27, 33), (102, 119, 129), (225, 242, 251),
                       (255, 255, 255), (130, 140, 145), (83, 189, 235))
WHATSAPP_DARK = Theme("whatsapp_dark", (11, 20, 26), (233, 237, 239), (32, 44, 51), (233, 237, 239),
                      (32, 44, 51), (0, 92, 75), (233, 237, 239), (160, 170, 175), (24, 34, 40), (32, 44, 51),
                      (140, 150, 155), (83, 189, 235))


@dataclass(frozen=True)
class Bubble:
    """One chat message. ``receipt`` is ``"ticks"`` (WhatsApp) or a word like ``"Delivered"`` (SMS)."""

    text: str
    outgoing: bool = False
    time: str = "10:42 AM"
    receipt: str | None = None


@dataclass(frozen=True)
class SampleScreenshot:
    """A renderable sample with its ground truth.

    Attributes:
        expected_label: ``"scam"`` or ``"safe"`` - the intended verdict.
        keywords: Words that must survive OCR + cleaning.
        url: The link in the message, if any (must be recovered intact).
        chrome: UI strings drawn on the screen that cleaning must remove.
    """

    name: str
    contact: str
    theme: Theme
    bubbles: tuple[Bubble, ...]
    expected_label: str
    keywords: tuple[str, ...]
    url: str | None = None
    input_hint: str = "Type a message"
    font_path: str | None = None
    chrome: tuple[str, ...] = field(default=("VoLTE", "Delivered", "Type a message", "10:42", "10:45"))

    @property
    def ground_truth(self) -> str:
        """What OCR + cleaning should recover: the contact name, then each bubble's text.

        The contact name is real on-screen content (and a sender ID like
        "VK-BNKALR" is a useful signal), so cleaning keeps it; only chrome
        (status bar, timestamps, receipts, input hint) is removed.
        """
        return "\n\n".join([self.contact, *(b.text for b in self.bubbles)])


def _font(size: int, path: str | None = None) -> ImageFont.FreeTypeFont:
    if path:
        return ImageFont.truetype(path, size)
    return ImageFont.load_default(size=size)


def _wrap(text: str, font: ImageFont.FreeTypeFont, max_w: int) -> list[str]:
    """Greedy word wrap; words wider than a line (long URLs) are hard-broken by character."""
    lines: list[str] = []
    cur = ""
    for word in text.split():
        while font.getlength(word) > max_w:  # hard-break an over-long token
            cut = len(word)
            while cut > 1 and font.getlength(word[:cut]) > max_w:
                cut -= 1
            if cur:
                lines.append(cur)
                cur = ""
            lines.append(word[:cut])
            word = word[cut:]
        candidate = f"{cur} {word}".strip()
        if font.getlength(candidate) <= max_w:
            cur = candidate
        else:
            lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


def _draw_ticks(draw: ImageDraw.ImageDraw, x: float, y: float, color: RGB) -> float:
    """Draw WhatsApp-style double ticks as strokes (no glyph needed). Returns width used."""
    for dx in (0, 7):
        draw.line([(x + dx, y + 7), (x + dx + 4, y + 11), (x + dx + 12, y + 1)], fill=color, width=2)
    return 20


def render(sample: SampleScreenshot) -> Image.Image:
    """Render ``sample`` as a 720x1280 RGB phone screenshot."""
    t = sample.theme
    body = _font(BODY_SIZE, sample.font_path)
    small = _font(SMALL_SIZE)
    header = _font(HEADER_SIZE)
    img = Image.new("RGB", (WIDTH, HEIGHT), t.bg)
    d = ImageDraw.Draw(img)

    # Status bar + header.
    d.rectangle([0, 0, WIDTH, 120], fill=t.header_bg)
    d.text((24, 10), "10:45", font=small, fill=t.status_fg if t.name != "sms_light" else t.status_fg)
    status = "VoLTE 4G 85%"
    d.text((WIDTH - 24 - small.getlength(status), 10), status, font=small, fill=t.status_fg)
    d.ellipse([24, 55, 74, 105], fill=t.meta)
    d.text((92, 64), sample.contact, font=header, fill=t.header_fg)

    # Date chip.
    y = 150
    chip = "Today"
    cw = small.getlength(chip) + 28
    d.rounded_rectangle([(WIDTH - cw) / 2, y, (WIDTH + cw) / 2, y + 32], radius=10, fill=t.chip_bg)
    d.text(((WIDTH - small.getlength(chip)) / 2, y + 6), chip, font=small, fill=t.meta)
    y += 60

    line_h = BODY_SIZE + 10
    for bubble in sample.bubbles:
        lines = _wrap(bubble.text, body, MAX_BUBBLE_W - 2 * PAD)
        meta_w = small.getlength(bubble.time) + (24 if bubble.receipt == "ticks" else 0)
        text_w = max(body.getlength(ln) for ln in lines)
        # The timestamp sits on its own row at the bubble's bottom right (as in SMS apps,
        # and WhatsApp when the last line is long).
        bw = max(text_w, meta_w) + 2 * PAD
        bh = len(lines) * line_h + SMALL_SIZE + 2 * PAD + 4
        x0 = WIDTH - 24 - bw if bubble.outgoing else 24
        d.rounded_rectangle([x0, y, x0 + bw, y + bh], radius=16, fill=t.outgoing if bubble.outgoing else t.incoming)
        for i, ln in enumerate(lines):
            d.text((x0 + PAD, y + PAD + i * line_h), ln, font=body, fill=t.text)
        my = y + bh - PAD - SMALL_SIZE
        mx = x0 + bw - PAD - meta_w
        d.text((mx, my), bubble.time, font=small, fill=t.meta)
        if bubble.receipt == "ticks":
            _draw_ticks(d, mx + small.getlength(bubble.time) + 6, my + 2, t.ticks)
        y += bh + 10
        if bubble.receipt and bubble.receipt != "ticks":
            d.text((x0 + bw - small.getlength(bubble.receipt), y), bubble.receipt, font=small, fill=t.meta)
            y += SMALL_SIZE + 12
        y += 14

    # Input bar.
    d.rounded_rectangle([16, HEIGHT - 90, WIDTH - 100, HEIGHT - 30], radius=30, fill=t.input_bg)
    d.text((44, HEIGHT - 72), sample.input_hint, font=body, fill=t.input_fg)
    d.ellipse([WIDTH - 84, HEIGHT - 90, WIDTH - 24, HEIGHT - 30], fill=t.header_bg)
    return img


def to_png_bytes(img: Image.Image) -> bytes:
    """Encode an image as PNG bytes."""
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


SAMPLES: tuple[SampleScreenshot, ...] = (
    SampleScreenshot(
        name="sms_kyc_scam_en",
        contact="VK-BNKALR",
        theme=SMS_LIGHT,
        bubbles=(
            Bubble("Dear customer, your KYC is not updated. Your account will be BLOCKED within 24 hours. "
                   "Update immediately: http://sbi-kyc-verify.tk/update", time="10:42 AM"),
            Bubble("Who is this?", outgoing=True, time="10:44 AM", receipt="Delivered"),
        ),
        expected_label="scam",
        keywords=("KYC", "BLOCKED", "24 hours", "Update immediately"),
        url="http://sbi-kyc-verify.tk/update",
        input_hint="Text message",
        chrome=("VoLTE", "85%", "Delivered", "Text message", "10:42 AM", "10:44 AM", "10:45", "Today"),
    ),
    SampleScreenshot(
        name="whatsapp_lottery_scam_hinglish",
        contact="+91 98XXX XXX21",
        theme=WHATSAPP_LIGHT,
        bubbles=(
            Bubble("Congratulations! Aapka number lucky draw mein select hua hai. 10 lakh rupaye jeetne ke liye "
                   "turant apna bank account number aur IFSC bhejein.", time="10:40 AM"),
            Bubble("Processing fee sirf Rs 4999 hai, aaj hi pay karein warna prize cancel ho jayega.",
                   time="10:41 AM"),
            Bubble("Aap kaun bol rahe ho?", outgoing=True, time="10:43 AM", receipt="ticks"),
        ),
        expected_label="scam",
        keywords=("lucky draw", "10 lakh", "bank account", "Processing fee", "prize"),
        chrome=("VoLTE", "85%", "Type a message", "10:40 AM", "10:41 AM", "10:43 AM", "10:45", "Today"),
    ),
    SampleScreenshot(
        name="sms_lunch_safe_en",
        contact="Rahul",
        theme=SMS_LIGHT,
        bubbles=(
            Bubble("Hi, are we still on for lunch tomorrow at 1pm?", time="9:15 AM"),
            Bubble("Yes! See you at the cafe near the office.", outgoing=True, time="9:20 AM", receipt="Delivered"),
            Bubble("Great, I will book a table for four.", time="9:21 AM"),
        ),
        expected_label="safe",
        keywords=("lunch tomorrow", "1pm", "cafe", "book a table"),
        input_hint="Text message",
        chrome=("VoLTE", "85%", "Delivered", "Text message", "9:15 AM", "9:20 AM", "9:21 AM", "10:45", "Today"),
    ),
    SampleScreenshot(
        name="whatsapp_dark_parcel_scam_en",
        contact="India Post Help",
        theme=WHATSAPP_DARK,
        bubbles=(
            Bubble("Your parcel is on hold at our warehouse due to an incomplete address. Pay the redelivery "
                   "fee of Rs 25 within 12 hours or it will be returned: http://indiapost-redeliver.top/pay",
                   time="10:38 AM"),
            Bubble("Is this real?", outgoing=True, time="10:39 AM", receipt="ticks"),
        ),
        expected_label="scam",
        keywords=("parcel", "on hold", "redelivery", "12 hours", "returned"),
        url="http://indiapost-redeliver.top/pay",
        chrome=("VoLTE", "85%", "Type a message", "10:38 AM", "10:39 AM", "10:45", "Today"),
    ),
)


def find_devanagari_font() -> str | None:
    """Path to an installed Devanagari-capable font, or ``None``."""
    for path in _DEVANAGARI_FONT_CANDIDATES:
        if path.exists():
            return str(path)
    return None


def devanagari_sample() -> SampleScreenshot | None:
    """An optional Hindi (Devanagari) SMS sample, or ``None`` without a suitable font.

    Words were chosen to avoid the pre-base ``ि`` matra and conjuncts, which
    Pillow renders out of order without the optional raqm shaping library.
    """
    font = find_devanagari_font()
    if font is None:
        return None
    return SampleScreenshot(
        name="sms_kyc_scam_hi",
        contact="VK-BNKALR",
        theme=SMS_LIGHT,
        bubbles=(Bubble("आपका बैंक खाता बंद हो जाएगा। तुरंत KYC अपडेट करें।", time="10:42 AM"),),
        expected_label="scam",
        keywords=("KYC",),
        input_hint="Text message",
        font_path=font,
        chrome=("VoLTE", "85%", "Text message", "10:42 AM", "10:45", "Today"),
    )


def write_samples(out_dir: Path | str) -> list[Path]:
    """Render every available sample to ``out_dir/<name>.png``; returns the paths."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    samples = list(SAMPLES)
    if (hi := devanagari_sample()) is not None:
        samples.append(hi)
    paths = []
    for sample in samples:
        path = out / f"{sample.name}.png"
        render(sample).save(path)
        paths.append(path)
    return paths


if __name__ == "__main__":
    import sys

    target = sys.argv[1] if len(sys.argv) > 1 else "data/samples/screenshots"
    for p in write_samples(target):
        print(p)
