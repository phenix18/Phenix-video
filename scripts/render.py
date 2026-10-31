#!/usr/bin/env python3
# Phenix-video — © 2026 Phenix - kcw. Tous droits réservés (voir LICENSE).
"""Rendu d'un clip en 1080p : recadrage intelligent + sous-titres + son, en UN SEUL encodage.

Modes de cadrage (--mode) :
  auto    suit les visages si on en trouve (>= 30 % des échantillons), sinon fond flou
  track   caméra virtuelle qui suit le visage (zone morte + lissage : pas de tremblement)
  center  recadrage centré
  blur    vidéo entière au centre sur fond flou (le look « fond flou » pour les plans larges)
  fit     vidéo entière avec bandes noires
  none    pas de recadrage : mise à l'échelle seule (sortie 16:9)

Qualité : 1080p (1080x1920 vertical, 1920x1080 horizontal), H.264 High, CRF 18, AAC 256k, loudnorm -14 LUFS.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from common import (StudioError, audio_args, die, ensure_parent, escape_filter_path, finalize,  # noqa: E402
                    need_binary, parse_size, parse_time, probe, temp_sibling)

QUALITY = {
    # nom: (crf, preset x264, débit audio)
    "max": (16, "slow", "256k"),
    "high": (18, "medium", "256k"),
    "balanced": (21, "veryfast", "192k"),
    "fast": (24, "ultrafast", "160k"),
}


def out_size_for(aspect: str, base: int = 1080) -> tuple[int, int]:
    """1080p : le petit côté vaut 1080. 9:16 -> 1080x1920, 16:9 -> 1920x1080, 1:1 -> 1080x1080."""
    a, _, b = aspect.partition(":")
    try:
        ratio = float(a) / float(b)
    except (ValueError, ZeroDivisionError) as exc:
        raise StudioError(f"Ratio invalide : {aspect!r} (ex. 9:16, 16:9, 1:1, 4:5)") from exc
    if ratio < 1:
        w, h = base, int(round(base / ratio))
    else:
        w, h = int(round(base * ratio)), base
    return w - w % 2, h - h % 2


# --------------------------------------------------------------------------- #
# Détection de visages (OpenCV Haar, fourni avec cv2, sans téléchargement)
# --------------------------------------------------------------------------- #
def _read_exact(stream, n: int) -> bytes:
    buf = bytearray()
    while len(buf) < n:
        chunk = stream.read(n - len(buf))
        if not chunk:
            break
        buf.extend(chunk)
    return bytes(buf)


YUNET_URL = ("https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/"
             "face_detection_yunet_2023mar.onnx")


def _yunet_model() -> str | None:
    """Modèle YuNet (OpenCV, licence MIT, ~230 Ko) : variable PHENIX_VIDEO_YUNET, cache, ou téléchargement."""
    import os
    import urllib.request
    env = os.environ.get("PHENIX_VIDEO_YUNET")
    if env and Path(env).exists():
        return env
    cache = Path.home() / ".cache" / "phenix-video" / "face_detection_yunet_2023mar.onnx"
    if cache.exists() and cache.stat().st_size > 100_000:
        return str(cache)
    try:
        cache.parent.mkdir(parents=True, exist_ok=True)
        urllib.request.urlretrieve(YUNET_URL, cache)
        if cache.stat().st_size > 100_000:
            return str(cache)
        cache.unlink(missing_ok=True)  # pointeur Git-LFS ou page d'erreur : pas un vrai modèle
    except Exception:  # noqa: BLE001 - hors-ligne : on essaiera Haar puis on se rabattra sur le flou
        cache.unlink(missing_ok=True)
    return None


class FaceDetector:
    """Détecte les visages : YuNet (précis, par défaut) -> cascade Haar (anciens OpenCV) -> aucun."""

    def __init__(self, width: int, height: int):
        import cv2
        self.cv2, self.kind, self.det = cv2, None, None
        self.size = (width, height)
        model = _yunet_model() if hasattr(cv2, "FaceDetectorYN") else None
        if model:
            self.det = cv2.FaceDetectorYN.create(model, "", self.size, 0.6, 0.3, 500)
            self.kind = "yunet"
            return
        data = getattr(getattr(cv2, "data", None), "haarcascades", "")
        cascade = Path(data) / "haarcascade_frontalface_default.xml" if data else None
        front = cv2.CascadeClassifier(str(cascade)) if cascade and cascade.exists() else None
        if front is not None and not front.empty():
            self.det, self.kind = front, "haar"

    def detect(self, bgr):
        """Retourne une liste de (x, y, w, h) en pixels de l'image analysée."""
        if self.kind == "yunet":
            self.det.setInputSize((bgr.shape[1], bgr.shape[0]))
            _, faces = self.det.detect(bgr)
            return [] if faces is None else [tuple(map(float, f[:4])) for f in faces]
        if self.kind == "haar":
            gray = self.cv2.equalizeHist(self.cv2.cvtColor(bgr, self.cv2.COLOR_BGR2GRAY))
            m = int(bgr.shape[0] * 0.07)
            return [tuple(map(float, f)) for f in self.det.detectMultiScale(gray, 1.15, 5, minSize=(m, m))]
        return []


