"""Phase 2 tests for ``shared.runtime_state.read_models``.

Pins:

- The hard layering rule: ``read_models.py`` must NOT import
  ``shared.runtime_state.store``. AST-walk the source to enforce.
- Each primitive against missing / corrupt / WAL-not-readable / empty
  / populated DBs.
- Tagged-union semantics on ``work_unit_progress``: ``not_found`` /
  ``empty`` / ``counts`` are distinguishable.
- ``attempt_health`` time-window math (per critique B2: parse-and-compare,
  not string-compare).
- ``has_pending_work`` matches the documented divergence from the
  orchestrator's ``_resume_has_pending_work``.
"""

from __future__ import annotations

import ast
import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from shared.runtime_state import read_models
from shared.runtime_state.read_models import (
    AttemptHealth,
    RunSummary,
    RunTelemetry,
    WorkUnitProgress,
    attempt_health,
    has_pending_work,
    latest_run_summary,
    run_telemetry,
    work_unit_progress,
)
from shared.runtime_state.store import RuntimeStateStore


# --- layering rule ----------------------------------------------------------


def test_read_models_does_not_import_runtime_state_store() -> None:
    """The whole point of read_models.py is to give read-only consumers
    a path that does NOT trigger RuntimeStateStore.__init__'s DDL +
    INSERT-OR-REPLACE side effects. Importing the store class would
    silently re-introduce that hazard. AST-walk the source so the
    enforcement is mechanical, not stylistic."""

    source = read_models.__file__
    assert source is not None
    tree = ast.parse(Path(source).read_text())

    forbidden = "RuntimeStateStore"
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module.endswith("runtime_state.store") or module == "shared.runtime_state.store":
                names = [alias.name for alias in node.names]
                assert forbidden not in names, (
                    f"read_models must not import {forbidden} from {module}; "
                    "the writer's __init__ runs DDL on every instantiation."
                )
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name != "shared.runtime_state.store", (
                    "read_models must not import the writer module."
                )


def test_read_models_does_not_create_db_files(tmp_path: Path) -> None:
    """Reading from a state dir whose runtime_state.sqlite3 does NOT
    exist must not create one. The writer creates the file on
    instantiation; this is exactly the behavior we're trying to avoid
    on the read path."""

    db_path = tmp_path / "runtime_state.sqlite3"
    assert not db_path.exists()

    assert latest_run_summary(db_path) is None
    assert has_pending_work(tmp_path) is None
    assert attempt_health(db_path, run_id=1) == AttemptHealth()
    assert work_unit_progress(db_path, run_id=1, kind="linkedin_string") == (
        WorkUnitProgress(kind="not_found")
    )
    # Bug 2 population audit: the four read helpers added to migrate
    # GET endpoints off RuntimeStateStore must also collapse cleanly
    # on missing DBs and must not create the file as a side effect.
    assert read_models.list_intake_sessions(db_path) == []
    assert read_models.get_intake_session(db_path, session_id=1) is None
    assert read_models.get_active_reflection_for_brief(
        db_path, brief_id="any"
    ) is None
    assert read_models.get_reflection_session(db_path, session_id=1) is None

    assert not db_path.exists(), "read primitives must not create the DB file"


# --- latest_run_summary -----------------------------------------------------


def test_latest_run_summary_missing_db(tmp_path: Path) -> None:
    assert latest_run_summary(tmp_path / "missing.sqlite3") is None


def test_latest_run_summary_corrupt_db(tmp_path: Path) -> None:
    bad = tmp_path / "bad.sqlite3"
    bad.write_bytes(b"not a sqlite db")
    assert latest_run_summary(bad) is None


def test_latest_run_summary_empty_runs(tmp_path: Path) -> None:
    db_path = tmp_path / "runtime_state.sqlite3"
    RuntimeStateStore(db_path)
    assert latest_run_summary(db_path) is None


def test_latest_run_summary_returns_latest_row(tmp_path: Path) -> None:
    db_path = tmp_path / "runtime_state.sqlite3"
    store = RuntimeStateStore(db_path)
    run_id = store.start_run(
        source="linkedin",
        brief_id="brief-rm",
        output_dir=str(tmp_path),
        mode="fresh",
    )
    store.finish_run(run_id, "completed", stop_reason="normal")

    summary = latest_run_summary(db_path)
    assert summary is not None
    assert summary.id == run_id
    assert summary.status == "completed"
    assert summary.stop_reason == "normal"
    assert summary.mode == "fresh"
    assert summary.started_at is not None
    assert summary.ended_at is not None


