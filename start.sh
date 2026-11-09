#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
python3 -c 'import tkinter' || { echo 'Instale o pacote python3-tk da sua distribuicao.'; exit 1; }
[ -x .venv/bin/python ] || python3 -m venv .venv
.venv/bin/python -m pip install --only-binary=:all: -r requirements.txt
.venv/bin/python tools/prepare_model.py
exec .venv/bin/python run.py "$@"
