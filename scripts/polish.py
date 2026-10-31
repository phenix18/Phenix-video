#!/usr/bin/env python3
# Phenix-video — © 2026 Phenix - kcw. Tous droits réservés (voir LICENSE).
"""Resserrage du rythme (jump-cuts) piloté par la transcription : enlève les temps morts entre les mots.

Contrairement à `edit.py silence` (détection sonore), on coupe d'après les horodatages des mots : les
pauses naturelles courtes sont gardées (respiration), les longs blancs sont réduits, et on obtient en plus
un transcript recalé sur la nouvelle durée, utilisable pour traduire, doubler et sous-titrer.

  polish.py video.mp4 transcript.json --start 120 --end 210 -o tight.mp4 [--max-gap 0.45]
-> tight.mp4 + tight.transcript.json (temps relatifs au nouveau clip, démarrant à 0)
"""
from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from common import (StudioError, audio_args, die, ensure_parent, finalize, load_json, probe,  # noqa: E402
                    run, save_json, temp_sibling)

FADE = 0.012  # fondu de 12 ms à chaque coupe : évite les « clics » audio


def keep_intervals(words: list[dict], start: float, end: float, max_gap: float = 0.45,
                   lead: float = 0.10, tail: float = 0.18) -> list[list[float]]:
    """Intervalles (temps source) à conserver : parole + marge ; les pauses <= max_gap restent intactes."""
    if max_gap <= lead + tail:
        raise StudioError("--max-gap doit être supérieur à 0,28 s.")
    ws = [w for w in words if w["end"] > start and w["start"] < end]
    if not ws:
        raise StudioError("Aucun mot dans cet intervalle : impossible de resserrer.")
    merged: list[list[float]] = []
    for w in ws:
        a, b = max(start, w["start"]), min(end, w["end"])
        if merged and a - merged[-1][1] <= max_gap:
            merged[-1][1] = max(merged[-1][1], b)
        else:
            merged.append([a, b])
    return [[max(start, a - lead), min(end, b + tail)] for a, b in merged]


def tighten_clip(src: str, transcript: dict, start: float, end: float, out: str, *, max_gap: float = 0.45,
                 crf: int = 14) -> dict:
    """Écrit `out` (clip resserré, résolution d'origine) et retourne {"transcript", "duration", "removed"}."""
    words = [w for seg in transcript["segments"] for w in (seg.get("words") or [])]
    intervals = keep_intervals(words, start, end, max_gap)
    info = probe(src)
    if not info.has_audio:
        raise StudioError("Pas de piste audio : rien à resserrer.")

    # --- carte ancien temps -> nouveau temps
    offsets, cum = [], 0.0
    for a, b in intervals:
        offsets.append(cum)
        cum += b - a
    new_dur = cum
    removed = (end - start) - new_dur

    def remap(t: float) -> float:
        for (a, b), off in zip(intervals, offsets):
            if a - 1e-6 <= t <= b + 1e-6:
                return off + (t - a)
        # t tombe dans une coupe : on le rattache au début de l'intervalle suivant
        for (a, b), off in zip(intervals, offsets):
            if t < a:
                return off
        return new_dur

    # --- filtre trim/concat (temps relatifs au -ss d'entrée)
    lines = []
    for i, (a, b) in enumerate(intervals):
        ra, rb = a - start, b - start
        dur = rb - ra
        lines.append(f"[0:v]trim=start={ra:.3f}:end={rb:.3f},setpts=PTS-STARTPTS[v{i}]")
        lines.append(f"[0:a]atrim=start={ra:.3f}:end={rb:.3f},asetpts=PTS-STARTPTS,"
                     f"afade=t=in:d={FADE},afade=t=out:st={max(0.0, dur - FADE):.3f}:d={FADE}[a{i}]")
    joined = "".join(f"[v{i}][a{i}]" for i in range(len(intervals)))
    lines.append(f"{joined}concat=n={len(intervals)}:v=1:a=1[v][a]")
    ensure_parent(out)
    tmp = temp_sibling(out)
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as fh:
        fh.write(";\n".join(lines))
        script = fh.name
    try:
        run(["ffmpeg", "-hide_banner", "-nostdin", "-y", "-loglevel", "error", "-ss", f"{start:.3f}",
             "-t", f"{end - start:.3f}", "-i", src, "-filter_complex_script", script, "-map", "[v]", "-map", "[a]",
             "-c:v", "libx264", "-preset", "veryfast", "-crf", str(crf), "-pix_fmt", "yuv420p",
             *audio_args("256k"), "-movflags", "+faststart", str(tmp)])
        finalize(tmp, out)
    finally:
        Path(script).unlink(missing_ok=True)
        tmp.unlink(missing_ok=True)

    # --- transcript recalé
    segments = []
    for seg in transcript["segments"]:
        if seg["end"] <= start or seg["start"] >= end:
            continue
        new_words = []
        for w in seg.get("words") or []:
            if w["end"] <= start or w["start"] >= end:
                continue
            ws_, we_ = remap(max(w["start"], start)), remap(min(w["end"], end))
            if we_ <= ws_:
                we_ = ws_ + 0.05
            new_words.append({**w, "start": round(ws_, 3), "end": round(we_, 3)})
        if new_words:
            segments.append({"id": len(segments), "start": new_words[0]["start"], "end": new_words[-1]["end"],
                             "text": " ".join(w["w"] for w in new_words), "words": new_words})
    data = {"language": transcript.get("language"), "duration": round(new_dur, 3),
            "engine": transcript.get("engine", "") + "+tight", "segments": segments}
    return {"transcript": data, "duration": new_dur, "removed": removed, "cuts": len(intervals) - 1}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("video")
    ap.add_argument("transcript")
    ap.add_argument("--start", type=float, default=0.0)
    ap.add_argument("--end", type=float, default=None)
    ap.add_argument("-o", "--out", required=True)
    ap.add_argument("--max-gap", type=float, default=0.45, help="pauses plus longues que ça (s) sont réduites")
    args = ap.parse_args()
    try:
        info = probe(args.video)
        end = args.end if args.end is not None else info.duration
        res = tighten_clip(args.video, load_json(args.transcript), args.start, min(end, info.duration), args.out,
                           max_gap=args.max_gap)
        tpath = str(Path(args.out).with_suffix("")) + ".transcript.json"
        save_json(tpath, res["transcript"])
        print(f"[ok] {args.out} : {res['cuts']} coupes, {res['removed']:.1f}s retirées "
              f"({res['removed'] / (end - args.start) * 100:.0f} %), durée {res['duration']:.1f}s -> {tpath}")
    except StudioError as exc:
        die(str(exc))


if __name__ == "__main__":
    main()
