#!/usr/bin/env python3
# Phenix-video — © 2026 Phenix - kcw. Tous droits réservés (voir LICENSE).
"""Traduction d'un transcript (EN↔FR et autres) sans API payante.

Trois moteurs :
  argos   hors-ligne (pip install argostranslate) ; télécharge le modèle de la paire de langues au 1er usage
  manual  export/import JSON : Claude (ou toi) traduit les phrases, le script remet les horodatages
          -> meilleure qualité, adapté aux contenus où le ton compte
  copy    ne traduit pas (tests)

Sortie : un transcript au même format que transcribe.py, découpé en phrases ("unités"), avec
  "text" traduit, "src_text" d'origine, et des mots horodatés ESTIMÉS (répartis dans la phrase),
  directement utilisables par captions.py (sous-titres traduits) et dub.py (voix off).

Exemples :
  translate.py transcript.json --to fr -o transcript.fr.json
  translate.py transcript.json --to en --start 120 --end 210 -o clip.en.json
  translate.py transcript.json --to fr --engine manual --export phrases.json
  # ... traduction de phrases.json -> traduit.json ([{"id":0,"text":"..."}]) ...
  translate.py transcript.json --to fr --engine manual --import traduit.json -o transcript.fr.json
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from common import StudioError, die, load_json, save_json  # noqa: E402
from highlights import Unit, build_units  # noqa: E402


# --------------------------------------------------------------------------- #
# Unités de traduction / doublage
# --------------------------------------------------------------------------- #
def merge_short(units: list[Unit], min_len: float = 1.6, max_len: float = 14.0, gap: float = 0.5) -> list[Unit]:
    """Fusionne les phrases très courtes avec la suivante : une voix off naturelle évite les micro-segments."""
    out: list[Unit] = []
    for u in units:
        if out and (out[-1].end - out[-1].start) < min_len and (u.start - out[-1].end) < gap \
                and (u.end - out[-1].start) <= max_len:
            prev = out[-1]
            out[-1] = Unit(prev.start, u.end, prev.text + " " + u.text, prev.words + u.words)
        else:
            out.append(u)
    return out


def select_units(transcript: dict, start: float | None, end: float | None) -> list[Unit]:
    units = merge_short(build_units(transcript))
    if start is None and end is None:
        return units
    lo = start if start is not None else 0.0
    hi = end if end is not None else float("inf")
    kept = []
    for u in units:
        centre = (u.start + u.end) / 2
        if lo <= centre <= hi:
            kept.append(Unit(max(u.start, lo), min(u.end, hi), u.text, u.words))
    if not kept:
        raise StudioError("Aucune phrase dans l'intervalle demandé.")
    return kept


def spread_words(text: str, start: float, end: float) -> list[dict]:
    """Répartit les mots d'un texte traduit dans [start, end] proportionnellement à leur longueur."""
    tokens = text.split()
    if not tokens:
        return []
    weights = [len(t.strip(".,;:!?…")) + 1.5 for t in tokens]
    total = sum(weights)
    cursor, out = start, []
    for tok, wgt in zip(tokens, weights):
        span = (end - start) * wgt / total
        out.append({"w": tok, "start": round(cursor, 3), "end": round(cursor + span, 3), "p": 0.5,
                    "estimated": True})
        cursor += span
    return out