# --- has_pending_work --------------------------------------------------------


def test_has_pending_work_missing_progress_json_returns_none(tmp_path: Path) -> None:
    """Per the documented divergence: passive read model returns None
    on missing/malformed inputs, NOT True. The orchestrator's bias
    toward "attempt resume" is appropriate for an active worker but
    wrong for a passive observer surface."""

    assert has_pending_work(tmp_path) is None


def test_has_pending_work_truthy_pending_block_strings(tmp_path: Path) -> None:
    (tmp_path / "progress.json").write_text(
        json.dumps({"pending_block_string_ids": ["s1", "s2"], "strings": []})
    )
    assert has_pending_work(tmp_path) is True


def test_has_pending_work_empty_returns_false(tmp_path: Path) -> None:
    (tmp_path / "progress.json").write_text(json.dumps({"strings": []}))
    assert has_pending_work(tmp_path) is False


def test_has_pending_work_queued_string_returns_true(tmp_path: Path) -> None:
    (tmp_path / "progress.json").write_text(
        json.dumps({"strings": [{"id": 1, "status": "queued"}]})
    )
    assert has_pending_work(tmp_path) is True


def test_has_pending_work_strings_not_list_returns_none(tmp_path: Path) -> None:
    (tmp_path / "progress.json").write_text(
        json.dumps({"strings": "not a list"})
    )
    assert has_pending_work(tmp_path) is None


def test_has_pending_work_malformed_json_returns_none(tmp_path: Path) -> None:
    (tmp_path / "progress.json").write_text("not json")
    assert has_pending_work(tmp_path) is None


# --- work_unit_progress ------------------------------------------------------


def test_work_unit_progress_not_found_for_unknown_run(tmp_path: Path) -> None:
    db_path = tmp_path / "runtime_state.sqlite3"
    RuntimeStateStore(db_path)
    result = work_unit_progress(db_path, run_id=9999, kind="linkedin_string")
    assert result.kind == "not_found"


def test_work_unit_progress_empty_when_no_units(tmp_path: Path) -> None:
    db_path = tmp_path / "runtime_state.sqlite3"
    store = RuntimeStateStore(db_path)
    run_id = store.start_run(
        source="linkedin",
        brief_id="brief-rm",
        output_dir=str(tmp_path),
        mode="fresh",
    )
    result = work_unit_progress(db_path, run_id=run_id, kind="linkedin_string")
    assert result.kind == "empty"


def test_work_unit_progress_counts_when_units_present(tmp_path: Path) -> None:
    db_path = tmp_path / "runtime_state.sqlite3"
    store = RuntimeStateStore(db_path)
    run_id = store.start_run(
        source="linkedin",
        brief_id="brief-rm",
        output_dir=str(tmp_path),
        mode="fresh",
    )
    for i, status in enumerate(["queued", "queued", "in_progress", "done"]):
        store.upsert_work_unit(
            run_id=run_id,
            source="linkedin",
            brief_id="brief-rm",
            kind="linkedin_string",
            source_unit_id=str(i),
            display_name=f"unit-{i}",
            ordering_index=i,
            status=status,
        )

    result = work_unit_progress(db_path, run_id=run_id, kind="linkedin_string")
    assert result.kind == "counts"
    assert result.queued == 2
    assert result.in_progress == 1
    assert result.done == 1


# --- attempt_health ----------------------------------------------------------


def _direct_insert_attempt(
    db_path: Path,
    *,
    run_id: int,
    candidate_id: int,
    status: str,
    failure_kind: str | None = None,
    started_at: str | None = None,
    ended_at: str | None = None,
) -> None:
    """Insert a candidate_attempts row directly. Bypasses the store's
    state-machine guards because attempt_health tests want to seed
    arbitrary status / failure_kind combinations without driving
    candidate lifecycle transitions."""

    started_at = started_at or datetime.now(timezone.utc).isoformat()
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            "INSERT INTO candidate_attempts(run_id, candidate_id, stage, "
            "attempt_number, status, failure_kind, started_at, ended_at) "
            "VALUES (?, ?, 'snippet', 1, ?, ?, ?, ?)",
            (run_id, candidate_id, status, failure_kind, started_at, ended_at),
        )
        conn.commit()
    finally:
        conn.close()


