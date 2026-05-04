#!/bin/bash
set -euo pipefail

cd "$(dirname "$0")"

BRIEF="config/FDL-Colombia/brief-fdl-colombia-v4.json"
LINKEDIN_STATE_DIR="${LINKEDIN_STATE_DIR:-output/state/linkedin/fdl_colombia_v4_dual}"
GITHUB_STATE_DIR="${GITHUB_STATE_DIR:-output/state/github/fdl_colombia_v4_dual}"
LOG_DIR="output/logs"
INPUT_MODE="concurrent"
RESUME=0
SINGLE_SESSION=0

usage() {
  cat <<'EOF'
Usage:
  ./run-colombia-dual.sh [--resume] [--single-session] [--input-mode concurrent|away]

What it does:
  1. Starts the GitHub Colombia sourcing run in the background
  2. Starts the LinkedIn Colombia sourcing run in the foreground

Notes:
  - Uses the shared Colombia v4 brief for both sources
  - Uses explicit state directories to avoid collisions with older Colombia runs
  - Expects Python 3.14 or another 3.10+ interpreter exposed as python3.14

Optional env vars:
  PYTHON_BIN           Override the Python interpreter path
  LINKEDIN_STATE_DIR   Override the LinkedIn state directory
  GITHUB_STATE_DIR     Override the GitHub state directory
EOF
}

if [ $# -gt 0 ]; then
  while [ $# -gt 0 ]; do
    case "$1" in
      --resume)
        RESUME=1
        shift
        ;;
      --single-session)
        SINGLE_SESSION=1
        shift
        ;;
      --input-mode)
        if [ $# -lt 2 ]; then
          echo "ERROR: --input-mode requires a value: concurrent or away" >&2
          exit 1
        fi
        INPUT_MODE="$2"
        case "$INPUT_MODE" in
          concurrent|away) ;;
          *)
            echo "ERROR: --input-mode must be 'concurrent' or 'away'" >&2
            exit 1
            ;;
        esac
        shift 2
        ;;
      --no-launch-chrome)
        # Backward-compatible no-op. This wrapper no longer touches Chrome.
        shift
        ;;
      -h|--help)
        usage
        exit 0
        ;;
      *)
        echo "ERROR: unknown option: $1" >&2
        usage >&2
        exit 1
        ;;
    esac
  done
fi

if [ ! -f "$BRIEF" ]; then
  echo "ERROR: brief not found: $BRIEF" >&2
  exit 1
fi

if [ -n "${PYTHON_BIN:-}" ]; then
  :
elif command -v python3.14 >/dev/null 2>&1; then
  PYTHON_BIN="$(command -v python3.14)"
elif [ -x "/Users/sam.vangelos/homebrew/bin/python3.14" ]; then
  PYTHON_BIN="/Users/sam.vangelos/homebrew/bin/python3.14"
else
  echo "ERROR: python3.14 not found. Set PYTHON_BIN to a Python 3.10+ interpreter." >&2
  exit 1
fi

mkdir -p "$LINKEDIN_STATE_DIR" "$GITHUB_STATE_DIR" "$LOG_DIR"

timestamp="$(date +%Y%m%d-%H%M%S)"
GITHUB_LOG="$LOG_DIR/github-colombia-v4-dual-$timestamp.log"

GITHUB_CMD=(
  "$PYTHON_BIN" run_github.py
  --brief "$BRIEF"
  --state-dir "$GITHUB_STATE_DIR"
)

LINKEDIN_CMD=(
  "$PYTHON_BIN" -m linkedin.session_orchestrator
  --brief "$BRIEF"
  --state-dir "$LINKEDIN_STATE_DIR"
  --input-mode "$INPUT_MODE"
)

if [ "$RESUME" -eq 1 ]; then
  GITHUB_CMD+=(--resume)
  LINKEDIN_CMD+=(--resume)
fi

if [ "$SINGLE_SESSION" -eq 1 ]; then
  GITHUB_CMD+=(--single-session)
  LINKEDIN_CMD+=(--single-session)
fi

echo "Starting GitHub Colombia run in background..."
echo "  brief: $BRIEF"
echo "  state: $GITHUB_STATE_DIR"
echo "  log:   $GITHUB_LOG"
"${GITHUB_CMD[@]}" >"$GITHUB_LOG" 2>&1 &
GITHUB_PID=$!

echo
echo "Starting LinkedIn Colombia run in foreground..."
echo "  brief: $BRIEF"
echo "  state: $LINKEDIN_STATE_DIR"
echo "  input: $INPUT_MODE"
echo
echo "GitHub pid: $GITHUB_PID"
echo "GitHub log: $GITHUB_LOG"
echo
exec "${LINKEDIN_CMD[@]}"
