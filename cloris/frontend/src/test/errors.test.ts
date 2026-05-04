// Tests for the API error → product-language translator (lib/errors.ts).
//
// The function under test is consumed at every action call-site (launch,
// resume, stop, ...) so the tests pin every documented branch:
//   - structured detail.error codes map through ERROR_COPY.
//   - 404s without a code fall through to a "gone or stale link" hint.
//   - status === 0 (network) and status >= 500 (server) get distinct
//     fallbacks so the recruiter has a useful next move.
//   - unknown / empty detail and non-ApiError values land in the
//     generic-but-action-shaped fallback.
//   - string detail uses the raw string.

import { describe, it, expect } from "vitest";
import { describeApiError } from "../lib/errors";
import { ApiError } from "../lib/api";

describe("describeApiError", () => {
  it("maps 404 with a known code through ERROR_COPY (state_dir_not_found)", () => {
    const err = new ApiError(404, { error: "state_dir_not_found" }, "missing");
    expect(describeApiError(err, "Stop")).toBe(
      "Stop failed: That card is gone — or the link is stale."
    );
  });

  it("maps detail.error=brief_path_not_found to the friendly copy", () => {
    const err = new ApiError(
      400,
      { error: "brief_path_not_found" },
      "bad path"
    );
    expect(describeApiError(err, "File card")).toBe(
      "File card failed: That brief is gone — or the link is stale."
    );
  });

  it("maps detail.error=worker_already_running to the friendly copy", () => {
    const err = new ApiError(
      409,
      { error: "worker_already_running" },
      "conflict"
    );
    expect(describeApiError(err, "File card")).toBe(
      "File card failed: That card is already being worked."
    );
  });

  it("maps detail.error=no_pending_work to the friendly copy", () => {
    const err = new ApiError(409, { error: "no_pending_work" }, "no work");
    expect(describeApiError(err, "Pull & Resume")).toBe(
      "Pull & Resume failed: Nothing pending to pull."
    );
  });

  it("maps detail.error=invalid_brief_path to the friendly copy", () => {
    const err = new ApiError(
      400,
      { error: "invalid_brief_path" },
      "bad path"
    );
    expect(describeApiError(err, "File card")).toBe(
      "File card failed: That brief path doesn't look right."
    );
  });

  it("maps detail.error=brief_already_exists with the recovery affordance", () => {
    const err = new ApiError(
      409,
      { error: "brief_already_exists" },
      "duplicate"
    );
    expect(describeApiError(err, "Filing this brief")).toBe(
      "Filing this brief failed: A brief with this role title already exists. Pick a different title or edit the existing brief from the library."
    );
  });

  it("uses the bare 404 fallback when no code is present", () => {
    const err = new ApiError(404, null, "missing");
    expect(describeApiError(err, "Loading the run")).toBe(
      "Loading the run failed: That's gone — or the link is stale."
    );
  });

  it("uses the network fallback when status === 0", () => {
    const err = new ApiError(0, "Network error contacting /api/x", "net");
    expect(describeApiError(err, "Loading briefs")).toBe(
      "Loading briefs failed: Cloris is offline. Check your connection and try again."
    );
  });

  it("uses the server fallback when status >= 500 with no code or string detail", () => {
    const err = new ApiError(500, null, "no detail");
    expect(describeApiError(err, "Stop")).toBe(
      "Stop failed: Something failed on Cloris's side. Try again in a moment."
    );
  });

  it("uses the server fallback when status >= 500 with empty string detail", () => {
    const err = new ApiError(500, "", "empty");
    expect(describeApiError(err, "File card")).toBe(
      "File card failed: Something failed on Cloris's side. Try again in a moment."
    );
  });

  it("falls back to the generic message for an unknown detail.error code", () => {
    const err = new ApiError(
      400,
      { error: "mystery_error_code" },
      "mystery"
    );
    expect(describeApiError(err, "File card")).toBe(
      "File card failed: Something didn't go through. Try again in a moment."
    );
  });

  it("uses a non-empty string detail verbatim", () => {
    const err = new ApiError(500, "downstream blew up", "downstream blew up");
    expect(describeApiError(err, "File card")).toBe(
      "File card failed: downstream blew up"
    );
  });

  it("falls back to the generic message for a non-ApiError thrown value", () => {
    const err = new Error("native failure");
    expect(describeApiError(err, "File card")).toBe(
      "File card failed: Something didn't go through. Try again in a moment."
    );
  });

  it("falls back to the generic message for a non-Error thrown value", () => {
    expect(describeApiError("oops", "Stop")).toBe(
      "Stop failed: Something didn't go through. Try again in a moment."
    );
  });
});
