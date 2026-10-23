"""Llamadas a modelos gratuitos: Gemini (AI Studio) y Groq."""
from __future__ import annotations

import json
import logging
import os
import re
import time

import requests

log = logging.getLogger(__name__)

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
DEFAULT_GROQ_MODEL = "openai/gpt-oss-120b"


class LLMError(RuntimeError):
    pass


def _clean_json(text: str) -> dict:
    text = (text or "").strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise LLMError("La respuesta no contiene un objeto JSON.")
    try:
        return json.loads(text[start : end + 1])
    except json.JSONDecodeError as exc:
        raise LLMError(f"JSON inválido: {exc}") from exc


def _post(url: str, **kwargs) -> requests.Response:
    last: Exception | None = None
    for attempt in range(3):
        try:
            response = requests.post(url, timeout=180, **kwargs)
        except requests.RequestException as exc:
            last = exc
            wait = 4 * (attempt + 1)
            log.warning("LLM intento %s falló (%s). Reintento en %ss", attempt + 1, exc, wait)
            time.sleep(wait)
            continue

        if response.status_code in (429, 500, 502, 503, 504):
            last = LLMError(f"HTTP {response.status_code}: {response.text[:300]}")
            wait = 4 * (attempt + 1)
            log.warning("LLM intento %s falló (%s). Reintento en %ss", attempt + 1, last, wait)
            time.sleep(wait)
            continue

        if response.status_code >= 400:
            raise LLMError(f"HTTP {response.status_code}: {response.text[:400]}")
        return response

    raise LLMError(f"No se pudo contactar con el modelo: {last}")


def gemini_json(system: str, user: str, cfg: dict) -> dict:
    key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not key:
        raise LLMError("Falta GEMINI_API_KEY.")
    model = cfg["llm"]["model"]
    payload = {
        "systemInstruction": {"parts": [{"text": system}]},
        "contents": [{"role": "user", "parts": [{"text": user}]}],
        "generationConfig": {
            "temperature": float(cfg["llm"]["temperature"]),
            "maxOutputTokens": int(cfg["llm"]["max_output_tokens"]),
            "responseMimeType": "application/json",
        },
    }
    response = _post(
        GEMINI_URL.format(model=model),
        headers={"x-goog-api-key": key, "Content-Type": "application/json"},
        json=payload,
    )
    data = response.json()
    candidates = data.get("candidates") or []
    if not candidates:
        raise LLMError(f"Gemini no devolvió candidatos: {str(data)[:300]}")
    parts = candidates[0].get("content", {}).get("parts") or []
    text = "".join(p.get("text", "") for p in parts)
    if not text.strip():
        reason = candidates[0].get("finishReason", "desconocido")
        raise LLMError(f"Gemini devolvió texto vacío (finishReason={reason}).")
    return _clean_json(text)


def groq_json(system: str, user: str, cfg: dict) -> dict:
    key = os.environ.get("GROQ_API_KEY")
    if not key:
        raise LLMError("Falta GROQ_API_KEY.")
    payload = {
        "model": cfg["llm"].get("groq_model") or DEFAULT_GROQ_MODEL,
        "temperature": float(cfg["llm"]["temperature"]),
        "max_tokens": int(cfg["llm"]["max_output_tokens"]),
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }
    response = _post(
        GROQ_URL,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json=payload,
    )
    data = response.json()
    try:
        text = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError) as exc:
        raise LLMError(f"Respuesta rara de Groq: {str(data)[:300]}") from exc
    return _clean_json(text)


def complete_json(system: str, user: str, cfg: dict) -> dict:
    """Intenta el proveedor configurado y, si falla, el alternativo."""
    provider = (cfg["llm"].get("provider") or "gemini").lower()
    order = ["gemini", "groq"] if provider == "gemini" else ["groq", "gemini"]
    errors = []
    for name in order:
        try:
            log.info("Generando guion con %s...", name)
            return gemini_json(system, user, cfg) if name == "gemini" else groq_json(system, user, cfg)
        except Exception as exc:  # noqa: BLE001
            log.warning("%s falló: %s", name, exc)
            errors.append(f"{name}: {exc}")
    raise LLMError("Ningún proveedor funcionó. " + " | ".join(errors))
