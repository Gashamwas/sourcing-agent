// Phase F Slice F1 — frontend launch helper.
//
// Pins the wire shape of `launchForSource(source, briefId, mode, force)`
// so F5's module picker (which fires N parallel launches) can rely on
// a stable contract. The browser fetch is stubbed so we assert the
// URL + body shape directly; integration with the live backend is
// covered by the Python tests at tests/test_launch_endpoint_generic.py.

import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";

import { launchForSource, ApiError } from "../lib/api";

describe("launchForSource — wire contract", () => {
  let originalFetch: typeof fetch;

  beforeEach(() => {
    originalFetch = globalThis.fetch;
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  function fakeOk(body: Record<string, unknown>): typeof fetch {
    return vi.fn(async () => {
      return new Response(JSON.stringify(body), {
        status: 201,
        headers: { "content-type": "application/json" }
      });
    }) as unknown as typeof fetch;
  }

  it("posts to /api/launch/<source> with brief_id + mode + force in body", async () => {
    const stub = fakeOk({
      slice: "v0-shell-slice-3",
      source: "github",
      input_mode: "concurrent",
      mode: "fresh",
      pid: 99,
      state_dir: "/tmp/state/github/abc",
      worker_json_path: "/tmp/state/github/abc/worker.json"
    });
    globalThis.fetch = stub;

    const result = await launchForSource("github", "abc-id", "fresh", false);

    expect(stub).toHaveBeenCalledOnce();
    const [url, init] = (stub as unknown as ReturnType<typeof vi.fn>).mock
      .calls[0];
    expect(url).toBe("/api/launch/github");
    expect((init as RequestInit).method).toBe("POST");
    const body = JSON.parse((init as RequestInit).body as string);
    expect(body).toEqual({ brief_id: "abc-id", mode: "fresh", force: false });

    expect(result.source).toBe("github");
    expect(result.mode).toBe("fresh");
    expect(result.pid).toBe(99);
  });

  it("encodes the source path segment", async () => {
    globalThis.fetch = fakeOk({
      slice: "v0-shell-slice-3",
      source: "linkedin",
      input_mode: "concurrent",
      mode: "resume",
      pid: 1,
      state_dir: "x",
      worker_json_path: "y"
    });
    await launchForSource("linkedin", "id", "resume", true);

    const [url] = (
      globalThis.fetch as unknown as ReturnType<typeof vi.fn>
    ).mock.calls[0];
    expect(url).toBe("/api/launch/linkedin");
  });

  it("surfaces ApiError on 422 unknown_source", async () => {
    globalThis.fetch = vi.fn(
      async () =>
        new Response(
          JSON.stringify({
            detail: {
              error: "unknown_source",
              source: "myspace",
              allowed: ["github", "linkedin"]
            }
          }),
          { status: 422, headers: { "content-type": "application/json" } }
        )
    ) as unknown as typeof fetch;

    await expect(
      launchForSource(
        "myspace" as unknown as Parameters<typeof launchForSource>[0],
        "id"
      )
    ).rejects.toBeInstanceOf(ApiError);
  });
});
