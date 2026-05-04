// Onboarding flow Svelte stores + sync helpers (A24 trial plan, Slice 1B).
//
// Mutations route through patchActiveSession / advanceStep /
// updateStateField, which apply the change locally first (optimistic
// UI) and then sync to the backend. On error the local change is
// reverted and `syncError` is set so the consumer can decide how to
// surface it.
//
// Concurrency model:
//   - syncInFlight is a counter — multiple PATCHes can be in flight
//     concurrently (different keys with different debounce timers, or
//     a manual patch landing while a debounced field flush is pending).
//   - updateStateField debounces per-key. Same-key calls coalesce into
//     a single PATCH carrying the latest value; different keys do not
//     coalesce.
//   - On flush failure we revert to the pre-first-edit value, not to
//     an intermediate optimistic value. We track that pre-edit value
//     in PendingFlush.originalValue and PRESERVE it across coalesce.

import { get, writable } from "svelte/store";
import type { IntakeSession, IntakeStep } from "../types";
import {
  createIntakeSession,
  getIntakeSession,
  patchIntakeSession,
  polishIntakeSession,
  restoreIntakeSession,
} from "./api";

// The active session being authored. Null when none is loaded.
export const activeSession = writable<IntakeSession | null>(null);

// Counter of in-flight backend syncs. We use a counter — not a
// boolean — because debounced per-key updates can fire concurrently.
export const syncInFlight = writable<number>(0);

// Last sync error if any. Cleared on the next successful sync.
export const syncError = writable<Error | null>(null);

// Debounce window for updateStateField. Mutable so tests can shorten
// it. Production code never reassigns this.
let debounceMs = 1000;

// Test hook only — exposed so tests can shorten the debounce window.
export function __setDebounceMsForTests(ms: number): void {
  debounceMs = ms;
}

// Per-key pending state. originalExisted + originalValue capture the
// pre-first-edit value so revert can distinguish "delete this key" from
// "restore previous value"; both fields are preserved across coalesce
// so rapid sequential edits revert all the way back on failure.
//
// ReturnType<typeof setTimeout> dodges the browser/node return-type
// mismatch under TS strict.
type PendingFlush = {
  timer: ReturnType<typeof setTimeout>;
  value: unknown;
  originalExisted: boolean;
  originalValue: unknown;
};
const pendingFlushes = new Map<string, PendingFlush>();

function bumpInFlight(delta: 1 | -1): void {
  syncInFlight.update((n) => n + delta);
}

// Snapshot-and-revert helper. On error we restore the pre-patch
// snapshot regardless of whether the user has since done another local
// edit; defending against interleaved edits would require a per-field
// version vector and is out of scope for Slice 1.
async function _syncPatch(
  id: number,
  patch: {
    current_step?: IntakeStep;
    state_json?: Record<string, unknown>;
    role_title?: string;
  },
  optimisticSession: IntakeSession,
  snapshot: IntakeSession | null
): Promise<IntakeSession | null> {
  activeSession.set(optimisticSession);
  bumpInFlight(1);
  try {
    const fresh = await patchIntakeSession(id, patch);
    activeSession.set(fresh);
    syncError.set(null);
    return fresh;
  } catch (err) {
    activeSession.set(snapshot);
    syncError.set(err instanceof Error ? err : new Error(String(err)));
    return null;
  } finally {
    bumpInFlight(-1);
  }
}

// Create a new session server-side and load it into activeSession.
export async function startNewSession(
  args: { role_title?: string } = {}
): Promise<IntakeSession> {
  bumpInFlight(1);
  try {
    const session = await createIntakeSession(args);
    activeSession.set(session);
    syncError.set(null);
    return session;
  } catch (err) {
    syncError.set(err instanceof Error ? err : new Error(String(err)));
    throw err;
  } finally {
    bumpInFlight(-1);
  }
}

// Fetch an existing session by id. On error activeSession stays at its
// prior value; a stale session is more useful to the UI than nothing
// during a transient network blip.
export async function loadSession(id: number): Promise<IntakeSession> {
  bumpInFlight(1);
  try {
    const session = await getIntakeSession(id);
    activeSession.set(session);
    syncError.set(null);
    return session;
  } catch (err) {
    syncError.set(err instanceof Error ? err : new Error(String(err)));
    throw err;
  } finally {
    bumpInFlight(-1);
  }
}

// Apply an optimistic patch and sync. Returns the server-confirmed
// session on success, null on failure (after reverting). Throws
// nothing — the error is observable via syncError so call sites can
// stay declarative.
export async function patchActiveSession(patch: {
  current_step?: IntakeStep;
  state_json?: Record<string, unknown>;
  role_title?: string;
}): Promise<IntakeSession | null> {
  const snapshot = get(activeSession);
  if (snapshot === null) {
    syncError.set(new Error("No active session to patch"));
    return null;
  }
  const optimistic: IntakeSession = {
    ...snapshot,
    ...(patch.current_step !== undefined
      ? { current_step: patch.current_step }
      : {}),
    ...(patch.state_json !== undefined ? { state_json: patch.state_json } : {}),
    ...(patch.role_title !== undefined ? { role_title: patch.role_title } : {}),
  };
  return _syncPatch(snapshot.id, patch, optimistic, snapshot);
}