def analyse_subject(src: str, start: float, dur: float, src_w: int, src_h: int, sample_fps: float = 5.0,
                    detector=None):
    """Retourne (times, centres_x, centres_y, cuts, taux_detection, détecteur) en coordonnées source."""
    import numpy as np

    lw = 480
    lh = max(2, int(round(src_h * lw / src_w / 2)) * 2)
    detector = detector or FaceDetector(lw, lh)
    if detector.kind is None:
        return [0.0, 1.0], [None, None], [None, None], [False, False], 0.0, None
    cmd = ["ffmpeg", "-nostdin", "-loglevel", "error", "-ss", f"{start:.3f}", "-t", f"{dur:.3f}", "-i", src,
           "-an", "-vf", f"fps={sample_fps},scale={lw}:{lh}", "-f", "rawvideo", "-pix_fmt", "bgr24", "-"]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)

    xs, ys, cuts, times = [], [], [], []
    prev = None
    prev_c = None
    idx = 0
    while True:
        raw = _read_exact(proc.stdout, lw * lh * 3)
        if len(raw) < lw * lh * 3:
            break
        frame = np.frombuffer(raw, dtype=np.uint8).reshape(lh, lw, 3)
        small = frame[::4, ::4].astype(np.int16)
        cut = prev is not None and float(np.abs(small - prev).mean()) > 38.0
        prev = small
        faces = detector.detect(frame)
        cx = cy = None
        if faces:
            if prev_c is None or cut:  # le plus grand visage
                f = max(faces, key=lambda r: r[2] * r[3])
            else:  # continuité : taille pondérée par la proximité du sujet précédent
                f = max(faces, key=lambda r: r[2] * r[3] / (1.0 + abs((r[0] + r[2] / 2) - prev_c) / lw * 4))
            cx = (f[0] + f[2] / 2) * src_w / lw
            cy = (f[1] + f[3] / 2) * src_h / lh
            prev_c = f[0] + f[2] / 2
        xs.append(cx); ys.append(cy); cuts.append(bool(cut)); times.append(idx / sample_fps)
        idx += 1
    proc.stdout.close()
    proc.wait()
    if len(times) < 2:
        return [0.0, 1.0], [None, None], [None, None], [False, False], 0.0, detector.kind
    rate = sum(v is not None for v in xs) / len(xs)
    return times, xs, ys, cuts, rate, detector.kind


def camera_path(times, xs, ys, cuts, crop_w: float, crop_h: float, src_w: int, src_h: int,
                fps: float, n_frames: int, deadband: float = 0.10, speed: float = 0.9):
    """Caméra virtuelle : ne bouge que si le visage sort de la zone morte, vitesse plafonnée, puis lissage."""
    import numpy as np

    default_x, default_y = src_w / 2, src_h * 0.42
    tx = np.array([default_x if v is None else v for v in xs], dtype=float)
    ty = np.array([default_y if v is None else v for v in ys], dtype=float)
    # trous : on garde le dernier sujet connu plutôt que de revenir au centre
    last_x, last_y = None, None
    for k in range(len(xs)):
        if xs[k] is None:
            if last_x is not None:
                tx[k], ty[k] = last_x, last_y
        else:
            last_x, last_y = xs[k], ys[k]
    first = next((k for k, v in enumerate(xs) if v is not None), None)
    if first is not None:
        tx[:first], ty[:first] = tx[first], ty[first]

    dt = times[1] - times[0] if len(times) > 1 else 0.2
    cam_x, cam_y = tx[0], ty[0]
    out_x, out_y = [], []
    dead_x, dead_y = crop_w * deadband, crop_h * deadband
    max_step_x, max_step_y = crop_w * speed * dt, crop_h * speed * dt
    for k in range(len(tx)):
        if cuts[k]:
            cam_x, cam_y = tx[k], ty[k]
        else:
            ex, ey = tx[k] - cam_x, ty[k] - cam_y
            if abs(ex) > dead_x:
                cam_x += float(np.clip(ex - np.sign(ex) * dead_x * 0.5, -max_step_x, max_step_x))
            if abs(ey) > dead_y:
                cam_y += float(np.clip(ey - np.sign(ey) * dead_y * 0.5, -max_step_y, max_step_y))
        out_x.append(cam_x); out_y.append(cam_y)

    out_x, out_y = np.array(out_x), np.array(out_y)
    kernel = np.hanning(7); kernel /= kernel.sum()  # lissage final doux (sans effacer les coupes franches)
    def smooth(v):
        pad = np.pad(v, (3, 3), mode="edge")
        sm = np.convolve(pad, kernel, mode="valid")
        for k, is_cut in enumerate(cuts):
            if is_cut:
                sm[max(0, k - 1):k + 2] = v[max(0, k - 1):k + 2]
        return sm
    out_x, out_y = smooth(out_x), smooth(out_y)

    frame_t = np.arange(n_frames) / fps
    fx = np.interp(frame_t, times, out_x)
    fy = np.interp(frame_t, times, out_y)
    fx = np.clip(fx - crop_w / 2, 0, src_w - crop_w)  # coin supérieur gauche du cadre
    fy = np.clip(fy - crop_h * 0.42, 0, src_h - crop_h)  # le visage reste dans le tiers supérieur
    return fx, fy