def test_attempt_health_no_attempts_returns_empty(tmp_path: Path) -> None:
    db_path = tmp_path / "runtime_state.sqlite3"
    store = RuntimeStateStore(db_path)
    run_id = store.start_run(
        source="linkedin",
        brief_id="brief-rm",
        output_dir=str(tmp_path),
        mode="fresh",
    )
    health = attempt_health(db_path, run_id=run_id)
    assert health.total_attempts_in_window == 0
    assert health.last_success_age_s is None
    assert health.dominant_failure_kind is None


def test_attempt_health_recent_failures_dominate(tmp_path: Path) -> None:
    db_path = tmp_path / "runtime_state.sqlite3"
    store = RuntimeStateStore(db_path)
    run_id = store.start_run(
        source="linkedin",
        brief_id="brief-rm",
        output_dir=str(tmp_path),
        mode="fresh",
    )
    candidate_id = store.ensure_candidate(
        source="linkedin", brief_id="brief-rm", identity_key="alice"
    )

    now = datetime.now(timezone.utc)
    for _ in range(8):
        _direct_insert_attempt(
            db_path,
            run_id=run_id,
            candidate_id=candidate_id,
            status="failed",
            failure_kind="http_429",
            started_at=now.isoformat(),
        )
    _direct_insert_attempt(
        db_path,
        run_id=run_id,
        candidate_id=candidate_id,
        status="failed",
        failure_kind="timeout",
        started_at=now.isoformat(),
    )
    _direct_insert_attempt(
        db_path,
        run_id=run_id,
        candidate_id=candidate_id,
        status="succeeded",
        started_at=now.isoformat(),
        ended_at=now.isoformat(),
    )

    health = attempt_health(db_path, run_id=run_id)
    assert health.total_attempts_in_window == 10
    assert health.failed_in_window == 9
    assert health.succeeded_in_window == 1
    assert health.dominant_failure_kind == "http_429"
    # last_success_age_s should be small (we just inserted a success).
    assert health.last_success_age_s is not None
    assert health.last_success_age_s < 5.0


def test_attempt_health_window_excludes_old_attempts(tmp_path: Path) -> None:
    """Per critique B2: parse-and-compare, not string-compare. An
    attempt outside the window (10 minutes ago) must not be counted in
    a 5-minute window."""

    db_path = tmp_path / "runtime_state.sqlite3"
    store = RuntimeStateStore(db_path)
    run_id = store.start_run(
        source="linkedin",
        brief_id="brief-rm",
        output_dir=str(tmp_path),
        mode="fresh",
    )
    candidate_id = store.ensure_candidate(
        source="linkedin", brief_id="brief-rm", identity_key="alice"
    )

    old = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
    _direct_insert_attempt(
        db_path,
        run_id=run_id,
        candidate_id=candidate_id,
        status="failed",
        failure_kind="http_429",
        started_at=old,
    )

    health = attempt_health(db_path, run_id=run_id, window_minutes=5)
    assert health.total_attempts_in_window == 0
    assert health.dominant_failure_kind is None


# --- run_telemetry ----------------------------------------------------------


def _direct_insert_event(
    db_path: Path,
    *,
    run_id: int,
    event_type: str,
    candidate_id: int | None = None,
    attempt_id: int | None = None,
    payload_json: str | None = None,
    created_at: str | None = None,
) -> None:
    """Insert an ``events`` row directly so telemetry tests can seed
    arbitrary event_type / payload combinations without driving the
    canonical writer's helper API."""

    created_at = created_at or datetime.now(timezone.utc).isoformat()
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            "INSERT INTO events(run_id, event_type, candidate_id, attempt_id, "
            "payload_json, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (
                run_id,
                event_type,
                candidate_id,
                attempt_id,
                payload_json or "{}",
                created_at,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def test_run_telemetry_missing_db_returns_empty(tmp_path: Path) -> None:
    """Bug 2 contract: missing DB collapses to an empty RunTelemetry
    instead of raising. Mirrors the existing aggregator pattern."""

    result = run_telemetry(
        tmp_path / "missing.sqlite3",
        run_id=1,
        attempts_limit=10,
        events_limit=10,
    )
    assert result == RunTelemetry()
    assert result.attempts == ()
    assert result.events == ()
    assert result.attempts_total == 0
    assert result.events_total == 0
    assert result.last_event_at is None


