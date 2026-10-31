#!/usr/bin/env python3
# Phenix-video — © 2026 Phenix - kcw. Tous droits réservés (voir LICENSE).
"""Diagnostic d'installation : dit ce qui manque et la commande exacte pour le réparer.

  python scripts/doctor.py
"""
from __future__ import annotations

import importlib
import os
import shutil
import socket
import subprocess
import sys
from pathlib import Path

CACHE = Path(os.environ.get("PHENIX_VIDEO_CACHE", Path.home() / ".cache" / "phenix-video"))
OK, KO, WARN = "[ok]   ", "[MANQUE]", "[info] "


def line(tag: str, text: str, fix: str = "") -> None:
    print(f"{tag} {text}" + (f"\n         -> {fix}" if fix else ""))


def module(name: str, pip: str, required: bool = True) -> bool:
    try:
        importlib.import_module(name)
        line(OK, name)
        return True
    except Exception:  # noqa: BLE001 - un import peut échouer de bien des façons
        line(KO if required else WARN, f"{name} absent", f"pip install {pip}")
        return False


def main() -> int:
    bad = 0
    print(f"Phenix-video — diagnostic (Python {sys.version.split()[0]}, {sys.platform})\n")
    if sys.version_info < (3, 10):
        line(KO, "Python 3.10 ou plus requis", "sudo apt install python3 python3-venv")
        bad += 1
    if not (hasattr(sys, "real_prefix") or sys.prefix != sys.base_prefix):
        line(WARN, "environnement virtuel non activé", "source .venv/bin/activate   (ou utilise ./phenix)")
    for tool in ("ffmpeg", "ffprobe"):
        if shutil.which(tool):
            ver = subprocess.run([tool, "-version"], capture_output=True, text=True).stdout.split("\n")[0][:60]
            line(OK, f"{tool} — {ver}")
        else:
            line(KO, f"{tool} introuvable", "sudo apt install -y ffmpeg")
            bad += 1
    if shutil.which("ffmpeg"):
        filt = subprocess.run(["ffmpeg", "-hide_banner", "-filters"], capture_output=True, text=True).stdout
        for f in ("ass", "xfade", "sidechaincompress", "loudnorm", "afftdn", "hqdn3d"):
            if f" {f} " not in filt:
                line(WARN, f"filtre ffmpeg « {f} » absent : certaines fonctions seront indisponibles")
    for mod, pip in (("numpy", "numpy"), ("cv2", "opencv-python-headless"), ("faster_whisper", "faster-whisper"),
                     ("argostranslate", "argostranslate"), ("piper", "piper-tts"), ("yt_dlp", "yt-dlp")):
        bad += 0 if module(mod, pip) else 1
    module("mediapipe", "mediapipe", required=False)
    module("edge_tts", "edge-tts", required=False)
    try:
        import torch
        cpu = "+cpu" in torch.__version__ or not torch.cuda.is_available()
        line(OK, f"torch {torch.__version__}" + (" (CPU)" if cpu else " (GPU)"))
    except Exception:  # noqa: BLE001
        line(WARN, "torch absent (utile à la traduction hors-ligne)",
             "pip install torch --index-url https://download.pytorch.org/whl/cpu")
    for name in ("selfie_segmenter.tflite", "face_detection_yunet_2023mar.onnx"):
        line(OK if (CACHE / name).is_file() else WARN, f"modèle {name}" + ("" if (CACHE / name).is_file() else " : se télécharge au 1er usage"))
    piper = list((CACHE / "piper").glob("*.onnx")) if (CACHE / "piper").is_dir() else []
    line(OK if piper else WARN, f"voix Piper : {len(piper)} installée(s)" + ("" if piper else " (téléchargées au 1er doublage)"))
    free = shutil.disk_usage(Path.home()).free / 1e9
    line(OK if free > 5 else WARN, f"espace disque libre : {free:.1f} Go" + ("" if free > 5 else " (prévois au moins 5 Go)"))
    with socket.socket() as s:
        busy = s.connect_ex(("127.0.0.1", 8765)) == 0
    line(WARN, "port 8765 " + ("déjà utilisé : l'application tourne peut-être déjà (http://127.0.0.1:8765)" if busy else "libre"))
    print("\n" + ("Tout est prêt." if not bad else f"{bad} élément(s) à corriger avant de continuer."))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
