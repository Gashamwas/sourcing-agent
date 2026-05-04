// RunReportPage tests — editorial run report surface.
//
// These tests pin the rules from `docs/cloris-surface-design-rules.md`:
//
// R2  — title falls back to humanized state_key, never raw numeric id
// R3  — Reference Slip footer (collapsed by default, contains diagnostics)
// R4  — decisions histogram + candidate list ordered by recruiter priority
// R5  — candidate list grouped by class, with collapse on noise
// R6  — empty sections (Progress, Attempt Health) are omitted
// R7  — section titles in serif, eyebrow only mono-caps
// R8  — content restraint: Timeline ≤3 fields, no em-dash filler
// R9  — no /Users/... paths leak into the editorial body
// R10 — tl;dr line right under the title
// R12 — capped default visible, "Show all N" expand

import { fireEvent, render, screen } from "@testing-library/svelte";
import { afterEach, beforeEach, describe, it, expect, vi } from "vitest";
import { tick } from "svelte";
import RunReportPage from "../RunReportPage.svelte";
import type {
  CandidateDecisionSummary,
  RunReportResponse
} from "../../lib/types";

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" }
  });
}

function makeCandidate(
  overrides: Partial<CandidateDecisionSummary> = {}
): CandidateDecisionSummary {
  return {
    candidate_id: 1,
    display_name: "Anonymous",
    profile_url: "https://example.com/anon",
    terminal_decision: "SAVE",
    confidence: 0.8,
    ...overrides
  };
}

function makeReport(
  overrides: Partial<RunReportResponse> = {}
): RunReportResponse {
  return {
    slice: "v0-shell-slice-b1",
    source: "linkedin",
    state_key: "research_engineer_colombia",
    // Phase 1B: state_dir + output_dir removed from the wire shape.
    run: {
      id: 42,
      source: "linkedin",
      brief_id: "brief-alpha",
      mode: "fresh",
      status: "completed",
      stop_reason: "normal",
      started_at: "2026-04-29T10:00:00Z",
      ended_at: "2026-04-29T11:30:00Z",
      resumed_from_run_id: null,
      brief_role_title: "Principal Engineer",
      brief_linkedin_project: null,
      brief_drift_since_run: null
    },
    work_unit_progress: {
      kind: "counts",
      queued: 2,
      in_progress: 0,
      done: 12,
      skipped: 1,
      error: 0
    },
    attempt_health: {
      total_attempts_in_window: 0,
      succeeded_in_window: 0,
      failed_in_window: 0,
      last_success_age_s: null,
      recent_failures: [],
      dominant_failure_kind: null
    },
    decisions: {
      total: 0,
      by_decision: {}
    },
    candidates: [],
    candidates_truncated: false,
    ...overrides
  };
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

// Helper for tests that need to wait for the in-flight `getRunReport`
// promise to resolve and for Svelte to flush the render.
async function flush() {
  await tick();
  await new Promise((r) => setTimeout(r, 0));
  await tick();
}

describe("RunReportPage — loading state", () => {
  it("renders the Finding loader while the request is in flight", () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() => new Promise(() => {}))
    );
    const { container } = render(RunReportPage, {
      source: "linkedin",
      stateKey: "test-key",
      runId: "42"
    });
    expect(container.querySelector(".finding-stage")).not.toBeNull();
  });
});

describe("RunReportPage — not-found path", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        jsonResponse({ detail: { error: "run_not_found" } }, 404)
      )
    );
  });

  it("renders the not-found surface for a 404", async () => {
    render(RunReportPage, {
      source: "linkedin",
      stateKey: "test-key",
      runId: "999"
    });
    await flush();
    expect(
      screen.getByText("We couldn't find that run.")
    ).toBeInTheDocument();
  });

  it("renders not-found when the run id is unparseable", async () => {
    render(RunReportPage, {
      source: "linkedin",
      stateKey: "test-key",
      runId: "not-a-number"
    });
    await tick();
    expect(
      screen.getByText("We couldn't find that run.")
    ).toBeInTheDocument();
  });
});