def test_run_telemetry_corrupt_db_returns_empty(tmp_path: Path) -> None:
    bad = tmp_path / "bad.sqlite3"
    bad.write_bytes(b"not a sqlite db")
    result = run_telemetry(bad, run_id=1, attempts_limit=10, events_limit=10)
    assert result == RunTelemetry()


def test_run_telemetry_does_not_create_db_file(tmp_path: Path) -> None:
    """The whole point of routing telemetry through read_models is to
    keep the API process from instantiating the writer. Confirm the
    helper does not create the DB file as a side effect."""

    db_path = tmp_path / "runtime_state.sqlite3"
    assert not db_path.exists()
    run_telemetry(db_path, run_id=1, attempts_limit=10, events_limit=10)
    assert not db_path.exists(), (
        "run_telemetry must not create the DB file (writer behavior)."
    )


def test_run_telemetry_does_not_mutate_meta_table(tmp_path: Path) -> None:
    """Regression for the read-path-violation class: instantiating
    RuntimeStateStore against a populated DB rewrites the
    ``schema_version`` row in ``meta``. The read_models helper must
    not. Pin by snapshotting meta before and after a telemetry read."""

    db_path = tmp_path / "runtime_state.sqlite3"
    store = RuntimeStateStore(db_path)
    run_id = store.start_run(
        source="linkedin",
        brief_id="brief-tel",
        output_dir=str(tmp_path),
        mode="fresh",
    )
    store.finish_run(run_id, "completed", stop_reason="normal")

    before = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    before.row_factory = sqlite3.Row
    snapshot_before = sorted(
        (row["key"], row["value"])
        for row in before.execute("SELECT key, value FROM meta").fetchall()
    )
    before.close()

    run_telemetry(db_path, run_id=run_id, attempts_limit=10, events_limit=10)

    after = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    after.row_factory = sqlite3.Row
    snapshot_after = sorted(
        (row["key"], row["value"])
        for row in after.execute("SELECT key, value FROM meta").fetchall()
    )
    after.close()

    assert snapshot_before == snapshot_after, (
        "run_telemetry must not rewrite the meta table; if this fails, "
        "the read path is silently instantiating the writer again."
    )


def test_run_telemetry_returns_attempts_and_events_newest_first(
    tmp_path: Path,
) -> None:
    """``store.start_run`` auto-creates a ``run_started`` event; the
    test seeds two more events on top so the total is 3 and the
    ordering pin has actual variation to assert against."""

    db_path = tmp_path / "runtime_state.sqlite3"
    store = RuntimeStateStore(db_path)
    run_id = store.start_run(
        source="linkedin",
        brief_id="brief-tel",
        output_dir=str(tmp_path),
        mode="fresh",
    )

    base = datetime.now(timezone.utc)
    for offset, status in enumerate(["succeeded", "failed", "succeeded"]):
        _direct_insert_attempt(
            db_path,
            run_id=run_id,
            candidate_id=offset + 1,
            status=status,
            failure_kind=("http_429" if status == "failed" else None),
            started_at=(base + timedelta(seconds=offset + 1)).isoformat(),
        )
    for offset, etype in enumerate(["candidate_seen", "candidate_terminal"]):
        _direct_insert_event(
            db_path,
            run_id=run_id,
            event_type=etype,
            created_at=(base + timedelta(seconds=offset + 10)).isoformat(),
        )

    result = run_telemetry(
        db_path, run_id=run_id, attempts_limit=10, events_limit=10
    )
    assert result.attempts_total == 3
    assert result.events_total == 3  # 2 seeded + 1 auto run_started
    assert len(result.attempts) == 3
    assert len(result.events) == 3
    assert result.last_event_at is not None

    attempt_started_descending = [a.started_at for a in result.attempts]
    assert attempt_started_descending == sorted(
        attempt_started_descending, reverse=True
    )
    event_created_descending = [e.created_at for e in result.events]
    assert event_created_descending == sorted(
        event_created_descending, reverse=True
    )


