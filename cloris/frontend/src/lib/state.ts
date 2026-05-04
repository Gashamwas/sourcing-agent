// Cloris-state language. Pure frontend mapping from raw runtime enums to
// human-readable copy. Keep all backend literals out of the visible UI;
// route them through these helpers and route raw values through the
// Reference Slip if a developer needs to see them.
//
// No backend / contract changes; these are display-only.

import type { Source, StateDirEntry } from "./types";
import { humanizeStateKey } from "./display";

// The Cloris state of a card — a small, closed product vocabulary. Order
// in the union below mirrors the visual precedence (stalled > working >
// limit reached > interrupted > completed > lost track > away > no record
// > unknown) but the precedence itself lives in `clorisStateKind()` so
// the rules and the labels stay aligned.
//
// `stalled` is distinct from `lost-track`: stalled means the worker is
// alive (or the run is "running") but Cloris hasn't gotten anywhere —
// retries are dominating attempts. Lost-track means the worker process
// is stale (no heartbeat). One is a problem with the search; the other
// is a problem with the runner.
export type ClorisStateKind =
  | "stalled"
  | "working"
  | "limit-reached"
  | "interrupted"
  | "completed"
  | "lost-track"
  | "away"
  | "no-record"
  | "unknown";

// The card's Cloris state. This is the human-language equivalent of the
// "status kind" the row used to compute. Renamed: nothing here mentions
// workers or runs directly to the user.
export function clorisStateKind(
  entry: StateDirEntry,
  optimisticallyStopping: boolean
): ClorisStateKind {
  if (optimisticallyStopping) return "working";
  const runStatus = entry.latest_run?.status;
  // Stalled wins over working: an alive/running worker that the backend
  // marked stalled is *not* progressing. The user needs to see "stuck",
  // not "she's on it".
  if (
    entry.run_stalled === true &&
    (entry.worker_state === "alive" || runStatus === "running")
  ) {
    return "stalled";
  }
  if (runStatus === "interrupted") return "interrupted";
  if (runStatus === "governor_limit_reached") return "limit-reached";
  // Phase 1A: the reconciler marks zombie runs status='abandoned' when
  // the worker process has died (no sidecar / dead PID). The UI honors
  // that with the 'lost-track' pill so the recruiter sees a truthful
  // signal instead of a "Working" lie. The mapping fires regardless of
  // the current worker_state because the run row is the durable truth
  // post-reconciliation; the sidecar may have already been overwritten
  // by a subsequent launch.
  if (runStatus === "abandoned") return "lost-track";
  if (entry.worker_state === "alive") return "working";
  if (entry.worker_state === "stale") return "lost-track";
  if (!entry.runtime_state_present) return "no-record";
  if (runStatus === "running") return "working";
  if (runStatus === "completed") return "completed";
  if (runStatus === null || runStatus === undefined) return "no-record";
  return "unknown";
}

// Sentence-case label rendered as the right-aligned status pill on a
// card. R22/R25: one canonical wording per state-kind. Sentence-case
// (not Title Case) so the pill reads as a plain label, not a shouting
// SaaS-banner. The pill CSS no longer applies text-transform: uppercase,
// so what's returned here is what the user sees verbatim.
export function clorisStateLabel(kind: ClorisStateKind): string {
  switch (kind) {
    case "stalled":
      return "Stalled";
    case "working":
      return "Working";
    case "limit-reached":
      return "Paused";
    case "interrupted":
      return "Stopped";
    case "completed":
      return "Completed";
    case "lost-track":
      return "Lost track";
    case "away":
      return "Away";
    case "no-record":
      return "No record";
    case "unknown":
      // R24: editorial-register fallback for state-machine values that don't
      // map onto the explicit kinds above. "Unknown" reads as a system
      // confessing it doesn't know; "Unresolved" frames the same situation
      // honestly without leaking diagnostic vocabulary into the pill.
      return "Unresolved";
  }
}

// Inline lower-case sentence form for the "Last Mark" field on the card
// face. This is what the user reads as "what was Cloris doing here" —
// short, plain English, no internal enum names.
export function clorisStateInline(kind: ClorisStateKind): string {
  switch (kind) {
    case "stalled":
      return "stalled";
    case "working":
      return "working";
    case "limit-reached":
      return "limit reached";
    case "interrupted":
      return "interrupted";
    case "completed":
      return "completed";
    case "lost-track":
      return "lost track";
    case "away":
      return "away";
    case "no-record":
      return "no card record";
    case "unknown":
      return "unresolved";
  }
}

