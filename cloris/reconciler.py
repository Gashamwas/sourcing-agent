"""Zombie-run reconciler.

Background
----------
A run row in canonical state goes ``status='running'`` at start_run and
stays that way until the orchestrator calls finish_run. If the worker
process dies hard — Mac sleep evicting the subprocess, kernel OOM,
``kill -9``, host reboot, anything — finish_run never fires and the row
is stranded. The Cloris UI faithfully renders ``status='running'`` and
shows a "Working" status pill on a brief that has been dead for days.

That contradiction is the deepest UX-as-data-model rot in the product:
the surface tells the truth about the row, but the row hasn't been
reconciled with worker-process reality.

Contract
--------
This module is the reconciler. It is **pure** in the read sense: it
walks state directories, opens canonical SQLite **read-only** via
:mod:`shared.runtime_state.read_models`, and inspects ``worker.json``
sidecars for liveness. It produces a list of :class:`Mutation`
records — what needs to change — without writing anything itself.

The caller (cloris/api.py) is responsible for executing the mutations
through the canonical write path
(:class:`shared.runtime_state.store.RuntimeStateStore.finish_run`).
This separation means:

  - Reconciliation can be unit-tested end-to-end without a live FastAPI.
  - The read-only contract on ``cloris/control_plane.py`` (no
    ``RuntimeStateStore`` import; enforced by tests) stays intact —
    this module is the only place that depends on the writer, and it
    isolates that dependency in the executor function.

Decision logic
--------------
For each state_dir with a canonical SQLite present:

  1. Read latest_run. If ``status != 'running'``, no mutation.
  2. Read worker sidecar (``worker.json``).
  3. Conservative trigger — only mutate when we're certain the worker
     is gone:
       - sidecar missing entirely → ``MISSING_SIDECAR``
       - sidecar present but ``pid`` non-int / non-positive → ``BAD_SIDECAR``
       - sidecar pid dead per :func:`cloris.worker.is_pid_alive` → ``PID_DEAD``
     "alive_silent" (PID alive but heartbeat stale) is **NOT** reconciled
     — a worker can be alive and silent during a long captcha wait or a
     suspended laptop. Killing those would create a worse failure mode.

Idempotency
-----------
A re-run of :func:`reconcile_orphans` after a previous reconciliation
returns an empty mutation list, because the runs that were marked
``status='abandoned'`` no longer match the ``status='running'`` filter.
Tests should pin this property explicitly.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, Literal

from cloris.control_plane import (
    enumerate_state_dirs,
    read_worker_sidecar,
    is_runtime_state_corrupt,
)
from cloris.worker import is_pid_alive
from shared.runtime_state import read_models
from shared.safety.stop_reasons import RunStopReason


_RUNTIME_DB_FILENAME = "runtime_state.sqlite3"


# Status to assign when a zombie is reconciled. We use ``abandoned`` rather
# than ``interrupted`` because:
#   - ``interrupted`` already means "operator-initiated stop or
#     cooperative pause" in the existing taxonomy
#     (``StopReason.OPERATOR_STOP`` / ``OPERATOR_PAUSE``).
#   - ``abandoned`` is unambiguous: nobody chose to stop this; the
#     worker process simply went away.
ABANDONED_STATUS = "abandoned"


ReconcileReason = Literal[
    "missing_sidecar",  # worker.json doesn't exist
    "bad_sidecar",      # worker.json exists but pid is missing / non-int / non-positive
    "pid_dead",         # worker.json's pid is a real int but the process is gone
]


@dataclass(frozen=True)
class Mutation:
    """One canonical-state mutation the caller should execute.

    The reconciler emits these; cloris/api.py applies them through
    :class:`shared.runtime_state.store.RuntimeStateStore`. Splitting
    "decide" from "apply" keeps the reconciler unit-testable without
    a writer dependency.
    """

    source: str
    state_key: str
    state_dir: Path
    run_id: int
    new_status: str
    stop_reason: str
    reason: ReconcileReason
    detected_at: str  # ISO-8601 UTC


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _classify_worker(state_dir: Path) -> ReconcileReason | None:
    """Return a reconcile reason if the worker is gone, else None.

    Mirrors the worker_state derivation in
    :func:`cloris.control_plane.aggregate_status` but conservatively —
    only the genuinely-dead branches map to a reason. ``alive`` and
    ``alive_silent`` both return ``None`` (do not reconcile).
    """
    sidecar = read_worker_sidecar(state_dir)
    if sidecar is None:
        return "missing_sidecar"
    pid_raw = sidecar.get("pid")
    if not isinstance(pid_raw, int) or isinstance(pid_raw, bool) or pid_raw <= 0:
        return "bad_sidecar"
    if not is_pid_alive(pid_raw):
        return "pid_dead"
    return None  # alive — leave alone (covers alive_silent too)


def reconcile_orphans(state_root: Path | None = None) -> list[Mutation]:
    """Walk every state dir; emit mutations for runs whose workers are gone.

    Pure function in the read sense — opens canonical SQLite read-only,
    reads sidecars, returns mutations. The caller executes them.

    Args:
        state_root: optional override for the state root directory. Defaults
            to ``shared.output_paths.STATE_ROOT`` via :func:`enumerate_state_dirs`.

    Returns:
        list of :class:`Mutation` records, possibly empty. Sorted by
        ``(source, state_key, run_id)`` for deterministic ordering.
    """
    mutations: list[Mutation] = []
    now = _utc_now_iso()
    for source, state_dir in enumerate_state_dirs(state_root):
        db_path = state_dir / _RUNTIME_DB_FILENAME
        if not db_path.exists() or is_runtime_state_corrupt(db_path):
            continue
        latest = read_models.latest_run_summary(db_path)
        if latest is None or latest.status != "running":
            continue
        reason = _classify_worker(state_dir)
        if reason is None:
            continue
        mutations.append(
            Mutation(
                source=source,
                state_key=state_dir.name,
                state_dir=state_dir,
                run_id=latest.id,
                new_status=ABANDONED_STATUS,
                stop_reason=RunStopReason.WORKER_MISSING,
                reason=reason,
                detected_at=now,
            )
        )
    mutations.sort(key=lambda m: (m.source, m.state_key, m.run_id))
    return mutations


def apply_mutations(mutations: list[Mutation]) -> int:
    """Execute reconciler mutations against canonical state.

    Opens a fresh :class:`RuntimeStateStore` per state_dir, calls
    ``finish_run`` with the abandoned status. Returns the number of
    mutations actually applied (may be less than the input length if a
    run was already finalized between read and write — a benign race
    we tolerate by re-reading the row and skipping when status has
    moved off 'running').

    Importing ``RuntimeStateStore`` here (and not in
    ``cloris.control_plane``) preserves the read-only contract pinned
    by tests/test_cloris_status_aggregation.py.
    """
    # Lazy import keeps the writer dependency out of read-only call sites
    # that import ``cloris.reconciler`` for type references only.
    from shared.runtime_state.store import RuntimeStateStore

    applied = 0
    for m in mutations:
        db_path = m.state_dir / _RUNTIME_DB_FILENAME
        # Re-check status before write to avoid finalizing a run that
        # legitimately transitioned to terminal between read and apply.
        latest = read_models.latest_run_summary(db_path)
        if latest is None or latest.id != m.run_id or latest.status != "running":
            continue
        store = RuntimeStateStore(db_path)
        store.finish_run(m.run_id, m.new_status, stop_reason=m.stop_reason)
        applied += 1
    return applied


def reconcile_and_apply(state_root: Path | None = None) -> tuple[int, list[Mutation]]:
    """Convenience: do the full reconcile-then-apply pass.

    Returns (applied_count, mutations) so callers can log / surface the
    forensic detail of what was reconciled. The mutations list is the
    reconciler's pre-apply view — it may include rows that the
    re-check rejected, in which case applied < len(mutations).
    """
    mutations = reconcile_orphans(state_root)
    applied = apply_mutations(mutations)
    return applied, mutations
