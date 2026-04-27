"""Cloris HTTP response models.

Pydantic v2 models for the Cloris HTTP surface. Slice 2 introduced read-only
status aggregation (``GET /api/status``); Slice 3 added the launch payload
contract (``POST /api/launch/linkedin``). Slice 4 enriches ``StateDirEntry``
with worker-sidecar provenance plus a ``resumable`` hint, and adds
:class:`StopResponse` and :class:`ResumeResponse` for ``POST /api/stop/...``
and ``POST /api/resume/linkedin``. Slice 4 also introduces
``StopResponseState`` alongside ``WorkerState`` so the stop response can
describe the result of a stop action (``stopping`` / ``missing`` / ``stale``)
without conflating that with the steady-state aggregator enum
(``WorkerState``).

Models stay deliberately small and explicit: no validators, no derived
fields, no semantic shaping beyond the ``WorkerState`` and
``StopResponseState`` literals. Anything that requires further
interpretation (normalized stop reasons, queue semantics, pause state) is
out of scope.

Slice tag conventions:

- :class:`StatusResponse.slice` is bumped to ``"v0-shell-slice-4"`` because
  Slice 4 enriches the payload shape.
- :class:`LaunchResponse.slice` stays ``"v0-shell-slice-3"`` — the launch
  contract did not change.
- :class:`StopResponse.slice` and :class:`ResumeResponse.slice` are
  ``"v0-shell-slice-4"`` (new payloads, new slice).
- ``GET /healthz`` continues to advertise ``"v0-shell-slice-1"`` because it
  is a stable readiness probe, not a slice-version banner.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


WorkerState = Literal["missing", "alive", "stale"]
StopResponseState = Literal["stopping", "missing", "stale"]


class RunSummary(BaseModel):
    """Verbatim subset of a ``runs`` row exposed by the status aggregator.

    All fields are optional because a state directory may be missing its
    ``runtime_state.sqlite3`` entirely, may have an empty ``runs`` table, or
    may have been written by an older schema variant. The aggregator never
    invents values; it only forwards what canonical SQLite returns.
    """

    id: int | None = None
    status: str | None = None
    stop_reason: str | None = None
    mode: str | None = None
    started_at: str | None = None
    ended_at: str | None = None


class StateDirEntry(BaseModel):
    """One entry per discovered ``output/state/<source>/<state_key>`` dir.

    The aggregator yields an entry for every state directory it discovers,
    including those without a ``runtime_state.sqlite3``. ``state_key`` is the
    on-disk directory name; ``brief_id_from_run`` is the ``runs.brief_id``
    column read from canonical SQLite (which can disagree with ``state_key``,
    especially for LinkedIn).

    Slice 4 adds worker-sidecar provenance fields. They all default in a way
    that preserves backward shape for callers that built ``StateDirEntry``
    manually before Slice 4: ``worker_state`` defaults to ``"missing"`` and
    every other worker_* field defaults to ``None`` / ``False``. The
    ``resumable`` field is ``None`` for GitHub entries (no analogous
    progress.json gate) and ``True``/``False``/``None`` for LinkedIn per
    :func:`cloris.control_plane.linkedin_resumable` semantics.
    """

    source: Literal["linkedin", "github"]
    state_key: str
    state_dir: str
    runtime_state_present: bool
    latest_run: RunSummary | None = None
    brief_id_from_run: str | None = None
    brief_path_from_worker: str | None = None
    worker_json_present: bool = False
    worker_pid: int | None = None
    worker_alive: bool | None = None
    worker_mode: str | None = None
    worker_input_mode: str | None = None
    resumable: bool | None = None
    worker_state: WorkerState = "missing"


class StatusResponse(BaseModel):
    """Top-level payload for ``GET /api/status``.

    ``slice`` is pinned to ``"v0-shell-slice-4"`` so callers can detect the
    contract version without re-typing the literal at every construction
    site. The bump from ``"v0-shell-slice-2"`` to ``"v0-shell-slice-4"``
    reflects the enriched :class:`StateDirEntry` shape Slice 4 ships.
    """

    slice: Literal["v0-shell-slice-4"] = Field(default="v0-shell-slice-4")
    entries: list[StateDirEntry]


class LaunchResponse(BaseModel):
    """Response payload for ``POST /api/launch/linkedin`` (Slice 3).

    ``slice`` is pinned to ``"v0-shell-slice-3"`` and intentionally does
    **not** bump in Slice 4 — the launch contract did not change. ``source``
    and ``input_mode`` are intentionally ``Literal``-typed because Slice 3
    is LinkedIn-only and concurrent-only; GitHub launches and ``away`` mode
    are out of scope.

    ``pid`` is the spawned worker process's PID at the moment ``Popen``
    returns; after the worker ``execvp``s into
    ``linkedin.session_orchestrator``, the same PID belongs to the
    orchestrator, so this value remains the truthful process handle for
    later stop/probe operations.
    """

    slice: Literal["v0-shell-slice-3"] = Field(default="v0-shell-slice-3")
    source: Literal["linkedin"]
    input_mode: Literal["concurrent"]
    pid: int
    state_dir: str
    worker_json_path: str


class StopResponse(BaseModel):
    """Response payload for ``POST /api/stop/{source}/{state_key}``.

    The HTTP status code conveys the action: 202 when SIGTERM was
    dispatched against an alive PID, 200 when there was nothing to signal
    (``worker_state`` ∈ ``{"missing", "stale"}``). The body conveys the
    truth — clients should branch on ``worker_state``, not on the status
    code, because the body is the durable contract.

    ``worker_state`` here is ``StopResponseState`` (``stopping`` /
    ``missing`` / ``stale``), intentionally distinct from
    :class:`StatusResponse`'s ``WorkerState`` because the stop response
    describes the **result of the stop action**, not a steady-state
    observation.
    """

    slice: Literal["v0-shell-slice-4"] = Field(default="v0-shell-slice-4")
    source: Literal["linkedin", "github"]
    state_key: str
    state_dir: str
    worker_state: StopResponseState
    pid: int | None = None


class ResumeResponse(BaseModel):
    """Response payload for ``POST /api/resume/linkedin`` (Slice 4).

    Mirrors :class:`LaunchResponse` except that ``slice`` advertises Slice 4
    and ``mode`` is fixed to ``"resume"``. Same ``pid`` / ``state_dir`` /
    ``worker_json_path`` semantics: ``pid`` is the spawned worker's PID at
    the moment ``Popen`` returns, which is also the orchestrator's PID
    after ``execvp``.
    """

    slice: Literal["v0-shell-slice-4"] = Field(default="v0-shell-slice-4")
    source: Literal["linkedin"]
    mode: Literal["resume"] = Field(default="resume")
    input_mode: Literal["concurrent"]
    pid: int
    state_dir: str
    worker_json_path: str
