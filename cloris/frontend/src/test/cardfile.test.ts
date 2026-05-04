// Tests for `groupEntriesByBrief` (Phase F Slice F7).
//
// Pins the F7 contract:
// - Two state_dirs with the same brief_id_from_run collapse to ONE
//   group with primary + secondary modules.
// - Distinct brief_ids stay as separate groups.
// - Entries without a brief_id collect as singleton groups (each
//   surfaces independently because grouping by null would conflate
//   unrelated state_dirs).
// - Primary picked by worker alive-ness first, recency second.

import { describe, it, expect } from "vitest";
import { groupEntriesByBrief } from "../lib/cardfile";
import { makeStateDirEntry } from "./fixtures";

describe("groupEntriesByBrief — F7 brief grouping", () => {
  it("collapses two modules with same brief_id into one group", () => {
    const entries = [
      makeStateDirEntry({
        source: "linkedin",
        state_key: "li-1",
        brief_id_from_run: "fde-nyc",
      }),
      makeStateDirEntry({
        source: "github",
        state_key: "gh-1",
        brief_id_from_run: "fde-nyc",
      }),
    ];

    const rows = groupEntriesByBrief(entries);

    expect(rows.length).toBe(1);
    expect(rows[0].secondary.length).toBe(1);
  });

  it("keeps distinct brief_ids as separate groups", () => {
    const entries = [
      makeStateDirEntry({
        source: "linkedin",
        state_key: "li-a",
        brief_id_from_run: "brief-a",
      }),
      makeStateDirEntry({
        source: "linkedin",
        state_key: "li-b",
        brief_id_from_run: "brief-b",
      }),
    ];

    const rows = groupEntriesByBrief(entries);

    expect(rows.length).toBe(2);
    expect(rows.every((r) => r.secondary.length === 0)).toBe(true);
  });

  it("entries without brief_id surface as separate singletons", () => {
    const entries = [
      makeStateDirEntry({
        source: "linkedin",
        state_key: "orphan-1",
        brief_id_from_run: null,
      }),
      makeStateDirEntry({
        source: "github",
        state_key: "orphan-2",
        brief_id_from_run: null,
      }),
    ];

    const rows = groupEntriesByBrief(entries);

    // Two independent orphans, NOT one group of two.
    expect(rows.length).toBe(2);
    expect(rows.every((r) => r.secondary.length === 0)).toBe(true);
  });

  it("primary is the alive worker when present", () => {
    const dormant = makeStateDirEntry({
      source: "linkedin",
      state_key: "li-dormant",
      brief_id_from_run: "shared",
      worker_state: "missing",
    });
    const alive = makeStateDirEntry({
      source: "github",
      state_key: "gh-alive",
      brief_id_from_run: "shared",
      worker_state: "alive",
    });

    const rows = groupEntriesByBrief([dormant, alive]);

    expect(rows.length).toBe(1);
    expect(rows[0].primary.source).toBe("github");
    expect(rows[0].secondary[0].source).toBe("linkedin");
  });
});