// Plain-English presentation for the run.stop_reason enum coming from
// the backend. R24: no raw API values like `governor_limit_reached`
// reach the user — they route through this function. The previous
// `r.run.stop_reason.replace(/_/g, " ")` rendering bypassed presentation
// and produced phrases like "governor limit" that mean nothing to a
// recruiter.
//
// Canonical wire domain comes from `shared/safety/stop_reasons.py`
// (`RunStopReason`). G1 closes a Phase G L14 audit that found the
// previous allow-list missed 6 of 10 canonical enum values — they fell
// through to the snake_case raw render. Legacy keys (`governor_limit_reached`,
// `interrupted`, `error`) are kept as defensive shims for any historical
// rows whose stop_reason wasn't normalized through `_split_stop_reason`.
export function clorisStopReasonLabel(stopReason: string | null): string {
  if (stopReason === null) return "";
  switch (stopReason) {
    // Canonical RunStopReason values:
    case "normal":
      return "Completed";
    case "governor_limit":
      return "Hit the daily limit";
    case "session_expired":
      return "Browser session timed out";
    case "operator_stop":
      return "Stopped by operator";
    case "operator_pause":
      return "Paused";
    case "lock_conflict":
      return "Another worker had the lock";
    case "browser_disconnect_unrecovered":
      return "Lost the browser session";
    case "api_budget_exhausted":
      return "Hit the API budget";
    case "fatal_runtime_error":
      return "Errored";
    case "worker_missing":
      // Phase 1A: reconciler-set stop_reason. The recruiter-facing
      // framing emphasizes that Cloris (as a service) doesn't know what
      // happened — not that the technical worker process died.
      return "Cloris lost track of this run";
    // Legacy aliases (defensive shims for pre-canonical-enum rows):
    case "governor_limit_reached":
      return "Hit the daily limit";
    case "interrupted":
      return "Stopped";
    case "error":
      return "Errored";
    default:
      // Unknown wire literal — best-effort plain rendering.
      return stopReason.replace(/_/g, " ");
  }
}

// Cloris-side rendering of the worker_state enum. The user sees Cloris,
// not the worker. "alive" -> working, "stale" -> lost track, "missing" ->
// away. The optimistic-stopping flag overrides the underlying state so
// the UI stays honest while a stop is in flight.
export type ClorisWorkerLabel =
  | "Working"
  | "Lost track"
  | "Away"
  | "Stopping…";

export function clorisWorkerLabel(
  entry: StateDirEntry,
  optimisticallyStopping: boolean
): ClorisWorkerLabel {
  if (optimisticallyStopping) return "Stopping…";
  if (entry.worker_state === "alive") return "Working";
  if (entry.worker_state === "stale") return "Lost track";
  return "Away";
}

export function clorisWorkerNeedsAttention(
  entry: StateDirEntry,
  optimisticallyStopping: boolean
): boolean {
  if (optimisticallyStopping) return true;
  return entry.worker_state === "stale";
}

// Pull (resume) availability label on the card face. The card-face copy
// reads "ready to pull", "nothing pending", or "—". Catalog detail uses
// the raw resumable enum if a developer wants to see it.
export function clorisPullLabel(entry: StateDirEntry): string {
  if (entry.resumable === true) return "ready to pull";
  if (entry.resumable === false) return "nothing pending";
  return "—";
}

// Canonical RunStopReason wire domain — mirrors `shared/safety/stop_reasons.py`.
// Mirrored here so frontend tests can pin coverage of the backend enum
// without scraping Python. Keep this list in sync when the backend adds
// new reasons; `clorisStopReasonLabel` and `STOP_REASON_COPY` must
// handle every value.
export const CANONICAL_STOP_REASONS = [
  "normal",
  "governor_limit",
  "session_expired",
  "operator_stop",
  "operator_pause",
  "lock_conflict",
  "browser_disconnect_unrecovered",
  "api_budget_exhausted",
  "fatal_runtime_error",
  "worker_missing"
] as const;
export type CanonicalStopReason = (typeof CANONICAL_STOP_REASONS)[number];

