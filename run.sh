#!/usr/bin/env bash
# Outcome-first agent loop controller. Contract: ./run.sh <SIM_URL> runs
# until the scenario finishes, with no manual steps.
# Plain Python 3 + SQLite, no Docker needed: the only dependency is httpx
# (everything else is the standard library). State lives in
# controller_state/<scenario>.db — kill and restart freely, it resumes.
set -euo pipefail
SIM_URL="${1:?usage: ./run.sh <SIM_URL>}"
cd "$(dirname "$0")"
PY="python3"
if [ -x ".venv/bin/python" ]; then PY=".venv/bin/python"; fi
exec "$PY" -m controller.main --url "$SIM_URL"
