// Wire types for the Cloris HTTP surface.
//
// Source of truth: cloris/models.py. Keep these literals byte-identical with
// the pydantic models there. The slice tags exist on every payload so the
// client can detect contract version skew without re-typing the literal at
// every consumption site.

export type Source = "linkedin" | "github" | "researcher" | "designer" | "exec_search";

export type WorkerState = "missing" | "alive" | "alive_silent" | "stale";

// Phase 1C: brief-vs-state-dir taxonomy. Mirrors cloris/models.py:EntryKind.
// See models.py docstring for the full classification semantics.
export type EntryKind =
  | "authored_brief"
  | "archived"
  | "intake_only"
  | "orphaned_state_dir";

export type StopResponseState = "stopping" | "missing" | "stale";

export interface RunSummary {
  id: number | null;
  status: string | null;
  stop_reason: string | null;
  mode: string | null;
  started_at: string | null;
  ended_at: string | null;
}

export interface StateDirEntry {
  source: Source;
  state_key: string;
  // Phase 1B: state_dir removed (R9 — no absolute paths in API responses).
  // If a surface needs a handle, compose `${source}/${state_key}`.
  runtime_state_present: boolean;
  runtime_state_corrupt: boolean;
  latest_run: RunSummary | null;
  brief_id_from_run: string | null;
  brief_path_from_worker: string | null;
  worker_json_present: boolean;
  worker_pid: number | null;
  worker_alive: boolean | null;
  worker_mode: string | null;
  worker_input_mode: string | null;
  resumable: boolean | null;
  worker_state: WorkerState;
  heartbeat_age_s: number | null;
  brief_role_title: string | null;
  brief_linkedin_project: string | null;
  brief_drift_since_last_run: boolean | null;
  attempt_health: AttemptHealthSummary | null;
  work_unit_progress: WorkUnitProgressSummary | null;
  run_stalled: boolean;
  stall_failure_kind: string | null;
  // Phase 1C: brief-vs-state-dir taxonomy. Defaults to "orphaned_state_dir"
  // server-side so partially-constructed payloads collapse to the safest
  // bucket; in production every entry receives an explicit kind.
  kind: EntryKind;
}

// Phase 1C: roll-up counts surfaced on /api/status. Replaces the
// 282/170/112 ribbon with recruiter-facing buckets.
export interface BriefCounts {
  active: number;
  working: number;
  paused: number;
  finished: number;
  lost: number;
  archived: number;
  orphaned: number;
}

export interface FailureKindCount {
  kind: string;
  count: number;
}

export interface AttemptHealthSummary {
  total_attempts_in_window: number;
  succeeded_in_window: number;
  failed_in_window: number;
  last_success_age_s: number | null;
  recent_failures: FailureKindCount[];
  dominant_failure_kind: string | null;
}

export interface WorkUnitProgressSummary {
  kind: "not_found" | "empty" | "counts";
  queued: number;
  in_progress: number;
  done: number;
  skipped: number;
  error: number;
}

// Phase F Slice F7: state-dir entries grouped by brief_id so home +
// filed surfaces can render one card per brief instead of one per
// (brief × module). `briefs` is additive — existing callers that read
// `entries` keep working.
export interface BriefStatusGroup {
  brief_id: string | null;
  brief_role_title: string | null;
  brief_linkedin_project: string | null;
  modules: StateDirEntry[];
}

export interface StatusResponse {
  slice: "v0-shell-slice-4";
  entries: StateDirEntry[];
  // Phase 1C: roll-up counts. Default-initialized server-side so payloads
  // from older callers (test fixtures, recorded captures) still parse —
  // missing field signals an old payload.
  counts?: BriefCounts;
  // Phase F Slice F7: present on every fresh response; missing on
  // older recorded captures.
  briefs?: BriefStatusGroup[];
}

