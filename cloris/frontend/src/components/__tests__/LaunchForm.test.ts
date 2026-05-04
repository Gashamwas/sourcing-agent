// LaunchForm — "Start a search" panel.
//
// What we're guarding (post Mock 4 density pass):
//   - Eyebrow text is "Start a search".
//   - Submit button is "Start search"; secondary is "Pull & Resume".
//   - The status region is announced via aria-live="polite".
//   - Telemetry: launch_attempted/_succeeded/_failed and resume_attempted/
//     _succeeded/_failed flow with brief_path_hash (never raw paths).
//   - markAction() is called on the success paths only (verified by reading
//     lastActionAt from the stores module).
//   - PII safety: emitted events never expose the raw brief path.
//   - Submitting empty trimmed input does NOT fire any telemetry.
//
// The prior helper-note assertion was retired — the note ("Pull & Resume
// only takes effect when this brief has work pending…") explained a state
// that no longer ships; the button is conditionally rendered now and only
// appears when a brief in the inventory is actually pull-able.

import { fireEvent, render, screen } from "@testing-library/svelte";
import { afterEach, beforeEach, describe, it, expect, vi } from "vitest";
import { get } from "svelte/store";
import LaunchForm from "../LaunchForm.svelte";
import { ApiError } from "../../lib/api";
import {
  launchFileCardButton,
  launchPanelEyebrow,
  launchPullResumeButton
} from "../../lib/copy";
import type { BriefInfo } from "../../lib/types";
import { lastActionAt, statusStore } from "../../lib/stores";
import { makeStateDirEntry } from "../../test/fixtures";
import {
  _testReadEvents,
  _testClearEvents,
  type TelemetryEvent
} from "../../lib/telemetry";

// Phase 3C: the Pull & Resume button is now conditionally rendered when
// at least one entry in the inventory is resumable. Tests that exercise
// the button install a status payload with a resumable entry.
function seedResumableInventory(): void {
  statusStore.set({
    slice: "v0-shell-slice-4",
    entries: [
      makeStateDirEntry({
        source: "linkedin",
        state_key: "test-resumable",
        runtime_state_present: true,
        resumable: true
      })
    ],
    counts: {
      active: 1,
      working: 0,
      paused: 1,
      finished: 0,
      lost: 0,
      archived: 0,
      orphaned: 0
    }
  });
}

// Hoisted vi.mock() so the LaunchForm module picks up the mocked api
// module at evaluation time. Each test reassigns the mock impls per
// scenario.
vi.mock("../../lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../lib/api")>();
  return {
    ...actual,
    // Phase F Slice F5: LaunchForm now fans out via launchForSource so
    // a brief targeting two modules fires N parallel launches. The
    // legacy launchLinkedIn helper is gone from LaunchForm's call
    // graph (still exported from api.ts for backward-compat callers).
    launchForSource: vi.fn(),
    resumeLinkedIn: vi.fn(),
    getBriefs: vi.fn(),
    getLaunchReadiness: vi.fn()
  };
});

// Re-import the mocked exports so we can redirect them per-test.
import {
  launchForSource,
  resumeLinkedIn,
  getBriefs,
  getLaunchReadiness
} from "../../lib/api";

// Phase 4 follow-on: the picker fetches /api/briefs on mount. Tests
// install a deterministic single-brief response so selection is
// trivially repeatable.
const TEST_BRIEF: BriefInfo = {
  path: "config/brief-some-role-v1.json",
  role_title: "Forward Deployed Engineer",
  linkedin_project: "FDE NYC",
  linkedin_project_id: "1990251114",
  modified_at: "2026-04-30T00:00:00+00:00"
};

function seedBriefsList(briefs: BriefInfo[] = [TEST_BRIEF]): void {
  (getBriefs as unknown as ReturnType<typeof vi.fn>).mockResolvedValue({
    slice: "v0-briefs-list-1",
    briefs
  });
}

// Phase D Slice D9 (Ledger L4). LaunchForm now fires getLaunchReadiness
// whenever a brief is selected. Tests that exercise the launch flow
// need the readiness probe to resolve `ready: true` so the launch
// button isn't disabled by the new pre-flight gate.
function seedReadyReadiness(): void {
  (
    getLaunchReadiness as unknown as ReturnType<typeof vi.fn>
  ).mockResolvedValue({
    slice: "v0-launch-readiness-1",
    source: "linkedin",
    brief_id: TEST_BRIEF.path,
    ready: true,
    blockers: []
  });
}