describe("RunReportPage — title fallback (R2)", () => {
  it("uses brief_role_title when present", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        jsonResponse(
          makeReport({
            run: {
              ...makeReport().run,
              brief_role_title: "Principal Engineer"
            }
          })
        )
      )
    );
    render(RunReportPage, {
      source: "linkedin",
      stateKey: "research_engineer_colombia",
      runId: "42"
    });
    await flush();
    expect(screen.getByText("Principal Engineer")).toBeInTheDocument();
  });

  it("falls back to humanized state_key when brief_role_title is null and brief_id is numeric", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        jsonResponse(
          makeReport({
            run: {
              ...makeReport().run,
              brief_role_title: null,
              brief_id: "2015831122"
            }
          })
        )
      )
    );
    render(RunReportPage, {
      source: "linkedin",
      stateKey: "research_engineer_colombia",
      runId: "42"
    });
    await flush();
    expect(
      screen.getByText("Research Engineer Colombia")
    ).toBeInTheDocument();
    // Numeric brief_id must NOT appear in the editorial title.
    expect(screen.queryByText("2015831122")).toBeNull();
  });

  it("falls back to source-typed generic + disambiguator subtitle for numeric state_keys", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        jsonResponse(
          makeReport({
            state_key: "1957683706",
            run: {
              ...makeReport().run,
              brief_role_title: null,
              brief_id: "2015831122"
            }
          })
        )
      )
    );
    render(RunReportPage, {
      source: "linkedin",
      stateKey: "1957683706",
      runId: "42"
    });
    await flush();
    // Phase 2A: pure-numeric state_keys collapse to "LinkedIn search"
    // (operational, never used as a card title elsewhere) plus a
    // mono-caps subtitle carrying the state_key for disambiguation.
    expect(screen.getByText("LinkedIn search")).toBeInTheDocument();
    expect(screen.getByText("#1957683706")).toBeInTheDocument();
  });
});

describe("RunReportPage — tl;dr (R10)", () => {
  it("renders the limit-reached headline with save/reject counts", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        jsonResponse(
          makeReport({
            run: {
              ...makeReport().run,
              status: "governor_limit_reached",
              stop_reason: "governor_limit_reached"
            },
            decisions: {
              total: 227,
              by_decision: { FACIAL_NO: 159, REJECT: 66, INFERENTIAL_SAVE: 1, TRANSFERABLE_SAVE: 1 }
            }
          })
        )
      )
    );
    const { container } = render(RunReportPage, {
      source: "linkedin",
      stateKey: "research_engineer_colombia",
      runId: "42"
    });
    await flush();
    const tldr = container.querySelector(".run-report-tldr");
    expect(tldr).not.toBeNull();
    const text = tldr?.textContent ?? "";
    expect(text).toContain("Limit reached.");
    // 2 saves come from INFERENTIAL_SAVE + TRANSFERABLE_SAVE.
    expect(text).toContain("2 saves");
    expect(text).toContain("66 rejects");
  });

  it("renders the no-saves completed headline distinctly", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        jsonResponse(
          makeReport({
            run: { ...makeReport().run, status: "completed" },
            decisions: {
              total: 50,
              by_decision: { REJECT: 50 }
            }
          })
        )
      )
    );
    const { container } = render(RunReportPage, {
      source: "linkedin",
      stateKey: "x",
      runId: "42"
    });
    await flush();
    const tldr = container.querySelector(".run-report-tldr");
    expect(tldr?.textContent ?? "").toContain("Nothing met the bar");
  });

  it("renders the running headline with done/total", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        jsonResponse(
          makeReport({
            run: { ...makeReport().run, status: "running" },
            work_unit_progress: {
              kind: "counts",
              queued: 5,
              in_progress: 1,
              done: 12,
              skipped: 0,
              error: 0
            },
            decisions: { total: 12, by_decision: { SAVE: 3, REJECT: 9 } }
          })
        )
      )
    );
    const { container } = render(RunReportPage, {
      source: "linkedin",
      stateKey: "x",
      runId: "42"
    });
    await flush();
    const tldr = container.querySelector(".run-report-tldr");
    expect(tldr?.textContent ?? "").toContain("She's still going");
    expect(tldr?.textContent ?? "").toContain("3 saves so far");
  });
});