// Stop-reason copy. A small allow-list of codes we know how to render in
// product language. Anything else falls back to a softened, sentence-case
// rendering of the raw code. The raw value is still available via the
// Reference Slip.
//
// Canonical wire domain comes from `shared/safety/stop_reasons.py`
// (`RunStopReason`). Legacy keys (`governor_limit_reached`, `user_stop`,
// `worker_killed`, `worker_crashed`, `browser_session_lost`) are kept as
// defensive shims for any pre-canonical-enum data still in production
// state DBs — `_split_stop_reason` normalizes new writes to the canonical
// set, but historical rows may carry the old strings.
const STOP_REASON_COPY: Record<string, string> = {
  // Canonical RunStopReason values:
  normal: "ended cleanly",
  governor_limit: "limit reached",
  session_expired: "session timed out",
  operator_stop: "stopped by you",
  operator_pause: "paused",
  lock_conflict: "another worker had the lock",
  browser_disconnect_unrecovered: "browser disconnected",
  api_budget_exhausted: "hit the API budget",
  fatal_runtime_error: "Cloris stopped unexpectedly",
  worker_missing: "lost track",
  // Legacy aliases (defensive shims):
  governor_limit_reached: "limit reached",
  browser_session_lost: "browser disconnected",
  user_stop: "stopped by you",
  worker_killed: "stopped",
  worker_crashed: "Cloris stopped unexpectedly"
};

// Returns a humanized stop-reason or null when there is nothing
// meaningful to surface (no run, or run ended cleanly with no reason
// worth surfacing on the card face).
export function clorisStopReasonInline(entry: StateDirEntry): string | null {
  const reason = entry.latest_run?.stop_reason;
  if (!reason) return null;
  if (reason === "normal") return null;
  const mapped = STOP_REASON_COPY[reason];
  if (mapped !== undefined) return mapped;
  // Soft fallback: turn snake_case into a sentence. Don't echo backend
  // literals verbatim into the UI.
  return reason.replace(/_/g, " ").toLowerCase();
}

// A small allow-list of stall failure kinds that the backend reports
// in `stall_failure_kind`. Anything outside the allow-list falls through
// to a softened snake_case → space rendering so the user never sees
// `http_429` style literals.
const STALL_FAILURE_COPY: Record<string, string> = {
  http_408: "request timeout",
  http_409: "conflict",
  http_425: "too early",
  http_429: "rate limited",
  http_500: "provider error",
  http_502: "provider error",
  http_503: "provider error",
  http_504: "provider error",
  rate_limit: "rate limited",
  browser_disconnect: "browser disconnected",
  timeout: "timed out",
  capacity: "provider over capacity"
};

// Humanize a failure-kind code or return null when there's nothing to
// surface. Used by the stall banner and the attempt-health summary.
export function clorisFailureKindLabel(kind: string | null): string | null {
  if (!kind) return null;
  if (kind in STALL_FAILURE_COPY) return STALL_FAILURE_COPY[kind];
  return kind.replace(/_/g, " ").toLowerCase();
}

// Stall reason for the Card Detail. Returns the humanized failure kind
// when the card is stalled, or null when it isn't.
export function clorisStallReason(entry: StateDirEntry): string | null {
  if (entry.run_stalled !== true) return null;
  return clorisFailureKindLabel(entry.stall_failure_kind);
}

// Work-unit progress for the Card Detail. Returns `{done, total, percent}`
// when the backend has counted units, or null when nothing meaningful is
// available (kind="not_found" or "empty", or all counts are zero).
export interface ClorisProgress {
  done: number;
  total: number;
  percent: number;
}

export function clorisProgress(entry: StateDirEntry): ClorisProgress | null {
  const wu = entry.work_unit_progress;
  if (!wu || wu.kind !== "counts") return null;
  const total =
    wu.queued + wu.in_progress + wu.done + wu.skipped + wu.error;
  if (total === 0) return null;
  const completed = wu.done + wu.skipped + wu.error;
  return {
    done: wu.done,
    total,
    percent: total === 0 ? 0 : Math.round((completed / total) * 100)
  };
}

// Attempt-health summary for the Reference Slip. Returns small render-
// ready phrases or null when there's nothing to show. The recent_failures
// histogram is summarized as "<dominant_kind> in N of M" — the
// recruiter-readable version of the underlying counts.
export interface ClorisAttemptSummary {
  lastSuccess: string | null;        // e.g. "12 minutes ago"
  failureLine: string | null;        // e.g. "rate limited in 9 of 11"
  totalAttempts: number;
}

