#!/usr/bin/env python3
# Phenix-video — © 2026 Phenix - kcw. Tous droits réservés (voir LICENSE).
"""Prépare un dossier « prêt à publier » par clip : vidéo, miniature, titre, description, hashtags.

  publish.py out/                 (dossier produit par pipeline.py, avec report.json)
  publish.py out/ --handle @anubislabs --lang fr

Pour chaque clip : `publish/NN_slug/` avec video.mp4, cover.jpg (si elle existe), youtube.txt, tiktok.txt,
metadata.json, et un `publish/INDEX.md`. Tout est local et sans API ; relis et réécris les titres avant d'envoyer.
Titres, descriptions et hashtags sont des PROPOSITIONS générées d'après la transcription : aucune garantie de portée.
"""
from __future__ import annotations

import argparse
import re
import shutil
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from common import StudioError, die, load_json, save_json, slugify  # noqa: E402

STOP = {
    "fr": set("""le la les un une des du de d l et ou mais donc or ni car que qui quoi dont où ce cet cette ces mon ton son
        ma ta sa mes tes ses notre votre leur nos vos leurs je tu il elle on nous vous ils elles me te se lui y en à au aux
        avec sans pour par sur sous dans entre vers chez très plus moins aussi alors comme si ne pas jamais rien tout tous
        toute toutes est sont suis es sommes êtes été être avoir a ai as avons avez ont fait faire peut peux cela ça c
        cest qu quil quon j m n s t voilà voila bien même mêmes donc encore déjà""".split()),
    "en": set("""the a an and or but so nor for yet that this these those my your his her its our their i you he she it we they
        me him us them to of in on at by with from as is are was were be been being have has had do does did not no
        yes just very more most also than then there here what which who whom whose when where why how all any each
        some can could will would should may might must about into over out up down off if because while like get
        got going thing things really actually people want need know does doesn dont didn isn aren wasn weren every
        everyone anyone someone something anything everything nothing these those would their there where which
        being other another always never often still every through between before after""".split()),
}
GENERIC_TAGS = {"fr": ["#astuce", "#conseils"], "en": ["#tips", "#learn"]}


def pick_transcript(out_dir: Path, clip_file: str) -> dict | None:
    stem = Path(clip_file).with_suffix("")
    for cand in (Path(str(stem) + ".transcript.json"), out_dir / (stem.name + ".transcript.json"),
                 out_dir / (re.sub(r"_[FM]$", "", stem.name) + ".tight.transcript.json")):
        if cand.is_file():
            try:
                return load_json(cand)
            except (OSError, ValueError):
                continue
    return None


def sentences(tr: dict) -> list[str]:
    text = " ".join(s.get("text", "").strip() for s in tr.get("segments", []))
    parts = [p.strip() for p in re.split(r"(?<=[.!?…])\s+", text) if len(p.strip()) > 25]
    return parts


def keywords(text: str, lang: str, n: int = 4) -> list[str]:
    stop = STOP.get(lang, STOP["en"])
    tokens = re.findall(r"[A-Za-zÀ-ÿ]+(?:['’][A-Za-zÀ-ÿ]+)*", text)
    words = [w.lower() for w in tokens if len(w) >= 5 and "'" not in w and "’" not in w]
    cnt = Counter(w for w in words if w not in stop)
    return [w for w, _ in cnt.most_common(n)]


def clamp(text: str, n: int) -> str:
    text = " ".join(text.split())
    return text if len(text) <= n else text[: n - 1].rsplit(" ", 1)[0].rstrip(",;:-") + "…"


def hashtag(word: str) -> str:
    import unicodedata
    w = unicodedata.normalize("NFKD", word).encode("ascii", "ignore").decode()
    return "#" + re.sub(r"[^A-Za-z0-9]", "", w)


def build_meta(clip: dict, tr: dict | None, lang: str, handle: str | None) -> dict:
    title = clamp(clip.get("title") or "Extrait", 60)
    sents = sentences(tr) if tr else []
    summary = clamp(" ".join(sents[:2]), 220) if sents else ""
    kws = keywords(" ".join(sents) if sents else title, lang)
    tags = [hashtag(k) for k in kws[:3]] + GENERIC_TAGS.get(lang, GENERIC_TAGS["en"])[:1]
    tags = list(dict.fromkeys(t for t in tags if len(t) > 3))[:5]
    ai_line = {"fr": "Voix off générée par IA (voix de synthèse).",
               "en": "Voiceover generated with AI (synthetic voice)."}.get(lang, "AI-generated voiceover.") \
        if clip.get("synthetic_voice") else ""
    desc_parts = [summary, ai_line, f"Crédit : {handle}" if handle else "", " ".join(tags)]
    return {
        "title": title,
        "description": "\n\n".join(p for p in desc_parts if p),
        "hashtags": tags,
        "synthetic_voice": bool(clip.get("synthetic_voice")),
        "duration_s": clip.get("duration"),
        "keywords": kws,
    }


