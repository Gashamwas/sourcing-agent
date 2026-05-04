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
  BriefDetailResponse,
  BriefEditRequest,
  BriefVersionsResponse,
  BriefsListResponse,
  CandidateDetailResponse,
  IdentityPendingResponse,
  LaunchReadinessResponse,
  LaunchResponse,
  LegacyResolveResponse,
  MarketDetailResponse,
  MarketsListResponse,
  MonitorIndexResponse,
  ReconcileResponse,
  ReflectionActiveResponse,
  ReflectionCommitResponse,
  ReflectionResponse,
  ResumeResponse,
  RunReportResponse,
  RunTelemetryResponse,
  SettingsResponse,
  Source,
  StatusResponse,
  StopResponse,
  ToolJobStatusWire,
  ToolRunAsyncWire,
  ToolRunSyncWire,
  ToolsIndexResponse,
  WorkspaceResponse
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

// Fetch timeout: when the Vite dev-server proxy can't reach the
// backend (ECONNREFUSED), it may leave the browser request pending
// indefinitely instead of returning a 5xx. AbortSignal.timeout
// ensures the fetch rejects after REQUEST_TIMEOUT_MS so the error-
// handling path in refreshStatus() fires and the UI can recover.
//
// Was 5_000 until the trial-walk doc measured the flagship workspace
// endpoint at ~14s on a 170KB / 77-save payload — first contact with
// the most-developed brief was a permanent error screen with no
// retry. 30_000 is the trial-day call: well above the largest
// observed legitimate response, still below the "user assumes the
// app is hung" threshold. When endpoint perf is fixed (the real
// long-term answer is making /api/workspace/* return faster), this
// can come back down.
const REQUEST_TIMEOUT_MS = 30_000;

async function request<T>(
  url: string,
  init: RequestInit = {}
): Promise<T> {
  let response: Response;
  try {
    // Merge timeout signal with any caller-supplied signal.
    const timeoutSignal = AbortSignal.timeout(REQUEST_TIMEOUT_MS);
    const mergedInit: RequestInit = {
      ...init,
      signal: init.signal
        ? AbortSignal.any([init.signal, timeoutSignal])
        : timeoutSignal,
    };
    response = await fetch(url, mergedInit);
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

// Phase 0 ``apikey-ui`` slice: first-launch welcome gate.
//
// The frontend gate in App.svelte fetches /api/onboarding/status on
// mount; welcome_complete=false renders Welcome.svelte instead of
// the route table. Gate is sticky for the lifetime of the page —
// once unlocked, no need to re-poll.
//
// Wire shape mirrors cloris/models.py:OnboardingStatusResponse.
export type OnboardingStatusResponse = {
  slice: "v0-onboarding-status-1";
  welcome_complete: boolean;
  anthropic_present: boolean;
  acknowledged: boolean;
  acknowledged_at: string | null;
  env_path: string;
  acknowledgment_path: string;
};

export type ChromeStatusResponse = {
  slice: "v0-chrome-status-1";
  state: "healthy" | "spawning" | "unhealthy" | "missing_chrome" | "unsupported_platform";
  cdp_url: string;
  profile_dir: string;
  message: string;
};

export async function getOnboardingStatus(): Promise<OnboardingStatusResponse> {
  return request<OnboardingStatusResponse>("/api/onboarding/status", {
    method: "GET"
  });
}

export async function postOnboardingCredential(
  key: string,
  value: string
): Promise<OnboardingStatusResponse> {
  return request<OnboardingStatusResponse>("/api/onboarding/credential", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ key, value })
  });
}

export async function postOnboardingAcknowledge(): Promise<OnboardingStatusResponse> {
  return request<OnboardingStatusResponse>("/api/onboarding/acknowledge", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ acknowledged: true })
  });
}

export async function getChromeStatus(): Promise<ChromeStatusResponse> {
  return request<ChromeStatusResponse>("/api/chrome-status", { method: "GET" });
}

export async function postChromeRelaunch(): Promise<ChromeStatusResponse> {
  return request<ChromeStatusResponse>("/api/chrome-relaunch", { method: "POST" });
}

// Phase 1A: zombie reconciler. The frontend calls this on app mount and
// on a slow timer so runs whose worker process died (Mac sleep, OOM,
// kill -9) get marked status='abandoned' instead of staying status='running'
// indefinitely. The aggregator at /api/status remains a pure read; this
// endpoint is the explicit write trigger.
export async function reconcileOrphans(): Promise<ReconcileResponse> {
  return request<ReconcileResponse>("/api/reconcile", { method: "POST" });
}

