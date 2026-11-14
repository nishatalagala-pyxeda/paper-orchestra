#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ ! -x .venv/bin/python ]]; then
  echo 'Create a Python 3.11+ .venv and install requirements.txt first.' >&2
  exit 1
fi
exec .venv/bin/python -m streamlit run frontend/app.py --server.address 127.0.0.1 --server.headless true --browser.gatherUsageStats false "$@"
