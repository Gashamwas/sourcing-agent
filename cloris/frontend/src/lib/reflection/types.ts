// Reflection-flow narrowed types — the wire shape (lib/types.ts) keeps
// state_json loose; this module narrows the bits the frontend actually
// reads. Defaults degrade gracefully when fields are missing so the
// UI never crashes on partially-populated sessions.

import type { BaseBriefChange, BriefChangeKind } from "../briefChanges";
import type { ReflectionSession } from "../types";

export interface ReflectionIntention {
  text: string;
  priority: "high" | "medium" | "low";
}

// EditorialBriefing — Cloris-voice reflection produced by the polish
// backend (market_intelligence/briefing_polish.py:EditorialBriefing).
// `source` is one of "llm" | "deterministic" | "empty"; `confidence`
// is programmatic (heuristic = signal-density populated_fields/6;
// LLM = containment-check pass=1.0/fail=0.4-cascade).
export interface ReflectionEditorialBriefing {
  paragraph: string;
  intentions: ReflectionIntention[];
  confidence: number;
  source: "llm" | "deterministic" | "empty" | string;
}

export interface ReflectionPlanBlock {
  // Primary briefing field, written by the polish backend.
  briefing: ReflectionEditorialBriefing;
  // editorial_briefing + intentions are kept on the type as back-compat
  // surface for sessions persisted before the polish backend shipped
  // (the Day-1 trial cutover): the reader collapses old shape into the
  // briefing field so consumers always have one place to read from.
  editorial_briefing: string;
  intentions: ReflectionIntention[];
  should_collect_external: boolean;
  should_collect_edge_case: boolean;
  // The full PlannerResult is in here too but the UI doesn't read its
  // structure directly — it surfaces in the Reference Slip as raw JSON.
  planner_result?: Record<string, unknown>;
}

export interface ReflectionResearchBlock {
  external_result: Record<string, unknown> | null;
  skip_reason: string | null;
  stage_errors: string[];
  summary: {
    sources: number;
    findings: number;
    implications: number;
  };
}

// Re-export of the base diff kind so existing consumers can keep
// importing from this module unchanged.
export type ReflectionHunkKind = BriefChangeKind;

export type ReflectionHunkSection =
  | "additional_search_terms"
  | "employer_signal_rules"
  | "search_priorities"
  | "instructions"
  | "notes"
  | "capability_areas"
  | "depth_distinction"
  | "non_fit_patterns"
  | "talent_pool_review";

// A reflection hunk extends BaseBriefChange (shared with BriefDiffEntry
// in lib/briefDiff.ts) with reflection-specific card chrome:
// - hunk_id: opaque identifier for the per-hunk approve/skip toggle
// - label: short editorial label rendered in the card header
// - confidence: 0.0-1.0; drives default_approved and visual weight
// - default_approved: starting state for the approve/skip toggle
// - target_field: the engine's structured target_field; may differ
//   from `field` when the engine maps a recommendation onto a
//   recruiter-readable section (e.g. employer_proxy → employer_signal_rules)
//
// `field` and `kind` come from the base; `rationale` and `before` are
// optional in the base but always populated by the engine emitter.
export interface ReflectionHunk extends BaseBriefChange {
  hunk_id: string;
  section: ReflectionHunkSection | string;
  label: string;
  rationale: string;
  confidence: number;
  default_approved: boolean;
  target_field: string;
}

export interface ReflectionProposeBlock {
  hunks: ReflectionHunk[];
  artifact?: Record<string, unknown>;
  agent_state?: Record<string, unknown>;
  critic_summary?: string;
  stage_errors?: string[];
  brief_at_propose?: Record<string, unknown>;
}

export interface ReflectionContextBlock {
  brief_path: string;
  run_dir: string | null;
  mode: string;
  market_identity?: Record<string, unknown>;
}

export interface ReflectionSteeringHistoryItem {
  iteration: number;
  note: string;
  timestamp: string;
}

