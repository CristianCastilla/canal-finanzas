"""Cola de trabajo persistida en data/queue.json."""
from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import QUEUE_FILE, SAMPLES_DIR

STATUSES = ("draft", "approved", "rejected", "scheduled", "published", "error")


def _empty() -> dict:
    return {"items": []}


def load_queue() -> dict:
    if not QUEUE_FILE.exists():
        _seed_from_samples()
    if not QUEUE_FILE.exists():
        return _empty()
    try:
        data = json.loads(QUEUE_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return _empty()
    if not isinstance(data, dict):
        return _empty()
    data.setdefault("items", [])
    return data


def save_queue(data: dict) -> None:
    QUEUE_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = QUEUE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(QUEUE_FILE)


def _seed_from_samples() -> None:
    if not SAMPLES_DIR.exists():
        return
    items = []
    for path in sorted(SAMPLES_DIR.glob("*.json")):
        try:
            item = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if isinstance(item, dict) and item.get("id"):
            items.append(item)
    if items:
        save_queue({"items": items})


def items() -> list[dict]:
    return load_queue()["items"]


def get(item_id: str) -> dict | None:
    for item in items():
        if item.get("id") == item_id:
            return item
    return None


def add(item: dict) -> dict:
    data = load_queue()
    data["items"] = [i for i in data["items"] if i.get("id") != item["id"]]
    data["items"].append(item)
    save_queue(data)
    return item


def update(item_id: str, **changes: Any) -> dict | None:
    data = load_queue()
    for item in data["items"]:
        if item.get("id") == item_id:
            item.update(changes)
            item["updated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
            save_queue(data)
            return item
    return None


def next_approved() -> dict | None:
    approved = [i for i in items() if i.get("status") == "approved"]
    approved.sort(key=lambda i: i.get("created_at", ""))
    return approved[0] if approved else None


def counts() -> dict[str, int]:
    result: dict[str, int] = {}
    for item in items():
        status = item.get("status", "draft")
        result[status] = result.get(status, 0) + 1
    return result


def reset_from_samples(force: bool = False) -> int:
    """Vuelve a copiar los guiones de ejemplo que falten en la cola."""
    data = load_queue()
    existing = {i.get("id") for i in data["items"]}
    added = 0
    for path in sorted(SAMPLES_DIR.glob("*.json")):
        try:
            item = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if item.get("id") in existing and not force:
            continue
        data["items"] = [i for i in data["items"] if i.get("id") != item.get("id")]
        data["items"].append(item)
        added += 1
    save_queue(data)
    return added


def backup_queue(dest: Path) -> None:
    if QUEUE_FILE.exists():
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(QUEUE_FILE, dest)
