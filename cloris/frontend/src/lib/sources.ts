// Centralized source-key registry for Cloris modules.
//
// Mirrors `cloris/control_plane.py:_SOURCES` MANUALLY. When backend ships a
// new module, widen `types.ts:Source` first (slice gated on backend rollout),
// then add the matching entry here. The exhaustive `Record<SourceKey, ...>`
// shape below ensures the type checker errors on missing entries.

import type { Source } from "./types";

// SourceKey mirrors the wire `Source` type. As new modules ship and
// `types.ts:Source` widens, this type widens with it.
export type SourceKey = Source;

export interface SourceMeta {
  key: SourceKey;
  // Recruiter-readable display (e.g., "LinkedIn").
  label: string;
  // Mono-meta short form for chips/badges (e.g., "linkedin").
  shortLabel: string;
  // Phase D Slice D10 (Ledger L5): two-letter mono-caps pill label
  // for the bridge UI on workspace candidate cards. Tells the recruiter
  // which discovery module surfaced this person at a glance. Removed
  // at Phase F when identity resolution merges per-source rows into
  // multi-source person rows; the pill becomes a list of contributors.
  pillLabel: string;
  // Whether the source has a stoppable worker. Today: true for both
  // linkedin and github.
  stoppable: boolean;
  // Whether this source is directly launchable from LaunchForm. False for
  // sub-modules that piggyback on another source's worker (e.g., a future
  // "maintainer" key would have launchable=false because maintainer briefs
  // target the github launcher).
  launchable: boolean;
}

// Initial registry — must mirror cloris/control_plane.py:_SOURCES verbatim.
export const SOURCES: Record<SourceKey, SourceMeta> = {
  linkedin:    { key: "linkedin",    label: "LinkedIn",          shortLabel: "linkedin",    pillLabel: "LI", stoppable: true, launchable: true },
  github:      { key: "github",      label: "GitHub",            shortLabel: "github",      pillLabel: "GH", stoppable: true, launchable: true },
  researcher:  { key: "researcher",  label: "Researcher",        shortLabel: "researcher",  pillLabel: "RE", stoppable: true, launchable: true },
  designer:    { key: "designer",    label: "Designer",          shortLabel: "designer",    pillLabel: "DE", stoppable: true, launchable: true },
  exec_search: { key: "exec_search", label: "Executive Search",  shortLabel: "exec_search", pillLabel: "ES", stoppable: true, launchable: true },
};

// Stable comparator: linkedin always first; remaining sources alphabetical
// by key.
function compareSourceMeta(a: SourceMeta, b: SourceMeta): number {
  if (a.key === "linkedin" && b.key !== "linkedin") return -1;
  if (b.key === "linkedin" && a.key !== "linkedin") return 1;
  if (a.key < b.key) return -1;
  if (a.key > b.key) return 1;
  return 0;
}

// Exhaustive lookup. For unknown keys (forward-compat: backend ships a new
// source before frontend updates), returns a defensive fallback with both
// affordances disabled and emits a console.warn. Under-offering on unknown
// sources is preferable to over-offering.
export function sourceMeta(key: string): SourceMeta {
  const registered = (SOURCES as Record<string, SourceMeta | undefined>)[key];
  if (registered !== undefined) {
    return registered;
  }
  console.warn(`sourceMeta: unknown source "${key}"; using defensive fallback`);
  return {
    key: key as SourceKey,
    label: key,
    shortLabel: key,
    pillLabel: key.slice(0, 2).toUpperCase(),
    stoppable: false,
    launchable: false,
  };
}

export function isStoppable(key: string): boolean {
  return sourceMeta(key).stoppable;
}

export function isLaunchable(key: string): boolean {
  return sourceMeta(key).launchable;
}

// Sources eligible for the LaunchForm selector — registered + launchable.
// Stable order: linkedin first, then alphabetical.
export function launchableSources(): SourceMeta[] {
  return Object.values(SOURCES)
    .filter((meta) => meta.launchable)
    .sort(compareSourceMeta);
}

// All registered sources. Stable order: linkedin first, then alphabetical.
export function allSources(): SourceMeta[] {
  return Object.values(SOURCES).sort(compareSourceMeta);
}
