"""Gráficos de mercado con datos gratuitos de Stooq + matplotlib."""
from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from . import market

log = logging.getLogger(__name__)

BG = "#0B1B2B"
PANEL = "#12283D"
CREAM = "#F5EFE2"
MUTED = "#8A9BAE"
CORAL = "#E4573D"
TEAL = "#4ECDC4"


def _history(ticker: str, days: int) -> list[tuple[datetime, float]]:
    return market.series(ticker, days)


def make_chart(spec: dict[str, Any], out: Path) -> Path | None:
    ticker = spec.get("ticker", "^spx")
    series = _history(ticker, int(spec.get("days", 365)))
    if len(series) < 10:
        log.warning("Sin datos suficientes para el gráfico de %s", ticker)
        return None

    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.dates as mdates
    import matplotlib.pyplot as plt

    dates = [point[0] for point in series]
    values = [point[1] for point in series]
    first, last = values[0], values[-1]
    change = (last / first - 1) * 100 if first else 0
    color = TEAL if change >= 0 else CORAL
    label = (spec.get("label") or ticker.upper()).strip()
    caption = (spec.get("caption") or "").strip()

    fig, ax = plt.subplots(figsize=(12.8, 7.2), dpi=150)
    fig.patch.set_facecolor(BG)
    ax.set_facecolor(BG)
    fig.subplots_adjust(left=0.075, right=0.95, top=0.78, bottom=0.16)

    ax.plot(dates, values, color=color, linewidth=3.2, solid_capstyle="round")
    ax.fill_between(dates, values, min(values) * 0.985, color=color, alpha=0.12)
    ax.grid(axis="y", color=PANEL, linewidth=1.1)
    ax.set_axisbelow(True)
    for spine in ("top", "right", "left"):
        ax.spines[spine].set_visible(False)
    ax.spines["bottom"].set_color(PANEL)
    ax.tick_params(colors=MUTED, labelsize=12, length=0)
    ax.yaxis.set_major_formatter(lambda value, _pos: f"{value:,.0f}".replace(",", "."))

    locator = mdates.AutoDateLocator(minticks=4, maxticks=7)
    ax.xaxis.set_major_locator(locator)
    ax.xaxis.set_major_formatter(mdates.ConciseDateFormatter(locator))

    fig.text(0.075, 0.90, label.upper(), color=CREAM, fontsize=27, fontweight="bold")
    fig.text(0.075, 0.855, spec.get("subtitle", "Datos diarios de cierre"), color=MUTED, fontsize=12)

    sign = "+" if change >= 0 else ""
    fig.text(0.95, 0.885, f"{last:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."),
             color=CREAM, fontsize=25, fontweight="bold", ha="right")
    fig.text(0.95, 0.845, f"{sign}{change:.1f}% en el periodo", color=color,
             fontsize=14, fontweight="bold", ha="right")

    if caption:
        fig.text(0.075, 0.812, caption[:110], color=CREAM, fontsize=12)
    fig.text(0.95, 0.812, "Fuente: Yahoo Finance", color=MUTED, fontsize=10, ha="right")

    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, facecolor=BG, bbox_inches=None)
    plt.close(fig)
    log.info("Gráfico listo: %s", out.name)
    return out
