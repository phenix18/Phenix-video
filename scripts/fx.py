#!/usr/bin/env python3
# Phenix-video — © 2026 Phenix - kcw. Tous droits réservés (voir LICENSE).
"""Catalogue d'effets et de nettoyage (100 % FFmpeg, gratuit, local).

  fx.py --list
  fx.py in.mp4 -o out.mp4 --effects vignette,warm,grain [--clean] [--title "Texte"]

Chaque effet est un petit bloc de filtres vidéo ; ils s'enchaînent dans l'ordre donné.
`--clean` applique le nettoyage (bruit audio/vidéo, netteté, lumière, volume).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from common import (StudioError, audio_args, die, ensure_parent, finalize, need_binary, probe, run,  # noqa: E402
                    temp_sibling)
from render import QUALITY  # noqa: E402


def _even(v: float) -> int:
    return max(2, int(v) // 2 * 2)


def _burst(period: float, length: float) -> str:
    return f"lt(mod(t\\,{period})\\,{length})"


# nom -> (description, fonction(w, h, dur) -> liste de filtres vidéo)
EFFECTS: dict[str, tuple[str, callable]] = {
    "vignette": ("Bords assombris, regard attiré au centre", lambda w, h, d: ["vignette=PI/5"]),
    "warm": ("Couleurs chaudes (peau, ambiance dorée)",
             lambda w, h, d: ["colorbalance=rs=.05:gs=.01:bs=-.06:rh=.04:bh=-.04", "eq=saturation=1.08"]),
    "cool": ("Couleurs froides (ambiance moderne)",
             lambda w, h, d: ["colorbalance=rs=-.05:bs=.07:rh=-.03:bh=.05", "eq=saturation=1.05"]),
    "cinema": ("Look cinéma orange/teal + contraste",
               lambda w, h, d: ["eq=contrast=1.12:saturation=0.95", "colorbalance=rs=-.04:bs=.06:rh=.06:bh=-.05",
                                "vignette=PI/6"]),
    "vivid": ("Couleurs éclatantes (idéal TikTok)", lambda w, h, d: ["eq=saturation=1.35:contrast=1.07"]),
    "bw": ("Noir et blanc contrasté", lambda w, h, d: ["hue=s=0", "eq=contrast=1.15"]),
    "grain": ("Grain de pellicule léger", lambda w, h, d: ["noise=alls=10:allf=t"]),
    "sharpen": ("Netteté", lambda w, h, d: ["unsharp=5:5:0.8:5:5:0.0"]),
    "glitch": ("Éclats de glitch RVB toutes les 3 s",
               lambda w, h, d: [f"rgbashift=rh=10:bh=-10:gv=4:enable='{_burst(3, 0.18)}'",
                                f"noise=alls=40:allf=t:enable='{_burst(3, 0.18)}'"]),
    "shake": ("Petit tremblement d'impact toutes les 4 s",
              lambda w, h, d: [f"scale={_even(w * 1.08)}:{_even(h * 1.08)}",
                               f"crop={_even(w)}:{_even(h)}:x='(in_w-out_w)/2+sin(t*55)*(in_w-out_w)/2*0.8*"
                               f"{_burst(4, 0.35)}':y='(in_h-out_h)/2+cos(t*47)*(in_h-out_h)/2*0.8*{_burst(4, 0.35)}'"]),
    "flash": ("Flash blanc bref toutes les 5 s",
              lambda w, h, d: [f"eq=brightness=0.45:enable='between(mod(t\\,5)\\,0\\,0.07)'"]),
    "zoomin": ("Zoom lent continu (dynamisme)",
               lambda w, h, d: [f"scale=w='trunc({w}*(1+0.06*t/{max(d, 1):.2f})/2)*2':h='trunc({h}*(1+0.06*t/{max(d, 1):.2f})/2)*2':eval=frame",
                                f"crop={_even(w)}:{_even(h)}"]),
    "fade": ("Fondu d'entrée et de sortie",
             lambda w, h, d: ["fade=t=in:d=0.35", f"fade=t=out:st={max(0.0, d - 0.45):.2f}:d=0.45"]),
    "lowlight": ("Éclaircit une vidéo sombre", lambda w, h, d: ["eq=brightness=0.06:gamma=1.25:contrast=1.05"]),
}

CLEAN_VIDEO = ["hqdn3d=2.0:1.5:3.0:3.0", "unsharp=5:5:0.55:5:5:0.0", "eq=contrast=1.04:saturation=1.06"]
CLEAN_AUDIO = "highpass=f=80,afftdn=nr=14:nf=-32:tn=1,acompressor=threshold=-20dB:ratio=2.5:attack=8:release=120," \
              "loudnorm=I=-14:TP=-1.5:LRA=11"


def build_filters(effects: list[str], w: int, h: int, dur: float, clean: bool) -> list[str]:
    chain: list[str] = []
    if clean:
        chain += CLEAN_VIDEO
    for name in effects:
        if name not in EFFECTS:
            raise StudioError(f"Effet inconnu : {name}. Disponibles : {', '.join(EFFECTS)}")
        chain += EFFECTS[name][1](w, h, dur)
    return chain


def apply(src: str, out: str, effects: list[str], *, clean: bool = False, title: str | None = None,
          quality: str = "balanced") -> None:
    need_binary("ffmpeg")
    info = probe(src)
    chain = build_filters(effects, info.width, info.height, info.duration, clean)
    if title:
        safe = title.replace("\\", "\\\\").replace("'", "’").replace(":", "\\:").replace("%", "\\%")
        size = max(28, info.width // 16)
        chain.append(f"drawtext=text='{safe}':fontcolor=white:fontsize={size}:x=(w-text_w)/2:y=h*0.12:"
                     f"box=1:boxcolor=black@0.45:boxborderw=18:enable='between(t,0.3,3.5)':"
                     f"alpha='if(lt(t,0.8),(t-0.3)/0.5,if(gt(t,3.0),(3.5-t)/0.5,1))'")
    crf, preset, abr = QUALITY[quality]
    cmd = ["ffmpeg", "-hide_banner", "-nostdin", "-y", "-loglevel", "error", "-i", src]
    if chain:
        cmd += ["-vf", ",".join(chain)]
    if clean and info.has_audio:
        cmd += ["-af", CLEAN_AUDIO]
    cmd += ["-map", "0:v", "-map", "0:a?", "-c:v", "libx264", "-preset", preset, "-crf", str(crf),
            "-profile:v", "high", "-pix_fmt", "yuv420p", "-movflags", "+faststart"]
    cmd += audio_args(abr) if (clean and info.has_audio) else ["-c:a", "copy"]
    ensure_parent(out)
    tmp = temp_sibling(out)
    try:
        run([*cmd, str(tmp)])
        finalize(tmp, out)
    finally:
        tmp.unlink(missing_ok=True)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("input", nargs="?")
    ap.add_argument("-o", "--out")
    ap.add_argument("--effects", default="", help="liste séparée par des virgules (voir --list)")
    ap.add_argument("--clean", action="store_true", help="nettoyage : bruit audio/vidéo, netteté, volume")
    ap.add_argument("--title", default=None, help="titre animé en haut pendant 3 s")
    ap.add_argument("--quality", default="balanced", choices=list(QUALITY))
    ap.add_argument("--list", action="store_true")
    a = ap.parse_args()
    if a.list:
        for k, (desc, _) in EFFECTS.items():
            print(f"{k:10s} {desc}")
        return
    if not a.input or not a.out:
        ap.error("input et -o sont requis")
    try:
        apply(a.input, a.out, [e for e in a.effects.split(",") if e], clean=a.clean, title=a.title, quality=a.quality)
        print(f"[ok] {a.out}")
    except StudioError as exc:
        die(str(exc))


if __name__ == "__main__":
    main()
