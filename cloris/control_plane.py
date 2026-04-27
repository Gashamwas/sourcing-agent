"""Cloris status aggregator.

Pure read-only aggregation over per-state-dir canonical SQLite stores plus
the per-state-dir ``worker.json`` sidecar plus a small ``progress.json``
peek for LinkedIn resumability. This is the single seam between Cloris and
the canonical runtime-state files; it has no FastAPI imports, no pywebview
imports, and **no** import of the canonical runtime-state store class in
production paths.

Why not the canonical store class? Its constructor runs unconditional DDL
plus ``INSERT OR REPLACE INTO meta`` on every instantiation
(``shared/runtime_state/store.py:56-213``), which would make the API
process silently writable against active runtime state. We open the file
directly via ``sqlite3.connect(f"file:{path}?mode=ro", uri=True)`` so the
read path is honestly read-only.

Public surfaces:

- :func:`enumerate_state_dirs` — list discovered state dirs across LinkedIn
  and GitHub.
- :func:`read_latest_run_readonly` — open one canonical SQLite read-only and
  return the latest ``runs`` row as a dict, or ``None``.
- :func:`read_worker_sidecar` — thin wrapper over :func:`cloris.worker.read_sidecar`.
- :func:`linkedin_resumable` — Slice 4 read-only resumability oracle that
  mirrors the semantics of ``linkedin.session_orchestrator._resume_has_pending_work``
  by reading ``progress.json`` directly. Returns ``True``/``False``/``None``;
  ``None`` means "unknown" (file missing or unreadable). Reimplemented here
  rather than imported so this module stays decoupled from
  ``linkedin/session_orchestrator.py`` and never triggers a ``mkdir``.
- :func:`aggregate_status` — orchestrate the above and return a
  :class:`cloris.models.StatusResponse`. Slice 4 enriches each
  :class:`cloris.models.StateDirEntry` with worker-sidecar provenance fields
  and a ``resumable`` hint (LinkedIn only).
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Iterator

from cloris.models import RunSummary, StateDirEntry, StatusResponse
from cloris.worker import is_pid_alive


_SOURCES: tuple[str, ...] = ("linkedin", "github")
_RUNTIME_DB_FILENAME = "runtime_state.sqlite3"
_PROGRESS_JSON_FILENAME = "progress.json"
_LATEST_RUN_QUERY = (
    "SELECT id, source, brief_id, mode, status, stop_reason, started_at, ended_at "
    "FROM runs ORDER BY id DESC LIMIT 1"
)


def enumerate_state_dirs(
    state_root: Path | None = None,
) -> Iterator[tuple[str, Path]]:
    """Yield ``(source, state_dir)`` pairs across LinkedIn and GitHub.

    ``state_root`` defaults to ``shared.output_paths.STATE_ROOT``; the lazy
    import keeps this module from pulling ``shared.config`` at import time
    (tests pass an explicit ``tmp_path`` and never touch the real
    ``output/state/`` tree).

    Per-source roots that don't exist (or aren't directories) are skipped
    silently; an empty source root yields no entries. Within each source root
    we iterate ``iterdir()`` filtered to directories, sorted by name, so test
    output is deterministic.
    """

    if state_root is None:
        from shared.output_paths import STATE_ROOT

        state_root = STATE_ROOT

    for source in _SOURCES:
        source_root = state_root / source
        if not source_root.exists() or not source_root.is_dir():
            continue
        for child in sorted(source_root.iterdir()):
            if child.is_dir():
                yield source, child


def read_latest_run_readonly(db_path: Path) -> dict | None:
    """Return the latest ``runs`` row from ``db_path`` as a dict, or ``None``.

    Opens the file in URI read-only mode so the API process cannot mutate
    canonical state, even by accident. A missing file, an empty ``runs``
    table, or a corrupt/in-flight DB all collapse to ``None`` rather than
    raising — one bad state dir must not take down the whole status payload.

    The ``runs`` schema this query depends on is fixed by
    ``shared/runtime_state/store.py:82-95``; column drift would be caught by
    the aggregation tests.
    """

    if not db_path.exists():
        return None

    conn: sqlite3.Connection | None = None
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        row = conn.execute(_LATEST_RUN_QUERY).fetchone()
        if row is None:
            return None
        return dict(row)
    except sqlite3.OperationalError:
        return None
    except sqlite3.DatabaseError:
        return None
    finally:
        if conn is not None:
            conn.close()


def read_worker_sidecar(state_dir: Path) -> dict | None:
    """Return the parsed ``worker.json`` for ``state_dir``, or ``None``.

    Thin wrapper around :func:`cloris.worker.read_sidecar` so the control
    plane stays the single seam between Cloris and per-state-dir disk
    artifacts (canonical SQLite + the ``worker.json`` sidecar). Slice 4
    uses this to enrich ``GET /api/status`` with worker provenance and to
    classify ``worker_state`` per :class:`cloris.models.WorkerState`.
    """

    from cloris.worker import read_sidecar

    return read_sidecar(state_dir)


def linkedin_resumable(state_dir: Path) -> bool | None:
    """Return whether the LinkedIn run in ``state_dir`` has pending work.

    Reads ``state_dir / "progress.json"`` directly, with no dependency on
    ``linkedin.session_orchestrator``, no ``resolve_linkedin_state_dir``,
    and no ``mkdir``. This keeps ``GET /api/status`` honestly read-only.

    Semantics mirror ``linkedin.session_orchestrator._resume_has_pending_work``
    (read-only excerpt, not imported):

    - Missing ``progress.json`` ⇒ ``None`` (unknown — caller decides).
    - Unreadable / malformed JSON ⇒ ``None``.
    - JSON top level is not an object ⇒ ``None``.
    - Truthy ``pending_block_string_ids`` ⇒ ``True``.
    - ``strings`` not a list ⇒ ``None``.
    - Empty ``strings`` and no pending blocks ⇒ ``False``.
    - Otherwise ⇒ ``True`` iff any string entry has
      ``status in {"queued", "in_progress"}``.

    The ``None`` for missing/malformed is the deliberate divergence from
    the orchestrator's ``True`` fallback: at the status surface, "unknown"
    is the truthful answer; the orchestrator's bias toward attempting
    resume on missing data is appropriate for an active worker but wrong
    for a passive read model.
    """

    progress_path = state_dir / _PROGRESS_JSON_FILENAME
    if not progress_path.exists():
        return None
    try:
        progress = json.loads(progress_path.read_text())
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return None
    if not isinstance(progress, dict):
        return None
    if progress.get("pending_block_string_ids"):
        return True
    strings = progress.get("strings", [])
    if not isinstance(strings, list):
        return None
    if not strings:
        return False
    return any(
        isinstance(s, dict) and s.get("status") in {"queued", "in_progress"}
        for s in strings
    )


def aggregate_status(state_root: Path | None = None) -> StatusResponse:
    """Build a :class:`StatusResponse` for ``GET /api/status``.

    Pure function of disk: walks every discovered state dir, reads the
    latest ``runs`` row read-only when a DB is present, reads the optional
    ``worker.json`` sidecar to classify ``worker_state``, and (LinkedIn
    only) reads ``progress.json`` to compute ``resumable``. Returns a
    stable response sorted by ``(source, state_key)`` so tests and clients
    see deterministic ordering.

    Slice 4 enrichment per :class:`cloris.models.StateDirEntry`:

    - ``worker_json_present`` — whether ``worker.json`` exists and parses.
    - ``worker_pid`` — int when sidecar's ``pid`` is an int, else ``None``.
    - ``worker_alive`` — :func:`cloris.worker.is_pid_alive` result when
      ``worker_pid`` is set; ``None`` otherwise.
    - ``worker_mode`` / ``worker_input_mode`` / ``brief_path_from_worker`` —
      forwarded verbatim from the sidecar.
    - ``worker_state`` ∈ ``{"missing", "alive", "stale"}`` — derived:
      ``"missing"`` when no parseable sidecar; ``"alive"`` when sidecar
      has an int PID currently alive; ``"stale"`` when sidecar exists but
      its PID is missing/non-int or dead.
    - ``resumable`` — :func:`linkedin_resumable` for LinkedIn, ``None``
      for GitHub (no analogous progress.json gate).
    """

    entries: list[StateDirEntry] = []
    for source, state_dir in enumerate_state_dirs(state_root):
        db_path = state_dir / _RUNTIME_DB_FILENAME
        runtime_state_present = db_path.exists()

        latest_run: RunSummary | None = None
        brief_id_from_run: str | None = None
        if runtime_state_present:
            row = read_latest_run_readonly(db_path)
            if row is not None:
                latest_run = RunSummary(
                    id=row.get("id"),
                    status=row.get("status"),
                    stop_reason=row.get("stop_reason"),
                    mode=row.get("mode"),
                    started_at=row.get("started_at"),
                    ended_at=row.get("ended_at"),
                )
                brief_id_from_run = row.get("brief_id")

        sidecar = read_worker_sidecar(state_dir)
        worker_json_present = sidecar is not None
        worker_pid: int | None = None
        worker_alive: bool | None = None
        worker_mode: str | None = None
        worker_input_mode: str | None = None
        brief_path_from_worker: str | None = None
        worker_state: str = "missing"

        if sidecar is not None:
            pid_raw = sidecar.get("pid")
            mode_raw = sidecar.get("mode")
            input_mode_raw = sidecar.get("input_mode")
            brief_path_raw = sidecar.get("brief_path")
            worker_mode = mode_raw if isinstance(mode_raw, str) else None
            worker_input_mode = (
                input_mode_raw if isinstance(input_mode_raw, str) else None
            )
            brief_path_from_worker = (
                brief_path_raw if isinstance(brief_path_raw, str) else None
            )
            if isinstance(pid_raw, int) and not isinstance(pid_raw, bool):
                worker_pid = pid_raw
                worker_alive = is_pid_alive(pid_raw)
                worker_state = "alive" if worker_alive else "stale"
            else:
                worker_pid = None
                worker_alive = None
                worker_state = "stale"

        if source == "linkedin":
            resumable = linkedin_resumable(state_dir)
        else:
            resumable = None

        entries.append(
            StateDirEntry(
                source=source,  # type: ignore[arg-type]
                state_key=state_dir.name,
                state_dir=str(state_dir),
                runtime_state_present=runtime_state_present,
                latest_run=latest_run,
                brief_id_from_run=brief_id_from_run,
                brief_path_from_worker=brief_path_from_worker,
                worker_json_present=worker_json_present,
                worker_pid=worker_pid,
                worker_alive=worker_alive,
                worker_mode=worker_mode,
                worker_input_mode=worker_input_mode,
                resumable=resumable,
                worker_state=worker_state,  # type: ignore[arg-type]
            )
        )

    entries.sort(key=lambda e: (e.source, e.state_key))
    return StatusResponse(slice="v0-shell-slice-4", entries=entries)
