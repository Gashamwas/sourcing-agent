#!/bin/bash
# Launch Chrome with CDP debugging enabled.
# Uses a dedicated profile at ~/.chrome-cdp (log into LinkedIn Recruiter once, persists forever).
cd "$(dirname "$0")"

PORT=9222
PROFILE="$HOME/.chrome-cdp"
FORCE_RELAUNCH=0

if [ "$1" = "--force" ]; then
    FORCE_RELAUNCH=1
fi

cdp_healthy() {
    local version_ok=1
    local list_ok=1

    curl -sf "http://127.0.0.1:$PORT/json/version" >/dev/null 2>&1 || version_ok=0
    curl -sf "http://127.0.0.1:$PORT/json/list" | python3 - <<'PY' >/dev/null 2>&1 || list_ok=0
import json
import sys

targets = json.load(sys.stdin)
if not isinstance(targets, list):
    raise SystemExit(1)
PY

    [ "$version_ok" -eq 1 ] && [ "$list_ok" -eq 1 ]
}

# Check if already running and healthy
if [ "$FORCE_RELAUNCH" -eq 0 ] && cdp_healthy; then
    echo "Chrome already running on CDP port $PORT."
    exit 0
fi

if [ "$FORCE_RELAUNCH" -eq 1 ]; then
    echo "Force relaunch requested — restarting Chrome on CDP port $PORT."
elif curl -sf "http://127.0.0.1:$PORT/json/version" >/dev/null 2>&1; then
    echo "Chrome CDP endpoint is up but unhealthy — restarting Chrome."
fi

pkill -9 -f "Google Chrome" 2>/dev/null
sleep 2
rm -f "$PROFILE/SingletonLock" 2>/dev/null
rm -f "$HOME/Library/Application Support/Google/Chrome/SingletonLock" 2>/dev/null
mkdir -p "$PROFILE"

/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome \
    --remote-debugging-port="$PORT" \
    --user-data-dir="$PROFILE" \
    >/dev/null 2>&1 &

for i in $(seq 1 20); do
    if curl -s "http://127.0.0.1:$PORT/json/version" >/dev/null 2>&1; then
        echo "Chrome ready on CDP port $PORT."
        echo "Open linkedin.com/talent in Chrome, then run ./run-search.sh"
        exit 0
    fi
    sleep 1
done

echo "ERROR: Chrome launched but CDP port $PORT never responded."
exit 1
