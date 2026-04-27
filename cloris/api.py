"""Cloris HTTP surface (Slice 1).

Exactly two endpoints in this slice:

- ``GET /healthz`` — readiness probe used by :func:`cloris.app.run_app` and by
  external smoke checks. Stable JSON contract: ``status``, ``slice``,
  ``version``.
- ``GET /`` — returns the inline placeholder ``index.html`` directly. Slice 1
  intentionally does **not** mount a ``StaticFiles`` tree.

Worker control, status aggregation, and any ``/api/*`` semantic surfaces are
out of scope per ``plans/cloris-shell-v0.md`` and the role-agnostic sequencing
discipline.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse

from cloris import __version__


router = APIRouter()

_FRONTEND_DIR = Path(__file__).parent / "frontend"
_INDEX_HTML = _FRONTEND_DIR / "index.html"


@router.get("/healthz")
def healthz() -> dict[str, str]:
    """Readiness probe used by the run_app lifecycle and tests."""

    return {
        "status": "ok",
        "slice": "v0-shell-slice-1",
        "version": __version__,
    }


@router.get("/")
def index() -> FileResponse:
    """Serve the placeholder index page directly (no static mount)."""

    return FileResponse(_INDEX_HTML, media_type="text/html")
