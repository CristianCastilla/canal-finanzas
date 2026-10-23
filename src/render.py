"""Montaje del vídeo: voz, imagen animada, subtítulos y música."""
from __future__ import annotations

import logging
import math
import os
import platform
import re
import shutil
import subprocess
import time
import wave
from pathlib import Path

from . import charts, images, tts
from .config import OUT_DIR, ROOT
from .thumbnail import make_thumbnail

log = logging.getLogger(__name__)

FFMPEG = os.environ.get("FFMPEG_BIN", "ffmpeg")
FFPROBE = os.environ.get("FFPROBE_BIN", "ffprobe")
GAP = 0.18


def _run(cmd: list[str], cwd: Path | None = None, timeout: int = 3600) -> None:
    result = subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )
    if result.returncode != 0:
        log.error("FFmpeg falló: %s", " ".join(cmd))
        log.error(result.stderr[-2500:])
        raise RuntimeError(f"FFmpeg devolvió {result.returncode}")


def _duration(path: Path) -> float:
    result = subprocess.run(
        [FFPROBE, "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", str(path)],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60,
    )
    try:
        return float(result.stdout.strip())
    except ValueError:
        return 0.0


def _to_wav(source: Path, out: Path) -> Path:
    _run([FFMPEG, "-y", "-i", str(source), "-ar", "24000", "-ac", "1",
          "-c:a", "pcm_s16le", str(out)], timeout=120)
    return out


def _build_voice(wavs: list[Path], texts: list[str], out: Path) -> tuple[list[tuple[float, float, str]], float]:
    with wave.open(str(wavs[0]), "rb") as first:
        channels = first.getnchannels()
        rate = first.getframerate()
        width = first.getsampwidth()

    silence = b"\x00" * int(rate * width * channels * GAP)
    timeline: list[tuple[float, float, str]] = []
    cursor = 0.0

    with wave.open(str(out), "wb") as dest:
        dest.setnchannels(channels)
        dest.setsampwidth(width)
        dest.setframerate(rate)
        for wav, text in zip(wavs, texts):
            with wave.open(str(wav), "rb") as source:
                frames = source.readframes(source.getnframes())
                duration = source.getnframes() / float(source.getframerate())
            dest.writeframes(frames)
            timeline.append((cursor, duration, text))
            dest.writeframes(silence)
            cursor += duration + GAP

    return timeline, cursor


def _chunks(text: str, max_chars: int) -> list[str]:
    sentences = re.split(r"(?<=[.!?])\s+", " ".join(text.split()))
    result: list[str] = []
    for sentence in sentences:
        if len(sentence) <= max_chars:
            result.append(sentence)
            continue
        words = sentence.split()
        current = ""
        for word in words:
            if len(current) + len(word) + 1 <= max_chars:
                current = f"{current} {word}".strip()
            else:
                if current:
                    result.append(current)
                current = word
        if current:
            result.append(current)
    return result or [text]


def _ass_time(seconds: float) -> str:
    seconds = max(0.0, seconds)
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = seconds % 60
    return f"{hours}:{minutes:02d}:{secs:05.2f}"


