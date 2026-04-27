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

import { writable, get } from "svelte/store";
import { ApiError, getStatus } from "./api";
import type { StatusResponse } from "./types";

export const statusStore = writable<StatusResponse | null>(null);
export const pollErrorStore = writable<ApiError | null>(null);
export const optimisticStoppingStore = writable<Set<string>>(new Set());

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
  }
}