// Authored briefs for the LaunchForm picker. Replaces the previous
// developer-language Brief Path text input with a recruiter-meaningful
// list of briefs from `config/`. See cloris/api.py:_scan_authored_briefs
// for the inclusion / exclusion rules.
export async function getBriefs(): Promise<BriefsListResponse> {
  return request<BriefsListResponse>("/api/briefs", { method: "GET" });
}

// Phase D Slice D2: brief detail / edit. GET returns the V2/legacy
// partition; PUT writes a new version after migrating flat → nested
// (Fork C) and atomic-writing canonical-then-versions/ (architectural-
// fit critique catch on ordering).
export async function getBrief(briefId: string): Promise<BriefDetailResponse> {
  const url = `/api/brief/${encodeURIComponent(briefId)}`;
  return request<BriefDetailResponse>(url, { method: "GET" });
}

export async function putBrief(
  briefId: string,
  body: BriefEditRequest
): Promise<BriefDetailResponse> {
  const url = `/api/brief/${encodeURIComponent(briefId)}`;
  return request<BriefDetailResponse>(url, {
    method: "PUT",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body)
  });
}

// Phase D Slice D5: brief version history listing. Read-only audit
// trail; full diff view defers to a follow-up.
export async function getBriefVersions(
  briefId: string
): Promise<BriefVersionsResponse> {
  const url = `/api/brief/${encodeURIComponent(briefId)}/versions`;
  return request<BriefVersionsResponse>(url, { method: "GET" });
}

// Phase E Slice E1: market viewer endpoints. Catalog list +
// per-market detail. Detail throws ApiError on 404 (market_not_found)
// so the caller can render an "unknown market" surface.
export async function getMarkets(): Promise<MarketsListResponse> {
  return request<MarketsListResponse>("/api/markets", { method: "GET" });
}

export async function getMarket(
  marketKey: string
): Promise<MarketDetailResponse> {
  const url = `/api/market/${encodeURIComponent(marketKey)}`;
  return request<MarketDetailResponse>(url, { method: "GET" });
}

// Phase G Slice G2: identity reconciliation endpoints. The pending
// list re-runs F3 resolution on read so newly-discovered candidates
// surface without a manual sync. Decision/unlink return 204 on success;
// the frontend re-fetches pending after each mutation.
export async function getIdentityPending(
  briefId: string
): Promise<IdentityPendingResponse> {
  const url = `/api/brief/${encodeURIComponent(briefId)}/identity/pending`;
  return request<IdentityPendingResponse>(url, { method: "GET" });
}

export async function postIdentityDecision(
  briefId: string,
  decisionId: number,
  choice: "merge" | "keep_separate"
): Promise<void> {
  const url = `/api/brief/${encodeURIComponent(briefId)}/identity/decision`;
  await request<void>(url, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ decision_id: decisionId, choice }),
  });
}

export async function postIdentityUnlink(
  briefId: string,
  source: Source,
  stateKey: string,
  candidateId: number
): Promise<void> {
  const url = `/api/brief/${encodeURIComponent(briefId)}/identity/unlink`;
  await request<void>(url, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({
      source,
      state_key: stateKey,
      candidate_id: candidateId,
    }),
  });
}

// Phase G Slice G3: Live Monitor endpoints. Index is cheap; telemetry
// is windowed (50 attempts + 30 events most-recent). Polled at 1s when
// active, 5s otherwise.
export async function getMonitorIndex(): Promise<MonitorIndexResponse> {
  return request<MonitorIndexResponse>("/api/monitor/index", { method: "GET" });
}

export async function getRunTelemetry(
  source: string,
  stateKey: string,
  runId: number
): Promise<RunTelemetryResponse> {
  const url = `/api/run/${encodeURIComponent(source)}/${encodeURIComponent(stateKey)}/${encodeURIComponent(String(runId))}/telemetry`;
  return request<RunTelemetryResponse>(url, { method: "GET" });
}

// Phase G Slice G4: Tools framework. Sync + async share one POST endpoint;
// the response type tells the frontend which path it took.
export async function getToolsIndex(): Promise<ToolsIndexResponse> {
  return request<ToolsIndexResponse>("/api/tools", { method: "GET" });
}

export async function runTool(
  toolId: string,
  args: Record<string, unknown>
): Promise<ToolRunSyncWire | ToolRunAsyncWire> {
  return request<ToolRunSyncWire | ToolRunAsyncWire>(
    `/api/tools/${encodeURIComponent(toolId)}`,
    {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ args }),
    }
  );
}

export async function getToolJobStatus(
  jobId: string
): Promise<ToolJobStatusWire> {
  return request<ToolJobStatusWire>(
    `/api/tools/jobs/${encodeURIComponent(jobId)}`,
    { method: "GET" }
  );
}

// Phase G Slice G5: Settings transparency snapshot.
export async function getSettings(): Promise<SettingsResponse> {
  return request<SettingsResponse>("/api/settings", { method: "GET" });
}

