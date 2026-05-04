// Vitest coverage for the telemetry scaffolding (P1.12).
//
// What we're guarding:
//   - The discriminated union compiles for every event variant the audit
//     requires (compile-time check via `satisfies`).
//   - `emit` is fire-and-forget: never throws on any valid variant, and
//     never throws on weird payloads (cyclic refs, etc.).
//   - PII sanitization at the emit boundary: ui_error_caught events buffer
//     only `component` + `error_type` (NEVER an `error.message` field).
//   - `hashBriefPath` is deterministic, 8-char hex, and collision-free on
//     a small distinct-input sample.
//   - Ring buffer caps at 100, drops the oldest events.
//   - Dev-mode toggling: console.log fires when DEV=true; no console output
//     when DEV=false (but the buffer still records).
//
// `_testReadEvents` / `_testClearEvents` are the test-only drain helpers.

import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import {
  emit,
  hashBriefPath,
  _testClearEvents,
  _testReadEvents,
  type TelemetryEvent,
} from "../lib/telemetry";

beforeEach(() => {
  _testClearEvents();
});

afterEach(() => {
  vi.unstubAllEnvs();
  vi.restoreAllMocks();
});

describe("TelemetryEvent — discriminated union compiles for every variant", () => {
  // The whole point of this block is the type system. Each `satisfies
  // TelemetryEvent` clause is the actual assertion: if a variant is dropped
  // or its shape changes, the file fails to typecheck (svelte-check covers
  // this in `pnpm check`). The runtime `expect` below is just a smoke test.
  it("every variant compiles via `satisfies`", () => {
    const surfaceViewed = { type: "surface_viewed", surface: "ledger" } satisfies TelemetryEvent;
    const launchAttempted = {
      type: "launch_attempted",
      source: "linkedin",
      brief_path_hash: "deadbeef",
    } satisfies TelemetryEvent;
    const launchSucceeded = {
      type: "launch_succeeded",
      source: "linkedin",
      brief_path_hash: "deadbeef",
      pid: 1234,
    } satisfies TelemetryEvent;
    const launchFailed = {
      type: "launch_failed",
      source: "linkedin",
      brief_path_hash: "deadbeef",
      error_code: "WORKER_SPAWN_FAILED",
    } satisfies TelemetryEvent;
    const resumeAttempted = {
      type: "resume_attempted",
      source: "github",
      brief_path_hash: "cafebabe",
    } satisfies TelemetryEvent;
    const resumeSucceeded = {
      type: "resume_succeeded",
      source: "github",
      brief_path_hash: "cafebabe",
      pid: 5678,
    } satisfies TelemetryEvent;
    const resumeFailed = {
      type: "resume_failed",
      source: "github",
      brief_path_hash: "cafebabe",
      error_code: "RESUME_REFUSED",
    } satisfies TelemetryEvent;
    const stopAttempted = {
      type: "stop_attempted",
      source: "linkedin",
      state_key: "linkedin-foo",
    } satisfies TelemetryEvent;
    const stopSucceeded = {
      type: "stop_succeeded",
      source: "linkedin",
      state_key: "linkedin-foo",
      worker_state: "stopping",
    } satisfies TelemetryEvent;
    const stopFailed = {
      type: "stop_failed",
      source: "linkedin",
      state_key: "linkedin-foo",
      error_code: "STOP_NOT_PERMITTED",
    } satisfies TelemetryEvent;
    const rowDrilledIn = {
      type: "row_drilled_in",
      source: "github",
      state_key: "github-bar",
    } satisfies TelemetryEvent;
    const candidateReviewMarked = {
      type: "candidate_review_marked",
      review_status: "approved",
      surface_type: "run-review",
    } satisfies TelemetryEvent;
    const uiErrorCaught = {
      type: "ui_error_caught",
      component: "LaunchForm",
      error_type: "TypeError",
    } satisfies TelemetryEvent;

    // Smoke: each value is a defined object. Real assertion is the
    // `satisfies` constraint compiling at all.
    for (const ev of [
      surfaceViewed,
      launchAttempted,
      launchSucceeded,
      launchFailed,
      resumeAttempted,
      resumeSucceeded,
      resumeFailed,
      stopAttempted,
      stopSucceeded,
      stopFailed,
      rowDrilledIn,
      candidateReviewMarked,
      uiErrorCaught,
    ]) {
      expect(ev).toBeDefined();
    }
  });
});

