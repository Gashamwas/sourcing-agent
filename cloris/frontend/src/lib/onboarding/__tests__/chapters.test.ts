// Tests for INTAKE_CHAPTER_MAP — Phase D Slice D3.
//
// The map is a single Svelte-side constant grouping the backend's 11
// intake phases into ~6 UI chapters. The architectural-fit critique's
// risk #1 was "the map drifts when backend phases get added"; these
// tests pin the discipline that prevents silent drift.

import { describe, it, expect } from "vitest";
import {
  INTAKE_CHAPTER_MAP,
  assertAllPhasesCovered,
  chapterForPhase,
  firstPhaseOf,
  nextChapter,
} from "../chapters";
import type { IntakeStep } from "../../types";

describe("INTAKE_CHAPTER_MAP — coverage", () => {
  it("every backend phase is covered by exactly one chapter", () => {
    const allPhases = assertAllPhasesCovered(); // throws on gap
    // 11 baseline phases + 1 design_rubric phase added in Designer
    // Slice 4 = 12. Adding a phase requires both this test bump and
    // an entry in `assertAllPhasesCovered.ALL_PHASES`.
    expect(allPhases.length).toBe(12);
    // No phase appears in more than one chapter.
    for (const phase of allPhases) {
      const matches = INTAKE_CHAPTER_MAP.filter((c) =>
        c.phases.includes(phase)
      );
      expect(matches.length).toBe(1);
    }
  });

  it("chapter ids are unique", () => {
    const ids = INTAKE_CHAPTER_MAP.map((c) => c.chapter_id);
    expect(new Set(ids).size).toBe(ids.length);
  });

  it("each chapter has non-empty heading + deck + forwardLabel + eyebrow", () => {
    for (const c of INTAKE_CHAPTER_MAP) {
      expect(c.heading.length).toBeGreaterThan(0);
      expect(c.deck.length).toBeGreaterThan(0);
      expect(c.forwardLabel.length).toBeGreaterThan(0);
      expect(c.eyebrow.length).toBeGreaterThan(0);
    }
  });

  it("forwardLabel is Cloris-voice — never the generic 'Next'", () => {
    for (const c of INTAKE_CHAPTER_MAP) {
      expect(c.forwardLabel.toLowerCase()).not.toBe("next");
    }
  });
});

describe("INTAKE_CHAPTER_MAP — lookups", () => {
  it("chapterForPhase returns the chapter that owns the phase", () => {
    const ch = chapterForPhase("good_looks_like");
    expect(ch?.chapter_id).toBe("good_looks");
  });

  it("chapterForPhase returns null for an unknown phase", () => {
    // The TS type forbids this, but a backend-added phase that the
    // wizard hasn't been taught about would slip past at runtime.
    const ch = chapterForPhase("phase_not_in_map" as unknown as IntakeStep);
    expect(ch).toBeNull();
  });

  it("nextChapter advances in declared order", () => {
    const after_role = nextChapter("role");
    expect(after_role?.chapter_id).toBe("good_looks");
    const after_completed = nextChapter("completed");
    expect(after_completed).toBeNull();
  });

  it("firstPhaseOf returns the chapter's first declared phase", () => {
    const role = INTAKE_CHAPTER_MAP.find((c) => c.chapter_id === "role")!;
    expect(firstPhaseOf(role)).toBe("role_basics");
  });
});
