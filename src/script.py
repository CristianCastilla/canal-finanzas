"""Genera guiones estructurados a partir de titulares y datos."""
from __future__ import annotations

import logging
import re
import secrets
from datetime import datetime, timezone
from string import Template

from . import ideas
from .config import ROOT
from .llm import complete_json

log = logging.getLogger(__name__)

LONG_RULES = """- Formato largo (6-8 minutos): 9-12 escenas.
- Cada escena: 70-110 palabras de narración (unas 35-55 s con la voz).
- Estructura: gancho (0:00-0:30) -> problema -> explicación -> ejemplo con números ->
  gráfico (1 escena) -> riesgos/matices -> conclusión con opinión -> pregunta final.
- La primera frase debe funcionar sola como gancho; nada de "hoy vamos a hablar de".
- Incluye una escena con "chart" (máximo 1) que aporte datos reales.
- La descripción incluye un resumen de 2 párrafos y las fuentes."""

SHORT_RULES = """- Short vertical (45-60 segundos): 4-6 escenas.
- Cada escena: 20-35 palabras (unas 8-13 s).
- UNA sola idea. Gancho en los primeros 3 segundos, desarrollo, giro y cierre.
- Sin gráficos ("chart": null en todas).
- La descripción es breve: 1 párrafo + fuentes."""

TICKERS = {"^spx", "^ndq", "^dji", "^ibex", "^dax", "^ftm", "eurusd", "btcusd", "ethusd", "oro"}


def _clean(value, limit: int = 2000) -> str:
    return " ".join(str(value or "").split())[:limit].strip()


def _load_prompts() -> tuple[str, str]:
    folder = ROOT / "prompts"
    system = (folder / "system_es.md").read_text(encoding="utf-8")
    user = (folder / "user_es.md").read_text(encoding="utf-8")
    return system, user


def _normalize_chart(chart) -> dict | None:
    if not isinstance(chart, dict):
        return None
    ticker = _clean(chart.get("ticker"), 12).lower()
    if ticker not in TICKERS:
        return None
    try:
        days = int(chart.get("days") or 365)
    except (TypeError, ValueError):
        days = 365
    days = max(30, min(days, 3650))
    label = _clean(chart.get("label"), 60) or ticker.upper()
    caption = _clean(chart.get("caption"), 120)
    return {"ticker": ticker, "label": label, "caption": caption, "days": days}


def _sentence_case(text: str) -> str:
    """Pone en mayúscula la primera letra (y la que sigue a ¿ o ¡)."""
    out = list(text)
    start = True
    for i, ch in enumerate(out):
        if ch in "¿¡":
            start = True
            continue
        if ch.isalpha():
            if start:
                out[i] = ch.upper()
                start = False
        elif ch not in " \t":
            start = False
    return "".join(out)


def _clean_description(text: str) -> str:
    """Quita listas de fuentes y enlaces que el modelo meta por su cuenta."""
    lines = []
    for line in text.splitlines():
        if re.match(r"^\s*(fuentes|sources|referencias)\s*:?\s*$", line, re.I):
            break
        if "http://" in line or "https://" in line:
            continue
        lines.append(line)
    cleaned = "\n".join(lines)
    cleaned = re.sub(r"\(?\bhttps?://\S+\)?", "", cleaned)
    cleaned = re.sub(r"[ \t]+\n", "\n", cleaned)
    return re.sub(r"\n{3,}", "\n\n", cleaned).strip()


def _strip_disclaimer(text: str) -> str:
    """Elimina avisos legales sueltos para dejar solo el oficial."""
    pattern = (
        r"(?is)\n*\s*(?:esto es contenido educativo[^\n]*"
        r"|no es asesoramiento financiero[^\n]*"
        r"|no constituye asesoramiento[^\n]*)\s*$"
    )
    previous = None
    while previous != text:
        previous = text
        text = re.sub(pattern, "", text).strip()
    return text