// Phase F Slice F1 widened `source` to include "github" and added
// `mode` so launch + resume share one response shape. The slice tag
// stays at "v0-shell-slice-3" — additive Literal widening + an
// optional new field don't bump the skew-detection signal.
export interface LaunchResponse {
  slice: "v0-shell-slice-3";
  source: Source;
  input_mode: "concurrent";
  mode: "fresh" | "resume";
  pid: number;
  state_dir: string;
  worker_json_path: string;
}

export interface ResumeResponse {
  slice: "v0-shell-slice-4";
  source: Source;
  mode: "resume";
  input_mode: "concurrent";
  pid: number;
  state_dir: string;
  worker_json_path: string;
}

export interface StopResponse {
  slice: "v0-shell-slice-4";
  source: Source;
  state_key: string;
  state_dir: string;
  worker_state: StopResponseState;
  pid: number | null;
}

// Authored brief picker (LaunchForm). Mirrors cloris/models.py:BriefInfo.

export interface BriefInfo {
  path: string;
  role_title: string | null;
  linkedin_project: string | null;
  linkedin_project_id: string | null;
  modified_at: string;
  // Phase D Slice D1: library-only run metadata. Nullable so picker
  // callers (LaunchForm BriefPicker) keep their existing shape; library
  // surface (`#/briefs`) reads the decorated fields. Backend
  // populates via aggregate_briefs(decorate_runs=True).
  brief_id?: string | null;
  last_run_id?: number | null;
  last_run_at?: string | null;
  last_run_status?: string | null;
  last_run_source?: Source | null;
  total_runs?: number;
  total_saves?: number;
  // Phase F Slice F5: which discovery modules this brief targets.
  // Legacy briefs without the key serialize as null; LaunchForm
  // defaults to ["linkedin"] in that case (mirrors BriefDetail's
  // destinationModules helper).
  target_modules?: string[] | null;
}

export interface BriefsListResponse {
  slice: "v0-briefs-list-1";
  briefs: BriefInfo[];
}

// Phase D Slice D2. Brief detail / edit wire shape — matches the
// MergedBrief partition from shared/brief_v2_schema.py so PUT can
// roundtrip without backend disk re-read.
export interface BriefDetailResponse {
  slice: "v0-brief-detail-1";
  brief_id: string;
  path: string;
  role_title: string | null;
  v2_data: Record<string, unknown>;
  preserved_legacy: Record<string, unknown>;
  deprecated_keys: string[];
  unknown_keys: string[];
  last_modified: string;
  version_count: number;
  was_flat: boolean;
}

export interface BriefEditRequest {
  v2_data: Record<string, unknown>;
  preserved_legacy?: Record<string, unknown>;
  dropped_legacy_keys?: string[];
}

// Phase D Slice D5. Brief version history list.
export interface BriefVersionEntry {
  version_id: string;
  created_at: string;
  size_bytes: number;
}

export interface BriefVersionsResponse {
  slice: "v0-brief-versions-1";
  brief_id: string;
  versions: BriefVersionEntry[];
}

// Phase D Slice D9 (Ledger L4). Launch-readiness pre-flight payload.
// Mirrors cloris/models.py:LaunchReadinessResponse.
export type LaunchReadinessBlockerKind = "auth" | "config" | "net";

export interface LaunchReadinessBlocker {
  kind: LaunchReadinessBlockerKind;
  message: string;
  remediation: string;
}

export interface LaunchReadinessResponse {
  slice: "v0-launch-readiness-1";
  source: Source;
  brief_id: string;
  ready: boolean;
  blockers: LaunchReadinessBlocker[];
}

// Phase 1A: zombie-run reconciler.

export interface ReconciledRun {
  source: Source;
  state_key: string;
  run_id: number;
  new_status: string;
  stop_reason: string;
  reason: "missing_sidecar" | "bad_sidecar" | "pid_dead";
}

export interface ReconcileResponse {
  slice: "v0-reconciler-slice-1";
  applied: number;
  mutations: ReconciledRun[];
}

// --- Phase B: per-run report ---

