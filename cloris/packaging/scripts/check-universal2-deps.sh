#!/bin/bash
# Verify every C-extension dep is Universal 2 (arm64 + x86_64).
#
# A24's Head of Recruiting may be on either Apple Silicon or Intel
# (older laptop, Intel mini, corp MBP not yet refreshed). The Cloris
# .app is committed to Universal 2 — see plan §2 "Architecture
# decision". An arm64-only dep will silently produce an arm64-only
# .app that crashes on Intel during signing or first launch.
#
# Run from the repo root, inside the active venv:
#     ./cloris/packaging/scripts/check-universal2-deps.sh
#
# Output: one line per checked dep with arch info; non-zero exit
# code if any dep is single-arch.

set -uo pipefail

cd "$(cd "$(dirname "$0")/../../.." && pwd)"

PYTHON_BIN="${PYTHON:-.venv/bin/python}"
if [ ! -x "$PYTHON_BIN" ]; then
    PYTHON_BIN="python3"
fi

VENV_LIB="$($PYTHON_BIN -c 'import site; print(site.getsitepackages()[0])')"
echo "Site-packages: $VENV_LIB"
echo ""

# Deps with .so / .dylib that need Universal 2 verification.
# Pure-Python deps (anthropic, openai, dotenv, etc.) are uniform —
# only check the binary ones.
DEPS_TO_CHECK=(
    "aiohttp"
    "h11"
    "websockets"
    "wsproto"
    "rebrowser_playwright"
    "google.protobuf"
    "pydantic_core"
    "yarl"
    "multidict"
    "frozenlist"
)

EXIT_CODE=0

for dep in "${DEPS_TO_CHECK[@]}"; do
    dep_dir="$VENV_LIB/${dep//.//}"
    if [ ! -d "$dep_dir" ]; then
        # Try egg-info / dist-info pattern.
        dep_dir="$VENV_LIB/${dep%%.*}"
    fi
    if [ ! -d "$dep_dir" ]; then
        echo "  SKIP $dep (not installed)"
        continue
    fi

    SOS=$(find "$dep_dir" \( -name '*.so' -o -name '*.dylib' \) 2>/dev/null | head -3)
    if [ -z "$SOS" ]; then
        echo "  PURE $dep (no compiled libs — universal2 by definition)"
        continue
    fi

    while IFS= read -r so; do
        archs=$(lipo -archs "$so" 2>/dev/null || echo "ERROR")
        if echo "$archs" | grep -qE 'x86_64.*arm64|arm64.*x86_64'; then
            echo "  OK   $dep: $(basename "$so") [$archs]"
        else
            echo "  FAIL $dep: $(basename "$so") [$archs]  <-- single-arch!"
            EXIT_CODE=1
        fi
    done <<<"$SOS"
done

echo ""
if [ "$EXIT_CODE" -eq 0 ]; then
    echo "All checked deps are universal2. Safe to build for both architectures."
else
    echo "WARNING: One or more deps are single-arch."
    echo ""
    echo "Options to fix (see plan §2 'Architecture decision'):"
    echo "  (a) Reinstall the failing dep with the missing arch wheel:"
    echo "      pip install --platform macosx_11_0_arm64 --only-binary=:all: <dep>"
    echo "      pip install --platform macosx_11_0_x86_64 --only-binary=:all: <dep>"
    echo "  (b) Drop universal2 commitment and ship two DMGs (arm64 + x86_64)."
    echo "  (c) Verify the failing arch's wheel actually exists on PyPI; some"
    echo "      C extensions only ship arm64 binary wheels and require source"
    echo "      install on x86_64."
fi

exit "$EXIT_CODE"
