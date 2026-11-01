#!/usr/bin/env python3
# Phenix-video — © 2026 Phenix - kcw. Tous droits réservés (voir LICENSE).
"""Analyse de tendances : étudie des vidéos virales (liens fournis) pour en tirer le STYLE, pas pour les copier.

  trends.py LIEN [LIEN …] -o dossier [--theme "argent"] [--lang fr] [--translate-to en] [--deep]
  trends.py --file liens.txt -o dossier
  trends.py --search "astuces argent" --n 12 -o dossier     (recherche YouTube via yt-dlp, gratuit)
  trends.py --from-json trends.json -o dossier              (ré-analyse des métadonnées déjà récupérées)

Pour chaque vidéo : titre, durée, vues/likes/commentaires, hashtags, heure de publication (métadonnées publiques
lues par yt-dlp, sans compte ni API payante). Avec --deep : télécharge en basse définition et lit l'accroche parlée
(3 à 8 premières secondes) + le rythme de montage.

Sortie : TENDANCES.md (rapport lisible), trends.json (données), idees.md (titres/accroches/hashtags à adapter à TON
sujet, dans ta langue ou traduits). Respect : on s'inspire de la formule (durée, structure d'accroche, rythme,
hashtags). On ne republie pas le contenu d'autrui et on ne copie pas ses textes mot pour mot.
"""
from __future__ import annotations

import argparse
import datetime as dt
import re
import statistics
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from common import StudioError, die, load_json, save_json  # noqa: E402

try:  # mots vides partagés avec publish.py
    from publish import STOP
except Exception:  # pragma: no cover
    STOP = {"fr": set(), "en": set()}

HASHTAG = re.compile(r"#([\wÀ-ɏ]{2,40})", re.UNICODE)
EMOJI = re.compile("[\U0001F300-\U0001FAFF☀-➿]")
GENERIC_REACH = {"fyp", "foryou", "foryoupage", "pourtoi", "viral", "trending", "fy", "xyzbca", "tiktok", "reels", "shorts"}
HOOK_FORMS = [
    ("question", re.compile(r"\?|^(pourquoi|comment|est-ce|why|how|what|who|do you|did you)\b", re.I)),
    ("chiffre / liste", re.compile(r"^\W*(\d+|top\s*\d+)|\b\d+\s+(façons|astuces|raisons|erreurs|ways|tips|reasons|mistakes|things)\b", re.I)),
    ("négation / erreur", re.compile(r"\b(jamais|arrête|stop|never|don'?t|ne fais pas|erreur|mistake|wrong|faux)\b", re.I)),
    ("secret / vérité", re.compile(r"\b(secret|vérité|truth|nobody|personne|caché|hidden|exposed)\b", re.I)),
    ("résultat / avant-après", re.compile(r"\b(avant|après|before|after|résultat|result|j'ai|i (made|tried|got|quit))\b", re.I)),
    ("consigne directe", re.compile(r"^(regarde|écoute|imagine|essaie|look|watch|try|listen|imagine)\b", re.I)),
    ("exclamation / choc", re.compile(r"!|\b(incroyable|fou|insane|crazy|wow|choquant|shocking)\b", re.I)),
]


# --------------------------------------------------------------------------- #
# Récupération des métadonnées
# --------------------------------------------------------------------------- #
def _hashtags(*texts: str | None) -> list[str]:
    seen: list[str] = []
    for t in texts:
        for h in HASHTAG.findall(t or ""):
            h = h.lower()
            if h not in seen:
                seen.append(h)
    return seen


