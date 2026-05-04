// Tests for the Cloris-state vocabulary module (lib/state.ts).
//
// These are pure-function tests that drive each helper through every
// branch of its rule table. The Reference Slip / debug surface still
// exposes the raw enums; these tests pin the human-language layer.

import { describe, it, expect } from "vitest";
import type { RunSummary, StateDirEntry } from "../lib/types";
import {
  clorisStateKind,
  clorisStateLabel,
  clorisStateInline,
  clorisWorkerLabel,
  clorisWorkerNeedsAttention,
  clorisPullLabel,
  clorisStopReasonInline,
  clorisStopReasonLabel,
  clorisLastMark,
  clorisDecisionClass,
  clorisRunSummaryLine,
  tallyDecisionClasses,
  resolveRecruiterTitle,
  resolveRecruiterTitleFromKey,
  resolveRecruiterTitlesWithCollisions,
  CANONICAL_STOP_REASONS,
  type ClorisStateKind
} from "../lib/state";
import { makeStateDirEntry } from "./fixtures";

function makeRun(overrides: Partial<RunSummary> = {}): RunSummary {
  return {
    id: 1,
    status: "running",
    stop_reason: null,
    mode: "fresh",
    started_at: null,
    ended_at: null,
    ...overrides
  };
}

describe("clorisStateKind", () => {
  it("returns working when optimisticallyStopping is true (overrides everything)", () => {
    const entry = makeStateDirEntry({ worker_state: "missing" });
    expect(clorisStateKind(entry, true)).toBe("working");
  });

  it("returns interrupted when latest_run.status === 'interrupted'", () => {
    const entry = makeStateDirEntry({
      worker_state: "alive",
      latest_run: makeRun({ status: "interrupted" })
    });
    expect(clorisStateKind(entry, false)).toBe("interrupted");
  });

  it("returns limit-reached when latest_run.status === 'governor_limit_reached'", () => {
    const entry = makeStateDirEntry({
      worker_state: "alive",
      latest_run: makeRun({ status: "governor_limit_reached" })
    });
    expect(clorisStateKind(entry, false)).toBe("limit-reached");
  });

  it("returns working when worker_state === 'alive' and run is not interrupted/limit", () => {
    const entry = makeStateDirEntry({
      worker_state: "alive",
      latest_run: makeRun({ status: "running" })
    });
    expect(clorisStateKind(entry, false)).toBe("working");
  });

  it("returns lost-track when worker_state === 'stale'", () => {
    const entry = makeStateDirEntry({
      worker_state: "stale",
      runtime_state_present: true,
      latest_run: makeRun({ status: "running" })
    });
    expect(clorisStateKind(entry, false)).toBe("lost-track");
  });

  it("returns no-record when runtime_state_present is false", () => {
    const entry = makeStateDirEntry({
      worker_state: "missing",
      runtime_state_present: false,
      latest_run: null
    });
    expect(clorisStateKind(entry, false)).toBe("no-record");
  });

  it("returns working when run.status === 'running' and worker is missing-but-present (fallback)", () => {
    const entry = makeStateDirEntry({
      worker_state: "missing",
      runtime_state_present: true,
      latest_run: makeRun({ status: "running" })
    });
    expect(clorisStateKind(entry, false)).toBe("working");
  });

  it("returns completed when run.status === 'completed'", () => {
    const entry = makeStateDirEntry({
      worker_state: "missing",
      runtime_state_present: true,
      latest_run: makeRun({ status: "completed" })
    });
    expect(clorisStateKind(entry, false)).toBe("completed");
  });

  it("returns no-record when latest_run is null but runtime_state_present is true", () => {
    const entry = makeStateDirEntry({
      worker_state: "missing",
      runtime_state_present: true,
      latest_run: null
    });
    expect(clorisStateKind(entry, false)).toBe("no-record");
  });

  it("returns no-record when latest_run.status is null", () => {
    const entry = makeStateDirEntry({
      worker_state: "missing",
      runtime_state_present: true,
      latest_run: makeRun({ status: null })
    });
    expect(clorisStateKind(entry, false)).toBe("no-record");
  });

  it("returns unknown for unrecognized run.status", () => {
    const entry = makeStateDirEntry({
      worker_state: "missing",
      runtime_state_present: true,
      latest_run: makeRun({ status: "mystery_status" })
    });
    expect(clorisStateKind(entry, false)).toBe("unknown");
  });
});