export function clorisAttemptSummary(
  entry: StateDirEntry
): ClorisAttemptSummary | null {
  const ah = entry.attempt_health;
  if (!ah) return null;
  if (ah.total_attempts_in_window === 0 && ah.last_success_age_s === null) {
    return null;
  }
  return {
    lastSuccess: formatAge(ah.last_success_age_s),
    failureLine:
      ah.dominant_failure_kind && ah.failed_in_window > 0
        ? `${clorisFailureKindLabel(ah.dominant_failure_kind)} in ${ah.failed_in_window} of ${ah.total_attempts_in_window}`
        : null,
    totalAttempts: ah.total_attempts_in_window
  };
}

// Format a number of seconds into a coarse human relative time. Inputs
// are bucketed (just-now / minutes / hours / days) so the surface stays
// stable across polls — small jitter on the underlying age would make
// fine-grained text twitch every second.
function formatAge(seconds: number | null): string | null {
  if (seconds === null || seconds < 0) return null;
  if (seconds < 60) return "just now";
  if (seconds < 3600) {
    const mins = Math.floor(seconds / 60);
    return `${mins} minute${mins === 1 ? "" : "s"} ago`;
  }
  if (seconds < 86400) {
    const hrs = Math.floor(seconds / 3600);
    return `${hrs} hour${hrs === 1 ? "" : "s"} ago`;
  }
  const days = Math.floor(seconds / 86400);
  return `${days} day${days === 1 ? "" : "s"} ago`;
}

// ----- Phase B refactor — decision-class classifier + run summary -----

// Recruiter-facing decision categories. Maps the wide wire-literal
// decision space onto five classes that drive grouping, ordering, and
// visual weight in the run report and, later, the candidate workspace.
//
// Why classes:
//   - "Save" outcomes (SAVE / INFERENTIAL_SAVE / TRANSFERABLE_SAVE /
//     SIGNAL_SAVE) are the recruiter-actionable headline.
//   - "Borderline" surfaces FACIAL_BORDERLINE — Cloris signaling she's
//     unsure; the recruiter looks.
//   - "Reject" is REJECT only — passed the facial gate, rejected on
//     substance. Recruiter-readable but not headline.
//   - "Filtered" is the noise: facial-gate filter outcomes, parse /
//     judgment failures, geo / pre-screen filters, insufficient data.
//     Aggregated as a single bucket; never shown as separate histogram
//     bars.
//   - "In progress" is null terminal_decision — the candidate is still
//     being processed.
export type ClorisDecisionClass =
  | "save"
  | "borderline"
  | "reject"
  | "filtered"
  | "in-progress";

const SAVE_DECISIONS = new Set([
  "SAVE",
  "INFERENTIAL_SAVE",
  "TRANSFERABLE_SAVE",
  "SIGNAL_SAVE"
]);

const FILTERED_DECISIONS = new Set([
  "FACIAL_NO",
  "FACIAL_SKIP",
  "GEO_FILTERED",
  "PRESCREEN_SKIP",
  "INSUFFICIENT_DATA",
  "PARSE_FAILURE",
  "JUDGMENT_FAILURE"
]);

export function clorisDecisionClass(
  decision: string | null
): ClorisDecisionClass {
  if (decision === null || decision === undefined || decision === "") {
    return "in-progress";
  }
  if (SAVE_DECISIONS.has(decision)) return "save";
  if (decision === "FACIAL_BORDERLINE") return "borderline";
  if (decision === "REJECT") return "reject";
  if (FILTERED_DECISIONS.has(decision)) return "filtered";
  // FACIAL_YES is intentionally absent from SAVE / FILTERED — it's a
  // transitional outcome that should not appear as a terminal_decision.
  // If a legacy DB still surfaces it, treat as in-progress (fail-safe).
  if (decision === "FACIAL_YES") return "in-progress";
  // Unknown wire literal: treat as filtered (noise) so it doesn't
  // accidentally inflate the save / reject lanes.
  return "filtered";
}