describe("RunReportPage — Timeline restraint (R1, R8)", () => {
  it("renders only Started, Ended, and Stop reason in the editorial body", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        jsonResponse(
          makeReport({
            run: {
              ...makeReport().run,
              stop_reason: "governor_limit_reached"
            }
          })
        )
      )
    );
    const { container } = render(RunReportPage, {
      source: "linkedin",
      stateKey: "research_engineer_colombia",
      runId: "42"
    });
    await flush();
    const timeline = screen.getByText("Timeline").closest("section");
    expect(timeline).not.toBeNull();
    const dts = timeline?.querySelectorAll("dt");
    const labels = Array.from(dts ?? []).map((dt) => dt.textContent?.trim());
    expect(labels).toEqual(["Started", "Ended", "Stop reason"]);
    // Mode / Run id / Output dir / Brief id are NOT in the timeline.
    expect(timeline?.textContent ?? "").not.toContain("Mode");
    expect(timeline?.textContent ?? "").not.toContain("Output");
    expect(timeline?.textContent ?? "").not.toContain("Run id");
  });

  it("omits Stop reason when it is 'normal'", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        jsonResponse(
          makeReport({
            run: { ...makeReport().run, stop_reason: "normal" }
          })
        )
      )
    );
    render(RunReportPage, {
      source: "linkedin",
      stateKey: "x",
      runId: "42"
    });
    await flush();
    const timeline = screen.getByText("Timeline").closest("section");
    const dts = Array.from(timeline?.querySelectorAll("dt") ?? []).map(
      (dt) => dt.textContent?.trim()
    );
    expect(dts).not.toContain("Stop reason");
  });
});

describe("RunReportPage — Progress + Attempt Health visibility (R6)", () => {
  it("omits Progress when work_unit_progress.kind === 'empty'", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        jsonResponse(
          makeReport({
            work_unit_progress: {
              kind: "empty",
              queued: 0,
              in_progress: 0,
              done: 0,
              skipped: 0,
              error: 0
            }
          })
        )
      )
    );
    render(RunReportPage, {
      source: "linkedin",
      stateKey: "x",
      runId: "42"
    });
    await flush();
    expect(screen.queryByText("Progress")).toBeNull();
  });

  it("omits Attempt Health when window is empty and no last success", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => jsonResponse(makeReport()))
    );
    render(RunReportPage, {
      source: "linkedin",
      stateKey: "x",
      runId: "42"
    });
    await flush();
    // The default fixture has total_attempts_in_window=0 and last_success_age_s=null.
    expect(screen.queryByText("Attempt health")).toBeNull();
  });

  it("renders Attempt Health as a single sentence when there is signal", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        jsonResponse(
          makeReport({
            attempt_health: {
              total_attempts_in_window: 12,
              succeeded_in_window: 3,
              failed_in_window: 9,
              last_success_age_s: 720,
              recent_failures: [{ kind: "http_429", count: 9 }],
              dominant_failure_kind: "http_429"
            }
          })
        )
      )
    );
    const { container } = render(RunReportPage, {
      source: "linkedin",
      stateKey: "x",
      runId: "42"
    });
    await flush();
    const section = screen.getByText("Attempt health").closest("section");
    const text = section?.textContent ?? "";
    expect(text).toContain("Last success 12 minutes ago");
    expect(text).toContain("9 of 12 recent attempts");
    expect(text).toContain("rate limited");
    // No 5-cell field grid — the section renders prose, not labels.
    expect(section?.querySelector(".run-report-fields")).toBeNull();
  });
});

