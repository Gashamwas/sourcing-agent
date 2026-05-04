// FiledAwayPage tests — the dedicated route for browsing The Quiet Drawer.
//
// What we're guarding:
//   - Loading / empty / populated states render the right copy.
//   - Find-a-card input narrows the visible list.
//   - Back link points at #/ so the user can return to the homescreen.
//   - Surface_viewed telemetry emits "filed_away" on mount.
//   - selectedCardStore is reset on mount so an open card from the
//     homescreen doesn't leak into the drawer view.

import { fireEvent, render, screen } from "@testing-library/svelte";
import { afterEach, beforeEach, describe, it, expect, vi } from "vitest";
import { tick } from "svelte";
import { get } from "svelte/store";
import FiledAwayPage from "../FiledAwayPage.svelte";
import { makeStateDirEntry } from "../../test/fixtures";
import { statusStore, selectedCardStore } from "../../lib/stores";
import { _testClearEvents, _testReadEvents } from "../../lib/telemetry";

beforeEach(() => {
  statusStore.set(null);
  selectedCardStore.set("linkedin/leftover");
  _testClearEvents();
  vi.stubGlobal(
    "fetch",
    vi.fn(() => new Promise(() => {}))
  );
  window.location.hash = "#/filed";
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  window.location.hash = "#/";
});

describe("FiledAwayPage — render", () => {
  it("renders the Paused briefs title", () => {
    render(FiledAwayPage);
    expect(screen.getByRole("heading", { level: 2 })).toHaveTextContent(
      "Paused briefs"
    );
  });

  it("renders a back link to #/", () => {
    // Phase 5 follow-on: back-nav refactored from inline
    // .homescreen-look-through into the dedicated PageBackLink primitive
    // (.page-back-link). Test asserts the new selector + label.
    const { container } = render(FiledAwayPage);
    const link = container.querySelector(
      ".page-back-link"
    ) as HTMLAnchorElement | null;
    expect(link).not.toBeNull();
    expect(link?.getAttribute("href")).toBe("#/");
    expect(link?.textContent ?? "").toContain("Back to active briefs");
  });

  it("shows a Finding loader when statusStore is null", () => {
    const { container } = render(FiledAwayPage);
    expect(container.querySelector(".finding-stage")).not.toBeNull();
  });

  it("shows the empty-back copy when no filed entries exist", async () => {
    statusStore.set({
      slice: "v0-shell-slice-4",
      entries: [
        makeStateDirEntry({
          state_key: "alpha",
          worker_state: "alive",
          worker_alive: true,
          worker_pid: 1
        })
      ]
    });
    render(FiledAwayPage);
    await tick();
    expect(screen.getByText("No paused briefs.")).toBeInTheDocument();
  });

  it("renders a card row per filed-away entry", async () => {
    statusStore.set({
      slice: "v0-shell-slice-4",
      entries: [
        makeStateDirEntry({
          state_key: "alpha",
          worker_state: "missing",
          latest_run: {
            id: 1,
            status: "completed",
            stop_reason: "normal",
            mode: null,
            started_at: null,
            ended_at: null
          }
        }),
        makeStateDirEntry({
          state_key: "beta",
          worker_state: "missing",
          latest_run: {
            id: 2,
            status: "completed",
            stop_reason: "normal",
            mode: null,
            started_at: null,
            ended_at: null
          }
        })
      ]
    });
    const { container } = render(FiledAwayPage);
    await tick();
    const cards = container.querySelectorAll(".card");
    expect(cards.length).toBe(2);
  });
});

describe("FiledAwayPage — find filter", () => {
  beforeEach(() => {
    statusStore.set({
      slice: "v0-shell-slice-4",
      entries: [
        makeStateDirEntry({
          state_key: "alpha-search",
          worker_state: "missing",
          latest_run: {
            id: 1,
            status: "completed",
            stop_reason: "normal",
            mode: null,
            started_at: null,
            ended_at: null
          }
        }),
        makeStateDirEntry({
          state_key: "beta-different",
          worker_state: "missing",
          latest_run: {
            id: 2,
            status: "completed",
            stop_reason: "normal",
            mode: null,
            started_at: null,
            ended_at: null
          }
        })
      ]
    });
  });

  it("narrows the visible list when the input matches", async () => {
    const { container } = render(FiledAwayPage);
    await tick();

    const input = container.querySelector("#filed-finder") as HTMLInputElement;
    expect(input).not.toBeNull();
    await fireEvent.input(input, { target: { value: "alpha" } });
    await tick();

    const cards = container.querySelectorAll(".card");
    expect(cards.length).toBe(1);
    expect(cards[0].getAttribute("data-source")).toBe("linkedin");
  });

  it("renders the no-match copy when nothing matches", async () => {
    const { container } = render(FiledAwayPage);
    await tick();

    const input = container.querySelector("#filed-finder") as HTMLInputElement;
    await fireEvent.input(input, { target: { value: "no-such-thing" } });
    await tick();

    expect(screen.getByText("No briefs match.")).toBeInTheDocument();
  });
});

describe("FiledAwayPage — mount side effects", () => {
  it("clears selectedCardStore on mount so a homescreen-open card does not leak", () => {
    expect(get(selectedCardStore)).toBe("linkedin/leftover");
    render(FiledAwayPage);
    expect(get(selectedCardStore)).toBeNull();
  });

  // Surface_viewed{filed_away} emission is tested in App.test.ts; this
  // component does not emit on mount.
});
