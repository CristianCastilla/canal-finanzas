"""CLI del canal.

Ejemplos:
    python -m src.main generate --weekly
    python -m src.main list
    python -m src.main show 20261023-120000-long
    python -m src.main approve 20261023-120000-long
    python -m src.main render 20261023-120000-long
    python -m src.main publish 20261023-120000-long
    python -m src.main run
    python -m src.main doctor
"""
from __future__ import annotations

import argparse
import importlib.util
import logging
import shutil
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from . import store, telegram_bot
from .config import OUT_DIR, ROOT, ensure_dirs, load_config, load_dotenv

log = logging.getLogger("canal")


def _setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-7s %(message)s",
        datefmt="%H:%M:%S",
    )
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass


def _generate_one(fmt: str, cfg: dict, brief: dict, index: int, total: int) -> dict | None:
    from . import script

    log.info("=== Guion %s/%s (%s) ===", index, total, fmt)
    try:
        item = script.generate(fmt, cfg, brief)
    except Exception as exc:  # noqa: BLE001
        log.error("No se pudo generar el guion %s: %s", fmt, exc)
        return None
    store.add(item)
    log.info("Guardado como %s: %s", item["id"], item["title"])
    return item


def cmd_generate(args: argparse.Namespace, cfg: dict) -> int:
    from . import ideas, notify, script

    if args.weekly:
        jobs = ["long"] * int(cfg["weekly"].get("long", 1))
        jobs += ["short"] * int(cfg["weekly"].get("shorts", 2))
    else:
        jobs = [args.format] * max(1, args.count)

    brief = ideas.build_brief()
    cooldown = int(cfg["llm"].get("cooldown_seconds", 0) or 0)
    created = []
    for index, fmt in enumerate(jobs, start=1):
        if index > 1 and cooldown > 0:
            log.info("Esperando %ss para no superar el límite de tokens por minuto...", cooldown)
            time.sleep(cooldown)
        item = _generate_one(fmt, cfg, ideas.vary_brief(brief, index, len(jobs)), index, len(jobs))
        if item:
            created.append(item)

    if not created:
        log.error("No se generó ningún guion. Revisa tu clave de API y la conexión.")
        return 1

    lines = ["<b>Guiones listos para revisar</b>"]
    sent = 0
    for item in created:
        if telegram_bot.send_approval(item):
            sent += 1
        lines.append(f"• <code>{notify.esc(item['id'])}</code>\n  {notify.esc(item['title'])}")
    if sent == 0:
        lines.append("\nAprueba con:\n<code>python -m src.main approve ID</code>")
        notify.send("\n".join(lines))
    print("\nGuiones creados:")
    for item in created:
        print(f"  {item['id']}  [{item['format']}]  {item['title']}")
    print("\nSiguiente paso: revisa el guion y apruébalo con `python -m src.main approve <id>`.")
    return 0


def cmd_list(args: argparse.Namespace, cfg: dict) -> int:
    items = store.items()
    if not items:
        print("La cola está vacía. Ejecuta: python -m src.main generate --weekly")
        return 0
    print(f"{'ID':<26} {'ESTADO':<10} {'FORMATO':<7} TÍTULO")
    print("-" * 100)
    for item in sorted(items, key=lambda i: i.get("created_at", ""), reverse=True):
        print(f"{item['id']:<26} {item.get('status','draft'):<10} "
              f"{item.get('format','?'):<7} {item.get('title','')[:58]}")
    counts = store.counts()
    print("\nResumen:", ", ".join(f"{k}={v}" for k, v in sorted(counts.items())))
    return 0


def cmd_show(args: argparse.Namespace, cfg: dict) -> int:
    item = store.get(args.id)
    if not item:
        print(f"No existe el guion {args.id}.")
        return 1
    print(f"ID: {item['id']}\nEstado: {item.get('status')}\nFormato: {item['format']}")
    print(f"\nTÍTULO: {item['title']}\nMINIATURA: {item.get('thumbnail_text','')}")
    print(f"\nDESCRIPCIÓN:\n{item.get('description','')}")
    print(f"\nETIQUETAS: {', '.join(item.get('tags', []))}")
    print("\nESCENAS:")
    for number, scene in enumerate(item["scenes"], start=1):
        print(f"\n[{number}] {scene['text']}")
        if scene.get("chart"):
            print(f"    GRÁFICO: {scene['chart']}")
    return 0


