"""Utilitaires partagés par tous les scripts de phenix-video.
# Phenix-video — © 2026 Phenix - kcw. Tous droits réservés (voir LICENSE).

Aucune dépendance payante : uniquement ffmpeg/ffprobe + bibliothèques Python libres.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

# --------------------------------------------------------------------------- #
# Presets de sortie (réseaux sociaux)
# --------------------------------------------------------------------------- #
PRESETS = {
    # nom: (largeur, hauteur, fps, crf, débit audio)
    "tiktok": (1080, 1920, 30, 20, "192k"),
    "reels": (1080, 1920, 30, 20, "192k"),
    "shorts": (1080, 1920, 30, 20, "192k"),
    "square": (1080, 1080, 30, 20, "192k"),
    "youtube": (1920, 1080, 30, 18, "256k"),
    "portrait45": (1080, 1350, 30, 20, "192k"),
}


class StudioError(RuntimeError):
    """Erreur lisible renvoyée à l'utilisateur sans trace Python."""


def die(message: str, code: int = 1) -> "None":
    print(f"[erreur] {message}", file=sys.stderr)
    sys.exit(code)


def need_binary(name: str) -> str:
    path = shutil.which(name)
    if not path:
        raise StudioError(
            f"'{name}' est introuvable. Installe FFmpeg (https://ffmpeg.org/download.html) "
            "puis relance."
        )
    return path


# --------------------------------------------------------------------------- #
# Exécution de sous-processus
# --------------------------------------------------------------------------- #
def run(cmd: Sequence[str | os.PathLike], *, quiet: bool = True) -> subprocess.CompletedProcess:
    """Lance une commande, lève StudioError avec la fin de stderr si elle échoue."""
    cmd = [str(c) for c in cmd]
    proc = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if proc.returncode != 0:
        tail = "\n".join(proc.stderr.strip().splitlines()[-12:])
        raise StudioError(f"Commande en échec ({cmd[0]}), code {proc.returncode} :\n{tail}")
    if not quiet and proc.stderr:
        print(proc.stderr, file=sys.stderr)
    return proc


def ffmpeg(args: Sequence[str | os.PathLike], *, quiet: bool = True) -> subprocess.CompletedProcess:
    need_binary("ffmpeg")
    return run(["ffmpeg", "-hide_banner", "-nostdin", "-y", "-loglevel", "error", *args], quiet=quiet)


# --------------------------------------------------------------------------- #
# Fichiers de sortie atomiques : jamais de .mp4 tronqué qui se lit quand même
# --------------------------------------------------------------------------- #
def temp_sibling(dest: str | os.PathLike) -> Path:
    dest = Path(dest)
    return dest.with_name(f".{dest.stem}.partial{dest.suffix}")


def finalize(tmp: str | os.PathLike, dest: str | os.PathLike) -> Path:
    tmp, dest = Path(tmp), Path(dest)
    if not tmp.exists() or tmp.stat().st_size == 0:
        raise StudioError(f"Sortie vide : {tmp}")
    os.replace(tmp, dest)
    return dest


def ensure_parent(path: str | os.PathLike) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


# --------------------------------------------------------------------------- #
# ffprobe
# --------------------------------------------------------------------------- #
@dataclass
class MediaInfo:
    path: str
    width: int
    height: int
    fps: float
    duration: float
    has_audio: bool
    rotation: int = 0


def _fraction(text: str) -> float:
    try:
        num, _, den = text.partition("/")
        return float(num) / float(den) if den else float(num)
    except (ValueError, ZeroDivisionError):
        return 0.0


def probe(path: str | os.PathLike) -> MediaInfo:
    need_binary("ffprobe")
    path = str(path)
    if not os.path.exists(path):
        raise StudioError(f"Fichier introuvable : {path}")
    proc = run(
        ["ffprobe", "-v", "error", "-print_format", "json", "-show_streams", "-show_format", path]
    )
    data = json.loads(proc.stdout)
    video = next((s for s in data.get("streams", []) if s.get("codec_type") == "video"), None)
    if video is None:
        raise StudioError(f"Aucune piste vidéo dans {path}")
    has_audio = any(s.get("codec_type") == "audio" for s in data["streams"])
    rotation = 0
    for side in video.get("side_data_list", []) or []:
        if "rotation" in side:
            rotation = int(side["rotation"])
    tags_rot = (video.get("tags") or {}).get("rotate")
    if tags_rot:
        rotation = int(tags_rot)
    width, height = int(video["width"]), int(video["height"])
    if abs(rotation) in (90, 270):
        width, height = height, width
    fps = _fraction(video.get("avg_frame_rate", "0")) or _fraction(video.get("r_frame_rate", "30"))
    duration = float(data.get("format", {}).get("duration") or video.get("duration") or 0.0)
    return MediaInfo(path, width, height, fps or 30.0, duration, has_audio, rotation)


