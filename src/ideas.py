"""Recopila titulares y datos de mercado para alimentar al guionista."""
from __future__ import annotations

import logging
import random
from datetime import date
from typing import Any

import feedparser
import requests

from . import market

log = logging.getLogger(__name__)

GOOGLE_NEWS = "https://news.google.com/rss/search?q={query}&hl=es&gl=ES&ceid=ES:es"
QUERIES = [
    "bolsa OR ibex 35",
    "inflación OR tipos de interés",
    "ahorro OR inversión",
    "vivienda OR hipotecas",
]
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; EconomiaIlustrada/1.0)"}

EVERGREEN = [
    "Qué es el interés compuesto y por qué empieza a notarse a los 10 años",
    "Fondo indexado vs. fondo de gestión activa: la diferencia que casi nadie mira",
    "Por qué tener 3 meses de gastos en efectivo cambia tus decisiones",
    "El error de medir la rentabilidad sin restar comisiones e impuestos",
    "Diversificar no es tener 20 fondos: es no depender de un solo país o sector",
    "Cuánto pierdes por dejar el dinero parado en la cuenta corriente",
    "La diferencia entre ahorrar e invertir (y cuándo toca cada cosa)",
    "Qué mirar antes de comprar un ETF: TER, réplica y tamaño",
    "Cómo afecta la inflación a tu sueldo real",
    "La trampa de los productos 'sin riesgo' con rentabilidad garantizada",
    "Por qué el mejor momento para invertir no existe",
    "Deudas: cuál pagar primero y cuál nunca deberías tener",
]


def headlines(limit: int = 14) -> list[dict[str, str]]:
    """Titulares recientes de Google News. Si falla, devuelve lista vacía."""
    found: list[dict[str, str]] = []
    seen: set[str] = set()
    for query in QUERIES[:3]:
        url = GOOGLE_NEWS.format(query=requests.utils.quote(query))
        try:
            response = requests.get(url, headers=HEADERS, timeout=20)
            response.raise_for_status()
            feed = feedparser.parse(response.content)
        except Exception as exc:  # noqa: BLE001 - la red nunca debe tumbar el pipeline
            log.warning("No se pudieron leer titulares (%s): %s", query, exc)
            continue
        for entry in feed.entries[:8]:
            title = " ".join(getattr(entry, "title", "").split())
            if not title or title.lower() in seen:
                continue
            seen.add(title.lower())
            source = ""
            if getattr(entry, "source", None):
                source = getattr(entry.source, "title", "") or ""
            found.append(
                {
                    "title": title,
                    "link": getattr(entry, "link", ""),
                    "published": getattr(entry, "published", ""),
                    "source": source,
                }
            )
    return found[:limit]


def market_snapshot() -> list[dict[str, str]]:
    """Cotizaciones recientes vía Yahoo Finance. Devuelve [] si falla."""
    return market.last_quotes(["^spx", "^ibex", "^ndq", "eurusd", "btcusd"])


def build_brief() -> dict[str, Any]:
    """Paquete de contexto que se le pasa al modelo."""
    return {
        "date": date.today().isoformat(),
        "headlines": headlines(),
        "market": market_snapshot(),
        "evergreen": random.choice(EVERGREEN),
    }


def brief_as_text(brief: dict[str, Any]) -> str:
    lines = [f"Fecha: {brief['date']}", "", "Titulares recientes (numerados):"]
    if brief["headlines"]:
        for number, item in enumerate(brief["headlines"], start=1):
            source = f" [{item['source']}]" if item.get("source") else ""
            lines.append(f"{number}. {item['title']}{source}")
    else:
        lines.append("- (sin titulares; usa el tema evergreen)")

    lines += ["", "Datos de mercado (cierre más reciente):"]
    if brief["market"]:
        for item in brief["market"]:
            lines.append(f"- {item['symbol']}: {item['close']} ({item['date']})")
    else:
        lines.append("- (sin datos)")

    lines += ["", f"Tema evergreen sugerido: {brief['evergreen']}"]
    return "\n".join(lines)


def vary_brief(brief: dict[str, Any], index: int, total: int) -> dict[str, Any]:
    """Reparte titulares y temas entre varios guiones para que no salgan clonados."""
    headlines_list = list(brief.get("headlines") or [])
    if total > 1 and len(headlines_list) >= total * 2:
        size = len(headlines_list) // total
        start = (index - 1) * size
        headlines_list = headlines_list[start : start + size + 1]
    try:
        position = EVERGREEN.index(brief["evergreen"]) + index
    except ValueError:
        position = index
    return {
        **brief,
        "headlines": headlines_list,
        "evergreen": EVERGREEN[position % len(EVERGREEN)],
    }


def allowed_urls(brief: dict[str, Any]) -> set[str]:
    return {h.get("link", "") for h in brief.get("headlines", []) if h.get("link")}
