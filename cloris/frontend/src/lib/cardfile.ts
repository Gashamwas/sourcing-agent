// Card-file partition + sort utilities.
//
// Front of File = cards that need attention (worker active/stale, work
// pending, or run currently in a non-terminal state). Filed Away =
// everything else. Sort order matches the original StateDirList logic so
// the homescreen mini-list, the full Front-of-File tab, and the Filed
// Away page all agree on what's "first."

import type { StateDirEntry } from "./types";

// Phase 1C: only entries the user actually authored show up in the
// homescreen lists. Orphans / archived / intake-only entries either
// live in their own surfaces or stay invisible until the user goes
// looking. The aggregator's `kind` field is the source of truth here;
// frontend code should never re-derive this from raw fields.
export function isAuthoredBrief(entry: StateDirEntry): boolean {
  return entry.kind === "authored_brief";
}

export function needsAttention(entry: StateDirEntry): boolean {
  if (entry.worker_state === "alive" || entry.worker_state === "stale") {
    return true;
  }
  if (entry.resumable === true) return true;
  const status = entry.latest_run?.status;
  if (
    status === "running" ||
    status === "interrupted" ||
    status === "governor_limit_reached"
  ) {
    return true;
  }
  return false;
}

function latestTime(entry: StateDirEntry): number {
  const value = entry.latest_run?.ended_at ?? entry.latest_run?.started_at;
  if (!value) return 0;
  const parsed = Date.parse(value);
  return Number.isNaN(parsed) ? 0 : parsed;
}

// Within Front of File, prioritize: alive worker first, then a running run,
// then resumable, then stale, then anything else that snuck in. Within the
// same priority, sort by most-recent activity.
function frontPriority(entry: StateDirEntry): number {
  if (entry.worker_state === "alive") return 0;
  if (entry.latest_run?.status === "running") return 0;
  if (entry.resumable === true) return 1;
  if (entry.worker_state === "stale") return 2;
  return 3;
}

function entryKey(entry: StateDirEntry): string {
  return `${entry.source}/${entry.state_key}`;
}

export function frontOfFile(entries: StateDirEntry[]): StateDirEntry[] {
  return entries
    .filter((e) => isAuthoredBrief(e) && needsAttention(e))
    .toSorted((a, b) => {
      const priorityDelta = frontPriority(a) - frontPriority(b);
      if (priorityDelta !== 0) return priorityDelta;
      const timeDelta = latestTime(b) - latestTime(a);
      if (timeDelta !== 0) return timeDelta;
      return entryKey(a).localeCompare(entryKey(b));
    });
}

export function filedAway(entries: StateDirEntry[]): StateDirEntry[] {
  return entries
    .filter((e) => isAuthoredBrief(e) && !needsAttention(e))
    .toSorted((a, b) => {
      const timeDelta = latestTime(b) - latestTime(a);
      if (timeDelta !== 0) return timeDelta;
      return entryKey(a).localeCompare(entryKey(b));
    });
}

// Phase 3C: predicate that drives the homescreen Pull & Resume button's
// visibility. The button has no purpose when no brief in the inventory
// is in a pull-able state — surfacing it then is class-7 (overflow /
// dead-end) rot. Hiding > disabling because a hidden button doesn't
// trigger the "why is this greyed out?" question.
export function anyResumable(entries: StateDirEntry[]): boolean {
  return entries.some((e) => e.resumable === true);
}

// Phase 3B: per-group filters for the FiledAwayPage IA refactor. Each
// helper takes the FULL entries list (not the already-filtered filedAway
// output) so it can pick up entries with kind = archived / orphaned that
// the authored-brief filter would otherwise hide.

function sortByActivity(entries: StateDirEntry[]): StateDirEntry[] {
  return entries.toSorted((a, b) => {
    const timeDelta = latestTime(b) - latestTime(a);
    if (timeDelta !== 0) return timeDelta;
    return entryKey(a).localeCompare(entryKey(b));
  });
}

// Authored briefs that ran to a clean terminal state.
export function finishedBriefs(entries: StateDirEntry[]): StateDirEntry[] {
  return sortByActivity(
    entries.filter((e) => {
      if (!isAuthoredBrief(e)) return false;
      const status = e.latest_run?.status;
      return status === "completed" || status === "succeeded";
    })
  );
}

