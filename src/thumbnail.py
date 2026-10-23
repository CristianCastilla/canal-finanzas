"""Miniaturas 1280x720 generadas con Pillow y una plantilla fija."""
from __future__ import annotations

import logging
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

from .config import ASSETS_DIR

log = logging.getLogger(__name__)

W, H = 1280, 720
CORAL = (228, 87, 61)
CREAM = (245, 239, 226)


def _font(size: int) -> ImageFont.FreeTypeFont:
    candidates = [
        ASSETS_DIR / "fonts" / "Inter-Bold.ttf",
        ASSETS_DIR / "fonts" / "Montserrat-Bold.ttf",
        Path("C:/Windows/Fonts/ariblk.ttf"),
        Path("C:/Windows/Fonts/arialbd.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
        Path("/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"),
    ]
    for path in candidates:
        try:
            if path.exists():
                return ImageFont.truetype(str(path), size=size)
        except OSError:
            continue
    try:
        return ImageFont.load_default(size=size)  # Pillow >= 10.1
    except TypeError:
        return ImageFont.load_default()


def _wrap(draw: ImageDraw.ImageDraw, text: str, font, max_width: int) -> list[str]:
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        width = draw.textbbox((0, 0), candidate, font=font)[2]
        if width <= max_width or not current:
            current = candidate
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def make_thumbnail(image_path: Path, text: str, out: Path, channel: str = "") -> Path:
    out.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(image_path) as source:
        image = source.convert("RGB")
    # Recorta la franja inferior (marca de agua / etiqueta) y ajusta a 16:9.
    width, height = image.size
    image = image.crop((0, 0, width, max(1, height - max(30, height // 12))))
    image = ImageOps.fit(image, (W, H), method=Image.LANCZOS)

    # Oscurecer la parte inferior para que el texto se lea siempre.
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    pixels = overlay.load()
    for y in range(H):
        ratio = max(0.0, (y - H * 0.28) / (H * 0.72))
        pixels_row = int(235 * min(ratio, 1.0) ** 1.2)
        for x in range(W):
            pixels[x, y] = (6, 14, 24, pixels_row)
    image = Image.alpha_composite(image.convert("RGBA"), overlay).convert("RGB")

    draw = ImageDraw.Draw(image)
    draw.rectangle([0, 0, 16, H], fill=CORAL)

    clean = " ".join((text or "").split()).upper()
    font = _font(96)
    lines: list[str] = []
    for size in range(96, 54, -4):
        font = _font(size)
        lines = _wrap(draw, clean, font, W - 150)
        if len(lines) <= 3:
            break
    if len(lines) > 3:
        lines = lines[:3]
        lines[-1] = lines[-1][:34] + "..."

    line_height = int(font.size * 1.08)
    block_height = line_height * len(lines)
    y = H - 58 - block_height
    for line in lines:
        draw.text((64, y), line, font=font, fill=CREAM, stroke_width=2, stroke_fill=(0, 0, 0))
        y += line_height

    if channel:
        small = _font(30)
        draw.rectangle([54, 42, 54 + draw.textbbox((0, 0), channel, font=small)[2] + 36, 100], fill=CORAL)
        draw.text((72, 54), channel, font=small, fill=(255, 255, 255))

    image.save(out, "JPEG", quality=91, optimize=True)
    log.info("Miniatura lista: %s", out.name)
    return out
