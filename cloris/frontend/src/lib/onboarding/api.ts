// Onboarding flow HTTP client (A24 trial plan, Slice 1B).
//
// Source of truth for the wire shapes is the Slice 1B server contract;
// the corresponding TS mirror lives in ../types.ts. This module is a
// thin fetch layer over the /api/intake/sessions endpoints.
//
// We duplicate a minimal copy of `parseJsonOrThrow` / `request<T>` from
// ../api.ts rather than re-export them from there: the existing module
// only exports its high-level call functions, and per slice constraints
// we don't modify it. The dup is deliberately tiny and behaviorally
// identical to keep ApiError semantics consistent across the app.

import { ApiError } from "../api";
import type {
  IntakeSession,
  IntakeSessionCompleteResponse,
  IntakeSessionDeleteResponse,
  IntakeSessionListResponse,
  IntakeSessionResponse,
  IntakeStep,
} from "../types";

async function parseJsonOrThrow(response: Response): Promise<unknown> {
  const text = await response.text();
  if (text.length === 0) return null;
  try {
    return JSON.parse(text);
  } catch {
    throw new ApiError(
      response.status,
      text,
      `Invalid JSON from ${response.url} (status ${response.status})`
    );
  }
}

async function request<T>(url: string, init: RequestInit = {}): Promise<T> {
  let response: Response;
  try {
    response = await fetch(url, init);
  } catch (err) {
    throw new ApiError(0, String(err), `Network error contacting ${url}`);
  }

  const body = (await parseJsonOrThrow(response)) as T | { detail?: unknown };
  if (!response.ok) {
    const detail =
      body && typeof body === "object" && "detail" in body
        ? (body as { detail: unknown }).detail
        : body;
    throw new ApiError(
      response.status,
      detail,
      `Request to ${url} failed (status ${response.status})`
    );
  }
  return body as T;
}

const BASE = "/api/intake/sessions";

// Create a new intake session. `role_title` is optional — the welcome
// phase may collect it later. Returns the unwrapped IntakeSession;
// callers don't need the slice envelope tag.
export async function createIntakeSession(
  args: { role_title?: string } = {}
): Promise<IntakeSession> {
  const body: Record<string, unknown> = {};
  if (args.role_title !== undefined) body.role_title = args.role_title;
  const envelope = await request<IntakeSessionResponse>(BASE, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
  return envelope.session;
}

// List active (non-archived) sessions, newest first per the server.
export async function listIntakeSessions(): Promise<IntakeSession[]> {
  const envelope = await request<IntakeSessionListResponse>(BASE, {
    method: "GET",
  });
  return envelope.sessions;
}

// Fetch a single session by id. 404 surfaces as ApiError(404, ...).
export async function getIntakeSession(id: number): Promise<IntakeSession> {
  const envelope = await request<IntakeSessionResponse>(
    `${BASE}/${encodeURIComponent(String(id))}`,
    { method: "GET" }
  );
  return envelope.session;
}

// Patch any subset of mutable fields. Empty body is allowed and bumps
// updated_at on the server.
export async function patchIntakeSession(
  id: number,
  patch: {
    current_step?: IntakeStep;
    state_json?: Record<string, unknown>;
    role_title?: string;
  }
): Promise<IntakeSession> {
  const envelope = await request<IntakeSessionResponse>(
    `${BASE}/${encodeURIComponent(String(id))}`,
    {
      method: "PATCH",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(patch),
    }
  );
  return envelope.session;
}

// Archive (soft-delete) the session server-side. Returns the deleted
// flag from the envelope so callers can distinguish a legitimate delete
// from an idempotent re-delete if the server later signals that.
export async function deleteIntakeSession(id: number): Promise<boolean> {
  const envelope = await request<IntakeSessionDeleteResponse>(
    `${BASE}/${encodeURIComponent(String(id))}`,
    { method: "DELETE" }
  );
  return envelope.deleted;
}

// Phase D Slice D3. Finalize the intake — server writes the V2 brief
// to disk and stamps the session as completed. Returns the brief_id
// + brief_path so the wizard can navigate to `#/brief/<brief_id>`
// without a second round-trip. ApiError(422, ...) surfaces V2
// validation failures with `missing_keys` / `invalid_keys` on detail;
// ApiError(409, ...) surfaces a name collision (target dir already
// has brief.json) so the wizard can prompt the recruiter.
export async function completeIntakeSession(
  id: number
): Promise<IntakeSessionCompleteResponse> {
  return request<IntakeSessionCompleteResponse>(
    `${BASE}/${encodeURIComponent(String(id))}/complete`,
    { method: "POST" }
  );
}

// Phase D Slice D4. Polish the in-flight v2_draft via the LLM cascade.
// Server reads chapter captures from state_json, snapshots the prior
// v2_draft into the one-deep undo buffer, runs the polish backend,
// and writes the polished v2_draft + polish_meta back. Returns the
// updated session; the caller's reactive store re-renders the editors
// against the new v2_draft automatically.
//
// The state.ts wrapper MUST flushAllPending() before invoking this —
// the server-side snapshot captures whatever v2_draft is on disk at
// the moment of the call, so any unflushed debounced edits would be
// lost from the snapshot.
export async function polishIntakeSession(
  id: number
): Promise<IntakeSession> {
  const envelope = await request<IntakeSessionResponse>(
    `${BASE}/${encodeURIComponent(String(id))}/polish`,
    { method: "POST" }
  );
  return envelope.session;
}

// Phase D Slice D4. Restore the pre-polish v2_draft from the one-deep
// undo buffer. Server pops state_json.v2_draft_prev into v2_draft,
// restores polish_meta from the buffer (or clears it if the buffer
// had no meta), and deletes the buffer key. One-shot consume.
//
// Named symmetrically with `polishIntakeSession` so the api.ts module's
// exports don't collide with the state.ts action wrappers (`polishBrief`,
// `restorePrevDraft`) when both are re-exported through the barrel
// at lib/onboarding/index.ts.
//
// 404 with detail.error === "no_prev_draft" when there's nothing to
// restore — the OnboardingFlow review chapter hides the link in that
// case, so this should never fire from the UI; the 404 is defensive
// for direct-API access.
export async function restoreIntakeSession(id: number): Promise<IntakeSession> {
  const envelope = await request<IntakeSessionResponse>(
    `${BASE}/${encodeURIComponent(String(id))}/restore_prev_draft`,
    { method: "POST" }
  );
  return envelope.session;
}
