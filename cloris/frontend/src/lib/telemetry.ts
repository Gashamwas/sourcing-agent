// Cloris frontend telemetry — scaffolding (P1.12).
//
// Fire-and-forget emitter. Component-level emission is wired in a follow-up
// task; this module only owns the API surface, the PII sanitizer, and the
// in-memory ring buffer used for tests and future debugging.
//
// Destination policy (v1):
//   - In dev (Vite's `import.meta.env.DEV` is true): console.log + ring buffer.
//   - In prod: ring buffer only; no console output.
//
// PII policy:
//   - Brief paths can encode customer-identifying info → hashed before emit.
//   - State keys are non-PII directory slugs → pass through unchanged.
//   - Error messages are NEVER emitted; only the typed `error_code` or
//     `error.name` makes it into the wire shape.
//
// All callers can rely on `emit` never throwing — its body is wrapped in
// try/catch so internal failures (e.g., console issues, JSON edge cases on
// future destinations) cannot propagate to UI code.
//
// Wire format intentionally matches the future hosted destination contract so
// switching from console.log → HTTP POST is a v2 decision with zero call-site
// changes.

import type { SourceKey } from "./sources";

// Discriminated union of all event types. Add new variants as new hooks are
// wired in. Keep payload fields PII-clean (state_key OK; brief_path_hash OK;
// raw paths NOT OK; error.message NOT OK).
export type TelemetryEvent =
  | { type: "surface_viewed"; surface: string }
  | { type: "launch_attempted"; source: SourceKey; brief_path_hash: string }
  | { type: "launch_succeeded"; source: SourceKey; brief_path_hash: string; pid: number }
  | { type: "launch_failed"; source: SourceKey; brief_path_hash: string; error_code: string }
  | { type: "resume_attempted"; source: SourceKey; brief_path_hash: string }
  | { type: "resume_succeeded"; source: SourceKey; brief_path_hash: string; pid: number }
  | { type: "resume_failed"; source: SourceKey; brief_path_hash: string; error_code: string }
  | { type: "stop_attempted"; source: SourceKey; state_key: string }
  | { type: "stop_succeeded"; source: SourceKey; state_key: string; worker_state: string }
  | { type: "stop_failed"; source: SourceKey; state_key: string; error_code: string }
  | { type: "row_drilled_in"; source: SourceKey; state_key: string }
  | { type: "candidate_review_marked"; review_status: string; surface_type: string }
  | { type: "ui_error_caught"; component: string; error_type: string }
  | { type: "verb_tile_clicked"; verb: VerbId }
  | { type: "verb_tile_disabled_clicked"; verb: VerbId };

export type VerbId =
  | "write_brief"
  | "start_search"
  | "read_report"
  | "learn_market";

// Ring-buffer cap. Bounded so a runaway emit loop can't OOM the tab. 100 is
// plenty for tests + manual debugging; production destinations (when wired)
// will drain, not bound.
const RING_BUFFER_MAX = 100;

const ringBuffer: TelemetryEvent[] = [];

function pushToBuffer(event: TelemetryEvent): void {
  ringBuffer.push(event);
  if (ringBuffer.length > RING_BUFFER_MAX) {
    // Drop from the front: keep the most recent RING_BUFFER_MAX events.
    ringBuffer.splice(0, ringBuffer.length - RING_BUFFER_MAX);
  }
}

// FNV-1a 32-bit hash → 8-char lowercase hex. NOT cryptographic; the goal is
// "two distinct brief paths get distinct identifiers without leaking the
// path itself", not secrecy. Inline implementation; zero deps.
//
// Reference: https://en.wikipedia.org/wiki/Fowler%E2%80%93Noll%E2%80%93Vo_hash_function
export function hashBriefPath(path: string): string {
  // FNV-1a 32-bit offset basis.
  let hash = 0x811c9dc5;
  for (let i = 0; i < path.length; i++) {
    hash ^= path.charCodeAt(i) & 0xff;
    // FNV prime: 16777619. Use Math.imul for 32-bit overflow semantics.
    hash = Math.imul(hash, 0x01000193);
  }
  // Force unsigned 32-bit, then pad to 8 hex chars.
  return (hash >>> 0).toString(16).padStart(8, "0");
}

// Fire-and-forget emit. Internal errors are swallowed — telemetry must
// never break the UI.
export function emit(event: TelemetryEvent): void {
  try {
    pushToBuffer(event);

    // import.meta.env.DEV is statically replaced by Vite at build time.
    // In Vitest it resolves to `true` (vitest sets DEV=true unless overridden).
    if (!import.meta.env.DEV) {
      return;
    }

    // Dev console output. We log the structured object so DevTools can
    // expand it; this is intentionally NOT a JSON.stringify — let the
    // browser handle cyclic refs gracefully.
    // eslint-disable-next-line no-console
    console.log("[cloris-telemetry]", event);
  } catch {
    // Swallow. Telemetry MUST NOT propagate errors to callers.
  }
}

// Test helpers. Underscore prefix marks them as non-production API.
export function _testReadEvents(): readonly TelemetryEvent[] {
  return ringBuffer.slice();
}

export function _testClearEvents(): void {
  ringBuffer.length = 0;
}
