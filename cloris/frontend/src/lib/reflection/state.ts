// Reflection-flow Svelte stores + sync helpers.
//
// Mirrors lib/onboarding/state.ts in spirit (optimistic updates,
// in-flight counter, syncError store) but the reflection lifecycle
// has fewer "free-form text edit" surfaces — the heavy interactions
// are explicit transitions (start_research, commit, discard) rather
// than per-keystroke debounced PATCHes. The one debounced surface is
// the steering textarea on Gate 1.
//
// Polling: while currentSession.current_phase === "researching" we
// poll GET /sessions/{id} on a short interval (default 3s) to detect
// the transition into "awaiting_diff" or back to "planning" on
// research error. Polling is started by the ReflectionFlow component
// and stopped on phase change / unmount.
//
// Concurrency note: the steering PATCH is a single-flight operation —
// the recruiter is staring at the loading state while the planner
// re-runs (5-15s). We don't try to coalesce multiple steering submits
// because the iteration cap is 3 anyway.

import { get, writable } from "svelte/store";

import type { ReflectionSession } from "../types";
import {
  commitReflection as apiCommit,
  createReflectionSession as apiCreate,
  discardReflection as apiDiscard,
  getReflectionSession as apiGet,
  patchReflectionSteering as apiSteer,
  startReflectionResearch as apiStartResearch,
} from "../api";

// The currently-loaded reflection session. Null when none is loaded.
export const activeReflection = writable<ReflectionSession | null>(null);

// Counter of in-flight backend syncs. Counter (not boolean) because
// polling can overlap a steering PATCH or discard.
export const reflectionSyncInFlight = writable<number>(0);

// Last sync error, if any. Cleared on next successful sync.
export const reflectionError = writable<Error | null>(null);

// Polling interval (ms) for the research phase. Mutable so tests can
// shorten it.
let pollIntervalMs = 3000;

export function __setReflectionPollIntervalForTests(ms: number): void {
  pollIntervalMs = ms;
}

let pollTimer: ReturnType<typeof setTimeout> | null = null;

function bumpInFlight(delta: 1 | -1): void {
  reflectionSyncInFlight.update((n) => n + delta);
}

// Boot or resume a reflection. If sessionId is provided, fetch it;
// otherwise create a new one. Returns the loaded session on success.
export async function bootReflection(args: {
  sessionId?: number | null;
  briefId?: string | null;
  sourceRunId?: number | null;
  runDir?: string | null;
}): Promise<ReflectionSession> {
  bumpInFlight(1);
  try {
    if (args.sessionId !== undefined && args.sessionId !== null) {
      const r = await apiGet(args.sessionId);
      activeReflection.set(r.session);
      reflectionError.set(null);
      maybeStartPolling(r.session);
      return r.session;
    }
    if (!args.briefId) {
      throw new Error("bootReflection requires sessionId or briefId");
    }
    const r = await apiCreate({
      brief_id: args.briefId,
      source_run_id: args.sourceRunId ?? null,
      run_dir: args.runDir ?? null,
    });
    activeReflection.set(r.session);
    reflectionError.set(null);
    maybeStartPolling(r.session);
    return r.session;
  } catch (err) {
    reflectionError.set(err instanceof Error ? err : new Error(String(err)));
    throw err;
  } finally {
    bumpInFlight(-1);
  }
}

// Submit a steering note (Gate 1). Returns null when the call no-ops
// (empty note) or when the iteration cap is hit (the API returns 409
// which the caller surfaces as the iteration_capped editorial state).
export async function submitSteering(
  note: string
): Promise<ReflectionSession | null> {
  const session = get(activeReflection);
  if (!session) {
    reflectionError.set(new Error("No active reflection to steer"));
    return null;
  }
  const trimmed = note.trim();
  if (!trimmed) return session; // no-op locally; don't bother the server
  bumpInFlight(1);
  try {
    const r = await apiSteer(session.id, trimmed);
    activeReflection.set(r.session);
    reflectionError.set(null);
    return r.session;
  } catch (err) {
    reflectionError.set(err instanceof Error ? err : new Error(String(err)));
    throw err;
  } finally {
    bumpInFlight(-1);
  }
}

