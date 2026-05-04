// Onboarding state-store tests.
//
// Covers the per-session lifecycle (start / load / patch / advance /
// updateStateField / clear), the optimistic-update + revert semantics
// on backend error, and the per-key debounce coalescing for
// updateStateField. We mock fetch directly because the api module is
// already covered in onboarding-api.test.ts; here we want end-to-end
// store behavior.

import {
  afterEach,
  beforeEach,
  describe,
  expect,
  it,
  vi,
} from "vitest";
import { get } from "svelte/store";
import {
  __setDebounceMsForTests,
  activeSession,
  advanceStep,
  clearActiveSession,
  loadSession,
  patchActiveSession,
  startNewSession,
  syncError,
  syncInFlight,
  updateStateField,
} from "../lib/onboarding/state";
import type { IntakeSession } from "../lib/types";

const BASE_SESSION: IntakeSession = {
  id: 42,
  brief_id_draft: null,
  role_title: "Tax Associate",
  current_step: "welcome",
  state_json: {},
  started_at: "2026-04-28T12:00:00Z",
  updated_at: "2026-04-28T12:00:00Z",
  completed_at: null,
  archived_at: null,
};

function envelope(session: IntakeSession): Response {
  return new Response(
    JSON.stringify({ slice: "v0-onboarding-slice-1", session }),
    { status: 200, headers: { "content-type": "application/json" } }
  );
}

function failure(status: number, detail: unknown): Response {
  return new Response(JSON.stringify({ detail }), {
    status,
    headers: { "content-type": "application/json" },
  });
}

const originalFetch = globalThis.fetch;

beforeEach(() => {
  globalThis.fetch = vi.fn() as typeof fetch;
  // Reset stores so each spec starts from a clean baseline.
  activeSession.set(null);
  syncError.set(null);
  syncInFlight.set(0);
  // Default to the production debounce; tests that need fake timers
  // override via __setDebounceMsForTests.
  __setDebounceMsForTests(1000);
});

afterEach(() => {
  globalThis.fetch = originalFetch;
  vi.useRealTimers();
  vi.restoreAllMocks();
  clearActiveSession();
});

describe("startNewSession", () => {
  it("creates a session, sets activeSession, and clears syncError", async () => {
    syncError.set(new Error("stale"));
    const fetchMock = globalThis.fetch as unknown as ReturnType<typeof vi.fn>;
    fetchMock.mockResolvedValueOnce(envelope(BASE_SESSION));

    const result = await startNewSession({ role_title: "Tax Associate" });

    expect(result).toEqual(BASE_SESSION);
    expect(get(activeSession)).toEqual(BASE_SESSION);
    expect(get(syncError)).toBeNull();
    expect(get(syncInFlight)).toBe(0);
  });

  it("propagates errors and sets syncError", async () => {
    const fetchMock = globalThis.fetch as unknown as ReturnType<typeof vi.fn>;
    fetchMock.mockResolvedValueOnce(failure(500, "boom"));

    await expect(startNewSession()).rejects.toBeDefined();
    expect(get(activeSession)).toBeNull();
    expect(get(syncError)).not.toBeNull();
    expect(get(syncInFlight)).toBe(0);
  });
});

describe("loadSession", () => {
  it("fetches a session by id and sets activeSession", async () => {
    const fetchMock = globalThis.fetch as unknown as ReturnType<typeof vi.fn>;
    fetchMock.mockResolvedValueOnce(envelope(BASE_SESSION));

    const result = await loadSession(42);

    expect(result).toEqual(BASE_SESSION);
    expect(get(activeSession)).toEqual(BASE_SESSION);
  });

  it("leaves activeSession alone and sets syncError on 404", async () => {
    activeSession.set(BASE_SESSION);
    const fetchMock = globalThis.fetch as unknown as ReturnType<typeof vi.fn>;
    fetchMock.mockResolvedValueOnce(
      failure(404, { error: "intake_session_not_found", id: 99 })
    );

    await expect(loadSession(99)).rejects.toBeDefined();
    expect(get(activeSession)).toEqual(BASE_SESSION);
    expect(get(syncError)).not.toBeNull();
  });
});

describe("patchActiveSession", () => {
  it("applies an optimistic update and replaces with the server response on success", async () => {
    activeSession.set(BASE_SESSION);
    const updated: IntakeSession = {
      ...BASE_SESSION,
      role_title: "Senior Tax Associate",
      updated_at: "2026-04-28T12:05:00Z",
    };
    const fetchMock = globalThis.fetch as unknown as ReturnType<typeof vi.fn>;
    fetchMock.mockResolvedValueOnce(envelope(updated));

    const result = await patchActiveSession({
      role_title: "Senior Tax Associate",
    });

    expect(result).toEqual(updated);
    expect(get(activeSession)).toEqual(updated);
  });

  it("reverts the optimistic update and sets syncError on backend error", async () => {
    activeSession.set(BASE_SESSION);
    const fetchMock = globalThis.fetch as unknown as ReturnType<typeof vi.fn>;
    fetchMock.mockResolvedValueOnce(failure(422, "bad step"));

    const result = await patchActiveSession({ current_step: "role_basics" });

    expect(result).toBeNull();
    expect(get(activeSession)).toEqual(BASE_SESSION); // reverted
    expect(get(syncError)).not.toBeNull();
  });

  it("returns null and sets syncError when there is no active session", async () => {
    const fetchMock = globalThis.fetch as unknown as ReturnType<typeof vi.fn>;

    const result = await patchActiveSession({ role_title: "X" });

    expect(result).toBeNull();
    expect(get(syncError)).not.toBeNull();
    expect(fetchMock).not.toHaveBeenCalled();
  });
});

