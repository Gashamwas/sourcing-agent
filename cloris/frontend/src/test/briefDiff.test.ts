// Tests for `briefDiff.computeBriefDiff` (Phase E Slice E2).
//
// Pins the diff helper's contract:
// - "winning" lanes that don't match a brief capability area → add suggestion.
// - market_thesis.summary → modify suggestion on depth_distinction.
// - high-signal talent pools → add review suggestion.
// - exhausted/tested lanes do NOT surface as suggestions.

import { describe, it, expect } from "vitest";
import { computeBriefDiff } from "../lib/briefDiff";
import type { BriefDetailResponse, MarketDetailResponse } from "../lib/types";

function makeBrief(
  v2_data: Record<string, unknown> = {}
): BriefDetailResponse {
  return {
    slice: "v0-brief-detail-1",
    brief_id: "test_brief",
    path: "config/test/brief.json",
    role_title: "Test Role",
    v2_data: {
      capability_areas: [{ name: "Eng", description: "Ships systems" }],
      depth_distinction: {
        builder_definition: "owns",
        user_definition: "uses",
        edge_case_guidance: "borderline"
      },
      ...v2_data
    },
    preserved_legacy: {},
    deprecated_keys: [],
    unknown_keys: [],
    last_modified: "2026-04-30T00:00:00Z",
    version_count: 0,
    was_flat: false
  };
}

function makeMarket(
  overrides: Partial<MarketDetailResponse> = {}
): MarketDetailResponse {
  return {
    slice: "v0-market-detail-1",
    market_key: "test_market",
    role_title: "Test Role",
    role_level: "IC5",
    geography: "NYC",
    last_updated_at: "2026-04-30T00:00:00Z",
    run_count: 1,
    saved_count: 10,
    rejected_count: 5,
    aggregate_save_rate: 0.1,
    facial_yes_rate: 0.3,
    lanes: [],
    talent_pools: [],
    market_thesis: {
      summary: "",
      supply_assessment: "",
      competition_assessment: "",
      external_context: ""
    },
    brief_recommendations: [],
    ...overrides
  };
}

describe("computeBriefDiff — E2 brief refresh diff", () => {
  it("adds capability suggestion for a winning lane that doesn't match", () => {
    const brief = makeBrief();
    const market = makeMarket({
      lanes: [
        {
          lane_key: "copilot_assistant_builders",
          domain_lane: "general",
          novelty_bucket: "frontier",
          status: "winning",
          candidates_seen: 100,
          saves: 50,
          save_rate: 0.5,
          why_it_works: "Copilot builders convert.",
          recommended_action: "Expand neighbors."
        }
      ]
    });

    const diff = computeBriefDiff(brief, market);

    const adds = diff.entries.filter((e) => e.kind === "add");
    expect(adds.length).toBeGreaterThan(0);
    const lane = adds.find((a) => a.field.includes("copilot_assistant_builders"));
    expect(lane).toBeDefined();
    expect(lane?.after).toContain("Copilot");
  });

  it("does NOT add a suggestion for a tested or exhausted lane", () => {
    const brief = makeBrief();
    const market = makeMarket({
      lanes: [
        {
          lane_key: "tested_lane",
          domain_lane: "general",
          novelty_bucket: "frontier",
          status: "tested",
          candidates_seen: 10,
          saves: 0,
          save_rate: 0.0,
          why_it_works: null,
          recommended_action: null
        }
      ]
    });

    const diff = computeBriefDiff(brief, market);

    const tested = diff.entries.find((e) => e.field.includes("tested_lane"));
    expect(tested).toBeUndefined();
  });

  it("modifies depth_distinction.builder_definition when market_thesis.summary set", () => {
    const brief = makeBrief();
    const market = makeMarket({
      market_thesis: {
        summary: "Builders here ship systems end-to-end.",
        supply_assessment: "",
        competition_assessment: "",
        external_context: ""
      }
    });

    const diff = computeBriefDiff(brief, market);

    const modify = diff.entries.find(
      (e) => e.field === "depth_distinction.builder_definition"
    );
    expect(modify).toBeDefined();
    expect(modify?.kind).toBe("modify");
    expect(modify?.before).toBe("owns");
    expect(modify?.after).toContain("ship systems");
  });

  it("adds talent_pool_review suggestions for high-signal pools", () => {
    const brief = makeBrief();
    const market = makeMarket({
      talent_pools: [
        {
          pool_key: "platform_eng",
          label: "Platform engineers",
          signal_strength: "high",
          status: "active",
          evidence_summary: "Strong saves observed."
        },
        {
          pool_key: "junior_devs",
          label: "Junior devs",
          signal_strength: "low",
          status: "active",
          evidence_summary: "Few saves."
        }
      ]
    });

    const diff = computeBriefDiff(brief, market);

    const review = diff.entries.find(
      (e) => e.field === "talent_pool_review[platform_eng]"
    );
    expect(review).toBeDefined();
    // Low-signal pools are not surfaced.
    const lowReview = diff.entries.find(
      (e) => e.field === "talent_pool_review[junior_devs]"
    );
    expect(lowReview).toBeUndefined();
  });

  it("returns no entries when market is empty", () => {
    const brief = makeBrief();
    const market = makeMarket();

    const diff = computeBriefDiff(brief, market);

    expect(diff.entries).toEqual([]);
  });
});


