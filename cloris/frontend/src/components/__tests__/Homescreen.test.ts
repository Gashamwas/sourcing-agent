// Homescreen tests — the new home surface for the Cloris card file.
//
// What we're guarding (post Mock 4):
//   - Renders all four verbs in their canonical order via RunningFolio.
//   - Click on each enabled verb fires the correct routing /
//     launchModeStore side effect.
//   - Soft-disabled verbs do not navigate or set the store.
//   - In-motion mini-list is capped at IN_MOTION_CAP entries, with a
//     "look through the rest" link to #/filed when there is data.
//   - Surface_viewed telemetry emits "homescreen" on mount.
//
// The prior `homescreen-ambient` narrative line was retired in the Mock 4
// density pass — its content was redundant with the AmbientBanner counts
// ribbon (R23 — no unjustified redundancy). Tests for that line moved
// with it.

import { fireEvent, render, screen } from "@testing-library/svelte";
import { afterEach, beforeEach, describe, it, expect, vi } from "vitest";
import { tick } from "svelte";
import Homescreen from "../Homescreen.svelte";
import { makeStateDirEntry } from "../../test/fixtures";
import {
  statusStore,
  pollErrorStore,
  selectedCardStore,
  launchModeStore
} from "../../lib/stores";
import { _testClearEvents, _testReadEvents } from "../../lib/telemetry";

beforeEach(() => {
  statusStore.set(null);
  pollErrorStore.set(null);
  selectedCardStore.set(null);
  launchModeStore.set(null);
  _testClearEvents();
  // Stub fetch to a never-resolving promise so any unintended status poll
  // doesn't actually hit the network in tests.
  vi.stubGlobal(
    "fetch",
    vi.fn(() => new Promise(() => {}))
  );
  // Reset the URL hash so navigate() in tests doesn't accumulate state
  // across runs.
  window.location.hash = "#/";
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  window.location.hash = "#/";
});

describe("Homescreen — running folio render", () => {
  it("renders all four verbs in canonical order", () => {
    const { container } = render(Homescreen);
    const verbs = container.querySelectorAll(".folio-verb");
    expect(verbs.length).toBe(4);
    const ids = Array.from(verbs).map((el) => el.getAttribute("data-verb"));
    expect(ids).toEqual([
      "write_brief",
      "start_search",
      "read_report",
      "learn_market"
    ]);
  });

  it("marks read_report (the only soft-disabled verb) as aria-disabled", () => {
    // Phase E Slice E3: learn_market flipped from soft-disabled to
    // active. read_report is the lone disabled verb until Phase E
    // wires up its target (or earlier).
    const { container } = render(Homescreen);
    const readReport = container.querySelector('.folio-verb[data-verb="read_report"]');
    const learnMarket = container.querySelector('.folio-verb[data-verb="learn_market"]');
    expect(readReport?.getAttribute("aria-disabled")).toBe("true");
    expect(learnMarket?.getAttribute("aria-disabled")).toBe("false");
  });

  it("renders the three wired verbs as enabled", () => {
    // Phase E Slice E3: learn_market joins the wired set.
    const { container } = render(Homescreen);
    for (const verb of ["write_brief", "start_search", "learn_market"]) {
      const tile = container.querySelector(`.folio-verb[data-verb="${verb}"]`);
      expect(tile?.getAttribute("aria-disabled")).toBe("false");
    }
  });
});