// Phase B: per-run report. Throws ApiError on 404 (state_dir_not_found
// or run_not_found) so the caller can render an "unknown run" surface
// without the network layer guessing intent.
export async function getRunReport(
  source: string,
  stateKey: string,
  runId: number
): Promise<RunReportResponse> {
  const url = `/api/run/${encodeURIComponent(source)}/${encodeURIComponent(stateKey)}/${encodeURIComponent(String(runId))}`;
  return request<RunReportResponse>(url, { method: "GET" });
}

// Phase C-bis 0.1: per-brief workspace, brief-first. The endpoint
// aggregates SAVE-class candidates across every state_dir whose latest
// run carries this brief_id. Throws ApiError on 404 (workspace_not_found)
// when no state_dir matches.
export async function getWorkspace(
  briefId: string
): Promise<WorkspaceResponse> {
  const url = `/api/workspace/${encodeURIComponent(briefId)}`;
  return request<WorkspaceResponse>(url, { method: "GET" });
}

// Phase C-bis 0.1: per-candidate detail, brief-first. Throws ApiError on
// 404 (candidate_not_found) when no state_dir under this brief_id
// contains a candidate with the given id. The cross-brief guard prevents
// a candidate from a different brief leaking under this URL.
export async function getCandidate(
  briefId: string,
  candidateId: number
): Promise<CandidateDetailResponse> {
  const url = `/api/candidate/${encodeURIComponent(briefId)}/${encodeURIComponent(String(candidateId))}`;
  return request<CandidateDetailResponse>(url, { method: "GET" });
}

// Phase C-bis 0.1: append a recruiter-authored note (brief-first URL).
export async function appendCandidateNote(
  briefId: string,
  candidateId: number,
  body: string
): Promise<CandidateDetailResponse> {
  const url = `/api/candidate/${encodeURIComponent(briefId)}/${encodeURIComponent(String(candidateId))}/note`;
  return request<CandidateDetailResponse>(url, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ body })
  });
}

// Phase C-bis 0.1: set or clear the recruiter-overridden status (brief-first URL).
// ``user_status: null`` clears the override; non-null must be in the
// validated set (shortlist / parked / contacted / hidden) — the server
// returns 422 for any other value.
export async function updateCandidateStatus(
  briefId: string,
  candidateId: number,
  user_status: string | null
): Promise<CandidateDetailResponse> {
  const url = `/api/candidate/${encodeURIComponent(briefId)}/${encodeURIComponent(String(candidateId))}`;
  return request<CandidateDetailResponse>(url, {
    method: "PATCH",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ user_status })
  });
}

// Phase D Slice D6 (Ledger L1): set or clear the recruiter's calibration
// signal on Cloris's judgment. Distinct from user_status — this captures
// whether Cloris's *judgment* was useful, wrong, or off-rubric, NOT what
// pipeline action the recruiter is taking. ``judgment_accuracy: null``
// clears; non-null must be in the validated set (useful / wrong /
// off_rubric / overstated_depth / understated_depth) — server returns
// 422 otherwise. Schema substrate landed in C-bis Slice 0.5.
export async function setCandidateJudgmentAccuracy(
  briefId: string,
  candidateId: number,
  judgment_accuracy: string | null
): Promise<CandidateDetailResponse> {
  const url = `/api/candidate/${encodeURIComponent(briefId)}/${encodeURIComponent(String(candidateId))}/judgment-accuracy`;
  return request<CandidateDetailResponse>(url, {
    method: "PATCH",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ judgment_accuracy })
  });
}

// Phase D Slice D9 (Ledger L4). Launch-readiness pre-flight probe.
// Returns source-level blockers (LinkedIn browser session, GitHub
// token scope) the LaunchForm renders ABOVE the launch button. The
// brief_id is opaque for Phase D — Phase F's per-brief
// save-destination check will start consulting it. Encoded path
// segments are accepted (`brief_id` may carry slashes like
// `config/<brief>/brief.json`).
export async function getLaunchReadiness(
  source: string,
  briefId: string
): Promise<LaunchReadinessResponse> {
  // Encode each segment separately so encoded slashes survive — the
  // backend route uses a `:path` converter that accepts them.
  const encodedSource = encodeURIComponent(source);
  // For the briefId we DO NOT encodeURIComponent the slashes; the
  // route uses :path which accepts them. But we DO encode characters
  // that would break URL parsing. Easiest: encode each segment
  // delimited by `/`.
  const encodedBriefId = briefId
    .split("/")
    .map((seg) => encodeURIComponent(seg))
    .join("/");
  const url = `/api/launch-readiness/${encodedSource}/${encodedBriefId}`;
  return request<LaunchReadinessResponse>(url, { method: "GET" });
}

