// Cloris HTTP client.
//
// Source of truth for the wire shapes is cloris/models.py. The
// corresponding TS mirror lives in ./types.ts; this module is a thin
// fetch layer with one error class.
//
// Most calls throw `ApiError` on non-2xx. `stopWorker` is the deliberate
// exception: the route returns 200 (missing/stale) or 202 (stopping)
// with the same body shape, and the UI needs to know which it got so it
// can decide whether to enter optimistic-stopping. We therefore return
// `{ status, body }` for stop and let the caller branch on status.

import type {
  LaunchResponse,
  ResumeResponse,
  StatusResponse,
  StopResponse
} from "./types";

export class ApiError extends Error {
  status: number;
  detail: unknown;

  constructor(status: number, detail: unknown, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

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

async function request<T>(
  url: string,
  init: RequestInit = {}
): Promise<T> {
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

export async function getStatus(): Promise<StatusResponse> {
  return request<StatusResponse>("/api/status", { method: "GET" });
}

export async function launchLinkedIn(
  briefPath: string
): Promise<LaunchResponse> {
  return request<LaunchResponse>("/api/launch/linkedin", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ brief_path: briefPath })
  });
}

export async function resumeLinkedIn(
  briefPath: string
): Promise<ResumeResponse> {
  return request<ResumeResponse>("/api/resume/linkedin", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ brief_path: briefPath })
  });
}

export async function stopWorker(
  source: string,
  stateKey: string
): Promise<{ status: number; body: StopResponse }> {
  // Stop deliberately bypasses request<T>() so the caller can branch on
  // 200 (missing/stale; no optimistic state) vs 202 (stopping; mark
  // optimistic-stopping) vs 404 (state dir not found; surface error).
  const url = `/api/stop/${encodeURIComponent(source)}/${encodeURIComponent(stateKey)}`;
  let response: Response;
  try {
    response = await fetch(url, { method: "POST" });
  } catch (err) {
    throw new ApiError(0, String(err), `Network error contacting ${url}`);
  }
  const parsed = (await parseJsonOrThrow(response)) as
    | StopResponse
    | { detail?: unknown };

  if (response.status === 200 || response.status === 202) {
    return { status: response.status, body: parsed as StopResponse };
  }

  const detail =
    parsed && typeof parsed === "object" && "detail" in parsed
      ? (parsed as { detail: unknown }).detail
      : parsed;
  throw new ApiError(
    response.status,
    detail,
    `Stop request failed (status ${response.status})`
  );
}
