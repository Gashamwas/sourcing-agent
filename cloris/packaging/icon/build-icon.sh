#!/bin/bash
# Cloris .app icon build — Phase 4 ``icon-pipeline`` slice.
#
# Renders both icon SVGs (full + small-size variant) at every macOS-
# required size, packs them into an .iconset, and runs ``iconutil``
# to produce the final ``cloris.icns`` PyInstaller embeds via the
# spec file's ``BUNDLE(..., icon=...)`` arg.
#
# Sizes (per Apple's "Provide multiple icon sizes" guidelines):
#     16, 32, 64, 128, 256, 512, 1024 — at @1x and @2x.
#
# Source picker:
#     ≤ 32 px → icon-small.svg  (deliberately reduced detail)
#     ≥ 64 px → icon-full.svg   (the sewing-needles motion graphic)
#
# Pre-requisites:
#     brew install librsvg   (provides rsvg-convert)
#     iconutil               (built into macOS, comes with Xcode CLI)
#
# Run from the repo root:
#     ./cloris/packaging/icon/build-icon.sh
#
# Output:
#     cloris/packaging/icon/cloris.icns
#
# After this completes, ``cloris/packaging/scripts/build-app.sh`` can
# proceed — its first check verifies cloris.icns exists.

set -euo pipefail

ICON_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$ICON_DIR"

if ! command -v iconutil >/dev/null 2>&1; then
    echo "ERROR: iconutil not found (built into macOS Xcode CLI)."
    echo "       Install via: xcode-select --install"
    exit 1
fi

# SVG renderer: prefer rsvg-convert (faster, smaller dep tree). Fall
# back to a Python helper that uses cairosvg, which is pip-installable
# and avoids the heavy librsvg homebrew install. The fallback ships in
# the same directory at render-svg.py.
RENDER_BACKEND=""
if command -v rsvg-convert >/dev/null 2>&1; then
    RENDER_BACKEND="rsvg"
    echo "==> Using rsvg-convert backend"
elif "${PYTHON:-${REPO_PYTHON:-python3}}" -c "import cairosvg" >/dev/null 2>&1; then
    RENDER_BACKEND="cairosvg"
    PYTHON_BIN="${PYTHON:-${REPO_PYTHON:-python3}}"
    echo "==> Using cairosvg (Python) backend via $PYTHON_BIN"
elif [ -x "$ICON_DIR/../../../.venv/bin/python" ] && \
     "$ICON_DIR/../../../.venv/bin/python" -c "import cairosvg" >/dev/null 2>&1; then
    RENDER_BACKEND="cairosvg"
    PYTHON_BIN="$ICON_DIR/../../../.venv/bin/python"
    echo "==> Using cairosvg (Python) backend via $PYTHON_BIN (project venv)"
else
    echo "ERROR: no SVG renderer available."
    echo ""
    echo "Install one of:"
    echo "  (a) brew install librsvg                   # rsvg-convert"
    echo "  (b) pip install cairosvg pillow            # Python fallback"
    exit 1
fi

if [ ! -f icon-full.svg ]; then
    echo "ERROR: icon-full.svg missing."
    exit 1
fi
if [ ! -f icon-small.svg ]; then
    echo "ERROR: icon-small.svg missing."
    exit 1
fi

ICONSET_DIR="cloris.iconset"
rm -rf "$ICONSET_DIR" cloris.icns
mkdir "$ICONSET_DIR"

# Background: --cream (#f5efe1) — see the SVGs. We pass it on the
# command line too so any transparent regions (e.g. anti-aliased
# edges of the rect) get the cream behind them in the rendered PNG.
BG_COLOR="#f5efe1"

render() {
    local size="$1"
    local out="$2"
    local src
    if [ "$size" -le 32 ]; then
        src=icon-small.svg
    else
        src=icon-full.svg
    fi
    if [ "$RENDER_BACKEND" = "rsvg" ]; then
        rsvg-convert -w "$size" -h "$size" -b "$BG_COLOR" "$src" -o "$ICONSET_DIR/$out"
    else
        "$PYTHON_BIN" "$ICON_DIR/render-svg.py" \
            --src "$src" \
            --out "$ICONSET_DIR/$out" \
            --size "$size" \
            --bg "$BG_COLOR"
    fi
    echo "  rendered $out (from $src)"
}

# Apple's iconset naming convention:
#   icon_<N>x<N>.png       (1x)
#   icon_<N>x<N>@2x.png    (2x — physical size 2N)
#
# So the 16x16 entries need a 16-pixel @1x and a 32-pixel @2x. The
# loop below covers every size Finder, Spotlight, and Dock will
# request.
for size in 16 32 128 256 512; do
    render "$size" "icon_${size}x${size}.png"
    dbl=$((size * 2))
    render "$dbl" "icon_${size}x${size}@2x.png"
done

# 1024@2x doesn't exist in Apple's spec; 512@2x = 1024 covers it.
# But Finder also looks for an explicit 1024 in some contexts.
render 1024 "icon_512x512@2x.png"

# Build the .icns.
iconutil -c icns "$ICONSET_DIR" -o cloris.icns

# Cleanup.
rm -rf "$ICONSET_DIR"

# Verify the .icns has all the expected sizes.
echo ""
echo "==> Verifying cloris.icns contents..."
sips -i cloris.icns 2>/dev/null | head -3 || true
ICNS_SIZE=$(stat -f %z cloris.icns)
echo "  cloris.icns built: ${ICNS_SIZE} bytes"

echo ""
echo "Icon ready: $ICON_DIR/cloris.icns"
echo "  Embedded by cloris/packaging/cloris.spec via BUNDLE(icon=...)"