def cmd_approve(args: argparse.Namespace, cfg: dict) -> int:
    item = store.get(args.id)
    if not item:
        print(f"No existe el guion {args.id}.")
        return 1
    store.update(args.id, status="approved")
    print(f"Aprobado: {args.id}")
    print(f"Para renderizar y programar: python -m src.main publish {args.id}")
    return 0


def cmd_reject(args: argparse.Namespace, cfg: dict) -> int:
    if not store.get(args.id):
        print(f"No existe el guion {args.id}.")
        return 1
    store.update(args.id, status="rejected")
    print(f"Rechazado: {args.id}")
    return 0


def cmd_render(args: argparse.Namespace, cfg: dict) -> int:
    from . import render

    item = store.get(args.id)
    if not item:
        print(f"No existe el guion {args.id}.")
        return 1
    result = render.render_item(item, cfg, force=args.force)
    store.update(args.id, **result)
    print(f"Vídeo:   {result['video_path']}")
    print(f"Miniatura: {result.get('thumb_path')}")
    print(f"Duración: {result.get('duration')} s")
    return 0


def _publish_item(
    item: dict, cfg: dict, when: str | None, force: bool, upload: bool = True
) -> int:
    from . import notify, publish, render

    if item.get("status") not in ("approved", "draft") or (
        item.get("status") == "draft" and not force
    ):
        print(f"El guion {item['id']} está en estado '{item.get('status')}'. "
              "Apruébalo antes de publicar.")
        return 1

    video_path = ROOT / item["video_path"] if item.get("video_path") else None
    if not video_path or not video_path.exists():
        log.info("Renderizando antes de publicar...")
        result = render.render_item(item, cfg)
        item = store.update(item["id"], **result) or item

    if not upload:
        video = ROOT / item["video_path"]
        print(f"Vídeo:   {video}")
        print(f"Miniatura: {item.get('thumb_path')}")
        print(f"Duración: {item.get('duration')} s")
        print("Modo sin subida: el vídeo queda en out/ para descargarlo a mano.")
        notify.send(
            f"<b>Vídeo renderizado</b>\n{notify.esc(item['title'])}\n"
            "<code>Subida a YouTube desactivada</code>"
        )
        return 0

    video = ROOT / item["video_path"]
    thumb = ROOT / item["thumb_path"] if item.get("thumb_path") else None
    slot = publish.next_slot(cfg, when)

    log.info("Subiendo a YouTube (privado hasta %s)...", slot)
    video_id = publish.upload(item, video, thumb, cfg, slot)
    store.update(
        item["id"], status="scheduled", youtube_id=video_id,
        publish_at=slot, uploaded_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )
    url = f"https://youtu.be/{video_id}"
    notify.send(
        f"<b>Programado</b>\n{notify.esc(item['title'])}\n"
        f"{url}\nPublicación: <code>{slot}</code>"
    )
    print(f"Programado: {url} para {slot}")
    return 0


def cmd_publish(args: argparse.Namespace, cfg: dict) -> int:
    item = store.get(args.id)
    if not item:
        print(f"No existe el guion {args.id}.")
        return 1
    if item.get("status") in ("scheduled", "published"):
        print(f"Ya está publicado/programado: https://youtu.be/{item.get('youtube_id')}")
        return 0
    return _publish_item(item, cfg, args.at, args.force, upload=not args.no_upload)


def cmd_run(args: argparse.Namespace, cfg: dict) -> int:
    if args.id:
        item = store.get(args.id)
        if not item:
            print(f"No existe el guion {args.id}.")
            return 1
        return _publish_item(item, cfg, None, args.force, upload=not args.no_upload)

    published = 0
    for _ in range(max(1, args.limit)):
        item = store.next_approved()
        if not item:
            break
        code = _publish_item(item, cfg, None, False, upload=not args.no_upload)
        if code != 0:
            return code
        published += 1
    if not published:
        print("No hay guiones aprobados. Nada que publicar.")
    return 0


def cmd_samples(args: argparse.Namespace, cfg: dict) -> int:
    added = store.reset_from_samples(force=args.force)
    print(f"Guiones de ejemplo añadidos: {added}")
    return 0


def cmd_telegram(args: argparse.Namespace, cfg: dict) -> int:
    handled = telegram_bot.poll()
    print(f"Actualizaciones procesadas: {handled}")
    return 0


