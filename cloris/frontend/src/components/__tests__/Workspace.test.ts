// Workspace tests — Phase C-bis 0.1 brief-first surface.
//
// Pins the contract of #/workspace/<brief_id>:
// - Renders recipe-card stats (total / this week / shortlisted / last save).
// - Renders one CandidateCard per save with brief-first navigation.
// - 404 (workspace_not_found) renders the not-found surface, NOT the loading skeleton.
// - Empty-saves state renders the SEARCHING loader (Finding) + empty title.
// - "View latest run report" link only renders when latest_run is set.

import { render } from "@testing-library/svelte";
import { afterEach, beforeEach, describe, it, expect, vi } from "vitest";
import Workspace from "../Workspace.svelte";
import type {
  CandidateCardSummary,
  WorkspaceResponse
} from "../../lib/types";

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" }
  });
}

function makeCard(
  overrides: Partial<CandidateCardSummary> = {}
): CandidateCardSummary {
  return {
    candidate_id: 1,
    source: "linkedin",
    identity_key: "li-default",
    display_name: "Anonymous Save",
    profile_url: "https://example.com/anon",
    terminal_decision: "SAVE",
    save_reason: null,
    confidence: 0.85,
    first_seen_at: "2026-04-29T10:00:00Z",
    last_seen_at: "2026-04-29T11:30:00Z",
    user_status: null,
    ...overrides
  };
}

function makeWorkspace(
  overrides: Partial<WorkspaceResponse> = {}
): WorkspaceResponse {
  return {
    slice: "v0-shell-slice-c5",
    brief_id: "brief-1",
    sources: ["linkedin"],
    brief_role_title: "Senior Forward Deployed Engineer",
    brief_linkedin_project: "FDE NYC",
    latest_run: {
      source: "linkedin",
      state_key: "research_engineer_colombia",
      run_id: 12
    },
    total_saves: 2,
    saves_this_week: 2,
    shortlisted_count: 0,
    last_save_at: "2026-04-29T11:30:00Z",
    candidates: [
      makeCard({ candidate_id: 1, display_name: "Pat Doe", save_reason: "Strong fit" }),
      makeCard({ candidate_id: 2, display_name: "Alex Smith", save_reason: "Adjacent" })
    ],
    ...overrides
  };
}

beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn());
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

async function flushMicrotasks(): Promise<void> {
  await new Promise((r) => setTimeout(r, 0));
  await new Promise((r) => setTimeout(r, 0));
}

describe("Workspace — happy path render", () => {
  it("renders one CandidateCard per save", async () => {
    (fetch as unknown as ReturnType<typeof vi.fn>).mockResolvedValue(
      jsonResponse(makeWorkspace())
    );
    const { container } = render(Workspace, {
      briefId: "brief-1"
    });
    await flushMicrotasks();
    expect(container.querySelectorAll(".candidate-card").length).toBe(2);
  });

  it("renders the recipe-card stats with total + shortlisted counts", async () => {
    // Plan Finding 5: dropped "Saves this week" and "Last save" cells.
    // "Last save" duplicated the byline date; "Saves this week" was
    // engineering-vocabulary leak (a metric existed, so it surfaced).
    // Total saves + Shortlisted are the two stats that drive recruiter
    // decisions: how much there is to look through, and how far through
    // it they are.
    (fetch as unknown as ReturnType<typeof vi.fn>).mockResolvedValue(
      jsonResponse(
        makeWorkspace({
          total_saves: 7,
          saves_this_week: 3,
          shortlisted_count: 2
        })
      )
    );
    const { container } = render(Workspace, {
      briefId: "brief-1"
    });
    await flushMicrotasks();
    const stats = Array.from(
      container.querySelectorAll(".workspace-stat-value")
    ).map((el) => el.textContent?.trim());
    expect(stats).toEqual(["7", "2"]);

    const labels = Array.from(
      container.querySelectorAll(".workspace-stat-label")
    ).map((el) => el.textContent?.trim());
    expect(labels).not.toContain("Saves this week");
    expect(labels).not.toContain("Last save");
  });

  it("each card links to brief-first #/candidate/...", async () => {
    (fetch as unknown as ReturnType<typeof vi.fn>).mockResolvedValue(
      jsonResponse(makeWorkspace())
    );
    const { container } = render(Workspace, {
      briefId: "brief-1"
    });
    await flushMicrotasks();
    const first = container.querySelector(
      "a.candidate-card"
    ) as HTMLAnchorElement | null;
    expect(first?.getAttribute("href")).toBe("#/candidate/brief-1/1");
  });

  it('renders the "View latest run report" link when latest_run is set', async () => {
    (fetch as unknown as ReturnType<typeof vi.fn>).mockResolvedValue(
      jsonResponse(
        makeWorkspace({
          latest_run: {
            source: "linkedin",
            state_key: "research_engineer_colombia",
            run_id: 99
          }
        })
      )
    );
    const { container } = render(Workspace, {
      briefId: "brief-1"
    });
    await flushMicrotasks();
    const link = container.querySelector(
      ".workspace-run-link a"
    ) as HTMLAnchorElement | null;
    expect(link?.getAttribute("href")).toBe(
      "#/run/linkedin/research_engineer_colombia/99"
    );
  });
});

describe("Workspace — fallbacks and error paths", () => {
  it("renders the empty-grid state when no saves exist", async () => {
    (fetch as unknown as ReturnType<typeof vi.fn>).mockResolvedValue(
      jsonResponse(
        makeWorkspace({
          total_saves: 0,
          saves_this_week: 0,
          last_save_at: null,
          candidates: []
        })
      )
    );
    const { container } = render(Workspace, {
      briefId: "brief-1"
    });
    await flushMicrotasks();
    expect(container.querySelector(".workspace-empty-grid")).not.toBeNull();
    expect(container.querySelectorAll(".candidate-card").length).toBe(0);
  });

  it("renders not-found on a 404 response", async () => {
    (fetch as unknown as ReturnType<typeof vi.fn>).mockResolvedValue(
      jsonResponse(
        { detail: { error: "workspace_not_found" } },
        404
      )
    );
    const { container } = render(Workspace, {
      briefId: "brief-missing"
    });
    await flushMicrotasks();
    expect(container.querySelector(".workspace-empty")).not.toBeNull();
    expect(
      container.querySelector(".workspace-empty h1")?.textContent
    ).toContain("couldn't find that workspace");
  });

  it("R9: rendered body contains no absolute /Users/ path", async () => {
    (fetch as unknown as ReturnType<typeof vi.fn>).mockResolvedValue(
      jsonResponse(makeWorkspace())
    );
    const { container } = render(Workspace, {
      briefId: "brief-1"
    });
    await flushMicrotasks();
    expect(container.textContent ?? "").not.toContain("/Users/");
  });
});
