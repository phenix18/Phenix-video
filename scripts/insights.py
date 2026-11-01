#!/usr/bin/env python3
# Phenix-video — © 2026 Phenix - kcw. Tous droits réservés (voir LICENSE).
"""Analyse de profil, recherche de niches et planning de publication — données publiques, sans API payante.

  insights.py profile LIEN_DU_PROFIL -o dossier [--n 25] [--tz 0] [--per-week 4]
        Lit les dernières vidéos d'un profil (YouTube : chaîne ou @nom ; TikTok : @nom ; autres si yt-dlp les gère) et en tire :
        niche réelle, cadence, meilleurs jours/heures (d'après LES RÉSULTATS de ce profil), durées et accroches qui marchent,
        hashtags porteurs, recommandations concrètes et un planning de la semaine (fichier .ics pour ton agenda).
  insights.py niches --keywords "argent, foot, cuisine" | --seeds -o dossier [--n 8]
        Compare des niches (recherche YouTube via yt-dlp) : demande (vues médianes), ouverture aux petites chaînes,
        fraîcheur, durée, hashtags et sous-niches, puis classe selon un score indicatif.
  insights.py plan -o dossier [--from-json insights.json] [--per-week 4] [--tz 0]
        Reconstruit seulement le planning (utile pour changer la fréquence ou le fuseau).
  Option commune : --from-json fichier.json  (ré-analyse de métadonnées déjà récupérées, sans réseau)

Sorties : insights.json (pour l'interface), INSIGHTS.md (lisible), planning.ics + PLANNING.md.
Limites : corrélations observées sur un échantillon public, jamais une garantie. Peu de vidéos = faible confiance (indiquée).
"""
from __future__ import annotations

import argparse
import datetime as dt
import math
import re
import statistics
import sys
import uuid
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from common import StudioError, die, load_json, save_json  # noqa: E402
from trends import EMOJI, GENERIC_REACH, HASHTAG, STOP, _entry, guess_lang, hook_forms  # noqa: E402

WEEKDAYS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
SEEDS = ["finance personnelle", "mobile money astuces", "entrepreneuriat Afrique", "football", "cuisine africaine",
         "agriculture", "intelligence artificielle", "immobilier construction", "motivation développement personnel",
         "éducation étudiants", "musique afrobeat", "humour sketch", "santé bien-être", "mode et beauté", "voyage",
         "technologie smartphones", "business en ligne", "sécurité informatique"]
# Repères génériques (hypothèses, pas des mesures) quand le profil n'a pas assez de données horaires :
DEFAULT_SLOTS = [(2, 12), (3, 19), (5, 18), (6, 10)]  # (jour 0=lundi, heure locale)


# --------------------------------------------------------------------------- #
# Collecte
# --------------------------------------------------------------------------- #
def _ydl(extra: dict | None = None, cookies: str | None = None):
    try:
        import yt_dlp
    except ImportError as exc:
        raise StudioError("yt-dlp n'est pas installé :  pip install yt-dlp") from exc
    opts = {"quiet": True, "no_warnings": True, "skip_download": True, "retries": 3, "socket_timeout": 25, **(extra or {})}
    if cookies:
        opts["cookiesfrombrowser"] = (cookies,)
    return yt_dlp.YoutubeDL(opts)


def _full(url: str, cookies: str | None) -> dict | None:
    try:
        with _ydl({"noplaylist": True}, cookies) as y:
            info = y.extract_info(url, download=False)
        return _entry(info, url) if info else None
    except Exception as exc:  # noqa: BLE001
        msg = re.sub(chr(27) + r"\[[0-9;]*m", "", str(exc)).strip().splitlines()[-1][:110]
        print(f"[ignoré] {url[:70]} : {msg}", file=sys.stderr)
        return None


def _urls_from_listing(url: str, n: int, cookies: str | None) -> list[str]:
    with _ydl({"extract_flat": "in_playlist", "playlistend": n}, cookies) as y:
        info = y.extract_info(url, download=False)
    out: list[str] = []
    for e in (info or {}).get("entries") or []:
        if not e:
            continue
        if e.get("entries"):  # onglets d'une chaîne imbriqués
            for s in e["entries"]:
                if s and (s.get("url") or s.get("webpage_url")):
                    out.append(s.get("webpage_url") or s["url"])
        elif e.get("url") or e.get("webpage_url"):
            out.append(e.get("webpage_url") or e["url"])
    return out[:n]