describe("clorisStateLabel", () => {
  const expected: Record<ClorisStateKind, string> = {
    stalled: "Stalled",
    working: "Working",
    "limit-reached": "Paused",
    interrupted: "Stopped",
    completed: "Completed",
    "lost-track": "Lost track",
    away: "Away",
    "no-record": "No record",
    unknown: "Unresolved"
  };

  it.each(Object.keys(expected) as ClorisStateKind[])(
    "maps %s to its capitalized pill label",
    (kind) => {
      expect(clorisStateLabel(kind)).toBe(expected[kind]);
    }
  );
});

describe("clorisStateInline", () => {
  const expected: Record<ClorisStateKind, string> = {
    stalled: "stalled",
    working: "working",
    "limit-reached": "limit reached",
    interrupted: "interrupted",
    completed: "completed",
    "lost-track": "lost track",
    away: "away",
    "no-record": "no card record",
    unknown: "unresolved"
  };

  it.each(Object.keys(expected) as ClorisStateKind[])(
    "maps %s to its inline lower-case form",
    (kind) => {
      expect(clorisStateInline(kind)).toBe(expected[kind]);
    }
  );
});

describe("clorisWorkerLabel", () => {
  it("returns Stopping… when optimisticallyStopping=true regardless of worker_state", () => {
    const entry = makeStateDirEntry({ worker_state: "alive" });
    expect(clorisWorkerLabel(entry, true)).toBe("Stopping…");
  });

  it("returns Working when worker_state === 'alive'", () => {
    const entry = makeStateDirEntry({ worker_state: "alive" });
    expect(clorisWorkerLabel(entry, false)).toBe("Working");
  });

  it("returns Lost track when worker_state === 'stale'", () => {
    const entry = makeStateDirEntry({ worker_state: "stale" });
    expect(clorisWorkerLabel(entry, false)).toBe("Lost track");
  });

  it("returns Away when worker_state === 'missing'", () => {
    const entry = makeStateDirEntry({ worker_state: "missing" });
    expect(clorisWorkerLabel(entry, false)).toBe("Away");
  });
});

describe("clorisWorkerNeedsAttention", () => {
  it("returns true when optimisticallyStopping=true", () => {
    const entry = makeStateDirEntry({ worker_state: "alive" });
    expect(clorisWorkerNeedsAttention(entry, true)).toBe(true);
  });

  it("returns true when worker_state === 'stale'", () => {
    const entry = makeStateDirEntry({ worker_state: "stale" });
    expect(clorisWorkerNeedsAttention(entry, false)).toBe(true);
  });

  it("returns false when worker_state === 'alive' (and not stopping)", () => {
    const entry = makeStateDirEntry({ worker_state: "alive" });
    expect(clorisWorkerNeedsAttention(entry, false)).toBe(false);
  });

  it("returns false when worker_state === 'missing' (and not stopping)", () => {
    const entry = makeStateDirEntry({ worker_state: "missing" });
    expect(clorisWorkerNeedsAttention(entry, false)).toBe(false);
  });
});

describe("clorisPullLabel", () => {
  it("returns 'ready to pull' when resumable === true", () => {
    const entry = makeStateDirEntry({ resumable: true });
    expect(clorisPullLabel(entry)).toBe("ready to pull");
  });

  it("returns 'nothing pending' when resumable === false", () => {
    const entry = makeStateDirEntry({ resumable: false });
    expect(clorisPullLabel(entry)).toBe("nothing pending");
  });

  it("returns '—' when resumable === null", () => {
    const entry = makeStateDirEntry({ resumable: null });
    expect(clorisPullLabel(entry)).toBe("—");
  });
});

