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

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


WorkerState = Literal["missing", "alive", "alive_silent", "stale"]
StopResponseState = Literal["stopping", "missing", "stale"]

# Phase 1C: brief-vs-state-dir taxonomy. Every state directory the
# aggregator discovers gets exactly one of these kinds:
#   - ``authored_brief`` — has a ``runs`` row that the user actually
#     authored (or a legacy run that pre-dates the intake-session FK,
#     treated as authored for backwards compatibility). The headline
#     count for the homescreen masthead derives from this kind.
#   - ``archived`` — the user has explicitly filed this brief away
#     (``runs.is_archived = 1``), or the reconciler has auto-archived
#     a long-stale orphan.
#   - ``intake_only`` — has an open intake-authoring session but no
#     completed run yet. Surfaced separately so the user can resume
#     authoring without losing track of in-progress drafts.
#   - ``orphaned_state_dir`` — a filesystem state directory with no
#     associated run history (an artifact left behind by a deleted
#     brief, an aborted CLI launch, or a manually-created folder).
#     These were the bulk of the meaningless "282 BRIEFS" header.
EntryKind = Literal[
    "authored_brief",
    "archived",
    "intake_only",
    "orphaned_state_dir",
]


class FailureKindCount(BaseModel):
    """Phase 4: one entry of an attempt-health failure-kind histogram.

    Mirrors :class:`shared.runtime_state.read_models.FailureKindCount`
    for the wire shape. The aggregator populates these from the read
    model so the UI can display "12 × http_429" style descriptions
    without duplicating SQL knowledge.
    """

    kind: str
    count: int


class AttemptHealthSummary(BaseModel):
    """Phase 4: attempt outcomes within the recent activity window.

    The aggregator computes this for the latest run of every state dir
    so the UI can surface stalled runs (alive worker, no recent
    success, retryable failures piling up — almost always provider
    degradation that the user needs to know about).
    """

    total_attempts_in_window: int = 0
    succeeded_in_window: int = 0
    failed_in_window: int = 0
    last_success_age_s: float | None = None
    recent_failures: list[FailureKindCount] = Field(default_factory=list)
    dominant_failure_kind: str | None = None


class WorkUnitProgressSummary(BaseModel):
    """Phase 4: queued / in_progress / done counts for the latest run.

    ``kind`` discriminates: ``"not_found"`` (no run / corrupt DB),
    ``"empty"`` (run exists but no work_units of the relevant kind),
    or ``"counts"`` (counts populated). The UI renders a "32 of 78"
    style progress fact only when ``kind == "counts"``.
    """

    kind: Literal["not_found", "empty", "counts"]
    queued: int = 0
    in_progress: int = 0
    done: int = 0
    skipped: int = 0
    error: int = 0


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

    source: Literal["linkedin", "github", "designer", "exec_search", "researcher"]
    state_key: str
    # Phase 1B: state_dir was an absolute /Users/... path leaked into 282/282
    # entries on every status poll. Dropped — recruiter-facing surfaces never
    # need a filesystem path, and developer-facing surfaces (Reference Slip)
    # can compose `<source>/<state_key>` if they need an unambiguous handle.
    runtime_state_present: bool
    runtime_state_corrupt: bool = False
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
    # Phase 1.6: heartbeat_age_s is None when no sidecar / no heartbeat_at /
    # unparseable. >0 when alive but the most recent canonical write was
    # heartbeat_age_s seconds ago. The aggregator promotes worker_state to
    # "alive_silent" when this exceeds ALIVE_SILENT_THRESHOLD_S and the PID
    # is alive — typically meaning the machine slept, the worker is hung in
    # a non-cancellable section, or rate-limit retries have stalled work.
    heartbeat_age_s: float | None = None
    # Phase 3: brief identity. ``brief_role_title`` and
    # ``brief_linkedin_project`` are extracted from the snapshot stored in
    # ``runs.brief_snapshot_json`` so the UI can render the recruiter-meaningful
    # role title as the row heading instead of the directory slug
    # (state_key). All three default to None for legacy rows that pre-date
    # Phase 3 — the UI falls back to state_key in that case.
    # ``brief_drift_since_last_run`` is True when the on-disk brief at
    # ``runs.brief_path_at_launch`` no longer hashes to the stored
    # ``runs.brief_content_hash``; False when they match; None when the
    # comparison cannot be made (legacy row, file moved, etc.).
    brief_role_title: str | None = None
    brief_linkedin_project: str | None = None
    brief_drift_since_last_run: bool | None = None
    # Phase 4: status enrichment. The aggregator surfaces attempt-health
    # and work-unit-progress on every state dir entry so the UI can
    # render progress facts ("32 of 78 strings") and promote stalled
    # runs to the attention lane. ``run_stalled`` is True when the
    # worker is alive but recent failures cluster around retryable
    # HTTP-style errors with no recent success — almost always provider
    # degradation. ``stall_failure_kind`` carries the dominant kind
    # (e.g. "http_429") so the UI can render the operational reason
    # without consulting the histogram.
    attempt_health: AttemptHealthSummary | None = None
    work_unit_progress: WorkUnitProgressSummary | None = None
    run_stalled: bool = False
    stall_failure_kind: str | None = None
    # Phase 1C: brief-taxonomy classifier. Computed by
    # :func:`cloris.control_plane._classify_entry`. Defaults to
    # ``orphaned_state_dir`` so a partially-constructed entry (e.g., legacy
    # test fixture) collapses to the safest bucket.
    kind: EntryKind = "orphaned_state_dir"


class RunDetail(BaseModel):
    """Phase B: the per-run report subject.

    Superset of :class:`RunSummary` adding identity columns
    (``brief_id``, ``output_dir``, ``brief_path_at_launch``,
    ``resumed_from_run_id``) and brief-derived fields the UI needs to
    render the role title and drift indicator. Wire shape mirrors
    :class:`shared.runtime_state.read_models.RunDetail`.
    """

    id: int
    source: Literal["linkedin", "github", "designer", "exec_search", "researcher"]
    brief_id: str | None = None
    # Phase 1B: output_dir dropped from the wire shape (R9 — no absolute
    # filesystem paths in API surfaces). It's still stored canonical-side
    # in `runs.output_dir` for forensic purposes; the wire payload
    # composes `<source>/<state_key>` when the frontend needs a handle.
    mode: str | None = None
    status: str | None = None
    stop_reason: str | None = None
    started_at: str | None = None
    ended_at: str | None = None
    resumed_from_run_id: int | None = None
    brief_role_title: str | None = None
    brief_linkedin_project: str | None = None
    brief_drift_since_run: bool | None = None