def _entry(info: dict, url: str) -> dict:
    title = (info.get("title") or info.get("fulltitle") or "").strip()
    desc = (info.get("description") or "").strip()
    ts = info.get("timestamp")
    hour = None
    weekday = None
    if ts:
        d_utc = dt.datetime.fromtimestamp(int(ts), tz=dt.timezone.utc)
        hour, weekday = d_utc.hour, d_utc.weekday()
    tags = _hashtags(title, desc) or [t.lower().lstrip("#") for t in (info.get("tags") or [])][:12]
    views = info.get("view_count") or 0
    likes = info.get("like_count") or 0
    comments = info.get("comment_count") or 0
    return {
        "url": info.get("webpage_url") or url, "platform": (info.get("extractor_key") or "").lower(),
        "title": title, "description": desc[:600], "duration": float(info.get("duration") or 0),
        "views": int(views), "likes": int(likes), "comments": int(comments),
        "shares": int(info.get("repost_count") or 0),
        "engagement": round((likes + comments) / views, 4) if views else None,
        "hashtags": tags, "hour_utc": hour, "weekday_utc": weekday, "timestamp": int(ts) if ts else None,
        "upload_date": info.get("upload_date"), "followers": info.get("channel_follower_count"),
        "channel": info.get("channel") or info.get("uploader"),
        "width": info.get("width"), "height": info.get("height"), "fps": info.get("fps"),
    }


def fetch_meta(urls: list[str], search: str | None = None, n: int = 10, cookies: str | None = None) -> list[dict]:
    try:
        import yt_dlp
    except ImportError as exc:
        raise StudioError("yt-dlp n'est pas installé :  pip install yt-dlp") from exc
    opts = {"quiet": True, "no_warnings": True, "skip_download": True, "noplaylist": True, "retries": 3,
            "socket_timeout": 25}
    if cookies:
        opts["cookiesfrombrowser"] = (cookies,)
    out: list[dict] = []
    targets = [f"ytsearch{max(1, min(n, 30))}:{search}"] if search else list(urls)
    with yt_dlp.YoutubeDL(opts) as ydl:
        for u in targets:
            try:
                if search:  # recherche : métadonnées complètes de chaque résultat
                    res = ydl.extract_info(u, download=False)
                    for e in (res or {}).get("entries") or []:
                        if not e:
                            continue
                        try:
                            full = ydl.extract_info(e.get("url") or e.get("webpage_url"), download=False)
                            out.append(_entry(full, e.get("url", "")))
                        except Exception as exc:  # noqa: BLE001
                            print(f"[ignoré] {e.get('title', '?')} : {str(exc)[:90]}", file=sys.stderr)
                else:
                    info = ydl.extract_info(u, download=False)
                    if info and info.get("entries"):
                        info = next((e for e in info["entries"] if e), None)
                    if info:
                        out.append(_entry(info, u))
                        print(f"[ok] {out[-1]['title'][:70]}", file=sys.stderr)
            except Exception as exc:  # noqa: BLE001
                msg = re.sub(r"\x1b\[[0-9;]*m", "", str(exc)).strip().splitlines()[-1][:160]
                print(f"[ignoré] {u[:70]} : {msg}", file=sys.stderr)
    if not out:
        raise StudioError("Aucune métadonnée récupérée : vérifie les liens et la connexion "
                          "(un réseau filtré peut bloquer la plateforme).")
    return out


# --------------------------------------------------------------------------- #
# Analyse approfondie (optionnelle) : accroche parlée + rythme de montage
# --------------------------------------------------------------------------- #
def deep_inspect(entry: dict, work: Path, model: str = "tiny") -> None:
    from fetch import download
    from transcribe import transcribe_whisper
    from common import ffmpeg as _ff
    meta = download(entry["url"], str(work), max_height=480, verbose=False)
    media = meta["path"]
    # rythme : nombre de changements de plan sur les 30 premières secondes
    proc = subprocess.run(["ffmpeg", "-nostdin", "-t", "30", "-i", media, "-vf", "select='gt(scene,0.32)',showinfo",
                           "-an", "-f", "null", "-"], capture_output=True, text=True)
    cuts = len(re.findall(r"pts_time:", proc.stderr))
    span = min(30.0, entry["duration"] or 30.0)
    entry["cuts_per_10s"] = round(cuts * 10.0 / max(span, 1.0), 2)
    # accroche parlée
    try:
        with tempfile.TemporaryDirectory() as tmp:
            head = str(Path(tmp) / "head.m4a")
            _ff(["-i", media, "-t", "8", "-vn", "-ac", "1", "-c:a", "aac", head])
            tr = transcribe_whisper(head, model, None, "cpu", "int8", 1, True, None)
        words = [w for s in tr.get("segments", []) for w in (s.get("words") or [])]
        entry["spoken_hook"] = " ".join(w["w"] for w in words).strip()
        entry["language"] = tr.get("language")
    except StudioError as exc:
        entry["spoken_hook"] = ""
        entry["deep_note"] = str(exc).splitlines()[0]


