#!/usr/bin/env python3
# Phenix-video — © 2026 Phenix - kcw. Tous droits réservés (voir LICENSE).
"""Personnages et stickers superposés à la vidéo (gratuit, local).

  characters.py mascot in.mp4 -o out.mp4 [--position br] [--scale 0.28] [--start 0 --end 10]
      Mascotte « phenix_forever » (ton phénix, assets/phenix_forever.png) : elle pulse, rebondit et rayonne avec le volume
      de la voix (--style chacal : ancienne mascotte dessinée, bouche synchronisée).
  characters.py sticker in.mp4 -o out.mp4 --image perso.png|anim.gif [--position tr] [--scale 0.2] [--start 2 --end 6]
      Image / GIF animé que tu fournis (logo, emoji, mascotte de ta marque).
  characters.py preview mascot.png        écrit un aperçu de la mascotte

Aucun personnage protégé (dessins animés, films, jeux) n'est fourni : utilise tes propres images ou la mascotte originale.
"""
from __future__ import annotations

import argparse
import math
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from common import (StudioError, audio_args, die, ensure_parent, finalize, need_binary, parse_time, probe,  # noqa: E402
                    temp_sibling)
from render import QUALITY  # noqa: E402

POS = {"tl": ("{m}", "{m}"), "tr": ("W-w-{m}", "{m}"), "bl": ("{m}", "H-h-{m}"), "br": ("W-w-{m}", "H-h-{m}"),
       "center": ("(W-w)/2", "(H-h)/2"), "bc": ("(W-w)/2", "H-h-{m}"), "tc": ("(W-w)/2", "{m}")}


def _pos(position: str, margin: int) -> str:
    if position not in POS:
        raise StudioError(f"Position inconnue : {position}. Choix : {', '.join(POS)}")
    x, y = POS[position]
    return f"{x.format(m=margin)}:{y.format(m=margin)}"


