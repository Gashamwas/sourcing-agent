// Briefs library tests — Phase D Slice D1.
//
// Pins the contract of `#/briefs`:
// - Renders one card per authored brief with role title (Fraunces),
//   source eyebrow (mono-caps), status pill, and Saves/Runs/Last touched fields.
// - Card link target is brief-first (`#/workspace/<brief_id>`).
// - Empty state: italic Cloris-voice line + Start one CTA.
// - Loading state.
// - Error state.

import { vi } from "vitest";
import { render, screen } from "@testing-library/svelte";
import { afterEach, beforeEach, describe, it, expect } from "vitest";

import Briefs from "../Briefs.svelte";
import type { BriefInfo, BriefsListResponse } from "../../lib/types";

vi.mock("../../lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../lib/api")>();
  return {
    ...actual,
    getBriefs: vi.fn()
  };
});

import { getBriefs } from "../../lib/api";

function makeBrief(overrides: Partial<BriefInfo> = {}): BriefInfo {
  return {
    path: "config/brief-fde-nyc.json",
    role_title: "Forward Deployed Engineer",
    linkedin_project: "FDE NYC",
    linkedin_project_id: "1990251114",
    modified_at: "2026-04-30T00:00:00+00:00",
    brief_id: "1990251114",
    last_run_id: 12,
    last_run_at: "2026-04-29T11:30:00Z",
    last_run_status: "completed",
    last_run_source: "linkedin",
    total_runs: 4,
    total_saves: 23,
    ...overrides
  };
}

function seedBriefs(briefs: BriefInfo[]): void {
  (getBriefs as unknown as ReturnType<typeof vi.fn>).mockResolvedValue({
    slice: "v0-briefs-list-1",
    briefs
  } satisfies BriefsListResponse);
}

beforeEach(() => {
  (getBriefs as unknown as ReturnType<typeof vi.fn>).mockReset();
});

afterEach(() => {
  vi.restoreAllMocks();
});

async function flushMicrotasks(): Promise<void> {
  await new Promise((r) => setTimeout(r, 0));
  await new Promise((r) => setTimeout(r, 0));
}

describe("Briefs — happy path render", () => {
  it("renders a card per brief with role title", async () => {
    seedBriefs([
      makeBrief({ path: "a.json", role_title: "FDE", brief_id: "a" }),
      makeBrief({ path: "b.json", role_title: "FDL", brief_id: "b" })
    ]);
    const { container } = render(Briefs);
    await flushMicrotasks();

    const cards = container.querySelectorAll(".briefs-card");
    expect(cards).toHaveLength(2);
    expect(container.textContent ?? "").toContain("FDE");
    expect(container.textContent ?? "").toContain("FDL");
  });

  it("each card links to the brief-first workspace", async () => {
    seedBriefs([makeBrief({ brief_id: "1990251114" })]);
    const { container } = render(Briefs);
    await flushMicrotasks();

    const link = container.querySelector(".briefs-card") as HTMLAnchorElement | null;
    expect(link).not.toBeNull();
    expect(link?.getAttribute("href")).toBe("#/workspace/1990251114");
  });

  it("renders source eyebrow + status pill from last_run metadata", async () => {
    seedBriefs([
      makeBrief({
        last_run_source: "linkedin",
        last_run_status: "completed"
      })
    ]);
    const { container } = render(Briefs);
    await flushMicrotasks();

    expect(
      container.querySelector(".briefs-card-source-eyebrow")?.textContent
    ).toContain("LinkedIn");
    const pill = container.querySelector(".card-status");
    expect(pill?.textContent?.trim()).toBe("Completed");
    expect(pill?.classList.contains("card-status--completed")).toBe(true);
  });

  it("renders Saves on each card (Plan Finding 13: Runs cell removed)", async () => {
    seedBriefs([
      makeBrief({ total_saves: 7, total_runs: 3 })
    ]);
    const { container } = render(Briefs);
    await flushMicrotasks();

    const labels = Array.from(
      container.querySelectorAll(".briefs-card-field-label")
    ).map((el) => el.textContent?.trim());
    const values = Array.from(
      container.querySelectorAll(".briefs-card-field-value")
    ).map((el) => el.textContent?.trim());
    // Saves is decision-influencing; Runs was operational metadata
    // about Cloris's execution loop and the recruiter never made
    // decisions against it. Pinning the removal here.
    expect(labels).toContain("Saves");
    expect(labels).not.toContain("Runs");
    expect(values).toContain("7");
    expect(values).not.toContain("3");
  });

  it("renders 'No runs yet' pill when last_run_status is null", async () => {
    seedBriefs([
      makeBrief({
        last_run_id: null,
        last_run_at: null,
        last_run_status: null,
        last_run_source: null,
        total_runs: 0,
        total_saves: 0
      })
    ]);
    const { container } = render(Briefs);
    await flushMicrotasks();

    const pill = container.querySelector(".card-status");
    expect(pill?.textContent?.trim()).toBe("No runs yet");
    expect(pill?.classList.contains("card-status--no-runs")).toBe(true);
  });
});

