#!/usr/bin/env python3
# Phenix-video — © 2026 Phenix - kcw. Tous droits réservés (voir LICENSE).
"""Transcription locale avec horodatage mot à mot (gratuit, hors-ligne après le 1er téléchargement).

Moteur : faster-whisper (pip install faster-whisper). Aucune clé API.
Alternative : importer un .srt / .vtt existant (--import-subs) ; les mots sont alors estimés.

Sortie : transcript.json
{
  "language": "fr", "duration": 123.4, "engine": "faster-whisper:small",
  "segments": [{"id": 0, "start": 0.0, "end": 3.2, "text": "...",
                "words": [{"w": "Bonjour", "start": 0.1, "end": 0.5, "p": 0.98}]}]
}
"""
from __future__ import annotations

import argparse
import re
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from common import StudioError, die, ffmpeg, probe, save_json, ensure_parent  # noqa: E402


def extract_audio(src: str, dest: str) -> None:
    ffmpeg(["-i", src, "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", dest])


def transcribe_whisper(src: str, model: str, language: str | None, device: str,
                       compute_type: str, beam: int, vad: bool, initial_prompt: str | None) -> dict:
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise StudioError(
            "faster-whisper n'est pas installé.\n"
            "  pip install faster-whisper\n"
            "Ou fournis des sous-titres existants : --import-subs fichier.srt"
        ) from exc

    info = probe(src)
    if not info.has_audio:
        raise StudioError("Cette vidéo n'a pas de piste audio : rien à transcrire.")

    with tempfile.TemporaryDirectory() as tmp:
        wav = str(Path(tmp) / "audio.wav")
        extract_audio(src, wav)
        print(f"[transcription] modèle={model} device={device} compute={compute_type}", file=sys.stderr)
        import wave

        import numpy as np
        with wave.open(wav, "rb") as fh:  # on passe un tableau numpy : évite les soucis de version de PyAV
            audio = np.frombuffer(fh.readframes(fh.getnframes()), dtype=np.int16).astype(np.float32) / 32768.0
        try:
            engine = WhisperModel(model, device=device, compute_type=compute_type)
        except Exception as exc:  # noqa: BLE001 - modèle introuvable, réseau, CUDA…
            raise StudioError(
                f"Impossible de charger le modèle Whisper '{model}' : {exc}\n"
                "Au premier usage il est téléchargé depuis Hugging Face (connexion nécessaire). "
                "Sans GPU, garde --device cpu --compute-type int8.") from exc
        segments_iter, meta = engine.transcribe(
            audio,
            language=language,
            beam_size=beam,
            word_timestamps=True,
            vad_filter=vad,
            vad_parameters={"min_silence_duration_ms": 400},
            initial_prompt=initial_prompt,
            condition_on_previous_text=False,  # évite les boucles de répétition
        )
        segments = []
        for idx, seg in enumerate(segments_iter):
            words = [
                {"w": w.word.strip(), "start": round(w.start, 3), "end": round(w.end, 3),
                 "p": round(float(w.probability), 3)}
                for w in (seg.words or []) if w.word.strip()
            ]
            segments.append({
                "id": idx, "start": round(seg.start, 3), "end": round(seg.end, 3),
                "text": seg.text.strip(), "words": words,
            })
            print(f"\r[transcription] {seg.end:7.1f}s / {info.duration:.0f}s", end="", file=sys.stderr)
        print(file=sys.stderr)
    return {
        "language": meta.language, "duration": round(info.duration, 3),
        "engine": f"faster-whisper:{model}", "segments": segments,
    }


# --------------------------------------------------------------------------- #
# Import SRT / VTT
# --------------------------------------------------------------------------- #
_CUE = re.compile(
    r"(?P<a>\d{1,2}:\d{2}:\d{2}[.,]\d{1,3}|\d{1,2}:\d{2}[.,]\d{1,3})\s*-->\s*"
    r"(?P<b>\d{1,2}:\d{2}:\d{2}[.,]\d{1,3}|\d{1,2}:\d{2}[.,]\d{1,3})"
)


def _to_seconds(text: str) -> float:
    text = text.replace(",", ".")
    parts = text.split(":")
    parts = [float(p) for p in parts]
    while len(parts) < 3:
        parts.insert(0, 0.0)
    return parts[0] * 3600 + parts[1] * 60 + parts[2]


def import_subtitles(path: str, language: str | None, duration: float | None) -> dict:
    raw = Path(path).read_text(encoding="utf-8-sig", errors="replace")
    blocks = re.split(r"\n\s*\n", raw.replace("\r\n", "\n"))
    segments = []
    for block in blocks:
        lines = [ln for ln in block.strip().splitlines() if ln.strip()]
        for i, line in enumerate(lines):
            m = _CUE.search(line)
            if not m:
                continue
            start, end = _to_seconds(m.group("a")), _to_seconds(m.group("b"))
            text = re.sub(r"<[^>]+>|\{[^}]*\}", "", " ".join(lines[i + 1:])).strip()
            if not text or end <= start:
                break
            tokens = text.split()
            total_chars = sum(len(t) for t in tokens) or 1
            cursor, words = start, []
            for tok in tokens:  # répartition proportionnelle à la longueur du mot
                span = (end - start) * len(tok) / total_chars
                words.append({"w": tok, "start": round(cursor, 3), "end": round(cursor + span, 3),
                              "p": 0.5, "estimated": True})
                cursor += span
            segments.append({"id": len(segments), "start": round(start, 3), "end": round(end, 3),
                             "text": text, "words": words})
            break
    if not segments:
        raise StudioError(f"Aucun sous-titre lisible dans {path}")
    return {
        "language": language or "und",
        "duration": round(duration or segments[-1]["end"], 3),
        "engine": "import-subs", "segments": segments,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("input", help="vidéo ou audio source")
    ap.add_argument("-o", "--out", default=None, help="transcript.json (défaut : <input>.transcript.json)")
    ap.add_argument("--model", default="small",
                    help="tiny|base|small|medium|large-v3|distil-large-v3 (défaut small ; medium conseillé pour le français)")
    ap.add_argument("--lang", default=None, help="fr, en, ar… (défaut : détection automatique)")
    ap.add_argument("--device", default="auto", help="auto|cpu|cuda")
    ap.add_argument("--compute-type", default="int8", help="int8 (CPU) | float16 (GPU)")
    ap.add_argument("--beam", type=int, default=5)
    ap.add_argument("--no-vad", action="store_true", help="désactive le filtre de silence")
    ap.add_argument("--prompt", default=None, help="vocabulaire/noms propres pour guider le modèle")
    ap.add_argument("--import-subs", default=None, help="importe un .srt/.vtt au lieu de transcrire")
    args = ap.parse_args()

    try:
        out = args.out or str(Path(args.input).with_suffix("")) + ".transcript.json"
        if args.import_subs:
            dur = None
            try:
                dur = probe(args.input).duration
            except StudioError:
                pass
            data = import_subtitles(args.import_subs, args.lang, dur)
        else:
            data = transcribe_whisper(args.input, args.model, args.lang, args.device,
                                      args.compute_type, args.beam, not args.no_vad, args.prompt)
        ensure_parent(out)
        save_json(out, data)
        n_words = sum(len(s["words"]) for s in data["segments"])
        print(f"[ok] {len(data['segments'])} segments, {n_words} mots -> {out}")
    except StudioError as exc:
        die(str(exc))


if __name__ == "__main__":
    main()