def _make_ass(timeline: list[tuple[float, float, str]], out: Path, size: tuple[int, int]) -> Path:
    width, height = size
    vertical = height > width
    font_size = 50 if vertical else 48
    margin_v = 320 if vertical else 70
    margin_h = 60 if vertical else 50
    font = "Arial" if platform.system() == "Windows" else "DejaVu Sans"

    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{font},{font_size},&H00FFFFFF,&H000000FF,&H00000000,&H64000000,-1,0,0,0,100,100,0,0,1,4,0,2,{margin_h},{margin_h},{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

    lines = [header]
    for start, duration, text in timeline:
        pieces = _chunks(text, 60 if vertical else 64)
        total_chars = sum(len(piece) for piece in pieces) or 1
        cursor = start
        for piece in pieces:
            share = duration * (len(piece) / total_chars)
            clean = piece.replace("\\", "/").replace("{", "(").replace("}", ")")
            lines.append(
                f"Dialogue: 0,{_ass_time(cursor)},{_ass_time(cursor + share)},Default,,0,0,0,,{clean}"
            )
            cursor += share

    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out


def _concat_line(path: Path) -> str:
    value = str(path).replace("\\", "/").replace("'", "'\\''")
    return f"file '{value}'"


def _make_clip(image: Path, out: Path, size: tuple[int, int], duration: float,
               fps: int, zoom_in: bool, static: bool = False) -> Path:
    width, height = size
    common = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
              "-pix_fmt", "yuv420p", "-an"]

    if static:
        vf = (f"scale={width}:{height}:force_original_aspect_ratio=increase,"
              f"crop={width}:{height},format=yuv420p")
        _run([FFMPEG, "-y", "-loop", "1", "-i", str(image), "-t", f"{duration:.3f}",
              "-vf", vf, "-r", str(fps), *common, str(out)])
        return out

    big_w, big_h = int(width * 1.15), int(height * 1.15)
    frames = max(1, math.ceil(duration * fps))
    zoom = "min(1.0+0.0011*on,1.14)" if zoom_in else "max(1.14-0.0011*on,1.0)"
    vf = (
        f"scale={big_w}:{big_h}:force_original_aspect_ratio=increase,"
        f"crop={big_w}:{big_h},"
        f"zoompan=z='{zoom}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
        f"d={frames}:s={width}x{height}:fps={fps},format=yuv420p"
    )
    _run([FFMPEG, "-y", "-i", str(image), "-vf", vf, "-frames:v", str(frames),
          *common, str(out)])
    return out


def _mix_audio(voice: Path, music: Path | None, out: Path, volume: float) -> Path:
    if music and music.exists():
        try:
            _run([
                FFMPEG, "-y", "-i", str(voice), "-stream_loop", "-1", "-i", str(music),
                "-filter_complex",
                f"[1:a]volume={volume}[m];[0:a][m]amix=inputs=2:duration=first:normalize=0[a]",
                "-map", "[a]", "-c:a", "aac", "-b:a", "192k", str(out),
            ])
            return out
        except RuntimeError:
            log.warning("No se pudo mezclar la música; sigo solo con la voz.")
    _run([FFMPEG, "-y", "-i", str(voice), "-c:a", "aac", "-b:a", "192k", str(out)])
    return out


