"""Configuración central y rutas del proyecto."""
from __future__ import annotations

import copy
import os
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
OUT_DIR = ROOT / "out"
ASSETS_DIR = ROOT / "assets"
SAMPLES_DIR = DATA_DIR / "samples"
QUEUE_FILE = DATA_DIR / "queue.json"


DEFAULTS: dict[str, Any] = {
    "channel": {
        "name": "Economía Ilustrada",
        "tagline": "Finanzas explicadas con dibujos",
        "language": "es",
        "disclaimer": "Esto es contenido educativo, no asesoramiento financiero.",
    },
    "weekly": {"long": 1, "shorts": 2},
    "formats": {
        "long": {
            "width": 1920,
            "height": 1080,
            "fps": 30,
            "scenes_min": 8,
            "scenes_max": 12,
            "words_per_scene": [70, 110],
            "target_seconds": 480,
        },
        "short": {
            "width": 1080,
            "height": 1920,
            "fps": 30,
            "scenes_min": 4,
            "scenes_max": 6,
            "words_per_scene": [20, 35],
            "target_seconds": 55,
        },
    },
    "llm": {
        "provider": "gemini",
        "model": "gemini-2.5-flash",
        "groq_model": "llama-3.3-70b-versatile",
        "temperature": 0.85,
        "max_output_tokens": 8192,
    },
    "tts": {
        "engine": "edge",
        "voice": "es-ES-AlvaroNeural",
        "rate": "-4%",
        "pitch": "+0Hz",
        "piper_bin": "piper",
        "piper_model": "",
    },
    "images": {
        "provider": "pollinations",
        "model": "flux",
        "width_long": 1280,
        "height_long": 720,
        "width_short": 720,
        "height_short": 1280,
        "style": "editorial illustration in ink and watercolor, no text, no logos",
        "seed": 7,
    },
    "video": {
        "music": "",
        "music_volume": 0.07,
        "subtitle": True,
        "crf": 20,
        "preset": "medium",
    },
    "youtube": {
        "category_id": "27",
        "privacy": "private",
        "publish_hour_utc": 16,
        "tags": ["finanzas personales", "educación financiera"],
    },
}


def _merge(base: dict, extra: dict) -> dict:
    for key, value in extra.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _merge(base[key], value)
        else:
            base[key] = value
    return base


def load_dotenv(path: Path | None = None) -> None:
    """Carga .env si existe, sin sobrescribir variables ya definidas."""
    env_path = path or (ROOT / ".env")
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            os.environ.setdefault(key, value)


def load_config(path: Path | None = None) -> dict:
    cfg = copy.deepcopy(DEFAULTS)
    cfg_path = path or (ROOT / "config.yaml")
    if cfg_path.exists():
        user = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
        if isinstance(user, dict):
            _merge(cfg, user)
    return cfg


def ensure_dirs() -> None:
    for folder in (DATA_DIR, OUT_DIR, ASSETS_DIR, SAMPLES_DIR):
        folder.mkdir(parents=True, exist_ok=True)