class CandidateDecisionSummary(BaseModel):
    """Phase B: one candidate row in the run-report decisions list.

    A "thin" view: name, profile URL, terminal decision, confidence.
    Evidence panels (snippet, profile summary, decision rationale,
    external evidence) are deferred to Phase C's Candidate Card —
    Phase B only needs to show *who* turned up and *what* the outcome
    was.
    """

    candidate_id: int
    display_name: str
    profile_url: str
    terminal_decision: str | None = None
    confidence: float | None = None


class DecisionCounts(BaseModel):
    """Phase B: counts of candidates by terminal decision in this run.

    The histogram complements the candidate list: even when the list is
    capped, the counts reflect the full population. Keys are the raw
    decision strings (``"SAVE"``, ``"REJECT"``, ``"FACIAL_NO"``, etc.);
    the UI maps these to product copy.
    """

    total: int = 0
    by_decision: dict[str, int] = Field(default_factory=dict)


class RunReportResponse(BaseModel):
    """Top-level payload for ``GET /api/run/{source}/{state_key}/{run_id}``.

    Slice tag ``"v0-shell-slice-b1"`` (Phase B) — bumped from the
    status response slice to mark this as a new contract surface that
    can evolve independently of the aggregator.
    """

    slice: Literal["v0-shell-slice-b1"] = Field(default="v0-shell-slice-b1")
    source: Literal["linkedin", "github", "designer", "exec_search", "researcher"]
    state_key: str
    # Phase 1B: state_dir dropped (R9 — no absolute paths on the wire).
    run: RunDetail
    work_unit_progress: WorkUnitProgressSummary
    attempt_health: AttemptHealthSummary
    decisions: DecisionCounts
    candidates: list[CandidateDecisionSummary] = Field(default_factory=list)
    candidates_truncated: bool = False


class LatestRunRef(BaseModel):
    """Phase C-bis 0.1: a (source, state_key, run_id) triple suitable for
    constructing a ``#/run/<source>/<state_key>/<run_id>`` link.

    The run report stays per-source / per-state-dir even after the
    workspace and candidate-detail routes pivot to brief-first, so this
    triple is what the new responses carry to keep "View latest run report"
    and the candidate-detail back-link working.
    """

    source: Literal["linkedin", "github", "designer", "exec_search", "researcher"]
    state_key: str
    run_id: int


class CrossSourceLink(BaseModel):
    """Phase F Slice F6: one of the OTHER sources a person aggregates.

    Renders as a multi-source pill on a workspace card and as a row in
    candidate-detail's "Cross-source evidence" section. The describe
    field carries the editorial prose
    (`shared.identity_resolution_service.describe_merge_signal`) so
    the frontend never sees a raw `link_kind` enum.
    """

    source: Literal["linkedin", "github", "designer", "exec_search", "researcher"]
    state_key: str
    candidate_id: int
    profile_url: str
    display_name: str
    link_kind: Literal["auto_strong", "auto_medium", "manual"]
    describe: str


class IdentityCandidateLink(BaseModel):
    """Phase G Slice G2: one candidate row backing a person in the
    identity reconciliation surface.

    Wire-distinct from the F6 ``CrossSourceLink`` because the identity
    surface needs the source/state_key/candidate_id triple even for the
    primary link, plus the editorial ``describe`` prose for each row.
    The frontend never sees raw ``link_kind`` enums or confidence floats.
    """

    source: Literal["linkedin", "github", "designer", "exec_search", "researcher"]
    state_key: str
    candidate_id: int
    link_kind: Literal["auto_strong", "auto_medium", "manual"]
    recruiter_locked: bool
    describe: str


class IdentityPerson(BaseModel):
    """Phase G Slice G2: a canonical person from the global identity
    store, enriched with all candidate links visible under one brief.
    """

    person_id: int
    canonical_name: str
    canonical_handle: str
    sources: list[IdentityCandidateLink]


class IdentityPendingDecision(BaseModel):
    """Phase G Slice G2: one unresolved merge decision for a brief.

    Carries side-by-side person evidence and Cloris-voice
    ``signal_summary`` prose. Confidence floats are intentionally
    omitted — the editorial summary carries the meaning so the
    recruiter doesn't see raw probability output.
    """

    decision_id: int
    person_a: IdentityPerson
    person_b: IdentityPerson
    signal_summary: str
    created_at: str


class IdentityPendingResponse(BaseModel):
    """GET /api/brief/{brief_id}/identity/pending response shape."""

    slice: Literal["v0-identity-pending-1"] = "v0-identity-pending-1"
    brief_id: str
    persons_total: int
    decisions: list[IdentityPendingDecision]


class IdentityDecisionRequest(BaseModel):
    """POST /api/brief/{brief_id}/identity/decision request body."""

    model_config = ConfigDict(extra="forbid")

    decision_id: int
    choice: Literal["merge", "keep_separate"]


class IdentityUnlinkRequest(BaseModel):
    """POST /api/brief/{brief_id}/identity/unlink request body."""

    model_config = ConfigDict(extra="forbid")

    source: Literal["linkedin", "github", "designer", "exec_search", "researcher"]
    state_key: str
    candidate_id: int


# ---------------------------------------------------------------------------
# Phase G Slice G3: Live Monitor wire models. Operational register — raw
# enums + dense per-attempt rows are correct here, NOT editorial. Recruiters
# come to Monitor when they want depth Run Report deliberately doesn't show.
# ---------------------------------------------------------------------------


class ActiveRunSummary(BaseModel):
    """One row on the Live Monitor index — a run currently in motion.

    Carried fields are a thin recruiter-friendly subset of StateDirEntry so
    the index page can render brief title + source + run state without
    fetching the full status payload again.
    """

    source: Literal["linkedin", "github", "designer", "exec_search", "researcher"]
    state_key: str
    run_id: int | None
    run_status: str | None
    stop_reason: str | None
    started_at: str | None
    ended_at: str | None
    brief_id: str | None
    brief_role_title: str | None
    worker_pid: int | None


class MonitorIndexResponse(BaseModel):
    """GET /api/monitor/index response shape."""

    slice: Literal["v0-monitor-index-1"] = "v0-monitor-index-1"
    active_runs: list[ActiveRunSummary]


class TelemetryAttemptRow(BaseModel):
    """One candidate_attempts row, raw enums preserved for operator view."""

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


class TelemetryEventRow(BaseModel):
    """One events row — raw event log."""

    id: int
    event_type: str
    candidate_id: int | None
    attempt_id: int | None
    payload_summary: str | None
    created_at: str


