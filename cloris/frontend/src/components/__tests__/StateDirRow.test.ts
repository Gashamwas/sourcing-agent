// StateDirRow tests for the card-file design.
//
// What we guard:
//   - Source label flows through sources.sourceMeta() so the recruiter
//     sees "LinkedIn" / "GitHub" rather than the wire literal.
//   - Empty / missing runtime cases collapse to a single "No record"
//     pill; the card-file design no longer distinguishes them visually
//     (the Reference Slip surfaces raw state for developers).
//   - Pull label flows through state.clorisPullLabel — "ready to pull" /
//     "nothing pending" / "—".
//   - Worker label flows through state.clorisWorkerLabel — "Working" /
//     "Lost track" / "Away" / "Stopping…".
//   - Stop lives inside the expanded card-detail section. Reachability and
//     telemetry tests must select the card first.
//   - Stop telemetry: stop_attempted → stop_succeeded on 202; stop_attempted
//     → stop_failed on 500. Events never expose error.message or path strings.
//   - The card-action error <p> announces via aria-live="polite" on stop
//     failures.

import { fireEvent, render, screen } from "@testing-library/svelte";
import { afterEach, beforeEach, describe, it, expect, vi } from "vitest";
import StateDirRow from "../StateDirRow.svelte";
import { makeStateDirEntry } from "../../test/fixtures";
import { _testClearEvents, _testReadEvents } from "../../lib/telemetry";
import { selectedCardStore } from "../../lib/stores";

// Force the card open before assertions on the expanded action area. The
// card is selected via the "{source}/{state_key}" key (see StateDirRow.key).
function selectCard(source: string, stateKey: string) {
  selectedCardStore.set(`${source}/${stateKey}`);
}

beforeEach(() => {
  selectedCardStore.set(null);
});