export interface RunDetail {
  id: number;
  source: Source;
  brief_id: string | null;
  // Phase 1B: output_dir removed (R9 — no absolute paths on the wire).
  mode: string | null;
  status: string | null;
  stop_reason: string | null;
  started_at: string | null;
  ended_at: string | null;
  resumed_from_run_id: number | null;
  brief_role_title: string | null;
  brief_linkedin_project: string | null;
  brief_drift_since_run: boolean | null;
}

export interface CandidateDecisionSummary {
  candidate_id: number;
  display_name: string;
  profile_url: string;
  terminal_decision: string | null;
  confidence: number | null;
}

export interface DecisionCounts {
  total: number;
  by_decision: Record<string, number>;
}

export interface RunReportResponse {
  slice: "v0-shell-slice-b1";
  source: Source;
  state_key: string;
  // Phase 1B: state_dir removed (R9 — no absolute paths on the wire).
  run: RunDetail;
  work_unit_progress: WorkUnitProgressSummary;
  attempt_health: AttemptHealthSummary;
  decisions: DecisionCounts;
  candidates: CandidateDecisionSummary[];
  candidates_truncated: boolean;
}

// --- Phase C-bis 0.1: brief-first workspace + candidate detail ---

export interface LatestRunRef {
  source: Source;
  state_key: string;
  run_id: number;
}

// Phase F Slice F6: cross-source link metadata. One of the OTHER
// (source, candidate_id) pairs aggregated under the same canonical
// person from F3's identity resolver. The `describe` field carries
// the editorial prose (`describe_merge_signal()` output) so the
// frontend never sees raw `link_kind` enums.
export type CrossSourceLinkKind = "auto_strong" | "auto_medium" | "manual";

export interface CrossSourceLink {
  source: Source;
  state_key: string;
  candidate_id: number;
  profile_url: string;
  display_name: string;
  link_kind: CrossSourceLinkKind;
  describe: string;
}

// Phase G Slice G2: identity reconciliation surface wire types.
// Wire-distinct from CrossSourceLink because the identity surface needs
// the source/state_key/candidate_id triple even for the primary link
// plus the editorial describe prose for each row.
export interface IdentityCandidateLink {
  source: Source;
  state_key: string;
  candidate_id: number;
  link_kind: CrossSourceLinkKind;
  recruiter_locked: boolean;
  describe: string;
}

export interface IdentityPerson {
  person_id: number;
  canonical_name: string;
  canonical_handle: string;
  sources: IdentityCandidateLink[];
}

export interface IdentityPendingDecision {
  decision_id: number;
  person_a: IdentityPerson;
  person_b: IdentityPerson;
  signal_summary: string;
  created_at: string;
}

export interface IdentityPendingResponse {
  slice: "v0-identity-pending-1";
  brief_id: string;
  persons_total: number;
  decisions: IdentityPendingDecision[];
}

export interface IdentityDecisionRequest {
  decision_id: number;
  choice: "merge" | "keep_separate";
}

export interface IdentityUnlinkRequest {
  source: Source;
  state_key: string;
  candidate_id: number;
}

// Phase G Slice G3: Live Monitor wire types. Operational register —
// raw enums + dense table rows are correct here, NOT editorial.
export interface ActiveRunSummary {
  source: Source;
  state_key: string;
  run_id: number | null;
  run_status: string | null;
  stop_reason: string | null;
  started_at: string | null;
  ended_at: string | null;
  brief_id: string | null;
  brief_role_title: string | null;
  worker_pid: number | null;
}

export interface MonitorIndexResponse {
  slice: "v0-monitor-index-1";
  active_runs: ActiveRunSummary[];
}

export interface TelemetryAttemptRow {
  id: number;
  candidate_id: number;
  work_unit_id: number | null;
  stage: string;
  attempt_number: number;
  status: string;
  failure_kind: string | null;
  failure_reason: string | null;
  started_at: string;
  ended_at: string | null;
}

