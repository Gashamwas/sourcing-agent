// Stores tests — currentPollCadence + markAction (P1.14).
//
// Pure-function tests over the cadence reader; we drive the contributing
// stores (statusStore, pollErrorStore, lastActionAt) directly and assert
// the exact cadence bucket. The contract is binary — 3000 or 10000 — so
// tests pin both branches and the explicit "now" override that the
// production code uses for windowing.

import { beforeEach, describe, expect, it } from "vitest";
import { get } from "svelte/store";
import {
  currentPollCadence,
  lastActionAt,
  launchModeStore,
  markAction,
  pollErrorStore,
  selectedCardStore,
  statusStore,
  POLL_FAST_MS,
  POLL_SLOW_MS
} from "../lib/stores";
import { ApiError } from "../lib/api";
import { makeStateDirEntry } from "./fixtures";

beforeEach(() => {
  // Reset every cadence-input store so each test starts from a known
  // baseline. Without this, pollErrorStore/lastActionAt leak across
  // specs in the same file.
  statusStore.set(null);
  pollErrorStore.set(null);
  lastActionAt.set(0);
  // Reset card-file UI stores too — they leak across specs otherwise.
  selectedCardStore.set(null);
  launchModeStore.set(null);
});

describe("currentPollCadence", () => {
  it("returns fast when statusStore is null (initial-load bias)", () => {
    expect(currentPollCadence()).toBe(POLL_FAST_MS);
  });

  it("returns fast when at least one entry has worker_state=alive", () => {
    statusStore.set({
      slice: "v0-shell-slice-4",
      entries: [
        makeStateDirEntry({
          state_key: "brief-a",
          worker_state: "alive"
        })
      ]
    });
    expect(currentPollCadence()).toBe(POLL_FAST_MS);
  });

  it("returns fast when no alive workers but there is a recent action", () => {
    statusStore.set({
      slice: "v0-shell-slice-4",
      entries: [makeStateDirEntry({ worker_state: "missing" })]
    });
    const now = 1_000_000;
    lastActionAt.set(now - 1000); // 1s ago — well inside the 30s window.
    expect(currentPollCadence(now)).toBe(POLL_FAST_MS);
  });

  it("returns slow when the action is older than the 30s window", () => {
    statusStore.set({
      slice: "v0-shell-slice-4",
      entries: [makeStateDirEntry({ worker_state: "missing" })]
    });
    const now = 1_000_000;
    lastActionAt.set(now - 60_000); // 60s ago — outside the window.
    expect(currentPollCadence(now)).toBe(POLL_SLOW_MS);
  });

  it("returns fast when the API is unreachable (pollErrorStore set)", () => {
    statusStore.set({
      slice: "v0-shell-slice-4",
      entries: [makeStateDirEntry({ worker_state: "missing" })]
    });
    pollErrorStore.set(
      new ApiError(0, "ECONNREFUSED", "Network error contacting /api/status")
    );
    expect(currentPollCadence()).toBe(POLL_FAST_MS);
  });

  it("returns slow when fully idle (no alive, no action, no error)", () => {
    statusStore.set({
      slice: "v0-shell-slice-4",
      entries: [
        makeStateDirEntry({ state_key: "brief-a", worker_state: "missing" }),
        makeStateDirEntry({ state_key: "brief-b", worker_state: "stale" })
      ]
    });
    expect(currentPollCadence()).toBe(POLL_SLOW_MS);
  });

  it("ignores worker_state=alive_silent and stale for the alive-bias", () => {
    // alive_silent / stale are NOT "actively making progress"; they
    // should not pin the fast lane. (Recent-action and poll-error stay
    // false here, so the result is purely about the alive check.)
    statusStore.set({
      slice: "v0-shell-slice-4",
      entries: [
        makeStateDirEntry({ state_key: "brief-a", worker_state: "alive_silent" }),
        makeStateDirEntry({ state_key: "brief-b", worker_state: "stale" })
      ]
    });
    expect(currentPollCadence()).toBe(POLL_SLOW_MS);
  });
});

describe("markAction", () => {
  it("updates lastActionAt to the current timestamp", () => {
    expect(get(lastActionAt)).toBe(0);
    const before = Date.now();
    markAction();
    const after = Date.now();
    const stamped = get(lastActionAt);
    expect(stamped).toBeGreaterThanOrEqual(before);
    expect(stamped).toBeLessThanOrEqual(after);
  });
});

describe("launchModeStore", () => {
  it("defaults to null (no pending homescreen → LaunchForm intent)", () => {
    expect(get(launchModeStore)).toBeNull();
  });

  it("round-trips 'file' and 'resume' values plus null clear", () => {
    launchModeStore.set("file");
    expect(get(launchModeStore)).toBe("file");
    launchModeStore.set("resume");
    expect(get(launchModeStore)).toBe("resume");
    launchModeStore.set(null);
    expect(get(launchModeStore)).toBeNull();
  });
});

describe("selectedCardStore", () => {
  it("defaults to null (no card selected)", () => {
    expect(get(selectedCardStore)).toBeNull();
  });

  it("round-trips a 'source/state_key' selection and clears back to null", () => {
    selectedCardStore.set("linkedin/brief-a");
    expect(get(selectedCardStore)).toBe("linkedin/brief-a");
    selectedCardStore.set(null);
    expect(get(selectedCardStore)).toBeNull();
  });
});