describe("Briefs — empty + error", () => {
  it("renders the empty state with Start-one CTA when no briefs", async () => {
    seedBriefs([]);
    const { container } = render(Briefs);
    await flushMicrotasks();

    expect(
      container.querySelector(".briefs-empty")
    ).not.toBeNull();
    expect(
      container.querySelector(".briefs-empty-line")?.textContent
    ).toContain("haven't authored");
    const cta = container.querySelector(".briefs-empty-link") as HTMLAnchorElement | null;
    expect(cta?.getAttribute("href")).toBe("#/brief/new");
  });

  it("renders an error line when getBriefs rejects", async () => {
    (getBriefs as unknown as ReturnType<typeof vi.fn>).mockRejectedValue(
      new Error("boom")
    );
    const { container } = render(Briefs);
    await flushMicrotasks();

    expect(
      container.querySelector(".briefs-page-error")
    ).not.toBeNull();
  });

  it("R9: rendered body contains no absolute /Users/ path", async () => {
    seedBriefs([
      makeBrief({ path: "config/brief-fde.json", brief_id: "1990251114" })
    ]);
    const { container } = render(Briefs);
    await flushMicrotasks();
    expect(container.textContent ?? "").not.toContain("/Users/");
  });

  it("Ledger L24: legacy briefs without role_title render humanized stems, not raw paths", async () => {
    // Phase D Block C ensemble caught: legacy briefs with no
    // role_title fell through to `{role_title ?? path}`, leaking
    // `config/FDL-Colombia/brief-colombia-v2.json` into the card title
    // (R2 violation). cardTitle() humanizes them.
    seedBriefs([
      makeBrief({
        path: "config/FDL-Colombia/brief-colombia-v2.json",
        role_title: null,
        brief_id: "fdl-colombia"
      }),
      makeBrief({
        path: "config/legacy-brief.json",
        role_title: null,
        brief_id: "legacy"
      }),
      makeBrief({
        path: "config/Head-of-Applied-AI/brief.json",
        role_title: null,
        brief_id: "head-aai"
      })
    ]);
    const { container } = render(Briefs);
    await flushMicrotasks();

    const titles = Array.from(
      container.querySelectorAll(".briefs-card-title")
    ).map((el) => el.textContent?.trim());
    // None of the rendered titles should leak filesystem paths.
    for (const t of titles) {
      expect(t).not.toContain("config/");
      expect(t).not.toContain(".json");
      expect(t).toContain("(Legacy)");
    }
    // Specific humanizations.
    expect(titles).toContain("colombia-v2 (Legacy)");
    expect(titles).toContain("legacy-brief (Legacy)");
    // Nested-with-no-role-title falls back to the parent dir name.
    expect(titles).toContain("Head-of-Applied-AI (Legacy)");
  });
});