def collect_profile(url: str, n: int, cookies: str | None) -> list[dict]:
    targets = [url]
    if re.search(r"youtube\.com/(@[\w.\-]+|channel/[\w\-]+|c/[\w\-]+|user/[\w\-]+)/?$", url):
        targets = [url.rstrip("/") + "/videos", url.rstrip("/") + "/shorts"]
    urls: list[str] = []
    for t in targets:
        try:
            urls += _urls_from_listing(t, n if len(targets) == 1 else max(5, n // 2 + 1), cookies)
        except Exception as exc:  # noqa: BLE001
            msg = re.sub(chr(27) + r"\[[0-9;]*m", "", str(exc)).strip().splitlines()[-1][:160]
            print(f"[ignoré] {t[:70]} : {msg}", file=sys.stderr)
    if not urls:
        raise StudioError("Impossible de lire ce profil. Vérifie le lien (chaîne YouTube ou @compte TikTok public) et ta "
                          "connexion ; pour TikTok, essaie l'option « cookies du navigateur ».")
    seen, uniq = set(), []
    for u in urls:
        if u not in seen:
            seen.add(u)
            uniq.append(u)
    print(f"[profil] {len(uniq)} vidéos à lire…", file=sys.stderr)
    with ThreadPoolExecutor(max_workers=4) as ex:
        entries = [e for e in ex.map(lambda u: _full(u, cookies), uniq[: n + 6]) if e]
    if len(entries) < 3:
        raise StudioError(f"Seulement {len(entries)} vidéo(s) lisible(s) : trop peu pour analyser (3 minimum).")
    return entries[:n + 6]


def collect_niche(keyword: str, n: int, cookies: str | None) -> list[dict]:
    with _ydl({"extract_flat": "in_playlist"}, cookies) as y:
        res = y.extract_info(f"ytsearch{n}:{keyword}", download=False)
    urls = [e.get("url") or e.get("webpage_url") for e in (res or {}).get("entries") or [] if e]
    with ThreadPoolExecutor(max_workers=4) as ex:
        return [e for e in ex.map(lambda u: _full(u, cookies), [u for u in urls if u]) if e]


# --------------------------------------------------------------------------- #
# Statistiques
# --------------------------------------------------------------------------- #
def med(xs) -> float:
    xs = [x for x in xs if x is not None]
    return float(statistics.median(xs)) if xs else 0.0


def _bucket_dur(d: float) -> str:
    return "< 15 s" if d < 15 else "15–30 s" if d < 30 else "30–60 s" if d < 60 else "1–3 min" if d < 180 else "> 3 min"


def _lift(groups: dict, min_count: int = 2) -> list[dict]:
    rows = [{"label": k, "count": len(v), "lift": round(med(v), 2)} for k, v in groups.items() if len(v) >= min_count]
    return sorted(rows, key=lambda r: (r["lift"], r["count"]), reverse=True)


def profile_stats(entries: list[dict], tz: float = 0.0) -> dict:
    vids = [e for e in entries if e.get("views") is not None]
    base = med([e["views"] for e in vids]) or 1.0
    for e in vids:
        e["_rel"] = e["views"] / base
    ts = sorted(e["timestamp"] for e in vids if e.get("timestamp"))
    if not ts:  # pas d'heure : on se rabat sur la date
        for e in vids:
            if e.get("upload_date"):
                try:
                    d = dt.datetime.strptime(e["upload_date"], "%Y%m%d").replace(tzinfo=dt.timezone.utc)
                    e["timestamp"], e["_date_only"] = int(d.timestamp()), True
                except ValueError:
                    pass
        ts = sorted(e["timestamp"] for e in vids if e.get("timestamp"))
    span_days = max(1.0, (ts[-1] - ts[0]) / 86400) if len(ts) >= 2 else None
    per_week = round(len(ts) / (span_days / 7), 1) if span_days else None
    gaps = [(b - a) / 86400 for a, b in zip(ts, ts[1:])]
    has_hours = any(e.get("hour_utc") is not None and not e.get("_date_only") for e in vids)

    hours: dict = defaultdict(list)
    days: dict = defaultdict(list)
    for e in vids:
        if e.get("timestamp") and not e.get("_date_only"):
            local = dt.datetime.fromtimestamp(e["timestamp"], tz=dt.timezone.utc) + dt.timedelta(hours=tz)
            hours[f"{(local.hour // 2) * 2:02d}h–{(local.hour // 2) * 2 + 2:02d}h"].append(e["_rel"])
            days[WEEKDAYS[local.weekday()]].append(e["_rel"])
        elif e.get("timestamp"):
            local = dt.datetime.fromtimestamp(e["timestamp"], tz=dt.timezone.utc)
            days[WEEKDAYS[local.weekday()]].append(e["_rel"])
    durs: dict = defaultdict(list)
    forms: dict = defaultdict(list)
    tags: dict = defaultdict(list)
    words: dict = defaultdict(list)
    for e in vids:
        if e.get("duration"):
            durs[_bucket_dur(e["duration"])].append(e["_rel"])
        for f in hook_forms(e["title"]) or ["sans accroche typée"]:
            forms[f].append(e["_rel"])
        for h in e.get("hashtags") or []:
            if h not in GENERIC_REACH:
                tags["#" + h].append(e["_rel"])
        lg = guess_lang(e["title"])
        for w in set(re.findall(r"[\w\u00C0-\u024F']{4,}", HASHTAG.sub("", e["title"]).lower())):
            if w not in STOP.get(lg, set()):
                words[w].append(e["_rel"])
    ranked = sorted(vids, key=lambda e: e["views"], reverse=True)
    eng = [e["engagement"] for e in vids if e.get("engagement") is not None]
    half = len(ranked) // 2
    chrono = sorted([e for e in vids if e.get("timestamp")], key=lambda e: e["timestamp"])
    momentum = None
    if len(chrono) >= 8:
        k = len(chrono) // 2
        old, new = med([e["views"] for e in chrono[:k]]), med([e["views"] for e in chrono[k:]])
        momentum = round(new / old, 2) if old else None
    n = len(vids)
    return {
        "count": n, "confidence": "élevée" if n >= 25 else "moyenne" if n >= 12 else "faible",
        "views_median": int(base), "views_top": int(ranked[0]["views"]) if ranked else 0,
        "engagement_median": round(med(eng), 4) if eng else None, "per_week": per_week,
        "gap_days_median": round(med(gaps), 1) if gaps else None, "momentum": momentum,
        "has_hours": has_hours, "tz": tz,
        "hours": _lift(hours), "weekdays": _lift(days), "durations": _lift(durs, 2), "hooks": _lift(forms, 2),
        "hashtags": _lift(tags, 2)[:10], "keywords": _lift(words, 2)[:12],
        "top_videos": [{"title": e["title"][:110], "views": e["views"], "duration": e["duration"], "url": e["url"],
                        "rel": round(e["_rel"], 2)} for e in ranked[:5]],
        "weak_videos": [{"title": e["title"][:110], "views": e["views"], "rel": round(e["_rel"], 2)} for e in ranked[::-1][:3]],
        "top_half_median_duration": round(med([e["duration"] for e in ranked[: max(1, half)]]), 1),
        "followers": max((e.get("followers") or 0 for e in vids), default=0) or None,
        "channel": next((e["channel"] for e in vids if e.get("channel")), None),
    }


def recommend(st: dict, lang: str = "fr") -> list[str]:
    r: list[str] = []
    if st["confidence"] == "faible":
        r.append(f"Échantillon réduit ({st['count']} vidéos) : traite ces pistes comme des hypothèses à tester, pas comme des règles.")
    kw = [k["label"] for k in st["keywords"][:3]]
    tg = [h["label"] for h in st["hashtags"][:3]]
    if kw or tg:
        r.append("Niche perçue : " + (", ".join(kw) if kw else "—") + (f" (hashtags porteurs : {' '.join(tg)})" if tg else "")
                 + ". Reste cohérent : un algorithme recommande mieux un compte dont le sujet est clair.")
    good_h = [h for h in st["hours"] if h["lift"] > 1.0 and h["count"] >= 2][:2]
    if st["has_hours"] and good_h:
        r.append("Publie surtout entre " + " et ".join(h["label"] for h in good_h) + f" (heure locale UTC{st['tz']:+g}) : "
                 "tes vidéos de ces créneaux dépassent ta médiane.")
    elif not st["has_hours"]:
        r.append("Les heures exactes de publication ne sont pas lisibles pour ce profil : regarde YouTube Studio → Audience "
                 "(« quand vos spectateurs sont en ligne ») ou les statistiques TikTok → Abonnés → Activité.")
    good_d = [d for d in st["weekdays"] if d["lift"] > 1.0 and d["count"] >= 2][:2]
    if good_d:
        r.append("Meilleurs jours observés : " + ", ".join(d["label"] for d in good_d) + ".")
    gd = [d for d in st["durations"] if d["lift"] > 1.0][:1]
    if gd:
        r.append(f"Durée qui performe le mieux : {gd[0]['label']} ({gd[0]['count']} vidéos, ×{gd[0]['lift']} ta médiane).")
    gf = [f for f in st["hooks"] if f["lift"] > 1.0 and f["label"] != "sans accroche typée"][:2]
    if gf:
        r.append("Formes d'accroche gagnantes : " + ", ".join(f"{f['label']} (×{f['lift']})" for f in gf) + ".")
    elif st["hooks"] and st["hooks"][-1]["label"] == "sans accroche typée":
        r.append("Peu de titres utilisent une accroche forte (question, chiffre, secret…) : teste-en une sur tes prochains clips.")
    if st.get("per_week") is not None:
        if st["per_week"] < 2:
            r.append(f"Cadence : {st['per_week']} vidéo(s)/semaine. Vise 3 à 5 pour donner de la matière à l'algorithme (sans sacrifier la qualité).")
        elif st["per_week"] > 10:
            r.append(f"Cadence : {st['per_week']} vidéos/semaine, très soutenue : vérifie que la rétention ne baisse pas.")
        else:
            r.append(f"Cadence : {st['per_week']} vidéos/semaine : c'est un bon rythme, garde-le régulier.")
    if st.get("momentum"):
        r.append("Dynamique : " + ("tes vidéos récentes font mieux que les anciennes (×%.2f), continue dans cette direction." % st["momentum"]
                                  if st["momentum"] > 1.1 else "tes vidéos récentes font moins bien que les anciennes (×%.2f) : "
                                  "reviens à ce qui marchait (voir top vidéos)." % st["momentum"] if st["momentum"] < 0.9
                                  else "stable (×%.2f)." % st["momentum"]))
    if st["top_videos"]:
        r.append(f"Refais une variante de ta meilleure vidéo (« {st['top_videos'][0]['title'][:60]} ») : même promesse, autre angle.")
    return r


# --------------------------------------------------------------------------- #
# Niches
# --------------------------------------------------------------------------- #
def niche_metrics(keyword: str, entries: list[dict]) -> dict | None:
    if len(entries) < 3:
        return None
    views = [e["views"] for e in entries]
    mv = med(views)
    foll = [e["followers"] for e in entries if e.get("followers")]
    small = [e for e in entries if e.get("followers") and e["followers"] < 100_000]
    wins = [e for e in small if e["views"] >= mv]
    opp = (len(wins) / len(small)) if small else (0.5 if not foll else 0.0)
    now = dt.datetime.now(dt.timezone.utc)
    fresh = 0
    dated = 0
    for e in entries:
        if e.get("upload_date"):
            try:
                d = dt.datetime.strptime(e["upload_date"], "%Y%m%d").replace(tzinfo=dt.timezone.utc)
                dated += 1
                fresh += (now - d).days <= 120
            except ValueError:
                pass
    tags = Counter(h for e in entries for h in e.get("hashtags") or [] if h not in GENERIC_REACH)
    words = Counter()
    for e in entries:
        lg = guess_lang(e["title"])
        for w in set(re.findall(r"[\w\u00C0-\u024F']{4,}", HASHTAG.sub("", e["title"]).lower())):
            if w not in STOP.get(lg, set()) and w not in keyword.lower():
                words[w] += 1
    return {"keyword": keyword, "sample": len(entries), "views_median": int(mv), "views_p75": int(sorted(views)[int(len(views) * 0.75) - 1] if len(views) > 1 else mv),
            "duration_median": round(med([e["duration"] for e in entries]), 1), "engagement_median": round(med([e["engagement"] for e in entries if e.get("engagement") is not None]), 4) or None,
            "small_channel_win_rate": round(opp, 2) if small else None, "followers_median": int(med(foll)) if foll else None,
            "fresh_share": round(fresh / dated, 2) if dated else None,
            "hashtags": [f"#{h}" for h, _ in tags.most_common(5)], "sub_niches": [w for w, c in words.most_common(6) if c >= 2],
            "titles": [e["title"][:90] for e in sorted(entries, key=lambda e: e["views"], reverse=True)[:3]],
            "_opp": opp, "_fresh": (fresh / dated) if dated else 0.5}


def rank_niches(rows: list[dict]) -> list[dict]:
    if not rows:
        return rows
    logs = [math.log10(r["views_median"] + 1) for r in rows]
    lo, hi = min(logs), max(logs)
    for r, lg in zip(rows, logs):
        demand = (lg - lo) / (hi - lo) if hi > lo else 0.5
        r["demand"] = round(demand, 2)
        r["score"] = int(round(100 * (0.45 * demand + 0.35 * r.pop("_opp") + 0.20 * r.pop("_fresh"))))
    return sorted(rows, key=lambda r: r["score"], reverse=True)


# --------------------------------------------------------------------------- #
# Planning
# --------------------------------------------------------------------------- #
def make_plan(per_week: int, tz: float, stats: dict | None, start: dt.date | None = None, theme: str = "") -> dict:
    per_week = max(1, min(14, per_week))
    start = start or (dt.date.today() + dt.timedelta(days=1))
    slots: list[tuple[int, int, str]] = []  # (weekday, hour, origine)
    if stats:
        gd = [WEEKDAYS.index(d["label"]) for d in stats.get("weekdays", []) if d["lift"] > 1.0 and d["count"] >= 2]
        gh = []
        for h in stats.get("hours", []):
            if h["lift"] > 1.0 and h["count"] >= 2:
                gh.append(int(h["label"][:2]) + 1)
        if gd or gh:
            days = (gd + [d for d, _ in DEFAULT_SLOTS if d not in gd])[: min(per_week, 7)]
            hrs = gh or [h for _, h in DEFAULT_SLOTS]
            for i, d in enumerate(days):
                slots.append((d, hrs[i % len(hrs)], "d'après tes résultats"))
    if not slots:
        base_days = [1, 3, 5, 0, 2, 4, 6]
        hrs = [19, 12, 18, 20, 12, 19, 10]
        for i in range(min(per_week, 7)):
            slots.append((base_days[i], hrs[i], "repère général (à vérifier)"))
    while len(slots) < per_week:  # plus d'1 publication/jour : 2e créneau
        d, h, _ = slots[len(slots) % max(1, min(7, len(slots)))]
        slots.append((d, (h + 3) % 24 or 12, "créneau complémentaire"))
    ideas = []
    best_hook = next((h["label"] for h in (stats or {}).get("hooks", []) if h["lift"] > 1 and h["label"] != "sans accroche typée"), "question")
    best_dur = next((d["label"] for d in (stats or {}).get("durations", []) if d["lift"] > 1), "30–60 s")
    rot = [f"Clip {best_dur} — accroche « {best_hook} »", "Clip tutoriel / astuce (valeur claire dès 3 s)",
           "Clip « résultat / avant-après »", "Réponse à un commentaire (interaction)", "Clip long 75–90 s (histoire complète)"]
    plan_slots = []
    for i, (wd, hr, origin) in enumerate(sorted(slots)):
        delta = (wd - start.weekday()) % 7
        day = start + dt.timedelta(days=delta)
        local = dt.datetime.combine(day, dt.time(hr % 24, 0))
        utc = local - dt.timedelta(hours=tz)
        plan_slots.append({"date": day.isoformat(), "weekday": WEEKDAYS[wd], "local_time": f"{hr % 24:02d}:00",
                           "utc": utc.strftime("%Y-%m-%dT%H:%M:00Z"), "origin": origin,
                           "idea": rot[i % len(rot)] + (f" · thème : {theme}" if theme else "")})
    return {"per_week": per_week, "tz": tz, "start": start.isoformat(), "slots": plan_slots,
            "checklist": ["Titre ≤ 60 caractères avec une promesse claire", "Accroche dans la 1re seconde",
                          "Sous-titres relus (traduction vérifiée)", "Étiquette « contenu IA » si voix de synthèse",
                          "Hashtags : 3 à 5, mélange niche + portée", "À J+1 et J+2 : durée moyenne de visionnage, rétention 3 s, partages"]}


def plan_ics(plan: dict) -> str:
    now = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    L = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Phenix-video//Planning//FR", "CALSCALE:GREGORIAN"]
    for s in plan["slots"]:
        t0 = dt.datetime.strptime(s["utc"], "%Y-%m-%dT%H:%M:%SZ")
        L += ["BEGIN:VEVENT", f"UID:{uuid.uuid4()}@phenix-video", f"DTSTAMP:{now}", f"DTSTART:{t0:%Y%m%dT%H%M%SZ}",
              f"DTEND:{t0 + dt.timedelta(minutes=30):%Y%m%dT%H%M%SZ}", "SUMMARY:Publier — Phenix-video",
              "DESCRIPTION:" + s["idea"].replace(",", "\\,").replace("\n", " "),
              "BEGIN:VALARM", "ACTION:DISPLAY", "DESCRIPTION:Publication dans 30 minutes", "TRIGGER:-PT30M", "END:VALARM", "END:VEVENT"]
    L.append("END:VCALENDAR")
    return "\r\n".join(L) + "\r\n"


def plan_md(plan: dict) -> str:
    L = ["# Planning de publication", "", f"{plan['per_week']} publication(s) par semaine · heures locales (UTC{plan['tz']:+g}). "
         "Les créneaux « repère général » sont des hypothèses : remplace-les par tes statistiques dès que possible.", "",
         "| Jour | Heure | Quoi publier | Origine du créneau |", "|---|---|---|---|"]
    L += [f"| {s['weekday']} {s['date']} | {s['local_time']} | {s['idea']} | {s['origin']} |" for s in plan["slots"]]
    L += ["", "## Avant chaque publication", *[f"- [ ] {c}" for c in plan["checklist"]]]
    return "\n".join(L) + "\n"


# --------------------------------------------------------------------------- #
# Rapports
# --------------------------------------------------------------------------- #
def profile_md(src: str, st: dict, recs: list[str]) -> str:
    L = [f"# Analyse de profil — {st.get('channel') or src}", "", f"Confiance : **{st['confidence']}** ({st['count']} vidéos lues). "
         "Corrélations observées sur des données publiques, pas des garanties.", "",
         f"- Vues médianes : **{st['views_median']}** · meilleure vidéo : **{st['views_top']}**",
         f"- Engagement médian : {('%.1f %%' % (st['engagement_median'] * 100)) if st['engagement_median'] is not None else 'n/a'}",
         f"- Cadence : {st['per_week'] if st['per_week'] is not None else 'n/a'} vidéo(s)/semaine · écart médian {st['gap_days_median']} j", "",
         "## Recommandations", *[f"- {r}" for r in recs], "", "## Créneaux (médiane des vues ÷ médiane du compte)"]
    L += [f"- {h['label']} : ×{h['lift']} ({h['count']} vidéos)" for h in st["hours"][:6]] or ["- (heures non disponibles)"]
    L += ["", "## Jours"] + ([f"- {d['label']} : ×{d['lift']} ({d['count']})" for d in st["weekdays"]] or ["- n/a"])
    L += ["", "## Durées"] + ([f"- {d['label']} : ×{d['lift']} ({d['count']})" for d in st["durations"]] or ["- n/a"])
    L += ["", "## Accroches"] + ([f"- {d['label']} : ×{d['lift']} ({d['count']})" for d in st["hooks"]] or ["- n/a"])
    L += ["", "## Meilleures vidéos"] + [f"- {v['views']} vues · {v['title']}  \n  {v['url']}" for v in st["top_videos"]]
    return "\n".join(L) + "\n"


def niches_md(rows: list[dict]) -> str:
    L = ["# Niches comparées", "", "Score indicatif = 45 % demande (vues médianes) + 35 % ouverture aux petites chaînes + 20 % fraîcheur. "
         "Un score élevé = terrain intéressant, pas un succès garanti : ton angle et ta régularité comptent plus.", "",
         "| # | Niche | Score | Vues médianes | Petites chaînes qui percent | Durée méd. | Sous-niches |", "|---|---|---|---|---|---|---|"]
    for i, r in enumerate(rows, 1):
        w = f"{int(r['small_channel_win_rate'] * 100)} %" if r["small_channel_win_rate"] is not None else "n/a"
        L.append(f"| {i} | {r['keyword']} | {r['score']} | {r['views_median']} | {w} | {r['duration_median']} s | {', '.join(r['sub_niches'][:4])} |")
    for r in rows[:5]:
        L += ["", f"### {r['keyword']}", "- Hashtags : " + (" ".join(r["hashtags"]) or "n/a"), *[f"- Exemple : {t}" for t in r["titles"]]]
    return "\n".join(L) + "\n"


def write_plan(out: Path, plan: dict) -> None:
    (out / "planning.ics").write_text(plan_ics(plan), encoding="utf-8")
    (out / "PLANNING.md").write_text(plan_md(plan), encoding="utf-8")


def run_profile(url: str | None, out_dir: str, *, n: int = 25, tz: float = 0.0, per_week: int = 4, cookies: str | None = None,
                from_json: str | None = None, theme: str = "") -> Path:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    if from_json:
        data = load_json(from_json)
        entries = data["entries"] if isinstance(data, dict) else data
        url = url or (data.get("source") if isinstance(data, dict) else "") or "profil"
    else:
        if not url:
            raise StudioError("Donne le lien du profil (chaîne YouTube, @compte TikTok…).")
        entries = collect_profile(url, max(5, min(n, 60)), cookies)
    st = profile_stats(entries, tz)
    recs = recommend(st)
    plan = make_plan(per_week, tz, st, theme=theme)
    clean = [{k: v for k, v in e.items() if not k.startswith("_")} for e in entries]
    save_json(out / "insights.json", {"kind": "profile", "source": url, "entries": clean, "stats": st, "recommendations": recs, "plan": plan})
    (out / "INSIGHTS.md").write_text(profile_md(url, st, recs), encoding="utf-8")
    write_plan(out, plan)
    return out


def run_niches(keywords: list[str], out_dir: str, *, n: int = 8, cookies: str | None = None, from_json: str | None = None) -> Path:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    if from_json:
        data = load_json(from_json)
        groups = data["groups"]
    else:
        if not keywords:
            raise StudioError("Donne au moins un mot-clé (ou utilise les idées de départ).")
        groups = {}
        for kw in keywords[:12]:
            print(f"[niche] analyse « {kw} »…", file=sys.stderr)
            try:
                groups[kw] = collect_niche(kw, max(4, min(n, 15)), cookies)
            except Exception as exc:  # noqa: BLE001
                print(f"[ignoré] {kw} : {str(exc)[:100]}", file=sys.stderr)
    rows = [m for kw, ents in groups.items() if (m := niche_metrics(kw, ents))]
    if not rows:
        raise StudioError("Aucune niche exploitable : vérifie la connexion (la recherche YouTube doit être accessible).")
    rows = rank_niches(rows)
    save_json(out / "insights.json", {"kind": "niches", "niches": rows, "groups": groups})
    (out / "INSIGHTS.md").write_text(niches_md(rows), encoding="utf-8")
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("profile")
    p.add_argument("url", nargs="?")
    p.add_argument("--n", type=int, default=25)
    p.add_argument("--theme", default="")
    n = sub.add_parser("niches")
    n.add_argument("--keywords", default="")
    n.add_argument("--seeds", action="store_true", help="utilise une liste d'idées de départ")
    n.add_argument("--n", type=int, default=8, help="vidéos lues par niche")
    pl = sub.add_parser("plan")
    pl.add_argument("--theme", default="")
    for x in (p, n, pl):
        x.add_argument("-o", "--out", required=True)
        x.add_argument("--from-json")
        x.add_argument("--cookies-from-browser", default=None)
    for x in (p, pl):
        x.add_argument("--tz", type=float, default=0.0, help="décalage horaire local par rapport à UTC (Burkina Faso : 0)")
        x.add_argument("--per-week", type=int, default=4)
    a = ap.parse_args()
    try:
        if a.cmd == "profile":
            d = run_profile(a.url, a.out, n=a.n, tz=a.tz, per_week=a.per_week, cookies=a.cookies_from_browser,
                            from_json=a.from_json, theme=a.theme)
        elif a.cmd == "niches":
            kws = SEEDS[:8] if a.seeds and not a.keywords else [k.strip() for k in a.keywords.split(",") if k.strip()]
            d = run_niches(kws, a.out, n=a.n, cookies=a.cookies_from_browser, from_json=a.from_json)
        else:
            out = Path(a.out)
            out.mkdir(parents=True, exist_ok=True)
            st = load_json(a.from_json)["stats"] if a.from_json else None
            plan = make_plan(a.per_week, a.tz, st, theme=a.theme)
            save_json(out / "plan.json", plan)
            write_plan(out, plan)
            d = out
        print(f"[ok] résultats : {d}")
    except StudioError as exc:
        die(str(exc))


if __name__ == "__main__":
    main()
