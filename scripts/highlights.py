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
    energy = None
    global_energy = None
    if media:
        try:
            energy = audio_energy(media)
            if energy is not None:
                global_energy = float(energy[0].mean())
        except Exception as exc:  # noqa: BLE001 - l'énergie est un bonus, jamais bloquant
            print(f"[avertissement] énergie audio ignorée : {exc}", file=sys.stderr)

    candidates = []
    for i in range(len(units)):
        for j in range(i, len(units)):
            dur = units[j].end - units[i].start
            if dur > max_len:
                break
            if dur < min_len:
                continue
            s, reasons = score_window(units, i, j, target, extra_power, energy, global_energy)
            candidates.append((s, i, j, reasons))
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
