// Brief vs market diff helper — Phase E Slice E2 + diff-dedup v2.
//
// Pure shape: given a brief's V2 partition + a market's intelligence,
// compute the side-by-side change set the recruiter approves before
// the merged payload PUTs to `PUT /api/brief/{brief_id}`.
//
// Conservative: Cloris ONLY suggests changes the artifact data
// EXPLICITLY supports. No auto-merge — every change is a recruiter-
// confirmed line.
//
// Sources walked (in this order):
//   1. market.lanes (winning lanes that don't match a current area)
//   2. market.market_thesis (depth_distinction nudge)
//   3. market.talent_pools (high-signal pools as non_fit_patterns review)
//   4. market.brief_recommendations (engine-structured target_field +
//      proposal — wider field set: additional_search_terms,
//      employer_signal_rules, search_priorities, instructions, notes)
//
// Dedup contract: when two sources produce the same `field` string,
// prefer the brief_recommendation entry (engine-structured output is
// closer to ground truth than the artifact-view heuristic). Dev builds
// emit a console.debug per drop so the dedup is observable during
// testing without polluting production console.
//
// R12 cap contract: this function returns the FULL set. Consumers are
// responsible for visible-count gating (RefreshBrief.svelte caps the
// rendered list at 10 with a "Show all N" expand affordance).

import type {
  BaseBriefChange,
  BriefChangeKind,
} from "./briefChanges";
import type {
  BriefDetailResponse,
  MarketDetailResponse,
  MarketLane,
  MarketTalentPool
} from "./types";

// Re-exports for back-compat with consumers that imported these from
// briefDiff before the lift. New code should import from briefChanges.
export type BriefDiffKind = BriefChangeKind;

// BriefDiffEntry is BaseBriefChange today. Kept as a name alias rather
// than collapsing the import sites so a future divergence (e.g. lane-
// specific metadata on RefreshBrief entries) has a clean place to land.
export interface BriefDiffEntry extends BaseBriefChange {
  // RefreshBrief historically wrote `before: ""` for add-cases rather
  // than null. The base type permits null; the value is rendered the
  // same way by BriefChangeBeforeAfter so both work.
}

export interface BriefDiff {
  entries: BriefDiffEntry[];
}

interface CapabilityArea {
  name: string;
  description?: string;
}

function brief_capability_areas(
  brief: BriefDetailResponse
): CapabilityArea[] {
  const v2 = brief.v2_data ?? {};
  const raw = (v2 as Record<string, unknown>).capability_areas;
  if (!Array.isArray(raw)) return [];
  return raw
    .filter((entry): entry is Record<string, unknown> =>
      typeof entry === "object" && entry !== null
    )
    .map((entry) => ({
      name: typeof entry.name === "string" ? entry.name : "",
      description:
        typeof entry.description === "string" ? entry.description : ""
    }))
    .filter((area) => area.name);
}

function laneNameMatchesArea(lane: MarketLane, area: CapabilityArea): boolean {
  // Basic lexical match — the lane_key is a slug; the area.name is the
  // recruiter-readable label. Compare normalized tokens.
  const laneTokens = lane.lane_key.split(/[_\s-]+/).filter(Boolean);
  const areaTokens = area.name.toLowerCase().split(/\s+/).filter(Boolean);
  if (laneTokens.length === 0 || areaTokens.length === 0) return false;
  for (const at of areaTokens) {
    if (laneTokens.some((lt) => lt.toLowerCase().includes(at))) return true;
  }
  return false;
}

