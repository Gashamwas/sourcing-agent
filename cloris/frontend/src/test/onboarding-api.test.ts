// Onboarding API client tests (Slice 1B contract).
//
// We mock globalThis.fetch directly; the request<T> helper inside
// lib/onboarding/api.ts is small and deterministic, and the goal is
// (a) exercise each function on the happy path and verify the request
// shape (method, url, body), and (b) cover the ApiError surfaces:
// non-2xx with a {detail} envelope, non-2xx without one, network
// failure, and invalid JSON.

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../lib/api";
import {
  createIntakeSession,
  deleteIntakeSession,
  getIntakeSession,
  listIntakeSessions,
  patchIntakeSession,
} from "../lib/onboarding/api";
import type { IntakeSession } from "../lib/types";

const SESSION: IntakeSession = {
  id: 7,
  brief_id_draft: null,
  role_title: "Financial Analyst",
  current_step: "welcome",
  state_json: {},
  started_at: "2026-04-28T12:00:00Z",
  updated_at: "2026-04-28T12:00:00Z",
  completed_at: null,
  archived_at: null,
};

function ok(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

function fail(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

const originalFetch = globalThis.fetch;

beforeEach(() => {
  globalThis.fetch = vi.fn() as typeof fetch;
});

afterEach(() => {
  globalThis.fetch = originalFetch;
  vi.restoreAllMocks();
});

describe("createIntakeSession", () => {
  it("POSTs to /api/intake/sessions with the role_title and unwraps the envelope", async () => {
    const fetchMock = globalThis.fetch as unknown as ReturnType<typeof vi.fn>;
    fetchMock.mockResolvedValueOnce(
      ok({ slice: "v0-onboarding-slice-1", session: SESSION }, 201)
    );

    const result = await createIntakeSession({ role_title: "Financial Analyst" });

    expect(result).toEqual(SESSION);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("/api/intake/sessions");
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body as string)).toEqual({
      role_title: "Financial Analyst",
    });
  });

  it("omits role_title from the body when not provided", async () => {
    const fetchMock = globalThis.fetch as unknown as ReturnType<typeof vi.fn>;
    fetchMock.mockResolvedValueOnce(
      ok({ slice: "v0-onboarding-slice-1", session: SESSION }, 201)
    );

    await createIntakeSession();

    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(JSON.parse(init.body as string)).toEqual({});
  });

  it("throws ApiError with the detail surfaced on non-2xx", async () => {
    const fetchMock = globalThis.fetch as unknown as ReturnType<typeof vi.fn>;
    fetchMock.mockResolvedValueOnce(fail(422, { detail: "bad" }));

    await expect(createIntakeSession()).rejects.toBeInstanceOf(ApiError);
  });
});

describe("listIntakeSessions", () => {
  it("GETs /api/intake/sessions and unwraps the sessions array", async () => {
    const fetchMock = globalThis.fetch as unknown as ReturnType<typeof vi.fn>;
    fetchMock.mockResolvedValueOnce(
      ok({ slice: "v0-onboarding-slice-1", sessions: [SESSION] })
    );

    const result = await listIntakeSessions();

    expect(result).toEqual([SESSION]);
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("/api/intake/sessions");
    expect(init.method).toBe("GET");
  });

  it("returns an empty array when the server has no active sessions", async () => {
    const fetchMock = globalThis.fetch as unknown as ReturnType<typeof vi.fn>;
    fetchMock.mockResolvedValueOnce(
      ok({ slice: "v0-onboarding-slice-1", sessions: [] })
    );

    const result = await listIntakeSessions();
    expect(result).toEqual([]);
  });

  it("propagates a network error as ApiError(0, ...)", async () => {
    const fetchMock = globalThis.fetch as unknown as ReturnType<typeof vi.fn>;
    fetchMock.mockRejectedValueOnce(new Error("ECONNREFUSED"));

    try {
      await listIntakeSessions();
      throw new Error("should have thrown");
    } catch (err) {
      expect(err).toBeInstanceOf(ApiError);
      expect((err as ApiError).status).toBe(0);
    }
  });
});

