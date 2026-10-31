# Phenix-video — © 2026 Phenix - kcw. Tous droits réservés (voir LICENSE).
"""Lanceur Windows (devient PhenixVideo.exe via PyInstaller, voir .github/workflows/build-windows.yml).

Premier lancement : vérifie Python et FFmpeg (les installe avec winget si besoin), crée un environnement dans
%LOCALAPPDATA%\\PhenixVideo, installe les dépendances (PyTorch CPU d'abord), puis démarre l'application locale.
Lancements suivants : démarre directement. Options passées à l'application (ex. --lan pour le téléphone).
Le .exe doit rester à côté du dossier `scripts` (il est livré ainsi dans l'archive Windows).
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

HOME = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "PhenixVideo"
VENV = HOME / "venv"
BASE = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent.parent


def say(msg: str) -> None:
    print(f"[Phenix-video] {msg}", flush=True)


def stop(msg: str, code: int = 1) -> None:
    say(msg)
    input("\nAppuie sur Entrée pour fermer…")
    sys.exit(code)


def find_python() -> str | None:
    for cmd in (["py", "-3"], ["python"], ["python3"]):
        exe = shutil.which(cmd[0])
        if not exe:
            continue
        try:
            out = subprocess.run([exe, *cmd[1:], "-c", "import sys;print(sys.version_info[:2]>=(3,10))"],
                                 capture_output=True, text=True, timeout=20).stdout.strip()
        except (OSError, subprocess.TimeoutExpired):
            continue
        if out == "True":
            return " ".join([exe, *cmd[1:]]) if len(cmd) > 1 else exe
    return None


def winget(pkg: str) -> bool:
    if not shutil.which("winget"):
        return False
    say(f"Installation de {pkg} (winget)…")
    return subprocess.run(["winget", "install", "-e", "--id", pkg, "--accept-source-agreements",
                           "--accept-package-agreements"]).returncode == 0


def main() -> None:
    if not (BASE / "scripts" / "app.py").is_file():
        stop(f"Dossier « scripts » introuvable à côté de l'exécutable ({BASE}). Dézippe toute l'archive avant de lancer.")
    py = find_python()
    if not py:
        if winget("Python.Python.3.12"):
            stop("Python est installé. FERME cette fenêtre puis relance PhenixVideo.exe.", 0)
        stop("Python 3.10+ est requis : installe-le depuis https://www.python.org/downloads/ (coche « Add to PATH »).")
    if not shutil.which("ffmpeg"):
        if winget("Gyan.FFmpeg"):
            stop("FFmpeg est installé. FERME cette fenêtre puis relance PhenixVideo.exe.", 0)
        stop("FFmpeg est requis : installe-le (winget install Gyan.FFmpeg) puis relance.")
    vpy = VENV / "Scripts" / "python.exe"
    if not vpy.is_file():
        say("Première installation (quelques minutes, une seule fois)…")
        HOME.mkdir(parents=True, exist_ok=True)
        if subprocess.run([*py.split(" "), "-m", "venv", str(VENV)]).returncode != 0:
            stop("Création de l'environnement impossible.")
        pip = [str(vpy), "-m", "pip", "install", "--default-timeout=120"]
        steps = [[str(vpy), "-m", "pip", "install", "--upgrade", "pip"],
                 [*pip, "torch", "--index-url", "https://download.pytorch.org/whl/cpu"],
                 [*pip, "-r", str(BASE / "requirements.txt")]]
        for step in steps:
            if subprocess.run(step).returncode != 0:
                shutil.rmtree(VENV, ignore_errors=True)  # évite un environnement à moitié installé
                stop("Échec du téléchargement (réseau ?). Relance PhenixVideo.exe pour reprendre.")
    say("Démarrage… (ferme cette fenêtre pour arrêter l'application)")
    sys.exit(subprocess.call([str(vpy), str(BASE / "scripts" / "app.py"), *sys.argv[1:]]))


if __name__ == "__main__":
    main()
