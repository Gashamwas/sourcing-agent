// Tests for the display helpers (lib/display.ts).
//
// Pin both `displayName` (which has a 4-step derivation policy) and
// `catalogNumber` (which is pure source + sanitized state_key) against
// realistic StateDirEntry shapes.

import { describe, it, expect } from "vitest";
import { displayName, catalogNumber } from "../lib/display";
import { makeStateDirEntry } from "./fixtures";

describe("displayName", () => {
  it("uses brief_id_from_run when it has letters", () => {
    const entry = makeStateDirEntry({
      brief_id_from_run: "fde-staff-platform"
    });
    // humanize: split on - → "Fde Staff Platform", then acronym map
    // applies to "fde" → "FDE Staff Platform".
    expect(displayName(entry)).toBe("FDE Staff Platform");
  });

  it("uses brief_path_from_worker basename (no extension) when brief_id is missing", () => {
    const entry = makeStateDirEntry({
      brief_id_from_run: null,
      brief_path_from_worker: "/work/briefs/swe-frontend-lead.json"
    });
    expect(displayName(entry)).toBe("SWE Frontend Lead");
  });

  it("uses cleaned state_key when brief id and path both lack letters", () => {
    const entry = makeStateDirEntry({
      brief_id_from_run: null,
      brief_path_from_worker: null,
      state_key: "platform-engineer-east"
    });
    expect(displayName(entry)).toBe("Platform Engineer East");
  });

  it("returns 'LinkedIn card' when all candidates are numeric-only and source is linkedin", () => {
    const entry = makeStateDirEntry({
      source: "linkedin",
      brief_id_from_run: "2015831122",
      brief_path_from_worker: null,
      state_key: "1957683706"
    });
    expect(displayName(entry)).toBe("LinkedIn card");
  });

  it("returns 'GitHub card' when all candidates are numeric-only and source is github", () => {
    const entry = makeStateDirEntry({
      source: "github",
      brief_id_from_run: "12345678",
      brief_path_from_worker: null,
      state_key: "987654321"
    });
    expect(displayName(entry)).toBe("GitHub card");
  });

  it("returns the empty string when brief_id is empty (whitespace-trimmed) and falls through", () => {
    // Whitespace-only brief_id_from_run trims to "" and is therefore
    // skipped — verifies the empty/falsy guard in the brief-id branch.
    const entry = makeStateDirEntry({
      source: "linkedin",
      brief_id_from_run: "   ",
      brief_path_from_worker: null,
      state_key: "engineering-card"
    });
    expect(displayName(entry)).toBe("Engineering Card");
  });
});

describe("catalogNumber", () => {
  it("prefixes LinkedIn state keys with LI-", () => {
    const entry = makeStateDirEntry({
      source: "linkedin",
      state_key: "fde-staff-platform"
    });
    expect(catalogNumber(entry)).toBe("LI-FDE-STAFF-PLATFORM");
  });

  it("prefixes GitHub state keys with GH-", () => {
    const entry = makeStateDirEntry({
      source: "github",
      state_key: "platform-engineer-east"
    });
    expect(catalogNumber(entry)).toBe("GH-PLATFORM-ENGINEER-EAST");
  });

  it("sanitizes special characters in the state_key (non-alphanumeric collapses to a single hyphen)", () => {
    const entry = makeStateDirEntry({
      source: "linkedin",
      state_key: "swe@frontend!lead#1"
    });
    // After uppercase: "SWE@FRONTEND!LEAD#1"
    // Replace non [A-Z0-9-] → "SWE-FRONTEND-LEAD-1"
    // No leading/trailing hyphens to strip.
    expect(catalogNumber(entry)).toBe("LI-SWE-FRONTEND-LEAD-1");
  });

  it("strips leading and trailing hyphens introduced by sanitization", () => {
    const entry = makeStateDirEntry({
      source: "github",
      state_key: "_swe-platform_"
    });
    // After uppercase: "_SWE-PLATFORM_"
    // Replace non [A-Z0-9-] → "-SWE-PLATFORM-"
    // Collapse repeats → "-SWE-PLATFORM-"
    // Trim ends → "SWE-PLATFORM".
    expect(catalogNumber(entry)).toBe("GH-SWE-PLATFORM");
  });

  it("caps long state_keys to 28 characters after sanitization", () => {
    const entry = makeStateDirEntry({
      source: "linkedin",
      // 50-char state key.
      state_key: "abcdefghijklmnopqrstuvwxyz0123456789abcdefghijklmn"
    });
    const result = catalogNumber(entry);
    expect(result).toBe("LI-" + "ABCDEFGHIJKLMNOPQRSTUVWXYZ01");
    expect(result.length).toBe(3 + 28);
  });
});