def test_run_telemetry_respects_limits(tmp_path: Path) -> None:
    """``start_run`` auto-creates one ``run_started`` event, so the
    seeded count of 5 plus that auto-event totals 6."""

    db_path = tmp_path / "runtime_state.sqlite3"
    store = RuntimeStateStore(db_path)
    run_id = store.start_run(
        source="linkedin",
        brief_id="brief-tel",
        output_dir=str(tmp_path),
        mode="fresh",
    )

    base = datetime.now(timezone.utc)
    for offset in range(8):
        _direct_insert_attempt(
            db_path,
            run_id=run_id,
            candidate_id=offset + 100,
            status="succeeded",
            started_at=(base + timedelta(seconds=offset + 1)).isoformat(),
        )
    for offset in range(5):
        _direct_insert_event(
            db_path,
            run_id=run_id,
            event_type="candidate_seen",
            created_at=(base + timedelta(seconds=offset + 10)).isoformat(),
        )

    result = run_telemetry(
        db_path, run_id=run_id, attempts_limit=3, events_limit=2
    )
    assert result.attempts_total == 8  # unbounded
    assert result.events_total == 6  # 5 seeded + 1 auto run_started
    assert len(result.attempts) == 3  # bounded by limit
    assert len(result.events) == 2  # bounded by limit


# --- intake-session read helpers --------------------------------------------


def _seed_intake_session(
    db_path: Path,
    *,
    role_title: str | None = None,
    archived: bool = False,
    state_json: str = "{}",
) -> int:
    """Insert a row directly into intake_sessions and return its id.

    Bypasses the writer-side helpers so this test module stays free of
    the RuntimeStateStore import path while still exercising the
    read helpers against realistic data. The row is created via direct
    SQL after the writer has set up the schema once at the module level
    (see fixture below)."""

    now = datetime.now(timezone.utc).isoformat()
    archived_at = now if archived else None
    conn = sqlite3.connect(str(db_path))
    try:
        cur = conn.execute(
            """
            INSERT INTO intake_sessions(
                role_title, current_step, state_json,
                started_at, updated_at, archived_at
            ) VALUES (?, 'welcome', ?, ?, ?, ?)
            """,
            (role_title, state_json, now, now, archived_at),
        )
        conn.commit()
        return int(cur.lastrowid)
    finally:
        conn.close()


def test_list_intake_sessions_excludes_archived(tmp_path: Path) -> None:
    """Mirrors the writer-side helper's contract: archived sessions must
    not surface in the active-list view."""

    db_path = tmp_path / "intake.sqlite3"
    RuntimeStateStore(db_path)
    active_id = _seed_intake_session(db_path, role_title="Active Role")
    _seed_intake_session(db_path, role_title="Archived Role", archived=True)

    sessions = read_models.list_intake_sessions(db_path)
    assert len(sessions) == 1
    assert sessions[0]["id"] == active_id
    assert sessions[0]["role_title"] == "Active Role"
    assert sessions[0]["archived_at"] is None


def test_list_intake_sessions_state_json_parsed(tmp_path: Path) -> None:
    db_path = tmp_path / "intake.sqlite3"
    RuntimeStateStore(db_path)
    _seed_intake_session(
        db_path,
        role_title="Parsed Role",
        state_json=json.dumps({"step": 1, "draft": {"k": "v"}}),
    )

    sessions = read_models.list_intake_sessions(db_path)
    assert sessions[0]["state_json"] == {"step": 1, "draft": {"k": "v"}}


def test_list_intake_sessions_corrupt_state_json_collapses_to_dict(
    tmp_path: Path,
) -> None:
    """Defensive parsing: a row with malformed JSON must not break the
    list view (matches the writer-side helper's posture)."""

    db_path = tmp_path / "intake.sqlite3"
    RuntimeStateStore(db_path)
    _seed_intake_session(
        db_path, role_title="Bad JSON", state_json="not valid json"
    )

    sessions = read_models.list_intake_sessions(db_path)
    assert sessions[0]["state_json"] == {}


def test_get_intake_session_returns_archived(tmp_path: Path) -> None:
    """The detail GET returns archived sessions too — recruiters use
    deep-links / unarchive flows that need to inspect the row."""

    db_path = tmp_path / "intake.sqlite3"
    RuntimeStateStore(db_path)
    archived_id = _seed_intake_session(
        db_path, role_title="Archived", archived=True
    )

    result = read_models.get_intake_session(db_path, session_id=archived_id)
    assert result is not None
    assert result["id"] == archived_id
    assert result["archived_at"] is not None


def test_get_intake_session_unknown_id_returns_none(tmp_path: Path) -> None:
    db_path = tmp_path / "intake.sqlite3"
    RuntimeStateStore(db_path)
    assert read_models.get_intake_session(db_path, session_id=999999) is None