# --------------------------------------------------------------------------- #
# Moteur Argos (hors-ligne)
# --------------------------------------------------------------------------- #
def argos_translate(texts: list[str], src: str, dst: str) -> list[str]:
    try:
        import argostranslate.package as pkg
        import argostranslate.translate as tr
    except ImportError as exc:
        raise StudioError(
            "argostranslate n'est pas installé :  pip install argostranslate\n"
            "Alternative sans installation : --engine manual (Claude traduit les phrases exportées)."
        ) from exc

    def installed(a: str, b: str) -> bool:
        langs = {l.code: l for l in tr.get_installed_languages()}
        return a in langs and b in langs and langs[a].get_translation(langs[b]) is not None

    def install_pair(a: str, b: str) -> None:
        pkg.update_package_index()
        found = next((p for p in pkg.get_available_packages() if p.from_code == a and p.to_code == b), None)
        if not found:
            raise StudioError(f"Argos n'a pas de modèle direct {a}→{b}.")
        print(f"[traduction] téléchargement du modèle {a}→{b} (une seule fois)…", file=sys.stderr)
        pkg.install_from_path(found.download())

    if not installed(src, dst):
        try:
            install_pair(src, dst)
        except StudioError:
            # pas de modèle direct : on passe par l'anglais
            if "en" in (src, dst):
                raise
            for a, b in ((src, "en"), ("en", dst)):
                if not installed(a, b):
                    install_pair(a, b)
        except Exception as exc:  # réseau, disque…
            raise StudioError(f"Téléchargement du modèle Argos impossible : {exc}") from exc
    out = []
    for i, text in enumerate(texts):
        out.append(tr.translate(text, src, dst))
        print(f"\r[traduction] {i + 1}/{len(texts)}", end="", file=sys.stderr)
    print(file=sys.stderr)
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("transcript")
    ap.add_argument("--to", dest="dst", required=True, help="langue cible : fr, en, es, ar, pt…")
    ap.add_argument("--from", dest="src", default=None, help="langue source (défaut : celle du transcript)")
    ap.add_argument("--start", type=float, default=None)
    ap.add_argument("--end", type=float, default=None)
    ap.add_argument("--engine", default="argos", choices=["argos", "manual", "copy"])
    ap.add_argument("--export", default=None, help="(manual) écrit les phrases à traduire dans ce JSON et s'arrête")
    ap.add_argument("--import", dest="imp", default=None, help="(manual) JSON [{id,text}] traduit")
    ap.add_argument("-o", "--out", default=None)
    args = ap.parse_args()
    try:
        data = load_json(args.transcript)
        src = (args.src or data.get("language") or "").lower()
        units = select_units(data, args.start, args.end)

        if args.engine == "manual" and args.export:
            save_json(args.export, [{"id": i, "start": round(u.start, 2), "end": round(u.end, 2),
                                     "max_words_hint": max(3, int((u.end - u.start) * 3.0)), "text": u.text}
                                    for i, u in enumerate(units)])
            print(f"[ok] {len(units)} phrases à traduire en '{args.dst}' -> {args.export}\n"
                  "Garde le même 'id' ; vise la durée de la phrase d'origine (voir max_words_hint) pour que la voix off tienne.")
            return

        if args.engine == "manual":
            if not args.imp:
                raise StudioError("--engine manual : utilise --export puis --import.")
            tr_items = {int(i["id"]): str(i["text"]).strip() for i in load_json(args.imp)}
            missing = [i for i in range(len(units)) if i not in tr_items or not tr_items[i]]
            if missing:
                raise StudioError(f"Traductions manquantes pour les id : {missing[:10]}")
            texts = [tr_items[i] for i in range(len(units))]
        elif args.engine == "copy":
            texts = [u.text for u in units]
        else:
            if not src or src == "und":
                raise StudioError("Langue source inconnue : ajoute --from fr|en|…")
            if src == args.dst.lower():
                raise StudioError("Langue source et cible identiques.")
            texts = argos_translate([u.text for u in units], src, args.dst.lower())

        segments = []
        for i, (u, text) in enumerate(zip(units, texts)):
            segments.append({"id": i, "start": round(u.start, 3), "end": round(u.end, 3), "text": text,
                             "src_text": u.text, "words": spread_words(text, u.start, u.end)})
        out = args.out or str(Path(args.transcript).with_suffix("")) + f".{args.dst}.json"
        save_json(out, {"language": args.dst.lower(), "source_language": src or None,
                        "duration": data.get("duration"), "engine": f"translate:{args.engine}",
                        "segments": segments})
        print(f"[ok] {len(segments)} phrases {src or '?'}→{args.dst} -> {out}")
    except StudioError as exc:
        die(str(exc))


if __name__ == "__main__":
    main()