// Narrowed view of session.state_json.
//
// Schema evolution: the v2 polish backend writes a single `briefing`
// object with paragraph / intentions / confidence / source. Sessions
// persisted before that ship have flat `editorial_briefing` + `intentions`
// at the top of the plan block. This reader prefers the `briefing` shape
// and falls back to the flat shape so in-flight pre-cutover sessions
// still render. Both ReadingShape consumers (the briefing paragraph
// surface and the intentions list) get one normalized place to read from.
export function readPlanBlock(
  session: ReflectionSession
): ReflectionPlanBlock | null {
  const phaseOutputs = session.state_json?.phase_outputs as
    | Record<string, unknown>
    | undefined;
  const plan = phaseOutputs?.plan as Record<string, unknown> | undefined;
  if (!plan || typeof plan !== "object") return null;

  const rawBriefing = plan.briefing as Record<string, unknown> | undefined;

  // Resolve paragraph: briefing.paragraph wins; fall back to flat field.
  const paragraph =
    (rawBriefing && typeof rawBriefing.paragraph === "string"
      ? rawBriefing.paragraph
      : null) ??
    (typeof plan.editorial_briefing === "string"
      ? plan.editorial_briefing
      : "");

  // Resolve intentions: briefing.intentions wins; fall back to flat array.
  const rawIntentionsCandidate = rawBriefing?.intentions ?? plan.intentions;
  const rawIntentions = Array.isArray(rawIntentionsCandidate)
    ? rawIntentionsCandidate
    : [];
  const intentions: ReflectionIntention[] = rawIntentions
    .filter(
      (item): item is Record<string, unknown> =>
        !!item && typeof item === "object"
    )
    .map((item) => ({
      text: typeof item.text === "string" ? item.text : "",
      priority: normalizePriority(item.priority),
    }))
    .filter((item) => item.text.length > 0);

  // Resolve confidence + source: only present on the new shape.
  // Old sessions get sentinel values that the Reference Slip can render
  // as "(legacy session)".
  const confidence =
    rawBriefing && typeof rawBriefing.confidence === "number"
      ? Math.max(0, Math.min(1, rawBriefing.confidence))
      : 0;
  const source =
    rawBriefing && typeof rawBriefing.source === "string"
      ? rawBriefing.source
      : rawBriefing
        ? "empty"
        : "legacy";

  return {
    briefing: {
      paragraph,
      intentions,
      confidence,
      source,
    },
    editorial_briefing: paragraph,
    intentions,
    should_collect_external: !!plan.should_collect_external,
    should_collect_edge_case: !!plan.should_collect_edge_case,
    planner_result: plan.planner_result as Record<string, unknown> | undefined,
  };
}

export function readResearchBlock(
  session: ReflectionSession
): ReflectionResearchBlock | null {
  const phaseOutputs = session.state_json?.phase_outputs as
    | Record<string, unknown>
    | undefined;
  const block = phaseOutputs?.research as Record<string, unknown> | undefined;
  if (!block || typeof block !== "object") return null;
  const summary = (block.summary ?? {}) as Record<string, unknown>;
  return {
    external_result:
      block.external_result === null || block.external_result === undefined
        ? null
        : (block.external_result as Record<string, unknown>),
    skip_reason:
      typeof block.skip_reason === "string" ? block.skip_reason : null,
    stage_errors: Array.isArray(block.stage_errors)
      ? (block.stage_errors as string[])
      : [],
    summary: {
      sources: typeof summary.sources === "number" ? summary.sources : 0,
      findings: typeof summary.findings === "number" ? summary.findings : 0,
      implications:
        typeof summary.implications === "number" ? summary.implications : 0,
    },
  };
}

