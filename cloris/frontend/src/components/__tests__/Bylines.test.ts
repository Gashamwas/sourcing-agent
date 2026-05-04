// Bylines.test.ts — editorial byline pin tests.
//
// Plan Finding 3 dropped the "Cloris's X — " prefix from every editorial-
// surface byline; the date stayed because it was load-bearing, the prefix
// did not. The candidateDetailByline was dropped entirely (the recruiter
// is here because they clicked the candidate; signing the page "by Cloris"
// frames her as the author of *this candidate*, which is the wrong mental
// model). The card-state byline (StateDirRow) is intentionally untouched —
// it surfaces only on stalled / limit-reached / lost-track / interrupted
// cards and tells the recruiter what to do.
//
// Pins on each surface today:
// 1. RunReportPage — "<date>." for finished runs; no byline while running.
// 2. Workspace — "Last touched <date>." when there are saves; no byline
//    when there are none (the empty-state body says it).
// 3. CandidateDetail — no editorial byline at all.
// 4. StateDirRow (card stack) — "Cloris paused — your call." etc. KEPT.

import { render } from "@testing-library/svelte";
import { afterEach, describe, it, expect } from "vitest";
import { tick } from "svelte";
import RunReportPage from "../RunReportPage.svelte";
import Workspace from "../Workspace.svelte";
import CandidateDetail from "../CandidateDetail.svelte";
import StateDirRow from "../StateDirRow.svelte";
import { makeStateDirEntry } from "../../test/fixtures";
import type { RunReportResponse, WorkspaceResponse, CandidateDetailResponse } from "../../lib/types";

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

async function flush() {
  await tick();
  await new Promise((r) => setTimeout(r, 0));
  await tick();
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

// ============ 1. RunReportPage byline ============

describe("R26 byline — RunReportPage", () => {
  function makeReport(overrides: Partial<RunReportResponse> = {}): RunReportResponse {
    return {
      slice: "v0-shell-slice-b1",
      source: "linkedin",
      state_key: "research_engineer_colombia",
      run: {
        id: 42,
        source: "linkedin",
        brief_id: "brief-alpha",
        mode: "fresh",
        status: "completed",
        stop_reason: "normal",
        started_at: "2026-04-29T10:00:00Z",
        ended_at: "2026-04-29T23:30:00Z",
        resumed_from_run_id: null,
        brief_role_title: "Principal Engineer",
        brief_linkedin_project: null,
        brief_drift_since_run: null,
      },
      work_unit_progress: { kind: "counts", queued: 0, in_progress: 0, done: 5, skipped: 0, error: 0 },
      attempt_health: {
        total_attempts_in_window: 0,
        succeeded_in_window: 0,
        failed_in_window: 0,
        last_success_age_s: null,
        recent_failures: [],
        dominant_failure_kind: null,
      },
      decisions: { total: 0, by_decision: {} },
      candidates: [],
      candidates_truncated: false,
      ...overrides,
    };
  }

  it("renders a date-only byline on a finished run (no 'Cloris's report' prefix)", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => jsonResponse(makeReport())));
    const { container } = render(RunReportPage, {
      source: "linkedin",
      stateKey: "research_engineer_colombia",
      runId: "42",
    });
    await flush();
    const byline = container.querySelector(".cloris-byline");
    expect(byline).not.toBeNull();
    // Plan Finding 3: "Cloris's report" prefix dropped; only the date remains.
    expect(byline?.textContent).not.toContain("Cloris\u2019s report");
    // The formatted date matches "MMM d, h:mm a." — pin a coarse shape.
    expect(byline?.textContent).toMatch(/[A-Z][a-z]{2} \d+, \d+:\d{2}\s*[AP]M\./);
  });

  it("omits the byline entirely while the run is in motion", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        jsonResponse(
          makeReport({
            run: { ...makeReport().run, status: "running", ended_at: null },
          })
        )
      )
    );
    const { container } = render(RunReportPage, {
      source: "linkedin",
      stateKey: "x",
      runId: "42",
    });
    await flush();
    // The running status pill at top-right already says "Working"; a
    // separate "still in motion" byline was restatement.
    const byline = container.querySelector(".cloris-byline");
    expect(byline).toBeNull();
  });
});

// ============ 2. Workspace byline ============

describe("R26 byline — Workspace", () => {
  function makeWorkspace(overrides: Partial<WorkspaceResponse> = {}): WorkspaceResponse {
    return {
      slice: "v0-shell-slice-c5",
      brief_id: "brief-1",
      sources: ["linkedin"],
      brief_role_title: "Senior FDE",
      brief_linkedin_project: "FDE NYC",
      latest_run: { source: "linkedin", state_key: "x", run_id: 12 },
      total_saves: 2,
      saves_this_week: 2,
      shortlisted_count: 0,
      last_save_at: "2026-04-29T11:30:00Z",
      candidates: [],
      ...overrides,
    };
  }

  it("renders a 'Last touched <date>' byline when there are saves", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => jsonResponse(makeWorkspace())));
    const { container } = render(Workspace, { briefId: "brief-1" });
    await flush();
    const byline = container.querySelector(".cloris-byline");
    expect(byline).not.toBeNull();
    // Plan Finding 3: "Cloris's saves" prefix dropped; "Last touched"
    // carries the date.
    expect(byline?.textContent).not.toContain("Cloris\u2019s saves");
    expect(byline?.textContent).toContain("Last touched");
  });

  it("omits the byline entirely when total_saves is 0", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        jsonResponse(makeWorkspace({ total_saves: 0, last_save_at: null }))
      )
    );
    const { container } = render(Workspace, { briefId: "brief-1" });
    await flush();
    // The workspace empty-state body ("No saves yet.") is the message;
    // restating it as a Cloris-voice byline above was redundancy.
    const byline = container.querySelector(".cloris-byline");
    expect(byline).toBeNull();
  });
});

