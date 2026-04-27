"""Cloris HTTP surface.

Slice 1 endpoints (kept byte-identical here):

- ``GET /healthz`` — readiness probe used by :func:`cloris.app.run_app` and by
  external smoke checks. Stable JSON contract: ``status``, ``slice``,
  ``version``. The slice tag stays ``"v0-shell-slice-1"`` because this is a
  readiness probe, not a slice-version banner.
- ``GET /`` — returns the inline placeholder ``index.html`` directly. Slice 1
  intentionally does **not** mount a ``StaticFiles`` tree.

Slice 2 endpoint (kept byte-identical here):

- ``GET /api/status`` — read-only aggregation across discovered
  ``output/state/<source>/*`` directories. The ``"v0-shell-slice-2"`` slice
  tag lives only in this payload.

Slice 3 endpoint:

- ``POST /api/launch/linkedin`` — spawn a detached
  ``python -m cloris.worker ...`` subprocess that writes ``worker.json``
  and ``execvp``s into ``linkedin.session_orchestrator``. LinkedIn-only,
  concurrent-only, fresh-only. Stop, resume, and pause are out of scope.

Pause/resume and any semantic surfaces are still out of scope per
``plans/cloris-shell-v0.md`` and the role-agnostic sequencing discipline.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict

from cloris import __version__
from cloris.control_plane import aggregate_status
from cloris.models import LaunchResponse, StatusResponse
from cloris.worker import (
    BriefPathNotFoundError,
    WorkerAlreadyRunningError,
    is_pid_alive,
    read_sidecar,
)


router = APIRouter()

_FRONTEND_DIR = Path(__file__).parent / "frontend"
_INDEX_HTML = _FRONTEND_DIR / "index.html"


class LaunchLinkedInRequest(BaseModel):
    """Request body for ``POST /api/launch/linkedin``.

    Slice 3 is concurrent-only and fresh-only, so the request model exposes
    exactly one field. ``model_config = ConfigDict(extra="forbid")`` makes
    Pydantic reject any extra field (e.g. ``input_mode``, ``mode``), which
    is how ``away`` is rejected at the request boundary.
    """

    model_config = ConfigDict(extra="forbid")
    brief_path: str


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


@router.get("/api/status")
def api_status() -> StatusResponse:
    """Aggregate read-only status across LinkedIn and GitHub state dirs."""

    return aggregate_status()


def launch_linkedin_worker(req: LaunchLinkedInRequest) -> LaunchResponse:
    """Spawn a detached LinkedIn worker for the given brief.

    Steps:

    1. Validate that ``brief_path`` exists on disk; raise
       :class:`BriefPathNotFoundError` if not (route maps to HTTP 400).
    2. Resolve the LinkedIn state directory and brief id via
       :mod:`shared.output_paths` so the sidecar carries a truthful
       ``brief_id`` even before the orchestrator inserts a ``runs`` row.
    3. Probe any existing ``worker.json``: a present sidecar with an
       ``int`` ``pid`` field that is currently alive raises
       :class:`WorkerAlreadyRunningError` (route maps to HTTP 409). A
       missing sidecar, malformed sidecar, non-int ``pid``, or dead
       ``pid`` is treated as stale and silently overwritten by the new
       worker (user-approved Option B).
    4. Spawn ``python -m cloris.worker ...`` with
       ``start_new_session=True`` so the worker survives the API process
       exiting and is its own process-group leader. Stdio is fully
       detached.
    5. Return a :class:`LaunchResponse` with ``pid`` from
       ``Popen.pid`` — the same PID will belong to the LinkedIn
       orchestrator after the worker ``execvp``s.
    """

    brief_path = Path(req.brief_path)
    if not brief_path.exists():
        raise BriefPathNotFoundError(req.brief_path)

    from shared.output_paths import linkedin_state_key, resolve_linkedin_state_dir

    state_dir = resolve_linkedin_state_dir(brief_path=str(brief_path))
    brief_id = linkedin_state_key(brief_path=str(brief_path))

    existing = read_sidecar(state_dir)
    if existing is not None:
        existing_pid = existing.get("pid")
        if isinstance(existing_pid, int) and is_pid_alive(existing_pid):
            raise WorkerAlreadyRunningError(
                pid=existing_pid,
                state_dir=str(state_dir),
            )

    argv = [
        sys.executable,
        "-m",
        "cloris.worker",
        "--brief",
        str(brief_path),
        "--brief-id",
        brief_id,
        "--state-dir",
        str(state_dir),
    ]
    process = subprocess.Popen(
        argv,
        start_new_session=True,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        close_fds=True,
    )

    return LaunchResponse(
        source="linkedin",
        input_mode="concurrent",
        pid=process.pid,
        state_dir=str(state_dir),
        worker_json_path=str(state_dir / "worker.json"),
    )


@router.post("/api/launch/linkedin", status_code=201, response_model=LaunchResponse)
def launch_linkedin(req: LaunchLinkedInRequest) -> LaunchResponse:
    """Spawn a detached LinkedIn worker; map typed errors to HTTP codes.

    - :class:`BriefPathNotFoundError` → HTTP 400 with
      ``{"error": "brief_path_not_found", "brief_path": "..."}``.
    - :class:`WorkerAlreadyRunningError` → HTTP 409 with
      ``{"error": "worker_already_running", "pid": ..., "state_dir": "..."}``.
    """

    try:
        return launch_linkedin_worker(req)
    except BriefPathNotFoundError as exc:
        raise HTTPException(
            status_code=400,
            detail={"error": "brief_path_not_found", "brief_path": str(exc)},
        ) from exc
    except WorkerAlreadyRunningError as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "worker_already_running",
                "pid": exc.pid,
                "state_dir": exc.state_dir,
            },
        ) from exc