// Phase C-bis 0.1: legacy URL resolvers. Old bookmarks pointing at the
// source-siloed URLs hit these to learn the brief_id, then the frontend
// rewrites the hash. Both endpoints return the same shape.
export async function resolveLegacyWorkspace(
  source: string,
  stateKey: string
): Promise<LegacyResolveResponse> {
  const url = `/api/resolve-legacy/workspace/${encodeURIComponent(source)}/${encodeURIComponent(stateKey)}`;
  return request<LegacyResolveResponse>(url, { method: "GET" });
}

export async function resolveLegacyCandidate(
  source: string,
  stateKey: string,
  candidateId: number
): Promise<LegacyResolveResponse> {
  const url = `/api/resolve-legacy/candidate/${encodeURIComponent(source)}/${encodeURIComponent(stateKey)}/${encodeURIComponent(String(candidateId))}`;
  return request<LegacyResolveResponse>(url, { method: "GET" });
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

// Phase F Slice F1. Generic per-source launch + resume.
//
// `source` is "linkedin" | "github" (validated server-side against the
// `cloris.launchers.LAUNCHERS` registry; unknown sources surface as
// ApiError(422) with the allowed list on `detail.allowed`).
//
// `mode: "resume"` collapses what used to be a separate
// `POST /api/resume/<source>` endpoint into one route — the existing
// `resumeLinkedIn` helper above is now a back-compat wrapper around the
// legacy literal endpoint and stays put for ~6 months of deprecation.
//
// `force: true` skips the launch-readiness probe (Phase D Slice D9). It
// does NOT skip pre-flight integrity checks (BriefIdNotFound,
// WorkerAlreadyRunning, NoPendingWork); those still surface as their
// canonical HTTP codes.
export async function launchForSource(
  source: Source,
  briefId: string,
  mode: "fresh" | "resume" = "fresh",
  force: boolean = false
): Promise<LaunchResponse> {
  const url = `/api/launch/${encodeURIComponent(source)}`;
  return request<LaunchResponse>(url, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ brief_id: briefId, mode, force })
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

// --- The Reflection — HITL Market Intelligence ---
//
// Two HITL gates wrapping the market-intel pipeline. Mirrors
// shared/runtime_state/reflection.py + cloris/api.py reflection
// endpoints. The state machine is:
//   planning → plan_approved → researching → awaiting_diff
//             → committed | discarded
// The frontend polls GET /sessions/{id} during researching; all other
// transitions are explicit POST/PATCH.

export async function createReflectionSession(args: {
  brief_id: string;
  source_run_id?: number | null;
  run_dir?: string | null;
}): Promise<ReflectionResponse> {
  return request<ReflectionResponse>("/api/reflection/sessions", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({
      brief_id: args.brief_id,
      source_run_id: args.source_run_id ?? null,
      run_dir: args.run_dir ?? null,
    }),
  });
}

export async function getReflectionSession(
  sessionId: number
): Promise<ReflectionResponse> {
  return request<ReflectionResponse>(
    `/api/reflection/sessions/${encodeURIComponent(String(sessionId))}`,
    { method: "GET" }
  );
}

export async function getActiveReflection(
  briefId: string
): Promise<ReflectionActiveResponse> {
  const url = `/api/reflection/sessions/active?brief_id=${encodeURIComponent(briefId)}`;
  return request<ReflectionActiveResponse>(url, { method: "GET" });
}

export async function patchReflectionSteering(
  sessionId: number,
  note: string
): Promise<ReflectionResponse> {
  return request<ReflectionResponse>(
    `/api/reflection/sessions/${encodeURIComponent(String(sessionId))}/steering`,
    {
      method: "PATCH",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ note }),
    }
  );
}

export async function startReflectionResearch(
  sessionId: number
): Promise<ReflectionResponse> {
  return request<ReflectionResponse>(
    `/api/reflection/sessions/${encodeURIComponent(String(sessionId))}/start_research`,
    {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({}),
    }
  );
}

export async function commitReflection(
  sessionId: number,
  acceptedHunkIds: string[],
  editedHunks: Record<string, { after: string }> | null = null
): Promise<ReflectionCommitResponse> {
  return request<ReflectionCommitResponse>(
    `/api/reflection/sessions/${encodeURIComponent(String(sessionId))}/commit`,
    {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        accepted_hunk_ids: acceptedHunkIds,
        edited_hunks: editedHunks,
      }),
    }
  );
}

export async function discardReflection(
  sessionId: number
): Promise<ReflectionResponse> {
  return request<ReflectionResponse>(
    `/api/reflection/sessions/${encodeURIComponent(String(sessionId))}/discard`,
    {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({}),
    }
  );
}