// Approve the plan; transition to researching and start polling.
export async function approvePlan(): Promise<ReflectionSession | null> {
  const session = get(activeReflection);
  if (!session) {
    reflectionError.set(new Error("No active reflection to approve"));
    return null;
  }
  bumpInFlight(1);
  try {
    const r = await apiStartResearch(session.id);
    activeReflection.set(r.session);
    reflectionError.set(null);
    maybeStartPolling(r.session);
    return r.session;
  } catch (err) {
    reflectionError.set(err instanceof Error ? err : new Error(String(err)));
    throw err;
  } finally {
    bumpInFlight(-1);
  }
}

// Commit accepted hunks (Gate 2). Returns the commit response so the
// caller can navigate to the new brief version. On success the session
// transitions to "committed" and polling stops.
export async function commitDiff(
  acceptedHunkIds: string[],
  editedHunks: Record<string, { after: string }> | null = null
): Promise<{
  session: ReflectionSession;
  brief_version_path: string;
  applied_hunks: Array<Record<string, unknown>>;
} | null> {
  const session = get(activeReflection);
  if (!session) {
    reflectionError.set(new Error("No active reflection to commit"));
    return null;
  }
  bumpInFlight(1);
  try {
    const r = await apiCommit(session.id, acceptedHunkIds, editedHunks);
    activeReflection.set(r.session);
    reflectionError.set(null);
    stopPolling();
    return {
      session: r.session,
      brief_version_path: r.brief_version_path,
      applied_hunks: r.applied_hunks,
    };
  } catch (err) {
    reflectionError.set(err instanceof Error ? err : new Error(String(err)));
    throw err;
  } finally {
    bumpInFlight(-1);
  }
}

// Discard the reflection. Brief untouched. Polling stops.
export async function discardCurrent(): Promise<ReflectionSession | null> {
  const session = get(activeReflection);
  if (!session) return null;
  bumpInFlight(1);
  try {
    const r = await apiDiscard(session.id);
    activeReflection.set(r.session);
    reflectionError.set(null);
    stopPolling();
    return r.session;
  } catch (err) {
    reflectionError.set(err instanceof Error ? err : new Error(String(err)));
    throw err;
  } finally {
    bumpInFlight(-1);
  }
}

// Clear local state (does not touch server). Stops polling.
export function clearActiveReflection(): void {
  stopPolling();
  activeReflection.set(null);
  reflectionError.set(null);
}

// --- Polling internals ---------------------------------------------------

function maybeStartPolling(session: ReflectionSession): void {
  if (session.current_phase === "researching") {
    startPolling(session.id);
  } else {
    stopPolling();
  }
}

function startPolling(sessionId: number): void {
  stopPolling();
  const tick = async (): Promise<void> => {
    try {
      const r = await apiGet(sessionId);
      activeReflection.set(r.session);
      reflectionError.set(null);
      if (r.session.current_phase !== "researching") {
        stopPolling();
        return;
      }
    } catch (err) {
      // Soft-fail polling: surface the error in the store but keep
      // polling. A transient blip shouldn't drop us out of the
      // "Cloris is reading" state — when the worker finishes the
      // session row will catch up.
      reflectionError.set(
        err instanceof Error ? err : new Error(String(err))
      );
    }
    pollTimer = setTimeout(() => {
      void tick();
    }, pollIntervalMs);
  };
  pollTimer = setTimeout(() => {
    void tick();
  }, pollIntervalMs);
}

function stopPolling(): void {
  if (pollTimer !== null) {
    clearTimeout(pollTimer);
    pollTimer = null;
  }
}