describe("StateDirRow — Phase A operational signals", () => {
  it("renders 'Stalled' pill + data-state-kind='stalled' when run_stalled is true on a live worker", () => {
    const entry = makeStateDirEntry({
      runtime_state_present: true,
      worker_state: "alive",
      worker_alive: true,
      worker_pid: 1,
      run_stalled: true,
      stall_failure_kind: "http_429"
    });
    const { container } = render(StateDirRow, { entry });
    const card = container.querySelector(".card");
    expect(card?.getAttribute("data-state-kind")).toBe("stalled");
    expect(screen.getByText("Stalled")).toBeInTheDocument();
  });

  it("does NOT promote to stalled when worker is missing (stalled requires alive/running)", () => {
    const entry = makeStateDirEntry({
      runtime_state_present: true,
      worker_state: "missing",
      run_stalled: true,
      stall_failure_kind: "rate_limit"
    });
    const { container } = render(StateDirRow, { entry });
    const card = container.querySelector(".card");
    expect(card?.getAttribute("data-state-kind")).not.toBe("stalled");
  });

  it("renders the humanized stall reason in the card detail when selected", () => {
    const entry = makeStateDirEntry({
      source: "linkedin",
      state_key: "alpha",
      runtime_state_present: true,
      worker_state: "alive",
      worker_alive: true,
      worker_pid: 1,
      run_stalled: true,
      stall_failure_kind: "http_429"
    });
    selectedCardStore.set("linkedin/alpha");
    render(StateDirRow, { entry });
    expect(screen.getByText("rate limited")).toBeInTheDocument();
  });

  it("renders a progress line when work_unit_progress has counts and the card is selected", () => {
    const entry = makeStateDirEntry({
      source: "linkedin",
      state_key: "alpha",
      runtime_state_present: true,
      worker_state: "alive",
      worker_alive: true,
      worker_pid: 1,
      work_unit_progress: {
        kind: "counts",
        queued: 4,
        in_progress: 1,
        done: 6,
        skipped: 0,
        error: 0
      }
    });
    selectedCardStore.set("linkedin/alpha");
    const { container } = render(StateDirRow, { entry });
    const line = container.querySelector(".card-progress-line");
    expect(line?.textContent).toContain("Progress");
    expect(line?.textContent).toContain("6");
    expect(line?.textContent).toContain("11");
    // 6 done out of 11 total = 55%.
    expect(line?.textContent).toContain("55%");
  });

  it("does NOT render progress when work_unit_progress.kind is 'empty'", () => {
    const entry = makeStateDirEntry({
      source: "linkedin",
      state_key: "alpha",
      runtime_state_present: true,
      work_unit_progress: {
        kind: "empty",
        queued: 0,
        in_progress: 0,
        done: 0,
        skipped: 0,
        error: 0
      }
    });
    selectedCardStore.set("linkedin/alpha");
    const { container } = render(StateDirRow, { entry });
    expect(container.querySelector(".card-progress")).toBeNull();
  });

  it("renders a brief-drift glyph in the meta-line when brief_drift_since_last_run is true", () => {
    const entry = makeStateDirEntry({
      brief_drift_since_last_run: true
    });
    const { container } = render(StateDirRow, { entry });
    const drift = container.querySelector(".card-meta-drift");
    expect(drift).not.toBeNull();
    expect(drift?.getAttribute("title")).toBe("Brief modified since last run");
  });

  it("does NOT render the brief-drift glyph when brief_drift is false or null", () => {
    const noDrift = makeStateDirEntry({ brief_drift_since_last_run: false });
    const { container, unmount } = render(StateDirRow, { entry: noDrift });
    expect(container.querySelector(".card-meta-drift")).toBeNull();
    unmount();

    const unknownDrift = makeStateDirEntry({
      brief_drift_since_last_run: null
    });
    const next = render(StateDirRow, { entry: unknownDrift });
    expect(next.container.querySelector(".card-meta-drift")).toBeNull();
  });

  it("renders a 'Read the report' link in Card Detail with the right href when latest_run.id is set", () => {
    const entry = makeStateDirEntry({
      source: "linkedin",
      state_key: "alpha",
      runtime_state_present: true,
      latest_run: {
        id: 42,
        status: "completed",
        stop_reason: "normal",
        mode: "fresh",
        started_at: null,
        ended_at: null
      }
    });
    selectedCardStore.set("linkedin/alpha");
    const { container } = render(StateDirRow, { entry });
    const link = container.querySelector(
      "a.card-read-report-link"
    ) as HTMLAnchorElement | null;
    expect(link).not.toBeNull();
    expect(link?.getAttribute("href")).toBe("#/run/linkedin/alpha/42");
    expect(link?.textContent?.trim()).toBe("Read the report");
  });

  it("uses the in-flight 'so far' label when worker is alive", () => {
    const entry = makeStateDirEntry({
      source: "linkedin",
      state_key: "alpha",
      runtime_state_present: true,
      worker_state: "alive",
      worker_alive: true,
      worker_pid: 1,
      latest_run: {
        id: 99,
        status: "running",
        stop_reason: null,
        mode: "fresh",
        started_at: null,
        ended_at: null
      }
    });
    selectedCardStore.set("linkedin/alpha");
    const { container } = render(StateDirRow, { entry });
    const link = container.querySelector(
      "a.card-read-report-link"
    ) as HTMLAnchorElement | null;
    expect(link?.textContent?.trim()).toBe("Read the report so far");
  });

  it("hides the 'Read the report' link when latest_run.id is null", () => {
    const entry = makeStateDirEntry({
      source: "linkedin",
      state_key: "alpha",
      runtime_state_present: true,
      latest_run: null
    });
    selectedCardStore.set("linkedin/alpha");
    const { container } = render(StateDirRow, { entry });
    expect(container.querySelector("a.card-read-report-link")).toBeNull();
  });

  it("renders attempt-health rows in the Reference Slip when attempt_health is present", async () => {
    const entry = makeStateDirEntry({
      source: "linkedin",
      state_key: "alpha",
      runtime_state_present: true,
      attempt_health: {
        total_attempts_in_window: 12,
        succeeded_in_window: 3,
        failed_in_window: 9,
        last_success_age_s: 180,
        recent_failures: [{ kind: "http_429", count: 9 }],
        dominant_failure_kind: "http_429"
      }
    });
    selectedCardStore.set("linkedin/alpha");
    const { container } = render(StateDirRow, { entry });
    // Open the Reference Slip.
    const toggle = container.querySelector(
      ".reference-slip-toggle"
    ) as HTMLButtonElement;
    await fireEvent.click(toggle);

    expect(screen.getByText("Last Success")).toBeInTheDocument();
    expect(screen.getByText("3 minutes ago")).toBeInTheDocument();
    expect(screen.getByText("Recent Failures")).toBeInTheDocument();
    expect(screen.getByText("rate limited in 9 of 12")).toBeInTheDocument();
  });
});