# --------------------------------------------------------------------------- mascotte
def draw_mascot(size: int, mouth: float = 0.0, blink: float = 0.0, bounce: float = 0.0):
    """Image BGRA (size x size). mouth 0..1, blink 0..1 (1 = yeux fermés), bounce -1..1."""
    import cv2
    import numpy as np
    ss = 3  # sur-échantillonnage : contours lisses
    S = size * ss
    img = np.zeros((S, S, 4), np.uint8)
    dy = int(bounce * 0.025 * S)

    def P(x, y):
        return int(x * S), int(y * S + dy)

    def poly(pts, color, edge=None):
        a = np.array([P(*p) for p in pts], np.int32)
        cv2.fillPoly(img, [a], color, cv2.LINE_AA)
        if edge:
            cv2.polylines(img, [a], True, edge, max(2, S // 140), cv2.LINE_AA)

    ink = (46, 38, 34, 255)       # anthracite (BGRA)
    ink2 = (70, 58, 52, 255)
    gold = (60, 175, 235, 255)
    gold_d = (35, 125, 200, 255)
    cream = (205, 225, 240, 255)
    dark = (24, 18, 18, 255)
    # buste / collier
    poly([(0.18, 1.0), (0.24, 0.80), (0.76, 0.80), (0.82, 1.0)], ink)
    poly([(0.28, 0.80), (0.72, 0.80), (0.64, 0.93), (0.36, 0.93)], gold, gold_d)
    poly([(0.40, 0.85), (0.60, 0.85), (0.50, 0.97)], (180, 90, 40, 255))
    # oreilles
    poly([(0.20, 0.50), (0.17, 0.06), (0.40, 0.30)], ink, dark)
    poly([(0.80, 0.50), (0.83, 0.06), (0.60, 0.30)], ink, dark)
    poly([(0.215, 0.42), (0.195, 0.15), (0.34, 0.31)], gold)
    poly([(0.785, 0.42), (0.805, 0.15), (0.66, 0.31)], gold)
    # tête
    cv2.ellipse(img, P(0.5, 0.46), (int(0.30 * S), int(0.28 * S)), 0, 0, 360, ink, -1, cv2.LINE_AA)
    cv2.ellipse(img, P(0.5, 0.46), (int(0.30 * S), int(0.28 * S)), 0, 0, 360, dark, max(2, S // 140), cv2.LINE_AA)
    # museau
    poly([(0.36, 0.50), (0.64, 0.50), (0.58, 0.72), (0.42, 0.72)], cream, dark)
    # mâchoire / bouche ouverte
    op = max(0.0, min(1.0, mouth))
    if op > 0.03:
        mh = 0.015 + 0.10 * op
        poly([(0.415, 0.665), (0.585, 0.665), (0.56, 0.665 + mh + 0.02), (0.44, 0.665 + mh + 0.02)], dark)
        if op > 0.45:
            cv2.ellipse(img, P(0.5, 0.665 + mh), (int(0.05 * S), int(0.025 * S)), 0, 0, 180, (110, 110, 235, 255), -1,
                        cv2.LINE_AA)
    else:
        cv2.line(img, P(0.43, 0.675), P(0.57, 0.675), dark, max(2, S // 120), cv2.LINE_AA)
    # nez
    poly([(0.45, 0.50), (0.55, 0.50), (0.50, 0.565)], dark)
    # yeux
    for cx in (0.37, 0.63):
        cv2.ellipse(img, P(cx, 0.40), (int(0.075 * S), int(0.085 * S * (1 - 0.92 * blink))), 0, 0, 360,
                    (250, 250, 250, 255), -1, cv2.LINE_AA)
        if blink < 0.7:
            cv2.circle(img, P(cx + 0.008, 0.405), int(0.032 * S), dark, -1, cv2.LINE_AA)
            cv2.circle(img, P(cx + 0.018, 0.39), int(0.010 * S), (255, 255, 255, 255), -1, cv2.LINE_AA)
        cv2.ellipse(img, P(cx, 0.40), (int(0.075 * S), int(0.085 * S * (1 - 0.92 * blink))), 0, 0, 360, gold_d,
                    max(2, S // 170), cv2.LINE_AA)
    # sourcils
    cv2.line(img, P(0.30, 0.30), P(0.43, 0.285), dark, max(3, S // 90), cv2.LINE_AA)
    cv2.line(img, P(0.70, 0.30), P(0.57, 0.285), dark, max(3, S // 90), cv2.LINE_AA)
    # marque dorée sur le front
    poly([(0.47, 0.20), (0.53, 0.20), (0.50, 0.29)], gold)
    return cv2.resize(img, (size, size), interpolation=cv2.INTER_AREA)


MASCOT_NAME = "phenix_forever"
MASCOT_IMG = Path(__file__).resolve().parent.parent / "assets" / "phenix_forever.png"


def load_phoenix(size: int):
    """Image de la mascotte phenix_forever (RGBA → BGRA, alpha non prémultiplié), carrée `size`."""
    import cv2
    img = cv2.imread(str(MASCOT_IMG), cv2.IMREAD_UNCHANGED)
    if img is None or img.ndim != 3 or img.shape[2] != 4:
        raise StudioError(f"Image de la mascotte introuvable ou sans transparence : {MASCOT_IMG}")
    return cv2.resize(img, (size, size), interpolation=cv2.INTER_AREA)


def draw_phoenix(base, level: float = 0.0, bob: float = 0.0, t: float = 0.0):
    """Une image de la mascotte : pulsation d'échelle + halo orangé selon le volume (`level` 0..1), flottement doux."""
    import cv2
    import numpy as np
    size = base.shape[0]
    scale = 0.90 + 0.10 * level + 0.012 * math.sin(t * 2.2)  # respiration lente + pulsation à la voix
    dy = (-0.035 * level + 0.012 * math.sin(t * 2.2) + 0.02 * bob) * size
    m = np.float32([[scale, 0, size * (1 - scale) / 2], [0, scale, size * (1 - scale) / 2 + dy]])
    out = cv2.warpAffine(base, m, (size, size), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=(0, 0, 0, 0))
    if level > 0.05:  # halo : alpha flouté teinté orange derrière l'oiseau
        a = cv2.GaussianBlur(out[..., 3].astype(np.float32) / 255.0, (0, 0), size * 0.035)
        glow_a = np.clip(a * 0.9 * level, 0, 1)
        res = np.zeros_like(out, dtype=np.float32)
        res[..., 0], res[..., 1], res[..., 2] = 40, 150, 255  # BGR : orange vif
        fa = out[..., 3].astype(np.float32) / 255.0
        total = glow_a + fa * (1 - glow_a)
        for c in range(3):
            res[..., c] = (res[..., c] * glow_a * (1 - fa) + out[..., c] * fa) / np.maximum(total - 0 * glow_a, 1e-4)
        res[..., 3] = np.clip(total, 0, 1) * 255
        return np.clip(res, 0, 255).astype(np.uint8)
    return out


def _envelope(src: str, fps: float, frames: int):
    """Volume de la voix par image, normalisé 0..1 (pour la bouche)."""
    import numpy as np
    proc = subprocess.run(["ffmpeg", "-hide_banner", "-nostdin", "-loglevel", "error", "-i", src, "-vn", "-ac", "1",
                           "-ar", "16000", "-f", "s16le", "-"], stdout=subprocess.PIPE)
    pcm = np.frombuffer(proc.stdout, np.int16).astype(np.float32) / 32768.0
    if pcm.size == 0:
        return np.zeros(frames, np.float32)
    hop = 16000.0 / fps
    env = np.zeros(frames, np.float32)
    for i in range(frames):
        seg = pcm[int(i * hop):int((i + 1) * hop) + 1]
        if seg.size:
            env[i] = float(np.sqrt(np.mean(seg ** 2)))
    ref = float(np.percentile(env, 92))
    if not ref > 1e-6:  # audio quasi muet : bouche fermée
        return np.zeros(frames, np.float32)
    env = np.clip(env / ref, 0, 1.2)
    env = np.clip((env - 0.12) / 0.7, 0, 1)  # seuil : pas de bouche qui bouge dans le silence
    out = env.copy()
    for i in range(1, frames):  # attaque rapide, relâchement doux
        out[i] = env[i] if env[i] > out[i - 1] else 0.6 * out[i - 1] + 0.4 * env[i]
    return out


def add_mascot(src: str, out: str, *, position: str = "br", scale: float = 0.28, start: float = 0.0,
               end: float | None = None, quality: str = "balanced", style: str = "phenix_forever") -> None:
    need_binary("ffmpeg")
    use_img = style != "chacal" and MASCOT_IMG.is_file()
    info = probe(src)
    fps = info.fps
    frames = int(info.duration * fps) + 2
    side = max(64, int(min(info.width, info.height) * scale) // 2 * 2)
    env = _envelope(src, fps, frames)
    end_t = end if end is not None else info.duration
    crf, preset, abr = QUALITY[quality]
    ensure_parent(out)
    tmp = temp_sibling(out)
    margin = max(12, info.width // 40)
    cmd = ["ffmpeg", "-hide_banner", "-nostdin", "-y", "-loglevel", "error", "-i", src,
           "-f", "rawvideo", "-pix_fmt", "bgra", "-s", f"{side}x{side}", "-r", f"{fps:.4f}", "-i", "-",
           "-filter_complex", f"[0:v][1:v]overlay={_pos(position, margin)}:enable='between(t,{start:.2f},{end_t:.2f})':"
                              f"eof_action=pass:format=auto,format=yuv420p[v]",
           "-map", "[v]", "-map", "0:a?", "-c:v", "libx264", "-preset", preset, "-crf", str(crf), "-profile:v", "high",
           *audio_args(abr), "-t", f"{info.duration:.3f}", "-movflags", "+faststart", str(tmp)]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        cache: dict[tuple, bytes] = {}
        base = load_phoenix(side) if use_img else None
        for i in range(frames):
            t = i / fps
            mouth = round(float(env[i]) * 6) / 6  # quantifié : réutilise les images déjà dessinées
            if use_img:
                bob = round(math.sin(t * 9.0) * float(env[i]) * 4) / 4
                key = (mouth, bob, round(t * 12) / 12)  # le flottement lent est recalculé ~12 fois/s
                if key not in cache:
                    cache[key] = draw_phoenix(base, mouth, bob, key[2]).tobytes()
                    if len(cache) > 600:
                        cache.pop(next(iter(cache)))
                proc.stdin.write(cache[key])
                continue
            blink = 1.0 if (t % 3.6) < 0.12 else 0.0
            bounce = round(math.sin(t * 9.0) * float(env[i]) * 4) / 4
            key = (mouth, blink, bounce)
            if key not in cache:
                cache[key] = draw_mascot(side, mouth, blink, bounce).tobytes()
            proc.stdin.write(cache[key])
        proc.stdin.close()
        err = proc.stderr.read().decode("utf-8", "replace")
        if proc.wait() != 0:
            raise StudioError(f"Encodage en échec : {err[-400:]}")
        finalize(tmp, out)
    finally:
        if proc.poll() is None:
            proc.kill()
        tmp.unlink(missing_ok=True)


# --------------------------------------------------------------------------- sticker
def add_sticker(src: str, out: str, image: str, *, position: str = "tr", scale: float = 0.2, start: float = 0.0,
                end: float | None = None, quality: str = "balanced") -> None:
    need_binary("ffmpeg")
    if not Path(image).is_file():
        raise StudioError(f"Image introuvable : {image}")
    info = probe(src)
    end_t = end if end is not None else info.duration
    sw = max(32, int(info.width * scale) // 2 * 2)
    is_gif = Path(image).suffix.lower() == ".gif"
    pre = ["-ignore_loop", "0"] if is_gif else ["-loop", "1", "-framerate", f"{info.fps:.3f}"]
    margin = max(12, info.width // 40)
    crf, preset, abr = QUALITY[quality]
    graph = (f"[1:v]scale={sw}:-2,format=rgba,setpts=PTS-STARTPTS+{start:.3f}/TB,"
             f"fade=t=in:st={start:.3f}:d=0.25:alpha=1[s];"
             f"[0:v][s]overlay={_pos(position, margin)}:enable='between(t,{start:.2f},{end_t:.2f})':"
             f"eof_action=pass:format=auto,format=yuv420p[v]")
    ensure_parent(out)
    tmp = temp_sibling(out)
    cmd = ["ffmpeg", "-hide_banner", "-nostdin", "-y", "-loglevel", "error", "-i", src, *pre, "-i", image,
           "-filter_complex", graph, "-map", "[v]", "-map", "0:a?", "-c:v", "libx264", "-preset", preset,
           "-crf", str(crf), "-profile:v", "high", *audio_args(abr), "-t", f"{info.duration:.3f}",
           "-movflags", "+faststart", str(tmp)]
    r = subprocess.run(cmd, stderr=subprocess.PIPE, text=True)
    try:
        if r.returncode != 0:
            raise StudioError(f"Sticker en échec : {r.stderr[-400:]}")
        finalize(tmp, out)
    finally:
        tmp.unlink(missing_ok=True)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("mascot", "sticker"):
        p = sub.add_parser(name)
        p.add_argument("input")
        p.add_argument("-o", "--out", required=True)
        p.add_argument("--position", default="br" if name == "mascot" else "tr", choices=list(POS))
        p.add_argument("--scale", type=float, default=0.28 if name == "mascot" else 0.2)
        p.add_argument("--start", default="0")
        p.add_argument("--end", default=None)
        p.add_argument("--quality", default="balanced", choices=list(QUALITY))
        if name == "sticker":
            p.add_argument("--image", required=True)
        else:
            p.add_argument("--style", default="phenix_forever", choices=["phenix_forever", "chacal"])
    pv = sub.add_parser("preview")
    pv.add_argument("out")
    a = ap.parse_args()
    try:
        if a.cmd == "preview":
            import cv2
            import numpy as np
            base = load_phoenix(300) if MASCOT_IMG.is_file() else None
            tiles = ([draw_phoenix(base, lv, 0, 0.5) for lv in (0, 0.4, 0.7, 1.0)] if base is not None
                     else [draw_mascot(300, m, b, 0) for m, b in ((0, 0), (0.5, 0), (1.0, 0), (0.4, 1))])
            sheet = np.concatenate(tiles, axis=1)
            bg = np.full(sheet.shape[:2] + (3,), 235, np.uint8)
            al = sheet[..., 3:4] / 255.0
            cv2.imwrite(a.out, (sheet[..., :3] * al + bg * (1 - al)).astype(np.uint8))
            print(f"[ok] {a.out}")
            return
        end = parse_time(a.end) if a.end else None
        if a.cmd == "mascot":
            add_mascot(a.input, a.out, position=a.position, scale=a.scale, start=parse_time(a.start), end=end,
                       quality=a.quality, style=a.style)
        else:
            add_sticker(a.input, a.out, a.image, position=a.position, scale=a.scale, start=parse_time(a.start),
                        end=end, quality=a.quality)
        print(f"[ok] {a.out}")
    except StudioError as exc:
        die(str(exc))


if __name__ == "__main__":
    main()
