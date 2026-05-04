# PyInstaller spec for the Cloris main app binary.
#
# Build:
#     pyinstaller --noconfirm cloris/packaging/cloris.spec
#
# Output:
#     dist/Cloris.app                      — the .app bundle
#     dist/Cloris.app/Contents/MacOS/Cloris — the main entry binary
#     dist/Cloris.app/Contents/Resources/  — bundled frontend dist + icon
#
# After this spec produces ``dist/Cloris.app``, the build script
# (cloris/packaging/scripts/build-app.sh) builds the worker spec
# separately and copies the resulting binary into
# ``dist/Cloris.app/Contents/MacOS/cloris-worker`` so the API spawn
# at ``cloris/api.py:_frozen_worker_binary_path`` finds it.
#
# Universal 2 (Apple Silicon + Intel) is the trial-day commitment —
# A24's Head of Recruiting may be on either architecture. Verify
# every C-extension dep with ``lipo -info`` BEFORE the first build
# (see cloris/packaging/APPLE_DEV_SETUP.md for the dep-checklist).

# ruff: noqa
# Spec files are executed by PyInstaller; the ``Analysis`` /
# ``EXE`` / ``BUNDLE`` symbols are injected into the namespace.

from pathlib import Path

# ``__file__`` is not defined in PyInstaller spec eval context.
# Resolve the project root from the working directory PyInstaller
# is invoked from (the repo root, per build-app.sh).
import os

PROJECT_ROOT = Path(os.getcwd()).resolve()

# Hidden imports: modules PyInstaller's static analysis cannot
# discover via ``import`` traversal because they are dynamically
# imported at runtime by FastAPI / uvicorn / our own code.
HIDDEN_IMPORTS = [
    # uvicorn dispatches its protocol handlers by string name.
    "uvicorn.lifespan.on",
    "uvicorn.lifespan.off",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.http.h11_impl",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.protocols.websockets.websockets_impl",
    "uvicorn.protocols.websockets.wsproto_impl",
    "uvicorn.loops.auto",
    "uvicorn.loops.asyncio",
    # h11 / websockets — pulled in by uvicorn protocols.
    "h11",
    "websockets",
    # Cloris's own optional/lazy modules referenced by api.py.
    "cloris.chrome_launcher",
    "cloris.onboarding",
    # python-dotenv used by shared.config.
    "dotenv",
]

# Static data: the built Vite bundle that cloris/api.py:_DIST_DIR
# expects to find at <package>/frontend/dist/. PyInstaller's
# ``datas`` semantics: tuple of (source_path_on_disk,
# destination_inside_bundle).
DATAS = [
    (str(PROJECT_ROOT / "cloris" / "frontend" / "dist"), "cloris/frontend/dist"),
]


a = Analysis(
    [str(PROJECT_ROOT / "cloris" / "packaging" / "entry" / "cloris_main.py")],
    pathex=[str(PROJECT_ROOT)],
    binaries=[],
    datas=DATAS,
    hiddenimports=HIDDEN_IMPORTS,
    hookspath=[],
    runtime_hooks=[],
    excludes=[
        # The orchestrator + worker dependency tree (rebrowser-playwright,
        # anthropic, openai, market_intelligence, linkedin, github, ...)
        # is bundled into the SEPARATE cloris-worker binary spec so the
        # main Cloris UI binary stays small. The main process spawns
        # cloris-worker for any actual sourcing work.
        "rebrowser_playwright",
        "anthropic",
        "openai",
        "google.genai",
        "linkedin",
        "github",
        "market_intelligence",
    ],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Cloris",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    target_arch="universal2",
    codesign_identity=None,  # Signing happens post-build via the
                             # codesign script — see
                             # cloris/packaging/scripts/sign-app.sh.
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="Cloris",
)

app = BUNDLE(
    coll,
    name="Cloris.app",
    icon=str(PROJECT_ROOT / "cloris" / "packaging" / "icon" / "cloris.icns"),
    bundle_identifier="com.cloris.app",
    info_plist={
        # Bundle identity. The bundle id is the canonical handle macOS
        # (and the notary service) use to identify Cloris; once shipped
        # this should not change without a deliberate rename.
        "CFBundleName": "Cloris",
        "CFBundleDisplayName": "Cloris",
        "CFBundleIdentifier": "com.cloris.app",
        "CFBundlePackageType": "APPL",
        # Version: keep both keys in sync. CFBundleShortVersionString
        # is what shows in About / Get Info; CFBundleVersion is the
        # build number macOS uses for "is this an update?" checks.
        "CFBundleShortVersionString": "0.0.1",
        "CFBundleVersion": "0.0.1",
        # Minimum macOS: 12 (Monterey, 2021). Universal 2 is supported
        # since Big Sur (11), but 12.0 is the practical floor for
        # python.org's universal2 interpreter wheels.
        "LSMinimumSystemVersion": "12.0",
        # Display: high-DPI on Retina; honor system dark/light mode
        # (Cloris's UI is light-cream regardless, but
        # NSRequiresAquaSystemAppearance=False prevents macOS from
        # forcing a legacy appearance on us).
        "NSHighResolutionCapable": True,
        "NSRequiresAquaSystemAppearance": False,
        # Cloris is a UI app (Dock icon, menu bar, focusable window),
        # not a background agent. Explicit so a future contributor
        # doesn't flip this to True by mistake.
        "LSUIElement": False,
        # App Store category for grouping (does not affect Gatekeeper
        # behavior; included for completeness so the bundle metadata
        # matches what the App Store / Spotlight surface).
        "LSApplicationCategoryType": "public.app-category.business",
        # Network: Cloris talks to LinkedIn (via the recipient's
        # browser, not directly), Anthropic API, and 127.0.0.1 (its
        # own UI server + CDP). NSAppTransportSecurity defaults are
        # fine — we don't need any insecure exceptions.
        # Explicitly disabling arbitrary loads keeps the app honest.
        "NSAppTransportSecurity": {
            "NSAllowsArbitraryLoads": False,
            # Localhost exception so the pywebview window can reach
            # Cloris's own FastAPI server over plain HTTP.
            "NSExceptionDomains": {
                "127.0.0.1": {
                    "NSExceptionAllowsInsecureHTTPLoads": True,
                },
                "localhost": {
                    "NSExceptionAllowsInsecureHTTPLoads": True,
                },
            },
        },
        # Privacy purpose strings: Cloris does NOT use camera /
        # microphone / contacts / location / etc. Leaving these out
        # means macOS won't surface spurious permission prompts. If
        # we ever add a feature requiring one, the Info.plist must
        # be updated AND a corresponding NSXxxUsageDescription must
        # be added or macOS will deny silently.
    },
)