def cmd_doctor(args: argparse.Namespace, cfg: dict) -> int:
    print(f"Python: {sys.version.split()[0]}")
    print(f"Proyecto: {ROOT}")

    ok = True
    import os

    for binary in ("ffmpeg", "ffprobe"):
        env_key = "FFMPEG_BIN" if binary == "ffmpeg" else "FFPROBE_BIN"
        path = os.environ.get(env_key) or shutil.which(binary)
        print(f"{binary}: {path or 'NO ENCONTRADO'}")
        ok = ok and bool(path)

    for module in ("yaml", "requests", "feedparser", "edge_tts", "PIL", "matplotlib"):
        found = importlib.util.find_spec(module) is not None
        print(f"módulo {module}: {'ok' if found else 'FALTA'}")
        ok = ok and found

    print(f"GEMINI_API_KEY: {'ok' if os.environ.get('GEMINI_API_KEY') else 'falta'}")
    print(f"GROQ_API_KEY: {'ok' if os.environ.get('GROQ_API_KEY') else 'falta'}")
    print(f"YOUTUBE_TOKEN_JSON: {'ok' if os.environ.get('YOUTUBE_TOKEN_JSON') else 'falta'}")
    print(f"TELEGRAM: {'ok' if os.environ.get('TELEGRAM_BOT_TOKEN') else 'opcional, no configurado'}")

    counts = store.counts()
    print("Cola:", ", ".join(f"{k}={v}" for k, v in sorted(counts.items())) or "vacía")
    free = shutil.disk_usage(OUT_DIR if OUT_DIR.exists() else ROOT).free / 1e9
    print(f"Espacio libre: {free:.1f} GB")
    print("\nTODO OK" if ok else "\nFaltan dependencias: revisa el README.")
    return 0 if ok else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="canal", description="Pipeline del canal de finanzas")
    sub = parser.add_subparsers(dest="command", required=True)

    gen = sub.add_parser("generate", help="Genera guiones con IA")
    gen.add_argument("--weekly", action="store_true", help="1 largo + N shorts")
    gen.add_argument("--format", choices=["long", "short"], default="long")
    gen.add_argument("--count", type=int, default=1)
    gen.set_defaults(func=cmd_generate)

    lst = sub.add_parser("list", help="Lista la cola")
    lst.set_defaults(func=cmd_list)

    show = sub.add_parser("show", help="Muestra un guion completo")
    show.add_argument("id")
    show.set_defaults(func=cmd_show)

    approve = sub.add_parser("approve", help="Aprueba un guion")
    approve.add_argument("id")
    approve.set_defaults(func=cmd_approve)

    reject = sub.add_parser("reject", help="Rechaza un guion")
    reject.add_argument("id")
    reject.set_defaults(func=cmd_reject)

    render_cmd = sub.add_parser("render", help="Renderiza un guion aprobado o en borrador")
    render_cmd.add_argument("id")
    render_cmd.add_argument("--force", action="store_true")
    render_cmd.set_defaults(func=cmd_render)

    pub = sub.add_parser("publish", help="Renderiza (si hace falta) y sube a YouTube")
    pub.add_argument("id")
    pub.add_argument("--at", help="Fecha ISO de publicación, p. ej. 2026-10-30T16:00")
    pub.add_argument("--force", action="store_true", help="Permite publicar un borrador")
    pub.add_argument(
        "--no-upload", action="store_true",
        help="Solo renderiza el vídeo en out/, sin subirlo a YouTube",
    )
    pub.set_defaults(func=cmd_publish)

    run = sub.add_parser("run", help="Publica el siguiente guion aprobado")
    run.add_argument("--id")
    run.add_argument("--limit", type=int, default=1)
    run.add_argument("--force", action="store_true")
    run.add_argument(
        "--no-upload", action="store_true",
        help="Solo renderiza el vídeo en out/, sin subirlo a YouTube",
    )
    run.set_defaults(func=cmd_run)

    samples = sub.add_parser("samples", help="Recarga los guiones de ejemplo")
    samples.add_argument("--force", action="store_true")
    samples.set_defaults(func=cmd_samples)

    telegram = sub.add_parser("telegram", help="Procesa los botones de aprobación de Telegram")
    telegram.set_defaults(func=cmd_telegram)

    doctor = sub.add_parser("doctor", help="Comprueba dependencias y secretos")
    doctor.set_defaults(func=cmd_doctor)
    return parser


def main(argv: list[str] | None = None) -> int:
    _setup_logging()
    load_dotenv()
    ensure_dirs()
    parser = build_parser()
    args = parser.parse_args(argv)
    cfg = load_config()
    try:
        return int(args.func(args, cfg))
    except KeyboardInterrupt:
        print("\nCancelado.")
        return 130
    except Exception as exc:  # noqa: BLE001
        log.error("Error: %s", exc)
        log.debug("Detalle", exc_info=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
