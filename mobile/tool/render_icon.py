"""Render the legacy launcher PNGs (Android 7.x) and a mask preview from the icon geometry.

The adaptive icon itself is vector XML (android/app/src/main/res/drawable/ic_launcher_*.xml);
this script draws the same shapes with Pillow so older launchers get a matching bitmap.
Run from mobile/:  ..\\.venv\\Scripts\\python tool\\render_icon.py [preview.png]
"""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw

INDIGO = (0x3B, 0x54, 0xD6, 255)
WHITE = (255, 255, 255, 255)
SIZES = {"mdpi": 48, "hdpi": 72, "xhdpi": 96, "xxhdpi": 144, "xxxhdpi": 192}
RES = Path("android/app/src/main/res")
ART_SCALE = 1.12


def _cubic(p0, p1, p2, p3, n=24):
    """Points along a cubic Bezier curve (without the start point)."""
    pts = []
    for i in range(1, n + 1):
        t = i / n
        mt = 1 - t
        pts.append(tuple(mt**3 * a + 3 * mt * mt * t * b + 3 * mt * t * t * c + t**3 * d
                         for a, b, c, d in zip(p0, p1, p2, p3)))
    return pts


def shield():
    """The shield window, same path as the vector (108-unit canvas)."""
    pts = [(54, 38.5), (64.5, 42.5), (64.5, 50.5)]
    pts += _cubic((64.5, 50.5), (64.5, 57), (60, 61.6), (54, 63.5))
    pts += _cubic((54, 63.5), (48, 61.6), (43.5, 57), (43.5, 50.5))
    pts += [(43.5, 42.5)]
    return pts


def draw_artwork(size: int, *, background: str) -> Image.Image:
    """The icon at ``size`` px. background: "square" (legacy), "full" (adaptive canvas) or "none"."""
    scale = 8  # supersample, then downscale for smooth edges
    big = size * scale
    # Legacy icons show the middle 76 units of the 108-unit adaptive canvas.
    crop = 76 if background == "square" else 108
    off = (108 - crop) / 2
    k = big / crop

    def tr(p):
        # The artwork is scaled 1.12x about the centre, like the vector's <group>.
        x, y = 54 + (p[0] - 54) * ART_SCALE, 54 + (p[1] - 54) * ART_SCALE
        return ((x - off) * k, (y - off) * k)

    img = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    if background == "square":
        d.rounded_rectangle([0, 0, big - 1, big - 1], radius=big * 0.18, fill=INDIGO)
    elif background == "full":
        d.rectangle([0, 0, big, big], fill=INDIGO)

    # Bubble: rounded rectangle 30..78 x 32..70 (radius 10) plus the tail to (39, 79).
    x0, y0 = tr((30, 32))
    x1, y1 = tr((78, 70))
    d.rounded_rectangle([x0, y0, x1, y1], radius=10 * ART_SCALE * k, fill=WHITE)
    d.polygon([tr((39, 66)), tr((52, 70)), tr((39, 79))], fill=WHITE)
    # Shield window: the background colour shows through.
    d.polygon([tr(p) for p in shield()], fill=INDIGO if background != "none" else (0, 0, 0, 0))
    # Tick.
    w = 3 * ART_SCALE * k
    pts = [tr((49, 50.8)), tr((52.6, 54.4)), tr((59.2, 47.6))]
    d.line(pts, fill=WHITE, width=round(w), joint="curve")
    for p in (pts[0], pts[-1]):
        d.ellipse([p[0] - w / 2, p[1] - w / 2, p[0] + w / 2, p[1] + w / 2], fill=WHITE)
    return img.resize((size, size), Image.LANCZOS)


def mask_preview(path: Path) -> None:
    """The adaptive icon under four launcher masks, for the report."""
    size, gap = 192, 32
    art = draw_artwork(size, background="full")
    masks = []
    for kind in ("circle", "squircle", "rounded", "teardrop"):
        m = Image.new("L", (size * 4, size * 4), 0)
        d = ImageDraw.Draw(m)
        s = size * 4
        if kind == "circle":
            d.ellipse([0, 0, s - 1, s - 1], fill=255)
        elif kind == "squircle":
            d.rounded_rectangle([0, 0, s - 1, s - 1], radius=s * 0.38, fill=255)
        elif kind == "rounded":
            d.rounded_rectangle([0, 0, s - 1, s - 1], radius=s * 0.16, fill=255)
        else:
            d.rounded_rectangle([0, 0, s - 1, s - 1], radius=s * 0.5, fill=255)
            d.rectangle([s // 2, s // 2, s - 1, s - 1], fill=255)
        masks.append(m.resize((size, size), Image.LANCZOS))
    sheet = Image.new("RGBA", (gap + 4 * (size + gap), size + 2 * gap), (246, 247, 249, 255))
    for i, m in enumerate(masks):
        sheet.paste(art, (gap + i * (size + gap), gap), m)
    sheet.save(path)


def main() -> None:
    for density, px in SIZES.items():
        draw_artwork(px, background="square").save(RES / f"mipmap-{density}" / "ic_launcher.png", optimize=True)
    if len(sys.argv) > 1:
        mask_preview(Path(sys.argv[1]))
    print("legacy icons written for", ", ".join(SIZES))


if __name__ == "__main__":
    main()