// Tally decisions in a histogram by class. Used by both the Decisions
// section (render the histogram) and the candidate-list grouping (size
// each group's "Show all N" affordance).
export interface DecisionClassCounts {
  save: number;
  borderline: number;
  reject: number;
  filtered: number;
  in_progress: number;
  total: number;
}

export function tallyDecisionClasses(
  byDecision: Record<string, number>
): DecisionClassCounts {
  const counts: DecisionClassCounts = {
    save: 0,
    borderline: 0,
    reject: 0,
    filtered: 0,
    in_progress: 0,
    total: 0
  };
  for (const [decision, n] of Object.entries(byDecision)) {
    const cls = clorisDecisionClass(decision);
    counts.total += n;
    if (cls === "save") counts.save += n;
    else if (cls === "borderline") counts.borderline += n;
    else if (cls === "reject") counts.reject += n;
    else if (cls === "filtered") counts.filtered += n;
    else counts.in_progress += n;
  }
  return counts;
}

// One-sentence tl;dr for the run-report headline. The phrasing branches
// by run status so the recruiter sees the answer ("0 saves") before the
// detail. Shape held tight on purpose — this is the one editorial line
// of the surface, not a paragraph.
export interface RunSummaryShape {
  status: string | null;
  stop_reason: string | null;
  started_at: string | null;
  ended_at: string | null;
  decisions_by_decision: Record<string, number>;
  attempt_health: {
    total_attempts_in_window: number;
    failed_in_window: number;
    last_success_age_s: number | null;
    dominant_failure_kind: string | null;
  } | null;
  work_unit_progress: {
    kind: string;
    queued: number;
    in_progress: number;
    done: number;
    skipped: number;
    error: number;
  };
}

export function clorisRunSummaryLine(report: RunSummaryShape): string {
  const counts = tallyDecisionClasses(report.decisions_by_decision);
  const saveCount = counts.save + counts.borderline; // borderline reads as "to review"
  const rejectCount = counts.reject;
  const total = counts.total;
  const status = report.status;

  // Stalled overrides any other status: if we're alive but failing, say
  // so. The run-report response doesn't carry `worker_state`, so we
  // infer stalled from attempt-health: lots of recent failures, no
  // recent success.
  const stalled = isStalled(report);
  if (stalled) {
    const failure = clorisFailureKindLabel(
      report.attempt_health?.dominant_failure_kind ?? null
    );
    const lastSuccess = formatAgeSeconds(
      report.attempt_health?.last_success_age_s ?? null
    );
    const tail = failure
      ? `Most attempts now ${failure}.`
      : "Most attempts are failing.";
    if (lastSuccess) {
      return `Stalled. Last success ${lastSuccess}. ${tail}`;
    }
    return `Stalled. ${tail}`;
  }

  if (status === "running") {
    const done = report.work_unit_progress.done;
    return `She's still going. ${pluralize(saveCount, "save", "saves")} so far, ${done} of ${nounTotal(total)} evaluated.`;
  }

  if (status === "governor_limit_reached") {
    const startShort = formatShortClock(report.started_at);
    const endShort = formatShortClock(report.ended_at);
    const tail =
      startShort && endShort
        ? ` Started ${startShort}; paused ${endShort}.`
        : "";
    return `Limit reached. ${pluralize(saveCount, "save", "saves")}, ${pluralize(rejectCount, "reject", "rejects")} across ${nounTotal(total)}.${tail}`;
  }

  if (status === "interrupted") {
    return `Interrupted. ${pluralize(saveCount, "save", "saves")}, ${pluralize(rejectCount, "reject", "rejects")} across ${nounTotal(total)}.`;
  }

  if (status === "completed") {
    if (saveCount > 0) {
      return `Completed. Saved ${saveCount} of ${nounTotal(total)} evaluated.`;
    }
    return `Completed. Nothing met the bar — ${nounTotal(total)} evaluated, 0 saved.`;
  }

  // Default / unknown status.
  return `${pluralize(saveCount, "save", "saves")}, ${pluralize(rejectCount, "reject", "rejects")} across ${nounTotal(total)}.`;
}

