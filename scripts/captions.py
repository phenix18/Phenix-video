#!/usr/bin/env python3
# Phenix-video — © 2026 Phenix - kcw. Tous droits réservés (voir LICENSE).
"""Sous-titres animés mot par mot (styles pop, karaoké, bandeau, minimal) au format ASS.

Le fichier .ass est brûlé dans la vidéo par ffmpeg (filtre `ass`), sans service externe.

Styles :
  pop      MAJUSCULES, 1-3 mots, mot actif en couleur, petite animation d'apparition (style Hormozi)
  karaoke  phrase de 4-7 mots, remplissage progressif du mot en cours
  clean    2 lignes blanches sur bandeau semi-transparent, sans surbrillance
  minimal  texte blanc fin avec ombre, discret (interviews, podcasts)

Exemples :
  captions.py transcript.json -o clip1.ass --start 120.5 --end 160.2 --style pop --size 1080x1920
"""
from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from common import StudioError, die, fmt_ass, load_json, parse_size  # noqa: E402


def ass_color(hex_rgb: str, alpha: int = 0) -> str:
    """'#FFD400' -> '&H0000D4FF' (ASS est en BGR avec alpha en tête)."""
    h = hex_rgb.lstrip("#")
    if len(h) != 6:
        raise StudioError(f"Couleur invalide : {hex_rgb!r} (attendu #RRGGBB)")
    r, g, b = h[0:2], h[2:4], h[4:6]
    return f"&H{alpha:02X}{b}{g}{r}".upper()


@dataclass
class Style:
    name: str
    font: str
    size_ratio: float      # taille de police / hauteur de la vidéo
    bold: bool
    uppercase: bool
    primary: str
    highlight: str
    outline_color: str
    outline_ratio: float   # épaisseur de contour / taille de police
    shadow: float
    box: bool              # fond opaque derrière le texte
    max_words: int
    max_chars: int
    alignment: int         # 2 = bas centre, 5 = milieu centre, 8 = haut centre
    margin_ratio: float    # marge verticale / hauteur
    animate: bool
    karaoke: bool


STYLES = {
    "pop": Style("pop", "Inter", 0.056, True, True, "#FFFFFF", "#FFD400", "#000000", 0.13, 0, False,
                 3, 16, 2, 0.30, True, False),
    "karaoke": Style("karaoke", "Inter", 0.048, True, False, "#FFFFFF", "#22E06B", "#000000", 0.12, 1, False,
                     7, 30, 2, 0.26, False, True),
    "clean": Style("clean", "Inter", 0.040, True, False, "#FFFFFF", "#FFFFFF", "#000000", 0.0, 0, True,
                   7, 34, 2, 0.22, False, False),
    "minimal": Style("minimal", "Inter", 0.036, False, False, "#FFFFFF", "#FFFFFF", "#000000", 0.07, 1.5, False,
                     8, 38, 2, 0.12, False, False),
}


# --------------------------------------------------------------------------- #
# Sélection des mots d'un clip
# --------------------------------------------------------------------------- #
def clip_words(transcript: dict, start: float, end: float) -> list[dict]:
    out = []
    for seg in transcript["segments"]:
        if seg["end"] < start or seg["start"] > end:
            continue
        for w in seg.get("words") or []:
            if w["end"] <= start or w["start"] >= end:
                continue
            out.append({"w": w["w"], "start": max(w["start"], start) - start,
                        "end": min(w["end"], end) - start})
    return out


def clean_token(token: str, upper: bool) -> str:
    token = token.strip()
    token = re.sub(r"[{}\\]", "", token)  # ces caractères casseraient les balises ASS
    return token.upper() if upper else token


def group_words(words: list[dict], max_words: int, max_chars: int, pause: float = 0.35) -> list[list[dict]]:
    groups: list[list[dict]] = []
    cur: list[dict] = []
    chars = 0
    for i, w in enumerate(words):
        token_len = len(w["w"]) + 1
        if cur and (len(cur) >= max_words or chars + token_len > max_chars):
            groups.append(cur); cur, chars = [], 0
        cur.append(w)
        chars += token_len
        nxt = words[i + 1] if i + 1 < len(words) else None
        sentence_end = w["w"].endswith((".", "!", "?", "…"))
        long_pause = nxt is not None and nxt["start"] - w["end"] > pause
        if sentence_end or long_pause:
            groups.append(cur); cur, chars = [], 0
    if cur:
        groups.append(cur)
    return groups


