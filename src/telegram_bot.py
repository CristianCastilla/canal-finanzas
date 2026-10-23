"""Aprobación de guiones desde Telegram con botones inline.

Se ejecuta desde GitHub Actions cada hora (o a mano). No necesita servidor:
usa getUpdates y guarda el offset en data/telegram_offset.json.
"""
from __future__ import annotations

import json
import logging
import os

import requests

from . import notify, store
from .config import DATA_DIR

log = logging.getLogger(__name__)
OFFSET_FILE = DATA_DIR / "telegram_offset.json"
API = "https://api.telegram.org/bot{token}/{method}"


def _token() -> str:
    return os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()


def _chat() -> str:
    return os.environ.get("TELEGRAM_CHAT_ID", "").strip()


def _api(method: str, **params):
    token = _token()
    if not token:
        raise RuntimeError("Falta TELEGRAM_BOT_TOKEN.")
    response = requests.post(API.format(token=token, method=method), json=params, timeout=30)
    data = response.json()
    if not data.get("ok"):
        raise RuntimeError(f"Telegram {method}: {data}")
    return data.get("result")


def _load_offset() -> int:
    try:
        return int(json.loads(OFFSET_FILE.read_text(encoding="utf-8")).get("offset", 0))
    except (OSError, ValueError, json.JSONDecodeError):
        return 0


def _save_offset(offset: int) -> None:
    OFFSET_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = OFFSET_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps({"offset": offset}, indent=2), encoding="utf-8")
    tmp.replace(OFFSET_FILE)


def send_approval(item: dict) -> bool:
    """Manda el guion con botones. Devuelve False si Telegram no está configurado."""
    if not _token() or not _chat():
        return False
    preview = item["scenes"][0]["text"][:280] if item.get("scenes") else ""
    text = (
        f"<b>Nuevo guion · {notify.esc(item.get('format', ''))}</b>\n"
        f"{notify.esc(item['title'])}\n\n"
        f"{notify.esc(preview)}…\n\n"
        f"<code>{notify.esc(item['id'])}</code>"
    )
    keyboard = {
        "inline_keyboard": [[
            {"text": "Aprobar", "callback_data": f"approve:{item['id']}"},
            {"text": "Rechazar", "callback_data": f"reject:{item['id']}"},
        ]]
    }
    try:
        _api("sendMessage", chat_id=_chat(), text=text, parse_mode="HTML",
             disable_web_page_preview=True, reply_markup=keyboard)
        return True
    except Exception as exc:  # noqa: BLE001
        log.warning("No se pudo enviar la aprobación por Telegram: %s", exc)
        return False


def _authorized(user_id) -> bool:
    return str(user_id) == str(_chat())


def _apply(item_id: str, action: str) -> str:
    item = store.get(item_id)
    if not item:
        return "Ese guion ya no existe."
    if action == "approve":
        store.update(item_id, status="approved")
        return f"Aprobado: {item['title']}"
    store.update(item_id, status="rejected")
    return f"Rechazado: {item['title']}"


def poll() -> int:
    if not _token() or not _chat():
        log.info("Telegram no configurado; nada que hacer.")
        return 0

    offset = _load_offset()
    try:
        updates = _api("getUpdates", offset=offset, timeout=0,
                       allowed_updates=["callback_query", "message"]) or []
    except Exception as exc:  # noqa: BLE001
        log.error("No se pudo consultar Telegram: %s", exc)
        return 0

    handled = 0
    for update in updates:
        offset = max(offset, int(update.get("update_id", 0)) + 1)
        callback = update.get("callback_query")
        message = update.get("message")

        if callback:
            handled += 1
            data = callback.get("data", "")
            user_id = (callback.get("from") or {}).get("id")
            if not _authorized(user_id):
                _api("answerCallbackQuery", callback_query_id=callback["id"],
                     text="No autorizado.")
                continue
            action, _, item_id = data.partition(":")
            result = _apply(item_id, action) if action in ("approve", "reject") else "Acción no válida."
            _api("answerCallbackQuery", callback_query_id=callback["id"], text=result)
            try:
                _api("editMessageReplyMarkup",
                     chat_id=callback["message"]["chat"]["id"],
                     message_id=callback["message"]["message_id"],
                     reply_markup={"inline_keyboard": []})
            except Exception:  # noqa: BLE001
                pass

        elif message:
            text = (message.get("text") or "").strip()
            user_id = (message.get("from") or {}).get("id")
            if not _authorized(user_id):
                continue
            if text in ("/lista", "/list"):
                handled += 1
                items = store.items()[-10:]
                lines = ["<b>Últimos guiones</b>"]
                for item in items:
                    lines.append(f"<code>{notify.esc(item['id'])}</code> · {item.get('status')} · "
                                 f"{notify.esc(item['title'][:50])}")
                _api("sendMessage", chat_id=_chat(), text="\n".join(lines), parse_mode="HTML")
            elif text.startswith(("/aprobar ", "/approve ")):
                handled += 1
                item_id = text.split(maxsplit=1)[1].strip()
                _api("sendMessage", chat_id=_chat(), text=_apply(item_id, "approve"))
            elif text.startswith(("/rechazar ", "/reject ")):
                handled += 1
                item_id = text.split(maxsplit=1)[1].strip()
                _api("sendMessage", chat_id=_chat(), text=_apply(item_id, "reject"))

    _save_offset(offset)
    log.info("Telegram: %s actualizaciones procesadas.", handled)
    return handled