describe("getIntakeSession", () => {
  it("GETs /api/intake/sessions/{id} with the id encoded", async () => {
    const fetchMock = globalThis.fetch as unknown as ReturnType<typeof vi.fn>;
    fetchMock.mockResolvedValueOnce(
      ok({ slice: "v0-onboarding-slice-1", session: SESSION })
    );

    const result = await getIntakeSession(7);

    expect(result).toEqual(SESSION);
    const [url] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("/api/intake/sessions/7");
  });

  it("throws ApiError(404) when the session does not exist", async () => {
    const fetchMock = globalThis.fetch as unknown as ReturnType<typeof vi.fn>;
    fetchMock.mockResolvedValueOnce(
      fail(404, { detail: { error: "intake_session_not_found", id: 99 } })
    );

    try {
      await getIntakeSession(99);
      throw new Error("should have thrown");
    } catch (err) {
      expect(err).toBeInstanceOf(ApiError);
      expect((err as ApiError).status).toBe(404);
    }
  });
});

describe("patchIntakeSession", () => {
  it("PATCHes /api/intake/sessions/{id} with the patch body and unwraps the envelope", async () => {
    const updated: IntakeSession = { ...SESSION, current_step: "role_basics" };
    const fetchMock = globalThis.fetch as unknown as ReturnType<typeof vi.fn>;
    fetchMock.mockResolvedValueOnce(
      ok({ slice: "v0-onboarding-slice-1", session: updated })
    );

    const result = await patchIntakeSession(7, { current_step: "role_basics" });

    expect(result).toEqual(updated);
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("/api/intake/sessions/7");
    expect(init.method).toBe("PATCH");
    expect(JSON.parse(init.body as string)).toEqual({
      current_step: "role_basics",
    });
  });

  it("forwards an empty patch body unchanged", async () => {
    const fetchMock = globalThis.fetch as unknown as ReturnType<typeof vi.fn>;
    fetchMock.mockResolvedValueOnce(
      ok({ slice: "v0-onboarding-slice-1", session: SESSION })
    );

    await patchIntakeSession(7, {});

    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(JSON.parse(init.body as string)).toEqual({});
  });

  it("throws ApiError on validation failure", async () => {
    const fetchMock = globalThis.fetch as unknown as ReturnType<typeof vi.fn>;
    fetchMock.mockResolvedValueOnce(fail(422, { detail: "bad step" }));

    try {
      await patchIntakeSession(7, { current_step: "welcome" });
      throw new Error("should have thrown");
    } catch (err) {
      expect(err).toBeInstanceOf(ApiError);
      expect((err as ApiError).status).toBe(422);
    }
  });
});

describe("deleteIntakeSession", () => {
  it("DELETEs /api/intake/sessions/{id} and returns the deleted flag", async () => {
    const fetchMock = globalThis.fetch as unknown as ReturnType<typeof vi.fn>;
    fetchMock.mockResolvedValueOnce(
      ok({ slice: "v0-onboarding-slice-1", deleted: true, id: 7 })
    );

    const result = await deleteIntakeSession(7);

    expect(result).toBe(true);
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("/api/intake/sessions/7");
    expect(init.method).toBe("DELETE");
  });

  it("throws ApiError(404) when the session is missing", async () => {
    const fetchMock = globalThis.fetch as unknown as ReturnType<typeof vi.fn>;
    fetchMock.mockResolvedValueOnce(
      fail(404, { detail: { error: "intake_session_not_found", id: 7 } })
    );

    try {
      await deleteIntakeSession(7);
      throw new Error("should have thrown");
    } catch (err) {
      expect(err).toBeInstanceOf(ApiError);
      expect((err as ApiError).status).toBe(404);
    }
  });
});