class RunTelemetryResponse(BaseModel):
    """GET /api/run/{source}/{state_key}/{run_id}/telemetry response shape.

    Bounded: at most 50 attempts + 30 events (most-recent first). The
    Monitor view is a window into the live run, not a full audit trail —
    the runtime_state DB itself holds everything; recruiters who need
    forensics use sqlite directly.
    """

    slice: Literal["v0-run-telemetry-1"] = "v0-run-telemetry-1"
    source: Literal["linkedin", "github", "designer", "exec_search", "researcher"]
    state_key: str
    run_id: int
    attempts: list[TelemetryAttemptRow]
    events: list[TelemetryEventRow]
    last_event_at: str | None
    attempts_total: int
    events_total: int


# ---------------------------------------------------------------------------
# Phase G Slice G4: Tools index + execution wire models.
# ---------------------------------------------------------------------------


class ToolEntry(BaseModel):
    """One tool in the catalog. ``schema_fields`` is a hand-crafted
    summary of the args schema (field name + type label) so the frontend
    can render a form without reflecting Pydantic at runtime.
    """

    tool_id: str
    tier: Literal["A", "B", "C"]
    label: str
    pitch: str
    cli_command: str
    execution_model: Literal["sync", "async", "cli_only"]
    schema_fields: list[dict] = Field(default_factory=list)


class ToolsIndexResponse(BaseModel):
    slice: Literal["v0-tools-index-1"] = "v0-tools-index-1"
    tools: list[ToolEntry]


class ToolRunRequest(BaseModel):
    """POST /api/tools/{tool_id} body — args validated per-tool."""

    model_config = ConfigDict(extra="forbid")

    args: dict = Field(default_factory=dict)


class ToolRunSyncWire(BaseModel):
    slice: Literal["v0-tool-sync-1"] = "v0-tool-sync-1"
    tool_id: str
    exit_code: int
    stdout_tail: str
    stderr_tail: str


class ToolRunAsyncWire(BaseModel):
    slice: Literal["v0-tool-async-1"] = "v0-tool-async-1"
    tool_id: str
    job_id: str


class ToolJobStatusWire(BaseModel):
    slice: Literal["v0-tool-job-1"] = "v0-tool-job-1"
    job_id: str
    tool_id: str
    status: Literal["queued", "running", "succeeded", "failed", "purged"]
    started_at: float
    finished_at: float | None
    exit_code: int | None
    stdout_tail: str
    stderr_tail: str
    error_message: str | None


# ---------------------------------------------------------------------------
# Phase G Slice G5: Settings transparency surface. Read-only — Cloris's
# operational config is hard-coded by deliberate engineering decision; this
# surface lets the recruiter see what's set without being able to break
# anything. Credentials surface as ✓/✗ booleans, NEVER values.
# ---------------------------------------------------------------------------


class SettingsCredential(BaseModel):
    key: str
    label: str
    present: bool
    pitch: str  # editorial Cloris-voice line


class SettingsBriefSaveSummary(BaseModel):
    brief_id: str
    role_title: str | None
    target_modules: list[str]
    linkedin_project_id: str | None


class SettingsGovernorLimit(BaseModel):
    name: str
    label: str
    value: int | str
    explainer: str  # Cloris-voice explanation of why this isn't editable


class SettingsResponse(BaseModel):
    slice: Literal["v0-settings-1"] = "v0-settings-1"
    credentials: list[SettingsCredential]
    save_destinations: list[SettingsBriefSaveSummary]
    governor: list[SettingsGovernorLimit]
    cdp_url: str


class CandidateCardSummary(BaseModel):
    """Phase C, slice C2 (extended in C4 + C-bis 0.1 + F6): one card on the Workspace surface.

    Trimmed view: name, profile URL, save reason, decision, confidence,
    timestamps. The full :class:`CandidateDetailResponse` is fetched
    when the user clicks through. Unlike
    :class:`CandidateDecisionSummary` (run-report scoped), this row is
    brief-scoped — saves across all runs of the same brief.

    C4 extension: ``user_status`` surfaces the recruiter override.
    C-bis 0.1: ``source`` is part of the wire shape so the workspace
    grid can render source-provenance on each card.
    F6: ``cross_source_links`` lists the OTHER (source, candidate_id)
    pairs aggregated under the same canonical person. Empty for a
    person observed on a single source.
    """

    candidate_id: int
    source: Literal["linkedin", "github", "designer", "exec_search", "researcher"]
    identity_key: str
    display_name: str
    profile_url: str
    terminal_decision: str
    save_reason: str | None = None
    confidence: float | None = None
    first_seen_at: str | None = None
    last_seen_at: str | None = None
    user_status: str | None = None
    cross_source_links: list[CrossSourceLink] = Field(default_factory=list)


class WorkspaceResponse(BaseModel):
    """Phase C-bis 0.1: per-brief workspace payload, brief-first.

    Wire shape for ``GET /api/workspace/{brief_id}``. Aggregates every
    SAVE-class candidate for the brief across every state_dir whose
    latest run carries that brief_id — typically one source today, but
    Phase F multi-module operation will fan out across LinkedIn +
    GitHub + Researcher etc.

    Recipe-card stats (``total_saves``, ``saves_this_week``,
    ``shortlisted_count``, ``last_save_at``) roll up across all matched
    state_dirs. ``sources`` lists which source modules contributed.
    ``latest_run`` is the most recent run across all matches, used by
    "View latest run report".

    Slice tag ``v0-shell-slice-c5`` marks the brief-first contract
    revision; the prior c4 source-siloed shape is gone.
    """

    slice: Literal["v0-shell-slice-c5"] = Field(default="v0-shell-slice-c5")
    brief_id: str
    sources: list[Literal["linkedin", "github", "designer", "exec_search", "researcher"]] = Field(default_factory=list)
    brief_role_title: str | None = None
    brief_linkedin_project: str | None = None
    latest_run: LatestRunRef | None = None
    total_saves: int = 0
    saves_this_week: int = 0
    shortlisted_count: int = 0
    last_save_at: str | None = None
    candidates: list[CandidateCardSummary] = Field(default_factory=list)


class CandidateNoteEntry(BaseModel):
    """Phase C, slice C3: one recruiter-authored note on a candidate."""

    body: str
    created_at: str


