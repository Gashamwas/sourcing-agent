"""SQLite-backed canonical runtime state store."""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from github.schemas import GitHubProgress, GitHubSearchQuery
from shared.contracts import TARGET_CANDIDATE_LIFECYCLE

GITHUB_QUERY_KIND = "github_query"
GITHUB_GRAPH_SEED_KIND = "github_graph_seed"
LINKEDIN_STRING_KIND = "linkedin_string"
SIDE_EFFECT_TERMINAL_STATUSES = {"succeeded", "failed", "skipped", "invalidated"}

TERMINAL_WORK_UNIT_STATUSES = {"done", "skipped", "error"}
DEDUP_BLOCKING_RUNTIME_DECISIONS = {
    "LEGACY_TERMINAL",
    "GEO_FILTERED",
    "PRESCREEN_SKIP",
    "INSUFFICIENT_DATA",
}
DEDUP_BLOCKING_LINKEDIN_DECISIONS = {
    "FACIAL_NO",
    "FACIAL_SKIP",
    "SAVE",
    "REJECT",
    "INFERENTIAL_SAVE",
    "TRANSFERABLE_SAVE",
    "SIGNAL_SAVE",
}
DEDUP_BLOCKING_DECISIONS = (
    DEDUP_BLOCKING_RUNTIME_DECISIONS | DEDUP_BLOCKING_LINKEDIN_DECISIONS
)

ALLOWED_LIFECYCLE_TRANSITIONS: dict[str, set[str]] = {
    "discovered": {"snippet_extracted", "failed_retryable", "failed_terminal"},
    "snippet_extracted": {"facial_started", "failed_retryable", "failed_terminal"},
    "facial_started": {"facial_terminal", "failed_retryable", "failed_terminal"},
    "facial_terminal": {"full_started", "failed_retryable", "failed_terminal"},
    "full_started": {"full_terminal", "failed_retryable", "failed_terminal"},
    "full_terminal": set(),
    "failed_retryable": {"snippet_extracted", "facial_started", "full_started", "failed_retryable", "failed_terminal"},
    "failed_terminal": set(),
}