export function readProposeBlock(
  session: ReflectionSession
): ReflectionProposeBlock | null {
  const phaseOutputs = session.state_json?.phase_outputs as
    | Record<string, unknown>
    | undefined;
  const block = phaseOutputs?.propose as Record<string, unknown> | undefined;
  if (!block || typeof block !== "object") return null;
  const rawHunks = Array.isArray(block.hunks) ? block.hunks : [];
  const hunks: ReflectionHunk[] = rawHunks
    .filter(
      (item): item is Record<string, unknown> =>
        !!item && typeof item === "object"
    )
    .map(normalizeHunk)
    .filter((h) => h.hunk_id.length > 0);
  return {
    hunks,
    artifact: block.artifact as Record<string, unknown> | undefined,
    agent_state: block.agent_state as Record<string, unknown> | undefined,
    critic_summary:
      typeof block.critic_summary === "string"
        ? block.critic_summary
        : undefined,
    stage_errors: Array.isArray(block.stage_errors)
      ? (block.stage_errors as string[])
      : undefined,
    brief_at_propose:
      block.brief_at_propose &&
      typeof block.brief_at_propose === "object" &&
      !Array.isArray(block.brief_at_propose)
        ? (block.brief_at_propose as Record<string, unknown>)
        : undefined,
  };
}

export function readContextBlock(
  session: ReflectionSession
): ReflectionContextBlock | null {
  const ctx = session.state_json?.context as Record<string, unknown> | undefined;
  if (!ctx || typeof ctx !== "object") return null;
  return {
    brief_path: typeof ctx.brief_path === "string" ? ctx.brief_path : "",
    run_dir: typeof ctx.run_dir === "string" ? ctx.run_dir : null,
    mode: typeof ctx.mode === "string" ? ctx.mode : "post_run",
    market_identity:
      ctx.market_identity && typeof ctx.market_identity === "object"
        ? (ctx.market_identity as Record<string, unknown>)
        : undefined,
  };
}

export function readSteeringHistory(
  session: ReflectionSession
): ReflectionSteeringHistoryItem[] {
  const history = session.state_json?.steering_history;
  if (!Array.isArray(history)) return [];
  return history
    .filter(
      (item): item is Record<string, unknown> =>
        !!item && typeof item === "object"
    )
    .map((item) => ({
      iteration: typeof item.iteration === "number" ? item.iteration : 0,
      note: typeof item.note === "string" ? item.note : "",
      timestamp: typeof item.timestamp === "string" ? item.timestamp : "",
    }))
    .filter((item) => item.note.length > 0);
}

function normalizePriority(value: unknown): "high" | "medium" | "low" {
  if (value === "high" || value === "medium" || value === "low") return value;
  return "medium";
}

function normalizeHunk(raw: Record<string, unknown>): ReflectionHunk {
  const targetField =
    typeof raw.target_field === "string"
      ? raw.target_field
      : typeof raw.section === "string"
        ? raw.section
        : "notes";
  return {
    // BaseBriefChange `field` mirrors target_field for reflection hunks
    // — both name the brief field the change targets. The split exists
    // because RefreshBrief uses bracketed compound keys (e.g.
    // "capability_areas[lane-x]") for its lane-derived entries; for
    // the wider field set sourced from brief_recommendations, field
    // and target_field are the same string.
    field: targetField,
    hunk_id: typeof raw.hunk_id === "string" ? raw.hunk_id : "",
    section: typeof raw.section === "string" ? raw.section : "notes",
    kind: normalizeHunkKind(raw.kind),
    label: typeof raw.label === "string" ? raw.label : "(unnamed change)",
    before:
      typeof raw.before === "string"
        ? raw.before
        : raw.before === null
          ? null
          : null,
    after: typeof raw.after === "string" ? raw.after : "",
    rationale: typeof raw.rationale === "string" ? raw.rationale : "",
    confidence:
      typeof raw.confidence === "number"
        ? Math.max(0, Math.min(1, raw.confidence))
        : 0.5,
    default_approved: !!raw.default_approved,
    target_field: targetField,
  };
}

function normalizeHunkKind(value: unknown): ReflectionHunkKind {
  if (value === "add" || value === "modify" || value === "remove") return value;
  return "add";
}
