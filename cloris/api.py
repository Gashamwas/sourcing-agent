"""Cloris HTTP surface.

Slice 1 endpoints (kept byte-identical here):

- ``GET /healthz`` — readiness probe used by :func:`cloris.app.run_app` and by
  external smoke checks. Stable JSON contract: ``status``, ``slice``,
  ``version``. The slice tag stays ``"v0-shell-slice-1"`` because this is a
  readiness probe, not a slice-version banner.
- ``GET /`` — returns the inline placeholder ``index.html`` directly. Slice 1
  intentionally does **not** mount a ``StaticFiles`` tree.

Slice 2 endpoint (route body byte-identical, payload bumped to slice-4 by the
aggregator):

- ``GET /api/status`` — read-only aggregation across discovered
  ``output/state/<source>/*`` directories. Slice 4 enriches the payload with
  worker-sidecar provenance and a ``resumable`` hint, and bumps the slice
  tag in :class:`cloris.models.StatusResponse` to ``"v0-shell-slice-4"``.

Slice 3 endpoint (route body byte-identical):

- ``POST /api/launch/linkedin`` — spawn a detached
  ``python -m cloris.worker ...`` subprocess that writes ``worker.json``
  and ``execvp``s into ``linkedin.session_orchestrator``. LinkedIn-only,
  concurrent-only, fresh-only. The :class:`cloris.models.LaunchResponse`
  slice tag stays ``"v0-shell-slice-3"`` — the launch contract did not
  change in Slice 4.

Slice 4 endpoints:

- ``POST /api/stop/{source}/{state_key}`` — resolve the state dir via
  :func:`cloris.control_plane.enumerate_state_dirs` (path-traversal-safe
  lookup; raw URL segments cannot escape the discovered set), read
  ``worker.json``, and:

  - Missing sidecar ⇒ HTTP 200, ``worker_state="missing"``.
  - Stale sidecar (PID malformed / non-int / dead) ⇒ HTTP 200,
    ``worker_state="stale"``. The stale sidecar is **not** deleted; the
    next launch overwrites it via the existing Slice-3 stale-overwrite
    policy.
  - Alive PID ⇒ HTTP 202, ``worker_state="stopping"``. Send
    ``signal.SIGTERM`` exactly once and return immediately. **No** wait
    for exit. **No** SIGKILL escalation.
  - Unknown ``(source, state_key)`` ⇒ HTTP 404 with
    ``error="state_dir_not_found"``.

- ``POST /api/resume/linkedin`` — same request body as launch
  (:class:`LaunchLinkedInRequest`, ``brief_path``-only with
  ``extra="forbid"``). Spawns a detached worker with ``--mode resume``,
  which threads ``--resume`` into the orchestrator argv. Returns
  :class:`cloris.models.ResumeResponse` (HTTP 201) with ``slice``
  ``"v0-shell-slice-4"`` and ``mode="resume"``. The launch's stale-sidecar
  overwrite policy and ``WorkerAlreadyRunningError`` / ``BriefPathNotFoundError``
  shapes are reused identically.

Pause is still out of scope per ``docs/cloris-control-plane-spec.md`` §7.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict

from cloris import __version__
from cloris.control_plane import aggregate_status, enumerate_state_dirs
from cloris.models import (
    LaunchResponse,
    ResumeResponse,
    StatusResponse,
    StopResponse,
)
from cloris.worker import (
    BriefPathNotFoundError,
    WorkerAlreadyRunningError,
    is_pid_alive,
    read_sidecar,
)


router = APIRouter()

_FRONTEND_DIR = Path(__file__).parent / "frontend"
_INDEX_HTML = _FRONTEND_DIR / "index.html"


def _send_sigterm(pid: int) -> None:
    """Module-level seam for the single SIGTERM dispatch in :func:`stop_worker`.

    Tests monkeypatch this symbol to a recorder so the SIGTERM dispatch
    can be observed without disturbing the unrelated ``os.kill(pid, 0)``
    liveness probe inside :func:`cloris.worker.is_pid_alive`. Production
    behavior is a single ``os.kill(pid, signal.SIGTERM)`` and nothing
    else.
    """

    os.kill(pid, signal.SIGTERM)


class StateDirNotFoundError(Exception):
    """Raised when ``stop_worker`` cannot resolve the requested state dir.

    The route maps this to HTTP 404 with
    ``{"error": "state_dir_not_found", "source": ..., "state_key": ...}``.
    Lives in :mod:`cloris.api` rather than :mod:`cloris.worker` because it
    is purely a routing-layer error: the worker module has no notion of
    URL-borne ``(source, state_key)`` lookups.
    """

    def __init__(self, source: str, state_key: str) -> None:
        super().__init__(
            f"state dir not found (source={source}, state_key={state_key})"
        )
        self.source = source
        self.state_key = state_key


class LaunchLinkedInRequest(BaseModel):
    """Request body for ``POST /api/launch/linkedin`` and
    ``POST /api/resume/linkedin``.

    Slice 4 reuses this exact model for resume because the user-approved
    contract is "same request body shape as launch" — a single
    ``brief_path`` string. ``extra="forbid"`` rejects any unknown field
    (e.g. ``input_mode``, ``mode``) at the request boundary, which is how
    ``away`` and stray fields are rejected without ever reaching the
    helper.
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