// Authored briefs whose run was abandoned by the reconciler or errored
// out. Distinct from finished — these need a "rerun?" cue, not just an
// archive cue.
export function lostBriefs(entries: StateDirEntry[]): StateDirEntry[] {
  return sortByActivity(
    entries.filter((e) => {
      if (!isAuthoredBrief(e)) return false;
      const status = e.latest_run?.status;
      return status === "abandoned" || status === "error";
    })
  );
}

// Archived briefs (user-archived) plus orphaned state directories
// (filesystem artifacts with no run history). Bucketed together because
// neither is a live brief — both are reference-only material that the
// recruiter rarely needs but might want to inspect.
export function archivedOrOrphaned(entries: StateDirEntry[]): StateDirEntry[] {
  return sortByActivity(
    entries.filter(
      (e) => e.kind === "archived" || e.kind === "orphaned_state_dir"
    )
  );
}

// Phase F Slice F7 (Ledger L11 + L22). Group state-dir entries by
// brief_id so the home + filed surfaces render ONE card per brief
// instead of one per (brief × module). Each group ships a primary
// entry (chosen for status priority + recency) and zero or more
// secondary entries that StateDirRow stacks as additional source
// pills.
export interface BriefGroupedRow {
  primary: StateDirEntry;
  secondary: StateDirEntry[];
}

export function groupEntriesByBrief(
  entries: StateDirEntry[]
): BriefGroupedRow[] {
  const groupsByBrief = new Map<string, StateDirEntry[]>();
  const ungrouped: StateDirEntry[] = [];
  for (const entry of entries) {
    const key = entry.brief_id_from_run;
    if (!key) {
      ungrouped.push(entry);
      continue;
    }
    const existing = groupsByBrief.get(key);
    if (existing) {
      existing.push(entry);
    } else {
      groupsByBrief.set(key, [entry]);
    }
  }

  const out: BriefGroupedRow[] = [];
  for (const [, modules] of groupsByBrief) {
    if (modules.length === 1) {
      out.push({ primary: modules[0], secondary: [] });
      continue;
    }
    // Primary pick: prefer worker_state "alive" (so the active source
    // drives the card pill), then most-recently-active by
    // latest_run.started_at, then stable tie-break by source.
    const sorted = modules.toSorted((a, b) => {
      const aliveDelta =
        Number(b.worker_state === "alive") - Number(a.worker_state === "alive");
      if (aliveDelta !== 0) return aliveDelta;
      return latestTime(b) - latestTime(a);
    });
    out.push({ primary: sorted[0], secondary: sorted.slice(1) });
  }
  for (const entry of ungrouped) {
    out.push({ primary: entry, secondary: [] });
  }
  return out;
}

// Phase RESUME: set of brief identifiers (brief_id_from_run OR
// brief_path_from_worker) that have at least one resumable entry.
// BriefPicker uses this to filter its list when the RESUME verb is
// active — the recruiter sees only briefs Cloris can continue.
export function resumableBriefIds(entries: StateDirEntry[]): Set<string> {
  const ids = new Set<string>();
  for (const e of entries) {
    if (e.resumable !== true) continue;
    if (e.brief_id_from_run) ids.add(e.brief_id_from_run);
    if (e.brief_path_from_worker) ids.add(e.brief_path_from_worker);
  }
  return ids;
}

// Ambient narrative parts for the homescreen — counts only, voice is
// applied at the call site so this stays a pure shape.
export interface AmbientCounts {
  inMotion: number;       // worker alive OR latest_run.status === running
  waiting: number;        // resumable === true AND not alive
  limitReached: number;   // latest_run.status === governor_limit_reached
}

export function ambientCounts(entries: StateDirEntry[]): AmbientCounts {
  let inMotion = 0;
  let waiting = 0;
  let limitReached = 0;
  for (const e of entries) {
    const running = e.worker_state === "alive" || e.latest_run?.status === "running";
    if (running) inMotion += 1;
    if (e.resumable === true && e.worker_state !== "alive") waiting += 1;
    if (e.latest_run?.status === "governor_limit_reached") limitReached += 1;
  }
  return { inMotion, waiting, limitReached };
}