# --------------------------------------------------------------------------- #
# Rendu
# --------------------------------------------------------------------------- #
def _ass_filter(ass: str | None, fontsdir: str | None) -> str | None:
    if not ass:
        return None
    flt = f"ass='{escape_filter_path(ass)}'"
    if fontsdir:
        flt += f":fontsdir='{escape_filter_path(fontsdir)}'"
    return flt


def _audio_inputs(src, start, dur, info, audio_override):
    if audio_override:
        return ["-i", audio_override], True
    if info.has_audio:
        return ["-ss", f"{start:.3f}", "-t", f"{dur:.3f}", "-i", src], True
    return [], False


def render_clip(src: str, start: float, end: float, out: str, *, aspect: str = "9:16",
                size: tuple[int, int] | None = None, mode: str = "auto", ass: str | None = None,
                audio_override: str | None = None, quality: str = "high", fps: float | None = None,
                loudnorm: bool = True, zoom: float = 1.0, fontsdir: str | None = None,
                verbose: bool = True) -> dict:
    need_binary("ffmpeg")
    info = probe(src)
    if start < 0 or end <= start:
        raise StudioError(f"Intervalle invalide : {start} → {end}")
    end = min(end, info.duration) if info.duration else end
    dur = end - start
    if dur < 0.5:
        raise StudioError("Clip trop court (< 0,5 s).")
    tw, th = size or out_size_for(aspect)
    crf, preset, abr = QUALITY[quality]
    out_fps = fps or (info.fps if 24 <= info.fps <= 60 else 30.0)
    out_fps = round(out_fps, 3)
    n_frames = int(round(dur * out_fps))
    ensure_parent(out)
    tmp = temp_sibling(out)

    target_ratio = tw / th
    src_ratio = info.width / info.height
    report = {"mode": mode, "size": f"{tw}x{th}", "fps": out_fps, "duration": round(dur, 2)}

    # --- choix du mode
    detect = None
    if mode == "auto":
        if abs(src_ratio - target_ratio) < 0.02:
            mode = "none"
        else:
            detect = analyse_subject(src, start, dur, info.width, info.height)
            mode = "track" if detect[4] >= 0.30 else "blur"
            report["face_rate"] = round(detect[4], 2)
            report["detector"] = detect[5]
    report["mode"] = mode

    # --- avertissement de résolution
    crop_h = info.height if src_ratio >= target_ratio else info.width / target_ratio
    if mode in ("none", "fit", "blur"):
        up = max(tw / info.width, th / info.height) if mode == "none" else min(tw / info.width, th / info.height)
        if up > 1.15:
            report["warning"] = (f"Source {info.width}x{info.height} plus petite que la sortie {tw}x{th} : l'image est "
                                 f"agrandie x{up:.2f} (netteté limitée). Récupère une source plus haute résolution si possible.")
    if mode in ("track", "center") and crop_h < th * 0.9:
        report["warning"] = (f"Source basse résolution : le cadrage {aspect} n'utilise que ~{int(crop_h)} px "
                             f"de haut, agrandi vers {th} px (image un peu douce).")

    audio_in, has_audio = _audio_inputs(src, start, dur, info, audio_override)
    af = ["loudnorm=I=-14:TP=-1.5:LRA=11"] if (loudnorm and has_audio) else []
    ass_flt = _ass_filter(ass, fontsdir)
    x264 = ["-c:v", "libx264", "-preset", preset, "-crf", str(crf), "-profile:v", "high", "-pix_fmt", "yuv420p",
            "-g", str(int(round(out_fps * 2))), "-movflags", "+faststart",
            "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709"]

    if mode in ("track", "center"):
        _render_pipe(src, start, dur, tmp, info, tw, th, out_fps, n_frames, mode, detect, zoom, ass_flt,
                     audio_in, has_audio, af, x264, abr)
    else:
        _render_filter(src, start, dur, tmp, tw, th, out_fps, mode, ass_flt, audio_in, has_audio, af, x264, abr,
                       info)
    finalize(tmp, out)
    if verbose:
        print(f"[ok] {out}  ({report['size']} @ {out_fps:g} fps, mode {mode}, {dur:.1f}s)", file=sys.stderr)
    return report


