#!/usr/bin/env python3
# Phenix-video — © 2026 Phenix - kcw. Tous droits réservés (voir LICENSE).
"""Détection des meilleurs moments (extraction automatique) à partir d'un transcript.json.

Aucun modèle payant : scoring heuristique transparent (accroche, émotion, rythme,
densité de parole, complétude de la phrase, énergie audio optionnelle).
Chaque clip retourné explique son score (`reasons`) pour que Claude ou l'utilisateur
puisse le re-classer, renommer ou rejeter avant le rendu.

Sortie : clips.json  {"source":..., "clips":[{id,start,end,duration,score,title,hook,reasons,text}]}
"""
from __future__ import annotations

import argparse
import math
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from common import StudioError, die, load_json, save_json  # noqa: E402

# --------------------------------------------------------------------------- #
# Lexiques (FR + EN). Étendables avec --lexicon fichier.txt (un mot/expression par ligne)
# --------------------------------------------------------------------------- #
HOOK_PATTERNS = [
    # français
    r"\b(le secret|la vérité|personne ne|jamais|stop|attention|arrête|erreur|pourquoi|comment|voici|"
    r"ce que|la raison|le truc|la seule|la meilleure|le pire|incroyable|choquant|gratuit|astuce|"
    r"saviez-vous|tu savais|imagine|écoute|regarde)\b",
    # english
    r"\b(secret|truth|nobody|never|stop|warning|mistake|why|how to|here's|here is|the reason|"
    r"the only|the best|the worst|incredible|shocking|free|hack|did you know|imagine|listen|look)\b",
]
POWER_WORDS = {
    "argent", "million", "millions", "milliard", "riche", "pauvre", "succès", "échec", "peur", "danger",
    "gagner", "perdre", "erreur", "secret", "vérité", "mensonge", "vie", "mort", "amour", "haine",
    "colère", "honte", "fierté", "liberté", "puissant", "énorme", "incroyable", "fou", "folie",
    "changer", "transformer", "révolution", "problème", "solution", "résultat", "preuve", "obligé",
    "money", "million", "billion", "rich", "poor", "success", "fail", "failure", "fear", "danger",
    "win", "lose", "mistake", "secret", "truth", "lie", "life", "death", "love", "hate", "anger",
    "shame", "proud", "freedom", "powerful", "huge", "insane", "crazy", "change", "transform",
    "problem", "solution", "result", "proof", "guaranteed",
}
CONCLUSION = re.compile(
    r"\b(donc|voilà|c'est pour ça|c'est pour cela|en résumé|retiens|la leçon|au final|"
    r"that's why|so remember|in the end|the lesson|bottom line|takeaway)\b", re.I)
CONTINUATION_START = re.compile(
    r"^(et|mais|donc|car|parce que|puis|ensuite|alors|du coup|and|but|so|because|then|which|that)\b", re.I)
FILLERS = {"euh", "heu", "hum", "ben", "bah", "genre", "um", "uh", "uhm", "like", "bref"}
TERMINAL = (".", "!", "?", "…")


@dataclass
class Unit:
    start: float
    end: float
    text: str
    words: list = field(default_factory=list)


# --------------------------------------------------------------------------- #
# Découpage en phrases
# --------------------------------------------------------------------------- #
def build_units(transcript: dict, pause: float = 0.7, soft_pause: float = 0.35, max_len: float = 14.0) -> list[Unit]:
    words = []
    for seg in transcript["segments"]:
        words.extend(seg.get("words") or [])
    if not words:
        raise StudioError("Le transcript ne contient aucun mot horodaté.")
    units: list[Unit] = []
    bucket: list[dict] = []

    def flush():
        if bucket:
            units.append(Unit(bucket[0]["start"], bucket[-1]["end"],
                              " ".join(w["w"] for w in bucket), list(bucket)))
            bucket.clear()

    for i, w in enumerate(words):
        bucket.append(w)
        nxt = words[i + 1] if i + 1 < len(words) else None
        gap = (nxt["start"] - w["end"]) if nxt else 99.0
        ends_sentence = w["w"].endswith(TERMINAL)
        too_long = bucket[-1]["end"] - bucket[0]["start"] > max_len
        soft_break = too_long and (w["w"].endswith((",", ";", ":")) or gap > soft_pause)
        if ends_sentence or gap > pause or soft_break or nxt is None:
            flush()
    return units