describe("StateDirRow — empty / missing runtime", () => {
  it("renders 'No card record' pill when DB is present but no runs exist", () => {
    const entry = makeStateDirEntry({
      runtime_state_present: true,
      latest_run: null
    });
    render(StateDirRow, { entry });
    expect(screen.getByText("No record")).toBeInTheDocument();
  });

  it("renders 'No card record' pill when the runtime DB is missing", () => {
    const entry = makeStateDirEntry({
      runtime_state_present: false,
      latest_run: null
    });
    render(StateDirRow, { entry });
    expect(screen.getByText("No record")).toBeInTheDocument();
  });

  it("tags the card root with data-state-kind='no-record' for empty runtime", () => {
    const entry = makeStateDirEntry({
      runtime_state_present: true,
      latest_run: null
    });
    const { container } = render(StateDirRow, { entry });
    const card = container.querySelector(".card");
    expect(card?.getAttribute("data-state-kind")).toBe("no-record");
  });
});

describe("StateDirRow — source label via sources registry", () => {
  it("renders 'LinkedIn' for source=linkedin", () => {
    const entry = makeStateDirEntry({ source: "linkedin" });
    render(StateDirRow, { entry });
    expect(screen.getByText("LinkedIn")).toBeInTheDocument();
  });

  it("renders 'GitHub' for source=github", () => {
    const entry = makeStateDirEntry({ source: "github" });
    render(StateDirRow, { entry });
    expect(screen.getByText("GitHub")).toBeInTheDocument();
  });
});

describe("StateDirRow — Pull label via state.clorisPullLabel", () => {
  // Two-Register Card: Pull/Cloris fields live in the expanded detail,
  // not the collapsed face. Each test selects the card before asserting.
  it("renders 'ready to pull' when resumable=true", () => {
    const entry = makeStateDirEntry({
      runtime_state_present: true,
      resumable: true
    });
    selectCard(entry.source, entry.state_key);
    render(StateDirRow, { entry });
    expect(screen.getByText("ready to pull")).toBeInTheDocument();
  });

  it("renders 'nothing pending' when resumable=false", () => {
    const entry = makeStateDirEntry({
      runtime_state_present: true,
      resumable: false
    });
    selectCard(entry.source, entry.state_key);
    render(StateDirRow, { entry });
    expect(screen.getByText("nothing pending")).toBeInTheDocument();
  });

  it("renders '—' for the Pull field when resumable is null (unknown)", () => {
    const entry = makeStateDirEntry({
      runtime_state_present: true,
      resumable: null
    });
    selectCard(entry.source, entry.state_key);
    const { container } = render(StateDirRow, { entry });
    const pullField = Array.from(container.querySelectorAll(".card-field")).find(
      (el) => el.querySelector(".card-field-label")?.textContent === "Pull"
    );
    expect(pullField?.querySelector(".card-field-value")?.textContent).toBe("—");
  });
});

describe("StateDirRow — Cloris worker label via state.clorisWorkerLabel", () => {
  it("renders 'Working' for an alive worker", () => {
    const entry = makeStateDirEntry({
      runtime_state_present: true,
      worker_state: "alive",
      worker_pid: 12345,
      heartbeat_age_s: 3
    });
    render(StateDirRow, { entry });
    // Status pill and Cloris field both read "Working".
    expect(screen.getAllByText("Working").length).toBeGreaterThanOrEqual(1);
  });

  it("renders 'Lost track' when the worker is stale", () => {
    const entry = makeStateDirEntry({
      runtime_state_present: true,
      worker_state: "stale",
      worker_pid: 4242
    });
    render(StateDirRow, { entry });
    // Sentence-case canonical label (R24) — pill and Cloris field both
    // render "Lost track" since the state-kind and the worker label
    // map to the same canonical wording for stale workers.
    expect(screen.getAllByText("Lost track").length).toBeGreaterThanOrEqual(1);
  });

  it("renders 'Away' when the worker is missing", () => {
    const entry = makeStateDirEntry({
      runtime_state_present: true,
      worker_state: "missing",
      worker_pid: null
    });
    selectCard(entry.source, entry.state_key);
    render(StateDirRow, { entry });
    expect(screen.getAllByText("Away").length).toBeGreaterThanOrEqual(1);
  });
});

