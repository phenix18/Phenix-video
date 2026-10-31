#!/usr/bin/env python3
# Phenix-video — © 2026 Phenix - kcw. Tous droits réservés (voir LICENSE).
"""Voix off de remplacement (doublage) à partir d'un transcript traduit — sans API payante.

Moteurs de synthèse vocale :
  piper    100 % hors-ligne, gratuit (pip install piper-tts) ; les voix .onnx sont téléchargées
           depuis le dépôt libre rhasspy/piper-voices au premier usage
  edge     gratuit, sans clé, en ligne (pip install edge-tts) ; voix neuronales très naturelles
           (service non officiel de Microsoft : peut changer sans préavis)
  espeak   dépannage hors-ligne (espeak-ng), voix robotique

Chaque phrase traduite est synthétisée, puis ACCÉLÉRÉE si besoin (jusqu'à --max-speed) pour tenir
dans le temps de la phrase d'origine ; les phrases suivantes sont décalées si ça déborde.
L'audio original peut être supprimé (--bg none), baissé sous la voix (--bg duck), ou débarrassé
de la voix d'origine avec demucs (--separate) pour garder musique et ambiance.

Sorties (préfixe -o) :
  <prefix>.mix.wav         son final à passer à render.py --audio
  <prefix>.voice.wav       voix seule
  <prefix>.transcript.json transcript recalé sur la voix synthétique (pour les sous-titres)

Exemple :
  dub.py clip.fr.json video.mp4 --start 120 --end 200 -o out/clip1.fr --voice fr_FR-siwis-medium
"""
from __future__ import annotations

import argparse
import asyncio
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from common import StudioError, die, ensure_parent, ffmpeg, load_json, probe, run, save_json  # noqa: E402
from translate import spread_words  # noqa: E402

SR = 48000

DEFAULT_PIPER = {
    "fr": "fr_FR-siwis-medium", "en": "en_US-lessac-medium", "es": "es_ES-davefx-medium",
    "ar": "ar_JO-kareem-medium", "pt": "pt_BR-faber-medium", "de": "de_DE-thorsten-medium",
    "it": "it_IT-riccardo-x_low", "nl": "nl_NL-mls-medium",
}
DEFAULT_EDGE = {
    "fr": "fr-FR-DeniseNeural", "en": "en-US-AriaNeural", "es": "es-ES-ElviraNeural",
    "ar": "ar-SA-HamedNeural", "pt": "pt-BR-FranciscaNeural", "de": "de-DE-KatjaNeural",
    "it": "it-IT-ElsaNeural", "nl": "nl-NL-ColetteNeural",
}
# Voix par genre (hauteur moyenne vérifiée : femmes ~210-230 Hz, hommes ~100-155 Hz). À écouter avant publication.
PIPER_BY_GENDER = {
    "fr": {"female": "fr_FR-siwis-medium", "male": "fr_FR-tom-medium"},
    "en": {"female": "en_US-lessac-medium", "male": "en_US-ryan-high"},
}
EDGE_BY_GENDER = {
    "fr": {"female": "fr-FR-DeniseNeural", "male": "fr-FR-HenriNeural"},
    "en": {"female": "en-US-AriaNeural", "male": "en-US-GuyNeural"},
    "es": {"female": "es-ES-ElviraNeural", "male": "es-ES-AlvaroNeural"},
    "ar": {"female": "ar-SA-ZariyahNeural", "male": "ar-SA-HamedNeural"},
    "pt": {"female": "pt-BR-FranciscaNeural", "male": "pt-BR-AntonioNeural"},
    "de": {"female": "de-DE-KatjaNeural", "male": "de-DE-ConradNeural"},
}
EDGE_ALTERNATIVES = ("fr: fr-FR-HenriNeural (homme), fr-FR-EloiseNeural (enfant) · en: en-US-GuyNeural (homme), "
                     "en-GB-RyanNeural · ar: ar-SA-ZariyahNeural (femme) · es: es-ES-AlvaroNeural (homme)")