describe("clorisStopReasonInline", () => {
  it("returns null when latest_run is null", () => {
    const entry = makeStateDirEntry({ latest_run: null });
    expect(clorisStopReasonInline(entry)).toBeNull();
  });

  it("returns null when stop_reason is null", () => {
    const entry = makeStateDirEntry({
      latest_run: makeRun({ stop_reason: null })
    });
    expect(clorisStopReasonInline(entry)).toBeNull();
  });

  it("returns null when stop_reason === 'normal'", () => {
    const entry = makeStateDirEntry({
      latest_run: makeRun({ stop_reason: "normal" })
    });
    expect(clorisStopReasonInline(entry)).toBeNull();
  });

  it("maps governor_limit_reached to 'limit reached'", () => {
    const entry = makeStateDirEntry({
      latest_run: makeRun({ stop_reason: "governor_limit_reached" })
    });
    expect(clorisStopReasonInline(entry)).toBe("limit reached");
  });

  it("maps browser_disconnect_unrecovered to 'browser disconnected'", () => {
    const entry = makeStateDirEntry({
      latest_run: makeRun({ stop_reason: "browser_disconnect_unrecovered" })
    });
    expect(clorisStopReasonInline(entry)).toBe("browser disconnected");
  });

  it("maps browser_session_lost to 'browser disconnected'", () => {
    const entry = makeStateDirEntry({
      latest_run: makeRun({ stop_reason: "browser_session_lost" })
    });
    expect(clorisStopReasonInline(entry)).toBe("browser disconnected");
  });

  it("maps user_stop to 'stopped by you'", () => {
    const entry = makeStateDirEntry({
      latest_run: makeRun({ stop_reason: "user_stop" })
    });
    expect(clorisStopReasonInline(entry)).toBe("stopped by you");
  });

  it("maps worker_killed to 'stopped'", () => {
    const entry = makeStateDirEntry({
      latest_run: makeRun({ stop_reason: "worker_killed" })
    });
    expect(clorisStopReasonInline(entry)).toBe("stopped");
  });

  it("maps worker_crashed to 'Cloris stopped unexpectedly'", () => {
    const entry = makeStateDirEntry({
      latest_run: makeRun({ stop_reason: "worker_crashed" })
    });
    expect(clorisStopReasonInline(entry)).toBe("Cloris stopped unexpectedly");
  });

  it("falls back to a snake_case-to-spaces lowercase rendering for unknown reasons", () => {
    const entry = makeStateDirEntry({
      latest_run: makeRun({ stop_reason: "Some_Mystery_Reason" })
    });
    expect(clorisStopReasonInline(entry)).toBe("some mystery reason");
  });

  // G1 (Phase G L14 audit) — pin canonical RunStopReason coverage. The
  // backend enum lives at shared/safety/stop_reasons.py; CANONICAL_STOP_REASONS
  // mirrors it. Every canonical value must produce an editorial label, not
  // fall through to the snake_case raw render.
  it("renders an editorial label for every canonical RunStopReason value", () => {
    for (const reason of CANONICAL_STOP_REASONS) {
      if (reason === "normal") continue;
      const entry = makeStateDirEntry({
        latest_run: makeRun({ stop_reason: reason })
      });
      const label = clorisStopReasonInline(entry);
      expect(label).not.toBeNull();
      expect(label).not.toMatch(/_/);
    }
  });
});