// Convenience wrapper around patchActiveSession.
export async function advanceStep(next: IntakeStep): Promise<void> {
  await patchActiveSession({ current_step: next });
}

// Shallow-merge {[key]: value} into state_json. Debounced per-key so
// rapid edits (typing in a prose field) collapse into one PATCH.
export async function updateStateField(
  key: string,
  value: unknown
): Promise<void> {
  const snapshot = get(activeSession);
  if (snapshot === null) {
    syncError.set(new Error("No active session for state update"));
    return;
  }

  // Coalesce: clear any active timer; preserve originalExisted/Value
  // from the first call so revert always restores the pre-first-edit
  // state, not an intermediate optimistic value.
  const existing = pendingFlushes.get(key);
  let originalExisted: boolean;
  let originalValue: unknown;
  if (existing !== undefined) {
    clearTimeout(existing.timer);
    originalExisted = existing.originalExisted;
    originalValue = existing.originalValue;
  } else {
    originalExisted = Object.prototype.hasOwnProperty.call(
      snapshot.state_json,
      key
    );
    originalValue = originalExisted ? snapshot.state_json[key] : undefined;
  }

  // Optimistic local update is immediate so any UI bound to
  // activeSession reflects the typed value without waiting for debounce.
  const optimisticState = { ...snapshot.state_json, [key]: value };
  activeSession.set({ ...snapshot, state_json: optimisticState });

  const timer = setTimeout(() => {
    void flushPendingField(key);
  }, debounceMs);
  pendingFlushes.set(key, { timer, value, originalExisted, originalValue });
}

async function flushPendingField(key: string): Promise<void> {
  const pending = pendingFlushes.get(key);
  if (pending === undefined) return;
  pendingFlushes.delete(key);

  const snapshot = get(activeSession);
  if (snapshot === null) return;

  // Re-derive nextState from the current activeSession so any other
  // key that landed concurrently is preserved on the server.
  const nextState: Record<string, unknown> = {
    ...snapshot.state_json,
    [key]: pending.value,
  };
  bumpInFlight(1);
  try {
    const fresh = await patchIntakeSession(snapshot.id, {
      state_json: nextState,
    });
    activeSession.set(fresh);
    syncError.set(null);
  } catch (err) {
    // Revert just this key. Other keys may have been updated by
    // concurrent successful calls; clobbering them would lose work.
    const current = get(activeSession);
    if (current !== null) {
      const reverted: Record<string, unknown> = { ...current.state_json };
      if (pending.originalExisted) reverted[key] = pending.originalValue;
      else delete reverted[key];
      activeSession.set({ ...current, state_json: reverted });
    }
    syncError.set(err instanceof Error ? err : new Error(String(err)));
  } finally {
    bumpInFlight(-1);
  }
}

// Force flush all pending debounced updates immediately.
// Used before completing the session so final keystrokes aren't lost.
export async function flushAllPending(): Promise<void> {
  const keys = Array.from(pendingFlushes.keys());
  for (const key of keys) {
    const pending = pendingFlushes.get(key);
    if (pending) clearTimeout(pending.timer);
  }
  await Promise.all(keys.map((key) => flushPendingField(key)));
}

// Local-only reset; doesn't touch the server. Cancels pending flushes
// — there's no session to apply them to anymore.
export function clearActiveSession(): void {
  for (const { timer } of pendingFlushes.values()) clearTimeout(timer);
  pendingFlushes.clear();
  activeSession.set(null);
  syncError.set(null);
}

// Phase D Slice D4. Polish the brief via the server-side LLM cascade.
// Flushes pending debounced edits FIRST so the server-side undo-buffer
// snapshot captures the recruiter's most recent hand-edits — without
// the flush, in-flight typing would be lost from `v2_draft_prev` and
// a subsequent restore would jump back further than the recruiter
// expects.
//
// Returns nothing; observe success via `activeSession` (which the
// server-confirmed session replaces) and failure via `syncError`. The
// review chapter renders re-actively — the polished v2_draft populates
// the editors automatically.
export async function polishBrief(): Promise<void> {
  const snapshot = get(activeSession);
  if (snapshot === null) {
    syncError.set(new Error("No active session to polish"));
    return;
  }
  await flushAllPending();
  bumpInFlight(1);
  try {
    const fresh = await polishIntakeSession(snapshot.id);
    activeSession.set(fresh);
    syncError.set(null);
  } catch (err) {
    syncError.set(err instanceof Error ? err : new Error(String(err)));
  } finally {
    bumpInFlight(-1);
  }
}

// Phase D Slice D4. Restore the pre-polish v2_draft from the one-deep
// undo buffer. No `flushAllPending()` needed — restore replaces
// v2_draft wholesale, so any in-flight hand-edits would be clobbered
// by the restore anyway. Same observability shape as polishBrief.
export async function restorePrevDraft(): Promise<void> {
  const snapshot = get(activeSession);
  if (snapshot === null) {
    syncError.set(new Error("No active session to restore"));
    return;
  }
  bumpInFlight(1);
  try {
    const fresh = await restoreIntakeSession(snapshot.id);
    activeSession.set(fresh);
    syncError.set(null);
  } catch (err) {
    syncError.set(err instanceof Error ? err : new Error(String(err)));
  } finally {
    bumpInFlight(-1);
  }
}