describe("advanceStep", () => {
  it("delegates to patchActiveSession with the next step", async () => {
    activeSession.set(BASE_SESSION);
    const updated: IntakeSession = {
      ...BASE_SESSION,
      current_step: "role_basics",
    };
    const fetchMock = globalThis.fetch as unknown as ReturnType<typeof vi.fn>;
    fetchMock.mockResolvedValueOnce(envelope(updated));

    await advanceStep("role_basics");

    expect(get(activeSession)).toEqual(updated);
    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(JSON.parse(init.body as string)).toEqual({
      current_step: "role_basics",
    });
  });
});

describe("updateStateField — debounce + coalescing", () => {
  it("applies the optimistic local update immediately", async () => {
    activeSession.set(BASE_SESSION);
    vi.useFakeTimers();
    __setDebounceMsForTests(50);
    const fetchMock = globalThis.fetch as unknown as ReturnType<typeof vi.fn>;
    fetchMock.mockResolvedValue(
      envelope({
        ...BASE_SESSION,
        state_json: { day_to_day: "writes Forms 1120" },
      })
    );

    await updateStateField("day_to_day", "writes Forms 1120");

    // Local update is immediate, before the debounce fires.
    expect(get(activeSession)?.state_json).toEqual({
      day_to_day: "writes Forms 1120",
    });
    // Backend has not been called yet.
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("coalesces rapid same-key updates into a single PATCH carrying the latest value", async () => {
    activeSession.set(BASE_SESSION);
    vi.useFakeTimers();
    __setDebounceMsForTests(50);
    const fetchMock = globalThis.fetch as unknown as ReturnType<typeof vi.fn>;
    fetchMock.mockResolvedValue(
      envelope({
        ...BASE_SESSION,
        state_json: { day_to_day: "final value" },
      })
    );

    await updateStateField("day_to_day", "v1");
    await updateStateField("day_to_day", "v2");
    await updateStateField("day_to_day", "final value");

    // Optimistic local state shows the latest typed value.
    expect(get(activeSession)?.state_json).toEqual({
      day_to_day: "final value",
    });
    expect(fetchMock).not.toHaveBeenCalled();

    await vi.advanceTimersByTimeAsync(60);

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(JSON.parse(init.body as string)).toEqual({
      state_json: { day_to_day: "final value" },
    });
  });

  it("does not coalesce updates on different keys", async () => {
    activeSession.set(BASE_SESSION);
    vi.useFakeTimers();
    __setDebounceMsForTests(50);
    const fetchMock = globalThis.fetch as unknown as ReturnType<typeof vi.fn>;
    fetchMock.mockImplementation(async (_input, init) => {
      const body = JSON.parse((init?.body as string) ?? "{}");
      const state_json = (body.state_json ?? {}) as Record<string, unknown>;
      return envelope({
        ...BASE_SESSION,
        state_json,
      });
    });

    await updateStateField("a", 1);
    await updateStateField("b", 2);

    await vi.advanceTimersByTimeAsync(60);

    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("reverts the optimistic update when the backend PATCH fails", async () => {
    activeSession.set(BASE_SESSION);
    vi.useFakeTimers();
    __setDebounceMsForTests(50);
    const fetchMock = globalThis.fetch as unknown as ReturnType<typeof vi.fn>;
    fetchMock.mockResolvedValueOnce(failure(422, "bad"));

    await updateStateField("day_to_day", "writes Forms 1120");

    expect(get(activeSession)?.state_json).toEqual({
      day_to_day: "writes Forms 1120",
    });

    await vi.advanceTimersByTimeAsync(60);

    // Reverted: the new key should be removed since it didn't exist
    // pre-edit.
    expect(get(activeSession)?.state_json).toEqual({});
    expect(get(syncError)).not.toBeNull();
  });

  it("reverts to the pre-first-edit value (not an intermediate optimistic value) on failure", async () => {
    const seed: IntakeSession = {
      ...BASE_SESSION,
      state_json: { day_to_day: "original" },
    };
    activeSession.set(seed);
    vi.useFakeTimers();
    __setDebounceMsForTests(50);
    const fetchMock = globalThis.fetch as unknown as ReturnType<typeof vi.fn>;
    fetchMock.mockResolvedValueOnce(failure(422, "bad"));

    await updateStateField("day_to_day", "intermediate");
    await updateStateField("day_to_day", "final");

    await vi.advanceTimersByTimeAsync(60);

    expect(get(activeSession)?.state_json).toEqual({ day_to_day: "original" });
  });

  it("does nothing and sets syncError when there is no active session", async () => {
    const fetchMock = globalThis.fetch as unknown as ReturnType<typeof vi.fn>;

    await updateStateField("k", "v");

    expect(fetchMock).not.toHaveBeenCalled();
    expect(get(syncError)).not.toBeNull();
  });
});

describe("clearActiveSession", () => {
  it("resets activeSession and clears syncError without calling the backend", () => {
    activeSession.set(BASE_SESSION);
    syncError.set(new Error("stale"));
    const fetchMock = globalThis.fetch as unknown as ReturnType<typeof vi.fn>;

    clearActiveSession();

    expect(get(activeSession)).toBeNull();
    expect(get(syncError)).toBeNull();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("cancels pending debounced flushes", async () => {
    activeSession.set(BASE_SESSION);
    vi.useFakeTimers();
    __setDebounceMsForTests(50);
    const fetchMock = globalThis.fetch as unknown as ReturnType<typeof vi.fn>;

    await updateStateField("day_to_day", "queued");
    clearActiveSession();
    await vi.advanceTimersByTimeAsync(100);

    expect(fetchMock).not.toHaveBeenCalled();
  });
});
