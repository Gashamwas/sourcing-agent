#!/bin/bash
set -euo pipefail

cd "$(dirname "$0")"

BRIEF="${BRIEF:-config/FDL-Colombia/brief-fdl-colombia-v4.json}"
LINKEDIN_STATE_DIR="${LINKEDIN_STATE_DIR:-output/state/linkedin/research_engineer_colombia_2015831122}"

if [ ! -f "$BRIEF" ]; then
  echo "ERROR: brief not found: $BRIEF" >&2
  exit 1
fi

if [ -n "${PYTHON_BIN:-}" ]; then
  :
elif [ -x ".venv/bin/python" ]; then
  PYTHON_BIN=".venv/bin/python"
elif command -v python3.14 >/dev/null 2>&1; then
  PYTHON_BIN="$(command -v python3.14)"
elif [ -x "/Users/sam.vangelos/homebrew/bin/python3.14" ]; then
  PYTHON_BIN="/Users/sam.vangelos/homebrew/bin/python3.14"
else
  echo "ERROR: no suitable Python interpreter found. Set PYTHON_BIN to the project venv or another Python 3.10+ interpreter." >&2
  exit 1
fi

mkdir -p "$LINKEDIN_STATE_DIR"

echo "Starting LinkedIn Colombia run..."
echo "  brief: $BRIEF"
echo "  state: $LINKEDIN_STATE_DIR"
echo

exec "$PYTHON_BIN" -m linkedin.session_orchestrator \
  --brief "$BRIEF" \
  --state-dir "$LINKEDIN_STATE_DIR" \
  "$@"
