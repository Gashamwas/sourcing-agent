// CandidateDetail tests — Phase C-bis 0.1 brief-first surface.
//
// Pins the contract of #/candidate/<brief_id>/<candidate_id>:
// - Renders the candidate name (Fraunces) and source eyebrow (mono-caps).
// - Renders save reason in italic prose when present.
// - Renders profile URL as an external anchor when present.
// - 404 (candidate_not_found) renders the not-found surface, NOT the loading skeleton.
// - Back-link points at the source run (via source_run.{source,state_key,run_id})
//   when available, falls back to home when no source_run is set.
// - The audit-pipeline R9 rule: no /Users/ paths leak into the rendered
//   body. Sniff for the substring across the full container text.

import { render, screen } from "@testing-library/svelte";
import { afterEach, beforeEach, describe, it, expect, vi } from "vitest";
import CandidateDetail from "../CandidateDetail.svelte";
import type { CandidateDetailResponse } from "../../lib/types";

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" }
  });
}

function makeDetail(
  overrides: Partial<CandidateDetailResponse> = {}
): CandidateDetailResponse {
  return {
    slice: "v0-shell-slice-c5",
    source: "linkedin",
    brief_id: "brief-1",
    candidate_id: 42,
    identity_key: "li-pat-doe",
    display_name: "Pat Doe",
    profile_url: "https://linkedin.com/in/pat",
    terminal_decision: "SAVE",
    confidence: 0.91,
    save_reason: "Strong systems-design background",
    current_lifecycle_state: "full_terminal",
    first_seen_at: "2026-04-29T10:00:00Z",
    last_seen_at: "2026-04-29T11:30:00Z",
    source_run: {
      source: "linkedin",
      state_key: "research_engineer_colombia",
      run_id: 12
    },
    brief_role_title: "Senior Forward Deployed Engineer",
    brief_linkedin_project: "FDE NYC",
    notes: [],
    user_status: null,
    is_failed_state: false,
    judgment_accuracy: null,
    judgment_accuracy_at: null,
    ...overrides
  };
}