# --------------------------------------------------------------------------- #
# Génération ASS
# --------------------------------------------------------------------------- #
def ass_header(style: Style, width: int, height: int, font: str, hl_override: str | None) -> str:
    size = max(24, int(round(height * style.size_ratio)))
    outline = round(size * style.outline_ratio, 1)
    margin_v = int(round(height * style.margin_ratio))
    margin_h = int(round(width * 0.06))
    primary = ass_color(style.primary)
    secondary = ass_color(hl_override or style.highlight)
    outline_col = ass_color(style.outline_color)
    back = ass_color("#000000", alpha=0x66 if style.box else 0x00)
    border_style = 3 if style.box else 1
    bold = -1 if style.bold else 0
    if style.box:
        outline = round(size * 0.28, 1)  # avec BorderStyle=3 l'outline sert de marge du bandeau
    return (
        "[Script Info]\n"
        "ScriptType: v4.00+\n"
        f"PlayResX: {width}\nPlayResY: {height}\n"
        "WrapStyle: 2\nScaledBorderAndShadow: yes\n\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
        "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
        "Alignment, MarginL, MarginR, MarginV, Encoding\n"
        f"Style: Main,{font},{size},{primary},{secondary},{outline_col},{back},{bold},0,0,0,100,100,0,0,"
        f"{border_style},{outline},{style.shadow},{style.alignment},{margin_h},{margin_h},{margin_v},1\n\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )


def build_ass(words: list[dict], style_name: str, width: int, height: int,
              font: str | None = None, highlight: str | None = None) -> str:
    if style_name not in STYLES:
        raise StudioError(f"Style inconnu : {style_name}. Choix : {', '.join(STYLES)}")
    style = STYLES[style_name]
    head = ass_header(style, width, height, font or style.font, highlight)
    hl = ass_color(highlight or style.highlight)
    base = ass_color(style.primary)
    lines: list[str] = []
    groups = group_words(words, style.max_words, style.max_chars)

    for g_idx, group in enumerate(groups):
        group_end = group[-1]["end"]
        next_start = groups[g_idx + 1][0]["start"] if g_idx + 1 < len(groups) else group_end + 0.4
        hold_end = min(group_end + 0.25, next_start)  # reste un peu à l'écran sans chevaucher

        if style.karaoke:
            parts = []
            for k, w in enumerate(group):
                nxt_start = group[k + 1]["start"] if k + 1 < len(group) else hold_end
                cs = max(1, int(round((nxt_start - w["start"]) * 100)))
                parts.append(f"{{\\kf{cs}}}{clean_token(w['w'], style.uppercase)}")
            text = " ".join(parts)
            lines.append(f"Dialogue: 0,{fmt_ass(group[0]['start'])},{fmt_ass(hold_end)},Main,,0,0,0,,{text}")
            continue

        if style.name in ("pop",):
            # un événement par mot : le mot actif est coloré, les autres restent blancs
            for k, w in enumerate(group):
                ev_start = w["start"]
                ev_end = group[k + 1]["start"] if k + 1 < len(group) else hold_end
                if ev_end - ev_start < 0.06:
                    ev_end = ev_start + 0.06
                tokens = []
                for m, other in enumerate(group):
                    tok = clean_token(other["w"], style.uppercase)
                    tokens.append(f"{{\\c{hl}}}{tok}{{\\c{base}}}" if m == k else tok)
                anim = "{\\fscx85\\fscy85\\t(0,90,\\fscx100\\fscy100)}" if style.animate else ""
                lines.append(
                    f"Dialogue: 0,{fmt_ass(ev_start)},{fmt_ass(ev_end)},Main,,0,0,0,,{anim}{' '.join(tokens)}")
            continue

        # clean / minimal : phrase fixe, apparition en fondu court
        text = " ".join(clean_token(w["w"], style.uppercase) for w in group)
        if len(text) > style.max_chars * 0.6:  # coupe en deux lignes équilibrées
            half = len(text) // 2
            cut = text.rfind(" ", 0, half + 6)
            if cut > 0:
                text = text[:cut] + "\\N" + text[cut + 1:]
        lines.append(f"Dialogue: 0,{fmt_ass(group[0]['start'])},{fmt_ass(hold_end)},Main,,0,0,0,,{{\\fad(80,60)}}{text}")

    return head + "\n".join(lines) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("transcript")
    ap.add_argument("-o", "--out", required=True, help="fichier .ass de sortie")
    ap.add_argument("--start", type=float, default=0.0, help="début du clip dans la source (s)")
    ap.add_argument("--end", type=float, default=None, help="fin du clip (s) ; défaut : fin du transcript")
    ap.add_argument("--style", default="pop", choices=list(STYLES))
    ap.add_argument("--size", default="1080x1920", help="résolution de la vidéo finale")
    ap.add_argument("--font", default=None, help="police installée (défaut Inter ; sinon Arial, DejaVu Sans…)")
    ap.add_argument("--highlight", default=None, help="couleur du mot actif, ex. #FF3B30")
    args = ap.parse_args()
    try:
        data = load_json(args.transcript)
        end = args.end if args.end is not None else float(data.get("duration") or 1e9)
        words = clip_words(data, args.start, end)
        if not words:
            raise StudioError("Aucun mot dans cet intervalle : rien à sous-titrer.")
        w, h = parse_size(args.size)
        Path(args.out).write_text(build_ass(words, args.style, w, h, args.font, args.highlight), encoding="utf-8")
        print(f"[ok] {len(words)} mots, style {args.style} -> {args.out}")
    except StudioError as exc:
        die(str(exc))


if __name__ == "__main__":
    main()
