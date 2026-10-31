#!/usr/bin/env python3
# Phenix-video — © 2026 Phenix - kcw. Tous droits réservés (voir LICENSE).
"""Remplacer l'arrière-plan derrière la personne (gratuit, local, sans API).

  background.py in.mp4 -o out.mp4 --bg blur
  background.py in.mp4 -o out.mp4 --bg color:#0B1F3A
  background.py in.mp4 -o out.mp4 --bg image:decor.jpg
  background.py in.mp4 -o out.mp4 --bg video:boucle.mp4

Détection de la personne : MediaPipe « selfie segmenter » (modèle de 250 Ko téléchargé une fois dans
~/.cache/phenix-video). Fait pour une personne face caméra ; les cheveux fins et les fonds très chargés
donnent des contours moins propres. Sans MediaPipe (`pip install mediapipe`), l'étape s'arrête avec un message clair.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from common import StudioError, audio_args, die, ensure_parent, finalize, need_binary, probe, temp_sibling  # noqa: E402
from render import QUALITY  # noqa: E402

MODEL_URL = "https://storage.googleapis.com/mediapipe-models/image_segmenter/selfie_segmenter/float16/latest/selfie_segmenter.tflite"
CACHE = Path(os.environ.get("PHENIX_VIDEO_CACHE", Path.home() / ".cache" / "phenix-video"))


def _model_path() -> str:
    env = os.environ.get("PHENIX_VIDEO_SEGMENTER")
    if env and Path(env).is_file():
        return env
    path = CACHE / "selfie_segmenter.tflite"
    if path.is_file() and path.stat().st_size > 100_000:
        return str(path)
    CACHE.mkdir(parents=True, exist_ok=True)
    try:
        tmp = path.with_suffix(".part")
        urllib.request.urlretrieve(MODEL_URL, tmp)
        if tmp.stat().st_size < 100_000:
            raise OSError("fichier trop petit")
        tmp.replace(path)
    except OSError as exc:
        raise StudioError(
            f"Modèle de segmentation indisponible ({exc}). Télécharge-le depuis :\n  {MODEL_URL}\n"
            f"et place-le ici : {path}  (ou définis PHENIX_VIDEO_SEGMENTER=/chemin/modele.tflite)") from exc
    return str(path)


class Segmenter:
    def __init__(self) -> None:
        try:
            import mediapipe as mp
            from mediapipe.tasks import python as mpp
            from mediapipe.tasks.python import vision
        except ImportError as exc:
            raise StudioError("MediaPipe manque : pip install mediapipe") from exc
        self.mp = mp
        opts = vision.ImageSegmenterOptions(
            base_options=mpp.BaseOptions(model_asset_path=_model_path()),
            running_mode=vision.RunningMode.IMAGE, output_confidence_masks=True, output_category_mask=False)
        self.seg = vision.ImageSegmenter.create_from_options(opts)

    def close(self) -> None:
        try:
            self.seg.close()
        except Exception:  # noqa: BLE001 - fermeture best-effort
            pass

    def person_mask(self, bgr):
        """Masque float32 0..1 (1 = personne), même taille que l'image."""
        import cv2
        rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
        res = self.seg.segment(self.mp.Image(image_format=self.mp.ImageFormat.SRGB, data=rgb))
        masks = res.confidence_masks
        m = masks[-1].numpy_view() if len(masks) > 1 else masks[0].numpy_view()
        m = m.astype("float32")
        return cv2.resize(m, (bgr.shape[1], bgr.shape[0]), interpolation=cv2.INTER_LINEAR)


def _background_frames(spec: str, w: int, h: int, fps: float):
    """Générateur de fonds (BGR). `blur` est traité à part (dépend de l'image)."""
    import cv2
    import numpy as np
    kind, _, val = spec.partition(":")
    if kind == "color":
        val = val.lstrip("#") or "000000"
        if len(val) != 6:
            raise StudioError("Couleur attendue : color:#RRGGBB")
        r, g, b = (int(val[i:i + 2], 16) for i in (0, 2, 4))
        frame = np.full((h, w, 3), (b, g, r), dtype=np.uint8)
        while True:
            yield frame
    elif kind == "image":
        img = cv2.imread(val)
        if img is None:
            raise StudioError(f"Image introuvable ou illisible : {val}")
        s = max(w / img.shape[1], h / img.shape[0])
        img = cv2.resize(img, (int(img.shape[1] * s) + 1, int(img.shape[0] * s) + 1), interpolation=cv2.INTER_AREA)
        y0, x0 = (img.shape[0] - h) // 2, (img.shape[1] - w) // 2
        frame = np.ascontiguousarray(img[y0:y0 + h, x0:x0 + w])
        while True:
            yield frame
    elif kind == "video":
        if not Path(val).is_file():
            raise StudioError(f"Vidéo de fond introuvable : {val}")
        cmd = ["ffmpeg", "-hide_banner", "-nostdin", "-loglevel", "error", "-stream_loop", "-1", "-i", val, "-an",
               "-vf", f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},fps={fps}",
               "-f", "rawvideo", "-pix_fmt", "bgr24", "-"]
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE)
        size = w * h * 3
        try:
            while True:
                buf = proc.stdout.read(size)
                if len(buf) < size:
                    return
                yield np.frombuffer(buf, np.uint8).reshape(h, w, 3)
        finally:
            proc.kill()
    else:
        raise StudioError("--bg : blur | color:#RRGGBB | image:fichier | video:fichier")