PIPER_ALTERNATIVES = ("fr: fr_FR-upmc-medium (homme/femme selon locuteur), fr_FR-gilles-low (homme) · "
                      "en: en_US-ryan-high (homme), en_GB-alba-medium (femme)")


# --------------------------------------------------------------------------- #
# Moteurs TTS
# --------------------------------------------------------------------------- #
def piper_voice_path(name_or_path: str) -> str:
    if name_or_path.endswith(".onnx") and Path(name_or_path).exists():
        return name_or_path
    cache = Path.home() / ".cache" / "phenix-video" / "piper"
    cache.mkdir(parents=True, exist_ok=True)
    onnx = cache / f"{name_or_path}.onnx"
    if onnx.exists() and (cache / f"{name_or_path}.onnx.json").exists():
        return str(onnx)
    try:
        region, speaker, quality = name_or_path.split("-", 2)
        lang = region.split("_")[0]
    except ValueError as exc:
        raise StudioError(f"Nom de voix Piper invalide : {name_or_path} (ex. fr_FR-siwis-medium)") from exc
    base = f"https://huggingface.co/rhasspy/piper-voices/resolve/main/{lang}/{region}/{speaker}/{quality}/{name_or_path}"
    print(f"[voix] téléchargement de {name_or_path} (une seule fois)…", file=sys.stderr)
    try:
        for suffix in (".onnx", ".onnx.json"):
            urllib.request.urlretrieve(base + suffix, cache / f"{name_or_path}{suffix}")
    except Exception as exc:  # noqa: BLE001
        for f in cache.glob(f"{name_or_path}*"):
            f.unlink(missing_ok=True)
        raise StudioError(
            f"Impossible de télécharger la voix {name_or_path} : {exc}\n"
            "Télécharge-la à la main depuis https://huggingface.co/rhasspy/piper-voices et passe --voice chemin.onnx"
        ) from exc
    return str(onnx)


def tts_piper(text: str, voice: str, speed: float, out_wav: str) -> None:
    exe = shutil.which("piper")
    cmd = [exe] if exe else [sys.executable, "-m", "piper"]
    if not exe:
        try:
            import piper  # noqa: F401
        except ImportError as exc:
            raise StudioError("Piper n'est pas installé :  pip install piper-tts") from exc
    cmd += ["--model", piper_voice_path(voice), "--output_file", out_wav,
            "--length_scale", f"{1.0 / max(0.5, speed):.3f}"]
    proc = subprocess.run(cmd, input=text, text=True, capture_output=True, encoding="utf-8")
    if proc.returncode != 0 or not Path(out_wav).exists():
        detail = (proc.stderr.strip().splitlines() or ["aucun détail"])[-1]
        raise StudioError(f"Piper a échoué : {detail}")


def tts_edge(text: str, voice: str, speed: float, out_audio: str) -> None:
    try:
        import edge_tts
    except ImportError as exc:
        raise StudioError("edge-tts n'est pas installé :  pip install edge-tts") from exc
    rate = f"{int(round((speed - 1.0) * 100)):+d}%"

    async def go():
        await edge_tts.Communicate(text, voice, rate=rate).save(out_audio)

    try:
        asyncio.run(go())
    except Exception as exc:  # noqa: BLE001 - réseau, voix inconnue…
        raise StudioError(f"edge-tts a échoué ({voice}) : {exc}") from exc


def tts_espeak(text: str, voice: str, speed: float, out_wav: str) -> None:
    exe = shutil.which("espeak-ng") or shutil.which("espeak")
    if not exe:
        raise StudioError("espeak-ng est introuvable (apt install espeak-ng / brew install espeak-ng).")
    run([exe, "-v", voice, "-s", str(int(165 * speed)), "-w", out_wav, text])


