#!/usr/bin/env python3
# Phenix-video — © 2026 Phenix - kcw. Tous droits réservés (voir LICENSE).
"""Pipeline complet « longue vidéo -> clips verticaux 1080p » (extraction automatique), en local et gratuit.

Étapes : transcription -> meilleurs moments -> [traduction] -> [voix off] -> cadrage intelligent
         -> sous-titres animés -> export 1080p + miniature + rapport.

Deux temps possibles (recommandé quand la qualité compte) :
  1) pipeline.py video.mp4 -o out --stop-after clips      # on relit/ajuste out/clips.json
  2) pipeline.py video.mp4 -o out --clips-file out/clips.json   # rendu des clips validés

Exemples :
  pipeline.py talk.mp4 -o out --clips 5 --lang en --style pop
  pipeline.py talk.mp4 -o out --translate-to fr                    # sous-titres traduits, voix d'origine
  pipeline.py talk.mp4 -o out --translate-to fr --dub --voice fr_FR-siwis-medium   # voix off française
  pipeline.py podcast.mp4 -o out --short --aspect 9:16 --mode blur
"""
from __future__ import annotations

import argparse
import sys
import time
from argparse import Namespace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import captions  # noqa: E402
import dub as dubmod  # noqa: E402
import edit  # noqa: E402
import fetch  # noqa: E402
import highlights  # noqa: E402
import polish  # noqa: E402
import transcribe as trans  # noqa: E402
import translate as tr  # noqa: E402
from common import StudioError, die, load_json, probe, save_json, slugify  # noqa: E402
from render import QUALITY, out_size_for, render_clip  # noqa: E402


def fmt_dur(sec: float) -> str:
    m, s = divmod(int(round(sec)), 60)
    return f"{m}:{s:02d}"


def normalize_clips(clips: list[dict], total: float) -> list[dict]:
    """Complète/valide les clips (un clips.json édité à la main peut omettre id, titre ou durée)."""
    out = []
    for n, c in enumerate(clips, 1):
        if "start" not in c or "end" not in c:
            raise StudioError(f"Clip #{n} : 'start' et 'end' sont obligatoires.")
        start, end = float(c["start"]), min(float(c["end"]), total)
        if start < 0 or end - start < 1.0:
            raise StudioError(f"Clip #{n} : intervalle invalide ({c['start']} → {c['end']}).")
        out.append({**c, "id": int(c.get("id", n)), "start": round(start, 2), "end": round(end, 2),
                    "duration": round(end - start, 2), "title": c.get("title") or f"Clip {n}"})
    if not out:
        raise StudioError("clips.json ne contient aucun clip.")
    return out


def get_transcript(args, out_dir: Path) -> dict:
    path = Path(args.transcript) if args.transcript else out_dir / "transcript.json"
    if path.exists():
        print(f"[1/5] transcript existant : {path}", file=sys.stderr)
        return load_json(path)
    if args.import_subs:
        print("[1/5] import des sous-titres…", file=sys.stderr)
        data = trans.import_subtitles(args.import_subs, args.lang, probe(args.input).duration)
    else:
        print("[1/5] transcription (faster-whisper)…", file=sys.stderr)
        data = trans.transcribe_whisper(args.input, args.model, args.lang, args.device, "int8", 5, True, None)
    save_json(path, data)
    return data