describe("emit — fire-and-forget contract", () => {
  it("does not throw on any valid event variant", () => {
    const variants: TelemetryEvent[] = [
      { type: "surface_viewed", surface: "ledger" },
      { type: "launch_attempted", source: "linkedin", brief_path_hash: "abcd1234" },
      { type: "launch_succeeded", source: "linkedin", brief_path_hash: "abcd1234", pid: 99 },
      { type: "launch_failed", source: "linkedin", brief_path_hash: "abcd1234", error_code: "X" },
      { type: "resume_attempted", source: "github", brief_path_hash: "efef" },
      { type: "resume_succeeded", source: "github", brief_path_hash: "efef", pid: 11 },
      { type: "resume_failed", source: "github", brief_path_hash: "efef", error_code: "Y" },
      { type: "stop_attempted", source: "linkedin", state_key: "k" },
      { type: "stop_succeeded", source: "linkedin", state_key: "k", worker_state: "stopping" },
      { type: "stop_failed", source: "linkedin", state_key: "k", error_code: "Z" },
      { type: "row_drilled_in", source: "github", state_key: "k" },
      { type: "candidate_review_marked", review_status: "approved", surface_type: "rr" },
      { type: "ui_error_caught", component: "X", error_type: "TypeError" },
    ];

    for (const ev of variants) {
      expect(() => emit(ev)).not.toThrow();
    }
  });

  it("does not throw when the event object contains a cyclic reference", () => {
    // Force a JSON.stringify edge case. Even if a future destination tries
    // to serialize the event, our emit body must swallow the failure.
    type Cyclic = TelemetryEvent & { _self?: unknown };
    const cyclic: Cyclic = {
      type: "surface_viewed",
      surface: "ledger",
    };
    cyclic._self = cyclic;

    expect(() => emit(cyclic as TelemetryEvent)).not.toThrow();
  });

  it("swallows internal errors when console.log itself throws", () => {
    // Force the dev-mode console path AND make console.log throw. emit
    // must still not propagate.
    vi.stubEnv("DEV", true);
    const logSpy = vi.spyOn(console, "log").mockImplementation(() => {
      throw new Error("console blew up");
    });

    expect(() =>
      emit({ type: "surface_viewed", surface: "ledger" }),
    ).not.toThrow();
    expect(logSpy).toHaveBeenCalled();
  });
});

describe("hashBriefPath", () => {
  it("returns an 8-char lowercase hex string", () => {
    const hash = hashBriefPath("config/brief-foo.json");
    expect(hash).toMatch(/^[0-9a-f]{8}$/);
    expect(hash.length).toBe(8);
  });

  it("is deterministic — same input always produces same output", () => {
    const a = hashBriefPath("config/brief-foo.json");
    const b = hashBriefPath("config/brief-foo.json");
    const c = hashBriefPath("config/brief-foo.json");
    expect(a).toBe(b);
    expect(b).toBe(c);
  });

  it("produces different outputs for different inputs (collision check)", () => {
    // Small distinct-input sample. FNV-1a 32-bit on 20 short, distinct
    // strings should yield 20 distinct hashes; if collisions show up at
    // this scale, something is wrong with the hash implementation.
    const inputs = [
      "config/brief-a.json",
      "config/brief-b.json",
      "config/brief-c.json",
      "config/brief-foo.json",
      "config/brief-bar.json",
      "config/brief-baz.json",
      "config/sub/dir/x.json",
      "config/sub/dir/y.json",
      "/absolute/path/to/brief.json",
      "/absolute/path/to/other.json",
      "brief.json",
      "BRIEF.json",
      "brief1.json",
      "brief2.json",
      "brief10.json",
      "brief-recruiter-1.json",
      "brief-recruiter-2.json",
      "linkedin-2025-01.json",
      "github-2025-01.json",
      "github-2025-02.json",
    ];
    const hashes = inputs.map(hashBriefPath);
    expect(new Set(hashes).size).toBe(inputs.length);
  });

  it("handles the empty string deterministically", () => {
    expect(hashBriefPath("")).toMatch(/^[0-9a-f]{8}$/);
    expect(hashBriefPath("")).toBe(hashBriefPath(""));
  });
});

