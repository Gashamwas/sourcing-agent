"""Phase 2: read-only canonical-state primitives.

The store class (``shared.runtime_state.store.RuntimeStateStore``) is hostile
to read-only consumers: every instantiation runs DDL plus
``INSERT OR REPLACE INTO meta``. Surfaces that need to inspect canonical
state without mutating it (Cloris's status aggregator today; Run Review
and Authoring Loop tomorrow) cannot use the store directly.

This module is the answer. It provides pure-function read primitives that
each open the SQLite file in URI ``mode=ro`` so the read path is honestly
read-only — even if a caller passes the wrong path, the kernel refuses
the write.

Layering rule (per critique B4 in the design plan): this module must not
import ``shared.runtime_state.store``. The hard rule is enforced by
``tests/test_read_models_no_writer_import.py``. If you find yourself
wanting a ``RuntimeStateStore`` symbol here, port the helper you need
from store.py into a free function and call that.

Contract:

- Each primitive accepts a ``Path`` (and, where useful, a pre-opened
  ``sqlite3.Connection`` for forward-compatibility with future
  per-poll connection reuse, per critique B1).
- Missing-DB / corrupt-DB / WAL-not-yet-readable all collapse to
  ``None`` (or the sum-typed ``NotFound`` variant for primitives whose
  caller needs to disambiguate). This matches the existing aggregator
  contract that one bad state dir must not take down the whole status
  payload.
- Time comparisons parse ISO-8601 timestamps via
  ``datetime.fromisoformat`` (per critique B2). String comparison would
  silently miss rows whose format diverged from the writer's
  fixed-width emit.

"Should I bother starting?" lives elsewhere: the orchestrator's
``linkedin/session_orchestrator._resume_has_pending_work`` reads
``progress.json`` directly and stays put. That check fires before
``Pipeline(...)`` is constructed and therefore before any canonical
SQLite write — the canonical signal isn't there yet at that moment.
This module's :func:`has_pending_work` answers a different question
("what's the live state?") for callers that already have a populated
state dir.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, Literal


_LATEST_RUN_QUERY = (
    "SELECT id, source, brief_id, mode, status, stop_reason, started_at, ended_at, "
    "is_archived, intake_session_id "
    "FROM runs ORDER BY id DESC LIMIT 1"
)
# Phase 1C fallback: legacy DBs (pre-v6/v7 schemas) lack the brief-taxonomy
# columns. Catching the OperationalError and falling back lets the aggregator
# survive against unmigrated DBs in the field — the new fields collapse to
# their defaults (is_archived=0, intake_session_id=NULL).
_LATEST_RUN_QUERY_LEGACY = (
    "SELECT id, source, brief_id, mode, status, stop_reason, started_at, ended_at "
    "FROM runs ORDER BY id DESC LIMIT 1"
)
_RUN_BY_ID_QUERY = (
    "SELECT id, source, brief_id, output_dir, mode, status, stop_reason, "
    "started_at, ended_at, resumed_from_run_id, "
    "brief_path_at_launch, brief_content_hash, brief_snapshot_json "
    "FROM runs WHERE id = ?"
)
_PROGRESS_JSON_FILENAME = "progress.json"


# --- types ------------------------------------------------------------------


@dataclass(frozen=True)
class RunSummary:
    """A latest-run snapshot suitable for read-only surfaces.

    Mirrors the field set of ``cloris.models.RunSummary`` so the
    aggregator can copy fields across without further interpretation.
    The Pydantic model in cloris is the wire shape; this dataclass is
    the canonical-read shape — they should track each other.
    """

    id: int | None = None
    status: str | None = None
    stop_reason: str | None = None
    mode: str | None = None
    started_at: str | None = None
    ended_at: str | None = None
    # Phase 1C: brief-taxonomy fields. is_archived flips when the user
    # files away a brief (or the reconciler auto-archives a stale orphan).
    # intake_session_id is non-null when this run was launched out of the
    # onboarding authoring flow — the aggregator uses it to distinguish
    # "authored brief" from "filesystem state-dir artifact." Both default
    # safely on legacy DBs that don't have the columns yet.
    is_archived: bool = False
    intake_session_id: int | None = None


@dataclass(frozen=True)
class FailureKindCount:
    """One entry of an attempt-health failure-kind histogram."""

    kind: str
    count: int


@dataclass(frozen=True)
class AttemptHealth:
    """Recent attempt outcomes for a run, used to detect stalled runs.

    Phase 4 wires this into the aggregator: when ``last_success_age_s``
    is large and ``recent_failures`` is dominated by retryable
    HTTP-style failure_kinds, the run is "stalled" — alive but not
    making progress, typically because the provider is degraded.
    """

    total_attempts_in_window: int = 0
    succeeded_in_window: int = 0
    failed_in_window: int = 0
    last_success_age_s: float | None = None
    recent_failures: tuple[FailureKindCount, ...] = field(default_factory=tuple)
    dominant_failure_kind: str | None = None


@dataclass(frozen=True)
class RunDetail:
    """Phase B: full ``runs`` row needed by the run-report surface.

    Superset of :class:`RunSummary` adding identity columns
    (``brief_id``, ``output_dir``, ``brief_path_at_launch``,
    ``brief_content_hash``, ``brief_snapshot_json``,
    ``resumed_from_run_id``). The status aggregator uses ``RunSummary``
    because it only needs the latest-run snapshot; the per-run report
    needs the brief-identity fields too so it can render the role
    title, drift detection, and the resume-chain.
    """

    id: int | None = None
    source: str | None = None
    brief_id: str | None = None
    output_dir: str | None = None
    mode: str | None = None
    status: str | None = None
    stop_reason: str | None = None
    started_at: str | None = None
    ended_at: str | None = None
    resumed_from_run_id: int | None = None
    brief_path_at_launch: str | None = None
    brief_content_hash: str | None = None
    brief_snapshot_json: str | None = None


@dataclass(frozen=True)
class CandidateDecision:
    """Phase B: per-candidate terminal-decision row for the run report.

    Decisions live on the ``candidates`` row (``terminal_decision`` +
    ``terminal_payload_json``), not on per-run rows — a candidate's
    final outcome is brief-wide, not run-scoped. The run-scoping comes
    from joining through ``candidate_attempts`` to filter to candidates
    that had at least one attempt in this run.
    """

    candidate_id: int
    identity_key: str
    display_name: str
    profile_url: str
    terminal_decision: str | None
    confidence: float | None


@dataclass(frozen=True)
class CandidateNote:
    """Phase C, slice C3: one recruiter-authored note on a candidate.

    Notes are append-only — a candidate accumulates notes across review
    sessions and across runs. The schema stores them as a JSON array on
    ``candidates.notes``; this primitive parses the array into a tuple
    of frozen records so consumers don't have to re-parse the JSON.
    """

    body: str
    created_at: str


@dataclass(frozen=True)
class CandidateRecord:
    """Phase C: full ``candidates`` row needed by the candidate-detail surface.

    Superset of :class:`CandidateDecision` returning every field a detail
    view needs to render: source/brief identity, terminal payload (parsed
    via :func:`candidate_terminal_payload` for the save reason / confidence
    / any source-specific judgment fields), and timestamps. The terminal
    payload stays as a raw ``str`` here so the Pydantic layer above can
    decide which keys the wire surfaces.

    C3 fields: ``notes`` (parsed from the JSON column) and ``user_status``
    (recruiter-overridden status; ``None`` = use Cloris's judgment).

    Phase C-bis Slice 0.5 fields: ``judgment_accuracy`` (recruiter
    calibration signal — distinct from ``user_status``) and
    ``judgment_accuracy_at`` (timestamp the signal was set). NULLs by
    default so legacy rows pass through without touching either column.
    """

    candidate_id: int
    source: str
    brief_id: str
    identity_key: str
    display_name: str
    profile_url: str
    current_lifecycle_state: str
    terminal_decision: str | None
    terminal_payload_json: str
    first_seen_at: str
    last_seen_at: str
    notes: tuple[CandidateNote, ...] = field(default_factory=tuple)
    user_status: str | None = None
    judgment_accuracy: str | None = None
    judgment_accuracy_at: str | None = None


@dataclass(frozen=True)
class CandidateCardRecord:
    """Phase C, slice C2 (extended in C4): per-card row for the Workspace grid.

    Trimmed shape of :class:`CandidateRecord` — the Workspace surface
    only needs the fields that fit on a card. Save reason and confidence
    arrive parsed (the Pydantic layer doesn't have to re-parse the
    terminal_payload_json from the wire). ``last_seen_at`` drives the
    sort order and the "Last touched" stamp on each card. ``user_status``
    is the recruiter override ("shortlist" / "contacted" / etc.; ``None``
    means use Cloris's terminal_decision).
    """

    candidate_id: int
    identity_key: str
    display_name: str
    profile_url: str
    terminal_decision: str
    save_reason: str | None
    confidence: float | None
    last_seen_at: str
    first_seen_at: str
    user_status: str | None = None


@dataclass(frozen=True)
class WorkUnitProgress:
    """Tagged-union return for work-unit status counts.

    Per critique B3: "run doesn't exist" / "run exists but work_units
    empty" / "run has counts" are semantically distinct and callers
    must be able to disambiguate. ``kind`` discriminates; ``counts``
    is populated only when ``kind == "counts"``.
    """

    kind: Literal["not_found", "empty", "counts"]
    queued: int = 0
    in_progress: int = 0
    done: int = 0
    skipped: int = 0
    error: int = 0


@dataclass(frozen=True)
class TelemetryAttempt:
    """One ``candidate_attempts`` row needed by the run-telemetry surface.

    Mirrors the columns selected by :func:`run_telemetry` so the wire
    layer in ``cloris/api.py`` doesn't have to re-handle row-factory
    coercion. ``failure_kind`` / ``failure_reason`` / ``ended_at`` are
    None on still-running or in-flight attempts.
    """

    id: int
    candidate_id: int
    work_unit_id: int | None
    stage: str
    attempt_number: int
    status: str
    failure_kind: str | None
    failure_reason: str | None
    started_at: str
    ended_at: str | None


@dataclass(frozen=True)
class TelemetryEvent:
    """One ``events`` row needed by the run-telemetry surface.

    ``payload_json`` is the raw JSON string from the column. Callers
    that need a bounded display payload truncate at the wire layer
    (see ``cloris.api._truncate_payload_for_telemetry``); this read
    primitive returns the canonical raw string so callers stay in
    control of the redaction policy.
    """

    id: int
    event_type: str
    candidate_id: int | None
    attempt_id: int | None
    payload_json: str | None
    created_at: str


@dataclass(frozen=True)
class RunTelemetry:
    """Bounded windowed telemetry for one run: attempts + events + totals.

    The recent windows (``attempts``, ``events``) are bounded by the
    caller's ``attempts_limit`` / ``events_limit`` arguments. The
    ``*_total`` counts are unbounded — the wire layer surfaces them
    so the recruiter sees "showing 50 of 312 attempts" framing rather
    than guessing whether the window is the full history.

    A missing or unreadable DB collapses to empty windows + zero totals
    + ``last_event_at=None``, mirroring the existing aggregator
    contract that one bad state dir must not break the whole response.
    """

    attempts: tuple[TelemetryAttempt, ...] = field(default_factory=tuple)
    events: tuple[TelemetryEvent, ...] = field(default_factory=tuple)
    attempts_total: int = 0
    events_total: int = 0
    last_event_at: str | None = None


# --- shared connection helper -----------------------------------------------


@contextmanager
def _open_readonly(db_path: Path) -> Iterator[sqlite3.Connection | None]:
    """Yield a read-only connection or ``None`` if the file is missing
    or unreadable.

    Critique A3 caveat: a freshly-created DB whose ``-wal``/``-shm``
    files don't exist yet cannot be opened with ``mode=ro``. The
    resulting ``OperationalError`` is treated as "not yet readable" —
    indistinguishable from "missing" at this layer. Callers that need
    the distinction must check ``Path.exists`` themselves before
    invoking the read primitive.
    """

    if not db_path.exists():
        yield None
        return
    conn: sqlite3.Connection | None = None
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        yield conn
    except (sqlite3.OperationalError, sqlite3.DatabaseError):
        yield None
    finally:
        if conn is not None:
            conn.close()


# --- primitives -------------------------------------------------------------


def latest_run_summary(db_path: Path) -> RunSummary | None:
    """Return the latest ``runs`` row as :class:`RunSummary`, or ``None``.

    ``None`` collapses three cases: file missing, file corrupt/unreadable,
    and ``runs`` table empty. This matches the aggregator's existing
    semantics (one bad state dir must not break the whole response).
    """

    with _open_readonly(db_path) as conn:
        if conn is None:
            return None
        try:
            row = conn.execute(_LATEST_RUN_QUERY).fetchone()
        except sqlite3.OperationalError:
            # Legacy DB without is_archived / intake_session_id columns.
            # Fall back to the pre-v6 query; the new fields collapse to
            # their dataclass defaults so callers continue to work.
            try:
                row = conn.execute(_LATEST_RUN_QUERY_LEGACY).fetchone()
            except sqlite3.DatabaseError:
                return None
        except sqlite3.DatabaseError:
            return None
    if row is None:
        return None
    keys = row.keys()
    return RunSummary(
        id=row["id"] if "id" in keys else None,
        status=row["status"] if "status" in keys else None,
        stop_reason=row["stop_reason"] if "stop_reason" in keys else None,
        mode=row["mode"] if "mode" in keys else None,
        started_at=row["started_at"] if "started_at" in keys else None,
        ended_at=row["ended_at"] if "ended_at" in keys else None,
        is_archived=bool(row["is_archived"]) if "is_archived" in keys else False,
        intake_session_id=(
            row["intake_session_id"] if "intake_session_id" in keys else None
        ),
    )


def run_by_id(db_path: Path, *, run_id: int) -> RunDetail | None:
    """Return the ``runs`` row identified by ``run_id`` as :class:`RunDetail`.

    ``None`` collapses three cases: file missing, file corrupt/unreadable,
    and the run id is not present in the ``runs`` table. Brief-identity
    columns may be ``None`` for pre-Phase-3 schema rows; the read
    primitive falls back to a stripped query in that case so a legacy
    DB still yields a usable :class:`RunDetail`.
    """

    with _open_readonly(db_path) as conn:
        if conn is None:
            return None
        try:
            row = conn.execute(_RUN_BY_ID_QUERY, (run_id,)).fetchone()
        except (sqlite3.OperationalError, sqlite3.DatabaseError):
            # Brief-identity columns not present (legacy schema). Fall
            # back to the latest_run shape projected onto a RunDetail.
            try:
                row = conn.execute(
                    "SELECT id, source, brief_id, output_dir, mode, status, "
                    "stop_reason, started_at, ended_at, resumed_from_run_id, "
                    "NULL AS brief_path_at_launch, NULL AS brief_content_hash, "
                    "NULL AS brief_snapshot_json FROM runs WHERE id = ?",
                    (run_id,),
                ).fetchone()
            except (sqlite3.OperationalError, sqlite3.DatabaseError):
                return None
    if row is None:
        return None
    return RunDetail(
        id=row["id"],
        source=row["source"],
        brief_id=row["brief_id"],
        output_dir=row["output_dir"] if "output_dir" in row.keys() else None,
        mode=row["mode"],
        status=row["status"],
        stop_reason=row["stop_reason"],
        started_at=row["started_at"],
        ended_at=row["ended_at"],
        resumed_from_run_id=row["resumed_from_run_id"]
        if "resumed_from_run_id" in row.keys()
        else None,
        brief_path_at_launch=row["brief_path_at_launch"]
        if "brief_path_at_launch" in row.keys()
        else None,
        brief_content_hash=row["brief_content_hash"]
        if "brief_content_hash" in row.keys()
        else None,
        brief_snapshot_json=row["brief_snapshot_json"]
        if "brief_snapshot_json" in row.keys()
        else None,
    )


def run_decisions(
    db_path: Path,
    *,
    run_id: int,
    limit: int = 200,
) -> tuple[CandidateDecision, ...]:
    """Return up to ``limit`` candidates that had attempts in ``run_id``.

    Joins ``candidate_attempts`` to ``candidates`` so the run-report
    surface lists who Cloris touched in this run. Each candidate's
    ``terminal_decision`` is the brief-wide outcome (a candidate's
    final decision can be set in a later run for the same brief), but
    that's the right value to surface — recruiters care about the
    final state, not the intermediate one.

    Confidence parses safely from ``terminal_payload_json``; malformed
    JSON or missing ``confidence`` keys collapse to ``None``.

    Empty tuple when DB is missing/corrupt or no attempts exist for
    this run.
    """

    with _open_readonly(db_path) as conn:
        if conn is None:
            return tuple()
        try:
            rows = conn.execute(
                "SELECT DISTINCT c.id, c.identity_key, c.display_name, "
                "c.profile_url, c.terminal_decision, c.terminal_payload_json, "
                "c.last_seen_at "
                "FROM candidates c "
                "JOIN candidate_attempts ca ON ca.candidate_id = c.id "
                "WHERE ca.run_id = ? "
                "ORDER BY c.last_seen_at DESC, c.id DESC "
                "LIMIT ?",
                (run_id, limit),
            ).fetchall()
        except (sqlite3.OperationalError, sqlite3.DatabaseError):
            return tuple()

    decisions: list[CandidateDecision] = []
    for row in rows:
        confidence: float | None = None
        payload_raw = row["terminal_payload_json"]
        if isinstance(payload_raw, str) and payload_raw and payload_raw != "{}":
            try:
                payload = json.loads(payload_raw)
                value = payload.get("confidence")
                if isinstance(value, (int, float)):
                    confidence = float(value)
            except (json.JSONDecodeError, TypeError, AttributeError):
                confidence = None
        decisions.append(
            CandidateDecision(
                candidate_id=row["id"],
                identity_key=row["identity_key"] or "",
                display_name=row["display_name"] or "",
                profile_url=row["profile_url"] or "",
                terminal_decision=row["terminal_decision"],
                confidence=confidence,
            )
        )
    return tuple(decisions)


def candidate_by_id(
    db_path: Path, *, candidate_id: int
) -> CandidateRecord | None:
    """Return a single candidate row by its primary-key id.

    Phase C primitive used by the candidate-detail surface. ``None``
    collapses three cases: file missing, file corrupt/unreadable, and
    the candidate id is not present in the ``candidates`` table.
    Source-agnostic — the row carries its own ``source`` and ``brief_id``.
    """

    with _open_readonly(db_path) as conn:
        if conn is None:
            return None
        # v8 fields (`notes`, `user_status`) and v9 fields
        # (`judgment_accuracy`, `judgment_accuracy_at`) are gated behind
        # their respective migrations. Try the v9 query first, fall back
        # to the v8 query, then to the v7 stripped query for legacy DBs
        # that haven't migrated yet. Each cascade adds NULL aliases so
        # the row dict shape stays stable above the SELECT.
        try:
            row = conn.execute(
                "SELECT id, source, brief_id, identity_key, display_name, "
                "profile_url, current_lifecycle_state, terminal_decision, "
                "terminal_payload_json, first_seen_at, last_seen_at, "
                "notes, user_status, judgment_accuracy, judgment_accuracy_at "
                "FROM candidates WHERE id = ?",
                (candidate_id,),
            ).fetchone()
        except (sqlite3.OperationalError, sqlite3.DatabaseError):
            try:
                row = conn.execute(
                    "SELECT id, source, brief_id, identity_key, display_name, "
                    "profile_url, current_lifecycle_state, terminal_decision, "
                    "terminal_payload_json, first_seen_at, last_seen_at, "
                    "notes, user_status, NULL AS judgment_accuracy, "
                    "NULL AS judgment_accuracy_at "
                    "FROM candidates WHERE id = ?",
                    (candidate_id,),
                ).fetchone()
            except (sqlite3.OperationalError, sqlite3.DatabaseError):
                try:
                    row = conn.execute(
                        "SELECT id, source, brief_id, identity_key, display_name, "
                        "profile_url, current_lifecycle_state, terminal_decision, "
                        "terminal_payload_json, first_seen_at, last_seen_at, "
                        "'[]' AS notes, NULL AS user_status, "
                        "NULL AS judgment_accuracy, NULL AS judgment_accuracy_at "
                        "FROM candidates WHERE id = ?",
                        (candidate_id,),
                    ).fetchone()
                except (sqlite3.OperationalError, sqlite3.DatabaseError):
                    return None
    if row is None:
        return None

    notes_raw = row["notes"] if "notes" in row.keys() else "[]"
    notes_parsed: list[CandidateNote] = []
    if isinstance(notes_raw, str) and notes_raw and notes_raw != "[]":
        try:
            entries = json.loads(notes_raw)
        except (json.JSONDecodeError, TypeError):
            entries = []
        if isinstance(entries, list):
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                body = entry.get("body")
                created_at = entry.get("created_at")
                if isinstance(body, str) and isinstance(created_at, str):
                    notes_parsed.append(
                        CandidateNote(body=body, created_at=created_at)
                    )

    user_status_raw = row["user_status"] if "user_status" in row.keys() else None
    judgment_accuracy_raw = (
        row["judgment_accuracy"] if "judgment_accuracy" in row.keys() else None
    )
    judgment_accuracy_at_raw = (
        row["judgment_accuracy_at"]
        if "judgment_accuracy_at" in row.keys()
        else None
    )

    return CandidateRecord(
        candidate_id=row["id"],
        source=row["source"] or "",
        brief_id=row["brief_id"] or "",
        identity_key=row["identity_key"] or "",
        display_name=row["display_name"] or "",
        profile_url=row["profile_url"] or "",
        current_lifecycle_state=row["current_lifecycle_state"] or "",
        terminal_decision=row["terminal_decision"],
        terminal_payload_json=row["terminal_payload_json"] or "{}",
        first_seen_at=row["first_seen_at"] or "",
        last_seen_at=row["last_seen_at"] or "",
        notes=tuple(notes_parsed),
        user_status=user_status_raw if isinstance(user_status_raw, str) and user_status_raw else None,
        judgment_accuracy=(
            judgment_accuracy_raw
            if isinstance(judgment_accuracy_raw, str) and judgment_accuracy_raw
            else None
        ),
        judgment_accuracy_at=(
            judgment_accuracy_at_raw
            if isinstance(judgment_accuracy_at_raw, str) and judgment_accuracy_at_raw
            else None
        ),
    )


def candidate_recent_run_id(
    db_path: Path, *, candidate_id: int
) -> int | None:
    """Return the most-recent ``run_id`` that had an attempt on this candidate.

    The candidate-detail page renders a back-link to "the run where Cloris
    found this person." A candidate may have attempts across multiple runs
    (judgement re-runs, retries); the highest run_id wins. ``None`` when
    there are no attempts (the candidate exists but has never been touched
    by any run — uncommon but possible for legacy/imported rows).
    """

    with _open_readonly(db_path) as conn:
        if conn is None:
            return None
        try:
            row = conn.execute(
                "SELECT MAX(run_id) AS run_id FROM candidate_attempts "
                "WHERE candidate_id = ?",
                (candidate_id,),
            ).fetchone()
        except (sqlite3.OperationalError, sqlite3.DatabaseError):
            return None
    if row is None or row["run_id"] is None:
        return None
    return int(row["run_id"])


def brief_saves(
    db_path: Path,
    *,
    source: str,
    brief_id: str,
    limit: int = 200,
) -> tuple[CandidateCardRecord, ...]:
    """Return all SAVE-class candidates for ``(source, brief_id)``.

    The Workspace surface aggregates saves *across all runs* of a brief,
    not just the latest run, so the join goes against ``candidates``
    directly rather than through ``candidate_attempts``. The terminal
    decision must be in the ``SAVE`` family (the orchestrator writes
    SAVE / INFERENTIAL_SAVE / TRANSFERABLE_SAVE / SIGNAL_SAVE for
    different judgment shapes — all are recruiter-actionable).

    Save reason and confidence are parsed safely from
    ``terminal_payload_json``; malformed JSON or missing keys collapse
    to ``None`` per :func:`candidate_terminal_payload`.

    Empty tuple when DB is missing / corrupt or no saves exist for
    this brief.
    """

    save_decisions = (
        "SAVE",
        "INFERENTIAL_SAVE",
        "TRANSFERABLE_SAVE",
        "SIGNAL_SAVE",
    )
    placeholders = ",".join("?" for _ in save_decisions)

    with _open_readonly(db_path) as conn:
        if conn is None:
            return tuple()
        # C4 extends the projection with `user_status`. Fall back to the
        # legacy projection on a v7-or-earlier DB where the column is
        # missing — the value collapses to NULL for those rows.
        try:
            rows = conn.execute(
                f"SELECT id, identity_key, display_name, profile_url, "
                f"terminal_decision, terminal_payload_json, "
                f"first_seen_at, last_seen_at, user_status "
                f"FROM candidates "
                f"WHERE source = ? AND brief_id = ? "
                f"  AND terminal_decision IN ({placeholders}) "
                f"  AND (current_lifecycle_state IS NULL OR current_lifecycle_state NOT LIKE 'failed_%') "
                f"ORDER BY last_seen_at DESC, id DESC "
                f"LIMIT ?",
                (source, brief_id, *save_decisions, limit),
            ).fetchall()
        except (sqlite3.OperationalError, sqlite3.DatabaseError):
            try:
                rows = conn.execute(
                    f"SELECT id, identity_key, display_name, profile_url, "
                    f"terminal_decision, terminal_payload_json, "
                    f"first_seen_at, last_seen_at, NULL AS user_status "
                    f"FROM candidates "
                    f"WHERE source = ? AND brief_id = ? "
                    f"  AND terminal_decision IN ({placeholders}) "
                    f"ORDER BY last_seen_at DESC, id DESC "
                    f"LIMIT ?",
                    (source, brief_id, *save_decisions, limit),
                ).fetchall()
            except (sqlite3.OperationalError, sqlite3.DatabaseError):
                return tuple()

    cards: list[CandidateCardRecord] = []
    for row in rows:
        payload = candidate_terminal_payload(row["terminal_payload_json"] or "{}")
        save_reason, confidence = extract_save_reason_and_confidence(payload)
        user_status_raw = row["user_status"] if "user_status" in row.keys() else None
        cards.append(
            CandidateCardRecord(
                candidate_id=row["id"],
                identity_key=row["identity_key"] or "",
                display_name=row["display_name"] or "",
                profile_url=row["profile_url"] or "",
                terminal_decision=row["terminal_decision"] or "SAVE",
                save_reason=save_reason,
                confidence=confidence,
                last_seen_at=row["last_seen_at"] or "",
                first_seen_at=row["first_seen_at"] or "",
                user_status=user_status_raw if isinstance(user_status_raw, str) and user_status_raw else None,
            )
        )
    return tuple(cards)


def latest_run_in_state_dir(db_path: Path) -> int | None:
    """Return the id of the most-recent run in this state dir's DB.

    Used by the Workspace aggregator to find the latest_run_id for the
    "View latest run report" link, plus to pick a brief_id when the URL
    only carries (source, state_key). ``None`` if the DB is missing /
    corrupt / has no runs.
    """

    with _open_readonly(db_path) as conn:
        if conn is None:
            return None
        try:
            row = conn.execute(
                "SELECT id FROM runs ORDER BY id DESC LIMIT 1"
            ).fetchone()
        except (sqlite3.OperationalError, sqlite3.DatabaseError):
            return None
    if row is None:
        return None
    return int(row["id"])


def candidate_terminal_payload(
    terminal_payload_json: str,
) -> dict | None:
    """Parse ``candidates.terminal_payload_json`` into a dict, safely.

    Returns ``None`` for empty / ``"{}"`` / malformed inputs so callers
    can ``if payload is None: skip`` rather than threading try/except.
    Save reason, confidence, and any source-specific judgment fields
    (e.g. linkedin's ``judgment_reason``) live in this blob; the wire
    surface decides which keys to publish.
    """

    if not terminal_payload_json or terminal_payload_json == "{}":
        return None
    try:
        parsed = json.loads(terminal_payload_json)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(parsed, dict):
        return None
    return parsed


def extract_save_reason_and_confidence(
    payload: dict | None,
) -> tuple[str | None, float | None]:
    """Extract recruiter-facing save reason + confidence from a parsed
    ``terminal_payload``, with provenance-aware priority.

    The substrate writes the orchestrator's full-stage judgment under
    ``payload["full_decision"]["rationale"]`` (and
    ``...["confidence"]``) — that's where the deep-eval payload
    lands when a candidate clears facial triage. The trial-walk audit
    (``docs/cloris-trial-walk-day1.md``) confirmed 114/114 SAVE-class
    candidates carry substantive rationale at that path. The earlier
    wiring at ``cloris/control_plane.py`` and at ``brief_saves``
    below read only top-level ``save_reason`` / ``reason`` keys —
    keys the orchestrator does not write — so every saved candidate
    surfaced ``save_reason=null`` on the wire and the candidate-detail
    + workspace surfaces dutifully rendered the "No save reason
    recorded" fallback on every save.

    Priority on read:

    - reason text: ``full_decision.rationale`` →
      ``save_reason`` (top-level) → ``reason`` (top-level legacy).
    - confidence: ``full_decision.confidence`` →
      ``confidence`` (top-level legacy).

    The top-level fallbacks preserve compatibility with any older /
    test-built payload that wrote at the top level (a few projection
    test fixtures and historical paths did so).

    Returns ``(None, None)`` for ``payload is None`` or for any
    missing / malformed values. Callers that want a ``"No save
    reason recorded"`` fallback at the surface layer should treat
    ``None`` as the trigger — the substrate now passes through
    truthful judgment whenever it exists.
    """

    if payload is None:
        return (None, None)

    save_reason: str | None = None
    confidence: float | None = None

    full_decision = payload.get("full_decision")
    if isinstance(full_decision, dict):
        candidate_text = full_decision.get("rationale")
        if isinstance(candidate_text, str) and candidate_text.strip():
            save_reason = candidate_text.strip()
        raw_conf = full_decision.get("confidence")
        if isinstance(raw_conf, (int, float)):
            confidence = float(raw_conf)

    if save_reason is None:
        for key in ("save_reason", "reason"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                save_reason = value.strip()
                break

    if confidence is None:
        raw_conf = payload.get("confidence")
        if isinstance(raw_conf, (int, float)):
            confidence = float(raw_conf)

    return (save_reason, confidence)


def has_pending_work(state_dir: Path) -> bool | None:
    """Return whether a LinkedIn run has queued or in-progress work.

    Reads ``progress.json`` directly — the same projection
    ``linkedin/session_orchestrator._resume_has_pending_work`` uses.
    The two diverge intentionally on missing/malformed inputs:

    - This function (passive read model): missing/malformed ⇒ ``None``
      (unknown). The aggregator surfaces "unknown" as null in the wire
      payload; the UI renders no resume affordance.
    - The orchestrator (active worker): missing/malformed ⇒ ``True``
      (attempt resume). That bias is correct for an active worker but
      wrong for a passive observer — see ``cloris.control_plane`` for
      the documented rationale.

    GitHub state dirs have no analogous projection; callers should
    check ``source == "linkedin"`` before invoking this helper.
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


def attempt_health(
    db_path: Path,
    *,
    run_id: int,
    window_minutes: int = 5,
) -> AttemptHealth:
    """Summarize recent ``candidate_attempts`` outcomes for ``run_id``.

    The window is "rows whose started_at is within the last
    ``window_minutes`` minutes." String-comparison on ISO-8601 would
    work for the canonical fixed-width format the writer emits, but
    we parse via ``datetime.fromisoformat`` to be robust to format
    drift — per critique B2.

    Returns an empty :class:`AttemptHealth` rather than ``None`` when
    the DB is missing/corrupt or the run has no attempts; that keeps
    the consuming aggregator simple (no Optional unwrapping at the
    call site).
    """

    empty = AttemptHealth()
    with _open_readonly(db_path) as conn:
        if conn is None:
            return empty
        try:
            rows = conn.execute(
                "SELECT status, failure_kind, started_at, ended_at "
                "FROM candidate_attempts WHERE run_id = ?",
                (run_id,),
            ).fetchall()
        except sqlite3.DatabaseError:
            return empty

    cutoff = datetime.now(timezone.utc).timestamp() - window_minutes * 60.0
    in_window: list[sqlite3.Row] = []
    last_success_at: float | None = None

    for row in rows:
        started = _parse_iso_to_epoch(row["started_at"])
        if started is None:
            continue
        if row["status"] == "succeeded":
            ended = _parse_iso_to_epoch(row["ended_at"]) or started
            if last_success_at is None or ended > last_success_at:
                last_success_at = ended
        if started >= cutoff:
            in_window.append(row)

    failure_kinds: dict[str, int] = {}
    succeeded = 0
    failed = 0
    for row in in_window:
        if row["status"] == "succeeded":
            succeeded += 1
        else:
            failed += 1
            kind = row["failure_kind"] or "unknown"
            failure_kinds[kind] = failure_kinds.get(kind, 0) + 1

    if last_success_at is None:
        last_success_age_s: float | None = None
    else:
        last_success_age_s = max(
            0.0, datetime.now(timezone.utc).timestamp() - last_success_at
        )

    histogram = tuple(
        FailureKindCount(kind=kind, count=count)
        for kind, count in sorted(
            failure_kinds.items(), key=lambda kv: (-kv[1], kv[0])
        )
    )
    dominant = histogram[0].kind if histogram else None

    return AttemptHealth(
        total_attempts_in_window=len(in_window),
        succeeded_in_window=succeeded,
        failed_in_window=failed,
        last_success_age_s=last_success_age_s,
        recent_failures=histogram,
        dominant_failure_kind=dominant,
    )


def work_unit_progress(
    db_path: Path,
    *,
    run_id: int,
    kind: str,
) -> WorkUnitProgress:
    """Return queued/in_progress/done/skipped/error counts for ``run_id``.

    Three-state result discriminated by ``kind``:

    - ``"not_found"``: no run exists with this id (or DB is missing/corrupt).
    - ``"empty"``: run exists but has no work_units of the given kind.
    - ``"counts"``: at least one row; counts are populated.
    """

    with _open_readonly(db_path) as conn:
        if conn is None:
            return WorkUnitProgress(kind="not_found")
        try:
            run_row = conn.execute(
                "SELECT id FROM runs WHERE id = ?", (run_id,)
            ).fetchone()
            if run_row is None:
                return WorkUnitProgress(kind="not_found")
            rows = conn.execute(
                "SELECT status, COUNT(*) as n FROM work_units "
                "WHERE run_id = ? AND kind = ? GROUP BY status",
                (run_id, kind),
            ).fetchall()
        except sqlite3.DatabaseError:
            return WorkUnitProgress(kind="not_found")

    if not rows:
        return WorkUnitProgress(kind="empty")

    counts = {"queued": 0, "in_progress": 0, "done": 0, "skipped": 0, "error": 0}
    for row in rows:
        counts[row["status"]] = counts.get(row["status"], 0) + int(row["n"])
    return WorkUnitProgress(
        kind="counts",
        queued=counts["queued"],
        in_progress=counts["in_progress"],
        done=counts["done"],
        skipped=counts["skipped"],
        error=counts["error"],
    )


def _parse_state_json_column(value: object) -> dict:
    """Parse a ``state_json`` TEXT column into a dict, defensively.

    Shared by the intake-session and reflection-session read helpers
    below. Mirrors the parsing posture of the writer-side helpers
    (:func:`cloris.intake_sessions._row_to_session` and
    :func:`shared.runtime_state.reflection._row_to_session`):

    - NULL / empty / non-string column -> ``{}``
    - non-JSON string -> ``{}``
    - parsed-but-non-dict JSON (e.g. legacy row writing a list) -> ``{}``

    The wire model never has to handle the missing/malformed case.

    Inlined here rather than imported from the writer-side modules
    because both ``cloris.intake_sessions`` and
    ``shared.runtime_state.reflection`` import :class:`RuntimeStateStore`
    at module load time, and the read_models layering rule forbids that
    transitive coupling (see module docstring + the AST-walk pin in
    ``tests/test_read_models.py``).
    """

    if not isinstance(value, str) or not value:
        return {}
    try:
        parsed = json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return {}
    if not isinstance(parsed, dict):
        return {}
    return parsed


def list_intake_sessions(db_path: Path) -> list[dict]:
    """Read-only counterpart to
    :func:`cloris.intake_sessions.list_intake_sessions`.

    Returns active (non-archived) sessions in the same dict shape so the
    GET endpoint can swap the writer-instantiated read for this helper
    without changing the wire payload. Newest first by ``updated_at``.

    Missing-DB / corrupt-DB collapses to an empty list, matching the
    aggregator pattern.
    """

    with _open_readonly(db_path) as conn:
        if conn is None:
            return []
        try:
            rows = conn.execute(
                """
                SELECT id, brief_id_draft, role_title, current_step,
                       state_json, started_at, updated_at, completed_at,
                       archived_at
                FROM intake_sessions
                WHERE archived_at IS NULL
                ORDER BY updated_at DESC
                """
            ).fetchall()
        except sqlite3.DatabaseError:
            return []
    return [
        {
            "id": row["id"],
            "brief_id_draft": row["brief_id_draft"],
            "role_title": row["role_title"],
            "current_step": row["current_step"],
            "state_json": _parse_state_json_column(row["state_json"]),
            "started_at": row["started_at"],
            "updated_at": row["updated_at"],
            "completed_at": row["completed_at"],
            "archived_at": row["archived_at"],
        }
        for row in rows
    ]


def get_intake_session(db_path: Path, *, session_id: int) -> dict | None:
    """Read-only counterpart to
    :func:`cloris.intake_sessions.get_intake_session`.

    Returns the session dict regardless of archived state — the GET
    endpoint is used for direct deep-links and resume flows where a
    recruiter may want to inspect or unarchive an old session.

    Missing-DB / corrupt-DB / unknown id all collapse to ``None``.
    """

    with _open_readonly(db_path) as conn:
        if conn is None:
            return None
        try:
            row = conn.execute(
                """
                SELECT id, brief_id_draft, role_title, current_step,
                       state_json, started_at, updated_at, completed_at,
                       archived_at
                FROM intake_sessions WHERE id = ?
                """,
                (session_id,),
            ).fetchone()
        except sqlite3.DatabaseError:
            return None
    if row is None:
        return None
    return {
        "id": row["id"],
        "brief_id_draft": row["brief_id_draft"],
        "role_title": row["role_title"],
        "current_step": row["current_step"],
        "state_json": _parse_state_json_column(row["state_json"]),
        "started_at": row["started_at"],
        "updated_at": row["updated_at"],
        "completed_at": row["completed_at"],
        "archived_at": row["archived_at"],
    }


def _row_to_reflection_session(row: object) -> dict:
    """Project a reflection_sessions row into the wire dict shape.

    Mirrors :func:`shared.runtime_state.reflection._row_to_session`
    column-for-column. Inlined for the same layering reason as
    :func:`_parse_state_json_column` above.
    """

    return {
        "id": row["id"],
        "brief_id": row["brief_id"],
        "source_run_id": row["source_run_id"],
        "current_phase": row["current_phase"],
        "state_json": _parse_state_json_column(row["state_json"]),
        "steering_iterations": row["steering_iterations"],
        "started_at": row["started_at"],
        "updated_at": row["updated_at"],
        "completed_at": row["completed_at"],
        "discarded_at": row["discarded_at"],
        "brief_version_committed": row["brief_version_committed"],
        "research_error": row["research_error"],
    }


def get_reflection_session(
    db_path: Path, *, session_id: int
) -> dict | None:
    """Read-only counterpart to
    :func:`shared.runtime_state.reflection.get_reflection_session`.

    Returns the session row regardless of completed/discarded state —
    the GET endpoint serves both in-flight resume and post-mortem
    inspection. The reflection GET endpoint is documented as
    polled at 2-3s intervals during research; routing it through this
    read helper means each poll no longer rewrites the schema_version
    meta row.
    """

    with _open_readonly(db_path) as conn:
        if conn is None:
            return None
        try:
            row = conn.execute(
                """
                SELECT id, brief_id, source_run_id, current_phase, state_json,
                       steering_iterations, started_at, updated_at,
                       completed_at, discarded_at, brief_version_committed,
                       research_error
                FROM reflection_sessions WHERE id = ?
                """,
                (session_id,),
            ).fetchone()
        except sqlite3.DatabaseError:
            return None
    if row is None:
        return None
    return _row_to_reflection_session(row)


def get_active_reflection_for_brief(
    db_path: Path, *, brief_id: str
) -> dict | None:
    """Read-only counterpart to
    :func:`shared.runtime_state.reflection.get_active_reflection_for_brief`.

    Active means ``completed_at IS NULL AND discarded_at IS NULL``.
    Returns the most recently updated active row, or ``None``.
    """

    with _open_readonly(db_path) as conn:
        if conn is None:
            return None
        try:
            row = conn.execute(
                """
                SELECT id, brief_id, source_run_id, current_phase, state_json,
                       steering_iterations, started_at, updated_at,
                       completed_at, discarded_at, brief_version_committed,
                       research_error
                FROM reflection_sessions
                WHERE brief_id = ?
                  AND completed_at IS NULL
                  AND discarded_at IS NULL
                ORDER BY updated_at DESC
                LIMIT 1
                """,
                (brief_id,),
            ).fetchone()
        except sqlite3.DatabaseError:
            return None
    if row is None:
        return None
    return _row_to_reflection_session(row)


def run_telemetry(
    db_path: Path,
    *,
    run_id: int,
    attempts_limit: int,
    events_limit: int,
) -> RunTelemetry:
    """Bounded operational-telemetry view for one run, opened read-only.

    Replaces the writer-instantiated read path in
    ``cloris.api.api_run_telemetry``. Instantiating
    :class:`shared.runtime_state.store.RuntimeStateStore` for
    SELECT-only work is hostile to the read-path invariant — the store's
    ``__init__`` runs unconditional DDL plus
    ``INSERT OR REPLACE INTO meta`` on every call (see
    ``shared/runtime_state/store.py:87``), which silently makes the API
    process writable against active runtime state. Telemetry endpoints
    are polled at high frequency (the Monitor surface refreshes per
    run); each poll bumps the schema_version meta row and serializes
    against any concurrent orchestrator write.

    Returns five fields packed into :class:`RunTelemetry`:

    - ``attempts``: ``attempts_limit`` most-recent ``candidate_attempts``
      rows for the run, newest first by ``started_at`` then ``id``.
    - ``events``: ``events_limit`` most-recent ``events`` rows for the
      run, newest first by ``created_at`` then ``id``.
    - ``attempts_total`` / ``events_total``: unbounded counts so callers
      can frame the windowed view ("showing 50 of N").
    - ``last_event_at``: ISO-8601 timestamp of the run's most recent
      event, or ``None`` if no events.

    Missing-DB / corrupt-DB collapses to an empty
    :class:`RunTelemetry`, matching the aggregator's existing pattern
    that one bad state dir must not take down the response.
    """

    with _open_readonly(db_path) as conn:
        if conn is None:
            return RunTelemetry()
        try:
            attempts_total_row = conn.execute(
                "SELECT COUNT(*) AS c FROM candidate_attempts WHERE run_id = ?",
                (run_id,),
            ).fetchone()
            events_total_row = conn.execute(
                "SELECT COUNT(*) AS c FROM events WHERE run_id = ?",
                (run_id,),
            ).fetchone()
            attempt_rows = conn.execute(
                """
                SELECT id, candidate_id, work_unit_id, stage, attempt_number,
                       status, failure_kind, failure_reason, started_at, ended_at
                FROM candidate_attempts
                WHERE run_id = ?
                ORDER BY started_at DESC, id DESC
                LIMIT ?
                """,
                (run_id, attempts_limit),
            ).fetchall()
            event_rows = conn.execute(
                """
                SELECT id, event_type, candidate_id, attempt_id, payload_json,
                       created_at
                FROM events
                WHERE run_id = ?
                ORDER BY created_at DESC, id DESC
                LIMIT ?
                """,
                (run_id, events_limit),
            ).fetchall()
            last_event_row = conn.execute(
                "SELECT MAX(created_at) AS last FROM events WHERE run_id = ?",
                (run_id,),
            ).fetchone()
        except sqlite3.DatabaseError:
            return RunTelemetry()

    attempts = tuple(
        TelemetryAttempt(
            id=int(r["id"]),
            candidate_id=int(r["candidate_id"]),
            work_unit_id=(
                int(r["work_unit_id"]) if r["work_unit_id"] is not None else None
            ),
            stage=str(r["stage"]),
            attempt_number=int(r["attempt_number"]),
            status=str(r["status"]),
            failure_kind=str(r["failure_kind"]) if r["failure_kind"] else None,
            failure_reason=(
                str(r["failure_reason"]) if r["failure_reason"] else None
            ),
            started_at=str(r["started_at"]),
            ended_at=str(r["ended_at"]) if r["ended_at"] else None,
        )
        for r in attempt_rows
    )
    events = tuple(
        TelemetryEvent(
            id=int(r["id"]),
            event_type=str(r["event_type"]),
            candidate_id=(
                int(r["candidate_id"]) if r["candidate_id"] is not None else None
            ),
            attempt_id=(
                int(r["attempt_id"]) if r["attempt_id"] is not None else None
            ),
            payload_json=(
                str(r["payload_json"]) if r["payload_json"] is not None else None
            ),
            created_at=str(r["created_at"]),
        )
        for r in event_rows
    )
    last_event_at: str | None = None
    if last_event_row is not None and last_event_row["last"]:
        last_event_at = str(last_event_row["last"])

    attempts_total = (
        int(attempts_total_row["c"] or 0) if attempts_total_row is not None else 0
    )
    events_total = (
        int(events_total_row["c"] or 0) if events_total_row is not None else 0
    )

    return RunTelemetry(
        attempts=attempts,
        events=events,
        attempts_total=attempts_total,
        events_total=events_total,
        last_event_at=last_event_at,
    )


# --- helpers ----------------------------------------------------------------


def _parse_iso_to_epoch(value: object) -> float | None:
    if not isinstance(value, str):
        return None
    try:
        ts = datetime.fromisoformat(value)
    except ValueError:
        return None
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return ts.timestamp()
