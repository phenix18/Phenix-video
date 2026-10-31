#!/usr/bin/env bash
# Phenix-video — © 2026 Phenix - kcw. Mise à jour : récupère la dernière version et met à jour les dépendances.
set -e
cd "$(dirname "$0")"
if [ -d .git ]; then
  git pull --ff-only
else
  echo "Ce dossier n'est pas un clone git : télécharge la dernière version depuis GitHub."
fi
[ -d .venv ] || { echo "Environnement absent : lance ./installer.sh"; exit 1; }
. .venv/bin/activate
pip install --default-timeout=120 --resume-retries 10 -r requirements.txt
python scripts/doctor.py || true
echo "Version : $(cat VERSION)"