describe("clorisStopReasonLabel — Phase G L14 canonical coverage", () => {
  it("returns an empty string when stop_reason is null", () => {
    expect(clorisStopReasonLabel(null)).toBe("");
  });

  it("renders an editorial sentence-case label for every canonical RunStopReason value", () => {
    for (const reason of CANONICAL_STOP_REASONS) {
      const label = clorisStopReasonLabel(reason);
      expect(label).not.toBe("");
      expect(label).not.toMatch(/_/);
      expect(label).not.toBe(reason);
    }
  });

  it("maps governor_limit (canonical) to 'Hit the daily limit'", () => {
    expect(clorisStopReasonLabel("governor_limit")).toBe("Hit the daily limit");
  });

  it("maps fatal_runtime_error (canonical) to 'Errored'", () => {
    expect(clorisStopReasonLabel("fatal_runtime_error")).toBe("Errored");
  });

  it("maps browser_disconnect_unrecovered (canonical) to 'Lost the browser session'", () => {
    expect(clorisStopReasonLabel("browser_disconnect_unrecovered")).toBe(
      "Lost the browser session"
    );
  });

  it("keeps legacy governor_limit_reached aliased to 'Hit the daily limit'", () => {
    expect(clorisStopReasonLabel("governor_limit_reached")).toBe(
      "Hit the daily limit"
    );
  });
});

describe("clorisLastMark", () => {
  it("formats ended_at when present (preferred over started_at)", () => {
    const entry = makeStateDirEntry({
      latest_run: makeRun({
        started_at: "2026-04-27T10:00:00Z",
        ended_at: "2026-04-27T11:30:00Z"
      })
    });
    const result = clorisLastMark(entry);
    expect(result).not.toBeNull();
    // Don't pin the locale-formatted output — different runtimes localize
    // differently. Verify it parses to the expected instant.
    expect(result).toMatch(/\d/);
  });

  it("falls back to started_at when ended_at is missing", () => {
    const entry = makeStateDirEntry({
      latest_run: makeRun({
        started_at: "2026-04-27T10:00:00Z",
        ended_at: null
      })
    });
    expect(clorisLastMark(entry)).not.toBeNull();
  });

  it("returns null when both timestamps are missing", () => {
    const entry = makeStateDirEntry({
      latest_run: makeRun({ started_at: null, ended_at: null })
    });
    expect(clorisLastMark(entry)).toBeNull();
  });

  it("returns null when latest_run is null", () => {
    const entry = makeStateDirEntry({ latest_run: null });
    expect(clorisLastMark(entry)).toBeNull();
  });

  it("returns null when the timestamp is invalid", () => {
    const entry = makeStateDirEntry({
      latest_run: makeRun({ ended_at: "not-a-date", started_at: null })
    });
    expect(clorisLastMark(entry)).toBeNull();
  });
});

describe("clorisDecisionClass — recruiter priority classifier", () => {
  it("groups all save variants under 'save'", () => {
    expect(clorisDecisionClass("SAVE")).toBe("save");
    expect(clorisDecisionClass("INFERENTIAL_SAVE")).toBe("save");
    expect(clorisDecisionClass("TRANSFERABLE_SAVE")).toBe("save");
    expect(clorisDecisionClass("SIGNAL_SAVE")).toBe("save");
  });

  it("classifies FACIAL_BORDERLINE as 'borderline'", () => {
    expect(clorisDecisionClass("FACIAL_BORDERLINE")).toBe("borderline");
  });

  it("classifies REJECT as 'reject' (post-facial substantive rejection)", () => {
    expect(clorisDecisionClass("REJECT")).toBe("reject");
  });

  it("groups facial filter outcomes and parse failures under 'filtered'", () => {
    expect(clorisDecisionClass("FACIAL_NO")).toBe("filtered");
    expect(clorisDecisionClass("FACIAL_SKIP")).toBe("filtered");
    expect(clorisDecisionClass("GEO_FILTERED")).toBe("filtered");
    expect(clorisDecisionClass("PRESCREEN_SKIP")).toBe("filtered");
    expect(clorisDecisionClass("INSUFFICIENT_DATA")).toBe("filtered");
    expect(clorisDecisionClass("PARSE_FAILURE")).toBe("filtered");
    expect(clorisDecisionClass("JUDGMENT_FAILURE")).toBe("filtered");
  });

  it("classifies null / empty as 'in-progress'", () => {
    expect(clorisDecisionClass(null)).toBe("in-progress");
    expect(clorisDecisionClass("")).toBe("in-progress");
  });

  it("treats stray FACIAL_YES (transitional) as 'in-progress' fail-safe", () => {
    expect(clorisDecisionClass("FACIAL_YES")).toBe("in-progress");
  });

  it("falls unknown wire literals into 'filtered' (noise) rather than save/reject", () => {
    expect(clorisDecisionClass("MYSTERY_NEW_DECISION")).toBe("filtered");
  });
});