beforeEach(() => {
  // Stub global fetch — each test sets its own response with vi.fn.
  vi.stubGlobal("fetch", vi.fn());
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

async function flushMicrotasks(): Promise<void> {
  // Two ticks: first to settle onMount/load(), second to settle the
  // post-set render of the await branch.
  await new Promise((r) => setTimeout(r, 0));
  await new Promise((r) => setTimeout(r, 0));
}

describe("CandidateDetail — happy path render", () => {
  it("renders the source eyebrow and display name", async () => {
    (fetch as unknown as ReturnType<typeof vi.fn>).mockResolvedValue(
      jsonResponse(makeDetail())
    );
    const { container } = render(CandidateDetail, {
      briefId: "brief-1",
      candidateId: "42"
    });
    await flushMicrotasks();
    expect(
      container.querySelector(".surface-eyebrow")?.textContent
    ).toBe("LINKEDIN");
    expect(screen.getByText("Pat Doe")).toBeInTheDocument();
  });

  it("renders the save reason in the editorial body", async () => {
    (fetch as unknown as ReturnType<typeof vi.fn>).mockResolvedValue(
      jsonResponse(makeDetail())
    );
    const { container } = render(CandidateDetail, {
      briefId: "brief-1",
      candidateId: "42"
    });
    await flushMicrotasks();
    expect(
      container.querySelector(".candidate-detail-save-reason-body")?.textContent
    ).toBe("Strong systems-design background");
  });

  it("renders the profile URL as an external anchor", async () => {
    (fetch as unknown as ReturnType<typeof vi.fn>).mockResolvedValue(
      jsonResponse(makeDetail())
    );
    const { container } = render(CandidateDetail, {
      briefId: "brief-1",
      candidateId: "42"
    });
    await flushMicrotasks();
    const link = container.querySelector(
      "a.candidate-detail-profile-link"
    ) as HTMLAnchorElement | null;
    expect(link).not.toBeNull();
    expect(link?.href).toBe("https://linkedin.com/in/pat");
    expect(link?.target).toBe("_blank");
    expect(link?.rel).toContain("noopener");
  });

  it("back-link points at the source run when source_run is set", async () => {
    (fetch as unknown as ReturnType<typeof vi.fn>).mockResolvedValue(
      jsonResponse(
        makeDetail({
          source_run: {
            source: "linkedin",
            state_key: "research_engineer_colombia",
            run_id: 17
          }
        })
      )
    );
    const { container } = render(CandidateDetail, {
      briefId: "brief-1",
      candidateId: "42"
    });
    await flushMicrotasks();
    const back = container.querySelector(
      "a.page-back-link"
    ) as HTMLAnchorElement | null;
    expect(back?.getAttribute("href")).toBe(
      "#/run/linkedin/research_engineer_colombia/17"
    );
  });

  it("back-link falls back to home when source_run is null", async () => {
    (fetch as unknown as ReturnType<typeof vi.fn>).mockResolvedValue(
      jsonResponse(makeDetail({ source_run: null }))
    );
    const { container } = render(CandidateDetail, {
      briefId: "brief-1",
      candidateId: "42"
    });
    await flushMicrotasks();
    const back = container.querySelector(
      "a.page-back-link"
    ) as HTMLAnchorElement | null;
    expect(back?.getAttribute("href")).toBe("#/");
  });

  it("renders the brief role title as a subtitle when present", async () => {
    (fetch as unknown as ReturnType<typeof vi.fn>).mockResolvedValue(
      jsonResponse(
        makeDetail({
          brief_linkedin_project: null,
          brief_role_title: "Principal Engineer"
        })
      )
    );
    const { container } = render(CandidateDetail, {
      briefId: "brief-1",
      candidateId: "42"
    });
    await flushMicrotasks();
    expect(
      container.querySelector(".candidate-detail-brief-subtitle")?.textContent
    ).toBe("Principal Engineer");
  });

  it("demotes confidence to the Reference Slip (Plan Finding 11: false precision)", async () => {
    // LLM-derived confidence is the wrong instrument for row-level
    // prioritization. The percentage no longer surfaces in the
    // header field grid; it lives in the (collapsed-by-default)
    // Reference Slip where a developer can inspect it without
    // weighting the recruiter's read of the candidate.
    (fetch as unknown as ReturnType<typeof vi.fn>).mockResolvedValue(
      jsonResponse(makeDetail({ confidence: 0.87 }))
    );
    const { container } = render(CandidateDetail, {
      briefId: "brief-1",
      candidateId: "42"
    });
    await flushMicrotasks();

    // Confidence is NOT in the header field rows.
    const headerFieldLabels = Array.from(
      container.querySelectorAll(".candidate-detail-field-label")
    ).map((el) => el.textContent?.trim());
    expect(headerFieldLabels).not.toContain("Confidence");

    // After opening the Reference Slip, the percent is visible.
    const toggle = container.querySelector(
      ".candidate-detail-reference-slip-toggle"
    ) as HTMLButtonElement;
    expect(toggle).not.toBeNull();
    toggle.click();
    await flushMicrotasks();
    const slipText = container.querySelector(
      ".candidate-detail-reference-slip-grid"
    )?.textContent ?? "";
    expect(slipText).toContain("87%");
    expect(slipText).toContain("Confidence");
  });
});

describe("CandidateDetail — fallbacks and error paths", () => {
  it("renders not-found on a 404 response", async () => {
    (fetch as unknown as ReturnType<typeof vi.fn>).mockResolvedValue(
      jsonResponse(
        { detail: { error: "candidate_not_found" } },
        404
      )
    );
    const { container } = render(CandidateDetail, {
      briefId: "brief-1",
      candidateId: "999"
    });
    await flushMicrotasks();
    expect(container.querySelector(".candidate-detail-empty")).not.toBeNull();
    expect(
      container.querySelector(".candidate-detail-empty h1")?.textContent
    ).toContain("couldn't find that candidate");
  });

  it("treats a non-numeric candidateId as not-found before any fetch", async () => {
    const fetchSpy = fetch as unknown as ReturnType<typeof vi.fn>;
    const { container } = render(CandidateDetail, {
      briefId: "brief-1",
      candidateId: "not-a-number"
    });
    await flushMicrotasks();
    expect(container.querySelector(".candidate-detail-empty")).not.toBeNull();
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it("R9: rendered body contains no absolute /Users/ path", async () => {
    (fetch as unknown as ReturnType<typeof vi.fn>).mockResolvedValue(
      jsonResponse(makeDetail())
    );
    const { container } = render(CandidateDetail, {
      briefId: "brief-1",
      candidateId: "42"
    });
    await flushMicrotasks();
    expect(container.textContent ?? "").not.toContain("/Users/");
  });

  it("renders the no-save-reason fallback when save_reason is null", async () => {
    (fetch as unknown as ReturnType<typeof vi.fn>).mockResolvedValue(
      jsonResponse(makeDetail({ save_reason: null }))
    );
    const { container } = render(CandidateDetail, {
      briefId: "brief-1",
      candidateId: "42"
    });
    await flushMicrotasks();
    expect(
      container.querySelector(".candidate-detail-empty-line")?.textContent
    ).toContain("No save reason");
  });
});