def _render_filter(src, start, dur, tmp, tw, th, fps, mode, ass_flt, audio_in, has_audio, af, x264, abr, info):
    sc = "flags=lanczos"
    if mode == "blur":
        graph = (f"[0:v]split[a][b];"
                 f"[a]scale={tw}:{th}:force_original_aspect_ratio=increase:{sc},crop={tw}:{th},"
                 f"gblur=sigma=40,eq=brightness=-0.06:saturation=1.1[bg];"
                 f"[b]scale={tw}:{th}:force_original_aspect_ratio=decrease:{sc}[fg];"
                 f"[bg][fg]overlay=(W-w)/2:(H-h)/2")
    elif mode == "fit":
        graph = (f"[0:v]scale={tw}:{th}:force_original_aspect_ratio=decrease:{sc},"
                 f"pad={tw}:{th}:(ow-iw)/2:(oh-ih)/2:black")
    else:  # none : met à l'échelle en conservant le ratio ; recadre le surplus
        graph = f"[0:v]scale={tw}:{th}:force_original_aspect_ratio=increase:{sc},crop={tw}:{th}"
    graph += f",fps={fps},setsar=1"
    if ass_flt:
        graph += "," + ass_flt
    graph += ",format=yuv420p[v]"
    cmd = ["ffmpeg", "-hide_banner", "-nostdin", "-y", "-loglevel", "error",
           "-ss", f"{start:.3f}", "-t", f"{dur:.3f}", "-i", src, *audio_in,
           "-filter_complex", graph, "-map", "[v]"]
    if has_audio:
        cmd += ["-map", "1:a:0"]
        if af:
            cmd += ["-af", ",".join(af)]
        cmd += audio_args(abr)
    cmd += x264 + ["-t", f"{dur:.3f}", "-f", "mp4", str(tmp)]
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, errors="replace")
    if proc.returncode != 0:
        raise StudioError("Rendu ffmpeg en échec :\n" + "\n".join(proc.stderr.strip().splitlines()[-10:]))