class CandidateDetailResponse(BaseModel):
    """Phase C-bis 0.1: candidate-detail surface payload, brief-first.

    Wire shape for ``GET /api/candidate/{brief_id}/{candidate_id}``. The
    URL no longer carries ``source`` or ``state_key`` — both are present
    in the response for rendering (source eyebrow, run back-link) but
    they're metadata, not identity.

    ``source_run`` bundles ``(source, state_key, run_id)`` so the
    candidate-detail page can construct ``#/run/<source>/<state_key>/<run_id>``
    for the back-link without round-tripping through the URL params.

    Slice tag ``v0-shell-slice-c5`` marks the brief-first contract
    revision; the prior c3 source-siloed shape is gone.
    """

    slice: Literal["v0-shell-slice-c5"] = Field(default="v0-shell-slice-c5")
    source: Literal["linkedin", "github", "designer", "exec_search", "researcher"]
    brief_id: str
    candidate_id: int
    identity_key: str
    display_name: str
    profile_url: str
    terminal_decision: str | None = None
    confidence: float | None = None
    save_reason: str | None = None
    current_lifecycle_state: str | None = None
    first_seen_at: str | None = None
    last_seen_at: str | None = None
    # Brief context from the most recent run that touched this candidate.
    source_run: LatestRunRef | None = None
    brief_role_title: str | None = None
    brief_linkedin_project: str | None = None
    # C3: recruiter-authored fields.
    notes: list[CandidateNoteEntry] = Field(default_factory=list)
    user_status: str | None = None
    # Phase C-bis 0.3: when the candidate's lifecycle state is in the
    # failed_* family, the workspace already filters it out — but a
    # recruiter who lands on the candidate detail directly (deep link)
    # needs the page to disable pipeline-action affordances (status
    # toggle, notes compose) until the next run resolves the failure.
    is_failed_state: bool = False
    # Phase C-bis 0.5: closed-loop feedback substrate. Distinct from
    # ``user_status`` — this is the recruiter's calibration signal on
    # whether Cloris's *judgment* was right, not a pipeline action.
    # Both fields ride on the wire so the future Next Run Learning
    # surface can render the calibration history without an extra
    # round-trip. NULL = no signal yet.
    judgment_accuracy: str | None = None
    judgment_accuracy_at: str | None = None
    # Phase F Slice F6: per-candidate cross-source links. Empty when
    # this person was only observed on a single source. Populated when
    # F3's identity resolver merged this candidate with one or more
    # candidates from other sources for the same brief. The
    # candidate-detail page renders these as a "Cross-source evidence"
    # section.
    cross_source_links: list[CrossSourceLink] = Field(default_factory=list)


class LegacyResolveResponse(BaseModel):
    """Phase C-bis 0.1: response for the legacy URL resolver endpoints.

    The frontend hits these when it parses an old-shape hash like
    ``#/workspace/<source>/<state_key>`` so it can rewrite to the
    brief-first equivalent. Same shape works for both workspace and
    candidate redirects — the candidate_id stays unchanged across the
    rewrite, so only ``brief_id`` is needed.
    """

    brief_id: str


class CandidateNoteRequest(BaseModel):
    """Phase C, slice C3: request body for ``POST /api/candidate/.../note``."""

    model_config = ConfigDict(extra="forbid")
    body: str


class CandidateStatusPatchRequest(BaseModel):
    """Phase C, slice C3: request body for ``PATCH /api/candidate/...``.

    A ``user_status`` of ``None`` clears the recruiter override and
    falls back to Cloris's terminal_decision. Non-empty strings set the
    override; the API layer validates the allowed set.
    """

    model_config = ConfigDict(extra="forbid")
    user_status: str | None = None


class CandidateJudgmentAccuracyPatchRequest(BaseModel):
    """Phase C-bis 0.5: request body for the judgment-accuracy PATCH.

    ``judgment_accuracy`` is the recruiter's calibration signal on
    Cloris's terminal decision — explicitly distinct from
    ``user_status`` (a pipeline action). ``None`` clears the signal.
    Non-null values must be in the allowed set; the API layer
    validates and returns 422 on unknown.
    """

    model_config = ConfigDict(extra="forbid")
    judgment_accuracy: str | None = None


class BriefCounts(BaseModel):
    """Phase 1C: roll-up of authored briefs by activity bucket.

    Replaces the meaningless 282 / 170 / 112 ribbon ("BRIEFS / ACTIVE /
    PAUSED") on the homescreen masthead — those numbers counted state
    directories on disk, of which 275/282 had no run history at all.
    These counts answer recruiter-facing questions:

      - ``active``: how many briefs are *live* — currently running, paused
        on a limit, or interrupted but resumable. The user might want
        to look at any of them today.
      - ``working``: how many of those are progressing right now (worker
        alive, run status='running'). Subset of ``active``.
      - ``paused``: those that hit a limit or were interrupted and now
        wait on the user to nudge them. Subset of ``active``.
      - ``finished``: completed cleanly; effectively done.
      - ``lost``: abandoned (zombie reconciled) or errored out. Need
        attention but not progressing.
      - ``archived``: explicitly filed away by the user (or auto-archived).
      - ``orphaned``: filesystem state directories with no run history,
        kept around for diagnostic purposes but not surfaced as briefs.
    """

    active: int = 0
    working: int = 0
    paused: int = 0
    finished: int = 0
    lost: int = 0
    archived: int = 0
    orphaned: int = 0


class BriefStatusGroup(BaseModel):
    """Phase F Slice F7: home + filed group state-dir entries by brief_id.

    A single brief can spawn N state dirs (one per discovery module).
    Pre-F7, each state dir rendered as its own card on home + filed
    surfaces — duplicate visual entries for one logical brief. F7
    groups by ``brief_id`` so the recruiter sees ONE card per brief
    with a multi-module status indicator inside.

    ``brief_id`` is None for orphaned state dirs (no run, no
    ``brief_id_from_run``) so they still surface in the response as a
    diagnostic group rather than being silently dropped.
    """

    brief_id: str | None = None
    brief_role_title: str | None = None
    brief_linkedin_project: str | None = None
    modules: list[StateDirEntry] = Field(default_factory=list)


class StatusResponse(BaseModel):
    """Top-level payload for ``GET /api/status``.

    ``slice`` is pinned to ``"v0-shell-slice-4"`` so callers can detect the
    contract version without re-typing the literal at every construction
    site. The bump from ``"v0-shell-slice-2"`` to ``"v0-shell-slice-4"``
    reflects the enriched :class:`StateDirEntry` shape Slice 4 ships.

    Phase 1C adds ``counts`` — a roll-up of the brief-taxonomy buckets so
    the masthead can render recruiter-facing numbers without computing them
    client-side from a partially-classified list.

    Phase F Slice F7 adds ``briefs`` — the same state-dir entries
    grouped by ``brief_id`` so the home + filed surfaces can render one
    card per brief instead of one per (brief × module). ``entries``
    stays for backward compat: existing callers that read it keep
    working. The frontend home + filed surfaces consume ``briefs``.
    """

    slice: Literal["v0-shell-slice-4"] = Field(default="v0-shell-slice-4")
    entries: list[StateDirEntry]
    counts: BriefCounts = Field(default_factory=BriefCounts)
    briefs: list[BriefStatusGroup] = Field(default_factory=list)