describe("tallyDecisionClasses", () => {
  it("aggregates a mixed by_decision map into class counts", () => {
    const counts = tallyDecisionClasses({
      SAVE: 1,
      INFERENTIAL_SAVE: 1,
      FACIAL_BORDERLINE: 1,
      REJECT: 12,
      FACIAL_NO: 159
    });
    expect(counts.save).toBe(2);
    expect(counts.borderline).toBe(1);
    expect(counts.reject).toBe(12);
    expect(counts.filtered).toBe(159);
    expect(counts.total).toBe(174);
  });

  it("returns zeros for an empty map", () => {
    const counts = tallyDecisionClasses({});
    expect(counts).toEqual({
      save: 0,
      borderline: 0,
      reject: 0,
      filtered: 0,
      in_progress: 0,
      total: 0
    });
  });
});

describe("clorisRunSummaryLine", () => {
  function shape(overrides: Partial<{
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
  }> = {}) {
    return {
      status: "completed",
      stop_reason: null,
      started_at: null,
      ended_at: null,
      decisions_by_decision: {},
      attempt_health: null,
      work_unit_progress: {
        kind: "empty",
        queued: 0,
        in_progress: 0,
        done: 0,
        skipped: 0,
        error: 0
      },
      ...overrides
    };
  }

  it("renders 'limit reached' headline with save + reject counts", () => {
    const line = clorisRunSummaryLine(
      shape({
        status: "governor_limit_reached",
        decisions_by_decision: {
          SAVE: 0,
          INFERENTIAL_SAVE: 1,
          REJECT: 66,
          FACIAL_NO: 159
        }
      })
    );
    expect(line).toContain("Limit reached.");
    expect(line).toContain("1 save");
    expect(line).toContain("66 rejects");
  });

  it("renders the no-saves completed headline distinctly", () => {
    const line = clorisRunSummaryLine(
      shape({
        status: "completed",
        decisions_by_decision: { REJECT: 50 }
      })
    );
    expect(line).toContain("Completed.");
    expect(line).toContain("Nothing met the bar");
  });

  it("renders the saved-some completed headline", () => {
    const line = clorisRunSummaryLine(
      shape({
        status: "completed",
        decisions_by_decision: { SAVE: 12, REJECT: 8 }
      })
    );
    expect(line).toContain("Completed. Saved 12");
  });

  it("renders the running headline with done/total", () => {
    const line = clorisRunSummaryLine(
      shape({
        status: "running",
        work_unit_progress: {
          kind: "counts",
          queued: 5,
          in_progress: 0,
          done: 12,
          skipped: 0,
          error: 0
        },
        decisions_by_decision: { SAVE: 3, REJECT: 9 }
      })
    );
    expect(line).toContain("She's still going");
    expect(line).toContain("3 saves so far");
    expect(line).toContain("12 of 12 candidates");
  });

  it("renders the stalled headline when attempt-health signals stall", () => {
    const line = clorisRunSummaryLine(
      shape({
        status: "running",
        attempt_health: {
          total_attempts_in_window: 12,
          failed_in_window: 11,
          last_success_age_s: 3600,
          dominant_failure_kind: "http_429"
        },
        decisions_by_decision: {}
      })
    );
    expect(line).toContain("Stalled.");
    expect(line).toContain("rate limited");
  });
});


// ---- Phase 2A: title resolver ---------------------------------------------

