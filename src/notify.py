"""Avisos opcionales por Telegram (gratis)."""
from __future__ import annotations

import html
import logging
import os

import requests

log = logging.getLogger(__name__)


def send(text: str) -> bool:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        return False
    try:
        response = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={
                "chat_id": chat_id,
                "text": text[:4000],
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            },
            timeout=20,
        )
        if response.status_code != 200:
            log.warning("Telegram HTTP %s: %s", response.status_code, response.text[:200])
            return False
        return True
    except Exception as exc:  # noqa: BLE001
        log.warning("No se pudo enviar Telegram: %s", exc)
        return False


def esc(text: str) -> str:
    return html.escape(text or "")
