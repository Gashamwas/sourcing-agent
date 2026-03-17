#!/bin/bash
# Start a sourcing session via the session orchestrator.
# Chrome must be running (./launch-chrome.sh).
#
# Usage:
#   ./run-search.sh                    # full day cycle with default brief
#   ./run-search.sh --single-session   # single session only
#   ./run-search.sh --decoy-only       # passive browsing only
#   ./run-search.sh --status           # check 24h budget
cd "$(dirname "$0")"
python3 session_orchestrator.py \
  --brief config/brief-fdl-brazil-v3.json \
  --search-config config/search-strings-and-filters.json \
  "$@"
