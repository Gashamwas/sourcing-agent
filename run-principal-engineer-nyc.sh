#!/bin/bash
set -euo pipefail

# Launch the brief-driven LinkedIn full run for the Principal Engineer - NYC brief.
#
# Typical usage:
#   ./launch-chrome.sh
#   bash ./run-principal-engineer-nyc.sh
#   ./run-principal-engineer-nyc.sh --resume

cd "$(dirname "$0")"

python3 -m linkedin.run \
  --brief config/Principal-Forward-Deployed-AI-Engineer/brief-principal-forward-deployed-ai-engineer-nyc-v1.json \
  --full-run \
  --input-mode concurrent \
  "$@"
