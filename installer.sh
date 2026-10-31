#!/usr/bin/env bash
# Phenix-video — © 2026 Phenix - kcw. Installation locale gratuite (Ubuntu/WSL, Debian, macOS).
set -e
cd "$(dirname "$0")"
command -v python3 >/dev/null || { echo "Installe Python 3.10+ : sudo apt install python3"; exit 1; }
if ! command -v ffmpeg >/dev/null; then
  if command -v apt >/dev/null; then sudo apt update && sudo apt install -y ffmpeg
  elif command -v brew >/dev/null; then brew install ffmpeg
  else echo "Installe FFmpeg manuellement"; exit 1; fi
fi
if command -v apt >/dev/null; then dpkg -s python3-venv >/dev/null 2>&1 || sudo apt install -y python3-venv python3-pip; fi
python3 -m venv .venv
. .venv/bin/activate
pip install --upgrade pip
# PyTorch version CPU d'abord : évite ~3 Go de paquets NVIDIA inutiles sans GPU
pip install --default-timeout=120 --resume-retries 10 torch --index-url https://download.pytorch.org/whl/cpu
pip install --default-timeout=120 --resume-retries 10 -r requirements.txt
chmod +x phenix update.sh lancer.sh 2>/dev/null || true
python scripts/doctor.py || true
echo
echo "Installation terminée. Lance :  ./phenix app --no-browser   puis ouvre http://127.0.0.1:8765"