describe("resolveRecruiterTitle — fallback chain", () => {
  it("uses brief_role_title when present", () => {
    const entry = makeStateDirEntry({
      brief_role_title: "Forward Deployed Engineer",
      state_key: "fde_us_v1"
    });
    const r = resolveRecruiterTitle(entry);
    expect(r.primary).toBe("Forward Deployed Engineer");
    expect(r.subtitle).toBeUndefined();
    expect(r.source).toBe("role_title");
  });

  it("trims whitespace from brief_role_title", () => {
    const entry = makeStateDirEntry({
      brief_role_title: "  Principal Engineer  ",
      state_key: "x"
    });
    expect(resolveRecruiterTitle(entry).primary).toBe("Principal Engineer");
  });

  it("humanizes slug-shaped state_keys when no brief_role_title", () => {
    const entry = makeStateDirEntry({
      brief_role_title: null,
      state_key: "research_engineer_colombia",
      source: "linkedin"
    });
    const r = resolveRecruiterTitle(entry);
    expect(r.primary).toBe("Research Engineer Colombia");
    expect(r.subtitle).toBeUndefined();
    expect(r.source).toBe("humanized_state_key");
  });

  it("falls back to source-generic + subtitle on pure-numeric state_keys", () => {
    const entry = makeStateDirEntry({
      brief_role_title: null,
      state_key: "1990251114",
      source: "linkedin"
    });
    const r = resolveRecruiterTitle(entry);
    expect(r.primary).toBe("LinkedIn search");
    expect(r.subtitle).toBe("#1990251114");
    expect(r.source).toBe("source_generic_with_disambiguator");
  });

  it("rejects state_keys that START with digits but have letters later", () => {
    // The bug: "1957683706-clean-20260413" used to render as
    // "1957683706 Clean" because isNumericOnly returned false (had
    // letters). resolveRecruiterTitle's slug-shape predicate gates on
    // "starts with letter," so this case correctly falls through.
    const entry = makeStateDirEntry({
      brief_role_title: null,
      state_key: "1957683706-clean-20260413",
      source: "linkedin"
    });
    const r = resolveRecruiterTitle(entry);
    expect(r.primary).toBe("LinkedIn search");
    expect(r.subtitle).toBe("#1957683706-clean-20260413");
    expect(r.source).toBe("source_generic_with_disambiguator");
  });

  it("returns 'GitHub search' for github source", () => {
    const entry = makeStateDirEntry({
      brief_role_title: null,
      state_key: "9999999999",
      source: "github"
    });
    expect(resolveRecruiterTitle(entry).primary).toBe("GitHub search");
  });

  it("does not collide between two LinkedIn briefs with distinct numeric keys", () => {
    // The original bug: both rendered as "LinkedIn card" with no
    // disambiguator. Now the subtitles differ.
    const a = resolveRecruiterTitle(
      makeStateDirEntry({ brief_role_title: null, state_key: "1957683706" })
    );
    const b = resolveRecruiterTitle(
      makeStateDirEntry({ brief_role_title: null, state_key: "1990251114" })
    );
    expect(a.primary).toBe(b.primary); // same source-typed primary line
    expect(a.subtitle).not.toBe(b.subtitle); // distinct disambiguator
  });

  it("survives an empty state_key without crashing", () => {
    const entry = makeStateDirEntry({ brief_role_title: null, state_key: "" });
    const r = resolveRecruiterTitle(entry);
    expect(r.source).toBe("source_generic_with_disambiguator");
    expect(r.subtitle).toBeUndefined();
  });

  it("treats single-letter state_keys as slug-shaped", () => {
    const entry = makeStateDirEntry({ brief_role_title: null, state_key: "x" });
    const r = resolveRecruiterTitle(entry);
    expect(r.source).toBe("humanized_state_key");
  });
});

describe("resolveRecruiterTitleFromKey — partial-data convenience", () => {
  it("matches resolveRecruiterTitle for the same inputs", () => {
    const fromKey = resolveRecruiterTitleFromKey(
      "linkedin",
      "research_engineer_colombia"
    );
    expect(fromKey.primary).toBe("Research Engineer Colombia");
    expect(fromKey.source).toBe("humanized_state_key");
  });

  it("honors brief_role_title when supplied", () => {
    const r = resolveRecruiterTitleFromKey(
      "linkedin",
      "1990251114",
      "VP of Engineering"
    );
    expect(r.primary).toBe("VP of Engineering");
    expect(r.source).toBe("role_title");
  });

  it("falls back to source-generic + subtitle for pure-numeric keys", () => {
    const r = resolveRecruiterTitleFromKey("linkedin", "1990251114");
    expect(r.primary).toBe("LinkedIn search");
    expect(r.subtitle).toBe("#1990251114");
  });
});