class LaunchResponse(BaseModel):
    """Response payload for ``POST /api/launch/{source}`` (Phase F Slice F1)
    and the legacy ``POST /api/launch/linkedin`` synonym.

    ``slice`` stays at ``"v0-shell-slice-3"`` — F1 widens ``source`` from
    ``Literal["linkedin"]`` to ``Literal["linkedin", "github", "designer", "exec_search", "researcher"]`` (additive)
    and adds ``mode`` so resume launches can carry their truth without
    needing the separate :class:`ResumeResponse`. The slice tag is the
    skew-detection signal for *shape* breaks; widening a Literal is
    additive, so the tag does not bump.

    ``pid`` is the spawned worker process's PID at the moment ``Popen``
    returns; after ``cloris.worker`` ``execvp``s into the per-source
    orchestrator, the same PID belongs to the orchestrator process, so
    this value remains the truthful process handle for later
    stop/probe operations.
    """

    slice: Literal["v0-shell-slice-3"] = Field(default="v0-shell-slice-3")
    source: Literal["linkedin", "github", "designer", "exec_search", "researcher"]
    input_mode: Literal["concurrent"]
    mode: Literal["fresh", "resume"] = Field(default="fresh")
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
    source: Literal["linkedin", "github", "designer", "exec_search", "researcher"]
    state_key: str
    state_dir: str
    worker_state: StopResponseState
    pid: int | None = None


class ResumeResponse(BaseModel):
    """Response payload for the legacy ``POST /api/resume/linkedin`` synonym.

    Phase F Slice F1 collapses launch + resume into a single endpoint
    (``POST /api/launch/{source}`` with ``mode="resume"``) and returns
    :class:`LaunchResponse`. This shape stays around for backward compat
    with clients still hitting the old route. The ``source`` Literal
    widens from ``Literal["linkedin"]`` to
    ``Literal["linkedin", "github", "designer", "exec_search", "researcher"]`` so the legacy resume route can
    redirect transparently to the F1 path without re-shaping the wire.
    """

    slice: Literal["v0-shell-slice-4"] = Field(default="v0-shell-slice-4")
    source: Literal["linkedin", "github", "designer", "exec_search", "researcher"]
    mode: Literal["resume"] = Field(default="resume")
    input_mode: Literal["concurrent"]
    pid: int
    state_dir: str
    worker_json_path: str


class LaunchRequest(BaseModel):
    """Request body for the generic ``POST /api/launch/{source}`` endpoint.

    Phase F Slice F1. The recruiter picks a brief by id (the same hash
    runtime_state tracks); the body carries no path. The dispatch
    layer in :mod:`cloris.api` resolves the brief_id to disk via
    :func:`_resolve_brief_by_id` and dispatches to the per-source
    spawn function via :data:`cloris.launchers.LAUNCHERS`.

    ``mode`` is strict ``Literal["fresh", "resume"]`` so an unrecognized
    value (e.g., a future ``"refresh"`` mode added by Phase E) is
    caught at the request boundary, forcing an explicit slice bump.

    ``force`` skips the launch-readiness probe (Phase D Slice D9). It
    does NOT skip ``BriefPathNotFoundError``,
    ``WorkerAlreadyRunningError``, or ``NoPendingWorkError`` — those
    are pre-flight integrity checks, not soft readiness signals. The
    recruiter mental model is "I know auth is iffy but try anyway."
    """

    model_config = ConfigDict(extra="forbid")
    brief_id: str
    mode: Literal["fresh", "resume"] = "fresh"
    force: bool = False


class BriefInfo(BaseModel):
    """One authored brief discovered under ``config/``.

    Two consumers, two surface use-cases:
    - **LaunchForm BriefPicker** (Phase 4) — pick by role to launch. Uses
      ``path``, ``role_title``, ``linkedin_project*``, ``modified_at``.
    - **Phase D Slice D1 — Brief library at ``#/briefs``** — list every
      authored brief with run metadata. Uses the picker fields PLUS the
      ``brief_id`` + ``last_run_*`` + ``total_*`` fields below.

    The library-only fields are nullable / default 0 so picker callers
    don't break — the same model serves both surfaces additively. The
    aggregator in :mod:`cloris.control_plane.aggregate_briefs` populates
    the library fields by walking ``state_dirs_for_brief_id()`` for each
    authored brief; the picker endpoint can skip the run-metadata
    decoration if it doesn't need it (cheaper).
    """

    path: str
    role_title: str | None = None
    linkedin_project: str | None = None
    linkedin_project_id: str | None = None
    modified_at: str  # ISO-8601 UTC; "" if stat failed

    # Phase D Slice D1: library-only run metadata. Nullable so picker
    # callers see the same shape they always have. ``brief_id`` is the
    # ``linkedin_state_key(path)`` hash that ``runs.brief_id`` carries.
    brief_id: str | None = None
    last_run_id: int | None = None
    last_run_at: str | None = None
    last_run_status: str | None = None
    last_run_source: Literal["linkedin", "github", "designer", "exec_search", "researcher"] | None = None
    total_runs: int = 0
    total_saves: int = 0

    # Phase F Slice F5: which discovery modules this brief targets.
    # Legacy briefs without this key default to ["linkedin"] at the
    # frontend (mirrors BriefDetail.svelte's destinationModules helper);
    # the backend sends None so the picker can distinguish "not set"
    # from "explicitly empty list" (which would mean "ask the recruiter
    # to pick at launch time").
    target_modules: list[str] | None = None


class BriefsListResponse(BaseModel):
    """Response payload for ``GET /api/briefs``.

    Sorted most-recently-modified first so the picker leads with what
    the user has been working on lately.
    """

    slice: Literal["v0-briefs-list-1"] = Field(default="v0-briefs-list-1")
    briefs: list[BriefInfo]


class BriefDetailResponse(BaseModel):
    """Response payload for ``GET /api/brief/{brief_id}``. Phase D Slice D2.

    Mirrors the partition that
    :class:`shared.brief_v2_schema.MergedBrief` already returns. The
    architectural-fit critique caught: if we only send ``deprecated_keys``
    (names) without ``preserved_legacy`` (values), the frontend can't
    render the legacy values in the deprecation drawer, AND the PUT
    handler would have to re-read disk to know what to keep. By sending
    the full partition over the wire, PUT becomes pure: rebuild =
    ``v2_data ∪ (preserved_legacy − dropped_legacy_keys)``.

    ``v2_data`` is intentionally typed as ``dict[str, Any]`` (not a
    Pydantic sub-model). The V2 schema has 60+ optional sub-shapes
    (capability_areas, depth_distinction, non_fit_patterns,
    facial_calibration, …); typing each is premature for D2. The frontend
    treats it as opaque + renders the fields it knows. The envelope
    stays Pydantic-typed for stable client expectations.

    ``was_flat`` tells the frontend the brief is currently a flat
    ``config/<name>.json`` and will migrate to nested
    ``config/<name>/brief.json`` on first edit (Fork C).
    """

    slice: Literal["v0-brief-detail-1"] = Field(default="v0-brief-detail-1")
    brief_id: str
    path: str
    role_title: str | None = None
    v2_data: dict[str, Any]
    preserved_legacy: dict[str, Any]
    deprecated_keys: list[str]
    unknown_keys: list[str]
    last_modified: str
    version_count: int = 0
    was_flat: bool = False


