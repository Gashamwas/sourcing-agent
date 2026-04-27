"""Cloris HTTP response models (Slice 2).

Pydantic v2 models for the read-only status aggregation surface. Kept
deliberately small and explicit: no validators, no derived fields, no semantic
shaping. Anything that requires interpretation (worker liveness, resumability,
normalized stop reasons) is out of scope until later slices.

These models are the contract for ``GET /api/status`` and nothing else; the
slice 1 endpoints (``GET /`` and ``GET /healthz``) keep their existing shapes.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


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
    """

    source: Literal["linkedin", "github"]
    state_key: str
    state_dir: str
    runtime_state_present: bool
    latest_run: RunSummary | None = None
    brief_id_from_run: str | None = None


class StatusResponse(BaseModel):
    """Top-level payload for ``GET /api/status``.

    ``slice`` is pinned to ``"v0-shell-slice-2"`` so callers can detect the
    contract version without re-typing the literal at every construction site.
    ``GET /healthz`` continues to advertise ``"v0-shell-slice-1"`` because it
    is a stable readiness probe, not a slice-version banner.
    """

    slice: Literal["v0-shell-slice-2"] = Field(default="v0-shell-slice-2")
    entries: list[StateDirEntry]


class LaunchResponse(BaseModel):
    """Response payload for ``POST /api/launch/linkedin`` (Slice 3).

    ``slice`` is pinned to ``"v0-shell-slice-3"`` so callers can detect the
    launch-contract version without re-typing the literal at every
    construction site. ``source`` and ``input_mode`` are intentionally
    ``Literal``-typed because Slice 3 is LinkedIn-only and concurrent-only;
    GitHub launches and ``away`` mode are out of scope.

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