def replace_background(src: str, out: str, bg: str = "blur", *, quality: str = "balanced", feather: int = 7,
                       smooth: float = 0.55) -> dict:
    """Retourne des statistiques (part moyenne de l'image occupée par la personne)."""
    import cv2
    import numpy as np
    need_binary("ffmpeg")
    info = probe(src)
    w, h, fps = info.width - info.width % 2, info.height - info.height % 2, info.fps
    seg = Segmenter()
    bg_iter = None if bg == "blur" else _background_frames(bg, w, h, fps)
    crf, preset, abr = QUALITY[quality]
    ensure_parent(out)
    tmp = temp_sibling(out)
    rd = subprocess.Popen(["ffmpeg", "-hide_banner", "-nostdin", "-loglevel", "error", "-i", src, "-an",
                           "-vf", f"scale={w}:{h}", "-f", "rawvideo", "-pix_fmt", "bgr24", "-"],
                          stdout=subprocess.PIPE)
    wr_cmd = ["ffmpeg", "-hide_banner", "-nostdin", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "bgr24",
              "-s", f"{w}x{h}", "-r", f"{fps:.4f}", "-i", "-", "-i", src, "-map", "0:v", "-map", "1:a?",
              "-c:v", "libx264", "-preset", preset, "-crf", str(crf), "-profile:v", "high", "-pix_fmt", "yuv420p",
              *audio_args(abr), "-shortest", "-movflags", "+faststart", str(tmp)]
    wr = subprocess.Popen(wr_cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    size, prev, frames, cover = w * h * 3, None, 0, 0.0
    k = feather | 1
    try:
        while True:
            buf = rd.stdout.read(size)
            if len(buf) < size:
                break
            frame = np.frombuffer(buf, np.uint8).reshape(h, w, 3)
            m = seg.person_mask(frame)
            prev = m if prev is None else smooth * prev + (1 - smooth) * m  # lissage temporel : moins de scintillement
            mm = prev
            mm = np.clip((mm - 0.35) / 0.4, 0.0, 1.0)  # durcit légèrement la frontière
            mm = cv2.GaussianBlur(mm, (k, k), 0)
            back = cv2.GaussianBlur(frame, (0, 0), max(8, w // 60)) if bg_iter is None else next(bg_iter)
            comp = cv2.blendLinear(frame, back, mm, 1.0 - mm)
            wr.stdin.write(comp.tobytes())
            frames += 1
            cover += float(mm.mean())
        wr.stdin.close()
        err = wr.stderr.read().decode("utf-8", "replace")
        if wr.wait() != 0:
            raise StudioError(f"Encodage en échec : {err[-400:]}")
        finalize(tmp, out)
    finally:
        seg.close()
        rd.kill()
        if wr.poll() is None:
            wr.kill()
        tmp.unlink(missing_ok=True)
    return {"frames": frames, "person_share": cover / max(frames, 1)}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("input")
    ap.add_argument("-o", "--out", required=True)
    ap.add_argument("--bg", default="blur")
    ap.add_argument("--quality", default="balanced", choices=list(QUALITY))
    ap.add_argument("--feather", type=int, default=7, help="adoucissement des contours (px, impair)")
    a = ap.parse_args()
    try:
        st = replace_background(a.input, a.out, a.bg, quality=a.quality, feather=a.feather)
        print(f"[ok] {a.out} — {st['frames']} images, personne ≈ {st['person_share'] * 100:.0f} % de l'image")
        if st["person_share"] < 0.03:
            print("[attention] presque aucune personne détectée : vérifie que quelqu'un est visible face caméra.")
    except StudioError as exc:
        die(str(exc))


if __name__ == "__main__":
    main()