export interface TelemetryEventRow {
  id: number;
  event_type: string;
  candidate_id: number | null;
  attempt_id: number | null;
  payload_summary: string | null;
  created_at: string;
}

export interface RunTelemetryResponse {
  slice: "v0-run-telemetry-1";
  source: Source;
  state_key: string;
  run_id: number;
  attempts: TelemetryAttemptRow[];
  events: TelemetryEventRow[];
  last_event_at: string | null;
  attempts_total: number;
  events_total: number;
}

// Phase G Slice G4: Tools index + execution wire types.
export type ToolTier = "A" | "B" | "C";
export type ToolExecutionModel = "sync" | "async" | "cli_only";

export interface ToolSchemaField {
  name: string;
  type: string;
  required: boolean;
  default: unknown;
  description: string;
}

export interface ToolEntry {
  tool_id: string;
  tier: ToolTier;
  label: string;
  pitch: string;
  cli_command: string;
  execution_model: ToolExecutionModel;
  schema_fields: ToolSchemaField[];
}

export interface ToolsIndexResponse {
  slice: "v0-tools-index-1";
  tools: ToolEntry[];
}

export interface ToolRunSyncWire {
  slice: "v0-tool-sync-1";
  tool_id: string;
  exit_code: number;
  stdout_tail: string;
  stderr_tail: string;
}

export interface ToolRunAsyncWire {
  slice: "v0-tool-async-1";
  tool_id: string;
  job_id: string;
}

export interface ToolJobStatusWire {
  slice: "v0-tool-job-1";
  job_id: string;
  tool_id: string;
  status: "queued" | "running" | "succeeded" | "failed" | "purged";
  started_at: number;
  finished_at: number | null;
  exit_code: number | null;
  stdout_tail: string;
  stderr_tail: string;
  error_message: string | null;
}

// Phase G Slice G5: Settings transparency wire types.
export interface SettingsCredential {
  key: string;
  label: string;
  present: boolean;
  pitch: string;
}

export interface SettingsBriefSaveSummary {
  brief_id: string;
  role_title: string | null;
  target_modules: string[];
  linkedin_project_id: string | null;
}

export interface SettingsGovernorLimit {
  name: string;
  label: string;
  value: number | string;
  explainer: string;
}

export interface SettingsResponse {
  slice: "v0-settings-1";
  credentials: SettingsCredential[];
  save_destinations: SettingsBriefSaveSummary[];
  governor: SettingsGovernorLimit[];
  cdp_url: string;
}

export interface CandidateCardSummary {
  candidate_id: number;
  source: Source;
  identity_key: string;
  display_name: string;
  profile_url: string;
  terminal_decision: string;
  save_reason: string | null;
  confidence: number | null;
  first_seen_at: string | null;
  last_seen_at: string | null;
  user_status: string | null;
  // F6: empty when this person was only observed on a single source.
  cross_source_links?: CrossSourceLink[];
}

export interface WorkspaceResponse {
  slice: "v0-shell-slice-c5";
  brief_id: string;
  sources: Source[];
  brief_role_title: string | null;
  brief_linkedin_project: string | null;
  latest_run: LatestRunRef | null;
  total_saves: number;
  saves_this_week: number;
  shortlisted_count: number;
  last_save_at: string | null;
  candidates: CandidateCardSummary[];
}

export interface CandidateNoteEntry {
  body: string;
  created_at: string;
}

export type CandidateUserStatus =
  | "shortlist"
  | "parked"
  | "contacted"
  | "hidden";

// Phase D Slice D6 (Ledger L1). Closed-loop calibration signal — kept
// schema-distinct from CandidateUserStatus so future Next Run Learning
// surfaces never conflate pipeline action with judgment calibration.
// Allowed values mirror the API server's _ALLOWED_JUDGMENT_ACCURACIES.
export type CandidateJudgmentAccuracy =
  | "useful"
  | "wrong"
  | "off_rubric"
  | "overstated_depth"
  | "understated_depth";

