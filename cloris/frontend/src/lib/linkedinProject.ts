// LinkedIn project URL parsing + brief save helpers — Path 3 trial slice.
//
// Three consumers — OnboardingFlow, BriefDetail, LaunchForm — all need
// the same regex parse and the same brief-save semantic. Centralized
// here so the regex stays in lockstep with linkedin/browser.py:198 and
// the merge shape stays consistent across consumers.
//
// Backend has no dedicated parse endpoint in the trial slice; the regex
// runs client-side and the parsed `project_id` flows into the existing
// PUT /api/brief/{brief_id} contract via `saveLinkedInProject*`.

import { getBrief, putBrief } from "./api";
import type { BriefDetailResponse } from "./types";

export interface ParsedLinkedInProject {
  projectId: string;
  projectName: string | null;
}

// Same regex linkedin/browser.py:198 uses — keep them aligned.
// Matches paths like /talent/hire/<digits>/... regardless of subpath
// (discover/recruiterSearch, search, manage, …).
const PROJECT_URL_PATTERN = /\/talent\/hire\/(\d+)/;

// Parse a Recruiter project URL into a `{projectId, projectName}` pair.
// Returns null on no-match so the caller can render an editorial-grade
// error rather than dispatching a doomed PUT. LinkedIn doesn't put the
// project name in the URL — `projectName` is always null at parse time
// today; future Path 1 work will fill it from the rendered page title.
export function parseLinkedInProjectUrl(
  input: string
): ParsedLinkedInProject | null {
  if (typeof input !== "string") return null;
  const trimmed = input.trim();
  if (trimmed === "") return null;
  const match = trimmed.match(PROJECT_URL_PATTERN);
  if (match === null) return null;
  return { projectId: match[1], projectName: null };
}

// Merge a parsed project into a BriefDetailResponse and write via PUT.
//
// Used by BriefDetail.svelte, which already has the full detail payload
// loaded — saves a redundant GET. Returns the freshly-written detail so
// the caller can swap its local state without re-fetching.
export async function saveLinkedInProjectFromDetail(
  detail: BriefDetailResponse,
  patch: ParsedLinkedInProject
): Promise<BriefDetailResponse> {
  const v2_data: Record<string, unknown> = { ...detail.v2_data };
  const existingSc = v2_data["source_config"];
  const sc: Record<string, unknown> =
    existingSc !== null && existingSc !== undefined && typeof existingSc === "object"
      ? { ...(existingSc as Record<string, unknown>) }
      : {};
  const existingLi = sc["linkedin"];
  const linkedin: Record<string, unknown> =
    existingLi !== null && existingLi !== undefined && typeof existingLi === "object"
      ? { ...(existingLi as Record<string, unknown>) }
      : {};
  linkedin["project_id"] = patch.projectId;
  // Only set `project_name` when the parser produced one; LinkedIn
  // doesn't put the name in the URL so we don't clobber a
  // human-authored name from the brief library or settings.
  if (patch.projectName !== null) {
    linkedin["project_name"] = patch.projectName;
  }
  sc["linkedin"] = linkedin;
  v2_data["source_config"] = sc;
  return putBrief(detail.brief_id, {
    v2_data,
    preserved_legacy: detail.preserved_legacy,
  });
}

// Same as `saveLinkedInProjectFromDetail` but starts from a brief id.
//
// Used by LaunchForm.svelte where the inline editor only has the
// selected brief's id and path — fetching detail is the cheapest way
// to recover the v2/legacy partition without a parallel API surface.
// One extra round-trip per save is a fair price for not duplicating
// the merge logic across two consumers.
export async function saveLinkedInProject(
  briefId: string,
  patch: ParsedLinkedInProject
): Promise<BriefDetailResponse> {
  const detail = await getBrief(briefId);
  return saveLinkedInProjectFromDetail(detail, patch);
}