def pick_engine(requested: str) -> str:
    if requested != "auto":
        return requested
    if shutil.which("piper"):
        return "piper"
    try:
        import piper  # noqa: F401
        return "piper"
    except ImportError:
        pass
    try:
        import edge_tts  # noqa: F401
        return "edge"
    except ImportError:
        pass
    if shutil.which("espeak-ng") or shutil.which("espeak"):
        return "espeak"
    raise StudioError("Aucun moteur de voix trouvé. Installe-en un :  pip install piper-tts   (hors-ligne, conseillé)\n"
                      "ou  pip install edge-tts   (en ligne, gratuit).")


def default_voice(engine: str, lang: str, gender: str | None = None) -> str:
    code = lang[:2].lower()
    if engine == "espeak":
        return code
    if gender:
        table = (PIPER_BY_GENDER if engine == "piper" else EDGE_BY_GENDER).get(code, {})
        if gender in table:
            return table[gender]
        if engine == "piper":
            raise StudioError(
                f"Pas de voix Piper {gender} vérifiée pour '{lang}' : précise --voice, ou utilise --engine edge.")
    base = {"piper": DEFAULT_PIPER, "edge": DEFAULT_EDGE}.get(engine, {})
    voice = base.get(code)
    if not voice:
        raise StudioError(f"Pas de voix par défaut pour '{lang}' avec {engine} : précise --voice.")
    return voice


# --------------------------------------------------------------------------- #
# Audio
# --------------------------------------------------------------------------- #
_RUBBERBAND: bool | None = None


def pitch_filter(semitones: float) -> str | None:
    global _RUBBERBAND
    if abs(semitones) < 0.05:
        return None
    ratio = 2 ** (semitones / 12)
    if _RUBBERBAND is None:
        _RUBBERBAND = "rubberband" in run(["ffmpeg", "-hide_banner", "-filters"]).stdout
    if _RUBBERBAND:
        return f"rubberband=pitch={ratio:.5f}"
    return f"asetrate={SR * ratio:.1f},aresample={SR},atempo={1 / ratio:.5f}"


def atempo_chain(factor: float) -> list[str]:
    parts = []
    while factor > 2.0:
        parts.append("atempo=2.0"); factor /= 2.0
    while factor < 0.5:
        parts.append("atempo=0.5"); factor /= 0.5
    parts.append(f"atempo={factor:.4f}")
    return parts


TRIM = ("silenceremove=start_periods=1:start_duration=0:start_threshold=-45dB,areverse,"
        "silenceremove=start_periods=1:start_duration=0:start_threshold=-45dB,areverse")


def to_mono48(src: str, dest: str, pitch: float = 0.0, tempo: float = 1.0) -> None:
    chain = [TRIM]
    pf = pitch_filter(pitch)
    if pf:
        chain.append(pf)
    if tempo > 1.01:
        chain += atempo_chain(tempo)
    ffmpeg(["-i", src, "-af", ",".join(chain), "-ar", str(SR), "-ac", "1", "-c:a", "pcm_s16le", dest])


def wav_duration(path: str) -> float:
    with wave.open(path, "rb") as w:
        return w.getnframes() / w.getframerate()


def read_wav(path: str):
    import numpy as np
    with wave.open(path, "rb") as w:
        data = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768.0
    return data