export interface CandidateDetailResponse {
  slice: "v0-shell-slice-c5";
  source: Source;
  brief_id: string;
  candidate_id: number;
  identity_key: string;
  display_name: string;
  profile_url: string;
  terminal_decision: string | null;
  confidence: number | null;
  save_reason: string | null;
  current_lifecycle_state: string | null;
  first_seen_at: string | null;
  last_seen_at: string | null;
  source_run: LatestRunRef | null;
  brief_role_title: string | null;
  brief_linkedin_project: string | null;
  notes: CandidateNoteEntry[];
  user_status: CandidateUserStatus | string | null;
  is_failed_state: boolean;
  // Phase D Slice D6 (substrate from C-bis 0.5). Both fields ride on
  // the wire by default; the toggle reads + writes them.
  judgment_accuracy: CandidateJudgmentAccuracy | string | null;
  judgment_accuracy_at: string | null;
  // Phase F Slice F6: cross-source links for the Cross-source evidence
  // section. Empty when the person was observed on one source only.
  cross_source_links?: CrossSourceLink[];
  // Designer Slice 6: surface_type discriminates rendering branches in
  // CandidateDetail.svelte. Today recognized values: "hitl_visual_review"
  // (Designer module saves carry visual_judgment). Other modules add
  // their own surface_types as the multimodal pattern generalizes.
  // Legacy candidates omit this field; the renderer falls back to the
  // text-only save_reason rendering.
  surface_type?: string | null;
  // Designer Slice 6: structured visual-judgment payload, present
  // when surface_type === "hitl_visual_review". Shape mirrors
  // designer/vision_evaluation.py:VisualJudgment.to_dict() —
  // model + per-principle scoring + overall verdict + assets.
  visual_judgment?: VisualJudgmentPayload | null;
}

export interface VisualJudgmentPayload {
  model: string;
  principles: VisualJudgmentPrinciplePayload[];
  overall_verdict: "yes" | "no" | "borderline";
  overall_confidence: number;
  fallback_reason?: string;
  cost_estimate_usd?: number;
  // Slice 8 populates this on top-decile candidates.
  cross_check?: VisualJudgmentCrossCheckPayload | null;
  // Asset-reference table the prompt grounded itself in. Indexed by
  // image_id so VisualReviewBeforeAfter can resolve cited image_ids
  // to thumbnails + URLs.
  assets: VisualJudgmentAssetPayload[];
}

export interface VisualJudgmentPrinciplePayload {
  name: string;
  score: number;
  anchor: "bad" | "okay" | "good" | "excellent";
  reasoning: string;
  image_ids: number[];
  anchor_consistency_pass?: boolean;
}

export interface VisualJudgmentAssetPayload {
  id: number;
  url: string;
  thumbnail_url?: string;
  source: string;
  project_title: string;
}

export interface VisualJudgmentCrossCheckPayload {
  model: string;
  principles: VisualJudgmentPrinciplePayload[];
  overall_verdict: "yes" | "no" | "borderline";
  overall_confidence: number;
}

export interface LegacyResolveResponse {
  brief_id: string;
}

// --- Onboarding flow intake sessions (A24 trial plan, Slice 1B) ---

export type IntakeStep =
  | "welcome"
  | "role_basics"
  | "role_framing"
  | "good_looks_like"
  | "lookalikes"
  | "exemplars"
  // Designer Slice 4: rubric-authoring chapter for design briefs.
  // Sits between exemplars and search_stance so the rubric is the
  // last thing the recruiter touches before declaring search posture.
  // Non-design briefs skip this chapter via the chapter renderer's
  // applicability check (target_modules contains "designer").
  | "design_rubric"
  | "search_stance"
  | "anything_else"
  | "synthesis"
  | "review"
  | "completed";

export interface IntakeSession {
  id: number;
  brief_id_draft: string | null;
  role_title: string | null;
  current_step: IntakeStep;
  state_json: Record<string, unknown>;
  started_at: string;
  updated_at: string;
  completed_at: string | null;
  archived_at: string | null;
}