async function selectFirstBrief(): Promise<void> {
  // BriefPicker fetch resolves on the next microtask; wait for it,
  // then click the role-title button.
  await new Promise((r) => setTimeout(r, 0));
  await new Promise((r) => setTimeout(r, 0));
  const button = screen.getByRole("button", {
    name: new RegExp(TEST_BRIEF.role_title!, "i")
  });
  await fireEvent.click(button);
}

describe("LaunchForm — operational copy", () => {
  beforeEach(() => {
    seedBriefsList();
  });

  it("renders the eyebrow 'Start a search'", () => {
    render(LaunchForm);
    expect(screen.getByText(launchPanelEyebrow)).toBeInTheDocument();
    expect(launchPanelEyebrow).toBe("Start a search");
  });

  it("renders the brief picker, not a raw path input (Phase 4 follow-on)", async () => {
    const { container } = render(LaunchForm);
    await new Promise((r) => setTimeout(r, 0));
    await new Promise((r) => setTimeout(r, 0));
    expect(container.querySelector(".brief-picker")).not.toBeNull();
    // The previous developer-language Brief Path input is gone.
    expect(container.querySelector(".brief-input")).toBeNull();
  });

  it("renders the submit button 'Start search'", () => {
    render(LaunchForm);
    const button = screen.getByRole("button", { name: launchFileCardButton });
    expect(button).toBeInTheDocument();
    expect(launchFileCardButton).toBe("Start search");
  });

  it("renders the secondary button 'Pull & Resume' when an entry is resumable", () => {
    seedResumableInventory();
    render(LaunchForm);
    const button = screen.getByRole("button", { name: launchPullResumeButton });
    expect(button).toBeInTheDocument();
    expect(launchPullResumeButton).toBe("Pull & Resume");
  });

  it("hides the secondary button when no entry is resumable (Phase 3C)", () => {
    statusStore.set({
      slice: "v0-shell-slice-4",
      entries: [],
      counts: {
        active: 0,
        working: 0,
        paused: 0,
        finished: 0,
        lost: 0,
        archived: 0,
        orphaned: 0
      }
    });
    render(LaunchForm);
    expect(
      screen.queryByRole("button", { name: launchPullResumeButton })
    ).toBeNull();
  });

  it("marks the file-panel-status region with aria-live='polite'", () => {
    const { container } = render(LaunchForm);
    const status = container.querySelector(".file-panel-status");
    expect(status).not.toBeNull();
    expect(status?.getAttribute("aria-live")).toBe("polite");
  });
});