def _normalize(raw: dict, fmt: str, cfg: dict, brief: dict) -> dict:
    if not isinstance(raw, dict):
        raise ValueError("El guion no es un objeto JSON.")

    fmt_cfg = cfg["formats"][fmt]
    scenes_raw = raw.get("scenes") or []
    if not isinstance(scenes_raw, list):
        raise ValueError("'scenes' no es una lista.")

    scenes = []
    for entry in scenes_raw[: int(fmt_cfg["scenes_max"]) + 2]:
        if not isinstance(entry, dict):
            continue
        text = _clean(entry.get("text"), 1500)
        if len(text) < 15:
            continue
        prompt = _clean(entry.get("image_prompt"), 600)
        if not prompt:
            prompt = "symbolic editorial illustration about money and everyday life"
        chart = _normalize_chart(entry.get("chart")) if fmt == "long" else None
        scenes.append({"text": text, "image_prompt": prompt, "chart": chart})

    if len(scenes) < 3:
        raise ValueError(f"El guion solo trae {len(scenes)} escenas válidas.")
    if len(scenes) > int(fmt_cfg["scenes_max"]):
        scenes = scenes[: int(fmt_cfg["scenes_max"])]

    title = _clean(raw.get("title"), 95)
    title = _sentence_case(title)
    if len(title) < 20 or len(title.split()) < 4:
        # Título demasiado corto o vago: nos quedamos con el gancho de la primera escena.
        fallback = " ".join(scenes[0]["text"].split()[:14]).rstrip(".,;:¿?¡!")
        title = _sentence_case(fallback or title or "Finanzas explicadas")[:95]

    thumb = _clean(raw.get("thumbnail_text"), 48) or title[:42]

    allowed = ideas.allowed_urls(brief)
    headline_list = brief.get("headlines") or []
    sources = []
    seen_urls = set()
    for entry in raw.get("sources") or []:
        # El modelo devuelve números de titular; también aceptamos dicts por si acaso.
        if isinstance(entry, (int, str)) and str(entry).strip().isdigit():
            index = int(str(entry).strip()) - 1
            if not 0 <= index < len(headline_list):
                continue
            headline = headline_list[index]
            url = _clean(headline.get("link"), 500)
            source_title = _clean(headline.get("source"), 60) or "Fuente"
        elif isinstance(entry, dict):
            url = _clean(entry.get("url"), 500)
            source_title = _clean(entry.get("title"), 80) or "Fuente"
        else:
            continue
        if not url.startswith("http") or url in seen_urls:
            continue
        if allowed and url not in allowed:
            continue  # evita URLs inventadas
        seen_urls.add(url)
        sources.append({"title": source_title, "url": url})
    sources = sources[:5]

    description = str(raw.get("description") or "").strip()
    description = _clean_description(description)
    description = _strip_disclaimer(description)[:3800]
    if sources:
        description += "\n\nFuentes:\n" + "\n".join(f"- {s['title']}: {s['url']}" for s in sources)
    disclaimer = cfg["channel"]["disclaimer"]
    if disclaimer not in description:
        description = (description + "\n\n" + disclaimer).strip()

    tags = []
    for tag in list(raw.get("tags") or []) + list(cfg["youtube"].get("tags") or []):
        tag = _clean(tag, 30)
        if tag and tag not in tags:
            tags.append(tag)
    tags = tags[:15]

    now = datetime.now(timezone.utc)
    item = {
        "id": f"{now:%Y%m%d-%H%M%S}-{fmt}-{secrets.token_hex(2)}",
        "status": "draft",
        "format": fmt,
        "title": title,
        "thumbnail_text": thumb.upper(),
        "description": description,
        "tags": tags,
        "sources": sources,
        "scenes": scenes,
        "created_at": now.isoformat(timespec="seconds"),
        "source": "ai",
        "video_path": None,
        "thumb_path": None,
        "youtube_id": None,
        "publish_at": None,
    }
    return item


def _max_tokens(fmt: str, cfg: dict) -> int:
    if fmt == "short":
        return int(cfg["llm"].get("max_output_tokens_short") or 2048)
    return int(cfg["llm"]["max_output_tokens"])


def generate(fmt: str, cfg: dict, brief: dict | None = None) -> dict:
    brief = brief or ideas.build_brief()
    system, user_tpl = _load_prompts()
    format_name = "vídeo largo horizontal" if fmt == "long" else "short vertical"
    rules = LONG_RULES if fmt == "long" else SHORT_RULES
    user = Template(user_tpl).safe_substitute(
        channel=cfg["channel"]["name"],
        date=brief["date"],
        format_name=format_name,
        format_rules=rules,
        brief=ideas.brief_as_text(brief),
    )
    system = system.replace("{channel}", cfg["channel"]["name"])

    raw = complete_json(system, user, cfg, max_tokens=_max_tokens(fmt, cfg))
    item = _normalize(raw, fmt, cfg, brief)
    log.info("Guion listo: %s (%s escenas)", item["title"], len(item["scenes"]))
    return item
