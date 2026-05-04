// Tests for the centralized copy module.
//
// What we're guarding (post Mock 4 density pass):
//   - The killed phrase "sorting the pile" (copy-bank :23-26) cannot appear
//     in any export. This is a voice-safety regression test.
//   - Card-file metaphor consistency: ledger-era language ("the ledger",
//     "the pile") was deliberately removed and must not be reintroduced.
//   - Pluralization handles regular -s and -y → -ies.
//   - Connection-loss copy is plain operational and never echoes character
//     voice or killed phrases.
//   - Sample structural exports (eyebrow, tab labels, reference slip) exist
//     and resolve to their canonical strings.
//
// The prior `cardFileRibbonTotal()` builder was retired alongside the
// "N BRIEFS ACTIVE" sum cell; tests for it moved with it.

import { describe, it, expect } from "vitest";
import * as copy from "../lib/copy";
import {
  cardFileBackTabLabel,
  cardFileFrontTabLabel,
  connectionLossMessage,
  launchPanelEyebrow,
  pluralize,
  referenceSlipLabel
} from "../lib/copy";

describe("connectionLossMessage", () => {
  it("is a non-empty string", () => {
    expect(typeof connectionLossMessage).toBe("string");
    expect(connectionLossMessage.length).toBeGreaterThan(0);
  });

  it("does not contain killed character-voice phrases", () => {
    const lower = connectionLossMessage.toLowerCase();
    expect(lower).not.toContain("sorting the pile");
    expect(lower).not.toContain("the ledger");
    expect(lower).not.toContain("the pile");
    // Plain operational tone — no character voice in error states.
    expect(lower).not.toContain("she");
  });
});

describe("voice safety — killed lines never ship", () => {
  // Enumerate every plain-string export and the dynamic helpers so killed
  // phrases can't sneak back into ANY export.
  function collectAllStrings(): string[] {
    const out: string[] = [];

    // Plain string exports.
    for (const value of Object.values(copy)) {
      if (typeof value === "string") out.push(value);
    }

    // pluralize — exercise singular and plural for representative nouns.
    for (const noun of ["card", "directory", "thread", "drawer", "run"]) {
      for (const n of [0, 1, 2, 5]) {
        out.push(pluralize(noun, n));
      }
    }

    return out;
  }

  it("no exported string contains 'sorting the pile'", () => {
    const all = collectAllStrings();
    const offenders = all.filter((s) => s.toLowerCase().includes("sorting the pile"));
    expect(offenders).toEqual([]);
  });

  it("no exported string contains 'the ledger' (ledger-era voice retired)", () => {
    const all = collectAllStrings();
    const offenders = all.filter((s) => s.toLowerCase().includes("the ledger"));
    expect(offenders).toEqual([]);
  });

  it("no exported string contains 'the pile' (ledger-era voice retired)", () => {
    const all = collectAllStrings();
    const offenders = all.filter((s) => s.toLowerCase().includes("the pile"));
    expect(offenders).toEqual([]);
  });
});

describe("pluralize", () => {
  it("returns the plural for n=0", () => {
    expect(pluralize("card", 0)).toBe("cards");
  });

  it("returns the singular for n=1", () => {
    expect(pluralize("card", 1)).toBe("card");
  });

  it("returns the plural for n>1", () => {
    expect(pluralize("card", 2)).toBe("cards");
  });

  it("keeps 'directory' singular at n=1", () => {
    expect(pluralize("directory", 1)).toBe("directory");
  });

  it("converts -y to -ies for n>1 (consonant + y)", () => {
    expect(pluralize("directory", 2)).toBe("directories");
  });
});

describe("static exports are non-empty", () => {
  // Cheap smoke test — catches accidental empty-string regressions.
  it("every static export is a non-empty string", () => {
    for (const [key, value] of Object.entries(copy)) {
      if (typeof value === "string") {
        expect(value.length, `expected ${key} to be non-empty`).toBeGreaterThan(0);
      }
    }
  });

  // Reference structural named imports explicitly so the test fails at
  // compile time if any required export is renamed or removed.
  it("structural named exports resolve to canonical operational strings", () => {
    expect(launchPanelEyebrow).toBe("Start a search");
    expect(cardFileFrontTabLabel).toBe("Active");
    expect(cardFileBackTabLabel).toBe("Paused");
    expect(referenceSlipLabel).toBe("Reference Slip");
  });
});

// Phase E Slice E4 (Ledger L6): decisionLabelClass returns "is-inferential"
// only for INFERENTIAL_SAVE; empty otherwise. Pinning so the call sites
// (CandidateCard, StatusPillToggle, RunReportPage) keep aligning class
// against the same key.
describe("decisionLabelClass — L6 italics gate", () => {
  it("returns is-inferential for INFERENTIAL_SAVE", () => {
    expect(copy.decisionLabelClass("INFERENTIAL_SAVE")).toBe("is-inferential");
  });
  it("returns empty for SAVE", () => {
    expect(copy.decisionLabelClass("SAVE")).toBe("");
  });
  it("returns empty for null", () => {
    expect(copy.decisionLabelClass(null)).toBe("");
  });
});

// Plan Finding 6 retired `runReportNextRunCalibrationHint`. Pin the
// removal so re-introducing the export trips a test.
describe("runReportNextRunCalibrationHint — Finding 6 retirement", () => {
  it("is no longer exported (calibration nudge was retired)", () => {
    expect(
      "runReportNextRunCalibrationHint" in copy
    ).toBe(false);
  });
});