describe("LaunchForm — telemetry emission", () => {
  const BRIEF_PATH = "config/brief-some-role-v1.json";
  const launchMock = launchForSource as unknown as ReturnType<typeof vi.fn>;
  const resumeMock = resumeLinkedIn as unknown as ReturnType<typeof vi.fn>;

  beforeEach(() => {
    _testClearEvents();
    launchMock.mockReset();
    resumeMock.mockReset();
    lastActionAt.set(0);
    // Phase 3C: tests that click the Pull & Resume button need a
    // resumable entry in the inventory; otherwise the button is hidden.
    seedResumableInventory();
    // Phase 4 follow-on: BriefPicker fetches /api/briefs on mount.
    // Seed the response so the picker renders the test brief.
    seedBriefsList();
    // Phase D Slice D9: LaunchForm probes /api/launch-readiness on
    // brief selection. Seed a ready response so the launch button
    // isn't disabled by the pre-flight gate.
    seedReadyReadiness();
    // Never-resolving fetch: refreshStatus() inside the success branch
    // calls api.getStatus() which uses fetch under the hood. We don't
    // want that promise resolving (or rejecting) in the middle of our
    // assertions.
    vi.stubGlobal(
      "fetch",
      vi.fn(() => new Promise(() => {}))
    );
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  async function flushMicrotasks(): Promise<void> {
    await new Promise((r) => setTimeout(r, 0));
  }

  function eventTypes(events: readonly TelemetryEvent[]): string[] {
    return events.map((e) => e.type);
  }

  it("emits launch_attempted then launch_succeeded on a successful File Card", async () => {
    launchMock.mockResolvedValue({
      pid: 4242,
      state_dir: "/tmp/output/state/linkedin/some-role"
    });

    render(LaunchForm);
    await selectFirstBrief();
    await fireEvent.click(
      screen.getByRole("button", { name: launchFileCardButton })
    );
    await flushMicrotasks();

    const events = _testReadEvents();
    const types = eventTypes(events);
    expect(types).toContain("launch_attempted");
    expect(types).toContain("launch_succeeded");
    expect(types).not.toContain("launch_failed");

    const success = events.find((e) => e.type === "launch_succeeded");
    expect(success).toBeDefined();
    if (success && success.type === "launch_succeeded") {
      expect(success.source).toBe("linkedin");
      expect(success.pid).toBe(4242);
      expect(success.brief_path_hash).toMatch(/^[0-9a-f]{8}$/);
    }
  });

  it("calls markAction() on a successful File Card", async () => {
    launchMock.mockResolvedValue({
      pid: 4242,
      state_dir: "/tmp/output/state/linkedin/some-role"
    });

    render(LaunchForm);
    expect(get(lastActionAt)).toBe(0);
    await selectFirstBrief();
    await fireEvent.click(
      screen.getByRole("button", { name: launchFileCardButton })
    );
    await flushMicrotasks();

    expect(get(lastActionAt)).toBeGreaterThan(0);
  });

  it("emits launch_attempted then launch_failed on a failed launch", async () => {
    const apiErr = new ApiError(
      400,
      { error: "brief_path_not_found", brief_path: BRIEF_PATH },
      "Request failed"
    );
    launchMock.mockRejectedValue(apiErr);

    render(LaunchForm);
    await selectFirstBrief();
    await fireEvent.click(
      screen.getByRole("button", { name: launchFileCardButton })
    );
    await flushMicrotasks();

    const events = _testReadEvents();
    const types = eventTypes(events);
    expect(types).toContain("launch_attempted");
    expect(types).toContain("launch_failed");
    expect(types).not.toContain("launch_succeeded");

    const failed = events.find((e) => e.type === "launch_failed");
    expect(failed).toBeDefined();
    if (failed && failed.type === "launch_failed") {
      expect(failed.source).toBe("linkedin");
      expect(failed.error_code).toBe("brief_path_not_found");
    }
  });

  it("does NOT call markAction() on a failed File Card", async () => {
    launchMock.mockRejectedValue(
      new ApiError(400, { error: "brief_path_not_found" }, "Request failed")
    );

    render(LaunchForm);
    expect(get(lastActionAt)).toBe(0);
    await selectFirstBrief();
    await fireEvent.click(
      screen.getByRole("button", { name: launchFileCardButton })
    );
    await flushMicrotasks();

    expect(get(lastActionAt)).toBe(0);
  });

  it("emits resume_attempted then resume_succeeded on a successful Pull & Resume", async () => {
    resumeMock.mockResolvedValue({
      pid: 5151,
      state_dir: "/tmp/output/state/linkedin/some-role"
    });

    render(LaunchForm);
    await selectFirstBrief();
    await fireEvent.click(
      screen.getByRole("button", { name: launchPullResumeButton })
    );
    await flushMicrotasks();

    const events = _testReadEvents();
    const types = eventTypes(events);
    expect(types).toContain("resume_attempted");
    expect(types).toContain("resume_succeeded");
    expect(types).not.toContain("resume_failed");

    const success = events.find((e) => e.type === "resume_succeeded");
    expect(success).toBeDefined();
    if (success && success.type === "resume_succeeded") {
      expect(success.source).toBe("linkedin");
      expect(success.pid).toBe(5151);
    }
  });

  it("calls markAction() on a successful Pull & Resume", async () => {
    resumeMock.mockResolvedValue({
      pid: 5151,
      state_dir: "/tmp/output/state/linkedin/some-role"
    });

    render(LaunchForm);
    expect(get(lastActionAt)).toBe(0);
    await selectFirstBrief();
    await fireEvent.click(
      screen.getByRole("button", { name: launchPullResumeButton })
    );
    await flushMicrotasks();

    expect(get(lastActionAt)).toBeGreaterThan(0);
  });

  it("emits resume_attempted then resume_failed on a failed Pull & Resume", async () => {
    const apiErr = new ApiError(
      409,
      { error: "no_pending_work" },
      "Request failed"
    );
    resumeMock.mockRejectedValue(apiErr);

    render(LaunchForm);
    await selectFirstBrief();
    await fireEvent.click(
      screen.getByRole("button", { name: launchPullResumeButton })
    );
    await flushMicrotasks();

    const events = _testReadEvents();
    const types = eventTypes(events);
    expect(types).toContain("resume_attempted");
    expect(types).toContain("resume_failed");
    expect(types).not.toContain("resume_succeeded");

    const failed = events.find((e) => e.type === "resume_failed");
    expect(failed).toBeDefined();
    if (failed && failed.type === "resume_failed") {
      expect(failed.error_code).toBe("no_pending_work");
    }
  });

  it("falls back to error_code='unknown' when ApiError has no detail.error", async () => {
    launchMock.mockRejectedValue(
      new ApiError(500, "internal server problem", "Request failed")
    );

    render(LaunchForm);
    await selectFirstBrief();
    await fireEvent.click(
      screen.getByRole("button", { name: launchFileCardButton })
    );
    await flushMicrotasks();

    const failed = _testReadEvents().find((e) => e.type === "launch_failed");
    expect(failed).toBeDefined();
    if (failed && failed.type === "launch_failed") {
      expect(failed.error_code).toBe("unknown");
    }
  });

  it("PII safety: launch events use brief_path_hash, never the raw path", async () => {
    launchMock.mockResolvedValue({
      pid: 1,
      state_dir: "/tmp/output/state/linkedin/some-role"
    });
    render(LaunchForm);
    await selectFirstBrief();
    await fireEvent.click(
      screen.getByRole("button", { name: launchFileCardButton })
    );
    await flushMicrotasks();

    for (const event of _testReadEvents()) {
      const serialized = JSON.stringify(event);
      expect(serialized).not.toContain("config/");
      expect(serialized).not.toContain(BRIEF_PATH);
      // No `brief_path` field — only `brief_path_hash`.
      expect(event).not.toHaveProperty("brief_path");
    }
  });

  it("does NOT fire telemetry when no brief is selected (File Card)", async () => {
    // Phase 4 follow-on: with the picker, "empty input" is replaced by
    // "no brief selected." The button is disabled in that state, so a
    // click is a no-op and no telemetry fires.
    render(LaunchForm);
    await flushMicrotasks();
    await flushMicrotasks();
    const button = screen.getByRole("button", { name: launchFileCardButton });
    await fireEvent.click(button);
    await flushMicrotasks();

    expect(_testReadEvents()).toEqual([]);
  });

  it("does NOT fire telemetry when no brief is selected (Pull & Resume)", async () => {
    render(LaunchForm);
    await flushMicrotasks();
    await flushMicrotasks();
    const button = screen.getByRole("button", { name: launchPullResumeButton });
    await fireEvent.click(button);
    await flushMicrotasks();

    expect(_testReadEvents()).toEqual([]);
  });
});

// Phase D Slice D9 (Ledger L4) — Launch-readiness pre-flight tests.
//
// Pins the contract:
// - Selecting a brief fires getLaunchReadiness("linkedin", brief.path).
// - When ready=true, the section renders the ready prose, no blockers list,
//   and the launch button stays enabled.
// - When ready=false, blockers render with editorial remediation prose,
//   the launch button is disabled, and force bypass is NOT active by default.
// - The pre-flight section does NOT render when no brief is selected.
describe("LaunchForm — D9 launch-readiness pre-flight", () => {
  beforeEach(() => {
    seedResumableInventory();
    seedBriefsList();
    seedReadyReadiness();
    vi.stubGlobal("fetch", vi.fn(() => new Promise(() => {})));
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
    statusStore.set(null);
  });

  it("does NOT render the pre-flight section before a brief is selected", async () => {
    const { container } = render(LaunchForm);
    await new Promise((r) => setTimeout(r, 0));
    expect(container.querySelector(".launch-readiness")).toBeNull();
  });

  it("calls getLaunchReadiness with linkedin + brief.path on selection", async () => {
    render(LaunchForm);
    await selectFirstBrief();
    await new Promise((r) => setTimeout(r, 0));
    expect(getLaunchReadiness).toHaveBeenCalledWith(
      "linkedin",
      TEST_BRIEF.path
    );
  });

  it("renders the ready label when readiness reports ready", async () => {
    const { container } = render(LaunchForm);
    await selectFirstBrief();
    // Two ticks: first for the $effect to fire, second for the
    // mockResolvedValue's promise to settle into state.
    await new Promise((r) => setTimeout(r, 0));
    await new Promise((r) => setTimeout(r, 0));
    // Plan Finding 4: dropped "Cloris is ready to start." in favor of
    // a quieter "Ready." — the Start button enabling carries the bulk
    // of the message.
    expect(
      container.querySelector(".launch-readiness-ready")?.textContent
    ).toContain("Ready.");
    expect(container.querySelector(".launch-readiness-blockers")).toBeNull();
  });

  it("renders blockers with kind-specific class when readiness reports !ready", async () => {
    (
      getLaunchReadiness as unknown as ReturnType<typeof vi.fn>
    ).mockResolvedValue({
      slice: "v0-launch-readiness-1",
      source: "linkedin",
      brief_id: TEST_BRIEF.path,
      ready: false,
      blockers: [
        {
          kind: "auth",
          message: "Chrome is up, but Cloris couldn't find a browser session.",
          remediation: "Open a Chrome window and navigate to linkedin.com/talent."
        }
      ]
    });

    const { container } = render(LaunchForm);
    await selectFirstBrief();
    await new Promise((r) => setTimeout(r, 0));
    await new Promise((r) => setTimeout(r, 0));

    const blocker = container.querySelector(".launch-readiness-blocker");
    expect(blocker).not.toBeNull();
    expect(
      blocker?.classList.contains("launch-readiness-blocker--auth")
    ).toBe(true);
    expect(
      container.querySelector(".launch-readiness-blocker-message")?.textContent
    ).toContain("browser session");
    expect(
      container.querySelector(".launch-readiness-blocker-remediation")?.textContent
    ).toContain("Chrome window");
  });

  it("disables the launch button when readiness reports !ready (no force)", async () => {
    (
      getLaunchReadiness as unknown as ReturnType<typeof vi.fn>
    ).mockResolvedValue({
      slice: "v0-launch-readiness-1",
      source: "linkedin",
      brief_id: TEST_BRIEF.path,
      ready: false,
      blockers: [
        {
          kind: "net",
          message: "Cloris can't reach Chrome over CDP.",
          remediation: "Run ./launch-chrome.sh --force."
        }
      ]
    });

    render(LaunchForm);
    await selectFirstBrief();
    await new Promise((r) => setTimeout(r, 0));
    await new Promise((r) => setTimeout(r, 0));

    const launchBtn = screen.getByRole("button", {
      name: launchFileCardButton
    }) as HTMLButtonElement;
    expect(launchBtn.disabled).toBe(true);
  });

  it("keeps the launch button enabled when readiness reports ready", async () => {
    render(LaunchForm);
    await selectFirstBrief();
    await new Promise((r) => setTimeout(r, 0));
    await new Promise((r) => setTimeout(r, 0));

    const launchBtn = screen.getByRole("button", {
      name: launchFileCardButton
    }) as HTMLButtonElement;
    expect(launchBtn.disabled).toBe(false);
  });

  it("does NOT block the launch when getLaunchReadiness rejects (graceful fallback)", async () => {
    (
      getLaunchReadiness as unknown as ReturnType<typeof vi.fn>
    ).mockRejectedValue(new Error("network down"));

    const { container } = render(LaunchForm);
    await selectFirstBrief();
    await new Promise((r) => setTimeout(r, 0));
    await new Promise((r) => setTimeout(r, 0));

    // Error prose renders.
    expect(
      container.querySelector(".launch-readiness-error")?.textContent
    ).toBeTruthy();
    // Launch button is NOT blocked — the probe fails open. The actual
    // launch will surface its own errors if the source is genuinely
    // unreachable; we don't double-fail the recruiter on a transient
    // probe error.
    const launchBtn = screen.getByRole("button", {
      name: launchFileCardButton
    }) as HTMLButtonElement;
    expect(launchBtn.disabled).toBe(false);
  });
});

// Phase F Slice F5. Module picker behavior:
// - Brief with target_modules:["linkedin","github"] pre-selects both chips.
// - Clicking a chip toggles selection.
// - Submit fans out to launchForSource per selected module.
// - "Pick at least one module" prose renders when none selected.
describe("LaunchForm — F5 module picker", () => {
  const launchMock = launchForSource as unknown as ReturnType<typeof vi.fn>;

  beforeEach(() => {
    _testClearEvents();
    launchMock.mockReset();
    seedResumableInventory();
    seedReadyReadiness();
    vi.stubGlobal(
      "fetch",
      vi.fn(() => new Promise(() => {}))
    );
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  function seedMultiModuleBrief(): void {
    (getBriefs as unknown as ReturnType<typeof vi.fn>).mockResolvedValue({
      slice: "v0-briefs-list-1",
      briefs: [
        {
          ...TEST_BRIEF,
          brief_id: "1990251114",
          target_modules: ["linkedin", "github"]
        }
      ]
    });
  }

  it("pre-selects chips per the brief's target_modules", async () => {
    seedMultiModuleBrief();
    const { container } = render(LaunchForm);
    await selectFirstBrief();
    await new Promise((r) => setTimeout(r, 0));
    await new Promise((r) => setTimeout(r, 0));

    const chips = container.querySelectorAll(".launch-module-chip");
    expect(chips.length).toBeGreaterThanOrEqual(2);
    const linkedinChip = container.querySelector(
      '.launch-module-chip[aria-pressed="true"][title=""], .launch-module-chip.is-selected'
    );
    expect(linkedinChip).not.toBeNull();
    // Both LinkedIn AND GitHub chips selected.
    const selectedChips = container.querySelectorAll(
      ".launch-module-chip.is-selected"
    );
    expect(selectedChips.length).toBe(2);
  });

  it("defaults to LinkedIn when target_modules is absent (legacy brief)", async () => {
    seedBriefsList();
    const { container } = render(LaunchForm);
    await selectFirstBrief();
    await new Promise((r) => setTimeout(r, 0));
    await new Promise((r) => setTimeout(r, 0));

    const selectedChips = container.querySelectorAll(
      ".launch-module-chip.is-selected"
    );
    expect(selectedChips.length).toBe(1);
    expect(selectedChips[0].textContent?.trim()).toBe("LinkedIn");
  });

  it("toggles a chip on click", async () => {
    seedMultiModuleBrief();
    const { container } = render(LaunchForm);
    await selectFirstBrief();
    await new Promise((r) => setTimeout(r, 0));

    const chips = Array.from(
      container.querySelectorAll(".launch-module-chip")
    ) as HTMLButtonElement[];
    const linkedinChip = chips.find((c) => c.textContent?.includes("LinkedIn"))!;
    expect(linkedinChip.classList.contains("is-selected")).toBe(true);

    await fireEvent.click(linkedinChip);
    expect(linkedinChip.classList.contains("is-selected")).toBe(false);
  });

  it("submit fans out to launchForSource for each selected module", async () => {
    seedMultiModuleBrief();
    launchMock.mockResolvedValue({
      pid: 9999,
      state_dir: "/tmp",
      source: "linkedin",
      mode: "fresh"
    });

    render(LaunchForm);
    await selectFirstBrief();
    await new Promise((r) => setTimeout(r, 0));
    await new Promise((r) => setTimeout(r, 0));

    await fireEvent.click(
      screen.getByRole("button", { name: launchFileCardButton })
    );
    await new Promise((r) => setTimeout(r, 0));

    expect(launchMock).toHaveBeenCalledTimes(2);
    const sources = launchMock.mock.calls.map((args) => args[0]);
    expect(sources).toContain("linkedin");
    expect(sources).toContain("github");
  });

  it("renders empty-prose cue when all modules deselected", async () => {
    seedBriefsList();
    const { container } = render(LaunchForm);
    await selectFirstBrief();
    await new Promise((r) => setTimeout(r, 0));

    // Click the LinkedIn chip to deselect.
    const linkedinChip = Array.from(
      container.querySelectorAll(".launch-module-chip")
    ).find((c) => c.textContent?.includes("LinkedIn")) as HTMLButtonElement;
    await fireEvent.click(linkedinChip);

    expect(container.querySelector(".launch-modules-empty")).not.toBeNull();
    const launchBtn = screen.getByRole("button", {
      name: launchFileCardButton
    }) as HTMLButtonElement;
    expect(launchBtn.disabled).toBe(true);
  });

  it("Researcher chip is rendered but disabled", async () => {
    seedBriefsList();
    const { container } = render(LaunchForm);
    await selectFirstBrief();
    await new Promise((r) => setTimeout(r, 0));

    const researcherChip = Array.from(
      container.querySelectorAll(".launch-module-chip")
    ).find((c) => c.textContent?.includes("Researcher")) as HTMLButtonElement;
    expect(researcherChip).toBeDefined();
    expect(researcherChip.classList.contains("is-disabled")).toBe(true);
    expect(researcherChip.getAttribute("aria-disabled")).toBe("true");
    // Clicking does not select.
    await fireEvent.click(researcherChip);
    expect(researcherChip.classList.contains("is-selected")).toBe(false);
  });
});