def translated_transcript(transcript: dict, args, clip: dict, prefix: Path) -> dict | None:
    """Traduit les phrases du clip. Retourne None si on attend une traduction manuelle."""
    dst = args.translate_to
    units = tr.select_units(transcript, clip["start"], clip["end"])
    src = (transcript.get("language") or args.lang or "").lower()
    if args.translate_engine == "manual":
        src_json, tr_json = Path(f"{prefix}.to_translate.json"), Path(f"{prefix}.translated.json")
        if not tr_json.exists():
            save_json(src_json, [{"id": i, "start": round(u.start, 2), "end": round(u.end, 2),
                                  "max_words_hint": max(3, int((u.end - u.start) * 3.0)), "text": u.text}
                                 for i, u in enumerate(units)])
            return None
        items = {int(x["id"]): str(x["text"]).strip() for x in load_json(tr_json)}
        missing = [i for i in range(len(units)) if not items.get(i)]
        if missing:
            raise StudioError(f"{tr_json} : traductions manquantes pour les id {missing[:8]}")
        texts = [items[i] for i in range(len(units))]
    else:
        if not src or src == "und":
            raise StudioError("Langue source inconnue : ajoute --lang.")
        texts = tr.argos_translate([u.text for u in units], src, dst)
    segs = [{"id": i, "start": round(u.start, 3), "end": round(u.end, 3), "text": t, "src_text": u.text,
             "words": tr.spread_words(t, u.start, u.end)} for i, (u, t) in enumerate(zip(units, texts))]
    data = {"language": dst, "source_language": src, "duration": transcript.get("duration"),
            "engine": f"translate:{args.translate_engine}", "segments": segs}
    save_json(f"{prefix}.{dst}.json", data)
    return data


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("input", help="fichier vidéo OU lien (YouTube, TikTok, Instagram, X, Vimeo, .mp4 direct…)")
    ap.add_argument("-o", "--out", required=True, help="dossier de sortie")
    ap.add_argument("--max-height", type=int, default=1080, help="si lien : hauteur max téléchargée (1080 ; 2160 pour la 4K)")
    ap.add_argument("--cookies-from-browser", default=None, help="si lien privé/limité : chrome|firefox|edge")
    g = ap.add_argument_group("sélection des clips")
    g.add_argument("--clips", type=int, default=5)
    g.add_argument("--min", dest="min_len", type=float, default=75.0, help="durée min (s), défaut 75 = 1 min 15")
    g.add_argument("--max", dest="max_len", type=float, default=180.0)
    g.add_argument("--target", type=float, default=100.0)
    g.add_argument("--short", action="store_true", help="clips 20-60 s")
    g.add_argument("--clips-file", default=None, help="réutilise un clips.json (relu/édité) au lieu de détecter")
    g.add_argument("--stop-after", choices=["clips"], default=None)
    g.add_argument("--lexicon", default=None)
    t = ap.add_argument_group("transcription")
    t.add_argument("--transcript", default=None)
    t.add_argument("--import-subs", default=None)
    t.add_argument("--lang", default=None)
    t.add_argument("--model", default="small")
    t.add_argument("--device", default="auto")
    l = ap.add_argument_group("traduction & voix off")
    l.add_argument("--translate-to", default=None, help="fr, en, es, ar…")
    l.add_argument("--translate-engine", default="argos", choices=["argos", "manual"])
    l.add_argument("--dub", action="store_true", help="remplace la voix par une voix de synthèse (nécessite --translate-to)")
    l.add_argument("--tts-engine", default="auto", choices=["auto", "piper", "edge", "espeak"])
    l.add_argument("--voice", default=None, help="nom précis de voix (sinon choisie selon --voice-gender)")
    l.add_argument("--voice-gender", default="female", choices=["female", "male", "both"],
                   help="voix féminine, masculine, ou both = une version de chaque (clip_F.mp4 / clip_M.mp4)")
    l.add_argument("--pitch", type=float, default=0.0)
    l.add_argument("--bg", default="duck", choices=["none", "duck", "keep"])
    l.add_argument("--separate", action="store_true")
    v = ap.add_argument_group("rendu")
    v.add_argument("--tighten", action="store_true",
                   help="resserre le rythme : coupe les temps morts entre les mots (jump-cuts), transcript recalé")
    v.add_argument("--max-gap", type=float, default=0.45, help="avec --tighten : pauses plus longues (s) réduites")
    v.add_argument("--aspect", default="9:16")
    v.add_argument("--mode", default="auto", choices=["auto", "track", "center", "blur", "fit", "none"])
    v.add_argument("--style", default="pop", choices=list(captions.STYLES))
    v.add_argument("--no-captions", action="store_true")
    v.add_argument("--font", default=None)
    v.add_argument("--highlight", default=None)
    v.add_argument("--quality", default="high", choices=list(QUALITY))
    v.add_argument("--no-thumbnails", action="store_true")
    args = ap.parse_args()

    started = time.time()
    try:
        if args.dub and not args.translate_to:
            raise StudioError("--dub demande --translate-to <langue>.")
        if args.short:
            args.min_len, args.max_len, args.target = 20.0, 60.0, 40.0
        out_dir = Path(args.out)
        out_dir.mkdir(parents=True, exist_ok=True)
        if fetch.is_url(args.input):
            print("[0/5] téléchargement du lien…", file=sys.stderr)
            meta = fetch.download(args.input, str(out_dir / "source"), args.max_height, args.cookies_from_browser)
            print(f"      {meta['title']} — {meta['width']}x{meta['height']}, {meta['duration']:.0f}s", file=sys.stderr)
            args.input = meta["path"]
        info = probe(args.input)
        tw, th = out_size_for(args.aspect)
        print(f"Source : {info.width}x{info.height} @ {info.fps:.0f} fps, {fmt_dur(info.duration)} · "
              f"sortie {tw}x{th} ({args.quality})", file=sys.stderr)

        transcript = get_transcript(args, out_dir)

        if args.clips_file:
            clips = normalize_clips(load_json(args.clips_file)["clips"], info.duration)
            print(f"[2/5] {len(clips)} clips lus depuis {args.clips_file}", file=sys.stderr)
        else:
            print("[2/5] recherche des meilleurs moments…", file=sys.stderr)
            extra = set()
            if args.lexicon:
                extra = {x.strip().lower() for x in Path(args.lexicon).read_text(encoding="utf-8").splitlines() if x.strip()}
            clips = highlights.find_clips(transcript, args.clips, args.min_len, args.max_len, args.target, extra,
                                          args.input, 2.0, 0.2, 0.4, info.duration)
            save_json(out_dir / "clips.json", {"source": args.input, "language": transcript.get("language"), "clips": clips})
        for c in clips:
            print(f"   #{c['id']:<2} {fmt_dur(c['start'])}–{fmt_dur(c['end'])} ({c['duration']:.0f}s) "
                  f"score {(c.get('score') or 0):.0f}  {c.get('title', '')}", file=sys.stderr)
        if args.stop_after == "clips":
            print(f"[ok] sélection écrite : {out_dir / 'clips.json'}  (modifie start/end/title puis relance avec --clips-file)")
            return

        variants = [None]
        if args.dub and not args.voice:
            variants = ["female", "male"] if args.voice_gender == "both" else [args.voice_gender]
        results, pending = [], []
        for n, clip in enumerate(clips, 1):
            name = f"clip_{clip.get('id', n):02d}_{slugify(clip.get('title', 'clip'), 32)}"
            prefix = out_dir / name
            print(f"[3/5] clip {n}/{len(clips)} : {name}", file=sys.stderr)
            base_row = {"id": clip.get("id", n), "title": clip.get("title"), "start": clip["start"],
                        "end": clip["end"], "score": clip.get("score")}
            try:
                work_src, work_clip, work_tr = args.input, clip, transcript
                if args.tighten:
                    res = polish.tighten_clip(args.input, transcript, clip["start"], clip["end"],
                                              str(prefix) + ".tight.mp4", max_gap=args.max_gap)
                    save_json(str(prefix) + ".tight.transcript.json", res["transcript"])
                    work_src, work_tr = str(prefix) + ".tight.mp4", res["transcript"]
                    work_clip = {**clip, "start": 0.0, "end": round(res["duration"], 3),
                                 "duration": round(res["duration"], 3)}
                    base_row["tightened"] = {"cuts": res["cuts"], "removed_s": round(res["removed"], 1)}
                    print(f"   resserrage : {res['cuts']} coupes, -{res['removed']:.1f}s", file=sys.stderr)

                td = None
                if args.translate_to:
                    td = translated_transcript(work_tr, args, work_clip, prefix)
                    if td is None:
                        pending.append(name)
                        results.append({**base_row, "status": "en attente de traduction"})
                        continue

                for gender in variants:
                    row = dict(base_row)
                    suffix = "" if len(variants) == 1 else ("_F" if gender == "female" else "_M")
                    vprefix = Path(str(prefix) + suffix)
                    audio_override, cap_tr = None, (td or work_tr)
                    if args.dub:
                        rep = dubmod.dub(td, work_src, work_clip["start"], work_clip["end"], str(vprefix),
                                         engine=args.tts_engine, voice=args.voice, speed=1.0, pitch=args.pitch,
                                         max_speed=1.35, bg=args.bg, bg_volume=0.18, separate=args.separate,
                                         gender=gender)
                        audio_override, cap_tr = rep["mix"], load_json(rep["transcript"])
                        row["dub"] = {k: rep[k] for k in ("voice", "engine", "avg_speedup", "overruns")}
                        row["synthetic_voice"] = True

                    ass_path = None
                    if not args.no_captions:
                        words = captions.clip_words(cap_tr, work_clip["start"], work_clip["end"])
                        if words:
                            ass_path = str(vprefix) + ".ass"
                            Path(ass_path).write_text(
                                captions.build_ass(words, args.style, tw, th, args.font, args.highlight),
                                encoding="utf-8")
                    out = str(vprefix) + ".mp4"
                    rep = render_clip(work_src, work_clip["start"], work_clip["end"], out, aspect=args.aspect,
                                      mode=args.mode, ass=ass_path, audio_override=audio_override,
                                      quality=args.quality, verbose=False)
                    row.update({"file": out, "mode": rep["mode"], "size": rep["size"], "status": "ok",
                                "duration": round(work_clip["end"] - work_clip["start"], 1)})
                    if rep.get("warning"):
                        row["warning"] = rep["warning"]
                    if not args.no_thumbnails:
                        try:
                            edit.cmd_thumbnail(Namespace(input=out, out=str(vprefix) + ".jpg", start="0", end=None,
                                                         width=1080, quality="high"))
                            row["thumbnail"] = str(vprefix) + ".jpg"
                        except Exception as exc:  # noqa: BLE001 - la miniature est un bonus
                            row["thumbnail_error"] = str(exc)
                    results.append(row)
            except StudioError as exc:
                results.append({**base_row, "status": f"échec : {exc}"})
                print(f"   [échec] {exc}", file=sys.stderr)

        save_json(out_dir / "report.json", {"source": args.input, "clips": results})
        lines = [f"# Rapport — {Path(args.input).name}", ""]
        for r in results:
            extra = f" ({r['duration']}s)" if r.get("duration") else ""
            lines.append(f"- **#{r['id']} {r.get('title')}** — {r['status']}{extra}"
                         + (f" — `{r['file']}`" if r.get("file") else ""))
            if r.get("dub"):
                lines.append(f"  - voix : {r['dub']['voice']} ({r['dub']['engine']}), accélération moy. x{r['dub']['avg_speedup']}")
            if r.get("tightened"):
                lines.append(f"  - resserrage : {r['tightened']['cuts']} coupes, -{r['tightened']['removed_s']}s")
            if r.get("warning"):
                lines.append(f"  - ⚠ {r['warning']}")
        lines += ["", "## Avant de publier", "",
                  "- Vérifier que tu as les droits de réutiliser cette vidéo (ou l'accord de son auteur).",
                  "- Regarder chaque clip en entier : cadrage, sous-titres, traduction, voix.",
                  "- Voir `references/platform-guidelines.md` (étiquette « contenu généré par IA », originalité, musique)."]
        if any(r.get("synthetic_voice") for r in results):
            lines.append("- **Voix de synthèse utilisée** : activer l'étiquette de contenu généré/modifié par IA "
                         "sur TikTok / YouTube quand la plateforme l'exige.")
        (out_dir / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

        done = sum(1 for r in results if r["status"] == "ok")
        print(f"[5/5] {done}/{len(results)} clips prêts dans {out_dir} ({time.time() - started:.0f}s)")
        if pending:
            print("\nTraduction manuelle requise. Pour chaque clip, traduis <clip>.to_translate.json vers "
                  f"'{args.translate_to}' et enregistre-le en <clip>.translated.json ([{{\"id\":0,\"text\":\"…\"}}]) :")
            for name in pending:
                print(f"  - {out_dir / name}.to_translate.json")
            print("puis relance la même commande.")
    except StudioError as exc:
        die(str(exc))


if __name__ == "__main__":
    main()