class RuntimeStateStore:
    """Authoritative runtime state for candidate lifecycle and resume semantics."""

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA journal_mode=WAL")
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def initialize(self) -> None:
        with self.connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source TEXT NOT NULL,
                    brief_id TEXT NOT NULL,
                    output_dir TEXT NOT NULL,
                    mode TEXT NOT NULL,
                    status TEXT NOT NULL,
                    stop_reason TEXT NOT NULL DEFAULT 'normal',
                    started_at TEXT NOT NULL,
                    ended_at TEXT,
                    resumed_from_run_id INTEGER,
                    resume_state_json TEXT NOT NULL DEFAULT '{}',
                    FOREIGN KEY(resumed_from_run_id) REFERENCES runs(id)
                );

                CREATE TABLE IF NOT EXISTS work_units (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id INTEGER NOT NULL,
                    source TEXT NOT NULL,
                    brief_id TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    source_unit_id TEXT NOT NULL,
                    display_name TEXT NOT NULL,
                    ordering_index INTEGER NOT NULL DEFAULT 0,
                    status TEXT NOT NULL,
                    payload_json TEXT NOT NULL DEFAULT '{}',
                    checkpoint_json TEXT NOT NULL DEFAULT '{}',
                    metrics_json TEXT NOT NULL DEFAULT '{}',
                    family_key TEXT NOT NULL DEFAULT '',
                    novelty_bucket TEXT NOT NULL DEFAULT '',
                    domain_lane TEXT NOT NULL DEFAULT '',
                    result_count INTEGER NOT NULL DEFAULT 0,
                    candidates_discovered INTEGER NOT NULL DEFAULT 0,
                    candidates_enriched INTEGER NOT NULL DEFAULT 0,
                    candidates_insufficient INTEGER NOT NULL DEFAULT 0,
                    facial_yes_count INTEGER NOT NULL DEFAULT 0,
                    facial_no_count INTEGER NOT NULL DEFAULT 0,
                    saves_count INTEGER NOT NULL DEFAULT 0,
                    rejected_count INTEGER NOT NULL DEFAULT 0,
                    notes TEXT NOT NULL DEFAULT '',
                    started_at TEXT,
                    ended_at TEXT,
                    FOREIGN KEY(run_id) REFERENCES runs(id) ON DELETE CASCADE,
                    UNIQUE(run_id, kind, source_unit_id)
                );

                CREATE TABLE IF NOT EXISTS candidates (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source TEXT NOT NULL,
                    brief_id TEXT NOT NULL,
                    identity_key TEXT NOT NULL,
                    display_name TEXT NOT NULL DEFAULT '',
                    profile_url TEXT NOT NULL DEFAULT '',
                    current_lifecycle_state TEXT NOT NULL,
                    terminal_decision TEXT,
                    terminal_payload_json TEXT NOT NULL DEFAULT '{}',
                    last_work_unit_id INTEGER,
                    last_attempt_id INTEGER,
                    first_seen_at TEXT NOT NULL,
                    last_seen_at TEXT NOT NULL,
                    UNIQUE(brief_id, source, identity_key),
                    FOREIGN KEY(last_work_unit_id) REFERENCES work_units(id) ON DELETE SET NULL
                );

                CREATE TABLE IF NOT EXISTS candidate_attempts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id INTEGER NOT NULL,
                    candidate_id INTEGER NOT NULL,
                    work_unit_id INTEGER,
                    stage TEXT NOT NULL,
                    attempt_number INTEGER NOT NULL,
                    batch_key TEXT,
                    status TEXT NOT NULL,
                    failure_kind TEXT,
                    failure_reason TEXT,
                    payload_json TEXT NOT NULL DEFAULT '{}',
                    source_cursor_json TEXT NOT NULL DEFAULT '{}',
                    started_at TEXT NOT NULL,
                    ended_at TEXT,
                    FOREIGN KEY(run_id) REFERENCES runs(id) ON DELETE CASCADE,
                    FOREIGN KEY(candidate_id) REFERENCES candidates(id) ON DELETE CASCADE,
                    FOREIGN KEY(work_unit_id) REFERENCES work_units(id) ON DELETE SET NULL
                );

                CREATE UNIQUE INDEX IF NOT EXISTS idx_candidate_open_attempt
                ON candidate_attempts(candidate_id)
                WHERE status = 'started';

                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id INTEGER,
                    work_unit_id INTEGER,
                    candidate_id INTEGER,
                    attempt_id INTEGER,
                    event_type TEXT NOT NULL,
                    payload_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(run_id) REFERENCES runs(id) ON DELETE CASCADE,
                    FOREIGN KEY(work_unit_id) REFERENCES work_units(id) ON DELETE CASCADE,
                    FOREIGN KEY(candidate_id) REFERENCES candidates(id) ON DELETE CASCADE,
                    FOREIGN KEY(attempt_id) REFERENCES candidate_attempts(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS side_effects (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id INTEGER,
                    candidate_id INTEGER NOT NULL,
                    attempt_id INTEGER,
                    effect_type TEXT NOT NULL,
                    idempotency_key TEXT NOT NULL,
                    status TEXT NOT NULL,
                    payload_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    invalidated_at TEXT,
                    FOREIGN KEY(run_id) REFERENCES runs(id) ON DELETE CASCADE,
                    FOREIGN KEY(candidate_id) REFERENCES candidates(id) ON DELETE CASCADE,
                    FOREIGN KEY(attempt_id) REFERENCES candidate_attempts(id) ON DELETE SET NULL,
                    UNIQUE(candidate_id, effect_type, idempotency_key)
                );
                """
            )
            conn.execute(
                "INSERT OR REPLACE INTO meta(key, value) VALUES (?, ?)",
                ("schema_version", "3"),
            )
            conn.execute(
                "INSERT OR REPLACE INTO meta(key, value) VALUES (?, ?)",
                ("target_candidate_lifecycle", json.dumps(TARGET_CANDIDATE_LIFECYCLE)),
            )
            self._migrate(conn)

    def _migrate(self, conn: sqlite3.Connection) -> None:
        columns = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(work_units)").fetchall()
        }
        if "metrics_json" not in columns:
            conn.execute(
                "ALTER TABLE work_units ADD COLUMN metrics_json TEXT NOT NULL DEFAULT '{}'"
            )
        run_columns = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(runs)").fetchall()
        }
        if "stop_reason" not in run_columns:
            conn.execute(
                "ALTER TABLE runs ADD COLUMN stop_reason TEXT NOT NULL DEFAULT 'normal'"
            )
        conn.execute(
            "INSERT OR REPLACE INTO meta(key, value) VALUES (?, ?)",
            ("schema_version", "3"),
        )

    # ------------------------------------------------------------------
    # Runs
    # ------------------------------------------------------------------

    def start_run(
        self,
        *,
        source: str,
        brief_id: str,
        output_dir: str,
        mode: str,
        resume_state: dict | None = None,
        resumed_from_run_id: int | None = None,
        clone_work_units_from_run_id: int | None = None,
    ) -> int:
        now = _utc_now()
        with self.connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO runs(source, brief_id, output_dir, mode, status, started_at, resumed_from_run_id, resume_state_json)
                VALUES (?, ?, ?, ?, 'running', ?, ?, ?)
                """,
                (
                    source,
                    brief_id,
                    str(output_dir),
                    mode,
                    now,
                    resumed_from_run_id,
                    _json_dumps(resume_state or {}),
                ),
            )
            run_id = int(cursor.lastrowid)
            if clone_work_units_from_run_id:
                rows = conn.execute(
                    """
                    SELECT source, brief_id, kind, source_unit_id, display_name, ordering_index, status,
                           payload_json, checkpoint_json, metrics_json, family_key, novelty_bucket, domain_lane,
                           result_count, candidates_discovered, candidates_enriched, candidates_insufficient,
                           facial_yes_count, facial_no_count, saves_count, rejected_count, notes
                    FROM work_units
                    WHERE run_id = ?
                    ORDER BY ordering_index ASC, id ASC
                    """,
                    (clone_work_units_from_run_id,),
                ).fetchall()
                for row in rows:
                    conn.execute(
                        """
                        INSERT INTO work_units(
                            run_id, source, brief_id, kind, source_unit_id, display_name, ordering_index, status,
                            payload_json, checkpoint_json, metrics_json, family_key, novelty_bucket, domain_lane,
                            result_count, candidates_discovered, candidates_enriched, candidates_insufficient,
                            facial_yes_count, facial_no_count, saves_count, rejected_count, notes
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            run_id,
                            row["source"],
                            row["brief_id"],
                            row["kind"],
                            row["source_unit_id"],
                            row["display_name"],
                            row["ordering_index"],
                            row["status"],
                            row["payload_json"],
                            row["checkpoint_json"],
                            row["metrics_json"],
                            row["family_key"],
                            row["novelty_bucket"],
                            row["domain_lane"],
                            row["result_count"],
                            row["candidates_discovered"],
                            row["candidates_enriched"],
                            row["candidates_insufficient"],
                            row["facial_yes_count"],
                            row["facial_no_count"],
                            row["saves_count"],
                            row["rejected_count"],
                            row["notes"],
                        ),
                    )
            self._insert_event(conn, run_id=run_id, event_type="run_started", payload={"mode": mode})
            return run_id

    def finish_run(self, run_id: int, status: str, *, stop_reason: str = "normal") -> None:
        with self.connect() as conn:
            conn.execute(
                "UPDATE runs SET status = ?, stop_reason = ?, ended_at = ? WHERE id = ?",
                (status, stop_reason, _utc_now(), run_id),
            )
            self._insert_event(
                conn,
                run_id=run_id,
                event_type="run_finished",
                payload={"status": status, "stop_reason": stop_reason},
            )

    def set_run_stop_reason(self, run_id: int, stop_reason: str) -> None:
        with self.connect() as conn:
            conn.execute(
                "UPDATE runs SET stop_reason = ? WHERE id = ?",
                (stop_reason, run_id),
            )

    def get_latest_run(self, *, source: str, brief_id: str) -> dict | None:
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM runs
                WHERE source = ? AND brief_id = ?
                ORDER BY id DESC
                LIMIT 1
                """,
                (source, brief_id),
            ).fetchone()
            return _row_to_dict(row) if row else None

    def list_runs(self, *, source: str, brief_id: str) -> list[dict]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT *
                FROM runs
                WHERE source = ? AND brief_id = ?
                ORDER BY id DESC
                """,
                (source, brief_id),
            ).fetchall()
            return [_row_to_dict(row) for row in rows]

    def get_run(self, run_id: int) -> dict | None:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
            return _row_to_dict(row) if row else None

    def update_run_resume_state(self, run_id: int, resume_state: dict) -> None:
        with self.connect() as conn:
            conn.execute(
                "UPDATE runs SET resume_state_json = ? WHERE id = ?",
                (_json_dumps(resume_state), run_id),
            )

    def get_run_resume_state(self, run_id: int) -> dict:
        run = self.get_run(run_id)
        if not run:
            return {}
        return _json_loads(run.get("resume_state_json"))

    # ------------------------------------------------------------------
    # Work units
    # ------------------------------------------------------------------

    def has_work_units(self, run_id: int) -> bool:
        with self.connect() as conn:
            row = conn.execute("SELECT 1 FROM work_units WHERE run_id = ? LIMIT 1", (run_id,)).fetchone()
            return row is not None

    def list_work_units(self, run_id: int, *, kind: str | None = None) -> list[dict]:
        sql = "SELECT * FROM work_units WHERE run_id = ?"
        params: list[Any] = [run_id]
        if kind is not None:
            sql += " AND kind = ?"
            params.append(kind)
        sql += " ORDER BY ordering_index ASC, id ASC"
        with self.connect() as conn:
            rows = conn.execute(sql, params).fetchall()
            return [_row_to_dict(row) for row in rows]

    def get_work_unit_by_source_id(self, run_id: int, *, kind: str, source_unit_id: str) -> dict | None:
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM work_units
                WHERE run_id = ? AND kind = ? AND source_unit_id = ?
                """,
                (run_id, kind, str(source_unit_id)),
            ).fetchone()
            return _row_to_dict(row) if row else None

    def get_work_unit_id(self, run_id: int, *, kind: str, source_unit_id: str) -> int | None:
        unit = self.get_work_unit_by_source_id(run_id, kind=kind, source_unit_id=source_unit_id)
        return int(unit["id"]) if unit else None

    def upsert_work_unit(
        self,
        *,
        run_id: int,
        source: str,
        brief_id: str,
        kind: str,
        source_unit_id: str,
        display_name: str,
        ordering_index: int,
        status: str,
        payload: dict | None = None,
        checkpoint: dict | None = None,
        metrics: dict | None = None,
        family_key: str = "",
        novelty_bucket: str = "",
        domain_lane: str = "",
        counters: dict | None = None,
        notes: str = "",
    ) -> int:
        payload_json = _json_dumps(payload or {})
        checkpoint_json = _json_dumps(checkpoint or {})
        metrics_json = _json_dumps(metrics or {})
        counters = counters or {}
        started_at = _utc_now() if status == "in_progress" else None
        ended_at = _utc_now() if status in TERMINAL_WORK_UNIT_STATUSES else None
        with self.connect() as conn:
            existing = conn.execute(
                """
                SELECT id, started_at FROM work_units
                WHERE run_id = ? AND kind = ? AND source_unit_id = ?
                """,
                (run_id, kind, str(source_unit_id)),
            ).fetchone()
            if existing:
                started_at = existing["started_at"] or started_at
                if status not in TERMINAL_WORK_UNIT_STATUSES:
                    ended_at = None
                conn.execute(
                    """
                    UPDATE work_units
                    SET display_name = ?, ordering_index = ?, status = ?, payload_json = ?, checkpoint_json = ?,
                        metrics_json = ?,
                        family_key = ?, novelty_bucket = ?, domain_lane = ?, result_count = ?, candidates_discovered = ?,
                        candidates_enriched = ?, candidates_insufficient = ?, facial_yes_count = ?, facial_no_count = ?,
                        saves_count = ?, rejected_count = ?, notes = ?, started_at = ?, ended_at = ?
                    WHERE id = ?
                    """,
                    (
                        display_name,
                        ordering_index,
                        status,
                        payload_json,
                        checkpoint_json,
                        metrics_json,
                        family_key,
                        novelty_bucket,
                        domain_lane,
                        int(counters.get("result_count", 0)),
                        int(counters.get("candidates_discovered", 0)),
                        int(counters.get("candidates_enriched", 0)),
                        int(counters.get("candidates_insufficient", 0)),
                        int(counters.get("facial_yes_count", 0)),
                        int(counters.get("facial_no_count", 0)),
                        int(counters.get("saves_count", 0)),
                        int(counters.get("rejected_count", 0)),
                        notes,
                        started_at,
                        ended_at,
                        int(existing["id"]),
                    ),
                )
                return int(existing["id"])

            cursor = conn.execute(
                """
                INSERT INTO work_units(
                    run_id, source, brief_id, kind, source_unit_id, display_name, ordering_index, status,
                    payload_json, checkpoint_json, metrics_json, family_key, novelty_bucket, domain_lane, result_count,
                    candidates_discovered, candidates_enriched, candidates_insufficient, facial_yes_count,
                    facial_no_count, saves_count, rejected_count, notes, started_at, ended_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    source,
                    brief_id,
                    kind,
                    str(source_unit_id),
                    display_name,
                    ordering_index,
                    status,
                    payload_json,
                    checkpoint_json,
                    metrics_json,
                    family_key,
                    novelty_bucket,
                    domain_lane,
                    int(counters.get("result_count", 0)),
                    int(counters.get("candidates_discovered", 0)),
                    int(counters.get("candidates_enriched", 0)),
                    int(counters.get("candidates_insufficient", 0)),
                    int(counters.get("facial_yes_count", 0)),
                    int(counters.get("facial_no_count", 0)),
                    int(counters.get("saves_count", 0)),
                    int(counters.get("rejected_count", 0)),
                    notes,
                    started_at,
                    ended_at,
                ),
            )
            return int(cursor.lastrowid)

    def delete_missing_work_units(
        self,
        run_id: int,
        *,
        kind: str,
        keep_source_unit_ids: set[str],
    ) -> None:
        with self.connect() as conn:
            existing = conn.execute(
                "SELECT source_unit_id FROM work_units WHERE run_id = ? AND kind = ?",
                (run_id, kind),
            ).fetchall()
            for row in existing:
                if row["source_unit_id"] not in keep_source_unit_ids:
                    conn.execute(
                        "DELETE FROM work_units WHERE run_id = ? AND kind = ? AND source_unit_id = ?",
                        (run_id, kind, row["source_unit_id"]),
                    )

    def requeue_work_unit(self, run_id: int, *, kind: str, source_unit_id: str) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE work_units
                SET status = 'queued', checkpoint_json = '{}', started_at = NULL, ended_at = NULL
                WHERE run_id = ? AND kind = ? AND source_unit_id = ?
                """,
                (run_id, kind, str(source_unit_id)),
            )
            self._insert_event(
                conn,
                run_id=run_id,
                work_unit_id=self.get_work_unit_id(run_id, kind=kind, source_unit_id=source_unit_id),
                event_type="work_unit_requeued",
                payload={"kind": kind, "source_unit_id": str(source_unit_id)},
            )

    # ------------------------------------------------------------------
    # Candidate lifecycle
    # ------------------------------------------------------------------

    def list_terminal_identity_keys(self, *, source: str, brief_id: str) -> list[str]:
        placeholders = ",".join("?" for _ in DEDUP_BLOCKING_DECISIONS)
        with self.connect() as conn:
            rows = conn.execute(
                f"""
                SELECT identity_key
                FROM candidates
                WHERE source = ? AND brief_id = ?
                  AND (
                    current_lifecycle_state = 'failed_terminal'
                    OR terminal_decision IN ({placeholders})
                  )
                ORDER BY identity_key ASC
                """,
                (source, brief_id, *sorted(DEDUP_BLOCKING_DECISIONS)),
            ).fetchall()
            return [str(row["identity_key"]) for row in rows]

    def is_dedup_blocked(self, *, source: str, brief_id: str, identity_key: str) -> bool:
        placeholders = ",".join("?" for _ in DEDUP_BLOCKING_DECISIONS)
        with self.connect() as conn:
            row = conn.execute(
                f"""
                SELECT 1
                FROM candidates
                WHERE source = ? AND brief_id = ? AND identity_key = ?
                  AND (
                    current_lifecycle_state = 'failed_terminal'
                    OR terminal_decision IN ({placeholders})
                  )
                LIMIT 1
                """,
                (source, brief_id, identity_key, *sorted(DEDUP_BLOCKING_DECISIONS)),
            ).fetchone()
            return row is not None

    def ensure_candidate(
        self,
        *,
        source: str,
        brief_id: str,
        identity_key: str,
        display_name: str = "",
        profile_url: str = "",
        initial_state: str = "discovered",
    ) -> int:
        now = _utc_now()
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT id, display_name, profile_url, current_lifecycle_state
                FROM candidates
                WHERE source = ? AND brief_id = ? AND identity_key = ?
                """,
                (source, brief_id, identity_key),
            ).fetchone()
            if row:
                conn.execute(
                    """
                    UPDATE candidates
                    SET display_name = ?, profile_url = ?, last_seen_at = ?
                    WHERE id = ?
                    """,
                    (
                        display_name or row["display_name"],
                        profile_url or row["profile_url"],
                        now,
                        int(row["id"]),
                    ),
                )
                return int(row["id"])

            cursor = conn.execute(
                """
                INSERT INTO candidates(
                    source, brief_id, identity_key, display_name, profile_url,
                    current_lifecycle_state, terminal_decision, terminal_payload_json,
                    first_seen_at, last_seen_at
                )
                VALUES (?, ?, ?, ?, ?, ?, NULL, '{}', ?, ?)
                """,
                (
                    source,
                    brief_id,
                    identity_key,
                    display_name,
                    profile_url,
                    initial_state,
                    now,
                    now,
                ),
            )
            return int(cursor.lastrowid)

    def record_candidate_discovery(
        self,
        *,
        run_id: int,
        work_unit_id: int | None,
        source: str,
        brief_id: str,
        identity_key: str,
        display_name: str = "",
        profile_url: str = "",
        payload: dict | None = None,
    ) -> int:
        candidate_id = self.ensure_candidate(
            source=source,
            brief_id=brief_id,
            identity_key=identity_key,
            display_name=display_name,
            profile_url=profile_url,
            initial_state="discovered",
        )
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE candidates
                SET display_name = ?, profile_url = ?, current_lifecycle_state = 'discovered',
                    last_work_unit_id = ?, last_seen_at = ?
                WHERE id = ?
                """,
                (
                    display_name,
                    profile_url,
                    work_unit_id,
                    _utc_now(),
                    candidate_id,
                ),
            )
            self._insert_event(
                conn,
                run_id=run_id,
                work_unit_id=work_unit_id,
                candidate_id=candidate_id,
                event_type="candidate_discovered",
                payload=payload or {"identity_key": identity_key},
            )
        return candidate_id

    def get_candidate(self, *, source: str, brief_id: str, identity_key: str) -> dict | None:
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM candidates
                WHERE source = ? AND brief_id = ? AND identity_key = ?
                """,
                (source, brief_id, identity_key),
            ).fetchone()
            return _row_to_dict(row) if row else None

    def set_candidate_state(
        self,
        *,
        run_id: int | None,
        source: str,
        brief_id: str,
        identity_key: str,
        new_state: str,
        terminal_decision: str | None = None,
        terminal_payload: dict | None = None,
        last_work_unit_id: int | None = None,
    ) -> None:
        candidate = self.get_candidate(source=source, brief_id=brief_id, identity_key=identity_key)
        if not candidate:
            raise ValueError(f"candidate not found: {source}:{brief_id}:{identity_key}")
        _guard_transition(candidate["current_lifecycle_state"], new_state)
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE candidates
                SET current_lifecycle_state = ?, terminal_decision = ?, terminal_payload_json = ?,
                    last_work_unit_id = COALESCE(?, last_work_unit_id), last_seen_at = ?
                WHERE id = ?
                """,
                (
                    new_state,
                    terminal_decision,
                    _json_dumps(terminal_payload or {}),
                    last_work_unit_id,
                    _utc_now(),
                    candidate["id"],
                ),
            )
            self._insert_event(
                conn,
                run_id=run_id,
                work_unit_id=last_work_unit_id,
                candidate_id=int(candidate["id"]),
                event_type="candidate_state_transition",
                payload={
                    "from_state": candidate["current_lifecycle_state"],
                    "to_state": new_state,
                    "terminal_decision": terminal_decision,
                },
            )

    def mark_candidate_terminal_runtime(
        self,
        *,
        run_id: int | None,
        source: str,
        brief_id: str,
        identity_key: str,
        decision: str,
        payload: dict | None = None,
        last_work_unit_id: int | None = None,
    ) -> None:
        self.set_candidate_state(
            run_id=run_id,
            source=source,
            brief_id=brief_id,
            identity_key=identity_key,
            new_state="failed_terminal",
            terminal_decision=decision,
            terminal_payload=payload,
            last_work_unit_id=last_work_unit_id,
        )

    def clear_candidate_terminal_state(self, *, source: str, brief_id: str, identity_key: str) -> None:
        candidate = self.get_candidate(source=source, brief_id=brief_id, identity_key=identity_key)
        if not candidate:
            raise ValueError(f"candidate not found: {source}:{brief_id}:{identity_key}")
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE candidates
                SET terminal_decision = NULL,
                    terminal_payload_json = '{}',
                    current_lifecycle_state = CASE
                        WHEN current_lifecycle_state = 'failed_terminal' THEN 'failed_retryable'
                        ELSE current_lifecycle_state
                    END,
                    last_seen_at = ?
                WHERE id = ?
                """,
                (_utc_now(), int(candidate["id"])),
            )
            self._insert_event(
                conn,
                candidate_id=int(candidate["id"]),
                event_type="candidate_terminal_cleared",
                payload={"identity_key": identity_key},
            )

    # ------------------------------------------------------------------
    # Attempts
    # ------------------------------------------------------------------

    def start_attempt(
        self,
        *,
        run_id: int,
        source: str,
        brief_id: str,
        identity_key: str,
        stage: str,
        work_unit_id: int | None = None,
        batch_key: str | None = None,
        payload: dict | None = None,
        source_cursor: dict | None = None,
        display_name: str = "",
        profile_url: str = "",
    ) -> int:
        candidate_id = self.ensure_candidate(
            source=source,
            brief_id=brief_id,
            identity_key=identity_key,
            display_name=display_name,
            profile_url=profile_url,
        )
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT COALESCE(MAX(attempt_number), 0) AS max_attempt
                FROM candidate_attempts
                WHERE candidate_id = ? AND stage = ?
                """,
                (candidate_id, stage),
            ).fetchone()
            attempt_number = int(row["max_attempt"]) + 1
            cursor = conn.execute(
                """
                INSERT INTO candidate_attempts(
                    run_id, candidate_id, work_unit_id, stage, attempt_number, batch_key,
                    status, payload_json, source_cursor_json, started_at
                )
                VALUES (?, ?, ?, ?, ?, ?, 'started', ?, ?, ?)
                """,
                (
                    run_id,
                    candidate_id,
                    work_unit_id,
                    stage,
                    attempt_number,
                    batch_key,
                    _json_dumps(payload or {}),
                    _json_dumps(source_cursor or {}),
                    _utc_now(),
                ),
            )
            attempt_id = int(cursor.lastrowid)
            conn.execute(
                """
                UPDATE candidates
                SET last_attempt_id = ?, last_work_unit_id = COALESCE(?, last_work_unit_id), last_seen_at = ?
                WHERE id = ?
                """,
                (attempt_id, work_unit_id, _utc_now(), candidate_id),
            )
            self._insert_event(
                conn,
                run_id=run_id,
                work_unit_id=work_unit_id,
                candidate_id=candidate_id,
                attempt_id=attempt_id,
                event_type="attempt_started",
                payload={"stage": stage, "attempt_number": attempt_number},
            )
            return attempt_id

    def finish_attempt_success(
        self,
        *,
        attempt_id: int,
        new_state: str,
        terminal_decision: str | None = None,
        payload: dict | None = None,
        run_id: int | None = None,
    ) -> None:
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT ca.*, c.source, c.brief_id, c.identity_key, c.current_lifecycle_state
                FROM candidate_attempts ca
                JOIN candidates c ON c.id = ca.candidate_id
                WHERE ca.id = ?
                """,
                (attempt_id,),
            ).fetchone()
            if not row:
                raise ValueError(f"attempt not found: {attempt_id}")
            _guard_transition(row["current_lifecycle_state"], new_state)
            conn.execute(
                """
                UPDATE candidate_attempts
                SET status = 'succeeded', payload_json = ?, ended_at = ?
                WHERE id = ?
                """,
                (_json_dumps(payload or {}), _utc_now(), attempt_id),
            )
            conn.execute(
                """
                UPDATE candidates
                SET current_lifecycle_state = ?, terminal_decision = ?, terminal_payload_json = ?,
                    last_attempt_id = ?, last_work_unit_id = COALESCE(?, last_work_unit_id), last_seen_at = ?
                WHERE id = ?
                """,
                (
                    new_state,
                    terminal_decision,
                    _json_dumps(payload or {}),
                    attempt_id,
                    row["work_unit_id"],
                    _utc_now(),
                    row["candidate_id"],
                ),
            )
            self._insert_event(
                conn,
                run_id=run_id or row["run_id"],
                work_unit_id=row["work_unit_id"],
                candidate_id=row["candidate_id"],
                attempt_id=attempt_id,
                event_type="attempt_succeeded",
                payload={"stage": row["stage"], "new_state": new_state, "terminal_decision": terminal_decision},
            )

    def finish_attempt_failure(
        self,
        *,
        attempt_id: int,
        failure_kind: str,
        failure_reason: str,
        retryable: bool,
        payload: dict | None = None,
        run_id: int | None = None,
    ) -> None:
        new_state = "failed_retryable" if retryable else "failed_terminal"
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT ca.*, c.current_lifecycle_state
                FROM candidate_attempts ca
                JOIN candidates c ON c.id = ca.candidate_id
                WHERE ca.id = ?
                """,
                (attempt_id,),
            ).fetchone()
            if not row:
                raise ValueError(f"attempt not found: {attempt_id}")
            _guard_transition(row["current_lifecycle_state"], new_state)
            conn.execute(
                """
                UPDATE candidate_attempts
                SET status = 'failed', failure_kind = ?, failure_reason = ?, payload_json = ?, ended_at = ?
                WHERE id = ?
                """,
                (
                    failure_kind,
                    failure_reason,
                    _json_dumps(payload or {}),
                    _utc_now(),
                    attempt_id,
                ),
            )
            conn.execute(
                """
                UPDATE candidates
                SET current_lifecycle_state = ?, last_attempt_id = ?, last_work_unit_id = COALESCE(?, last_work_unit_id), last_seen_at = ?
                WHERE id = ?
                """,
                (
                    new_state,
                    attempt_id,
                    row["work_unit_id"],
                    _utc_now(),
                    row["candidate_id"],
                ),
            )
            self._insert_event(
                conn,
                run_id=run_id or row["run_id"],
                work_unit_id=row["work_unit_id"],
                candidate_id=row["candidate_id"],
                attempt_id=attempt_id,
                event_type="attempt_failed",
                payload={
                    "stage": row["stage"],
                    "new_state": new_state,
                    "failure_kind": failure_kind,
                    "failure_reason": failure_reason,
                },
            )

    def list_orphaned_attempts(self, *, source: str, brief_id: str) -> list[dict]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT ca.*, c.identity_key, c.source, c.brief_id
                FROM candidate_attempts ca
                JOIN candidates c ON c.id = ca.candidate_id
                WHERE ca.status = 'started' AND c.source = ? AND c.brief_id = ?
                ORDER BY ca.id ASC
                """,
                (source, brief_id),
            ).fetchall()
            return [_row_to_dict(row) for row in rows]

    def reconcile_open_attempts(self, *, source: str, brief_id: str) -> int:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT ca.id, ca.run_id, ca.work_unit_id, ca.stage, ca.candidate_id, c.current_lifecycle_state
                FROM candidate_attempts ca
                JOIN candidates c ON c.id = ca.candidate_id
                WHERE ca.status = 'started' AND c.source = ? AND c.brief_id = ?
                ORDER BY ca.id ASC
                """,
                (source, brief_id),
            ).fetchall()
            reconciled = 0
            for row in rows:
                current_state = row["current_lifecycle_state"]
                if current_state not in ("full_terminal", "failed_terminal"):
                    _guard_transition(current_state, "failed_retryable")
                    conn.execute(
                        """
                        UPDATE candidates
                        SET current_lifecycle_state = 'failed_retryable', last_attempt_id = ?, last_work_unit_id = COALESCE(?, last_work_unit_id), last_seen_at = ?
                        WHERE id = ?
                        """,
                        (
                            row["id"],
                            row["work_unit_id"],
                            _utc_now(),
                            row["candidate_id"],
                        ),
                    )
                conn.execute(
                    """
                    UPDATE candidate_attempts
                    SET status = 'reconciled',
                        failure_kind = COALESCE(failure_kind, 'orphaned_attempt'),
                        failure_reason = COALESCE(failure_reason, 'interrupted before attempt completion'),
                        ended_at = ?
                    WHERE id = ?
                    """,
                    (_utc_now(), row["id"]),
                )
                self._insert_event(
                    conn,
                    run_id=row["run_id"],
                    work_unit_id=row["work_unit_id"],
                    candidate_id=row["candidate_id"],
                    attempt_id=row["id"],
                    event_type="orphaned_attempt_reconciled",
                    payload={"stage": row["stage"]},
                )
                reconciled += 1
            return reconciled

    # ------------------------------------------------------------------
    # Candidate side effects
    # ------------------------------------------------------------------

    def begin_candidate_side_effect(
        self,
        *,
        run_id: int | None,
        source: str,
        brief_id: str,
        identity_key: str,
        attempt_id: int | None,
        effect_type: str,
        idempotency_key: str,
        payload: dict | None = None,
    ) -> dict:
        candidate = self.get_candidate(source=source, brief_id=brief_id, identity_key=identity_key)
        if not candidate:
            raise ValueError(f"candidate not found: {source}:{brief_id}:{identity_key}")
        now = _utc_now()
        with self.connect() as conn:
            existing = conn.execute(
                """
                SELECT *
                FROM side_effects
                WHERE candidate_id = ? AND effect_type = ? AND idempotency_key = ?
                """,
                (int(candidate["id"]), effect_type, idempotency_key),
            ).fetchone()
            if existing:
                existing_dict = _row_to_dict(existing)
                if existing["status"] == "invalidated":
                    conn.execute(
                        """
                        UPDATE side_effects
                        SET run_id = ?, attempt_id = ?, status = 'pending', payload_json = ?, updated_at = ?, invalidated_at = NULL
                        WHERE id = ?
                        """,
                        (
                            run_id,
                            attempt_id,
                            _json_dumps(payload or {}),
                            now,
                            int(existing["id"]),
                        ),
                    )
                    self._insert_event(
                        conn,
                        run_id=run_id,
                        candidate_id=int(candidate["id"]),
                        attempt_id=attempt_id,
                        event_type="side_effect_pending",
                        payload={
                            "effect_type": effect_type,
                            "idempotency_key": idempotency_key,
                            "replayed_from_invalidated": True,
                        },
                    )
                    existing_dict.update(
                        {
                            "run_id": run_id,
                            "attempt_id": attempt_id,
                            "status": "pending",
                            "payload_json": _json_dumps(payload or {}),
                            "updated_at": now,
                            "invalidated_at": None,
                        }
                    )
                    return {"should_execute": True, "side_effect": existing_dict}

                self._insert_event(
                    conn,
                    run_id=run_id,
                    candidate_id=int(candidate["id"]),
                    attempt_id=attempt_id,
                    event_type="side_effect_result",
                    payload={
                        "effect_type": effect_type,
                        "status": "skipped",
                        "idempotency_key": idempotency_key,
                        "skip_reason": f"existing_{existing['status']}",
                    },
                )
                return {"should_execute": False, "side_effect": _row_to_dict(existing)}

            cursor = conn.execute(
                """
                INSERT INTO side_effects(
                    run_id, candidate_id, attempt_id, effect_type, idempotency_key,
                    status, payload_json, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, 'pending', ?, ?, ?)
                """,
                (
                    run_id,
                    int(candidate["id"]),
                    attempt_id,
                    effect_type,
                    idempotency_key,
                    _json_dumps(payload or {}),
                    now,
                    now,
                ),
            )
            side_effect_id = int(cursor.lastrowid)
            self._insert_event(
                conn,
                run_id=run_id,
                candidate_id=int(candidate["id"]),
                attempt_id=attempt_id,
                event_type="side_effect_pending",
                payload={
                    "effect_type": effect_type,
                    "idempotency_key": idempotency_key,
                },
            )
            row = conn.execute("SELECT * FROM side_effects WHERE id = ?", (side_effect_id,)).fetchone()
            return {"should_execute": True, "side_effect": _row_to_dict(row)}

    def complete_candidate_side_effect(
        self,
        *,
        side_effect_id: int,
        status: str,
        payload: dict | None = None,
    ) -> None:
        if status not in SIDE_EFFECT_TERMINAL_STATUSES:
            raise ValueError(f"invalid side_effect status: {status}")
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM side_effects WHERE id = ?", (side_effect_id,)).fetchone()
            if not row:
                raise ValueError(f"side effect not found: {side_effect_id}")
            conn.execute(
                """
                UPDATE side_effects
                SET status = ?, payload_json = ?, updated_at = ?, invalidated_at = CASE
                    WHEN ? = 'invalidated' THEN ?
                    ELSE invalidated_at
                END
                WHERE id = ?
                """,
                (
                    status,
                    _json_dumps(payload or {}),
                    _utc_now(),
                    status,
                    _utc_now(),
                    side_effect_id,
                ),
            )
            self._insert_event(
                conn,
                run_id=row["run_id"],
                candidate_id=row["candidate_id"],
                attempt_id=row["attempt_id"],
                event_type="side_effect_result",
                payload={
                    "effect_type": row["effect_type"],
                    "status": status,
                    "idempotency_key": row["idempotency_key"],
                    **(payload or {}),
                },
            )

    def list_candidate_side_effects(
        self,
        *,
        source: str,
        brief_id: str,
        status: str | None = None,
        identity_key: str | None = None,
    ) -> list[dict]:
        sql = """
            SELECT se.*, c.identity_key, c.source, c.brief_id
            FROM side_effects se
            JOIN candidates c ON c.id = se.candidate_id
            WHERE c.source = ? AND c.brief_id = ?
        """
        params: list[Any] = [source, brief_id]
        if status is not None:
            sql += " AND se.status = ?"
            params.append(status)
        if identity_key is not None:
            sql += " AND c.identity_key = ?"
            params.append(identity_key)
        sql += " ORDER BY se.id ASC"
        with self.connect() as conn:
            rows = conn.execute(sql, params).fetchall()
            return [_row_to_dict(row) for row in rows]

    def reconcile_pending_side_effects(self, *, source: str, brief_id: str) -> int:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT se.*, c.identity_key
                FROM side_effects se
                JOIN candidates c ON c.id = se.candidate_id
                WHERE se.status = 'pending' AND c.source = ? AND c.brief_id = ?
                ORDER BY se.id ASC
                """,
                (source, brief_id),
            ).fetchall()
            reconciled = 0
            for row in rows:
                conn.execute(
                    """
                    UPDATE side_effects
                    SET status = 'failed',
                        payload_json = ?,
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        _json_dumps({"reason": "interrupted"}),
                        _utc_now(),
                        int(row["id"]),
                    ),
                )
                self._insert_event(
                    conn,
                    run_id=row["run_id"],
                    candidate_id=row["candidate_id"],
                    attempt_id=row["attempt_id"],
                    event_type="side_effect_result",
                    payload={
                        "effect_type": row["effect_type"],
                        "status": "failed",
                        "idempotency_key": row["idempotency_key"],
                        "reason": "interrupted",
                    },
                )
                reconciled += 1
            return reconciled

    def invalidate_candidate_side_effects(
        self,
        *,
        source: str,
        brief_id: str,
        identity_key: str,
        effect_type: str | None = None,
    ) -> int:
        candidate = self.get_candidate(source=source, brief_id=brief_id, identity_key=identity_key)
        if not candidate:
            return 0
        sql = """
            SELECT id, run_id, candidate_id, attempt_id, effect_type, idempotency_key
            FROM side_effects
            WHERE candidate_id = ?
              AND status != 'invalidated'
        """
        params: list[Any] = [int(candidate["id"])]
        if effect_type is not None:
            sql += " AND effect_type = ?"
            params.append(effect_type)
        with self.connect() as conn:
            rows = conn.execute(sql, params).fetchall()
            for row in rows:
                conn.execute(
                    """
                    UPDATE side_effects
                    SET status = 'invalidated', updated_at = ?, invalidated_at = ?
                    WHERE id = ?
                    """,
                    (_utc_now(), _utc_now(), int(row["id"])),
                )
                self._insert_event(
                    conn,
                    run_id=row["run_id"],
                    candidate_id=row["candidate_id"],
                    attempt_id=row["attempt_id"],
                    event_type="side_effect_result",
                    payload={
                        "effect_type": row["effect_type"],
                        "status": "invalidated",
                        "idempotency_key": row["idempotency_key"],
                    },
                )
            return len(rows)

    # ------------------------------------------------------------------
    # GitHub-specific helpers
    # ------------------------------------------------------------------

    def sync_github_progress(self, run_id: int, progress: GitHubProgress) -> None:
        run = self.get_run(run_id)
        if not run:
            raise ValueError(f"run not found: {run_id}")

        query_ids: set[str] = set()
        for index, query in enumerate(progress.queries):
            query_ids.add(str(query.id))
            self.upsert_work_unit(
                run_id=run_id,
                source="github",
                brief_id=run["brief_id"],
                kind=GITHUB_QUERY_KIND,
                source_unit_id=str(query.id),
                display_name=query.name,
                ordering_index=index,
                status=query.status,
                payload=query.to_dict(),
                checkpoint={"hit_result_cap": query.hit_result_cap},
                counters={
                    "result_count": query.result_count,
                    "candidates_discovered": query.candidates_discovered,
                    "saves_count": len(query.saves),
                },
                notes=query.notes,
            )
        self.delete_missing_work_units(run_id, kind=GITHUB_QUERY_KIND, keep_source_unit_ids=query_ids)

        seed_ids: set[str] = set()
        queued_usernames = {entry.get("username", "") for entry in progress.graph_expansion_queue if entry.get("username")}
        processed_usernames = set(progress.graph_expansion_processed or [])
        for index, username in enumerate(sorted(queued_usernames | processed_usernames)):
            if not username:
                continue
            seed_ids.add(username)
            entry = next((item for item in progress.graph_expansion_queue if item.get("username") == username), None) or {
                "username": username,
            }
            status = "done" if username in processed_usernames and username not in queued_usernames else "queued"
            self.upsert_work_unit(
                run_id=run_id,
                source="github",
                brief_id=run["brief_id"],
                kind=GITHUB_GRAPH_SEED_KIND,
                source_unit_id=username,
                display_name=f"Graph expansion seed: {username}",
                ordering_index=len(progress.queries) + index,
                status=status,
                payload=entry,
            )
        self.delete_missing_work_units(run_id, kind=GITHUB_GRAPH_SEED_KIND, keep_source_unit_ids=seed_ids)

        for username in progress.discovered_usernames:
            candidate_id = self.ensure_candidate(
                source="github",
                brief_id=run["brief_id"],
                identity_key=username,
                display_name=username,
                profile_url=f"https://github.com/{username}",
                initial_state="failed_terminal",
            )
            with self.connect() as conn:
                conn.execute(
                    """
                    UPDATE candidates
                    SET current_lifecycle_state = 'failed_terminal',
                        terminal_decision = COALESCE(terminal_decision, 'LEGACY_TERMINAL'),
                        terminal_payload_json = CASE
                            WHEN terminal_payload_json = '{}' THEN ?
                            ELSE terminal_payload_json
                        END,
                        last_seen_at = ?
                    WHERE id = ?
                    """,
                    (
                        _json_dumps({"username": username}),
                        _utc_now(),
                        candidate_id,
                    ),
                )

        self.update_run_resume_state(
            run_id,
            {
                "brief_name": progress.brief_name,
                "candidates_discovered": progress.candidates_discovered,
                "candidates_enriched": progress.candidates_enriched,
                "candidates_saved": progress.candidates_saved,
                "candidates_rejected": progress.candidates_rejected,
                "candidates_insufficient": progress.candidates_insufficient,
                "current_query_id": progress.current_query_id,
                "mined_repos": progress.mined_repos,
                "api_calls_made": progress.api_calls_made,
            },
        )

    def load_github_progress(self, run_id: int) -> GitHubProgress:
        run = self.get_run(run_id)
        if not run:
            raise ValueError(f"run not found: {run_id}")
        resume_state = _json_loads(run.get("resume_state_json"))
        query_rows = self.list_work_units(run_id, kind=GITHUB_QUERY_KIND)
        queries: list[GitHubSearchQuery] = []
        for row in query_rows:
            payload = _json_loads(row["payload_json"])
            query_id = _coerce_int(payload.get("id"), fallback=_coerce_int(row["source_unit_id"]))
            query_name = str(
                payload.get("name") or row["display_name"] or f"query-{query_id}"
            ).strip()
            query_text = str(
                payload.get("query")
                or payload.get("boolean")
                or payload.get("search_query")
                or query_name
            ).strip()
            channel = str(payload.get("channel") or "user_search").strip()
            payload.update(
                {
                    "id": query_id,
                    "name": query_name,
                    "query": query_text,
                    "channel": channel,
                    "status": row["status"],
                    "result_count": row["result_count"],
                    "candidates_discovered": row["candidates_discovered"],
                    "notes": row["notes"],
                    "hit_result_cap": _json_loads(row["checkpoint_json"]).get("hit_result_cap", payload.get("hit_result_cap", False)),
                }
            )
            queries.append(GitHubSearchQuery.from_dict(payload))

        graph_rows = self.list_work_units(run_id, kind=GITHUB_GRAPH_SEED_KIND)
        graph_queue = []
        graph_processed = []
        for row in graph_rows:
            payload = _json_loads(row["payload_json"])
            payload.setdefault("username", row["source_unit_id"])
            if row["status"] == "queued":
                graph_queue.append(payload)
            elif row["status"] == "done":
                graph_processed.append(row["source_unit_id"])

        return GitHubProgress(
            brief_name=resume_state.get("brief_name", run["brief_id"]),
            queries=queries,
            candidates_discovered=int(resume_state.get("candidates_discovered", 0)),
            candidates_enriched=int(resume_state.get("candidates_enriched", 0)),
            candidates_saved=int(resume_state.get("candidates_saved", 0)),
            candidates_rejected=int(resume_state.get("candidates_rejected", 0)),
            candidates_insufficient=int(resume_state.get("candidates_insufficient", 0)),
            current_query_id=resume_state.get("current_query_id"),
            discovered_usernames=self.list_terminal_identity_keys(source="github", brief_id=run["brief_id"]),
            mined_repos=list(resume_state.get("mined_repos", [])),
            api_calls_made=int(resume_state.get("api_calls_made", 0)),
            graph_expansion_queue=sorted(graph_queue, key=lambda item: item.get("confidence", 0), reverse=True),
            graph_expansion_processed=sorted(graph_processed),
        )

    def enqueue_graph_expansion_seed(
        self,
        *,
        run_id: int,
        username: str,
        reason: str,
        confidence: float,
        capability_area: str,
    ) -> None:
        run = self.get_run(run_id)
        if not run:
            raise ValueError(f"run not found: {run_id}")
        existing = self.get_work_unit_by_source_id(
            run_id,
            kind=GITHUB_GRAPH_SEED_KIND,
            source_unit_id=username,
        )
        payload = {
            "username": username,
            "reason": reason,
            "confidence": confidence,
            "capability_area": capability_area,
            "added_at": _utc_now(),
        }
        ordering_index = len(self.list_work_units(run_id, kind=GITHUB_QUERY_KIND)) + len(
            self.list_work_units(run_id, kind=GITHUB_GRAPH_SEED_KIND)
        )
        status = existing["status"] if existing and existing["status"] == "done" else "queued"
        self.upsert_work_unit(
            run_id=run_id,
            source="github",
            brief_id=run["brief_id"],
            kind=GITHUB_GRAPH_SEED_KIND,
            source_unit_id=username,
            display_name=f"Graph expansion seed: {username}",
            ordering_index=ordering_index,
            status=status,
            payload=payload,
        )

    def list_graph_expansion_seeds(self, run_id: int, *, status: str = "queued") -> list[dict]:
        seeds = self.list_work_units(run_id, kind=GITHUB_GRAPH_SEED_KIND)
        out = []
        for seed in seeds:
            if seed["status"] != status:
                continue
            payload = _json_loads(seed["payload_json"])
            payload.setdefault("username", seed["source_unit_id"])
            payload["_work_unit_id"] = seed["id"]
            out.append(payload)
        return out

    def mark_graph_expansion_seed_processed(self, run_id: int, username: str) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE work_units
                SET status = 'done', ended_at = ?
                WHERE run_id = ? AND kind = ? AND source_unit_id = ?
                """,
                (_utc_now(), run_id, GITHUB_GRAPH_SEED_KIND, username),
            )

    def get_github_blocked_usernames(self, brief_id: str, usernames: list[str]) -> set[str]:
        if not usernames:
            return set()
        placeholders = ",".join("?" for _ in usernames)
        decision_placeholders = ",".join("?" for _ in DEDUP_BLOCKING_DECISIONS)
        with self.connect() as conn:
            rows = conn.execute(
                f"""
                SELECT identity_key
                FROM candidates
                WHERE source = 'github' AND brief_id = ?
                  AND identity_key IN ({placeholders})
                  AND (
                    current_lifecycle_state = 'failed_terminal'
                    OR terminal_decision IN ({decision_placeholders})
                  )
                """,
                [brief_id, *usernames, *sorted(DEDUP_BLOCKING_DECISIONS)],
            ).fetchall()
            return {str(row["identity_key"]) for row in rows}

    def has_candidates(self, *, source: str, brief_id: str) -> bool:
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT 1
                FROM candidates
                WHERE source = ? AND brief_id = ?
                LIMIT 1
                """,
                (source, brief_id),
            ).fetchone()
            return row is not None

    def record_event(
        self,
        *,
        event_type: str,
        payload: dict | None = None,
        run_id: int | None = None,
        work_unit_id: int | None = None,
        candidate_id: int | None = None,
        attempt_id: int | None = None,
    ) -> None:
        with self.connect() as conn:
            self._insert_event(
                conn,
                event_type=event_type,
                payload=payload,
                run_id=run_id,
                work_unit_id=work_unit_id,
                candidate_id=candidate_id,
                attempt_id=attempt_id,
            )

    # ------------------------------------------------------------------
    # Events
    # ------------------------------------------------------------------

    def _insert_event(
        self,
        conn: sqlite3.Connection,
        *,
        event_type: str,
        payload: dict | None = None,
        run_id: int | None = None,
        work_unit_id: int | None = None,
        candidate_id: int | None = None,
        attempt_id: int | None = None,
    ) -> None:
        conn.execute(
            """
            INSERT INTO events(run_id, work_unit_id, candidate_id, attempt_id, event_type, payload_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                work_unit_id,
                candidate_id,
                attempt_id,
                event_type,
                _json_dumps(payload or {}),
                _utc_now(),
            ),
        )


def _guard_transition(current_state: str, new_state: str) -> None:
    if current_state == new_state:
        return
    allowed = ALLOWED_LIFECYCLE_TRANSITIONS.get(current_state)
    if allowed is None:
        raise ValueError(f"unknown lifecycle state: {current_state}")
    if new_state not in allowed:
        raise ValueError(f"invalid lifecycle transition: {current_state} -> {new_state}")


def _row_to_dict(row: sqlite3.Row | None) -> dict | None:
    if row is None:
        return None
    return {key: row[key] for key in row.keys()}


def _json_dumps(data: Any) -> str:
    if is_dataclass(data):
        data = asdict(data)
    return json.dumps(data or {}, sort_keys=True)


def _json_loads(raw: str | bytes | None) -> Any:
    if not raw:
        return {}
    return json.loads(raw)


def _coerce_int(value: Any, fallback: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
