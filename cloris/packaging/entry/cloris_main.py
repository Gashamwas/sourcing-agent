"""PyInstaller entry script for the Cloris main app.

Build target: ``Cloris.app/Contents/MacOS/Cloris`` (the binary the
recipient launches by double-clicking the .app in Applications).

Boots Cloris's app process exactly the way ``cloris start`` does
from the CLI: builds the FastAPI app, opens the pywebview window,
ensures Chrome is up on the dedicated CDP profile, and blocks until
the window closes. There are no CLI args in the .app context — the
recipient never sees a command line — so we hard-code the default
host/port and ignore any args macOS may pass on launch.
"""

from __future__ import annotations

import sys


def _entry() -> int:
    # Lazy import so a packaging-time syntax error in cloris.cli or
    # cloris.app surfaces inside _entry rather than at import-time
    # (which is harder to attach a debugger to under a frozen .app).
    from cloris import app as cloris_app

    fastapi_app = cloris_app.create_app()
    cloris_app.run_app(fastapi_app, host="127.0.0.1", port=0)
    return 0


if __name__ == "__main__":
    raise SystemExit(_entry())