class BriefVersionEntry(BaseModel):
    """One row in the version history list. Phase D Slice D5."""

    version_id: str  # filename stem, e.g. "2026-05-01T16-32-12.567+00-00"
    created_at: str  # ISO-8601 (decoded from filename)
    size_bytes: int


class BriefVersionsResponse(BaseModel):
    """Response for ``GET /api/brief/{brief_id}/versions``. Phase D Slice D5."""

    slice: Literal["v0-brief-versions-1"] = Field(default="v0-brief-versions-1")
    brief_id: str
    versions: list[BriefVersionEntry]


# Phase E Slice E1: Market viewer wire shapes. Distinct from
# `market_intelligence.schema.MarketIntelArtifact` so the on-disk
# artifact format can evolve without breaking the wire (and so the
# detail payload can flatten + trim the artifact to recruiter-facing
# fields rather than shipping the full 60-lane raw JSON).


class MarketSummary(BaseModel):
    """One row in the market viewer's catalog list."""

    market_key: str
    role_title: str
    role_level: str
    geography: str
    last_updated_at: str
    run_count: int
    saved_count: int
    aggregate_save_rate: float | None = None


class MarketsListResponse(BaseModel):
    """Response payload for ``GET /api/markets``. Most-recently-updated
    first so the list reads as "what Cloris has been studying lately."""

    slice: Literal["v0-markets-list-1"] = Field(default="v0-markets-list-1")
    markets: list[MarketSummary]


class MarketLane(BaseModel):
    """One lane row on the market detail page.

    Trimmed shape — ``why_it_works`` + ``recommended_action`` carry the
    recruiter-readable prose; metrics roll up the per-lane volumes.
    Drops the supporting_run_refs + dominant_anchors machinery (that
    detail belongs in a future Reference Slip / Cloris-internal view).
    """

    lane_key: str
    domain_lane: str
    novelty_bucket: str
    status: str
    candidates_seen: int
    saves: int
    save_rate: float | None = None
    why_it_works: str | None = None
    recommended_action: str | None = None


class MarketTalentPool(BaseModel):
    """One talent-pool row on the market detail page."""

    pool_key: str
    label: str
    signal_strength: str
    status: str
    evidence_summary: str | None = None


class MarketThesis(BaseModel):
    """The "Cloris's read" stanza copy."""

    summary: str
    supply_assessment: str = ""
    competition_assessment: str = ""
    external_context: str = ""


class MarketDetailResponse(BaseModel):
    """Response payload for ``GET /api/market/{market_key}``."""

    slice: Literal["v0-market-detail-1"] = Field(default="v0-market-detail-1")
    market_key: str
    role_title: str
    role_level: str
    geography: str
    last_updated_at: str
    run_count: int
    saved_count: int
    rejected_count: int = 0
    aggregate_save_rate: float | None = None
    facial_yes_rate: float | None = None
    lanes: list[MarketLane] = Field(default_factory=list)
    talent_pools: list[MarketTalentPool] = Field(default_factory=list)
    market_thesis: MarketThesis
    # Engine's structured brief-edit proposals from the market intel
    # artifact. The frontend's computeBriefDiff() walks this as a fourth
    # source alongside lanes/thesis/talent_pools so RefreshBrief surfaces
    # the wider field set (additional_search_terms,
    # employer_signal_rules, search_priorities, instructions, notes)
    # the same way Reflection's HunkCard surface does. Default-empty
    # so any consumer built before the field was added handles it as
    # "no recommendations" — forward-compatible.
    brief_recommendations: list[dict] = Field(default_factory=list)


class BriefEditRequest(BaseModel):
    """Request body for ``PUT /api/brief/{brief_id}``. Phase D Slice D2.

    The frontend rebuilds the full brief client-side and ships:
    - ``v2_data`` — the V2-schema fields the recruiter edited (or kept).
    - ``preserved_legacy`` — every legacy/unknown key the recruiter
      decided to keep. The backend writes ``v2_data ∪ preserved_legacy``
      verbatim. Anything not in either dict is dropped.
    - ``dropped_legacy_keys`` — optional, audit-only list of which
      deprecated/unknown keys the recruiter dropped this edit. Captured
      for telemetry; the actual dropping is just "key absent from
      ``preserved_legacy``."
    """

    model_config = ConfigDict(extra="forbid")
    v2_data: dict[str, Any]
    preserved_legacy: dict[str, Any] = Field(default_factory=dict)
    dropped_legacy_keys: list[str] = Field(default_factory=list)


class LaunchReadinessBlocker(BaseModel):
    """One reason a launch isn't ready. Phase D Slice D9 (Ledger L4).

    Each blocker carries an editorial remediation string the LaunchForm
    renders as italic prose — never a red form-error chip. The ``kind``
    discriminator lets the frontend tint each remediation per category
    (auth = peach-deep, config = blue-pencil, net = wood) without a
    per-source switch.
    """

    kind: Literal["auth", "config", "net"]
    message: str
    remediation: str


class LaunchReadinessResponse(BaseModel):
    """Response payload for ``GET /api/launch-readiness/{source}/{brief_id}``.

    Phase D Slice D9 (Ledger L4). ``ready`` is true iff ``blockers`` is
    empty. The ``source`` and ``brief_id`` echo the request so the
    frontend can verify it got an answer for what it asked. The
    ``brief_id`` slot is captured but not used by Phase D's checks
    (which are all source-level: browser session, token scope). Phase
    F's per-brief save-destination check will start consulting it.

    Slice tag ``v0-launch-readiness-1`` is the wire-shape version. It
    bumps when the response gains new fields (e.g. Phase F's brief-
    specific blockers), not when the underlying probe logic shifts.
    """

    slice: Literal["v0-launch-readiness-1"] = Field(default="v0-launch-readiness-1")
    source: Literal["linkedin", "github", "designer", "exec_search", "researcher"]
    brief_id: str
    ready: bool
    blockers: list[LaunchReadinessBlocker]


