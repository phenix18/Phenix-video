#!/usr/bin/env bash
# Linux / macOS : installation locale (gratuite)
set -e
cd "$(dirname "$0")"
command -v python3 >/dev/null || { echo "Installe Python 3.10+"; exit 1; }
if ! command -v ffmpeg >/dev/null; then
  if command -v apt >/dev/null; then sudo apt update && sudo apt install -y ffmpeg python3-venv;
  elif command -v brew >/dev/null; then brew install ffmpeg;
  else echo "Installe FFmpeg manuellement"; exit 1; fi
fi
python3 -m venv .venv
. .venv/bin/activate
pip install --upgrade pip
# PyTorch version CPU (évite ~3 Go de paquets NVIDIA inutiles sans GPU)
pip install --resume-retries 10 torch --index-url https://download.pytorch.org/whl/cpu
pip install --default-timeout=120 --resume-retries 10 -r requirements.txt
echo "OK. Lance l'application avec : ./lancer.sh"