# --------------------------------------------------------------------------- #
# Énergie audio (optionnelle)
# --------------------------------------------------------------------------- #
def audio_energy(media: str, hop: float = 1.0):
    import numpy as np
    proc = subprocess.run(
        ["ffmpeg", "-nostdin", "-loglevel", "error", "-i", media, "-vn", "-ac", "1", "-ar", "8000",
         "-f", "s16le", "-"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if proc.returncode != 0 or not proc.stdout:
        return None
    samples = np.frombuffer(proc.stdout, dtype=np.int16).astype(np.float32) / 32768.0
    step = int(8000 * hop)
    n = len(samples) // step
    if n < 2:
        return None
    rms = np.sqrt((samples[: n * step].reshape(n, step) ** 2).mean(axis=1) + 1e-12)
    return rms, hop


# --------------------------------------------------------------------------- #
# Scoring
# --------------------------------------------------------------------------- #
def gauss(x: float, mu: float, sigma: float) -> float:
    return math.exp(-((x - mu) ** 2) / (2 * sigma ** 2))


STOP_LOOP = {"the","and","that","this","with","you","for","are","was","les","des","une","que","qui","pour","dans","pas",
             "est","sur","vous","nous","avec","mais","donc","not","but","have","has"}


def algo_signals(span: list, words: list, dur: float) -> tuple[float, list[str]]:
    """Signaux alignés sur ce que les plateformes disent mesurer (rétention, fin de visionnage, relecture).
    Aucun n'est une garantie : ce sont des heuristiques prudentes (bonus/pénalités bornés, -10 à +12)."""
    bonus = 0.0
    why: list[str] = []
    first_words = [w for u in span[:3] for w in u.words]
    # 1) gratification rapide : un mot fort ou un chiffre dans les ~5 premières secondes
    t0 = span[0].start
    early = [w for w in first_words if w["start"] - t0 <= 5.0]
    if any(re.sub(r"\W", "", w["w"].lower()) in POWER_WORDS or re.search(r"\d", w["w"]) for w in early):
        bonus += 3; why.append("gratification rapide (mot fort/chiffre dans les 5 s)")
    # 2) départ immédiat : pas de silence d'ouverture
    if words and words[0]["start"] - t0 <= 0.6:
        bonus += 2
    elif words and words[0]["start"] - t0 > 1.5:
        bonus -= 3; why.append("pénalité : silence d'ouverture")
    # 3) trou de rétention : longue pause au milieu (le public « swipe » quand ça traîne)
    gaps = [b["start"] - a["end"] for a, b in zip(words, words[1:])]
    long_gaps = sum(1 for g in gaps if g > 1.8)
    if long_gaps:
        bonus -= min(6, 3 * long_gaps); why.append(f"pénalité : {long_gaps} temps mort(s) > 1,8 s")
    # 4) boucle : la fin reprend un mot-clé de l'ouverture → incite à la relecture
    def keys(ws):
        return {re.sub(r"\W", "", w["w"].lower()) for w in ws if len(re.sub(r"\W", "", w["w"])) >= 5} - STOP_LOOP
    if keys(first_words) & keys([w for u in span[-2:] for w in u.words]):
        bonus += 3; why.append("fin qui reboucle sur l'accroche")
    # 5) durée courte : meilleure chance d'être regardé jusqu'au bout (taux de complétion)
    if dur <= 45:
        bonus += 2
    elif dur <= 75:
        bonus += 1
    return max(-10.0, min(12.0, bonus)), why


def score_window(units: list[Unit], i: int, j: int, target: float, extra_power: set[str],
                 energy=None, global_energy=None) -> tuple[float, list[str]]:
    span = units[i:j + 1]
    start, end = span[0].start, span[-1].end
    dur = end - start
    words = [w for u in span for w in u.words]
    n_words = max(1, len(words))
    text = " ".join(u.text for u in span)
    first = span[0].text
    reasons: list[str] = []
    score = 0.0

    # --- accroche (0-25)
    hook = 0.0
    if "?" in first:
        hook += 9; reasons.append("accroche : question")
    if any(re.search(p, first, re.I) for p in HOOK_PATTERNS):
        hook += 10; reasons.append("accroche : formule d'attention")
    if re.search(r"\d", first):
        hook += 4; reasons.append("accroche : chiffre")
    if len(first.split()) <= 14:
        hook += 2  # phrase d'ouverture courte et percutante
    score += min(25, hook)

    # --- mots forts / émotion (0-20)
    power = sum(1 for w in words if re.sub(r"\W", "", w["w"].lower()) in (POWER_WORDS | extra_power))
    density = power / n_words * 100
    p_score = min(20.0, density * 4.0)
    if p_score >= 6:
        reasons.append(f"mots forts ({power})")
    score += p_score

    # --- rythme (0-15) : 2.2-3.6 mots/s idéal
    speech_time = sum(w["end"] - w["start"] for w in words)
    wps = n_words / max(dur, 0.1)
    pace = 15 * gauss(wps, 2.9, 0.9)
    if pace > 11:
        reasons.append(f"rythme dynamique ({wps:.1f} mots/s)")
    score += pace

    # --- densité de parole (0-10)
    ratio = min(1.0, speech_time / max(dur, 0.1))
    score += 10 * max(0.0, (ratio - 0.55) / 0.40)

    # --- longueur (0-10)
    score += 10 * gauss(dur, target, max(8.0, target * 0.35))
    if dur < 60:
        reasons.append("clip court (< 1 min)")

    # --- ponctuation expressive (0-5)
    expressive = text.count("!") + text.count("?")
    score += min(5.0, expressive * 1.5)

    # --- fin satisfaisante (0-10)
    last = span[-1].text
    if last.endswith(TERMINAL):
        score += 5
    else:
        score -= 8; reasons.append("pénalité : fin en cours de phrase")
    if CONCLUSION.search(last) or CONCLUSION.search(text[-120:]):
        score += 5; reasons.append("conclusion nette")

    # --- pénalités
    if CONTINUATION_START.match(first):
        score -= 8; reasons.append("pénalité : commence au milieu d'une idée")
    fillers = sum(1 for w in words if re.sub(r"\W", "", w["w"].lower()) in FILLERS)
    if fillers / n_words > 0.04:
        score -= 6; reasons.append("pénalité : beaucoup de tics de langage")
    probs = [w.get("p", 1.0) for w in words if not w.get("estimated")]
    if probs and sum(probs) / len(probs) < 0.6:
        score -= 6; reasons.append("pénalité : transcription peu fiable")

    # --- signaux de rétention / complétion / relecture (-10 à +12)
    adj, adj_why = algo_signals(span, words, dur)
    score += adj
    reasons.extend(adj_why)

    # --- énergie audio (0-5)
    if energy is not None and global_energy is not None:
        rms, hop = energy
        a, b = int(start / hop), max(int(end / hop), int(start / hop) + 1)
        seg = rms[a:b]
        if len(seg):
            lift = float(seg.mean() / (global_energy + 1e-9))
            var = float(seg.std() / (seg.mean() + 1e-9))
            bonus = min(5.0, max(0.0, (lift - 1.0) * 5.0 + var * 2.0))
            if bonus > 3:
                reasons.append("énergie vocale élevée")
            score += bonus

    return max(0.0, min(100.0, score)), reasons


def make_title(first_sentence: str, limit: int = 64) -> str:
    text = re.sub(r"\s+", " ", first_sentence).strip(" ,;:-")
    text = text.rstrip(".!")
    if len(text) > limit:
        text = text[:limit].rsplit(" ", 1)[0] + "…"
    return text[:1].upper() + text[1:] if text else "Clip"


def find_clips(transcript: dict, count: int, min_len: float, max_len: float, target: float,
               extra_power: set[str], media: str | None, gap: float, pad_before: float, pad_after: float,
               total_duration: float | None) -> list[dict]:
    units = build_units(transcript)
    if total_duration and total_duration <= min_len:
        # source plus courte que le minimum demandé : on garde la vidéo entière plutôt que d'échouer
        text = " ".join(u.text for u in units)
        print(f"[info] vidéo de {total_duration:.0f}s plus courte que le minimum ({min_len:.0f}s) : clip unique = vidéo entière.",
              file=sys.stderr)
        return [{"id": 1, "start": 0.0, "end": round(total_duration, 2), "duration": round(total_duration, 2),
                 "score": 0.0, "title": make_title(units[0].text) if units else "Vidéo complète",
                 "hook": units[0].text if units else "", "reasons": ["vidéo plus courte que le minimum"], "text": text}]
    energy = None
    global_energy = None
    if media:
        try:
            energy = audio_energy(media)
            if energy is not None:
                global_energy = float(energy[0].mean())
        except Exception as exc:  # noqa: BLE001 - l'énergie est un bonus, jamais bloquant
            print(f"[avertissement] énergie audio ignorée : {exc}", file=sys.stderr)

    def gather(lo: float) -> list:
        found = []
        for i in range(len(units)):
            for j in range(i, len(units)):
                dur = units[j].end - units[i].start
                if dur > max_len:
                    break
                if dur < lo:
                    continue
                s, reasons = score_window(units, i, j, target, extra_power, energy, global_energy)
                found.append((s, i, j, reasons))
        return found

    candidates = gather(min_len)
    for factor in (0.75, 0.55, 0.35):  # peu de parole : on assouplit la durée minimale au lieu d'échouer
        if candidates:
            break
        lo = max(12.0, min_len * factor)
        candidates = gather(lo)
        if candidates:
            print(f"[info] pas assez de parole pour {min_len:.0f}s : durée minimale abaissée à {lo:.0f}s.", file=sys.stderr)
    if not candidates and total_duration and total_duration <= max_len * 1.5:
        print("[info] sélection impossible par la parole : clip unique = vidéo entière.", file=sys.stderr)
        return [{"id": 1, "start": 0.0, "end": round(total_duration, 2), "duration": round(total_duration, 2),
                 "score": 0.0, "title": make_title(units[0].text) if units else "Vidéo complète",
                 "hook": "", "reasons": ["repli : vidéo entière"], "text": " ".join(u.text for u in units)}]
    if not candidates:
        raise StudioError(
            f"Aucune fenêtre de {min_len:.0f}-{max_len:.0f}s trouvée. Réduis --min ou augmente --max, "
            "ou vérifie que la transcription contient assez de parole.")
    candidates.sort(key=lambda c: c[0], reverse=True)

    chosen: list[tuple] = []
    for s, i, j, reasons in candidates:
        a, b = units[i].start, units[j].end
        overlaps = any(
            not (b + gap <= units[ci].start or a - gap >= units[cj].end)
            for _, ci, cj, _ in chosen
        )
        if overlaps:
            continue
        chosen.append((s, i, j, reasons))
        if len(chosen) >= count:
            break

    clips = []
    for n, (s, i, j, reasons) in enumerate(sorted(chosen, key=lambda c: c[0], reverse=True), 1):
        prev_end = units[i - 1].end if i > 0 else 0.0
        next_start = units[j + 1].start if j + 1 < len(units) else (total_duration or units[j].end + pad_after)
        start = max(units[i].start - pad_before, (prev_end + units[i].start) / 2 if i > 0 else 0.0)
        end = min(units[j].end + pad_after, (units[j].end + next_start) / 2 if j + 1 < len(units) else units[j].end + pad_after)
        if total_duration:
            end = min(end, total_duration)
        text = " ".join(u.text for u in units[i:j + 1])
        clips.append({
            "id": n,
            "start": round(max(0.0, start), 2),
            "end": round(end, 2),
            "duration": round(end - max(0.0, start), 2),
            "score": round(s, 1),
            "title": make_title(units[i].text),
            "hook": units[i].text,
            "reasons": reasons,
            "text": text,
        })
    return clips


def word_count(transcript: dict) -> int:
    return sum(len(seg.get("words") or []) for seg in transcript.get("segments", []))


def motion_profile(media: str, total: float, rate: int = 4):
    """Mouvement moyen par seconde (différence entre images réduites) : repère l'action visuelle."""
    import numpy as np
    side = 48
    proc = subprocess.run(
        ["ffmpeg", "-nostdin", "-loglevel", "error", "-i", media, "-an", "-vf",
         f"fps={rate},scale={side}:{side},format=gray", "-f", "rawvideo", "-"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    frames = np.frombuffer(proc.stdout, dtype=np.uint8)
    n = len(frames) // (side * side)
    if proc.returncode != 0 or n < rate * 2:
        return None
    frames = frames[: n * side * side].reshape(n, side * side).astype(np.float32)
    diff = np.abs(np.diff(frames, axis=0)).mean(axis=1)
    secs = int(total)
    out = np.zeros(max(secs, 1), np.float32)
    for t in range(secs):
        seg = diff[t * rate:(t + 1) * rate]
        if seg.size:
            out[t] = float(seg.mean())
    return out


def _z(x):
    import numpy as np
    sd = float(x.std())
    return (x - float(x.mean())) / sd if sd > 1e-9 else x * 0.0


def find_visual_clips(media: str, count: int, min_len: float, max_len: float, target: float, total: float,
                      title_hint: str = "", gap: float = 2.0) -> list[dict]:
    """Choix des moments forts SANS parole : pics de volume (musique, public, impacts) + mouvement visuel."""
    import numpy as np
    secs = int(total)
    sig = []
    reasons_by = []
    en = audio_energy(media, 1.0)
    if en is not None:
        a = np.log(en[0][:secs] + 1e-4)
        a = np.pad(a, (0, max(0, secs - len(a))), mode="edge")
        sig.append((0.5, _z(a)))
        reasons_by.append("énergie sonore")
    mo = motion_profile(media, total)
    if mo is not None:
        mo = np.pad(mo[:secs], (0, max(0, secs - len(mo))), mode="edge")
        sig.append((0.5, _z(mo)))
        reasons_by.append("mouvement visuel")
    if not sig:
        raise StudioError("Impossible d'analyser le son ni l'image de cette vidéo.")
    wsum = sum(w for w, _ in sig)
    score = sum(w * z for w, z in sig) / wsum
    length = int(min(total, max(min_len, min(max_len, target))))
    if total <= min_len or length >= secs - 1:
        print(f"[info] vidéo de {total:.0f}s : clip unique = vidéo entière.", file=sys.stderr)
        return [{"id": 1, "start": 0.0, "end": round(total, 2), "duration": round(total, 2), "score": 0.0,
                 "title": title_hint or "Vidéo complète", "hook": "", "reasons": ["vidéo courte : entière"], "text": ""}]
    cs = np.concatenate([[0.0], np.cumsum(score)])
    cands = []
    for a0 in range(0, secs - length + 1):
        mean = (cs[a0 + length] - cs[a0]) / length
        hook = (cs[a0 + min(3, length)] - cs[a0]) / min(3, length)  # début fort = bonne accroche
        cands.append((float(mean + 0.35 * hook), a0))
    cands.sort(reverse=True)
    chosen: list[tuple[float, int]] = []
    for sc, a0 in cands:
        if all(a0 + length + gap <= b or a0 >= b + length + gap for _, b in chosen):
            chosen.append((sc, a0))
        if len(chosen) >= count:
            break
    if len(chosen) < count:
        print(f"[info] {len(chosen)} clip(s) sans chevauchement possible sur {total:.0f}s (demandé : {count}).", file=sys.stderr)
    clips = []
    for n, (sc, a0) in enumerate(chosen, 1):
        clips.append({"id": n, "start": float(a0), "end": float(a0 + length), "duration": float(length),
                      "score": round(50 + 15 * sc, 1),
                      "title": f"{title_hint[:48]} — moment {n}" if title_hint else f"Moment fort {n}",
                      "hook": "", "reasons": ["sans parole : " + " + ".join(reasons_by)], "text": ""})
    return clips


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("transcript", help="transcript.json produit par transcribe.py")
    ap.add_argument("-o", "--out", default="clips.json")
    ap.add_argument("--count", type=int, default=5, help="nombre de clips (défaut 5)")
    ap.add_argument("--min", dest="min_len", type=float, default=75.0, help="durée min en s (défaut 75 = 1 min 15)")
    ap.add_argument("--max", dest="max_len", type=float, default=180.0, help="durée max en s (défaut 180)")
    ap.add_argument("--target", type=float, default=100.0, help="durée idéale en s (défaut 100)")
    ap.add_argument("--short", action="store_true", help="raccourci pour des clips 20-60 s (cible 40 s)")
    ap.add_argument("--gap", type=float, default=2.0, help="écart minimal entre deux clips (s)")
    ap.add_argument("--pad-before", type=float, default=0.2)
    ap.add_argument("--pad-after", type=float, default=0.4)
    ap.add_argument("--media", default=None, help="vidéo source : active le bonus d'énergie audio")
    ap.add_argument("--lexicon", default=None, help="mots forts supplémentaires (un par ligne)")
    args = ap.parse_args()

    try:
        if args.short:
            args.min_len, args.max_len, args.target = 20.0, 60.0, 40.0
        if args.min_len >= args.max_len:
            raise StudioError("--min doit être inférieur à --max")
        transcript = load_json(args.transcript)
        extra = set()
        if args.lexicon:
            extra = {ln.strip().lower() for ln in Path(args.lexicon).read_text(encoding="utf-8").splitlines() if ln.strip()}
        clips = find_clips(transcript, args.count, args.min_len, args.max_len, args.target, extra,
                           args.media, args.gap, args.pad_before, args.pad_after, transcript.get("duration"))
        save_json(args.out, {"source": args.media, "language": transcript.get("language"), "clips": clips})
        print(f"[ok] {len(clips)} clips -> {args.out}")
        if len(clips) < args.count:
            print(f"[info] seulement {len(clips)} clip(s) sur {args.count} demandés : la vidéo est trop courte ou trop "
                  f"peu variée pour des clips de {args.min_len:.0f}-{args.max_len:.0f}s sans chevauchement "
                  "(essaie --min plus bas ou --short).")
        for c in clips:
            print(f"  #{c['id']}  {c['start']:7.1f}s → {c['end']:7.1f}s  ({c['duration']:4.1f}s)  "
                  f"score {c['score']:5.1f}  {c['title']}")
    except StudioError as exc:
        die(str(exc))


if __name__ == "__main__":
    main()