describe("StateDirRow — stop error announces via aria-live", () => {
  const originalFetch = globalThis.fetch;

  afterEach(() => {
    globalThis.fetch = originalFetch;
    vi.restoreAllMocks();
  });

  it("renders a card-action error <p> with aria-live='polite' on failure", async () => {
    globalThis.fetch = vi.fn(async (input: RequestInfo | URL) => {
      const url = typeof input === "string" ? input : input.toString();
      if (url.includes("/api/stop/")) {
        return new Response(JSON.stringify({ detail: "boom" }), {
          status: 500,
          headers: { "content-type": "application/json" }
        });
      }
      return new Response(
        JSON.stringify({ slice: "v0-shell-slice-4", entries: [] }),
        { status: 200, headers: { "content-type": "application/json" } }
      );
    }) as typeof fetch;

    const entry = makeStateDirEntry({
      source: "linkedin",
      state_key: "test-brief",
      runtime_state_present: true,
      worker_json_present: true,
      worker_pid: 12345,
      worker_alive: true,
      worker_state: "alive",
      heartbeat_age_s: 3
    });
    selectCard("linkedin", "test-brief");
    const { container } = render(StateDirRow, { entry });

    await fireEvent.click(screen.getByRole("button", { name: "Stop" }));
    await new Promise((r) => setTimeout(r, 0));

    const errorParagraph = container.querySelector("p.card-action-error");
    expect(errorParagraph).not.toBeNull();
    expect(errorParagraph?.getAttribute("aria-live")).toBe("polite");
    expect(errorParagraph?.textContent ?? "").toContain("Stop failed");
  });
});

describe("StateDirRow — stop button reachability", () => {
  it("renders a Stop button when source=linkedin, worker is alive, and the card is selected", () => {
    const entry = makeStateDirEntry({
      source: "linkedin",
      state_key: "test-brief",
      runtime_state_present: true,
      worker_json_present: true,
      worker_pid: 12345,
      worker_alive: true,
      worker_state: "alive",
      heartbeat_age_s: 3
    });
    selectCard("linkedin", "test-brief");
    render(StateDirRow, { entry });

    const button = screen.getByRole("button", { name: "Stop" });
    expect(button).toBeInTheDocument();
    expect(button).toBeEnabled();
  });

  it("renders a Stop button when source=github, worker is alive, and the card is selected", () => {
    const entry = makeStateDirEntry({
      source: "github",
      state_key: "test-brief",
      runtime_state_present: true,
      worker_json_present: true,
      worker_pid: 12345,
      worker_alive: true,
      worker_state: "alive",
      heartbeat_age_s: 3
    });
    selectCard("github", "test-brief");
    render(StateDirRow, { entry });

    const button = screen.getByRole("button", { name: "Stop" });
    expect(button).toBeInTheDocument();
    expect(button).toBeEnabled();
  });

  it("hides the Stop button when worker is missing", () => {
    const entry = makeStateDirEntry({
      source: "linkedin",
      state_key: "test-brief",
      runtime_state_present: true,
      worker_state: "missing"
    });
    selectCard("linkedin", "test-brief");
    render(StateDirRow, { entry });

    expect(
      screen.queryByRole("button", { name: "Stop" })
    ).not.toBeInTheDocument();
  });

  it("does not render the Stop button when the card is not selected", () => {
    const entry = makeStateDirEntry({
      source: "linkedin",
      state_key: "test-brief",
      runtime_state_present: true,
      worker_json_present: true,
      worker_pid: 12345,
      worker_alive: true,
      worker_state: "alive",
      heartbeat_age_s: 3
    });
    render(StateDirRow, { entry });
    expect(
      screen.queryByRole("button", { name: "Stop" })
    ).not.toBeInTheDocument();
  });
});

