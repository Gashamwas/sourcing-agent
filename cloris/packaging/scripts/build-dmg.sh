#!/bin/bash
# Cloris DMG build — Phase 3 ``dmg`` slice.
#
# Wraps the signed + notarized Cloris.app into a Drag-To-Applications
# DMG, signs the DMG itself (so the recipient gets a "verified
# developer" signature on first download), and outputs the final
# distribution artifact at dist/Cloris.dmg.
#
# Pre-requisites:
#   - sign-app.sh + notarize-app.sh have produced a notarized
#     dist/Cloris.app with the staple ticket attached.
#   - ``brew install create-dmg`` (https://github.com/sindresorhus/create-dmg)
#   - CLORIS_SIGN_IDENTITY env var (same as sign-app.sh).
#
# Run from the repo root:
#     ./cloris/packaging/scripts/build-dmg.sh
#
# Output:
#   dist/Cloris.dmg                     — the final distributable
#   dist/Cloris.dmg.sha256              — checksum (optional, generated)
#
# Distribution: upload Cloris.dmg + CLORIS_DOES_AND_DOES_NOT.md to a
# private cloud bucket with a presigned URL. Do NOT use a public
# link — the marquee customer should receive the artifact through a
# named delivery channel.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
cd "$REPO_ROOT"

APP_PATH="dist/Cloris.app"
DMG_PATH="dist/Cloris.dmg"
DMG_DIR="$(dirname "$DMG_PATH")"

if [ ! -d "$APP_PATH" ]; then
    echo "ERROR: $APP_PATH does not exist."
    echo "       Run build-app.sh + sign-app.sh + notarize-app.sh first."
    exit 1
fi

# Verify the app is notarized (the staple ticket is attached).
echo "==> Verifying notarization staple..."
if ! xcrun stapler validate "$APP_PATH" >/dev/null 2>&1; then
    echo "WARNING: $APP_PATH is not stapled."
    echo "         The recipient will need internet on first launch for"
    echo "         Gatekeeper to phone home and verify notarization."
    echo "         Run notarize-app.sh first if you want offline validation."
fi

if [ -z "${CLORIS_SIGN_IDENTITY:-}" ]; then
    echo "WARNING: CLORIS_SIGN_IDENTITY is unset; DMG will not be signed."
    echo "         An unsigned DMG triggers Gatekeeper warnings on download."
    echo "         Set CLORIS_SIGN_IDENTITY (see APPLE_DEV_SETUP.md) and re-run."
fi

# Check create-dmg is installed.
if ! command -v create-dmg >/dev/null 2>&1; then
    echo "ERROR: create-dmg is not installed."
    echo "       Install via: brew install create-dmg"
    exit 1
fi

# Build the DMG.
#
# Layout:
#   - Window: 540x380 px
#   - Icon size: 96 px
#   - Cloris.app on the left, Applications symlink on the right
#   - Recipient drags one to the other (the macOS-canonical install gesture)
#
# Volume name "Cloris" appears in Finder's sidebar after mount.
echo "==> Building DMG..."
rm -f "$DMG_PATH"

create-dmg \
    --volname "Cloris" \
    --window-pos 200 120 \
    --window-size 540 380 \
    --icon-size 96 \
    --icon "Cloris.app" 140 190 \
    --hide-extension "Cloris.app" \
    --app-drop-link 400 190 \
    --no-internet-enable \
    "$DMG_PATH" \
    "$APP_PATH"

if [ ! -f "$DMG_PATH" ]; then
    echo "ERROR: create-dmg did not produce $DMG_PATH"
    exit 1
fi

# Sign the DMG itself if the identity is configured.
if [ -n "${CLORIS_SIGN_IDENTITY:-}" ]; then
    echo "==> Signing DMG..."
    codesign --sign "$CLORIS_SIGN_IDENTITY" --timestamp "$DMG_PATH"

    # Verify signature.
    codesign --verify --verbose=2 "$DMG_PATH"
fi

# Generate a checksum for the recipient to verify the download.
echo "==> Generating SHA-256 checksum..."
shasum -a 256 "$DMG_PATH" | tee "${DMG_PATH}.sha256"

# Final summary.
DMG_SIZE_HUMAN=$(du -h "$DMG_PATH" | awk '{print $1}')
echo ""
echo "DMG ready: $DMG_PATH ($DMG_SIZE_HUMAN)"
echo "Checksum: ${DMG_PATH}.sha256"
echo ""
echo "Hand-off package for the recipient:"
echo "  $DMG_PATH"
echo "  ${DMG_PATH}.sha256"
echo "  cloris/packaging/CLORIS_DOES_AND_DOES_NOT.md"
echo ""
echo "Upload these to a private S3 bucket with a presigned URL"
echo "(7-day expiry recommended). Do NOT use a public link."
