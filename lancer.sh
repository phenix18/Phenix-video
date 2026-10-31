#!/usr/bin/env bash
cd "$(dirname "$0")"
[ -d .venv ] || { echo "Lance d'abord ./installer.sh"; exit 1; }
. .venv/bin/activate
python scripts/app.py "$@"