// ============ 3. CandidateDetail byline ============

describe("R26 byline — CandidateDetail", () => {
  function makeDetail(overrides: Partial<CandidateDetailResponse> = {}): CandidateDetailResponse {
    return {
      slice: "v0-shell-slice-c5",
      source: "linkedin",
      brief_id: "brief-1",
      candidate_id: 42,
      identity_key: "li-pat",
      display_name: "Pat Doe",
      profile_url: "https://example.com/pat",
      terminal_decision: "SAVE",
      confidence: 0.91,
      save_reason: "Strong fit",
      current_lifecycle_state: "full_terminal",
      first_seen_at: "2026-04-29T10:00:00Z",
      last_seen_at: "2026-04-29T11:30:00Z",
      source_run: { source: "linkedin", state_key: "x", run_id: 12 },
      brief_role_title: "Senior FDE",
      brief_linkedin_project: "FDE NYC",
      notes: [],
      user_status: null,
      is_failed_state: false,
      judgment_accuracy: null,
      judgment_accuracy_at: null,
      ...overrides,
    };
  }

  it("never renders an editorial byline (with or without first_seen_at)", async () => {
    // Plan Finding 3: candidateDetailByline was dropped entirely.
    // Signing the candidate page "Cloris flagged this Apr 28" framed
    // her as the author of *this candidate*, which is the wrong mental
    // model for a candidate detail page (the page is the recruiter's
    // workshop). The first-seen date already lives in the Reference Slip.
    vi.stubGlobal("fetch", vi.fn(async () => jsonResponse(makeDetail())));
    const { container: withDate } = render(CandidateDetail, {
      briefId: "brief-1",
      candidateId: "42",
    });
    await flush();
    expect(withDate.querySelector(".cloris-byline")).toBeNull();

    vi.stubGlobal(
      "fetch",
      vi.fn(async () => jsonResponse(makeDetail({ first_seen_at: null })))
    );
    const { container: noDate } = render(CandidateDetail, {
      briefId: "brief-1",
      candidateId: "43",
    });
    await flush();
    expect(noDate.querySelector(".cloris-byline")).toBeNull();
  });
});

// ============ 4. StateDirRow card byline ============

describe("R26 byline — StateDirRow (card stack)", () => {
  it("renders 'Cloris paused' byline on a limit-reached card", () => {
    const entry = makeStateDirEntry({
      runtime_state_present: true,
      worker_state: "missing",
      latest_run: {
        id: 1,
        status: "governor_limit_reached",
        stop_reason: "governor_limit_reached",
        mode: "fresh",
        started_at: null,
        ended_at: null,
      },
    });
    const { container } = render(StateDirRow, { entry });
    const byline = container.querySelector(".cloris-byline--card");
    expect(byline).not.toBeNull();
    expect(byline?.textContent).toContain("Cloris paused");
    expect(byline?.textContent).toContain("your call");
  });

  it("renders 'Cloris lost track' on a stale-worker card", () => {
    const entry = makeStateDirEntry({
      runtime_state_present: true,
      worker_state: "stale",
      worker_pid: 4242,
    });
    const { container } = render(StateDirRow, { entry });
    const byline = container.querySelector(".cloris-byline--card");
    expect(byline).not.toBeNull();
    expect(byline?.textContent).toContain("Cloris lost track");
  });

  it("renders 'Cloris is stuck' on a stalled card", () => {
    const entry = makeStateDirEntry({
      runtime_state_present: true,
      worker_state: "alive",
      worker_alive: true,
      worker_pid: 1,
      run_stalled: true,
      stall_failure_kind: "http_429",
    });
    const { container } = render(StateDirRow, { entry });
    const byline = container.querySelector(".cloris-byline--card");
    expect(byline).not.toBeNull();
    expect(byline?.textContent).toContain("Cloris is stuck");
  });

  it("does NOT render a byline on a working card", () => {
    const entry = makeStateDirEntry({
      runtime_state_present: true,
      worker_state: "alive",
      worker_alive: true,
      worker_pid: 1,
      latest_run: {
        id: 1,
        status: "running",
        stop_reason: null,
        mode: "fresh",
        started_at: null,
        ended_at: null,
      },
    });
    const { container } = render(StateDirRow, { entry });
    const byline = container.querySelector(".cloris-byline--card");
    expect(byline).toBeNull();
  });
});