def run(out_dir: str, *, lang: str | None = None, handle: str | None = None) -> Path:
    base = Path(out_dir)
    rep_path = next((p for p in (base / "report.json", base / "out" / "report.json") if p.is_file()), None)
    if not rep_path:
        raise StudioError(f"report.json introuvable dans {base} : lance d'abord pipeline.py.")
    base = rep_path.parent
    rep = load_json(rep_path)
    clips = [c for c in rep.get("clips", []) if c.get("status") == "ok" and c.get("file")]
    if not clips:
        raise StudioError("Aucun clip rendu dans ce rapport.")
    dest = base / "publish"
    dest.mkdir(exist_ok=True)
    index = ["# Dossier de publication", "",
             "Propositions automatiques : relis, adapte le titre et vérifie les règles actuelles de chaque plateforme.", ""]
    for i, clip in enumerate(clips, 1):
        f = Path(clip["file"])
        if not f.is_file():
            f = base / f.name
        if not f.is_file():
            continue
        tr = pick_transcript(base, str(f))
        lg = lang or (tr or {}).get("language") or "fr"
        meta = build_meta(clip, tr, lg if lg in STOP else "en", handle)
        folder = dest / f"{i:02d}_{slugify(meta['title'], 30)}{('_' + f.stem[-1]) if re.search(r'_[FM]$', f.stem) else ''}"
        folder.mkdir(exist_ok=True)
        shutil.copy2(f, folder / "video.mp4")
        cover = f.with_suffix(".jpg")
        if cover.is_file():
            shutil.copy2(cover, folder / "cover.jpg")
        yt_title = meta["title"] + (" #Shorts" if (clip.get("duration") or 0) <= 180 and len(meta["title"]) <= 50 else "")
        (folder / "youtube.txt").write_text(
            f"TITRE (≤ 100) :\n{clamp(yt_title, 100)}\n\nDESCRIPTION :\n{meta['description']}\n\n"
            "RÉGLAGES À COCHER DANS YOUTUBE STUDIO :\n- Contenu modifié ou synthétique : "
            f"{'OUI (voix de synthèse)' if meta['synthetic_voice'] else 'à vérifier'}\n- Destiné aux enfants : non (sauf si c'est le cas)\n",
            encoding="utf-8")
        (folder / "tiktok.txt").write_text(
            clamp(f"{meta['title']} {' '.join(meta['hashtags'])}", 2200) + "\n\n"
            "RÉGLAGES DANS TIKTOK :\n- Activer « Contenu généré par IA » si une voix ou une image de synthèse réaliste est utilisée\n"
            "- Choisir la miniature (cover.jpg) ; ne pas republier de contenu sans droits\n", encoding="utf-8")
        save_json(folder / "metadata.json", meta)
        index.append(f"## {i}. {meta['title']}\n- Dossier : `{folder.name}`\n- Hashtags : {' '.join(meta['hashtags'])}\n"
                     f"- Durée : {meta['duration_s']} s\n")
    index += ["", "## Horaire de publication", "Indicatif : début de soirée heure locale de ton public. Vérifie dans les "
              "statistiques de ton compte (heures d'activité des abonnés) : c'est la seule source fiable.", "",
              "## Après publication", "Regarde la durée moyenne de visionnage et la rétention à 24–48 h ; "
              "refais les accroches qui décrochent dans les 3 premières secondes."]
    (dest / "INDEX.md").write_text("\n".join(index), encoding="utf-8")
    return dest


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("out_dir")
    ap.add_argument("--lang", default=None, help="langue des textes (fr|en), sinon celle de la transcription")
    ap.add_argument("--handle", default=None, help="crédit/compte à mentionner (@nom)")
    a = ap.parse_args()
    try:
        d = run(a.out_dir, lang=a.lang, handle=a.handle)
        print(f"[ok] dossier de publication : {d}")
    except StudioError as exc:
        die(str(exc))


if __name__ == "__main__":
    main()