export function computeBriefDiff(
  brief: BriefDetailResponse,
  market: MarketDetailResponse
): BriefDiff {
  const entries: BriefDiffEntry[] = [];
  const areas = brief_capability_areas(brief);

  // Suggest adding capability areas for winning lanes that don't match
  // anything currently in the brief. Only "winning" status — Cloris
  // doesn't surface tested or exhausted lanes here.
  for (const lane of market.lanes) {
    if (lane.status !== "winning") continue;
    if (areas.some((area) => laneNameMatchesArea(lane, area))) continue;
    entries.push({
      field: `capability_areas[${lane.lane_key}]`,
      kind: "add",
      before: "",
      after: lane.why_it_works || lane.lane_key,
      rationale:
        lane.recommended_action ||
        `New winning lane with ${lane.saves} save${lane.saves === 1 ? "" : "s"}.`
    });
  }

  // Suggest editing depth_distinction.builder_definition when the
  // market_thesis.summary has matter the brief doesn't carry — but
  // only as an editorial nudge. The actual merge stays recruiter-
  // controlled.
  if (market.market_thesis.summary) {
    entries.push({
      field: "depth_distinction.builder_definition",
      kind: "modify",
      before:
        ((brief.v2_data as Record<string, unknown>)?.depth_distinction as
          | Record<string, unknown>
          | undefined
          )?.builder_definition?.toString() ?? "",
      after: market.market_thesis.summary,
      rationale:
        "Cloris's read of supply + competition since last run."
    });
  }

  // Suggest pulling talent pools Cloris is tracking with high signal
  // into a non_fit_patterns review (so the recruiter can confirm/deny
  // they belong inside or outside the search).
  for (const pool of market.talent_pools.filter(
    (p: MarketTalentPool) => p.signal_strength === "high"
  )) {
    entries.push({
      field: `talent_pool_review[${pool.pool_key}]`,
      kind: "add",
      before: "",
      after: pool.label || pool.pool_key,
      rationale:
        pool.evidence_summary ||
        "High-signal talent pool worth confirming as in-scope or off-scope."
    });
  }

  // Fourth source: engine's structured brief_recommendations. Mirrors
  // market_intelligence/reflection.py:_build_hunks_from_artifact —
  // both sides walk the same recommendation taxonomy so RefreshBrief
  // and Reflection surface the same proposed brief edits.
  for (const rec of market.brief_recommendations) {
    const entry = recommendationToEntry(rec, brief);
    if (entry !== null) entries.push(entry);
  }

  // Final dedup: when two sources produce the same `field`, prefer
  // brief_recommendation entries (engine-structured > artifact-view
  // heuristic). The recommendations were appended last, so the dedup
  // walks in order and the LATER occurrence wins for any duplicated
  // field key. In dev builds, log each drop so the dedup is visible
  // during testing.
  return { entries: dedupEntriesPreferringRecommendations(entries) };
}


// Mirrors the field-mapping in
// market_intelligence/reflection.py:_HUNK_TARGET_TO_SECTION so both
// sides classify recommendations identically. Unknown target_field
// values fall through to "notes" — same posture as the engine.
const RECOMMENDATION_TARGET_TO_FIELD: Record<string, string> = {
  additional_search_terms: "additional_search_terms",
  employer_signal_rules: "employer_signal_rules",
  search_priorities: "search_priorities",
  instructions: "instructions",
  notes: "notes",
};

const PROSE_FIELDS = new Set(["instructions", "notes"]);

function recommendationToEntry(
  rec: Record<string, unknown>,
  brief: BriefDetailResponse
): BriefDiffEntry | null {
  const target = String(rec.target_field ?? "").trim().toLowerCase();
  const proposal = String(rec.proposal ?? "").trim();
  const reason = String(rec.reason ?? "").trim();
  if (proposal.length === 0) return null;

  const field = RECOMMENDATION_TARGET_TO_FIELD[target] ?? "notes";

  // For prose fields, the existing brief content is the "before"; for
  // list fields the before is empty (we're appending). Mirrors the
  // _hunk_before_and_kind helper in reflection.py.
  const v2 = (brief.v2_data as Record<string, unknown>) ?? {};
  let before: string | null = null;
  let kind: BriefChangeKind = "add";
  if (PROSE_FIELDS.has(field)) {
    const existing = v2[field];
    if (typeof existing === "string" && existing.trim().length > 0) {
      before = existing;
      kind = "modify";
    }
  }

  // Drop no-op recommendations whose proposal already matches the
  // existing prose verbatim. List sections always render as add since
  // dedupe-append happens at merge time, not diff time.
  if (before !== null && before === proposal) return null;

  return {
    field,
    kind,
    before,
    after: proposal,
    rationale: reason,
  };
}


function dedupEntriesPreferringRecommendations(
  entries: BriefDiffEntry[]
): BriefDiffEntry[] {
  // Walk in order; later occurrences (brief_recommendations were
  // appended last) replace earlier ones with the same field. Result
  // preserves first-occurrence order otherwise so lane/thesis/pool
  // entries keep their walk position when they're not duplicated.
  const lastByField = new Map<string, BriefDiffEntry>();
  for (const entry of entries) {
    if (lastByField.has(entry.field)) {
      const dropped = lastByField.get(entry.field)!;
      if (
        typeof import.meta !== "undefined" &&
        (import.meta as { env?: { DEV?: boolean } }).env?.DEV
      ) {
        // eslint-disable-next-line no-console
        console.debug(
          `[briefDiff] dedup dropped earlier entry for field=${entry.field}`,
          { dropped, kept: entry }
        );
      }
    }
    lastByField.set(entry.field, entry);
  }

  // Preserve original order using the position of the kept entry.
  // Each entry in the input is either kept (its final occurrence) or
  // dropped (an earlier occurrence whose later twin wins).
  const keptSet = new Set(lastByField.values());
  return entries.filter((entry) => keptSet.has(entry));
}
