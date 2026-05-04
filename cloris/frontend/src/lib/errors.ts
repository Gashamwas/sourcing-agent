// Plain-language error copy for Cloris API failures.
//
// The backend returns structured error codes inside `detail.error`. The
// product UI must render them in product language — no PIDs, no
// "backend reports", no raw code strings.
//
// Editorial register (R18 / Plan Finding 20c): errors drop character
// voice. Every entry below is plain operational copy. Cloris-as-system
// noun is acceptable ("Cloris is offline"); Cloris-as-narrator ("I
// couldn't find that") is not. Where a clear next move exists, the
// entry names it — error copy's job is to tell the recruiter what to do
// next, not to narrate what failed.
//
// Reflection codes (`reflection_*`, `reflection_plan_failed`,
// `reflection_commit_failed`) are explicitly out of scope for this
// pass; they were addressed in the prior reflection-error work and the
// surface-level guidance lives in `lib/reflection/copy.ts`. Touching
// them here would step on that contract.

import { ApiError } from "./api";

// Translation table for the error codes the existing routes can return.
// Keep this list aligned with the codes raised by `cloris/api.py` and
// `cloris/worker.py`. Extend it as new codes appear.
const ERROR_COPY: Record<string, string> = {
  brief_path_not_found: "That brief is gone — or the link is stale.",
  worker_already_running: "That card is already being worked.",
  no_pending_work: "Nothing pending to pull.",
  state_dir_not_found: "That card is gone — or the link is stale.",
  invalid_brief_path: "That brief path doesn't look right.",
  // Intake / brief-authoring (Phase D Slice D3 + D4).
  intake_session_not_found: "That draft is gone — or the link is stale.",
  invalid_v2_brief: "The brief isn't quite ready to file.",
  brief_already_exists:
    "A brief with this role title already exists. Pick a different title or edit the existing brief from the library.",
  brief_write_failed: "Couldn't save that brief. Try again in a moment.",
  brief_id_computation_failed:
    "The brief was saved, but its id couldn't be pinned. Refresh the brief library to find it.",
  intake_session_gone_after_complete:
    "The brief was saved, but the draft was cleared while the save was in flight. Refresh the brief library.",
  // The Reflection — HITL market intelligence. These reflection-scoped
  // entries are intentionally untouched by Plan Finding 20; surface-
  // level guidance lives in lib/reflection/copy.ts.
  reflection_session_not_found:
    "I couldn't find that reflection — it may have been discarded.",
  reflection_session_gone:
    "That reflection finished while you were away.",
  reflection_already_active:
    "A reflection is already in flight for this brief.",
  reflection_phase_locked:
    "That action no longer applies — the reflection moved to a new gate.",
  reflection_no_evidence:
    "There isn't enough run evidence yet to reflect on.",
  brief_id_not_found: "That brief is gone — or the link is stale.",
  reflection_steering_capped:
    "You've refined this plan three times. Trust it or discard.",
  reflection_plan_failed: "I lost my train of thought — start over.",
  reflection_commit_no_hunks:
    "Approve at least one change before filing the brief.",
  reflection_commit_failed:
    "I couldn't file the new brief. The previous brief is still in place.",
};

// Returns the human-readable copy when no `ERROR_COPY` entry matches.
// Distinguishes the two failure modes the fallback actually catches so
// the recruiter has a recovery affordance rather than the previous
// content-free "Something went wrong":
//   - status === 0 → network blip (api.ts wraps fetch failures here)
//   - status >= 500 → server-side error
//   - everything else → generic but with a concrete next move
function genericFallback(err: unknown): string {
  if (err instanceof ApiError) {
    if (err.status === 0) {
      return "Cloris is offline. Check your connection and try again.";
    }
    if (err.status >= 500) {
      return "Something failed on Cloris's side. Try again in a moment.";
    }
  }
  return "Something didn't go through. Try again in a moment.";
}

// Translate a thrown error into a single-sentence product string.
// `actionLabel` is the verb the user just attempted (e.g. "File card",
// "Pull & Resume", "Stop"). The label is used as the leading noun in the
// sentence so the user knows which action failed.
export function describeApiError(
  err: unknown,
  actionLabel: string
): string {
  if (err instanceof ApiError) {
    // Network blip — api.ts wraps fetch failures as ApiError(0, ...,
    // synthesized message). Short-circuit to the network fallback
    // BEFORE the string-detail branch so the recruiter sees a recovery
    // hint instead of the synthesized URL string.
    if (err.status === 0) {
      return `${actionLabel} failed: ${genericFallback(err)}`;
    }
    // Code-based mapping wins over status-based fallbacks — a 404
    // with `error: intake_session_not_found` should read with that
    // entry's recovery affordance, not the generic 404 fallback.
    const d = err.detail;
    if (d && typeof d === "object" && "error" in d) {
      const code = String((d as Record<string, unknown>).error ?? "");
      const mapped = ERROR_COPY[code];
      if (mapped !== undefined) {
        return `${actionLabel} failed: ${mapped}`;
      }
    }
    if (err.status === 404) {
      return `${actionLabel} failed: That's gone — or the link is stale.`;
    }
    if (typeof d === "string" && d.trim().length > 0) {
      return `${actionLabel} failed: ${d}`;
    }
  }
  return `${actionLabel} failed: ${genericFallback(err)}`;
}