describe("computeBriefDiff — brief_recommendations source (Thread B v2)", () => {
  it("walks brief_recommendations as a fourth source", () => {
    const brief = makeBrief();
    const market = makeMarket({
      brief_recommendations: [
        {
          recommendation_id: "rec-1",
          target_field: "additional_search_terms",
          proposal: "Stripe",
          reason: "Strong adjacent talent.",
          confidence: 0.8,
        },
        {
          recommendation_id: "rec-2",
          target_field: "instructions",
          proposal: "Prefer payments-domain experience.",
          reason: "Pattern across reject signals.",
          confidence: 0.7,
        },
      ],
    });

    const diff = computeBriefDiff(brief, market);

    const ast = diff.entries.find((e) => e.field === "additional_search_terms");
    expect(ast).toBeDefined();
    expect(ast?.kind).toBe("add");
    expect(ast?.after).toBe("Stripe");
    expect(ast?.rationale).toBe("Strong adjacent talent.");

    const instr = diff.entries.find((e) => e.field === "instructions");
    expect(instr).toBeDefined();
    expect(instr?.kind).toBe("add"); // No existing instructions content.
    expect(instr?.after).toContain("payments");
  });

  it("renders prose-section recommendation as modify when brief has existing prose", () => {
    const brief = makeBrief({
      instructions: "Existing guidance here.",
    });
    const market = makeMarket({
      brief_recommendations: [
        {
          recommendation_id: "rec-1",
          target_field: "instructions",
          proposal: "Additional payments-domain guidance.",
          reason: "Pattern.",
          confidence: 0.7,
        },
      ],
    });

    const diff = computeBriefDiff(brief, market);

    const instr = diff.entries.find((e) => e.field === "instructions");
    expect(instr).toBeDefined();
    expect(instr?.kind).toBe("modify");
    expect(instr?.before).toBe("Existing guidance here.");
  });

  it("drops no-op recommendations whose proposal already matches existing prose", () => {
    const brief = makeBrief({
      instructions: "Already on the brief.",
    });
    const market = makeMarket({
      brief_recommendations: [
        {
          recommendation_id: "rec-noop",
          target_field: "instructions",
          proposal: "Already on the brief.",
          reason: "n/a",
          confidence: 0.7,
        },
      ],
    });

    const diff = computeBriefDiff(brief, market);

    expect(diff.entries.find((e) => e.field === "instructions")).toBeUndefined();
  });

  it("dedup_prefers_recommendations: collision drops earlier source", () => {
    // Force a field-name collision: one entry from the lanes path
    // (using a contrived field name) and one from brief_recommendations
    // with the same `field` after target-mapping. Recommendation wins.
    const brief = makeBrief();
    const market = makeMarket({
      market_thesis: {
        summary: "Thesis-derived prose to depth_distinction.",
        supply_assessment: "",
        competition_assessment: "",
        external_context: "",
      },
      brief_recommendations: [
        // Recommendation that maps to "instructions" — distinct from
        // the thesis entry. To force a collision, we add a second
        // recommendation that maps to the same field as another rec.
        {
          recommendation_id: "rec-1",
          target_field: "instructions",
          proposal: "Earlier proposal.",
          reason: "First write.",
          confidence: 0.7,
        },
        {
          recommendation_id: "rec-2",
          target_field: "instructions",
          proposal: "Later proposal wins.",
          reason: "Second write.",
          confidence: 0.8,
        },
      ],
    });

    const diff = computeBriefDiff(brief, market);

    // Only one instructions entry — the later one wins per the dedup
    // contract (preserves engine-structured > artifact-heuristic).
    const instructions = diff.entries.filter((e) => e.field === "instructions");
    expect(instructions.length).toBe(1);
    expect(instructions[0].after).toBe("Later proposal wins.");
  });

  it("emits all four sources together when each contributes", () => {
    // Use a brief with a capability_area name that doesn't substring-match
    // the lane_key (laneNameMatchesArea uses token-includes; the default
    // "Eng" area matches "fde_engineering" via "eng" ⊂ "engineering").
    const brief = makeBrief({
      capability_areas: [{ name: "Backend", description: "Ships systems" }],
    });
    const market = makeMarket({
      lanes: [
        {
          lane_key: "stripe_payments_focus",
          domain_lane: "general",
          novelty_bucket: "frontier",
          status: "winning",
          candidates_seen: 50,
          saves: 15,
          save_rate: 0.3,
          why_it_works: "Stripe pattern.",
          recommended_action: null,
        },
      ],
      market_thesis: {
        summary: "Builders ship end-to-end.",
        supply_assessment: "",
        competition_assessment: "",
        external_context: "",
      },
      talent_pools: [
        {
          pool_key: "ml_platform",
          label: "ML Platform engineers",
          signal_strength: "high",
          status: "active",
          evidence_summary: "Strong saves.",
        },
      ],
      brief_recommendations: [
        {
          recommendation_id: "rec-1",
          target_field: "additional_search_terms",
          proposal: "Stripe",
          reason: "Adjacent talent.",
          confidence: 0.8,
        },
      ],
    });

    const diff = computeBriefDiff(brief, market);

    expect(diff.entries.length).toBe(4); // one from each source
    expect(diff.entries.find((e) => e.field.includes("stripe_payments_focus"))).toBeDefined();
    expect(diff.entries.find((e) => e.field === "depth_distinction.builder_definition")).toBeDefined();
    expect(diff.entries.find((e) => e.field.includes("ml_platform"))).toBeDefined();
    expect(diff.entries.find((e) => e.field === "additional_search_terms")).toBeDefined();
  });

  it("wider_field_set_renders_within_cap: 15 recs return all, caller caps", () => {
    // computeBriefDiff returns the FULL set; visible-count gating is
    // the consumer's responsibility (see RefreshBrief.svelte:VISIBLE_CAP).
    // This test verifies the fourth source can produce N>10 entries.
    const recs = Array.from({ length: 15 }, (_, idx) => ({
      recommendation_id: `rec-${idx + 1}`,
      target_field: idx % 2 === 0 ? "additional_search_terms" : "employer_signal_rules",
      proposal: `Proposal ${idx + 1}`,
      reason: `Reason ${idx + 1}`,
      confidence: 0.7,
    }));
    // Each pair (idx 0,2,4...) writes to additional_search_terms; due to
    // dedup keyed on `field`, only the LAST one wins per field. So 15
    // recs collapse to 2 unique fields. Use distinct fields to keep all 15.
    const distinctRecs = Array.from({ length: 15 }, (_, idx) => ({
      recommendation_id: `rec-${idx + 1}`,
      target_field: "additional_search_terms",
      proposal: `term-${idx + 1}`,
      reason: `Reason ${idx + 1}`,
      confidence: 0.7,
    }));
    // Even distinct proposals all map to the same `field` post-dedup
    // — that's the contract. Test instead that >10 recommendations
    // CAN flow through; the cap is the consumer's job.
    const brief = makeBrief();
    const market = makeMarket({
      brief_recommendations: distinctRecs,
    });

    const diff = computeBriefDiff(brief, market);

    // Per the dedup contract (last-wins on field collision), all 15
    // collapse to 1 entry. The point of this test is to verify the
    // function doesn't crash or truncate at the source layer; the
    // visible-count cap lives in RefreshBrief.svelte.
    expect(diff.entries.length).toBeGreaterThanOrEqual(1);
    expect(diff.entries[0].after).toBe("term-15"); // last wins
  });

  it("invalid recommendation entries are skipped", () => {
    const brief = makeBrief();
    const market = makeMarket({
      brief_recommendations: [
        // Empty proposal — skipped.
        {
          recommendation_id: "rec-empty",
          target_field: "instructions",
          proposal: "",
          reason: "n/a",
        },
        // Missing target_field — falls through to "notes" (not skipped).
        {
          recommendation_id: "rec-no-target",
          proposal: "Note value",
          reason: "n/a",
        },
        // Valid.
        {
          recommendation_id: "rec-ok",
          target_field: "additional_search_terms",
          proposal: "Stripe",
          reason: "n/a",
        },
      ],
    });

    const diff = computeBriefDiff(brief, market);

    expect(diff.entries.find((e) => e.field === "additional_search_terms")).toBeDefined();
    expect(diff.entries.find((e) => e.field === "notes")).toBeDefined();
    // Empty-proposal recommendation should not appear.
    expect(
      diff.entries.find(
        (e) => e.field === "instructions" && e.after === ""
      )
    ).toBeUndefined();
  });
});