# --------------------------------------------------------------------------- #
# Temps et formats
# --------------------------------------------------------------------------- #
_TS = re.compile(r"^(?:(\d+):)?(\d+):(\d+(?:[.,]\d+)?)$")


def parse_time(value: str | float | int) -> float:
    """Accepte 12.5, '12.5', '01:02.5', '1:02:03'."""
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    match = _TS.match(text)
    if match:
        hours = int(match.group(1) or 0)
        minutes = int(match.group(2))
        seconds = float(match.group(3).replace(",", "."))
        return hours * 3600 + minutes * 60 + seconds
    try:
        return float(text.replace(",", "."))
    except ValueError as exc:
        raise StudioError(f"Temps invalide : {value!r}") from exc


def fmt_clock(seconds: float) -> str:
    seconds = max(0.0, seconds)
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{int(h):02d}:{int(m):02d}:{s:06.3f}"


def fmt_srt(seconds: float) -> str:
    return fmt_clock(seconds).replace(".", ",")


def fmt_ass(seconds: float) -> str:
    seconds = max(0.0, seconds)
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{int(h)}:{int(m):02d}:{s:05.2f}"


def parse_size(text: str) -> tuple[int, int]:
    match = re.fullmatch(r"(\d{2,5})x(\d{2,5})", text.strip().lower())
    if not match:
        raise StudioError(f"Taille invalide : {text!r} (attendu : 1080x1920)")
    w, h = int(match.group(1)), int(match.group(2))
    return w - w % 2, h - h % 2


def size_for(aspect: str | None, preset: str | None, width: int | None = None) -> tuple[int, int, int, int, str]:
    """Retourne (w, h, fps, crf, audio_bitrate) à partir d'un preset ou d'un ratio."""
    if preset:
        if preset not in PRESETS:
            raise StudioError(f"Preset inconnu : {preset}. Choix : {', '.join(PRESETS)}")
        return PRESETS[preset]
    if aspect:
        a, _, b = aspect.partition(":")
        ratio = float(a) / float(b)
        base = width or 1080
        w = base
        h = int(round(w / ratio))
        return w - w % 2, h - h % 2, 30, 20, "192k"
    return PRESETS["tiktok"]


# --------------------------------------------------------------------------- #
# JSON
# --------------------------------------------------------------------------- #
def load_json(path: str | os.PathLike):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError as exc:
        raise StudioError(f"Fichier introuvable : {path}") from exc
    except json.JSONDecodeError as exc:
        raise StudioError(f"JSON invalide dans {path} : {exc}") from exc


def save_json(path: str | os.PathLike, data) -> None:
    ensure_parent(path)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)


def slugify(text: str, maxlen: int = 48) -> str:
    import unicodedata

    norm = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^A-Za-z0-9]+", "-", norm).strip("-").lower()
    return (slug[:maxlen].rstrip("-")) or "clip"


def x264_args(crf: int = 20, preset: str = "veryfast") -> list[str]:
    """Encodage H.264 compatible partout (TikTok, Reels, Shorts, WhatsApp)."""
    return [
        "-c:v", "libx264", "-preset", preset, "-crf", str(crf),
        "-profile:v", "high", "-pix_fmt", "yuv420p", "-movflags", "+faststart",
    ]


def audio_args(bitrate: str = "192k") -> list[str]:
    return ["-c:a", "aac", "-b:a", bitrate, "-ar", "48000", "-ac", "2"]


def escape_filter_path(path: str | os.PathLike) -> str:
    """Échappe un chemin pour l'utiliser dans un filtre ffmpeg (ass=, subtitles=)."""
    text = str(Path(path).resolve()).replace("\\", "/")
    text = text.replace(":", r"\:").replace("'", r"\'").replace(",", r"\,").replace("[", r"\[").replace("]", r"\]")
    return text


def chunks(items: Iterable, size: int):
    bucket = []
    for item in items:
        bucket.append(item)
        if len(bucket) == size:
            yield bucket
            bucket = []
    if bucket:
        yield bucket
