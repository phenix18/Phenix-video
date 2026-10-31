#!/usr/bin/env python3
# Phenix-video — © 2026 Phenix - kcw. Tous droits réservés (voir LICENSE).
"""Améliorer une vidéo en une commande : nettoyage → fond → effets → personnages/stickers.

  enhance.py clip.mp4 -o clip_pro.mp4 --clean --bg blur --effects cinema,vignette --mascot --title "Ma vidéo"
  enhance.py clip.mp4 -o out.mp4 --bg color:#0B1F3A --sticker logo.png@tr,0.15,0,99

Ordre fixe : 1) fond (si demandé)  2) nettoyage + effets + titre  3) mascotte  4) stickers.
Les étapes intermédiaires sont en qualité élevée puis supprimées ; `clip.mp4` n'est jamais modifié.
"""
from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from common import StudioError, die, ensure_parent, finalize, temp_sibling  # noqa: E402
from render import QUALITY  # noqa: E402


def parse_sticker(spec: str) -> dict:
    """image[@position,échelle,début,fin]  — ex. logo.png@tr,0.15,0,99"""
    path, _, rest = spec.partition("@")
    opts = {"image": path, "position": "tr", "scale": 0.2, "start": 0.0, "end": None}
    if rest:
        parts = rest.split(",")
        opts["position"] = parts[0] or "tr"
        if len(parts) > 1 and parts[1]:
            opts["scale"] = float(parts[1])
        if len(parts) > 2 and parts[2]:
            opts["start"] = float(parts[2])
        if len(parts) > 3 and parts[3]:
            opts["end"] = float(parts[3])
    return opts


def enhance(src: str, out: str, *, clean: bool = False, bg: str | None = None, effects: list[str] | None = None,
            title: str | None = None, mascot: bool = False, mascot_position: str = "br", mascot_scale: float = 0.28,
            stickers: list[str] | None = None, quality: str = "balanced", log=print) -> dict:
    import background
    import characters
    import fx

    effects = effects or []
    stickers = stickers or []
    if not (clean or bg or effects or title or mascot or stickers):
        raise StudioError("Rien à faire : choisis au moins une option (--clean, --bg, --effects, --mascot, …).")
    steps = ([("fond", 1)] if bg else []) + ([("effets", 1)] if (clean or effects or title) else []) \
        + ([("mascotte", 1)] if mascot else []) + [(f"sticker {i + 1}", 1) for i in range(len(stickers))]
    report = {"steps": [s for s, _ in steps], "warnings": []}
    ensure_parent(out)
    tmpdir = Path(tempfile.mkdtemp(prefix="enhance_", dir=str(Path(out).resolve().parent)))
    cur = src
    try:
        n = 0

        def nxt() -> str:
            nonlocal n
            n += 1
            return str(tmpdir / f"step{n}.mp4")

        if bg:
            log(f"[fond] {bg}")
            o = nxt()
            st = background.replace_background(cur, o, bg, quality="high")
            if st["person_share"] < 0.03:
                report["warnings"].append("Presque aucune personne détectée : le fond n'a pas pu être remplacé proprement.")
            cur = o
        if clean or effects or title:
            log(f"[effets] clean={clean} effets={','.join(effects) or '-'} titre={'oui' if title else 'non'}")
            o = nxt()
            fx.apply(cur, o, effects, clean=clean, title=title, quality="high")
            cur = o
        if mascot:
            log("[mascotte] chacal original, bouche synchronisée à la voix")
            o = nxt()
            characters.add_mascot(cur, o, position=mascot_position, scale=mascot_scale, quality="high")
            cur = o
        for i, spec in enumerate(stickers):
            sp = parse_sticker(spec)
            log(f"[sticker {i + 1}] {sp['image']}")
            o = nxt()
            characters.add_sticker(cur, o, sp["image"], position=sp["position"], scale=sp["scale"], start=sp["start"],
                                   end=sp["end"], quality="high")
            cur = o
        # passage final : encodage à la qualité demandée (une seule fois)
        from common import audio_args, ffmpeg
        crf, preset, abr = QUALITY[quality]
        tmp = temp_sibling(out)
        try:
            ffmpeg(["-i", cur, "-c:v", "libx264", "-preset", preset, "-crf", str(crf), "-profile:v", "high",
                    "-pix_fmt", "yuv420p", *audio_args(abr), "-movflags", "+faststart", str(tmp)])
            finalize(tmp, out)
        finally:
            tmp.unlink(missing_ok=True)
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
    return report


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("input")
    ap.add_argument("-o", "--out", required=True)
    ap.add_argument("--clean", action="store_true", help="nettoyage audio/vidéo + volume")
    ap.add_argument("--bg", default=None, help="blur | color:#RRGGBB | image:fichier | video:fichier")
    ap.add_argument("--effects", default="", help="liste (fx.py --list)")
    ap.add_argument("--title", default=None)
    ap.add_argument("--mascot", action="store_true")
    ap.add_argument("--mascot-position", default="br")
    ap.add_argument("--mascot-scale", type=float, default=0.28)
    ap.add_argument("--sticker", action="append", default=[], help="image[@position,échelle,début,fin] (répétable)")
    ap.add_argument("--quality", default="balanced", choices=list(QUALITY))
    a = ap.parse_args()
    try:
        rep = enhance(a.input, a.out, clean=a.clean, bg=a.bg, effects=[e for e in a.effects.split(",") if e],
                      title=a.title, mascot=a.mascot, mascot_position=a.mascot_position, mascot_scale=a.mascot_scale,
                      stickers=a.sticker, quality=a.quality)
        for w in rep["warnings"]:
            print(f"[attention] {w}")
        print(f"[ok] {a.out}")
    except StudioError as exc:
        die(str(exc))


if __name__ == "__main__":
    main()
