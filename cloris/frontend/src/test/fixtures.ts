// Shared test fixtures for component tests.
//
// Build a StateDirEntry with sensible defaults; tests override fields they care
// about. Mirroring the wire shape from cloris/models.py exactly so we catch
// drift early (Phase 0 only ships the fixture; later phases extend the shape
// and update this file alongside lib/types.ts).

import type { StateDirEntry } from "../lib/types";

export function makeStateDirEntry(
  overrides: Partial<StateDirEntry> = {}
): StateDirEntry {
  return {
    source: "linkedin",
    state_key: "test-brief",
    // Phase 1B: state_dir removed from StateDirEntry wire shape.
    runtime_state_present: false,
    runtime_state_corrupt: false,
    latest_run: null,
    brief_id_from_run: null,
    brief_path_from_worker: null,
    worker_json_present: false,
    worker_pid: null,
    worker_alive: null,
    worker_mode: null,
    worker_input_mode: null,
    resumable: null,
    worker_state: "missing",
    heartbeat_age_s: null,
    brief_role_title: null,
    brief_linkedin_project: null,
    brief_drift_since_last_run: null,
    attempt_health: null,
    work_unit_progress: null,
    run_stalled: false,
    stall_failure_kind: null,
    // Phase 1C: default to authored_brief so existing fixtures continue to
    // surface in frontOfFile / filedAway. Tests that need orphans / archived
    // entries override `kind` explicitly.
    kind: "authored_brief",
    ...overrides
  };
}
