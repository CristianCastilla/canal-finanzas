"""Voz: Edge-TTS (gratis, sin clave) o Piper (local, open source)."""
from __future__ import annotations

import asyncio
import logging
import shutil
import subprocess
import time
from pathlib import Path

from .config import ROOT

log = logging.getLogger(__name__)


def _edge(text: str, out: Path, cfg: dict) -> None:
    import edge_tts

    async def _run() -> None:
        communicate = edge_tts.Communicate(
            text,
            voice=cfg["tts"]["voice"],
            rate=cfg["tts"].get("rate", "+0%"),
            pitch=cfg["tts"].get("pitch", "+0Hz"),
        )
        await communicate.save(str(out))

    last: Exception | None = None
    for attempt in range(3):
        try:
            asyncio.run(_run())
            if out.exists() and out.stat().st_size > 1000:
                return
            raise RuntimeError("archivo de audio vacío")
        except Exception as exc:  # noqa: BLE001
            last = exc
            log.warning("TTS intento %s falló: %s", attempt + 1, exc)
            time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"Edge-TTS no pudo generar el audio: {last}")


def _piper(text: str, out: Path, cfg: dict) -> None:
    model = cfg["tts"].get("piper_model") or ""
    if not model:
        raise RuntimeError("Configura tts.piper_model con la ruta al .onnx de Piper.")
    model_path = Path(model)
    if not model_path.is_absolute():
        model_path = ROOT / model_path
    if not model_path.exists():
        raise RuntimeError(f"No existe el modelo Piper: {model_path}")

    binary = cfg["tts"].get("piper_bin") or "piper"
    if not shutil.which(binary) and not Path(binary).exists():
        raise RuntimeError("No encuentro el ejecutable de Piper. Instala piper-tts.")

    result = subprocess.run(
        [binary, "--model", str(model_path), "--output_file", str(out)],
        input=text.encode("utf-8"),
        capture_output=True,
        timeout=180,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.decode("utf-8", "replace")[-800:])
    if not out.exists() or out.stat().st_size < 1000:
        raise RuntimeError("Piper generó un archivo vacío.")


def synthesize(text: str, out: Path, cfg: dict) -> Path:
    out.parent.mkdir(parents=True, exist_ok=True)
    text = " ".join(text.split())
    if not text:
        raise ValueError("Texto vacío para TTS.")
    engine = (cfg["tts"].get("engine") or "edge").lower()
    if engine == "piper":
        _piper(text, out, cfg)
    else:
        _edge(text, out, cfg)
    log.info("Audio: %s (%.1f KB)", out.name, out.stat().st_size / 1024)
    return out
