"""Tests for the Cloris status aggregator (Slice 2).

These tests pin the read-only contract of :mod:`cloris.control_plane`:

- The aggregator opens canonical SQLite read-only and never instantiates
  :class:`shared.runtime_state.store.RuntimeStateStore` in production paths.
  Test fixtures *may* use ``RuntimeStateStore`` to build a real DB — that is
  the cleanest way to exercise the read path.
- An empty state root returns an empty list, not an error.
- A state dir with no DB shows ``runtime_state_present=False`` and null run
  fields.
- A real ``runs`` row is forwarded verbatim (no semantic shaping).
- The aggregator is source-symmetric across LinkedIn and GitHub.
- Repeated polls do not mutate the underlying DB (the canonical read-only
  invariant Slice 2 must hold).
- A corrupt DB collapses cleanly to ``latest_run=None`` instead of crashing
  the whole response.
"""

from __future__ import annotations

import inspect
import os
from pathlib import Path

from cloris import control_plane
from cloris.control_plane import aggregate_status
from shared.runtime_state.store import RuntimeStateStore


assert "RuntimeStateStore" not in inspect.getsource(control_plane), (
    "cloris/control_plane.py must not import or reference RuntimeStateStore "
    "in production paths (Slice 2 read-only contract)."
)


def _build_state_dir(state_root: Path, source: str, key: str) -> Path:
    state_dir = state_root / source / key
    state_dir.mkdir(parents=True, exist_ok=True)
    return state_dir


def test_aggregate_empty_state_root(tmp_path: Path) -> None:
    response = aggregate_status(tmp_path)

    assert response.slice == "v0-shell-slice-2"
    assert response.entries == []


def test_aggregate_state_dir_without_db(tmp_path: Path) -> None:
    _build_state_dir(tmp_path, "linkedin", "some-key")

    response = aggregate_status(tmp_path)

    assert response.slice == "v0-shell-slice-2"
    assert len(response.entries) == 1

    entry = response.entries[0]
    assert entry.source == "linkedin"
    assert entry.state_key == "some-key"
    assert entry.runtime_state_present is False
    assert entry.latest_run is None
    assert entry.brief_id_from_run is None


def test_aggregate_state_dir_with_run_row(tmp_path: Path) -> None:
    state_dir = _build_state_dir(tmp_path, "linkedin", "key")
    db_path = state_dir / "runtime_state.sqlite3"
    store = RuntimeStateStore(db_path)
    run_id = store.start_run(
        source="linkedin",
        brief_id="brief-1",
        output_dir=str(state_dir),
        mode="fresh",
        resume_state={"brief_name": "brief-1"},
    )
    store.finish_run(run_id, "completed")

    response = aggregate_status(tmp_path)

    assert len(response.entries) == 1
    entry = response.entries[0]
    assert entry.source == "linkedin"
    assert entry.state_key == "key"
    assert entry.runtime_state_present is True
    assert entry.brief_id_from_run == "brief-1"
    assert entry.latest_run is not None
    assert entry.latest_run.status == "completed"
    assert entry.latest_run.id == run_id
    assert entry.latest_run.mode == "fresh"


def test_aggregate_across_linkedin_and_github(tmp_path: Path) -> None:
    linkedin_dir = _build_state_dir(tmp_path, "linkedin", "li-key")
    li_store = RuntimeStateStore(linkedin_dir / "runtime_state.sqlite3")
    li_store.start_run(
        source="linkedin",
        brief_id="brief-li",
        output_dir=str(linkedin_dir),
        mode="fresh",
        resume_state={"brief_name": "brief-li"},
    )

    github_dir = _build_state_dir(tmp_path, "github", "gh-key")
    gh_store = RuntimeStateStore(github_dir / "runtime_state.sqlite3")
    gh_run_id = gh_store.start_run(
        source="github",
        brief_id="brief-gh",
        output_dir=str(github_dir),
        mode="fresh",
        resume_state={"brief_name": "brief-gh"},
    )
    gh_store.finish_run(gh_run_id, "interrupted")

    response = aggregate_status(tmp_path)

    by_source = {entry.source: entry for entry in response.entries}
    assert set(by_source) == {"linkedin", "github"}

    li_entry = by_source["linkedin"]
    assert li_entry.state_key == "li-key"
    assert li_entry.runtime_state_present is True
    assert li_entry.latest_run is not None
    assert li_entry.latest_run.status == "running"
    assert li_entry.brief_id_from_run == "brief-li"

    gh_entry = by_source["github"]
    assert gh_entry.state_key == "gh-key"
    assert gh_entry.runtime_state_present is True
    assert gh_entry.latest_run is not None
    assert gh_entry.latest_run.status == "interrupted"
    assert gh_entry.brief_id_from_run == "brief-gh"


def test_aggregator_does_not_write_to_db(tmp_path: Path) -> None:
    state_dir = _build_state_dir(tmp_path, "linkedin", "ro-key")
    db_path = state_dir / "runtime_state.sqlite3"
    store = RuntimeStateStore(db_path)
    run_id = store.start_run(
        source="linkedin",
        brief_id="brief-ro",
        output_dir=str(state_dir),
        mode="fresh",
        resume_state={"brief_name": "brief-ro"},
    )
    store.finish_run(run_id, "completed")

    pinned_mtime_ns = 1_700_000_000_000_000_000
    os.utime(db_path, ns=(pinned_mtime_ns, pinned_mtime_ns))
    baseline_mtime = db_path.stat().st_mtime_ns

    for _ in range(3):
        aggregate_status(tmp_path)
        assert db_path.stat().st_mtime_ns == baseline_mtime, (
            "aggregate_status must be a pure read; db mtime changed across polls"
        )


def test_aggregator_handles_corrupt_db_gracefully(tmp_path: Path) -> None:
    state_dir = _build_state_dir(tmp_path, "linkedin", "corrupt-key")
    db_path = state_dir / "runtime_state.sqlite3"
    db_path.write_bytes(b"not a sqlite database")

    response = aggregate_status(tmp_path)

    assert len(response.entries) == 1
    entry = response.entries[0]
    assert entry.runtime_state_present is True
    assert entry.latest_run is None
    assert entry.brief_id_from_run is None