describe("RunReportPage — Candidate grouping (R4, R5, R12)", () => {
  function reportWithCandidates() {
    return makeReport({
      decisions: {
        total: 17,
        by_decision: {
          SAVE: 1,
          INFERENTIAL_SAVE: 1,
          FACIAL_BORDERLINE: 1,
          REJECT: 12,
          FACIAL_NO: 2
        }
      },
      candidates: [
        makeCandidate({
          candidate_id: 1,
          display_name: "Alice Save",
          terminal_decision: "SAVE"
        }),
        makeCandidate({
          candidate_id: 2,
          display_name: "Aaron Inferential",
          terminal_decision: "INFERENTIAL_SAVE"
        }),
        makeCandidate({
          candidate_id: 3,
          display_name: "Beth Borderline",
          terminal_decision: "FACIAL_BORDERLINE"
        }),
        ...Array.from({ length: 12 }, (_, i) =>
          makeCandidate({
            candidate_id: 100 + i,
            display_name: `Reject ${i}`,
            terminal_decision: "REJECT"
          })
        ),
        makeCandidate({
          candidate_id: 200,
          display_name: "Filtered Person",
          terminal_decision: "FACIAL_NO"
        }),
        makeCandidate({
          candidate_id: 201,
          display_name: "Other Filtered",
          terminal_decision: "FACIAL_NO"
        })
      ]
    });
  }

  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => jsonResponse(reportWithCandidates()))
    );
  });

  it("renders Saves and Borderline groups visible by default", async () => {
    render(RunReportPage, {
      source: "linkedin",
      stateKey: "x",
      runId: "42"
    });
    await flush();
    expect(screen.getByText("Alice Save")).toBeInTheDocument();
    expect(screen.getByText("Aaron Inferential")).toBeInTheDocument();
    expect(screen.getByText("Beth Borderline")).toBeInTheDocument();
  });

  it("collapses Rejects and Filtered groups by default", async () => {
    render(RunReportPage, {
      source: "linkedin",
      stateKey: "x",
      runId: "42"
    });
    await flush();
    // Reject and filtered candidate names are NOT visible until expanded.
    expect(screen.queryByText("Reject 0")).toBeNull();
    expect(screen.queryByText("Filtered Person")).toBeNull();
    // The group toggle header is visible with the count.
    const rejectsToggle = screen
      .getByText("Rejects")
      .closest("button");
    expect(rejectsToggle).not.toBeNull();
    expect(rejectsToggle?.textContent).toContain("12");
  });

  it("expanding Rejects shows the first 10 with a 'Show all 12' button", async () => {
    render(RunReportPage, {
      source: "linkedin",
      stateKey: "x",
      runId: "42"
    });
    await flush();

    const rejectsToggle = screen.getByText("Rejects").closest("button");
    await fireEvent.click(rejectsToggle as HTMLButtonElement);

    // First 10 rejects visible.
    expect(screen.getByText("Reject 0")).toBeInTheDocument();
    expect(screen.getByText("Reject 9")).toBeInTheDocument();
    // 11th and 12th not yet visible.
    expect(screen.queryByText("Reject 10")).toBeNull();

    // "Show all 12 rejects" expands.
    const showAll = screen.getByText("Show all 12 rejects");
    await fireEvent.click(showAll);
    expect(screen.getByText("Reject 10")).toBeInTheDocument();
    expect(screen.getByText("Reject 11")).toBeInTheDocument();
  });

  it("does not render the obsolete 'Where to start' headline (R23 redundancy collapse)", async () => {
    const { container } = render(RunReportPage, {
      source: "linkedin",
      stateKey: "x",
      runId: "42"
    });
    await flush();
    // The .run-report-where-to-start element was removed because it
    // restated counts already shown by the tl;dr above and by the
    // group headers below. Group headers (Saves N, Borderline N) are
    // the canonical save-count location now.
    expect(container.querySelector(".run-report-where-to-start")).toBeNull();
  });
});