// Stalled inference for the run-summary line. Mirrors
// cloris/control_plane.py's stalled classifier in spirit: alive recent
// activity, dominated by failures, no recent success. Read-only — does
// not consult worker_state.
function isStalled(report: RunSummaryShape): boolean {
  const ah = report.attempt_health;
  if (!ah) return false;
  if (report.status !== "running") return false;
  if (ah.total_attempts_in_window < 3) return false;
  if (ah.failed_in_window === 0) return false;
  if (ah.failed_in_window / ah.total_attempts_in_window < 0.8) return false;
  // Last-success threshold: if a success landed in the last 5 minutes,
  // we're not stalled — failures in window are within recoverable range.
  if (ah.last_success_age_s !== null && ah.last_success_age_s < 300) {
    return false;
  }
  return true;
}

// Render N candidates / saves / rejects with the right pluralization.
function pluralize(
  n: number,
  singular: string,
  plural: string
): string {
  return `${n} ${n === 1 ? singular : plural}`;
}

function nounTotal(n: number): string {
  return pluralize(n, "candidate", "candidates");
}

// Compact "Apr 28, 7:58 PM" format for the run-summary line. Returns
// null when the input is missing/unparseable so the caller can drop
// the timing tail rather than render "Started null".
function formatShortClock(value: string | null): string | null {
  if (!value) return null;
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return null;
  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit"
  }).format(parsed);
}

function formatAgeSeconds(seconds: number | null): string | null {
  if (seconds === null || seconds < 0) return null;
  if (seconds < 60) return "just now";
  if (seconds < 3600) {
    const mins = Math.floor(seconds / 60);
    return `${mins} minute${mins === 1 ? "" : "s"} ago`;
  }
  if (seconds < 86400) {
    const hrs = Math.floor(seconds / 3600);
    return `${hrs} hour${hrs === 1 ? "" : "s"} ago`;
  }
  const days = Math.floor(seconds / 86400);
  return `${days} day${days === 1 ? "" : "s"} ago`;
}

// Last-mark formatter. The most recent meaningful run timestamp from the
// payload, rendered as a localized human date/time string. Returns null
// when there is no timestamp at all — the card face renders "—" in that
// case rather than an empty value.
export function clorisLastMark(entry: StateDirEntry): string | null {
  const value = entry.latest_run?.ended_at ?? entry.latest_run?.started_at;
  if (!value) return null;
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return null;
  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit"
  }).format(parsed);
}

// Phase 2A: title resolver — one canonical chain for every recruiter-facing
// title across the homescreen, run report, and any future surface.
//
// Why this lives here, not in display.ts: R24 ("one canonical wording per
// state") puts state vocabulary in this file; titles are a special case
// of state-vocabulary because two distinct briefs ending up with the same
// title is a state-collision bug. By co-locating here, every surface that
// reads a title goes through the same function.
//
// Three-step fallback chain:
//   1. brief_role_title — the human label authored in the brief.
//   2. humanized state_key — only when state_key is slug-shaped (starts
//      with a letter). "research_engineer_colombia" → "Research Engineer
//      Colombia". Pure-numeric LinkedIn project ids and date-suffixed
//      hyphenated keys are NOT humanized — those fall through to (3).
//   3. Source-typed generic with a disambiguator subtitle.
//      `{primary: "LinkedIn search", subtitle: "#1990251114"}`. This is
//      the fix for the "LinkedIn card" collision: two distinct briefs
//      that previously rendered identically as "LinkedIn card" now share
//      a primary line but carry distinct mono-caps subtitles, so the
//      visual identity of each card is unambiguous.

export interface TitleResolution {
  primary: string;
  subtitle?: string;
  source:
    | "role_title"
    | "role_title_with_disambiguator"
    | "humanized_state_key"
    | "source_generic_with_disambiguator";
}

// A state_key is "slug-shaped" when it starts with a letter and contains
// at least one letter. Numeric LinkedIn project ids ("1990251114") and
// keys whose first token is purely numeric ("1957683706-clean-20260413")
// fall outside this and route to the generic fallback.
function isSlugShaped(stateKey: string): boolean {
  return /^[a-zA-Z]/.test(stateKey) && /[a-zA-Z]/.test(stateKey);
}

function sourceGenericLabel(source: Source): string {
  if (source === "linkedin") return "LinkedIn search";
  if (source === "github") return "GitHub search";
  return "Sourcing search";
}

