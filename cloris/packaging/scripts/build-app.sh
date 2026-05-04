#!/bin/bash
# Cloris .app build script — Phase 1 ``pyinstaller-specs`` slice.
#
# Builds both PyInstaller specs (cloris.spec + cloris-worker.spec)
# and assembles the final ``dist/Cloris.app`` with the worker
# binary placed at ``Contents/MacOS/cloris-worker`` so the API
# spawn at ``cloris/api.py:_frozen_worker_binary_path`` finds it.
#
# Run from the repo root:
#     ./cloris/packaging/scripts/build-app.sh
#
# Prerequisites (verify before first run):
#     - ``pip install pyinstaller`` in the active venv.
#     - ``cloris/packaging/icon/cloris.icns`` exists (Phase 4 icon).
#     - The frontend dist/ is up to date (``cd cloris/frontend && pnpm build``).
#     - Universal 2 wheels for every dep — see APPLE_DEV_SETUP.md.
#       Run ``./cloris/packaging/scripts/check-universal2-deps.sh`` to verify.
#
# This script does NOT sign or notarize. Run sign-app.sh +
# notarize-app.sh after this completes (both gated on Apple
# Developer setup — see APPLE_DEV_SETUP.md).

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
cd "$REPO_ROOT"

echo "==> Cleaning previous build artifacts..."
rm -rf dist/Cloris.app dist/cloris-worker build

echo "==> Verifying frontend dist/ is up to date..."
if [ ! -f "cloris/frontend/dist/index.html" ]; then
    echo "ERROR: cloris/frontend/dist/index.html missing."
    echo "       Run: cd cloris/frontend && pnpm build"
    exit 1
fi

echo "==> Verifying icon exists..."
if [ ! -f "cloris/packaging/icon/cloris.icns" ]; then
    echo "ERROR: cloris/packaging/icon/cloris.icns missing."
    echo "       Run: ./cloris/packaging/icon/build-icon.sh"
    exit 1
fi

echo "==> Building cloris-worker spec (heavy orchestrator deps)..."
pyinstaller --noconfirm --clean cloris/packaging/cloris-worker.spec

echo "==> Building cloris.spec (main UI)..."
pyinstaller --noconfirm --clean cloris/packaging/cloris.spec

echo "==> Copying cloris-worker into Cloris.app/Contents/MacOS/..."
WORKER_BIN="dist/cloris-worker/cloris-worker"
APP_MACOS_DIR="dist/Cloris.app/Contents/MacOS"
if [ ! -x "$WORKER_BIN" ]; then
    echo "ERROR: cloris-worker binary not found at $WORKER_BIN"
    exit 1
fi
cp "$WORKER_BIN" "$APP_MACOS_DIR/cloris-worker"
chmod +x "$APP_MACOS_DIR/cloris-worker"

echo "==> Copying worker dependencies (libs/binaries) into Cloris.app..."
# The worker's _internal/ tree (PyInstaller's collected libraries) must
# travel with the worker binary. Copy it into the .app's
# Contents/Resources so cloris-worker's bootloader can find its libs.
WORKER_INTERNAL_SRC="dist/cloris-worker/_internal"
WORKER_INTERNAL_DST="dist/Cloris.app/Contents/Resources/cloris-worker-internal"
if [ -d "$WORKER_INTERNAL_SRC" ]; then
    rm -rf "$WORKER_INTERNAL_DST"
    cp -R "$WORKER_INTERNAL_SRC" "$WORKER_INTERNAL_DST"
fi

echo "==> Verifying universal2 architectures..."
for binary in "$APP_MACOS_DIR/Cloris" "$APP_MACOS_DIR/cloris-worker"; do
    if ! lipo -info "$binary" 2>&1 | grep -qE "x86_64.*arm64|arm64.*x86_64"; then
        echo "WARNING: $binary is not universal2 (lipo -info: $(lipo -info "$binary"))"
        echo "         A24 may be on Intel — verify deps with check-universal2-deps.sh"
    else
        echo "OK: $binary is universal2"
    fi
done

echo ""
echo "Build complete: dist/Cloris.app"
echo ""
echo "Next steps:"
echo "  1. ./cloris/packaging/scripts/sign-app.sh   (signs nested binaries inside-out)"
echo "  2. ./cloris/packaging/scripts/notarize-app.sh (xcrun notarytool + stapler)"
echo "  3. ./cloris/packaging/scripts/build-dmg.sh   (signed DMG with drag-to-Apps)"
