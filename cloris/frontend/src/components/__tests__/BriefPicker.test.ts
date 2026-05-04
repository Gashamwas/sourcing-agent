// BriefPicker tests — pin the post-Gemini-review subtitle policy.
//
// What we guard:
//   - Subtitle suppressed when it would echo the primary label
//     (case-insensitive). Caught a real defect: a brief whose
//     linkedin_project mirrored its role_title rendered "Head of
//     Applied AI Lab / Head of Applied AI Lab" — a duplication that
//     reads as a template failure on the home picker.
//   - Subtitle never falls back to brief.path. Phase D's L24 closed
//     the path-as-card-primary leak in the brief library; the picker
//     was a parallel leak surface (subtitle fallback).
//   - Distinct subtitles still render — disambiguator behavior
//     preserved when a recruiter has two briefs with the same
//     role_title but different linkedin projects.
//   - Falls through to "LinkedIn #<id>" when project label collides
//     with primary but a project ID exists.

import { render } from "@testing-library/svelte";
import { tick } from "svelte";
import { afterEach, beforeEach, describe, it, expect, vi } from "vitest";
import BriefPicker from "../BriefPicker.svelte";
import type { BriefInfo } from "../../lib/types";

vi.mock("../../lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../lib/api")>();
  return {
    ...actual,
    getBriefs: vi.fn()
  };
});

import { getBriefs } from "../../lib/api";

function seed(briefs: BriefInfo[]): void {
  (getBriefs as unknown as ReturnType<typeof vi.fn>).mockResolvedValue({
    slice: "v0-briefs-list-1",
    briefs
  });
}

beforeEach(() => {
  vi.clearAllMocks();
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("BriefPicker — subtitle policy", () => {
  it("suppresses the subtitle when it would mirror the primary label", async () => {
    seed([
      {
        path: "config/Head-of-Applied-AI-Lab/brief.json",
        role_title: "Head of Applied AI Lab",
        // The recruiter named the LinkedIn project the same as the role.
        // Without the duplicate guard, the picker rendered the title
        // twice. Subtitle should drop and the card collapses to one line.
        linkedin_project: "Head of Applied AI Lab",
        linkedin_project_id: null,
        modified_at: "2026-04-30T00:00:00+00:00"
      }
    ]);
    const { container } = render(BriefPicker, { props: { onSelect: () => {} } });
    await tick();
    await tick();
    const primary = container.querySelector(".brief-picker-primary");
    const subtitle = container.querySelector(".brief-picker-subtitle");
    expect(primary?.textContent).toBe("Head of Applied AI Lab");
    expect(subtitle).toBeNull();
  });

  it("falls through to 'LinkedIn #<id>' when the project label echoes primary", async () => {
    seed([
      {
        path: "config/Head-of-Applied-AI-Lab/brief.json",
        role_title: "Head of Applied AI Lab",
        linkedin_project: "Head of Applied AI Lab",
        linkedin_project_id: "1990251114",
        modified_at: "2026-04-30T00:00:00+00:00"
      }
    ]);
    const { container } = render(BriefPicker, { props: { onSelect: () => {} } });
    await tick();
    await tick();
    const subtitle = container.querySelector(".brief-picker-subtitle");
    expect(subtitle?.textContent).toBe("LinkedIn #1990251114");
  });

  it("renders a distinct project label when it differs from primary", async () => {
    seed([
      {
        path: "config/brief-fde.json",
        role_title: "Forward Deployed Engineer",
        linkedin_project: "FDE NYC",
        linkedin_project_id: "1990251114",
        modified_at: "2026-04-30T00:00:00+00:00"
      }
    ]);
    const { container } = render(BriefPicker, { props: { onSelect: () => {} } });
    await tick();
    await tick();
    expect(
      container.querySelector(".brief-picker-primary")?.textContent
    ).toBe("Forward Deployed Engineer");
    expect(
      container.querySelector(".brief-picker-subtitle")?.textContent
    ).toBe("FDE NYC");
  });

  it("never falls back to brief.path as the subtitle (path-leak guard)", async () => {
    seed([
      {
        path: "config/brief-orphan.json",
        role_title: "Orphan brief",
        // No linkedin_project, no linkedin_project_id. Old behavior:
        // subtitle = brief.path. New behavior: subtitle suppressed.
        linkedin_project: null,
        linkedin_project_id: null,
        modified_at: "2026-04-30T00:00:00+00:00"
      }
    ]);
    const { container } = render(BriefPicker, { props: { onSelect: () => {} } });
    await tick();
    await tick();
    const subtitle = container.querySelector(".brief-picker-subtitle");
    expect(subtitle).toBeNull();
    // Belt-and-suspenders: the path string never appears in the
    // rendered card body.
    expect(container.textContent ?? "").not.toContain("config/brief-orphan.json");
  });
});
