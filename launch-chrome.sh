#!/bin/bash
# Launch Chrome with CDP debugging enabled.
# Uses a dedicated profile at ~/.chrome-cdp (log into LinkedIn Recruiter once, persists forever).
cd "$(dirname "$0")"

PORT=9222
PROFILE="$HOME/.chrome-cdp"

# Check if already running
if curl -s "http://127.0.0.1:$PORT/json/version" >/dev/null 2>&1; then
    echo "Chrome already running on CDP port $PORT."
    exit 0
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