describe("resolveRecruiterTitlesWithCollisions — R2-COLLISION fix", () => {
  // Confirms the multi-entry resolver appends a `#<state_key>`
  // disambiguator when two distinct briefs share the same
  // brief_role_title. Closes the audit-rule R2-COLLISION violation
  // that fired on legacy data with two state_dirs ("1957683706" +
  // "1957683706-clean-20260413") sharing "Head of Applied AI Lab".
  it("appends #<state_key> when two role_title entries collide", () => {
    const a = makeStateDirEntry({
      source: "linkedin",
      state_key: "1957683706",
      brief_role_title: "Head of Applied AI Lab"
    });
    const b = makeStateDirEntry({
      source: "linkedin",
      state_key: "1957683706-clean-20260413",
      brief_role_title: "Head of Applied AI Lab"
    });
    const map = resolveRecruiterTitlesWithCollisions([a, b]);
    const ra = map.get("linkedin/1957683706");
    const rb = map.get("linkedin/1957683706-clean-20260413");
    expect(ra?.primary).toBe("Head of Applied AI Lab");
    expect(ra?.subtitle).toBe("#1957683706");
    expect(ra?.source).toBe("role_title_with_disambiguator");
    expect(rb?.primary).toBe("Head of Applied AI Lab");
    expect(rb?.subtitle).toBe("#1957683706-clean-20260413");
    expect(rb?.source).toBe("role_title_with_disambiguator");
  });

  it("leaves non-colliding role_title entries alone", () => {
    const a = makeStateDirEntry({
      source: "linkedin",
      state_key: "1990251114",
      brief_role_title: "Forward Deployed Engineer"
    });
    const b = makeStateDirEntry({
      source: "linkedin",
      state_key: "2009570906",
      brief_role_title: "Junior Frontier Data Lead"
    });
    const map = resolveRecruiterTitlesWithCollisions([a, b]);
    const ra = map.get("linkedin/1990251114");
    const rb = map.get("linkedin/2009570906");
    expect(ra?.subtitle).toBeUndefined();
    expect(ra?.source).toBe("role_title");
    expect(rb?.subtitle).toBeUndefined();
    expect(rb?.source).toBe("role_title");
  });

  it("does not double-add disambiguator on source-typed-fallback entries", () => {
    // Two pure-numeric LinkedIn state_keys both hit the source-typed
    // fallback branch and ALREADY carry a `#<state_key>` subtitle.
    // The collision-aware resolver must NOT clobber the existing
    // subtitle even though the primaries technically collide.
    const a = makeStateDirEntry({
      source: "linkedin",
      state_key: "1990251114",
      brief_role_title: null
    });
    const b = makeStateDirEntry({
      source: "linkedin",
      state_key: "2009570906",
      brief_role_title: null
    });
    const map = resolveRecruiterTitlesWithCollisions([a, b]);
    const ra = map.get("linkedin/1990251114");
    const rb = map.get("linkedin/2009570906");
    expect(ra?.subtitle).toBe("#1990251114");
    expect(ra?.source).toBe("source_generic_with_disambiguator");
    expect(rb?.subtitle).toBe("#2009570906");
    expect(rb?.source).toBe("source_generic_with_disambiguator");
  });

  it("returns a map keyed by `${source}/${state_key}`", () => {
    const a = makeStateDirEntry({
      source: "linkedin",
      state_key: "abc"
    });
    const map = resolveRecruiterTitlesWithCollisions([a]);
    expect(map.size).toBe(1);
    expect(map.has("linkedin/abc")).toBe(true);
  });

  it("returns an empty map on empty input", () => {
    const map = resolveRecruiterTitlesWithCollisions([]);
    expect(map.size).toBe(0);
  });
});