class OnboardingStatusResponse(BaseModel):
    """Response payload for ``GET /api/onboarding/status``.

    Phase 0 ``apikey-ui`` slice. The frontend gate in App.svelte
    fetches this on mount and, when ``welcome_complete`` is false,
    renders Welcome.svelte instead of the route table. The other
    fields let the welcome surface reflect partial progress (key
    entered but acknowledgment missing, or vice versa) without
    losing what the recipient already typed.

    ``env_path`` and ``acknowledgment_path`` are surfaced to the wire
    so the welcome copy can name the exact paths Cloris will write to
    on the recipient's Mac. This is the relational-disclosure layer
    the IT-defensibility README leans on.
    """

    slice: Literal["v0-onboarding-status-1"] = Field(
        default="v0-onboarding-status-1"
    )
    welcome_complete: bool
    anthropic_present: bool
    acknowledged: bool
    acknowledged_at: str | None
    env_path: str
    acknowledgment_path: str


class CredentialUpsertRequest(BaseModel):
    """Request body for ``POST /api/onboarding/credential``.

    Phase 0 ``apikey-ui`` slice. ``key`` mirrors the wire-side
    credential key surface in ``cloris.api._CREDENTIAL_LABELS``
    (``anthropic_api_key`` / ``openai_api_key`` / ``google_api_key``
    / ``perplexity_api_key``). ``value`` is the raw secret; the
    backend chmod 600's the .env file on every write.

    ``extra="forbid"`` rejects unknown fields at the request boundary
    so a typo in the welcome / Settings UI surfaces clearly.
    """

    model_config = ConfigDict(extra="forbid")
    key: str
    value: str


class AcknowledgmentRequest(BaseModel):
    """Request body for ``POST /api/onboarding/acknowledge``.

    Phase 0 ``apikey-ui`` / ``disclosure`` slices. ``acknowledged``
    must be ``true`` — the welcome surface only sends this on the
    explicit checkbox-checked + Continue flow. Sending ``false`` is
    rejected at the route layer.
    """

    model_config = ConfigDict(extra="forbid")
    acknowledged: bool


class ChromeStatusResponse(BaseModel):
    """Response payload for ``GET /api/chrome-status`` and
    ``POST /api/chrome-relaunch``.

    Phase 0 ``chrome-launcher`` slice. Wire shape for the welcome
    surface's polling loop and the Settings "Re-open Chrome" control.
    Mirrors :class:`cloris.chrome_launcher.ChromeStatus` exactly; the
    Pydantic shell is just for FastAPI response validation.

    ``state`` values:

    - ``healthy`` — CDP is reachable; the recipient can sign into
      LinkedIn Recruiter and start a search.
    - ``spawning`` — Cloris kicked Chrome off; not healthy yet. The
      welcome surface should keep polling.
    - ``unhealthy`` — Chrome isn't up and Cloris hasn't relaunched
      it. The welcome surface offers the "Re-open Chrome" control.
    - ``missing_chrome`` — Google Chrome isn't installed at the
      expected path. ``message`` carries the install URL prompt.
    - ``unsupported_platform`` — non-macOS host. The .app is
      macOS-only; the wire response makes the failure mode explicit.

    ``message`` is a recruiter-readable one-sentence summary that the
    welcome surface can render verbatim.
    """

    slice: Literal["v0-chrome-status-1"] = Field(default="v0-chrome-status-1")
    state: Literal[
        "healthy",
        "spawning",
        "unhealthy",
        "missing_chrome",
        "unsupported_platform",
    ]
    cdp_url: str
    profile_dir: str
    message: str


class ReconciledRun(BaseModel):
    """One run that the reconciler marked abandoned.

    Returned in :class:`ReconcileResponse`. Frontend uses these for a
    one-time "Cloris noticed N runs lost track" toast on app startup so
    the user has forensic context for status pills that just changed.
    """

    source: Literal["linkedin", "github", "designer", "exec_search", "researcher"]
    state_key: str
    run_id: int
    new_status: str
    stop_reason: str
    reason: str  # missing_sidecar / bad_sidecar / pid_dead


class ReconcileResponse(BaseModel):
    """Response payload for ``POST /api/reconcile``.

    Returned synchronously after the reconciler walks every state dir,
    emits mutations for runs whose worker process is gone, and applies
    them through the canonical write path. ``applied`` is the count
    actually written; ``mutations`` are the per-run records for the
    UI to surface (and for tests to inspect).
    """

    slice: Literal["v0-reconciler-slice-1"] = Field(default="v0-reconciler-slice-1")
    applied: int
    mutations: list[ReconciledRun]


# --- Onboarding flow intake sessions (A24 trial plan, Slice 1B) ---
#
# Authoring state for the brief-authoring conversation. Per the plan's A1
# decision, intake sessions live in a dedicated SQLite table that colocates
# with the runtime-state DB but is distinct from run-lifecycle state. The
# slice tag ``"v0-onboarding-slice-1"`` is new (no relation to the
# v0-shell-slice tags) so onboarding-flow versioning evolves independently
# of the launch/status surface.


class IntakeSession(BaseModel):
    """One brief-authoring conversation, resumable across reloads.

    ``current_step`` is the literal step name used by the onboarding flow
    state machine. The full set of legal values:

    ``"welcome"``, ``"role_basics"``, ``"role_framing"``,
    ``"good_looks_like"``, ``"lookalikes"``, ``"exemplars"``,
    ``"search_stance"``, ``"anything_else"``, ``"synthesis"``, ``"review"``,
    ``"completed"``.

    Slice 1B does not enforce these as a Literal because the synthesis
    endpoint (Slice 5) may want to introduce new transitional steps without
    a wire-shape break; the column is a free-form ``TEXT`` and the model
    surface accepts any string. ``state_json`` is the parsed dict (the DB
    column is TEXT and stores JSON).
    """

    id: int
    brief_id_draft: str | None
    role_title: str | None
    current_step: str
    state_json: dict
    started_at: str
    updated_at: str
    completed_at: str | None
    archived_at: str | None


class IntakeSessionCreateRequest(BaseModel):
    """Request body for ``POST /api/intake/sessions``.

    ``role_title`` is an optional initial hint surfaced by the welcome
    step; everything else is set server-side at creation time.
    """

    model_config = ConfigDict(extra="forbid")
    role_title: str | None = None


class IntakeSessionPatchRequest(BaseModel):
    """Request body for ``PATCH /api/intake/sessions/{session_id}``.

    All fields optional — the patch endpoint is a partial update. Sending
    no body is a no-op patch that still bumps ``updated_at`` so the UI's
    last-seen timestamp ticks even when only a heartbeat-style ping is
    issued.
    """

    model_config = ConfigDict(extra="forbid")
    current_step: str | None = None
    state_json: dict | None = None
    role_title: str | None = None