def render_item(item: dict, cfg: dict, force: bool = False) -> dict:
    fmt = item["format"]
    fmt_cfg = cfg["formats"][fmt]
    width, height = int(fmt_cfg["width"]), int(fmt_cfg["height"])
    fps = int(fmt_cfg["fps"])

    outdir = OUT_DIR / item["id"]
    build = outdir / "build"
    if build.exists():
        shutil.rmtree(build)
    for sub in ("audio", "images", "clips"):
        (build / sub).mkdir(parents=True, exist_ok=True)

    final_video = outdir / "video.mp4"
    if final_video.exists() and not force:
        log.info("Ya existe %s (usa --force para rehacerlo).", final_video)
        return {
            "video_path": final_video.relative_to(ROOT).as_posix(),
            "thumb_path": (outdir / "thumb.jpg").relative_to(ROOT).as_posix()
            if (outdir / "thumb.jpg").exists() else None,
            "duration": _duration(final_video),
        }

    img_w = int(cfg["images"][f"width_{fmt}"])
    img_h = int(cfg["images"][f"height_{fmt}"])
    seed_base = int(cfg["images"].get("seed", 7))

    wavs: list[Path] = []
    texts: list[str] = []
    clips: list[Path] = []
    first_image: Path | None = None
    image_budget = time.time() + 1500  # 25 min para todas las ilustraciones

    for index, scene in enumerate(item["scenes"], start=1):
        log.info("[%s] escena %s/%s", item["id"], index, len(item["scenes"]))
        text = scene["text"]
        texts.append(text)

        mp3 = build / "audio" / f"scene_{index:02d}.mp3"
        wav = build / "audio" / f"scene_{index:02d}.wav"
        tts.synthesize(text, mp3, cfg)
        _to_wav(mp3, wav)
        wavs.append(wav)
        duration = _duration(wav)

        image = build / "images" / f"scene_{index:02d}.jpg"
        static = False
        chart = scene.get("chart")
        if chart and fmt == "long":
            try:
                made = charts.make_chart(chart, image)
            except Exception as exc:  # noqa: BLE001
                log.warning("No se pudo dibujar el gráfico: %s", exc)
                made = None
            if made:
                static = True
        if not image.exists():
            if time.time() > image_budget:
                log.warning("Presupuesto de imágenes agotado; uso respaldo en la escena %s.", index)
                images.fallback(scene["image_prompt"], image, img_w, img_h,
                                seed_base + index, cfg)
            else:
                images.generate(
                    scene["image_prompt"], image, img_w, img_h,
                    seed_base + index, cfg, label=item["title"],
                )
        if first_image is None and not static:
            first_image = image

        clip = build / "clips" / f"scene_{index:02d}.mp4"
        _make_clip(image, clip, (width, height), duration + GAP, fps,
                   zoom_in=(index % 2 == 1), static=static)
        clips.append(clip)

    if first_image is None:
        first_image = build / "images" / "scene_01.jpg"

    voice = build / "voice.wav"
    timeline, total = _build_voice(wavs, texts, voice)

    list_file = build / "clips.txt"
    list_file.write_text("\n".join(_concat_line(c) for c in clips) + "\n", encoding="utf-8")
    silent = build / "silent.mp4"
    try:
        _run([FFMPEG, "-y", "-f", "concat", "-safe", "0", "-i", "clips.txt",
              "-c", "copy", "-fflags", "+genpts", "silent.mp4"], cwd=build)
    except RuntimeError:
        log.warning("El concat directo falló; re-codifico los clips.")
        _run([FFMPEG, "-y", "-f", "concat", "-safe", "0", "-i", "clips.txt",
              "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
              "-pix_fmt", "yuv420p", "silent.mp4"], cwd=build)

    music_path = None
    if cfg["video"].get("music"):
        candidate = Path(cfg["video"]["music"])
        music_path = candidate if candidate.is_absolute() else ROOT / candidate
        if not music_path.exists():
            log.warning("No existe la música %s; sigo sin música.", music_path)
            music_path = None

    audio = _mix_audio(voice, music_path, build / "audio.m4a",
                       float(cfg["video"].get("music_volume", 0.07)))

    ass = _make_ass(timeline, build / "subs.ass", (width, height))
    cmd = [FFMPEG, "-y", "-i", "silent.mp4", "-i", "audio.m4a"]
    if cfg["video"].get("subtitle", True):
        cmd += ["-vf", f"ass={ass.name}", "-c:v", "libx264",
                "-crf", str(cfg["video"].get("crf", 20)),
                "-preset", str(cfg["video"].get("preset", "medium"))]
    else:
        cmd += ["-c:v", "copy"]
    cmd += ["-c:a", "copy", "-shortest", "-movflags", "+faststart", "video.mp4"]
    _run(cmd, cwd=build)

    final_video.unlink(missing_ok=True)
    shutil.move(str(build / "video.mp4"), str(final_video))

    thumb = outdir / "thumb.jpg"
    if fmt == "long":
        make_thumbnail(first_image, item.get("thumbnail_text") or item["title"], thumb,
                       cfg["channel"]["name"])
    else:
        # En Shorts YouTube usa un fotograma vertical; una miniatura 16:9 recortada queda peor.
        thumb.unlink(missing_ok=True)
        thumb = None

    log.info("Vídeo listo: %s (%.1f s)", final_video, _duration(final_video))
    return {
        "video_path": final_video.relative_to(ROOT).as_posix(),
        "thumb_path": thumb.relative_to(ROOT).as_posix() if thumb else None,
        "duration": round(_duration(final_video) or total, 2),
    }