describe("StateDirRow — stop telemetry emission", () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    _testClearEvents();
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
    vi.restoreAllMocks();
  });

  function aliveEntry() {
    return makeStateDirEntry({
      source: "linkedin",
      state_key: "test-brief",
      runtime_state_present: true,
      worker_json_present: true,
      worker_pid: 12345,
      worker_alive: true,
      worker_state: "alive",
      heartbeat_age_s: 3
    });
  }

  it("emits stop_attempted then stop_succeeded on a 202 response", async () => {
    globalThis.fetch = vi.fn(async (input: RequestInfo | URL) => {
      const url = typeof input === "string" ? input : input.toString();
      if (url.includes("/api/stop/")) {
        return new Response(
          JSON.stringify({ worker_state: "stopping" }),
          {
            status: 202,
            headers: { "content-type": "application/json" }
          }
        );
      }
      return new Response(
        JSON.stringify({ slice: "v0-shell-slice-4", entries: [] }),
        { status: 200, headers: { "content-type": "application/json" } }
      );
    }) as typeof fetch;

    selectCard("linkedin", "test-brief");
    render(StateDirRow, { entry: aliveEntry() });
    await fireEvent.click(screen.getByRole("button", { name: "Stop" }));
    await new Promise((r) => setTimeout(r, 0));

    const events = _testReadEvents();
    const types = events.map((e) => e.type);
    expect(types).toContain("stop_attempted");
    expect(types).toContain("stop_succeeded");
    expect(types).not.toContain("stop_failed");

    const success = events.find((e) => e.type === "stop_succeeded");
    expect(success).toBeDefined();
    if (success && success.type === "stop_succeeded") {
      expect(success.source).toBe("linkedin");
      expect(success.state_key).toBe("test-brief");
      expect(success.worker_state).toBe("stopping");
    }
  });

  it("emits stop_attempted then stop_failed on a 500 response", async () => {
    globalThis.fetch = vi.fn(async (input: RequestInfo | URL) => {
      const url = typeof input === "string" ? input : input.toString();
      if (url.includes("/api/stop/")) {
        return new Response(
          JSON.stringify({ detail: { error: "stop_failure_internal" } }),
          {
            status: 500,
            headers: { "content-type": "application/json" }
          }
        );
      }
      return new Response(
        JSON.stringify({ slice: "v0-shell-slice-4", entries: [] }),
        { status: 200, headers: { "content-type": "application/json" } }
      );
    }) as typeof fetch;

    selectCard("linkedin", "test-brief");
    render(StateDirRow, { entry: aliveEntry() });
    await fireEvent.click(screen.getByRole("button", { name: "Stop" }));
    await new Promise((r) => setTimeout(r, 0));

    const events = _testReadEvents();
    const types = events.map((e) => e.type);
    expect(types).toContain("stop_attempted");
    expect(types).toContain("stop_failed");
    expect(types).not.toContain("stop_succeeded");

    const failed = events.find((e) => e.type === "stop_failed");
    expect(failed).toBeDefined();
    if (failed && failed.type === "stop_failed") {
      expect(failed.source).toBe("linkedin");
      expect(failed.state_key).toBe("test-brief");
      expect(failed.error_code).toBe("stop_failure_internal");
    }
  });

  it("PII safety: stop events never expose error.message or path strings", async () => {
    globalThis.fetch = vi.fn(async (input: RequestInfo | URL) => {
      const url = typeof input === "string" ? input : input.toString();
      if (url.includes("/api/stop/")) {
        return new Response(JSON.stringify({ detail: "boom" }), {
          status: 500,
          headers: { "content-type": "application/json" }
        });
      }
      return new Response(
        JSON.stringify({ slice: "v0-shell-slice-4", entries: [] }),
        { status: 200, headers: { "content-type": "application/json" } }
      );
    }) as typeof fetch;

    selectCard("linkedin", "test-brief");
    render(StateDirRow, { entry: aliveEntry() });
    await fireEvent.click(screen.getByRole("button", { name: "Stop" }));
    await new Promise((r) => setTimeout(r, 0));

    for (const event of _testReadEvents()) {
      const serialized = JSON.stringify(event);
      expect(serialized).not.toContain("config/");
      expect(serialized).not.toContain("Stop failed");
    }
  });
});

describe("StateDirRow — suppressStatePill", () => {
  // Default behavior: pill renders. Pin so a future refactor that
  // changes the default value (e.g. flipping suppress to true by
  // accident) breaks loudly.
  it("renders the state pill by default", () => {
    const entry = makeStateDirEntry({
      runtime_state_present: true,
      worker_state: "missing",
      latest_run: {
        id: 1,
        status: "completed",
        stop_reason: "normal",
        mode: null,
        started_at: null,
        ended_at: null
      }
    });
    const { container } = render(StateDirRow, { entry });
    expect(container.querySelector(".card-status")).not.toBeNull();
    expect(screen.getAllByText("Completed").length).toBeGreaterThanOrEqual(1);
  });

  // Suppression contract: when the row is rendered inside a
  // homogeneous-state group (Filed page's "Finished cleanly" / "Lost
  // track" sections), GroupedList passes suppressStatePill=true so
  // the section header carries the state and the cards don't repeat
  // it. Caught a Gemini-flagged hierarchy inversion: every card's
  // "Lost track" pill duplicated the section header above it.
  it("hides the state pill when suppressStatePill is true", () => {
    const entry = makeStateDirEntry({
      runtime_state_present: true,
      worker_state: "missing",
      latest_run: {
        id: 1,
        status: "completed",
        stop_reason: "normal",
        mode: null,
        started_at: null,
        ended_at: null
      }
    });
    selectCard(entry.source, entry.state_key);
    const { container } = render(StateDirRow, {
      entry,
      suppressStatePill: true
    });
    expect(container.querySelector(".card-status")).toBeNull();
    // The Cloris/Pull fields still render — only the right-aligned
    // status pill in the header is suppressed.
    expect(container.querySelector(".card-field")).not.toBeNull();
  });
});