class IntakeSessionListResponse(BaseModel):
    """Response payload for ``GET /api/intake/sessions``."""

    slice: Literal["v0-onboarding-slice-1"] = Field(
        default="v0-onboarding-slice-1"
    )
    sessions: list[IntakeSession]


class IntakeSessionResponse(BaseModel):
    """Response payload for ``POST/GET/PATCH /api/intake/sessions[...]``."""

    slice: Literal["v0-onboarding-slice-1"] = Field(
        default="v0-onboarding-slice-1"
    )
    session: IntakeSession


class IntakeSessionDeleteResponse(BaseModel):
    """Response payload for ``DELETE /api/intake/sessions/{session_id}``."""

    slice: Literal["v0-onboarding-slice-1"] = Field(
        default="v0-onboarding-slice-1"
    )
    deleted: bool
    id: int


class IntakeSessionCompleteResponse(BaseModel):
    """Response payload for ``POST /api/intake/sessions/{session_id}/complete``.

    Phase D Slice D3. The intake wizard's terminal call writes the
    drafted V2 brief to disk and stamps the session as completed; this
    response carries both the freshly-completed session and the new
    ``brief_id`` / ``brief_path`` so the wizard can navigate directly
    to ``#/brief/<brief_id>`` without a second round-trip.
    """

    slice: Literal["v0-onboarding-slice-1"] = Field(
        default="v0-onboarding-slice-1"
    )
    session: IntakeSession
    brief_id: str
    brief_path: str


# --- The Reflection — HITL market intelligence flow ---
#
# Wire models for the two-gate HITL flow that pauses around the market
# intelligence engine. Slice tag ``"v0-reflection-slice-1"`` is new and
# evolves independently of the onboarding/intake versioning.
#
# Wire-shape note: the ``state_json`` and ``hunks`` payloads carry the
# engine's structured outputs (planner result, editorial briefing,
# proposed hunks). The Pydantic surface keeps them as opaque dicts/lists
# at the BaseModel boundary; the engine module owns their schema.
# Keeping the wire types loose is deliberate — if a follow-up enriches
# the hunk shape, the API doesn't need a model bump.


class ReflectionSession(BaseModel):
    """One reflection session, persisted across the full HITL flow.

    ``current_phase`` walks: ``planning`` → ``plan_approved`` →
    ``researching`` → ``awaiting_diff`` → ``committed`` (terminal) |
    ``discarded`` (terminal).

    ``state_json`` is the engine's phase-output bag: keys
    ``phase_outputs.plan``, ``phase_outputs.research``,
    ``phase_outputs.propose``, plus a top-level ``context`` block and
    ``steering_history`` list. The frontend reads structured sub-keys
    off the dict; the wire type is permissive on purpose.

    ``research_error`` is non-null when the research phase hit a fatal
    error (Perplexity timeout, network blip). The frontend surfaces it
    as an editorial recovery prompt; the user can re-trigger research
    or proceed to propose using internal evidence only.
    """

    id: int
    brief_id: str
    source_run_id: int | None
    current_phase: str
    state_json: dict
    steering_iterations: int
    started_at: str
    updated_at: str
    completed_at: str | None
    discarded_at: str | None
    brief_version_committed: str | None
    research_error: str | None


class ReflectionCreateRequest(BaseModel):
    """Request body for ``POST /api/reflection/sessions``.

    ``brief_id`` identifies the brief the recruiter wants Cloris to
    reflect on. ``source_run_id`` optionally biases the reflection
    toward a specific run (otherwise the planner uses whatever
    evidence it can find for the brief). ``run_dir`` is an explicit
    override for the snapshot directory; in practice the API resolves
    it from ``source_run_id`` when not provided.
    """

    model_config = ConfigDict(extra="forbid")
    brief_id: str
    source_run_id: int | None = None
    run_dir: str | None = None


class ReflectionSteeringRequest(BaseModel):
    """Request body for ``PATCH /api/reflection/sessions/{id}/steering``.

    ``note`` is the recruiter's natural-language steering input.
    Empty strings degenerate to a no-op (the API echoes the existing
    state without bumping the iteration counter). The 3-iteration cap
    is enforced server-side; over the cap the call returns 409.
    """

    model_config = ConfigDict(extra="forbid")
    note: str


class ReflectionStartResearchRequest(BaseModel):
    """Request body for ``POST /api/reflection/sessions/{id}/start_research``.

    No fields today — Gate 1 approval is just a state transition. The
    request body exists so the endpoint can grow extension fields
    (e.g., ``with_external_research`` override) without a wire break.
    """

    model_config = ConfigDict(extra="forbid")


class ReflectionCommitRequest(BaseModel):
    """Request body for ``POST /api/reflection/sessions/{id}/commit``.

    ``accepted_hunk_ids`` is the list of hunk ids the recruiter
    approved at Gate 2. ``edited_hunks`` is an optional map of
    ``hunk_id -> {"after": "<edited value>"}`` for hunks the recruiter
    edited inline. Hunks not in ``accepted_hunk_ids`` are dropped on
    the floor; the brief is committed with only accepted (and possibly
    edited) hunks applied.
    """

    model_config = ConfigDict(extra="forbid")
    accepted_hunk_ids: list[str]
    edited_hunks: dict[str, dict] | None = None


class ReflectionDiscardRequest(BaseModel):
    """Request body for ``POST /api/reflection/sessions/{id}/discard``.

    No fields. Discarding is unconditional — the recruiter has decided
    to walk away from this reflection entirely. The brief stays
    untouched.
    """

    model_config = ConfigDict(extra="forbid")


class ReflectionResponse(BaseModel):
    """Response payload for most reflection endpoints (POST/GET/PATCH)."""

    slice: Literal["v0-reflection-slice-1"] = Field(
        default="v0-reflection-slice-1"
    )
    session: ReflectionSession


class ReflectionCommitResponse(BaseModel):
    """Response payload for ``POST /api/reflection/sessions/{id}/commit``.

    Carries the freshly-committed session plus the new brief version
    path so the frontend can surface it (and link to the brief detail
    surface for inspection).
    """

    slice: Literal["v0-reflection-slice-1"] = Field(
        default="v0-reflection-slice-1"
    )
    session: ReflectionSession
    brief_version_path: str
    applied_hunks: list[dict]


class ReflectionActiveResponse(BaseModel):
    """Response payload for ``GET /api/reflection/sessions/active?brief_id=...``.

    Returns the active (non-terminal) reflection session for a brief,
    or ``session=None`` when there isn't one. Used by the workspace
    surface to decide whether to render the "review what Cloris read"
    pickup card.
    """

    slice: Literal["v0-reflection-slice-1"] = Field(
        default="v0-reflection-slice-1"
    )
    session: ReflectionSession | None