export function resolveRecruiterTitle(entry: StateDirEntry): TitleResolution {
  const role = entry.brief_role_title?.trim();
  if (role) {
    return { primary: role, source: "role_title" };
  }
  const stateKey = entry.state_key.trim();
  if (isSlugShaped(stateKey)) {
    return {
      primary: humanizeStateKey(stateKey, entry.source),
      source: "humanized_state_key",
    };
  }
  // Source-typed fallback with disambiguator. The subtitle is what
  // prevents collisions: two LinkedIn searches with different state_keys
  // now have visually distinct cards even though the primary line matches.
  return {
    primary: sourceGenericLabel(entry.source),
    subtitle: stateKey ? `#${stateKey}` : undefined,
    source: "source_generic_with_disambiguator",
  };
}

// Convenience for surfaces that have only (source, state_key) and not a
// full StateDirEntry — typically the run-report page when the URL params
// are the only source of truth.
export function resolveRecruiterTitleFromKey(
  source: Source,
  stateKey: string,
  briefRoleTitle?: string | null,
): TitleResolution {
  // Synthesize a minimal entry for resolveRecruiterTitle. We only need
  // the three fields it reads.
  const stub = {
    source,
    state_key: stateKey,
    brief_role_title: briefRoleTitle ?? null,
  } as unknown as StateDirEntry;
  return resolveRecruiterTitle(stub);
}

// Collision-aware bulk resolver. When two or more entries' single-entry
// resolutions collapse onto the same `primary`, this appends a
// `#<state_key>` subtitle so the cards stay visually distinct on the
// homescreen + filed surfaces. Closes the R2-COLLISION audit-rule
// violation that fires when legacy data has multiple briefs sharing the
// same `brief_role_title` (e.g. an original brief and a later "clean"
// re-run state_dir).
//
// Why a Map keyed by `${source}/${state_key}`: the consumer iterates
// rows post F7-dedup and looks up its resolution; a flat list would
// force an N² scan. The key shape mirrors `rowKey()` used across the
// home + filed surfaces.
//
// Single-entry callers (RunReportPage, Workspace, etc.) keep using
// `resolveRecruiterTitle` / `resolveRecruiterTitleFromKey` — collisions
// only matter on multi-row surfaces.
export function resolveRecruiterTitlesWithCollisions(
  entries: StateDirEntry[],
): Map<string, TitleResolution> {
  const out = new Map<string, TitleResolution>();
  const primaryCounts = new Map<string, number>();
  for (const entry of entries) {
    const resolution = resolveRecruiterTitle(entry);
    out.set(`${entry.source}/${entry.state_key}`, resolution);
    primaryCounts.set(
      resolution.primary,
      (primaryCounts.get(resolution.primary) ?? 0) + 1,
    );
  }
  for (const entry of entries) {
    const key = `${entry.source}/${entry.state_key}`;
    const resolution = out.get(key);
    if (!resolution) continue;
    // Skip non-collisions and entries that already carry a subtitle
    // (the source-typed-fallback branch already disambiguates).
    if ((primaryCounts.get(resolution.primary) ?? 0) < 2) continue;
    if (resolution.subtitle !== undefined) continue;
    const stateKey = entry.state_key.trim();
    if (!stateKey) continue;
    out.set(key, {
      ...resolution,
      subtitle: `#${stateKey}`,
      source: "role_title_with_disambiguator",
    });
  }
  return out;
}

// ── Two-Register Card: action hint ──────────────────────────────
// Maps a card's Cloris state to a short action verb displayed on the
// collapsed card face ("Resume →", "Investigate →"). Returns null
// when no recruiter action is needed (working, away, no-record).
//
// `verb` tells the template which click handler to wire:
//   resume   → fire onPullAndResume() directly from the collapsed face
//   report   → navigate to the run-report page
//   navigate → expand the card so the recruiter can see details

export type ActionHintVerb = "resume" | "report" | "navigate";

export interface ActionHint {
  label: string;
  verb: ActionHintVerb;
}

export function clorisActionLabel(
  kind: ClorisStateKind,
  resumable: boolean,
): ActionHint | null {
  switch (kind) {
    case "limit-reached":
    case "interrupted":
      return resumable ? { label: "Resume", verb: "resume" } : null;
    case "lost-track":
      return { label: "Investigate", verb: "navigate" };
    case "stalled":
      return { label: "Check stall", verb: "navigate" };
    case "completed":
      return { label: "Read report", verb: "report" };
    case "working":
    case "away":
    case "no-record":
    case "unknown":
      return null;
  }
}
