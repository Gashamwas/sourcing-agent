#!/bin/bash
set -euo pipefail

cd "$(dirname "$0")"

BRIEF="${BRIEF:-config/FDL-Colombia/brief-fdl-colombia-v4.json}"
GITHUB_STATE_DIR="${GITHUB_STATE_DIR:-output/state/github/research_engineer_colombia}"
LIVE_LOG="$GITHUB_STATE_DIR/live-console.log"

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

mkdir -p "$GITHUB_STATE_DIR"

echo "Starting GitHub Colombia run..."
echo "  brief: $BRIEF"
echo "  state: $GITHUB_STATE_DIR"
echo "  live log: $LIVE_LOG"
echo

exec > >(tee "$LIVE_LOG") 2>&1

"$PYTHON_BIN" run_github.py \
  --brief "$BRIEF" \
  --state-dir "$GITHUB_STATE_DIR" \
  "$@"