describe("RunReportPage — Reference Slip footer (R3, R9)", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        jsonResponse(
          makeReport({
            run: {
              ...makeReport().run,
              brief_id: "2015831122"
              // Phase 1B: output_dir is no longer on the wire (R9).
            }
          })
        )
      )
    );
  });

  it("does not render the raw filesystem path in the editorial body", async () => {
    const { container } = render(RunReportPage, {
      source: "linkedin",
      stateKey: "x",
      runId: "42"
    });
    await flush();
    // The /Users/... path may live in the (collapsed) Reference Slip,
    // but it must NOT appear in the editorial sections (Timeline,
    // Decisions, Candidates, etc.).
    const timeline = screen.getByText("Timeline").closest("section");
    expect(timeline?.textContent ?? "").not.toContain("/Users/test/");
    const heading = container.querySelector(".run-report-heading");
    expect(heading?.textContent ?? "").not.toContain("/Users/test/");
  });

  it("renders the Reference Slip toggle (collapsed by default)", async () => {
    const { container } = render(RunReportPage, {
      source: "linkedin",
      stateKey: "x",
      runId: "42"
    });
    await flush();
    const toggle = container.querySelector(
      ".run-report-reference-slip-toggle"
    );
    expect(toggle).not.toBeNull();
    expect(toggle?.getAttribute("aria-expanded")).toBe("false");
    // Diagnostic fields are NOT visible until the slip is opened.
    expect(screen.queryByText("Run id")).toBeNull();
  });

  it("opens the Reference Slip on click and reveals diagnostic fields", async () => {
    const { container } = render(RunReportPage, {
      source: "linkedin",
      stateKey: "x",
      runId: "42"
    });
    await flush();
    const toggle = container.querySelector(
      ".run-report-reference-slip-toggle"
    ) as HTMLButtonElement;
    await fireEvent.click(toggle);

    expect(screen.getByText("Run id")).toBeInTheDocument();
    expect(screen.getByText("Brief")).toBeInTheDocument();
    expect(screen.getByText("State directory")).toBeInTheDocument();
    // Phase 1B: the raw numeric brief id is still surfaced inside the
    // slip — that's the correct home for diagnostic data. The state
    // directory now renders as the relative `<source>/<state_key>`
    // form (R9 — no absolute /Users/ paths anywhere on the wire).
    expect(screen.getByText("2015831122")).toBeInTheDocument();
    // makeReport()'s state_key is "research_engineer_colombia" (the route
    // prop differs in this test, but the slip surfaces what the response
    // contains — that's the canonical handle a developer needs).
    const slip = container.querySelector(".run-report-reference-slip-fields");
    expect(slip?.textContent ?? "").toContain(
      "linkedin/research_engineer_colombia"
    );
  });
});

describe("RunReportPage — Resumed-from + brief drift", () => {
  it("renders the brief-drift note when run.brief_drift_since_run is true", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        jsonResponse(
          makeReport({
            run: { ...makeReport().run, brief_drift_since_run: true }
          })
        )
      )
    );
    render(RunReportPage, {
      source: "linkedin",
      stateKey: "x",
      runId: "42"
    });
    await flush();
    expect(
      screen.getByText("Brief edited since this run started.")
    ).toBeInTheDocument();
  });

  it("renders a Resumed-from link to the prior run id", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        jsonResponse(
          makeReport({
            run: {
              ...makeReport().run,
              resumed_from_run_id: 41
            }
          })
        )
      )
    );
    const { container } = render(RunReportPage, {
      source: "linkedin",
      stateKey: "research_engineer_colombia",
      runId: "42"
    });
    await flush();
    const link = Array.from(
      container.querySelectorAll("a.run-report-link")
    ).find((a) => a.textContent?.includes("Run #41"));
    expect(link).toBeDefined();
    expect(link?.getAttribute("href")).toBe(
      "#/run/linkedin/research_engineer_colombia/41"
    );
  });
});