def resume_linkedin_worker(req: LaunchLinkedInRequest) -> ResumeResponse:
    """Spawn a detached LinkedIn worker in resume mode.

    Identical to :func:`launch_linkedin_worker` except:

    - The spawned worker argv carries ``--mode resume``, which threads
      ``--resume`` into the orchestrator argv inside ``cloris.worker``.
    - Returns a :class:`cloris.models.ResumeResponse` (slice tag
      ``"v0-shell-slice-4"``, ``mode="resume"``) instead of
      :class:`cloris.models.LaunchResponse`.

    The brief-validation, state-dir resolution, and stale-sidecar
    overwrite policies are byte-identical to launch — including the
    ``WorkerAlreadyRunningError`` / ``BriefPathNotFoundError`` raise
    semantics — because resume is just "spawn the same worker pointed at
    the same state dir, with one extra CLI flag".
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
        "--mode",
        "resume",
    ]
    process = subprocess.Popen(
        argv,
        start_new_session=True,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        close_fds=True,
    )

    return ResumeResponse(
        source="linkedin",
        input_mode="concurrent",
        pid=process.pid,
        state_dir=str(state_dir),
        worker_json_path=str(state_dir / "worker.json"),
    )


def _resolve_state_dir(source: str, state_key: str) -> Optional[Path]:
    """Return the discovered state dir matching ``(source, state_key)``.

    Iterates :func:`cloris.control_plane.enumerate_state_dirs` rather than
    naively joining ``STATE_ROOT / source / state_key``. This is the
    path-traversal-safe lookup: any ``state_key`` that doesn't appear in
    the discovered set returns ``None``, which the route translates to
    HTTP 404.
    """

    for discovered_source, discovered_state_dir in enumerate_state_dirs():
        if discovered_source == source and discovered_state_dir.name == state_key:
            return discovered_state_dir
    return None


def stop_worker(source: str, state_key: str) -> StopResponse:
    """Resolve the state dir, classify the worker, optionally SIGTERM.

    Pure helper — no FastAPI imports beyond the type contract. Returns a
    :class:`cloris.models.StopResponse`; the route is responsible for
    setting the HTTP status code (202 when ``worker_state == "stopping"``,
    200 otherwise).

    Steps:

    1. Resolve ``state_dir`` via :func:`_resolve_state_dir`. If not
       found, raise :class:`StateDirNotFoundError`.
    2. Read ``worker.json`` via :func:`cloris.worker.read_sidecar`.
    3. Missing sidecar ⇒ ``worker_state="missing"``, ``pid=None``. **No
       signal sent.**
    4. Sidecar present, but ``pid`` is not a valid int OR
       :func:`cloris.worker.is_pid_alive` returns ``False`` ⇒
       ``worker_state="stale"``. **No signal sent. Sidecar not deleted.**
    5. Alive PID ⇒ ``os.kill(pid, signal.SIGTERM)`` exactly once and
       return ``worker_state="stopping"``. ``ProcessLookupError`` (race:
       process died between probe and signal) ⇒ treat as stale.
       ``PermissionError`` (we cannot signal it but it exists) ⇒ also
       treat as stale; the user-facing contract is "stop is best-effort
       against the worker we own".

    Slice 4 deliberately does **not** wait for SIGTERM to take effect
    and does **not** escalate to SIGKILL. Both are explicit non-goals
    per the operative plan.
    """

    state_dir = _resolve_state_dir(source, state_key)
    if state_dir is None:
        raise StateDirNotFoundError(source, state_key)

    sidecar = read_sidecar(state_dir)
    if sidecar is None:
        return StopResponse(
            source=source,  # type: ignore[arg-type]
            state_key=state_key,
            state_dir=str(state_dir),
            worker_state="missing",
            pid=None,
        )

    pid_raw = sidecar.get("pid")
    if not isinstance(pid_raw, int) or isinstance(pid_raw, bool):
        return StopResponse(
            source=source,  # type: ignore[arg-type]
            state_key=state_key,
            state_dir=str(state_dir),
            worker_state="stale",
            pid=None,
        )

    if not is_pid_alive(pid_raw):
        return StopResponse(
            source=source,  # type: ignore[arg-type]
            state_key=state_key,
            state_dir=str(state_dir),
            worker_state="stale",
            pid=pid_raw,
        )

    try:
        _send_sigterm(pid_raw)
    except ProcessLookupError:
        return StopResponse(
            source=source,  # type: ignore[arg-type]
            state_key=state_key,
            state_dir=str(state_dir),
            worker_state="stale",
            pid=pid_raw,
        )
    except PermissionError:
        return StopResponse(
            source=source,  # type: ignore[arg-type]
            state_key=state_key,
            state_dir=str(state_dir),
            worker_state="stale",
            pid=pid_raw,
        )

    return StopResponse(
        source=source,  # type: ignore[arg-type]
        state_key=state_key,
        state_dir=str(state_dir),
        worker_state="stopping",
        pid=pid_raw,
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


@router.post(
    "/api/resume/linkedin", status_code=201, response_model=ResumeResponse
)
def resume_linkedin(req: LaunchLinkedInRequest) -> ResumeResponse:
    """Spawn a detached LinkedIn worker in resume mode.

    Same error mapping as launch:

    - :class:`BriefPathNotFoundError` → HTTP 400.
    - :class:`WorkerAlreadyRunningError` → HTTP 409.
    """

    try:
        return resume_linkedin_worker(req)
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


@router.post("/api/stop/{source}/{state_key}", response_model=StopResponse)
def stop(source: str, state_key: str, response: Response) -> StopResponse:
    """Send SIGTERM to the worker for ``(source, state_key)`` if alive.

    Status code is dynamic:

    - 202 when the helper signaled an alive PID.
    - 200 when there was nothing to signal (``missing`` or ``stale``).
    - 404 when the state dir isn't in the discovered set.

    The body always carries the truthful ``worker_state``; clients should
    branch on the body, not on the status code.
    """

    try:
        result = stop_worker(source, state_key)
    except StateDirNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "state_dir_not_found",
                "source": exc.source,
                "state_key": exc.state_key,
            },
        ) from exc

    if result.worker_state == "stopping":
        response.status_code = 202
    return result