# --------------------------------------------------------------------------- #
# Analyse
# --------------------------------------------------------------------------- #
def hook_forms(text: str) -> list[str]:
    return [name for name, rx in HOOK_FORMS if rx.search(text or "")]


def guess_lang(text: str) -> str:
    words = re.findall(r"[a-zàâçéèêëîïôûùüÿœ']+", text.lower())
    fr = sum(1 for w in words if w in STOP["fr"])
    en = sum(1 for w in words if w in STOP["en"])
    return "fr" if fr > en else "en"


def _median(xs: list[float]) -> float:
    return float(statistics.median(xs)) if xs else 0.0


def analyse(entries: list[dict]) -> dict:
    ranked = sorted(entries, key=lambda e: (e["views"], e["engagement"] or 0), reverse=True)
    top = ranked[: max(3, len(ranked) // 2)]  # la moitié la plus vue = « modèle »
    durs = [e["duration"] for e in top if e["duration"]]
    buckets = Counter()
    for d in durs:
        buckets["< 15 s" if d < 15 else "15–30 s" if d < 30 else "30–60 s" if d < 60 else "1–3 min" if d < 180 else "> 3 min"] += 1
    tagc: Counter = Counter()
    for e in top:
        tagc.update(h for h in e["hashtags"])
    niche = [(h, c) for h, c in tagc.most_common(40) if h not in GENERIC_REACH]
    reach = [(h, c) for h, c in tagc.most_common(40) if h in GENERIC_REACH]
    forms: Counter = Counter()
    for e in top:
        forms.update(hook_forms(e["title"] + " " + (e.get("spoken_hook") or "")))
    lens = [len(re.sub(HASHTAG, "", e["title"]).strip()) for e in top if e["title"]]
    emoji_share = sum(1 for e in top if EMOJI.search(e["title"])) / max(1, len(top))
    num_share = sum(1 for e in top if re.search(r"\d", e["title"])) / max(1, len(top))
    q_share = sum(1 for e in top if "?" in e["title"]) / max(1, len(top))
    hours = Counter(e["hour_utc"] for e in top if e["hour_utc"] is not None)
    wordc: Counter = Counter()
    for e in top:
        lg = guess_lang(e["title"])
        for w in re.findall(r"[\wÀ-ɏ']{4,}", re.sub(HASHTAG, "", e["title"]).lower()):
            if w not in STOP.get(lg, set()):
                wordc[w] += 1
    cuts = [e["cuts_per_10s"] for e in top if e.get("cuts_per_10s") is not None]
    eng = [e["engagement"] for e in top if e["engagement"] is not None]
    return {
        "count": len(entries), "model_count": len(top),
        "duration_median_s": round(_median(durs), 1), "duration_buckets": dict(buckets),
        "engagement_median": round(_median(eng), 4) if eng else None,
        "title_len_median": int(_median(lens)) if lens else 0,
        "emoji_share": round(emoji_share, 2), "number_share": round(num_share, 2), "question_share": round(q_share, 2),
        "hook_forms": forms.most_common(), "niche_hashtags": niche[:12], "reach_hashtags": reach[:5],
        "top_words": [w for w, _ in wordc.most_common(15)],
        "hours_utc": hours.most_common(4), "cuts_per_10s_median": round(_median(cuts), 2) if cuts else None,
        "ranked": [{"title": e["title"], "views": e["views"], "engagement": e["engagement"], "duration": e["duration"],
                    "url": e["url"], "forms": hook_forms(e["title"])} for e in ranked],
    }


# --------------------------------------------------------------------------- #
# Idées adaptées à TON sujet
# --------------------------------------------------------------------------- #
TEMPLATES = {
    "fr": {
        "question": ["Pourquoi personne ne te dit la vérité sur {t} ?", "{T} : tu fais peut-être cette erreur ?"],
        "chiffre / liste": ["3 erreurs sur {t} qui te coûtent cher", "5 choses à savoir sur {t} avant de commencer"],
        "négation / erreur": ["Arrête de faire ça avec {t}", "Ne fais JAMAIS ça quand tu parles de {t}"],
        "secret / vérité": ["Le secret sur {t} que personne ne montre", "La vérité sur {t} (ce qu'on ne te dit pas)"],
        "résultat / avant-après": ["J'ai testé {t} pendant 7 jours : voici le résultat", "Avant / après : {t}"],
        "consigne directe": ["Regarde ça avant de te lancer dans {t}", "Écoute bien : {t} en 30 secondes"],
        "exclamation / choc": ["{T} : c'est vraiment fou !", "Incroyable : ce qu'on ignore sur {t}"],
    },
    "en": {
        "question": ["Why nobody tells you the truth about {t}?", "{T}: are you making this mistake?"],
        "chiffre / liste": ["3 {t} mistakes that cost you money", "5 things to know about {t} before you start"],
        "négation / erreur": ["Stop doing this with {t}", "Never do this when it comes to {t}"],
        "secret / vérité": ["The {t} secret nobody shows you", "The truth about {t} (what they don't tell you)"],
        "résultat / avant-après": ["I tried {t} for 7 days: here's the result", "Before / after: {t}"],
        "consigne directe": ["Watch this before you start {t}", "Listen up: {t} in 30 seconds"],
        "exclamation / choc": ["{T} is insane!", "Unbelievable: what most people miss about {t}"],
    },
}


def ideas(stats: dict, theme: str, lang: str) -> dict:
    lang = lang if lang in TEMPLATES else "en"
    t = re.sub(r"^(l'|d'|le |la |les |un |une |the |a |an )", "", theme.strip(), flags=re.I).strip()
    t = t or ("ton sujet" if lang == "fr" else "your topic")
    forms = [f for f, _ in stats["hook_forms"]] or ["question", "chiffre / liste", "secret / vérité"]
    titles: list[str] = []
    for f in forms[:4]:
        for tpl in TEMPLATES[lang].get(f, [])[:2]:
            titles.append(tpl.format(t=t, T=t[:1].upper() + t[1:]))
    base_tags = [h for h, _ in stats["niche_hashtags"]][:6]
    mine = re.sub(r"\W+", "", t.lower())
    tags = ([f"#{mine}"] if mine else []) + [f"#{h}" for h in base_tags if h != mine][:5]
    tags += [f"#{h}" for h, _ in stats["reach_hashtags"][:1]]
    dur = stats["duration_median_s"]
    return {"titles": titles, "hashtags": tags, "target_duration_s": dur, "theme": t,
            "structure": [
                "0–3 s : accroche qui montre le résultat ou pose la question (une des formes dominantes ci-dessus)",
                "3–" + str(int(max(10, dur * 0.8))) + " s : 2 ou 3 preuves/étapes courtes, un plan nouveau toutes les "
                + (f"{10 / stats['cuts_per_10s_median']:.1f} s" if stats.get("cuts_per_10s_median") else "3 à 4 s"),
                "fin : chute ou reprise du mot de l'accroche (incite à rejouer) + appel à commenter",
            ]}


def maybe_translate(items: list[str], src: str, dst: str) -> list[str]:
    if not dst or dst == src or not items:
        return items
    try:
        from translate import argos_translate
        return argos_translate(items, src, dst)
    except Exception as exc:  # noqa: BLE001
        print(f"[traduction] ignorée : {str(exc).splitlines()[0][:120]}", file=sys.stderr)
        return items


# --------------------------------------------------------------------------- #
# Rapport
# --------------------------------------------------------------------------- #
def fmt_n(n: int) -> str:
    return f"{n / 1e6:.1f} M" if n >= 1e6 else f"{n / 1e3:.1f} k" if n >= 1e3 else str(n)


def report(stats: dict, idea: dict, entries: list[dict]) -> str:
    L = ["# Tendances — analyse de vidéos virales", "",
         f"{stats['count']} vidéos analysées ; modèle = la moitié la plus vue ({stats['model_count']}). "
         "Ce sont des **corrélations observées**, pas des garanties : une vidéo virale réussit aussi grâce à son "
         "contenu, son compte et son moment.", "",
         "## Formule dominante",
         f"- Durée médiane : **{stats['duration_median_s']} s** — répartition : "
         + (", ".join(f"{k} ×{v}" for k, v in stats["duration_buckets"].items()) or "n/a"),
         f"- Engagement médian (likes + commentaires / vues) : **"
         + (f"{stats['engagement_median'] * 100:.1f} %" if stats["engagement_median"] is not None else "n/a") + "**",
         f"- Titre : ~{stats['title_len_median']} caractères ; chiffre dans {int(stats['number_share'] * 100)} % ; "
         f"question dans {int(stats['question_share'] * 100)} % ; emoji dans {int(stats['emoji_share'] * 100)} %"]
    if stats.get("cuts_per_10s_median") is not None:
        L.append(f"- Rythme de montage : ~{stats['cuts_per_10s_median']} changements de plan / 10 s")
    L += ["", "## Formes d'accroche les plus fréquentes"]
    L += [f"- {name} ({c})" for name, c in stats["hook_forms"]] or ["- (pas assez de données)"]
    L += ["", "## Hashtags", "- Niche : " + (" ".join(f"#{h} ({c})" for h, c in stats["niche_hashtags"]) or "n/a"),
          "- Portée : " + (" ".join(f"#{h}" for h, _ in stats["reach_hashtags"]) or "n/a"),
          "", "## Mots qui reviennent dans les titres", ", ".join(stats["top_words"]) or "n/a"]
    if stats["hours_utc"]:
        L += ["", "## Heures de publication (UTC) des vidéos modèles",
              ", ".join(f"{h:02d}h ×{c}" for h, c in stats["hours_utc"]),
              "(Burkina Faso = UTC, donc identique. Vérifie surtout les statistiques de TON audience.)"]
    L += ["", "## Classement"]
    for i, r in enumerate(stats["ranked"][:15], 1):
        eng = f"{r['engagement'] * 100:.1f} %" if r["engagement"] is not None else "–"
        L.append(f"{i}. {fmt_n(r['views'])} vues · eng. {eng} · {int(r['duration'])} s — {r['title'][:90]}  \n   {r['url']}")
    spoken = [e for e in entries if e.get("spoken_hook")]
    if spoken:
        L += ["", "## Accroches parlées relevées (à t'inspirer de la forme, pas de la copier)"]
        L += [f"- « {e['spoken_hook'][:140]} »" for e in spoken[:10]]
    L += ["", "## À retenir pour ton prochain clip",
          f"- Viser environ {idea['target_duration_s']} s", *[f"- {s}" for s in idea["structure"]],
          "", "Idées de titres, accroches et hashtags : voir `idees.md`."]
    return "\n".join(L) + "\n"


def ideas_md(idea: dict, translated: list[str] | None, dst: str | None) -> str:
    L = [f"# Idées pour : {idea['theme']}", "", "Titres/accroches à adapter avec tes propres mots :", ""]
    L += [f"- {t}" for t in idea["titles"]]
    if translated and dst:
        L += ["", f"## Traduction ({dst}) — relis avant d'utiliser", ""]
        L += [f"- {t}" for t in translated]
    L += ["", "## Hashtags suggérés", " ".join(idea["hashtags"]), "",
          "## Structure conseillée", *[f"- {s}" for s in idea["structure"]], "",
          "## Rappel", "- Fais ton propre contenu : n'utilise pas les images, voix ou textes d'un autre créateur sans autorisation.",
          "- Voix de synthèse = active l'étiquette « contenu généré par IA »."]
    return "\n".join(L) + "\n"


def run(urls: list[str], out_dir: str, *, theme: str = "", lang: str = "fr", translate_to: str | None = None,
        deep: bool = False, search: str | None = None, n: int = 10, from_json: str | None = None,
        cookies: str | None = None, max_deep: int = 6) -> Path:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    if from_json:
        data = load_json(from_json)
        entries = data["entries"] if isinstance(data, dict) else data
    else:
        if not urls and not search:
            raise StudioError("Donne au moins un lien, un fichier de liens (--file) ou une recherche (--search).")
        entries = fetch_meta(urls, search, n, cookies)
    if deep and not from_json:
        work = out / "_tmp"
        for e in sorted(entries, key=lambda x: x["views"], reverse=True)[:max_deep]:
            try:
                print(f"[approfondi] {e['title'][:60]}", file=sys.stderr)
                deep_inspect(e, work)
            except StudioError as exc:
                e["deep_note"] = str(exc).splitlines()[0]
                print(f"[approfondi ignoré] {e['deep_note'][:120]}", file=sys.stderr)
            except Exception as exc:  # noqa: BLE001
                e["deep_note"] = str(exc)[:120]
        import shutil
        shutil.rmtree(work, ignore_errors=True)
    stats = analyse(entries)
    idea = ideas(stats, theme, lang)
    tr = maybe_translate(idea["titles"], lang, translate_to) if translate_to else None
    save_json(out / "trends.json", {"entries": entries, "stats": stats, "ideas": idea})
    (out / "TENDANCES.md").write_text(report(stats, idea, entries), encoding="utf-8")
    (out / "idees.md").write_text(ideas_md(idea, tr, translate_to), encoding="utf-8")
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("urls", nargs="*")
    ap.add_argument("-o", "--out", required=True)
    ap.add_argument("--file", help="fichier texte : un lien par ligne")
    ap.add_argument("--search", help="recherche YouTube (yt-dlp) au lieu de liens")
    ap.add_argument("--n", type=int, default=10, help="résultats de recherche (≤ 30)")
    ap.add_argument("--theme", default="", help="TON sujet (pour générer des idées)")
    ap.add_argument("--lang", default="fr", choices=["fr", "en"], help="langue des idées")
    ap.add_argument("--translate-to", default=None, help="traduire les titres proposés (fr|en|es|pt|de|ar)")
    ap.add_argument("--deep", action="store_true", help="télécharge en basse définition : accroche parlée + rythme")
    ap.add_argument("--max-deep", type=int, default=6)
    ap.add_argument("--from-json", help="ré-analyse un trends.json existant (sans réseau)")
    ap.add_argument("--cookies-from-browser", default=None)
    a = ap.parse_args()
    urls = list(a.urls)
    if a.file:
        urls += [l.strip() for l in Path(a.file).read_text(encoding="utf-8").splitlines()
                 if l.strip().startswith(("http://", "https://"))]
    try:
        d = run(urls, a.out, theme=a.theme, lang=a.lang, translate_to=a.translate_to, deep=a.deep, search=a.search,
                n=a.n, from_json=a.from_json, cookies=a.cookies_from_browser, max_deep=a.max_deep)
        print(f"[ok] rapport : {d / 'TENDANCES.md'}  ·  idées : {d / 'idees.md'}")
    except StudioError as exc:
        die(str(exc))


if __name__ == "__main__":
    main()
