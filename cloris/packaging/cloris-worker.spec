# PyInstaller spec for the Cloris worker binary.
#
# Build:
#     pyinstaller --noconfirm cloris/packaging/cloris-worker.spec
#
# Output:
#     dist/cloris-worker/cloris-worker — the standalone worker binary
#
# The build script (cloris/packaging/scripts/build-app.sh) copies
# this binary into ``dist/Cloris.app/Contents/MacOS/cloris-worker``
# after the main app spec produces the .app bundle.
#
# Why a separate binary? In the frozen .app, ``sys.executable`` is
# the main Cloris UI binary (not a python interpreter). The API
# process spawns the worker via subprocess.Popen; with two specs we
# can ship a sibling binary with the heavy orchestrator dep tree
# (rebrowser-playwright, anthropic, openai, linkedin/, github/,
# market_intelligence/, ...) without bloating the main UI binary.
#
# Universal 2 (Apple Silicon + Intel) — same trial-day commitment as
# the main spec. Verify every C-extension dep with ``lipo -info``.

# ruff: noqa

from pathlib import Path
import os

PROJECT_ROOT = Path(os.getcwd()).resolve()

# Hidden imports: anything PyInstaller's static analyzer can't follow.
# The orchestrators dispatch by string in places (e.g. provider lookup,
# strategy registry); pulling them in via hiddenimports keeps the
# bundle complete.
HIDDEN_IMPORTS = [
    # Cloris launchers + orchestrator dispatch.
    "cloris.launchers",
    "cloris.worker",
    # LinkedIn orchestrator + its full dep tree.
    "linkedin",
    "linkedin.session_orchestrator",
    "linkedin.orchestrator",
    "linkedin.browser",
    "linkedin.health",
    "linkedin.input_backends",
    "linkedin.activity_parser",
    "linkedin.identity_experiment_browser",
    # GitHub orchestrator + deps.
    "github",
    "github.session_orchestrator",
    "github.orchestrator",
    "github.config",
    # Shared runtime + brief plumbing.
    "shared",
    "shared.config",
    "shared.user_data_dir",
    "shared.runtime_state",
    "shared.runtime_state.store",
    "shared.runtime_state.read_models",
    "shared.runtime_state.linkedin",
    "shared.runtime_state.linkedin_progress_sync",
    "shared.runtime_state.projections",
    "shared.brief_iteration",
    "shared.brief_loader",
    "shared.brief_writer",
    "shared.brief_v2_schema",
    "shared.judger",
    "shared.identity_resolution",
    "shared.recruiter_brief_resolution",
    "shared.output_paths",
    "shared.governor",
    "shared.human_timing",
    # LLM providers — string dispatch in shared.judger means
    # PyInstaller can't always trace these.
    "anthropic",
    "openai",
    "google.genai",
    # rebrowser-playwright is the CDP client the worker uses to
    # attach to Chrome. It in turn dynamically imports its async
    # backend.
    "rebrowser_playwright",
    "rebrowser_playwright.async_api",
    "rebrowser_playwright._impl",
    # Market intelligence (referenced by tools and reflection paths).
    "market_intelligence",
    "market_intelligence.engine",
    "market_intelligence.reflection",
    # python-dotenv used by shared.config.
    "dotenv",
    # aiohttp + dependencies (rebrowser-playwright pulls these).
    "aiohttp",
    "aiohttp.client",
    "aiohttp.connector",
    # python-ghost-cursor — used by the linkedin browser input
    # backends for human-like typing/clicking.
    "ghost_cursor",
]

# Data: the worker doesn't need the frontend dist/ tree (it's a
# headless process), but it DOES need brief schema files / any
# bundled config Cloris ships. Phase 0 trial doesn't ship sample
# briefs in the .app — the recipient creates briefs through the
# OnboardingFlow. Leave datas empty for now; add config/ files here
# if Phase 1 polish surfaces a need.
DATAS = []


a = Analysis(
    [str(PROJECT_ROOT / "cloris" / "packaging" / "entry" / "cloris_worker.py")],
    pathex=[str(PROJECT_ROOT)],
    binaries=[],
    datas=DATAS,
    hiddenimports=HIDDEN_IMPORTS,
    hookspath=[],
    runtime_hooks=[],
    excludes=[
        # The frontend stack (svelte build) is not needed in the
        # worker binary — the worker has no UI.
        # pywebview is similarly not needed.
        "webview",
    ],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="cloris-worker",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,  # The worker writes to stdout/stderr (logs +
                   # error reporting). Spawn-side detaches stdio
                   # via subprocess.Popen DEVNULL anyway, but
                   # console=True lets dev runs see worker output.
    disable_windowed_traceback=False,
    target_arch="universal2",
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="cloris-worker",
)