describe("Homescreen — verb routing", () => {
  it("Write a brief → navigates to #/brief/new", async () => {
    const { container } = render(Homescreen);
    const tile = container.querySelector(
      '.folio-verb[data-verb="write_brief"]'
    ) as HTMLElement;
    await fireEvent.click(tile);
    expect(window.location.hash).toBe("#/brief/new");
  });

  it("Start a search → signals launchModeStore with 'file'", async () => {
    const seen: ("file" | "resume" | null)[] = [];
    const unsub = launchModeStore.subscribe((v) => seen.push(v));
    const { container } = render(Homescreen);
    const tile = container.querySelector(
      '.folio-verb[data-verb="start_search"]'
    ) as HTMLElement;
    await fireEvent.click(tile);
    unsub();
    // LaunchForm consumes the intent and clears it back to null; the test
    // verifies that "file" was observed at least once during the click
    // sequence rather than asserting the post-click resting value.
    expect(seen).toContain("file");
  });

  it("Read a run's report → does not navigate or signal launchModeStore", async () => {
    const seen: ("file" | "resume" | null)[] = [];
    const unsub = launchModeStore.subscribe((v) => seen.push(v));
    const { container } = render(Homescreen);
    const tile = container.querySelector(
      '.folio-verb[data-verb="read_report"]'
    ) as HTMLElement;
    await fireEvent.click(tile);
    unsub();
    expect(window.location.hash).toBe("#/");
    expect(seen.filter((v) => v !== null)).toEqual([]);
  });

  it("Learn about the market → navigates to #/market (Phase E Slice E3)", async () => {
    const seen: ("file" | "resume" | null)[] = [];
    const unsub = launchModeStore.subscribe((v) => seen.push(v));
    const { container } = render(Homescreen);
    const tile = container.querySelector(
      '.folio-verb[data-verb="learn_market"]'
    ) as HTMLElement;
    await fireEvent.click(tile);
    unsub();
    expect(window.location.hash).toBe("#/market");
    expect(seen.filter((v) => v !== null)).toEqual([]);
  });

  it("Read a run's report → enables when at least one run exists, navigating to its brief-first workspace", async () => {
    statusStore.set({
      slice: "v0-shell-slice-4",
      entries: [
        makeStateDirEntry({
          source: "linkedin",
          state_key: "older",
          runtime_state_present: true,
          brief_id_from_run: "brief-older",
          latest_run: {
            id: 5,
            status: "completed",
            stop_reason: "normal",
            mode: "fresh",
            started_at: "2026-04-29T08:00:00Z",
            ended_at: "2026-04-29T09:00:00Z"
          }
        }),
        makeStateDirEntry({
          source: "linkedin",
          state_key: "newest",
          runtime_state_present: true,
          brief_id_from_run: "brief-newest",
          latest_run: {
            id: 12,
            status: "completed",
            stop_reason: "normal",
            mode: "fresh",
            started_at: "2026-04-29T11:00:00Z",
            ended_at: "2026-04-29T11:30:00Z"
          }
        })
      ]
    });
    const { container } = render(Homescreen);
    await tick();

    const tile = container.querySelector(
      '.folio-verb[data-verb="read_report"]'
    ) as HTMLElement;
    expect(tile.getAttribute("aria-disabled")).toBe("false");

    await fireEvent.click(tile);
    // Phase C-bis 0.1: REVIEW navigates to the brief-first workspace URL
    // using the latest run's brief_id (not source/state_key).
    expect(window.location.hash).toBe("#/workspace/brief-newest");
  });
});

describe("Homescreen — in-motion mini-list", () => {
  it("shows a Finding loader when statusStore is null", () => {
    const { container } = render(Homescreen);
    expect(container.querySelector(".finding-stage")).not.toBeNull();
  });

  it("shows the empty-front copy when no entries need attention", async () => {
    statusStore.set({ slice: "v0-shell-slice-4", entries: [] });
    render(Homescreen);
    await tick();
    expect(screen.getByText("No briefs need attention.")).toBeInTheDocument();
  });

  it("renders one card row per front-of-file entry", async () => {
    statusStore.set({
      slice: "v0-shell-slice-4",
      entries: [
        makeStateDirEntry({
          state_key: "alpha",
          worker_state: "alive",
          worker_alive: true,
          worker_pid: 1
        }),
        makeStateDirEntry({
          state_key: "beta",
          worker_state: "missing",
          resumable: true
        })
      ]
    });
    const { container } = render(Homescreen);
    await tick();
    const cards = container.querySelectorAll(".card");
    expect(cards.length).toBe(2);
  });

  it("caps the mini-list at five entries even when more are present", async () => {
    const entries = Array.from({ length: 8 }, (_, i) =>
      makeStateDirEntry({
        state_key: `brief-${i}`,
        worker_state: "alive",
        worker_alive: true,
        worker_pid: 1000 + i
      })
    );
    statusStore.set({ slice: "v0-shell-slice-4", entries });
    const { container } = render(Homescreen);
    await tick();
    const cards = container.querySelectorAll(".card");
    expect(cards.length).toBe(5);
  });
});

describe("Homescreen — look-through link", () => {
  it("does not render when statusStore has not loaded", () => {
    const { container } = render(Homescreen);
    expect(container.querySelector(".homescreen-look-through")).toBeNull();
  });

  it("renders and points at #/filed when entries exist", async () => {
    statusStore.set({
      slice: "v0-shell-slice-4",
      entries: [makeStateDirEntry({ state_key: "alpha" })]
    });
    const { container } = render(Homescreen);
    await tick();
    const link = container.querySelector(
      ".homescreen-look-through"
    ) as HTMLAnchorElement | null;
    expect(link).not.toBeNull();
    expect(link?.getAttribute("href")).toBe("#/filed");
  });
});

// Surface_viewed{homescreen} emission is tested in App.test.ts where the
// route subscription that drives the emit lives. Homescreen.svelte itself
// does not emit on mount — adding it here would double-fire when App.svelte
// also emits for the home route.
