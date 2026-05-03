// Plain-language error copy for Cloris API failures.
//
// The backend returns structured error codes inside `detail.error`. The
// product UI must render them in product language — no PIDs, no
// "backend reports", no raw code strings. If there is no recognized
// code, fall back to a generic short message.

import { ApiError } from "./api";

// Translation table for the error codes the existing routes can return.
// Keep this list aligned with the codes raised by `cloris/api.py` and
// `cloris/worker.py`. Extend it as new codes appear.
const ERROR_COPY: Record<string, string> = {
  brief_path_not_found: "I could not find that brief.",
  worker_already_running: "That card is already being worked.",
  no_pending_work: "Nothing pending to pull.",
  state_dir_not_found: "I could not find that card.",
  invalid_brief_path: "That brief path doesn't look right.",
  // Intake / brief-authoring (Phase D Slice D3 + D4).
  intake_session_not_found: "I couldn't find that draft.",
  invalid_v2_brief: "The brief isn't quite ready to file.",
  brief_already_exists:
    "A brief with this role title already exists.",
  brief_write_failed: "I couldn't write the brief to disk.",
  brief_id_computation_failed:
    "I wrote the brief but couldn't pin its id. Refresh the brief library to find it.",
  intake_session_gone_after_complete:
    "The brief was written but the draft was removed mid-flight."
};

// Returns the human-readable copy for an unknown error. Used as the
// final fallback when nothing in `ERROR_COPY` matches.
function genericFallback(): string {
  return "Something went wrong. Try again.";
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
    // Code-based mapping wins over status-based fallbacks — a 404
    // with `error: intake_session_not_found` should read "I couldn't
    // find that draft.", not "I couldn't find that." (R21 voice
    // metaphor "card" is also dropped from the generic fallback below).
    const d = err.detail;
    if (d && typeof d === "object" && "error" in d) {
      const code = String((d as Record<string, unknown>).error ?? "");
      const mapped = ERROR_COPY[code];
      if (mapped !== undefined) {
        return `${actionLabel} failed: ${mapped}`;
      }
    }
    if (err.status === 404) {
      return `${actionLabel} failed: I couldn't find that.`;
    }
    if (typeof d === "string" && d.trim().length > 0) {
      return `${actionLabel} failed: ${d}`;
    }
    return `${actionLabel} failed: ${genericFallback()}`;
  }
  return `${actionLabel} failed: ${genericFallback()}`;
}