export interface IntakeSessionListResponse {
  slice: "v0-onboarding-slice-1";
  sessions: IntakeSession[];
}

export interface IntakeSessionResponse {
  slice: "v0-onboarding-slice-1";
  session: IntakeSession;
}

export interface IntakeSessionDeleteResponse {
  slice: "v0-onboarding-slice-1";
  deleted: boolean;
  id: number;
}

// Phase D Slice D3. Terminal call from the wizard — writes the V2
// draft to disk and stamps the session as completed in one step.
export interface IntakeSessionCompleteResponse {
  slice: "v0-onboarding-slice-1";
  session: IntakeSession;
  brief_id: string;
  brief_path: string;
}

// Phase E Slice E1: market viewer wire shapes. Mirrors
// `cloris/models.py:MarketSummary`/`MarketDetailResponse` etc.

export interface MarketSummary {
  market_key: string;
  role_title: string;
  role_level: string;
  geography: string;
  last_updated_at: string;
  run_count: number;
  saved_count: number;
  aggregate_save_rate: number | null;
}

export interface MarketsListResponse {
  slice: "v0-markets-list-1";
  markets: MarketSummary[];
}

export interface MarketLane {
  lane_key: string;
  domain_lane: string;
  novelty_bucket: string;
  status: string;
  candidates_seen: number;
  saves: number;
  save_rate: number | null;
  why_it_works: string | null;
  recommended_action: string | null;
}

export interface MarketTalentPool {
  pool_key: string;
  label: string;
  signal_strength: string;
  status: string;
  evidence_summary: string | null;
}

export interface MarketThesis {
  summary: string;
  supply_assessment: string;
  competition_assessment: string;
  external_context: string;
}

export interface MarketDetailResponse {
  slice: "v0-market-detail-1";
  market_key: string;
  role_title: string;
  role_level: string;
  geography: string;
  last_updated_at: string;
  run_count: number;
  saved_count: number;
  rejected_count: number;
  aggregate_save_rate: number | null;
  facial_yes_rate: number | null;
  lanes: MarketLane[];
  talent_pools: MarketTalentPool[];
  market_thesis: MarketThesis;
  // Engine's structured brief-edit proposals (target_field + proposal +
  // reason + confidence). Frontend's computeBriefDiff() walks this as
  // a fourth source. Default-empty so a server build that doesn't
  // include the field yet renders as "no recommendations" rather than
  // crashing.
  brief_recommendations: Array<Record<string, unknown>>;
}

// --- The Reflection — HITL Market Intelligence wire shapes ---
//
// Mirrors cloris/models.py:ReflectionSession etc. The state_json bag
// is loosely typed at the wire boundary because the engine owns its
// shape. Frontend code reads structured sub-keys via the helpers in
// lib/reflection/types.ts (which narrows where it matters and degrades
// gracefully where it doesn't).

export type ReflectionPhase =
  | "planning"
  | "plan_approved"
  | "researching"
  | "awaiting_diff"
  | "committed"
  | "discarded";

export interface ReflectionSession {
  id: number;
  brief_id: string;
  source_run_id: number | null;
  current_phase: ReflectionPhase;
  state_json: Record<string, unknown>;
  steering_iterations: number;
  started_at: string;
  updated_at: string;
  completed_at: string | null;
  discarded_at: string | null;
  brief_version_committed: string | null;
  research_error: string | null;
}

export interface ReflectionResponse {
  slice: "v0-reflection-slice-1";
  session: ReflectionSession;
}

export interface ReflectionActiveResponse {
  slice: "v0-reflection-slice-1";
  session: ReflectionSession | null;
}

export interface ReflectionCommitResponse {
  slice: "v0-reflection-slice-1";
  session: ReflectionSession;
  brief_version_path: string;
  applied_hunks: Array<Record<string, unknown>>;
}