def write_wav(path: str, samples) -> None:
    import numpy as np
    pcm = (np.clip(samples, -1.0, 1.0) * 32767.0).astype(np.int16)
    with wave.open(path, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes(pcm.tobytes())


# --------------------------------------------------------------------------- #
# Doublage
# --------------------------------------------------------------------------- #
def dub(transcript: dict, src: str, start: float, end: float, out_prefix: str, *, engine: str, voice: str | None,
        speed: float, pitch: float, max_speed: float, bg: str, bg_volume: float, separate: bool,
        gender: str | None = None) -> dict:
    import numpy as np

    lang = (transcript.get("language") or "").lower()
    engine = pick_engine(engine)
    voice = voice or default_voice(engine, lang, gender)
    clip_dur = end - start
    segs = [s for s in transcript["segments"] if s["end"] > start and s["start"] < end and s["text"].strip()]
    if not segs:
        raise StudioError("Aucune phrase à doubler dans cet intervalle.")
    print(f"[doublage] moteur={engine} voix={voice} phrases={len(segs)}", file=sys.stderr)

    total = int(clip_dur * SR) + SR
    track = np.zeros(total, dtype=np.float32)
    aligned = []
    cursor = 0.0
    speeds = []
    overruns = 0
    ensure_parent(out_prefix + ".x")

    with tempfile.TemporaryDirectory() as tmp:
        for i, seg in enumerate(segs):
            s0 = max(seg["start"], start) - start
            s1 = min(seg["end"], end) - start
            nxt = (max(segs[i + 1]["start"], start) - start) if i + 1 < len(segs) else clip_dur
            raw = str(Path(tmp) / f"raw{i}.{'mp3' if engine == 'edge' else 'wav'}")
            text = seg["text"].strip()
            if engine == "piper":
                tts_piper(text, voice, speed, raw)
            elif engine == "edge":
                tts_edge(text, voice, speed, raw)
            else:
                tts_espeak(text, voice, speed, raw)
            base = str(Path(tmp) / f"base{i}.wav")
            to_mono48(raw, base, pitch=pitch)
            d = wav_duration(base)
            place = max(s0, cursor)
            avail = max(0.4, min(s1 + 0.6, nxt) - place)
            factor = min(max(1.0, d / avail), max_speed)
            if factor > 1.01:
                fitted = str(Path(tmp) / f"fit{i}.wav")
                ffmpeg(["-i", base, "-af", ",".join(atempo_chain(factor)), "-ar", str(SR), "-ac", "1",
                        "-c:a", "pcm_s16le", fitted])
                base, d = fitted, wav_duration(fitted)
            speeds.append(factor)
            if d > avail + 0.05:
                overruns += 1
            samples = read_wav(base)
            a = int(place * SR)
            b = min(a + len(samples), total)
            if a < total:
                track[a:b] += samples[: b - a]
            aligned.append({"id": i, "start": round(start + place, 3), "end": round(start + place + d, 3),
                            "text": text, "src_text": seg.get("src_text"),
                            "words": spread_words(text, start + place, start + place + d)})
            cursor = place + d + 0.10

        track = track[: int(clip_dur * SR)]
        voice_wav = out_prefix + ".voice.wav"
        write_wav(voice_wav, track)

        # --- fond sonore
        mix_wav = out_prefix + ".mix.wav"
        if bg == "none":
            shutil.copyfile(voice_wav, mix_wav)
        else:
            bg_raw = str(Path(tmp) / "bg.wav")
            ffmpeg(["-ss", f"{start:.3f}", "-t", f"{clip_dur:.3f}", "-i", src, "-vn", "-ac", "2", "-ar", str(SR),
                    "-c:a", "pcm_s16le", bg_raw])
            if separate:
                bg_raw = separate_vocals(bg_raw, tmp)
            if bg == "duck":
                graph = ("[0:a]aformat=channel_layouts=stereo,asplit[v1][v2];"
                         f"[1:a]volume={bg_volume}[b];"
                         "[b][v1]sidechaincompress=threshold=0.02:ratio=10:attack=15:release=350[bd];"
                         "[v2][bd]amix=inputs=2:duration=first:normalize=0,alimiter=limit=0.95[m]")
            else:
                graph = (f"[1:a]volume={bg_volume}[b];[0:a]aformat=channel_layouts=stereo[v];"
                         "[v][b]amix=inputs=2:duration=first:normalize=0,alimiter=limit=0.95[m]")
            ffmpeg(["-i", voice_wav, "-i", bg_raw, "-filter_complex", graph, "-map", "[m]", "-ar", str(SR),
                    "-c:a", "pcm_s16le", mix_wav])

    save_json(out_prefix + ".transcript.json", {
        "language": lang, "duration": round(clip_dur, 3), "engine": f"dub:{engine}:{voice}", "segments": aligned})
    return {"engine": engine, "voice": voice, "segments": len(aligned),
            "avg_speedup": round(sum(speeds) / len(speeds), 2), "max_speedup": round(max(speeds), 2),
            "overruns": overruns, "mix": mix_wav, "voice_only": voice_wav,
            "transcript": out_prefix + ".transcript.json"}


def separate_vocals(wav: str, tmp: str) -> str:
    """Retire la voix d'origine avec demucs (pip install demucs) ; garde musique et ambiance."""
    try:
        import demucs  # noqa: F401
    except ImportError as exc:
        raise StudioError("--separate demande demucs :  pip install demucs  (gros téléchargement, CPU lent)") from exc
    out_dir = Path(tmp) / "demucs"
    run([sys.executable, "-m", "demucs", "--two-stems=vocals", "-o", str(out_dir), wav])
    found = next(out_dir.rglob("no_vocals.wav"), None)
    if not found:
        raise StudioError("demucs n'a pas produit de piste sans voix.")
    return str(found)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("transcript", nargs="?", help="transcript traduit (translate.py)")
    ap.add_argument("video", nargs="?", help="vidéo source (pour le fond sonore)")
    ap.add_argument("--start", type=float, default=0.0)
    ap.add_argument("--end", type=float, default=None)
    ap.add_argument("-o", "--out", help="préfixe de sortie, ex. out/clip1.fr")
    ap.add_argument("--engine", default="auto", choices=["auto", "piper", "edge", "espeak"])
    ap.add_argument("--voice", default=None, help="nom ou chemin de voix (voir --list-voices)")
    ap.add_argument("--gender", default=None, choices=["female", "male"], help="voix féminine ou masculine (fr, en…)")
    ap.add_argument("--speed", type=float, default=1.0, help="débit de base du moteur (1.0 = normal)")
    ap.add_argument("--pitch", type=float, default=0.0, help="décalage de hauteur en demi-tons (-3 = plus grave)")
    ap.add_argument("--max-speed", type=float, default=1.35, help="accélération maximale pour tenir dans le temps")
    ap.add_argument("--bg", default="duck", choices=["none", "duck", "keep"],
                    help="son d'origine sous la voix : none | duck (baissé auto) | keep")
    ap.add_argument("--bg-volume", type=float, default=0.18)
    ap.add_argument("--separate", action="store_true", help="retire la voix d'origine (demucs), garde la musique")
    ap.add_argument("--list-voices", action="store_true")
    args = ap.parse_args()
    try:
        if args.list_voices:
            print("Par genre (Piper) :", PIPER_BY_GENDER)
            print("Par genre (Edge)  :", EDGE_BY_GENDER)
            print("Piper (hors-ligne) par défaut :", DEFAULT_PIPER)
            print("  alternatives :", PIPER_ALTERNATIVES)
            print("Edge (en ligne, gratuit) par défaut :", DEFAULT_EDGE)
            print("  alternatives :", EDGE_ALTERNATIVES)
            print("Catalogue complet Piper : https://huggingface.co/rhasspy/piper-voices · Edge : `edge-tts --list-voices`")
            return
        if not (args.transcript and args.video and args.out):
            ap.error("transcript, video et -o sont requis")
        data = load_json(args.transcript)
        info = probe(args.video)
        end = args.end if args.end is not None else (data.get("duration") or info.duration)
        rep = dub(data, args.video, args.start, min(end, info.duration), args.out, engine=args.engine,
                  voice=args.voice, speed=args.speed, pitch=args.pitch, max_speed=args.max_speed, bg=args.bg,
                  bg_volume=args.bg_volume, separate=args.separate, gender=args.gender)
        print(f"[ok] voix {rep['voice']} ({rep['engine']}), {rep['segments']} phrases, "
              f"accélération moy. x{rep['avg_speedup']} / max x{rep['max_speedup']}, débordements : {rep['overruns']}")
        print(f"     audio final : {rep['mix']}")
        if rep["overruns"]:
            print("[conseil] Des phrases débordent : raccourcis la traduction (translate.py --engine manual) "
                  "ou monte --max-speed.", file=sys.stderr)
    except StudioError as exc:
        die(str(exc))


if __name__ == "__main__":
    main()