# --- reflection read helpers ------------------------------------------------


def _seed_reflection_session(
    db_path: Path,
    *,
    brief_id: str,
    current_phase: str = "planning",
    completed: bool = False,
    discarded: bool = False,
    state_json: str = "{}",
) -> int:
    """Insert a reflection_sessions row directly. Same posture as the
    intake helper above."""

    now = datetime.now(timezone.utc).isoformat()
    completed_at = now if completed else None
    discarded_at = now if discarded else None
    conn = sqlite3.connect(str(db_path))
    try:
        cur = conn.execute(
            """
            INSERT INTO reflection_sessions(
                brief_id, source_run_id, current_phase, state_json,
                steering_iterations, started_at, updated_at,
                completed_at, discarded_at
            ) VALUES (?, NULL, ?, ?, 0, ?, ?, ?, ?)
            """,
            (
                brief_id,
                current_phase,
                state_json,
                now,
                now,
                completed_at,
                discarded_at,
            ),
        )
        conn.commit()
        return int(cur.lastrowid)
    finally:
        conn.close()


def test_get_active_reflection_picks_non_terminal(tmp_path: Path) -> None:
    db_path = tmp_path / "intake.sqlite3"
    RuntimeStateStore(db_path)
    active_id = _seed_reflection_session(db_path, brief_id="brief-a")
    _seed_reflection_session(
        db_path, brief_id="brief-a", completed=True
    )

    result = read_models.get_active_reflection_for_brief(
        db_path, brief_id="brief-a"
    )
    assert result is not None
    assert result["id"] == active_id
    assert result["completed_at"] is None
    assert result["discarded_at"] is None


def test_get_active_reflection_returns_none_when_all_terminal(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "intake.sqlite3"
    RuntimeStateStore(db_path)
    _seed_reflection_session(db_path, brief_id="brief-a", completed=True)
    _seed_reflection_session(db_path, brief_id="brief-a", discarded=True)

    assert read_models.get_active_reflection_for_brief(
        db_path, brief_id="brief-a"
    ) is None


def test_get_reflection_session_returns_terminal_rows(tmp_path: Path) -> None:
    """The GET endpoint serves both in-flight resume and post-mortem;
    discarded/completed rows must remain visible by id."""

    db_path = tmp_path / "intake.sqlite3"
    RuntimeStateStore(db_path)
    discarded_id = _seed_reflection_session(
        db_path, brief_id="brief-x", discarded=True
    )

    result = read_models.get_reflection_session(
        db_path, session_id=discarded_id
    )
    assert result is not None
    assert result["id"] == discarded_id
    assert result["discarded_at"] is not None


def test_get_reflection_session_unknown_id_returns_none(tmp_path: Path) -> None:
    db_path = tmp_path / "intake.sqlite3"
    RuntimeStateStore(db_path)
    assert read_models.get_reflection_session(db_path, session_id=999999) is None


def test_run_telemetry_filters_by_run_id(tmp_path: Path) -> None:
    """Belt-and-suspenders: a row for a different run must not leak
    into another run's telemetry view. Each ``start_run`` auto-creates
    one ``run_started`` event scoped to its own run_id."""

    db_path = tmp_path / "runtime_state.sqlite3"
    store = RuntimeStateStore(db_path)
    run_a = store.start_run(
        source="linkedin",
        brief_id="brief-a",
        output_dir=str(tmp_path),
        mode="fresh",
    )
    run_b = store.start_run(
        source="linkedin",
        brief_id="brief-b",
        output_dir=str(tmp_path),
        mode="fresh",
    )
    _direct_insert_attempt(
        db_path, run_id=run_a, candidate_id=1, status="succeeded"
    )
    _direct_insert_event(
        db_path, run_id=run_b, event_type="candidate_seen"
    )

    result_a = run_telemetry(
        db_path, run_id=run_a, attempts_limit=10, events_limit=10
    )
    assert result_a.attempts_total == 1
    assert result_a.events_total == 1  # auto run_started for run_a only
    assert all(e.event_type == "run_started" for e in result_a.events)

    result_b = run_telemetry(
        db_path, run_id=run_b, attempts_limit=10, events_limit=10
    )
    assert result_b.attempts_total == 0
    # auto run_started + seeded candidate_seen, both for run_b
    assert result_b.events_total == 2