describe("ring buffer & test helpers", () => {
  it("_testReadEvents returns empty after _testClearEvents", () => {
    emit({ type: "surface_viewed", surface: "ledger" });
    _testClearEvents();
    expect(_testReadEvents()).toEqual([]);
  });

  it("preserves emit order: emit(a) then emit(b) → [a, b]", () => {
    const a: TelemetryEvent = { type: "surface_viewed", surface: "ledger" };
    const b: TelemetryEvent = {
      type: "stop_attempted",
      source: "linkedin",
      state_key: "k",
    };
    emit(a);
    emit(b);
    expect(_testReadEvents()).toEqual([a, b]);
  });

  it("caps at 100 events: emitting 105 keeps the LAST 100", () => {
    for (let i = 0; i < 105; i++) {
      emit({ type: "surface_viewed", surface: `s-${i}` });
    }
    const buffered = _testReadEvents();
    expect(buffered.length).toBe(100);

    // First buffered event should be s-5 (events 0..4 were dropped).
    const first = buffered[0];
    expect(first?.type).toBe("surface_viewed");
    if (first?.type === "surface_viewed") {
      expect(first.surface).toBe("s-5");
    }

    // Last buffered event should be s-104.
    const last = buffered[buffered.length - 1];
    expect(last?.type).toBe("surface_viewed");
    if (last?.type === "surface_viewed") {
      expect(last.surface).toBe("s-104");
    }
  });

  it("returns a read-only snapshot — mutating the result does not poison the buffer", () => {
    emit({ type: "surface_viewed", surface: "ledger" });
    const snapshot = _testReadEvents();
    // The cast is intentional — we want to prove that even a buggy caller
    // who forces a mutation cannot corrupt the internal buffer.
    (snapshot as TelemetryEvent[]).pop();

    expect(_testReadEvents().length).toBe(1);
  });
});

describe("PII sanitization — ui_error_caught events", () => {
  it("buffered event has only component + error_type (no error.message field)", () => {
    emit({
      type: "ui_error_caught",
      component: "LaunchForm",
      error_type: "TypeError",
    });

    const events = _testReadEvents();
    expect(events.length).toBe(1);

    const ev = events[0];
    expect(ev).toBeDefined();
    if (ev?.type !== "ui_error_caught") {
      throw new Error("expected ui_error_caught variant");
    }

    // Required fields present.
    expect(ev.component).toBe("LaunchForm");
    expect(ev.error_type).toBe("TypeError");

    // PII-bearing fields explicitly absent. The wire format is locked: any
    // future contributor adding `message` / `stack` / `error` to the
    // payload trips this guard.
    const keys = Object.keys(ev);
    expect(keys).toEqual(expect.arrayContaining(["type", "component", "error_type"]));
    expect(keys).not.toContain("message");
    expect(keys).not.toContain("stack");
    expect(keys).not.toContain("error");
  });
});

describe("destination toggling — DEV vs prod", () => {
  it("logs to console when import.meta.env.DEV is true", () => {
    vi.stubEnv("DEV", true);
    const logSpy = vi.spyOn(console, "log").mockImplementation(() => {});

    emit({ type: "surface_viewed", surface: "ledger" });

    expect(logSpy).toHaveBeenCalledTimes(1);
    expect(logSpy).toHaveBeenCalledWith("[cloris-telemetry]", {
      type: "surface_viewed",
      surface: "ledger",
    });
  });

  it("does NOT log to console in prod, but still buffers the event", () => {
    vi.stubEnv("DEV", false);
    const logSpy = vi.spyOn(console, "log").mockImplementation(() => {});

    emit({ type: "surface_viewed", surface: "ledger" });

    expect(logSpy).not.toHaveBeenCalled();

    // Buffer is the dev-and-prod fallback; events MUST land in it
    // regardless of console behavior.
    expect(_testReadEvents()).toEqual([
      { type: "surface_viewed", surface: "ledger" },
    ]);
  });
});
