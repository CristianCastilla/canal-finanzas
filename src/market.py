"""Datos de mercado gratuitos vía la API pública de gráficos de Yahoo Finance."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import requests

log = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"
    )
}
URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"

# Ticker interno -> símbolo de Yahoo Finance
SYMBOLS = {
    "^spx": "^GSPC",
    "^ndq": "^IXIC",
    "^dji": "^DJI",
    "^ibex": "^IBEX",
    "^dax": "^GDAXI",
    "^ftm": "^FTSE",
    "eurusd": "EURUSD=X",
    "btcusd": "BTC-USD",
    "ethusd": "ETH-USD",
    "oro": "GC=F",
}

NAMES = {
    "^spx": "S&P 500",
    "^ndq": "Nasdaq Composite",
    "^dji": "Dow Jones",
    "^ibex": "IBEX 35",
    "^dax": "DAX",
    "^ftm": "FTSE 100",
    "eurusd": "EUR/USD",
    "btcusd": "Bitcoin",
    "ethusd": "Ethereum",
    "oro": "Oro",
}


def _range_for(days: int) -> str:
    if days <= 90:
        return "3mo"
    if days <= 365:
        return "1y"
    if days <= 730:
        return "2y"
    if days <= 1825:
        return "5y"
    if days <= 3650:
        return "10y"
    return "max"


def series(ticker: str, days: int = 365) -> list[tuple[datetime, float]]:
    symbol = SYMBOLS.get(ticker.lower(), ticker)
    try:
        response = requests.get(
            URL.format(symbol=requests.utils.quote(symbol)),
            params={"range": _range_for(days), "interval": "1d"},
            headers=HEADERS,
            timeout=30,
        )
        response.raise_for_status()
        payload = response.json()
        result = (payload.get("chart") or {}).get("result") or []
        if not result:
            return []
        timestamps = result[0].get("timestamp") or []
        closes = ((result[0].get("indicators") or {}).get("quote") or [{}])[0].get("close") or []
    except Exception as exc:  # noqa: BLE001
        log.warning("Yahoo Finance falló (%s): %s", ticker, exc)
        return []

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    points: list[tuple[datetime, float]] = []
    for stamp, close in zip(timestamps, closes):
        if close is None:
            continue
        moment = datetime.fromtimestamp(stamp, tz=timezone.utc).replace(tzinfo=None)
        if moment >= cutoff.replace(tzinfo=None):
            points.append((moment, float(close)))
    return points


def last_quotes(tickers: list[str]) -> list[dict[str, str]]:
    quotes = []
    for ticker in tickers:
        points = series(ticker, 7)
        if not points:
            continue
        moment, close = points[-1]
        quotes.append({
            "symbol": NAMES.get(ticker.lower(), ticker),
            "close": f"{close:,.2f}",
            "date": moment.strftime("%Y-%m-%d"),
        })
    return quotes
