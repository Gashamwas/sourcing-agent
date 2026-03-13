#!/bin/bash
# Start a sourcing session. Chrome must be running (./launch-chrome.sh).
cd "$(dirname "$0")"
python3 run.py --brief config/brief-brazil-real.json --full-run "$@"
