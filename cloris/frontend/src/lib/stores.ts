// Cloris UI state stores.
//
// statusStore — last successful /api/status payload, or null before the
//   first poll. The UI reads this everywhere; never mutate it from
//   anywhere except `refreshStatus`.
// pollErrorStore — the last polling error, cleared on the next successful
//   poll. The AmbientBanner uses this to surface a plain operational
//   error block (no character voice) when the API is unreachable.
// optimisticStoppingStore — keys "{source}/{state_key}" for which the UI
//   has optimistically rendered "Stopping..." after a 202 stop response.
//   Reconciled on each poll: any key whose worker_state is no longer
//   "alive" gets cleared (reality has caught up with the optimistic
//   render).
// lastActionAt — Date.now() of the most recent user action that should
//   bias the poll cadence to the fast lane (3s). Set by callers via
//   markAction() right after a launch / resume / stop request fires.
//   Pure timestamp; readers compare to a window (default 30s).

import { writable, get } from "svelte/store";
import { ApiError, getStatus } from "./api";
import type { StatusResponse } from "./types";

export const statusStore = writable<StatusResponse | null>(null);
export const pollErrorStore = writable<ApiError | null>(null);
export const optimisticStoppingStore = writable<Set<string>>(new Set());
export const lastActionAt = writable<number>(0);

// Card-file UI: which card (if any) is currently selected/expanded.
// Key format: "{source}/{state_key}". null when no card is selected.
export const selectedCardStore = writable<string | null>(null);

// Homescreen → LaunchForm intent. Set by VerbTile clicks ("Start a search"
// or "Resume a search") so LaunchForm can focus the brief-path input and
// shift the corresponding button to visual primary. Cleared on submit and
// on form reset. null = no pending intent.
export type LaunchMode = "file" | "resume";
export const launchModeStore = writable<LaunchMode | null>(null);

// Adaptive poll cadence (P1.14).
//
// Two-bucket cadence: fast (3s) when something is actively changing or
// likely to change soon, slow (10s) when the ledger is idle. We bound
// the cadence to exactly these two values — no intermediate steps —
// because a clearly-binary cadence is easier to reason about and easier
// to test than a sliding window.
//
// `currentPollCadence` is a pure function of the current store snapshot.
// It is exported so App.svelte can call it from a subscriber and so the
// unit test can drive it directly without timers.
export const POLL_FAST_MS = 3000 as const;
export const POLL_SLOW_MS = 10000 as const;
const ACTION_RECENT_WINDOW_MS = 30_000;

export type PollCadence = typeof POLL_FAST_MS | typeof POLL_SLOW_MS;

// Stamp the last-action timestamp. Callers (LaunchForm, StateDirRow stop)
// invoke this synchronously when their action fires. The cadence reader
// then biases toward fast polling for ACTION_RECENT_WINDOW_MS afterward.
export function markAction(): void {
  lastActionAt.set(Date.now());
}

// Compute the next poll cadence from the current ambient state.
//
// Fast (3s) if ANY of:
//   - any tracked entry has worker_state === "alive" (something running)
//   - lastActionAt is within ACTION_RECENT_WINDOW_MS of `now` (user just
//     acted; we want the UI to reflect the result quickly)
//   - pollErrorStore is non-null (API is unreachable; shorter retry loop)
//
// Slow (10s) otherwise (idle ledger).
//
// Initial-load bias: when statusStore is null (before first poll lands)
// we return fast — first-render responsiveness matters more than the
// cost of one or two extra requests.
export function currentPollCadence(now: number = Date.now()): PollCadence {
  const status = get(statusStore);
  if (status === null) return POLL_FAST_MS;

  const hasAlive = status.entries.some(
    (entry) => entry.worker_state === "alive"
  );
  if (hasAlive) return POLL_FAST_MS;

  const recentActionAt = get(lastActionAt);
  if (recentActionAt > 0 && now - recentActionAt < ACTION_RECENT_WINDOW_MS) {
    return POLL_FAST_MS;
  }

  if (get(pollErrorStore) !== null) return POLL_FAST_MS;

  return POLL_SLOW_MS;
}

function key(source: string, stateKey: string): string {
  return `${source}/${stateKey}`;
}

export function markStopping(source: string, stateKey: string): void {
  optimisticStoppingStore.update((current) => {
    const next = new Set(current);
    next.add(key(source, stateKey));
    return next;
  });
}

export function clearStopping(source: string, stateKey: string): void {
  optimisticStoppingStore.update((current) => {
    if (!current.has(key(source, stateKey))) return current;
    const next = new Set(current);
    next.delete(key(source, stateKey));
    return next;
  });
}

export async function refreshStatus(): Promise<void> {
  try {
    const next = await getStatus();
    statusStore.set(next);
    pollErrorStore.set(null);

    // Reconcile optimistic-stopping against reality: any key whose
    // worker_state in the freshly polled response is no longer "alive"
    // means the worker has actually stopped (or was never alive). Clear
    // the optimistic flag so the UI falls back to the truth from the
    // payload.
    const stopping = get(optimisticStoppingStore);
    if (stopping.size > 0) {
      const next_set = new Set(stopping);
      let changed = false;
      for (const k of stopping) {
        const [source, stateKey] = k.split("/", 2);
        const entry = next.entries.find(
          (e) => e.source === source && e.state_key === stateKey
        );
        if (!entry || entry.worker_state !== "alive") {
          next_set.delete(k);
          changed = true;
        }
      }
      if (changed) optimisticStoppingStore.set(next_set);
    }
  } catch (err) {
    if (err instanceof ApiError) {
      pollErrorStore.set(err);
    } else {
      pollErrorStore.set(
        new ApiError(0, String(err), "Unknown polling error")
      );
    }

    // If we've never had a successful response, promote statusStore
    // from null to an empty payload so the UI can move past the
    // initial-load Finding loader. Without this, a downed backend
    // leaves the user staring at the loader forever. The pollErrorStore
    // already carries the error for the AmbientBanner to surface.
    if (get(statusStore) === null) {
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
          orphaned: 0,
        },
        briefs: [],
      });
    }
  }
}
