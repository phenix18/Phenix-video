#!/usr/bin/env python3
# Phenix-video — © 2026 Phenix - kcw. Tous droits réservés (voir LICENSE).
"""Boîte à outils de montage de montage mobile, 100 % ffmpeg (gratuit, local).

Sous-commandes :
  trim        couper un passage                         edit.py trim in.mp4 -o out.mp4 --start 5 --end 20
  concat      assembler + transitions (xfade)           edit.py concat a.mp4 b.mp4 -o out.mp4 --xfade fade
  speed       accélérer / ralentir (son compris)        edit.py speed in.mp4 -o out.mp4 --factor 1.25
  silence     jump-cuts : supprime les blancs           edit.py silence in.mp4 -o out.mp4
  music       musique de fond avec ducking auto         edit.py music in.mp4 --track bg.mp3 -o out.mp4
  text        titre animé (fondu) sur une plage         edit.py text in.mp4 -o out.mp4 --text "Mon titre"
  punch       zooms d'emphase (punch-in)                edit.py punch in.mp4 -o out.mp4 --at 3.2,9.5
  voice       changeur de voix (hauteur / effets)       edit.py voice in.mp4 -o out.mp4 --preset deep
  loudnorm    normalise le volume (-14 LUFS)            edit.py loudnorm in.mp4 -o out.mp4
  burn        incruster des sous-titres .srt/.ass       edit.py burn in.mp4 --subs s.srt -o out.mp4
  logo        filigrane / logo                          edit.py logo in.mp4 --image logo.png -o out.mp4
  delogo      masquer TON logo / ta marque (flou, fondu ou cache)   edit.py delogo in.mp4 -o out.mp4 --area br
  stabilize   stabilisation (vidstab, 2 passes)         edit.py stabilize in.mp4 -o out.mp4
  thumbnail   meilleure image de couverture             edit.py thumbnail in.mp4 -o cover.jpg
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from common import (StudioError, audio_args, die, ensure_parent, escape_filter_path, ffmpeg, finalize,  # noqa: E402
                    need_binary, parse_size, parse_time, probe, run, temp_sibling)
from render import QUALITY  # noqa: E402


def enc(quality: str) -> list[str]:
    crf, preset, _ = QUALITY[quality]
    return ["-c:v", "libx264", "-preset", preset, "-crf", str(crf), "-profile:v", "high", "-pix_fmt", "yuv420p",
            "-movflags", "+faststart"]


def aenc(quality: str) -> list[str]:
    return audio_args(QUALITY[quality][2])


def out_ffmpeg(args: list, out: str) -> None:
    """Écrit dans un fichier temporaire puis renomme : jamais de sortie tronquée."""
    ensure_parent(out)
    tmp = temp_sibling(out)
    try:
        ffmpeg([*args, str(tmp)])
        finalize(tmp, out)
    finally:
        tmp.unlink(missing_ok=True)
    print(f"[ok] {out}")


def atempo_chain(factor: float) -> str:
    parts = []
    while factor > 2.0:
        parts.append("atempo=2.0"); factor /= 2.0
    while factor < 0.5:
        parts.append("atempo=0.5"); factor /= 0.5
    parts.append(f"atempo={factor:.4f}")
    return ",".join(parts)


def default_font() -> str | None:
    for query in ("Inter:bold", "DejaVu Sans:bold", "Arial:bold", "sans-serif:bold"):
        proc = subprocess.run(["fc-match", "-f", "%{file}", query], capture_output=True, text=True)
        if proc.returncode == 0 and proc.stdout and Path(proc.stdout).exists():
            return proc.stdout
    return None


# --------------------------------------------------------------------------- #
def cmd_trim(a):
    info = probe(a.input)
    start = parse_time(a.start)
    end = parse_time(a.end) if a.end else info.duration
    if end <= start:
        raise StudioError("--end doit être supérieur à --start")
    if a.copy:  # instantané mais coupe sur image clé
        out_ffmpeg(["-ss", f"{start}", "-to", f"{end}", "-i", a.input, "-c", "copy", "-avoid_negative_ts", "make_zero"], a.out)
    else:
        out_ffmpeg(["-ss", f"{start}", "-t", f"{end - start}", "-i", a.input, *enc(a.quality), *aenc(a.quality)], a.out)


def cmd_concat(a):
    if len(a.inputs) < 2:
        raise StudioError("concat demande au moins 2 fichiers.")
    infos = [probe(p) for p in a.inputs]
    W, H = parse_size(a.size) if a.size else (infos[0].width - infos[0].width % 2, infos[0].height - infos[0].height % 2)
    fps = a.fps or (infos[0].fps if 24 <= infos[0].fps <= 60 else 30)
    xd = a.xfade_duration if a.xfade else 0.0
    for inf in infos:
        if xd and inf.duration < xd * 2.5:
            raise StudioError(f"{inf.path} est trop court pour une transition de {xd}s.")
    chains, vl, al = [], [], []
    for i, inf in enumerate(infos):
        chains.append(f"[{i}:v]scale={W}:{H}:force_original_aspect_ratio=decrease:flags=lanczos,"
                      f"pad={W}:{H}:(ow-iw)/2:(oh-ih)/2:black,setsar=1,fps={fps:g},format=yuv420p[v{i}]")
        if inf.has_audio:
            chains.append(f"[{i}:a]aresample=48000,aformat=channel_layouts=stereo,asetpts=PTS-STARTPTS[a{i}]")
        else:
            chains.append(f"anullsrc=r=48000:cl=stereo,atrim=duration={inf.duration:.3f}[a{i}]")
        vl.append(f"[v{i}]"); al.append(f"[a{i}]")
    if xd:
        merged = infos[0].duration
        cur_v, cur_a = "[v0]", "[a0]"
        for k in range(1, len(infos)):
            off = merged - xd
            chains.append(f"{cur_v}[v{k}]xfade=transition={a.xfade}:duration={xd}:offset={off:.3f}[xv{k}]")
            chains.append(f"{cur_a}[a{k}]acrossfade=d={xd}[xa{k}]")
            cur_v, cur_a = f"[xv{k}]", f"[xa{k}]"
            merged += infos[k].duration - xd
        maps = ["-map", cur_v, "-map", cur_a]
    else:
        chains.append("".join(x for pair in zip(vl, al) for x in pair) + f"concat=n={len(infos)}:v=1:a=1[v][a]")
        maps = ["-map", "[v]", "-map", "[a]"]
    inputs = [x for p in a.inputs for x in ("-i", p)]
    out_ffmpeg([*inputs, "-filter_complex", ";".join(chains), *maps, *enc(a.quality), *aenc(a.quality)], a.out)


def cmd_speed(a):
    if not 0.25 <= a.factor <= 4.0:
        raise StudioError("--factor doit être entre 0.25 et 4.")
    info = probe(a.input)
    args = ["-i", a.input, "-vf", f"setpts=PTS/{a.factor}"]
    if info.has_audio:
        args += ["-af", atempo_chain(a.factor)]
    out_ffmpeg([*args, *enc(a.quality), *(aenc(a.quality) if info.has_audio else [])], a.out)


def detect_silences(path: str, threshold: str, min_silence: float) -> list[tuple[float, float | None]]:
    proc = subprocess.run(["ffmpeg", "-nostdin", "-hide_banner", "-i", path, "-vn", "-af",
                           f"silencedetect=noise={threshold}:d={min_silence}", "-f", "null", "-"],
                          capture_output=True, text=True, errors="replace")
    spans, cur = [], None
    for line in proc.stderr.splitlines():
        m = re.search(r"silence_start: (-?[\d.]+)", line)
        if m:
            cur = max(0.0, float(m.group(1)))
        m = re.search(r"silence_end: (-?[\d.]+)", line)
        if m and cur is not None:
            spans.append((cur, float(m.group(1)))); cur = None
    if cur is not None:
        spans.append((cur, None))
    return spans


def cmd_silence(a):
    info = probe(a.input)
    if not info.has_audio:
        raise StudioError("Pas de piste audio : impossible de détecter les silences.")
    silences = detect_silences(a.input, a.threshold, a.min_silence)
    keep, cursor = [], 0.0
    for s, e in silences:
        s_cut, e_cut = s + a.pad, (e - a.pad if e is not None else info.duration)
        if e_cut - s_cut < 0.15:
            continue
        if s_cut > cursor:
            keep.append((cursor, s_cut))
        cursor = e_cut if e is not None else info.duration
    if cursor < info.duration - 0.05:
        keep.append((cursor, info.duration))
    keep = [(s, e) for s, e in keep if e - s > 0.12]
    if not keep:
        raise StudioError("Tout est détecté comme silence : baisse --threshold (ex. -45dB).")
    removed = info.duration - sum(e - s for s, e in keep)
    lines = []
    for i, (s, e) in enumerate(keep):
        lines.append(f"[0:v]trim=start={s:.3f}:end={e:.3f},setpts=PTS-STARTPTS[v{i}]")
        lines.append(f"[0:a]atrim=start={s:.3f}:end={e:.3f},asetpts=PTS-STARTPTS[a{i}]")
    joined = "".join(f"[v{i}][a{i}]" for i in range(len(keep)))
    lines.append(f"{joined}concat=n={len(keep)}:v=1:a=1[v][a]")
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as fh:
        fh.write(";\n".join(lines))
        script = fh.name
    try:
        out_ffmpeg(["-i", a.input, "-filter_complex_script", script, "-map", "[v]", "-map", "[a]",
                    *enc(a.quality), *aenc(a.quality)], a.out)
    finally:
        Path(script).unlink(missing_ok=True)
    print(f"     {len(keep)} segments gardés, {removed:.1f}s de silence retirées ({removed / info.duration * 100:.0f} %)")


def cmd_music(a):
    info = probe(a.input)
    d = info.duration
    fade_out = min(2.5, d / 4)
    music = f"[1:a]volume={a.volume},afade=t=in:st=0:d=1.0,afade=t=out:st={d - fade_out:.2f}:d={fade_out:.2f}," \
            f"aformat=channel_layouts=stereo,aresample=48000,atrim=0:{d:.3f}[m]"
    if info.has_audio and a.duck:
        graph = (f"[0:a]aformat=channel_layouts=stereo,aresample=48000,asplit[v1][v2];{music};"
                 "[m][v1]sidechaincompress=threshold=0.03:ratio=8:attack=20:release=400[md];"
                 "[v2][md]amix=inputs=2:duration=first:normalize=0,alimiter=limit=0.95[aout]")
    elif info.has_audio:
        graph = (f"[0:a]aformat=channel_layouts=stereo,aresample=48000[v];{music};"
                 "[v][m]amix=inputs=2:duration=first:normalize=0,alimiter=limit=0.95[aout]")
    else:
        graph = music.replace("[m]", "[aout]")
    out_ffmpeg(["-i", a.input, "-stream_loop", "-1", "-i", a.track, "-filter_complex", graph, "-map", "0:v",
                "-map", "[aout]", "-c:v", "copy", *aenc(a.quality), "-t", f"{d:.3f}", "-movflags", "+faststart"], a.out)


def cmd_text(a):
    info = probe(a.input)
    start = parse_time(a.start)
    end = parse_time(a.end) if a.end else min(info.duration, start + 3.0)
    font = a.font or default_font()
    if not font:
        raise StudioError("Aucune police trouvée : passe --font chemin.ttf")
    y = {"top": "h*0.12", "center": "(h-text_h)/2", "bottom": "h*0.70"}[a.position]
    size = a.size or max(28, int(info.height * 0.05))
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as fh:
        fh.write(a.text.replace("\\n", "\n"))
        txt = fh.name
    alpha = f"if(lt(t,{start}+0.25),(t-{start})/0.25,if(gt(t,{end}-0.25),({end}-t)/0.25,1))"
    box = f":box=1:boxcolor=black@0.45:boxborderw={int(size * 0.35)}" if a.box else ""
    vf = (f"drawtext=fontfile='{escape_filter_path(font)}':textfile='{escape_filter_path(txt)}':fontsize={size}:"
          f"fontcolor={a.color}:borderw={max(2, size // 14)}:bordercolor=black@0.85:x=(w-text_w)/2:y={y}:"
          f"line_spacing={size // 5}:alpha='{alpha}':enable='between(t,{start},{end})'{box}")
    try:
        out_ffmpeg(["-i", a.input, "-vf", vf, *enc(a.quality), "-c:a", "copy"], a.out)
    finally:
        Path(txt).unlink(missing_ok=True)


def cmd_punch(a):
    info = probe(a.input)
    times = [parse_time(t) for t in a.at.split(",") if t.strip()]
    if not times:
        raise StudioError("--at attend des instants, ex. 3.2,9.5")
    pulses = "+".join(f"between(t,{t},{t + a.duration})*pow(sin(PI*(t-{t})/{a.duration}),2)" for t in times)
    z = f"(1+{a.amount}*({pulses}))"
    W, H = info.width - info.width % 2, info.height - info.height % 2
    vf = (f"scale=w='trunc(iw*{z}/2)*2':h='trunc(ih*{z}/2)*2':eval=frame:flags=bicubic,crop={W}:{H},setsar=1")
    out_ffmpeg(["-i", a.input, "-vf", vf, *enc(a.quality), "-c:a", "copy"], a.out)


VOICE_PRESETS = {
    "deep": (-3.5, None), "low": (-2.0, None), "high": (2.5, None), "child": (6.0, None),
    "radio": (0.0, "highpass=f=300,lowpass=f=3400,acompressor=threshold=-18dB:ratio=6,volume=1.4"),
    "echo": (0.0, "aecho=0.8:0.7:90:0.35"),
    "robot": (0.0, "afftfilt=real='hypot(re,im)*sin(0)':imag='hypot(re,im)*cos(0)':win_size=512:overlap=0.75"),
}


def cmd_voice(a):
    info = probe(a.input)
    if not info.has_audio:
        raise StudioError("Pas de piste audio.")
    semis, extra = VOICE_PRESETS.get(a.preset, (0.0, None)) if a.preset else (0.0, None)
    semis = a.semitones if a.semitones is not None else semis
    chain = []
    if abs(semis) >= 0.05:
        ratio = 2 ** (semis / 12)
        has_rb = "rubberband" in run(["ffmpeg", "-hide_banner", "-filters"]).stdout
        chain.append(f"rubberband=pitch={ratio:.5f}" if has_rb
                     else f"asetrate={48000 * ratio:.1f},aresample=48000,atempo={1 / ratio:.5f}")
    if extra:
        chain.append(extra)
    if not chain:
        raise StudioError("Rien à faire : choisis --preset ou --semitones.")
    out_ffmpeg(["-i", a.input, "-af", ",".join(chain), "-c:v", "copy", *aenc(a.quality)], a.out)


def cmd_loudnorm(a):
    info = probe(a.input)
    if not info.has_audio:
        raise StudioError("Pas de piste audio.")
    out_ffmpeg(["-i", a.input, "-af", f"loudnorm=I={a.lufs}:TP=-1.5:LRA=11", "-c:v", "copy", *aenc(a.quality),
                "-t", f"{info.duration:.3f}"], a.out)


def cmd_burn(a):
    subs = Path(a.subs)
    if not subs.exists():
        raise StudioError(f"Sous-titres introuvables : {subs}")
    if subs.suffix.lower() == ".ass":
        vf = f"ass='{escape_filter_path(subs)}'"
    else:
        size = a.size or 22
        style = (f"FontName=Inter,FontSize={size},Bold=1,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,"
                 f"BorderStyle=1,Outline=2,Shadow=0,Alignment=2,MarginV={a.margin}")
        vf = f"subtitles='{escape_filter_path(subs)}':force_style='{style}'"
    out_ffmpeg(["-i", a.input, "-vf", vf, *enc(a.quality), "-c:a", "copy"], a.out)


def cmd_logo(a):
    if not Path(a.image).exists():
        raise StudioError(f"Image introuvable : {a.image}")
    info = probe(a.input)
    lw = int(info.width * a.scale)
    pos = {"tl": "20:20", "tr": "W-w-20:20", "bl": "20:H-h-20", "br": "W-w-20:H-h-20",
           "center": "(W-w)/2:(H-h)/2"}[a.position]
    graph = (f"[1:v]scale={lw}:-1,format=rgba,colorchannelmixer=aa={a.opacity}[lg];"
             f"[0:v][lg]overlay={pos}:format=auto,format=yuv420p[v]")
    out_ffmpeg(["-i", a.input, "-i", a.image, "-filter_complex", graph, "-map", "[v]", "-map", "0:a?",
                *enc(a.quality), "-c:a", "copy"], a.out)


def _area_px(spec: str, w: int, h: int, frac: float) -> tuple[int, int, int, int]:
    """'tl|tr|bl|br' (coin, taille = frac de la largeur) ou 'x,y,w,h' en pixels."""
    if spec in ("tl", "tr", "bl", "br"):
        bw, bh = int(w * frac), int(w * frac * 0.45)
        x = 12 if spec[1] == "l" else w - bw - 12
        y = 12 if spec[0] == "t" else h - bh - 12
        return x, max(0, y), bw, bh
    try:
        x, y, bw, bh = (int(float(v)) for v in spec.split(","))
    except ValueError as exc:
        raise StudioError("--area : tl|tr|bl|br ou x,y,largeur,hauteur en pixels.") from exc
    if bw <= 0 or bh <= 0 or x < 0 or y < 0 or x + bw > w or y + bh > h:
        raise StudioError(f"--area hors de l'image ({w}x{h}).")
    return x, y, bw, bh


def cmd_delogo(a):
    """Masque une marque QUI T'APPARTIENT (ton logo, ton nom de compte) à une zone choisie.

    Ne sert pas à retirer le crédit ou le filigrane d'un autre créateur (voir references/platform-guidelines.md).
    """
    info = probe(a.input)
    w, h = info.width, info.height
    when = ""
    if a.start or a.end:
        t0 = parse_time(a.start or "0")
        t1 = parse_time(a.end) if a.end else info.duration
        when = f":enable='between(t,{t0:.3f},{t1:.3f})'"
    chain, cur = [], "[0:v]"
    for i, spec in enumerate(a.area):
        x, y, bw, bh = _area_px(spec, w, h, a.size)
        nxt = "[v]" if i == len(a.area) - 1 else f"[d{i}]"
        if a.method == "delogo":
            # delogo exige une marge d'au moins 1 px autour de la zone
            x, y = max(1, x), max(1, y)
            bw, bh = min(bw, w - x - 1), min(bh, h - y - 1)
            chain.append(f"{cur}delogo=x={x}:y={y}:w={bw}:h={bh}{when}{nxt}")
        elif a.method == "blur":
            chain.append(f"{cur}split[m{i}][b{i}];[b{i}]crop={bw}:{bh}:{x}:{y},gblur=sigma=18[bl{i}];"
                         f"[m{i}][bl{i}]overlay={x}:{y}{when}{nxt}")
        else:
            chain.append(f"{cur}drawbox=x={x}:y={y}:w={bw}:h={bh}:color={a.color}@1:t=fill{when}{nxt}")
        cur = nxt
    graph = ";".join(chain)
    out_ffmpeg(["-i", a.input, "-filter_complex", graph, "-map", "[v]", "-map", "0:a?", *enc(a.quality),
                "-c:a", "copy"], a.out)


def cmd_stabilize(a):
    if "vidstabdetect" not in run(["ffmpeg", "-hide_banner", "-filters"]).stdout:
        raise StudioError("Ce ffmpeg n'a pas libvidstab : installe une version complète (ex. build gyan.dev / johnvansickle).")
    with tempfile.TemporaryDirectory() as tmp:
        trf = str(Path(tmp) / "t.trf")
        ffmpeg(["-i", a.input, "-vf", f"vidstabdetect=shakiness={a.shakiness}:result={trf}", "-f", "null", "-"])
        vf = f"vidstabtransform=input={trf}:smoothing={a.smoothing}:zoom=1,unsharp=5:5:0.8:3:3:0.4"
        out_ffmpeg(["-i", a.input, "-vf", vf, *enc(a.quality), "-c:a", "copy"], a.out)


def cmd_thumbnail(a):
    import cv2
    import numpy as np

    info = probe(a.input)
    start = parse_time(a.start)
    end = parse_time(a.end) if a.end else info.duration
    dur = max(0.5, end - start)
    step = max(0.5, dur / 40)
    lw = 480
    lh = max(2, int(round(info.height * lw / info.width / 2)) * 2)
    proc = subprocess.Popen(["ffmpeg", "-nostdin", "-loglevel", "error", "-ss", f"{start}", "-t", f"{dur}", "-i", a.input,
                             "-an", "-vf", f"fps={1 / step:.4f},scale={lw}:{lh}", "-f", "rawvideo", "-pix_fmt", "bgr24", "-"],
                            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    from render import FaceDetector
    detector = FaceDetector(lw, lh)
    best, best_score, idx = 0.0, -1.0, 0
    size = lw * lh * 3
    while True:
        raw = proc.stdout.read(size)
        if len(raw) < size:
            break
        frame = np.frombuffer(raw, dtype=np.uint8).reshape(lh, lw, 3)
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        sharp = float(cv2.Laplacian(gray, cv2.CV_64F).var())
        bright = float(gray.mean())
        faces = detector.detect(frame)
        score = min(sharp, 600) / 600 * 50 + (30 if len(faces) else 0) + 20 * (1 - abs(bright - 125) / 125)
        if idx * step > 0.8 and score > best_score:  # évite le tout premier plan (souvent un fondu)
            best, best_score = start + idx * step, score
        idx += 1
    proc.stdout.close(); proc.wait()
    out_ffmpeg(["-ss", f"{best:.3f}", "-i", a.input, "-frames:v", "1", "-q:v", "2",
                "-vf", f"scale={a.width}:-2:flags=lanczos"], a.out)
    print(f"     image choisie à {best:.1f}s (score {best_score:.0f})")


# --------------------------------------------------------------------------- #
def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    def add(name, fn, with_input=True):
        p = sub.add_parser(name)
        if with_input:
            p.add_argument("input")
        p.add_argument("-o", "--out", required=True)
        p.add_argument("--quality", default="high", choices=list(QUALITY))
        p.set_defaults(fn=fn)
        return p

    p = add("trim", cmd_trim); p.add_argument("--start", default="0"); p.add_argument("--end")
    p.add_argument("--copy", action="store_true", help="sans ré-encodage (coupe sur image clé)")
    p = add("concat", cmd_concat, False); p.add_argument("inputs", nargs="+")
    p.add_argument("--xfade", default=None, help="fade, wipeleft, slideleft, circleopen, dissolve, pixelize…")
    p.add_argument("--xfade-duration", type=float, default=0.5); p.add_argument("--size"); p.add_argument("--fps", type=float)
    p = add("speed", cmd_speed); p.add_argument("--factor", type=float, required=True)
    p = add("silence", cmd_silence); p.add_argument("--threshold", default="-35dB")
    p.add_argument("--min-silence", type=float, default=0.45); p.add_argument("--pad", type=float, default=0.12)
    p = add("music", cmd_music); p.add_argument("--track", required=True)
    p.add_argument("--volume", type=float, default=0.15); p.add_argument("--no-duck", dest="duck", action="store_false")
    p = add("text", cmd_text); p.add_argument("--text", required=True); p.add_argument("--start", default="0")
    p.add_argument("--end"); p.add_argument("--position", default="top", choices=["top", "center", "bottom"])
    p.add_argument("--size", type=int); p.add_argument("--color", default="white"); p.add_argument("--font")
    p.add_argument("--box", action="store_true")
    p = add("punch", cmd_punch); p.add_argument("--at", required=True, help="instants en s, séparés par des virgules")
    p.add_argument("--amount", type=float, default=0.12); p.add_argument("--duration", type=float, default=0.45)
    p = add("voice", cmd_voice); p.add_argument("--preset", choices=list(VOICE_PRESETS))
    p.add_argument("--semitones", type=float, default=None)
    p = add("loudnorm", cmd_loudnorm); p.add_argument("--lufs", type=float, default=-14.0)
    p = add("burn", cmd_burn); p.add_argument("--subs", required=True); p.add_argument("--size", type=int)
    p.add_argument("--margin", type=int, default=60)
    p = add("logo", cmd_logo); p.add_argument("--image", required=True)
    p.add_argument("--position", default="br", choices=["tl", "tr", "bl", "br", "center"])
    p.add_argument("--scale", type=float, default=0.15); p.add_argument("--opacity", type=float, default=0.8)
    p = add("delogo", cmd_delogo)
    p.add_argument("--area", action="append", required=True,
                   help="zone à masquer : tl|tr|bl|br ou x,y,larg,haut (px). Répétable (ex. nom qui change de coin).")
    p.add_argument("--method", default="blur", choices=["blur", "delogo", "box"])
    p.add_argument("--size", type=float, default=0.28, help="largeur de la zone d'un coin (fraction de l'image)")
    p.add_argument("--start", default=None); p.add_argument("--end", default=None)
    p.add_argument("--color", default="black")
    p = add("stabilize", cmd_stabilize); p.add_argument("--shakiness", type=int, default=5)
    p.add_argument("--smoothing", type=int, default=15)
    p = add("thumbnail", cmd_thumbnail); p.add_argument("--start", default="0"); p.add_argument("--end")
    p.add_argument("--width", type=int, default=1080)
    return ap


def main() -> None:
    args = build_parser().parse_args()
    try:
        need_binary("ffmpeg")
        args.fn(args)
    except StudioError as exc:
        die(str(exc))


if __name__ == "__main__":
    main()