def _render_pipe(src, start, dur, tmp, info, tw, th, fps, n_frames, mode, detect, zoom, ass_flt, audio_in,
                 has_audio, af, x264, abr):
    import cv2
    import numpy as np

    W, H = info.width, info.height
    target_ratio = tw / th
    if W / H >= target_ratio:
        crop_h, crop_w = float(H), H * target_ratio
    else:
        crop_w, crop_h = float(W), W / target_ratio
    zoom = max(1.0, min(zoom, 2.0))
    crop_w, crop_h = crop_w / zoom, crop_h / zoom

    if mode == "track":
        if detect is None:
            detect = analyse_subject(src, start, dur, W, H)
        times, xs, ys, cuts, _, kind = detect
        if kind is None:
            print('[info] aucun détecteur de visage (YuNet indisponible) : cadrage centré.', file=sys.stderr)
        if len(times) < 2:
            raise StudioError("Clip trop court pour le suivi de visage.")
        fx, fy = camera_path(times, xs, ys, cuts, crop_w, crop_h, W, H, fps, n_frames)
    else:
        fx = np.full(n_frames, (W - crop_w) / 2)
        fy = np.full(n_frames, (H - crop_h) / 2 if zoom == 1.0 else (H - crop_h) * 0.42)

    scale = th / crop_h
    interp = cv2.INTER_CUBIC if scale >= 1.0 else cv2.INTER_LINEAR

    reader = subprocess.Popen(
        ["ffmpeg", "-nostdin", "-loglevel", "error", "-ss", f"{start:.3f}", "-t", f"{dur:.3f}", "-i", src,
         "-an", "-vf", f"fps={fps}", "-f", "rawvideo", "-pix_fmt", "bgr24", "-"],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)

    vf = ["scale=out_color_matrix=bt709:out_range=tv:flags=lanczos"]
    if ass_flt:
        vf.append(ass_flt)
    vf.append("format=yuv420p")
    wcmd = ["ffmpeg", "-hide_banner", "-nostdin", "-y", "-loglevel", "error",
            "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{tw}x{th}", "-r", f"{fps}", "-i", "-", *audio_in,
            "-map", "0:v", "-vf", ",".join(vf)]
    if has_audio:
        wcmd += ["-map", "1:a:0"]
        if af:
            wcmd += ["-af", ",".join(af)]
        wcmd += audio_args(abr)
    wcmd += x264 + ["-t", f"{dur:.3f}", "-f", "mp4", str(tmp)]
    with tempfile.TemporaryFile() as werr:
        writer = subprocess.Popen(wcmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=werr)
        frame_bytes = W * H * 3
        written = 0
        try:
            for i in range(n_frames):
                raw = _read_exact(reader.stdout, frame_bytes)
                if len(raw) < frame_bytes:
                    break
                frame = np.frombuffer(raw, dtype=np.uint8).reshape(H, W, 3)
                x0, y0 = float(fx[min(i, len(fx) - 1)]), float(fy[min(i, len(fy) - 1)])
                if scale < 0.8:  # forte réduction : découpe entière puis INTER_AREA (meilleure qualité)
                    xi, yi = int(round(x0)), int(round(y0))
                    slab = frame[yi:yi + int(round(crop_h)), xi:xi + int(round(crop_w))]
                    out_frame = cv2.resize(slab, (tw, th), interpolation=cv2.INTER_AREA)
                else:  # recadrage sub-pixel : mouvement de caméra fluide
                    M = np.array([[scale, 0, -x0 * scale], [0, scale, -y0 * scale]], dtype=np.float32)
                    out_frame = cv2.warpAffine(frame, M, (tw, th), flags=interp, borderMode=cv2.BORDER_REPLICATE)
                writer.stdin.write(out_frame.tobytes())
                written += 1
        except BrokenPipeError:
            pass
        finally:
            try:
                writer.stdin.close()
            except BrokenPipeError:
                pass
            reader.stdout.close()
            reader.wait()
            writer.wait()
        if writer.returncode != 0 or written == 0:
            werr.seek(0)
            tail = werr.read().decode("utf-8", "replace").strip().splitlines()[-10:]
            raise StudioError("Rendu en échec :\n" + "\n".join(tail))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("input")
    ap.add_argument("-o", "--out", required=True)
    ap.add_argument("--start", default="0")
    ap.add_argument("--end", default=None, help="défaut : fin de la vidéo")
    ap.add_argument("--aspect", default="9:16", help="9:16 | 16:9 | 1:1 | 4:5")
    ap.add_argument("--size", default=None, help="force la taille, ex. 1080x1920")
    ap.add_argument("--mode", default="auto", choices=["auto", "track", "center", "blur", "fit", "none"])
    ap.add_argument("--ass", default=None, help="sous-titres .ass à incruster")
    ap.add_argument("--fontsdir", default=None)
    ap.add_argument("--audio", default=None, help="piste audio de remplacement (voix off doublée)")
    ap.add_argument("--quality", default="high", choices=list(QUALITY))
    ap.add_argument("--fps", type=float, default=None)
    ap.add_argument("--zoom", type=float, default=1.0, help="1.0-2.0 : resserre le cadre (mode track/center)")
    ap.add_argument("--no-loudnorm", action="store_true")
    args = ap.parse_args()
    try:
        info = probe(args.input)
        start = parse_time(args.start)
        end = parse_time(args.end) if args.end else info.duration
        size = parse_size(args.size) if args.size else None
        rep = render_clip(args.input, start, end, args.out, aspect=args.aspect, size=size, mode=args.mode,
                          ass=args.ass, audio_override=args.audio, quality=args.quality, fps=args.fps,
                          loudnorm=not args.no_loudnorm, zoom=args.zoom, fontsdir=args.fontsdir)
        if rep.get("warning"):
            print("[avertissement] " + rep["warning"], file=sys.stderr)
    except StudioError as exc:
        die(str(exc))


if __name__ == "__main__":
    main()
