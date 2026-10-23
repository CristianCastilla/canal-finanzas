"""Subida a YouTube con la API oficial (cuota gratuita diaria)."""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

log = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube",
]
API_SERVICE_NAME = "youtube"
API_VERSION = "v3"


class PublishError(RuntimeError):
    pass


def _credentials():
    raw = os.environ.get("YOUTUBE_TOKEN_JSON", "").strip()
    if not raw:
        raise PublishError("Falta el secret YOUTUBE_TOKEN_JSON.")
    try:
        info = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise PublishError("YOUTUBE_TOKEN_JSON no es JSON válido.") from exc
    if not info.get("refresh_token"):
        raise PublishError("YOUTUBE_TOKEN_JSON no contiene refresh_token.")

    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials

    credentials = Credentials(
        token=None,
        refresh_token=info["refresh_token"],
        token_uri=info.get("token_uri", "https://oauth2.googleapis.com/token"),
        client_id=info.get("client_id"),
        client_secret=info.get("client_secret"),
        scopes=info.get("scopes") or SCOPES,
    )
    credentials.refresh(Request())
    return credentials


def _service():
    from googleapiclient.discovery import build

    return build(API_SERVICE_NAME, API_VERSION, credentials=_credentials(),
                 cache_discovery=False)


def next_slot(cfg: dict, when: str | None = None) -> str:
    """Devuelve la fecha de publicación en RFC3339 UTC."""
    if when:
        parsed = datetime.fromisoformat(when.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        if parsed <= datetime.now(timezone.utc) + timedelta(minutes=5):
            raise PublishError("La fecha de publicación debe estar al menos 5 minutos en el futuro.")
        return parsed.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    now = datetime.now(timezone.utc)
    hour = int(cfg["youtube"].get("publish_hour_utc", 16))
    slot = now.replace(hour=hour, minute=0, second=0, microsecond=0)
    if slot <= now + timedelta(minutes=5):
        slot += timedelta(days=1)
    return slot.strftime("%Y-%m-%dT%H:%M:%SZ")


def upload(item: dict, video: Path, thumbnail: Path | None, cfg: dict,
           publish_at: str) -> str:
    from googleapiclient.http import MediaFileUpload

    if not video.exists():
        raise PublishError(f"No existe el vídeo: {video}")
    if video.stat().st_size > 128 * 1024 * 1024:
        log.warning("El vídeo supera 128 MB; la subida puede tardar más.")

    body = {
        "snippet": {
            "title": item["title"][:100],
            "description": item["description"][:5000],
            "tags": item.get("tags", [])[:15],
            "categoryId": str(cfg["youtube"].get("category_id", "27")),
            "defaultLanguage": "es",
            "defaultAudioLanguage": "es",
        },
        "status": {
            "privacyStatus": "private",
            "publishAt": publish_at,
            "selfDeclaredMadeForKids": False,
        },
    }

    youtube = _service()
    media = MediaFileUpload(str(video), mimetype="video/mp4",
                            chunksize=8 * 1024 * 1024, resumable=True)
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)

    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            log.info("Subiendo: %s%%", int(status.progress() * 100))

    video_id = response.get("id")
    if not video_id:
        raise PublishError(f"YouTube no devolvió ID: {str(response)[:300]}")
    log.info("Vídeo subido: https://youtu.be/%s", video_id)

    if thumbnail and thumbnail.exists():
        try:
            youtube.thumbnails().set(
                videoId=video_id, media_body=MediaFileUpload(str(thumbnail), mimetype="image/jpeg")
            ).execute()
            log.info("Miniatura subida.")
        except Exception as exc:  # noqa: BLE001 - la miniatura no debe tumbar la subida
            log.warning("No se pudo subir la miniatura: %s", exc)

    return video_id
