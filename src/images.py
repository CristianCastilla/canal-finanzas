"""Ilustraciones gratuitas con Pollinations (sin clave) y respaldo local."""
from __future__ import annotations

import logging
import os
import random
import time
from pathlib import Path
from urllib.parse import quote

import requests
from PIL import Image, ImageDraw

log = logging.getLogger(__name__)
ENDPOINT = "https://image.pollinations.ai/prompt/"

# Pollinations limita a 1 imagen cada 45 s por IP en su plan gratuito.
_last_call = 0.0


def _throttle(has_token: bool) -> None:
    global _last_call
    interval = 2.0 if has_token else 47.0
    wait = interval - (time.time() - _last_call)
    if wait > 0:
        time.sleep(wait)
    _last_call = time.time()


def _fallback(out: Path, width: int, height: int, seed: int, label: str) -> Path:
    """Ilustración abstracta generada con Pillow si la IA no responde."""
    random.seed(seed)
    image = Image.new("RGB", (width, height), "#0B1B2B")
    draw = ImageDraw.Draw(image)
    for y in range(height):
        ratio = y / max(height - 1, 1)
        color = (
            int(11 + 18 * ratio),
            int(27 + 30 * ratio),
            int(43 + 34 * ratio),
        )
        draw.line([(0, y), (width, y)], fill=color)
    for _ in range(14):
        x = random.randint(-width // 4, width)
        y = random.randint(0, height)
        r = random.randint(width // 18, width // 5)
        draw.ellipse([x, y, x + r, y + r], outline="#E4573D", width=max(2, width // 300))
    draw.line([(0, height * 0.72), (width, height * 0.45)], fill="#4ECDC4", width=max(3, width // 240))
    image.save(out, "JPEG", quality=90)
    return out


def _brand(image_path: Path, cfg: dict) -> None:
    """Tapa la marca de agua del servicio con una etiqueta del canal."""
    try:
        with Image.open(image_path) as source:
            image = source.convert("RGB")
        width, height = image.size
        draw = ImageDraw.Draw(image)
        text = cfg["channel"]["name"]
        size = max(12, width // 44)
        from PIL import ImageFont

        font = None
        for candidate in (
            Path("C:/Windows/Fonts/arialbd.ttf"),
            Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
            Path("/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"),
        ):
            if candidate.exists():
                font = ImageFont.truetype(str(candidate), size)
                break
        if font is None:
            font = ImageFont.load_default(size=size)
        box = draw.textbbox((0, 0), text, font=font)
        text_w, text_h = box[2] - box[0], box[3] - box[1]
        pad = max(4, size // 3)
        x1, y1 = width - pad, height - pad
        draw.rounded_rectangle(
            [x1 - text_w - pad * 2, y1 - text_h - pad * 2, x1, y1],
            radius=pad,
            fill=(11, 27, 43),
        )
        draw.text((x1 - text_w - pad, y1 - text_h - pad), text, font=font, fill=(245, 239, 226))
        image.save(image_path, "JPEG", quality=92)
    except Exception as exc:  # noqa: BLE001 - nunca debe tumbar el render
        log.warning("No se pudo poner la etiqueta del canal: %s", exc)


def fallback(prompt: str, out: Path, width: int, height: int, seed: int, cfg: dict) -> Path:
    """Fondo abstracto de emergencia, sin llamadas a red."""
    out.parent.mkdir(parents=True, exist_ok=True)
    return _fallback(out, width, height, seed, prompt)


def generate(
    prompt: str,
    out: Path,
    width: int,
    height: int,
    seed: int,
    cfg: dict,
    label: str = "",
) -> Path:
    out.parent.mkdir(parents=True, exist_ok=True)
    style = cfg["images"].get("style", "")
    subject = prompt.strip().rstrip(".")
    full_prompt = f"{style}. Subject: {subject}" if style else subject
    url = ENDPOINT + quote(full_prompt, safe="")
    token = os.environ.get("POLLINATIONS_TOKEN", "").strip()
    params = {
        "width": width,
        "height": height,
        "seed": seed,
        "model": cfg["images"].get("model", "flux"),
        "nologo": "true",
        "enhance": "false",
        "negative_prompt": "photo, photorealistic, 3d render, text, letters, numbers, logo, watermark",
    }
    if token:
        params["token"] = token

    started = time.time()
    for attempt in range(3):
        if time.time() - started > 240:
            log.warning("Tiempo máximo por imagen agotado; uso respaldo.")
            break
        _throttle(bool(token))
        try:
            response = requests.get(url, params=params, timeout=(20, 150))
            if response.status_code == 200 and len(response.content) > 8000:
                out.write_bytes(response.content)
                with Image.open(out) as check:
                    check.verify()
                _brand(out, cfg)
                log.info("Imagen %s lista (%.0f KB)", out.name, len(response.content) / 1024)
                return out
            if response.status_code == 402:
                log.warning("Pollinations: límite gratuito. Esperando 50 s...")
                time.sleep(50)
                continue
            log.warning("Pollinations HTTP %s (intento %s)", response.status_code, attempt + 1)
        except Exception as exc:  # noqa: BLE001
            log.warning("Pollinations falló (%s). Intento %s", exc, attempt + 1)
        time.sleep(5 + attempt * 5)

    log.warning("Uso imagen de respaldo para %s", out.name)
    return _fallback(out, width, height, seed, label or "Economía Ilustrada")
