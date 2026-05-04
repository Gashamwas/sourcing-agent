#!/bin/bash
# Cloris .app notarization — Phase 2 ``notarize`` slice.
#
# Submits the signed Cloris.app to Apple's notary service via
# ``xcrun notarytool``, waits for the verdict (typically minutes),
# and staples the resulting notarization ticket onto the .app so
# it validates offline on the recipient's Mac.
#
# Pre-requisites:
#   - sign-app.sh has produced a hardened-runtime-signed Cloris.app.
#   - Apple Developer account is set up with a Developer ID
#     Application cert and an app-specific password — see
#     APPLE_DEV_SETUP.md.
#
# Required env vars:
#   CLORIS_NOTARY_PROFILE   — keychain profile name from
#                              `xcrun notarytool store-credentials`
#                              (preferred path).
#   OR ALL OF:
#   CLORIS_APPLE_ID         — your Apple ID email.
#   CLORIS_TEAM_ID          — 10-char Team ID.
#   CLORIS_NOTARY_PASSWORD  — app-specific password for the Apple ID.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
cd "$REPO_ROOT"

APP_PATH="dist/Cloris.app"
ZIP_PATH="dist/Cloris-notary-submission.zip"

if [ ! -d "$APP_PATH" ]; then
    echo "ERROR: $APP_PATH does not exist. Run build-app.sh + sign-app.sh first."
    exit 1
fi

# Verify hardened runtime is on. The notary service rejects apps
# without it — better to catch it here than to wait minutes for the
# notary verdict.
echo "==> Verifying hardened runtime is enabled..."
if ! codesign -dv --verbose=4 "$APP_PATH" 2>&1 | grep -q "flags=.*runtime"; then
    echo "ERROR: $APP_PATH is not signed with hardened runtime."
    echo "       Re-run sign-app.sh — the notary service will reject this."
    exit 1
fi

# Create a flat ZIP for submission. The notary service requires a
# .zip, .pkg, .dmg, or .xip. We submit a ZIP for the .app bundle
# and notarize the DMG separately later in build-dmg.sh.
echo "==> Creating ZIP for notarization submission..."
rm -f "$ZIP_PATH"
ditto -c -k --keepParent "$APP_PATH" "$ZIP_PATH"

# Submit and wait. Two auth paths: keychain profile (preferred) or
# inline Apple ID + app-specific password.
NOTARY_AUTH_ARGS=()
if [ -n "${CLORIS_NOTARY_PROFILE:-}" ]; then
    echo "==> Authenticating via keychain profile: $CLORIS_NOTARY_PROFILE"
    NOTARY_AUTH_ARGS=(--keychain-profile "$CLORIS_NOTARY_PROFILE")
elif [ -n "${CLORIS_APPLE_ID:-}" ] && \
     [ -n "${CLORIS_TEAM_ID:-}" ] && \
     [ -n "${CLORIS_NOTARY_PASSWORD:-}" ]; then
    echo "==> Authenticating via Apple ID + app-specific password"
    NOTARY_AUTH_ARGS=(
        --apple-id "$CLORIS_APPLE_ID"
        --team-id "$CLORIS_TEAM_ID"
        --password "$CLORIS_NOTARY_PASSWORD"
    )
else
    echo "ERROR: No notary credentials configured."
    echo ""
    echo "Either:"
    echo "  (a) Set CLORIS_NOTARY_PROFILE to a profile name from"
    echo "      'xcrun notarytool store-credentials' (preferred)."
    echo "  (b) Set CLORIS_APPLE_ID + CLORIS_TEAM_ID + CLORIS_NOTARY_PASSWORD."
    echo ""
    echo "See APPLE_DEV_SETUP.md."
    exit 1
fi

echo "==> Submitting to Apple notary service (this can take 1-30 minutes)..."
SUBMIT_OUTPUT="$(mktemp)"
xcrun notarytool submit "$ZIP_PATH" "${NOTARY_AUTH_ARGS[@]}" --wait \
    | tee "$SUBMIT_OUTPUT"

# Check verdict.
if grep -q "status: Accepted" "$SUBMIT_OUTPUT"; then
    echo ""
    echo "==> Notary accepted. Stapling the ticket onto the .app..."
    xcrun stapler staple "$APP_PATH"

    echo ""
    echo "==> Verifying staple..."
    xcrun stapler validate "$APP_PATH"

    echo ""
    echo "==> Verifying Gatekeeper acceptance (the recipient's experience)..."
    spctl -a -v "$APP_PATH"

    echo ""
    echo "Notarization complete: $APP_PATH"
    echo "Next: ./cloris/packaging/scripts/build-dmg.sh"
    rm -f "$SUBMIT_OUTPUT"
else
    echo ""
    echo "ERROR: Notarization was not accepted."
    echo ""
    SUBMISSION_ID="$(grep -oE 'id: [a-f0-9-]{36}' "$SUBMIT_OUTPUT" | head -1 | awk '{print $2}')"
    if [ -n "${SUBMISSION_ID:-}" ]; then
        echo "Fetching detailed log for submission $SUBMISSION_ID..."
        xcrun notarytool log "$SUBMISSION_ID" "${NOTARY_AUTH_ARGS[@]}"
    fi
    echo ""
    echo "Common rejection causes:"
    echo "  - Hardened runtime not enabled (re-run sign-app.sh)"
    echo "  - Missing entitlements (check entitlements.plist + sign-app.sh)"
    echo "  - Unsigned nested binaries (the inside-out signing missed something)"
    echo "  - Insecure HTTP loads not declared in NSAppTransportSecurity"
    echo "    (check Info.plist in cloris.spec)"
    rm -f "$SUBMIT_OUTPUT"
    exit 1
fi
