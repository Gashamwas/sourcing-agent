#!/bin/bash
# Cloris .app code signing — Phase 2 ``codesign`` slice.
#
# Signs the built ``dist/Cloris.app`` from the inside out:
#
#   1. Every .so / .dylib in Contents/Frameworks/ and
#      Contents/Resources/ (including the worker's _internal/
#      tree we copied in during build-app.sh).
#   2. The cloris-worker sibling binary at Contents/MacOS/cloris-worker.
#   3. The main Cloris binary at Contents/MacOS/Cloris.
#   4. The .app bundle itself.
#
# Apple's recommendation: sign nested code from the inside out,
# WITHOUT --deep. ``--deep`` hides which item is failing if signing
# breaks, and Apple has been deprecating the pattern.
# https://developer.apple.com/forums/thread/691986
#
# Required env vars (see APPLE_DEV_SETUP.md):
#     CLORIS_SIGN_IDENTITY  — the full "Developer ID Application: ..."
#                              string from `security find-identity`.
#
# Run from the repo root, after build-app.sh:
#     ./cloris/packaging/scripts/sign-app.sh

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
cd "$REPO_ROOT"

if [ -z "${CLORIS_SIGN_IDENTITY:-}" ]; then
    echo "ERROR: CLORIS_SIGN_IDENTITY env var is unset."
    echo ""
    echo "Set it to your Developer ID Application identity, e.g.:"
    echo "  export CLORIS_SIGN_IDENTITY='Developer ID Application: Your Org (TEAMID1234)'"
    echo ""
    echo "Find it via: security find-identity -p codesigning -v | grep 'Developer ID Application'"
    echo ""
    echo "If you have not set up the cert yet, see APPLE_DEV_SETUP.md."
    exit 1
fi

APP_PATH="dist/Cloris.app"
ENTITLEMENTS="cloris/packaging/entitlements.plist"

if [ ! -d "$APP_PATH" ]; then
    echo "ERROR: $APP_PATH does not exist. Run build-app.sh first."
    exit 1
fi
if [ ! -f "$ENTITLEMENTS" ]; then
    echo "ERROR: $ENTITLEMENTS missing."
    exit 1
fi

echo "==> Signing identity: $CLORIS_SIGN_IDENTITY"
echo "==> Entitlements: $ENTITLEMENTS"
echo ""

# Common codesign args used everywhere.
#   --timestamp           Required for notarization compliance.
#   --options runtime     Hardened runtime — required by notary service.
#   --force               Overwrite any existing signature; idempotent
#                         re-runs are a frequent need during debugging.
SIGN_OPTS=(
    --sign "$CLORIS_SIGN_IDENTITY"
    --timestamp
    --options runtime
    --force
    --entitlements "$ENTITLEMENTS"
)

# Step 1: nested .so / .dylib files.
#
# Order matters: dynamic libraries that other libraries depend on
# must be signed before their dependents. ``find ... -depth`` walks
# leaves first, which approximates the right order well enough for
# a pure Python+C-extension app. Hand-curate if signing fails on a
# specific dylib due to a dependent already being signed.
echo "==> Signing nested .so / .dylib files (deepest first)..."
find "$APP_PATH" \( -name '*.so' -o -name '*.dylib' \) -depth -print0 | \
while IFS= read -r -d '' lib; do
    codesign "${SIGN_OPTS[@]}" "$lib" 2>&1 | grep -v "^$APP_PATH" || true
done

# Step 2: framework bundles (if any).
echo "==> Signing nested .framework bundles..."
find "$APP_PATH" -name '*.framework' -depth -print0 | \
while IFS= read -r -d '' framework; do
    codesign "${SIGN_OPTS[@]}" "$framework" || true
done

# Step 3: the cloris-worker sibling binary.
WORKER_BIN="$APP_PATH/Contents/MacOS/cloris-worker"
if [ -f "$WORKER_BIN" ]; then
    echo "==> Signing cloris-worker..."
    codesign "${SIGN_OPTS[@]}" "$WORKER_BIN"
else
    echo "WARNING: $WORKER_BIN not found. The .app will fail to launch sourcing runs."
fi

# Step 4: the main Cloris binary.
MAIN_BIN="$APP_PATH/Contents/MacOS/Cloris"
echo "==> Signing main Cloris binary..."
codesign "${SIGN_OPTS[@]}" "$MAIN_BIN"

# Step 5: the .app bundle as a whole.
echo "==> Signing Cloris.app bundle..."
codesign "${SIGN_OPTS[@]}" "$APP_PATH"

# Verify.
echo ""
echo "==> Verifying signature..."
codesign --verify --deep --strict --verbose=2 "$APP_PATH"

echo ""
echo "==> Verifying hardened runtime + entitlements..."
codesign -dv --verbose=4 "$APP_PATH" 2>&1 | grep -E "Authority|TeamIdentifier|flags|Hash"
codesign -d --entitlements - "$APP_PATH" 2>&1 | head -20

echo ""
echo "Signing complete: $APP_PATH"
echo ""
echo "Next: ./cloris/packaging/scripts/notarize-app.sh"
