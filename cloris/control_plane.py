"""Cloris status aggregator (Slice 2).

Pure read-only aggregation over per-state-dir canonical SQLite stores. This is
the single seam between Cloris and the canonical runtime-state files; it has
no FastAPI imports, no pywebview imports, and **no** import of the canonical
runtime-state store class in production paths.

Why not the canonical store class? Its constructor runs unconditional DDL plus
``INSERT OR REPLACE INTO meta`` on every instantiation
(``shared/runtime_state/store.py:56-213``), which would make the API process
silently writable against active runtime state. We open the file directly via
``sqlite3.connect(f"file:{path}?mode=ro", uri=True)`` so the read path is
honestly read-only.

Only Slice 2 surfaces live here:

- :func:`enumerate_state_dirs` — list discovered state dirs across LinkedIn
  and GitHub.
- :func:`read_latest_run_readonly` — open one canonical SQLite read-only and
  return the latest ``runs`` row as a dict, or ``None``.
- :func:`aggregate_status` — orchestrate the two above and return a
  :class:`cloris.models.StatusResponse`.

Worker control, ``worker.json`` sidecar reads, and any semantic shaping of
``runs.status`` are explicitly out of scope until later slices.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Iterator

from cloris.models import RunSummary, StateDirEntry, StatusResponse


_SOURCES: tuple[str, ...] = ("linkedin", "github")
_RUNTIME_DB_FILENAME = "runtime_state.sqlite3"
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


def aggregate_status(state_root: Path | None = None) -> StatusResponse:
    """Build a :class:`StatusResponse` for ``GET /api/status``.

    Pure function of disk: walks every discovered state dir, reads the
    latest ``runs`` row read-only when a DB is present, and returns a stable
    response sorted by ``(source, state_key)`` so tests and clients see
    deterministic ordering.
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

        entries.append(
            StateDirEntry(
                source=source,  # type: ignore[arg-type]
                state_key=state_dir.name,
                state_dir=str(state_dir),
                runtime_state_present=runtime_state_present,
                latest_run=latest_run,
                brief_id_from_run=brief_id_from_run,
            )
        )

    entries.sort(key=lambda e: (e.source, e.state_key))
    return StatusResponse(slice="v0-shell-slice-2", entries=entries)
