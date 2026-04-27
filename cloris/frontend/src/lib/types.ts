// Wire types for the Cloris HTTP surface.
//
// Source of truth: cloris/models.py. Keep these literals byte-identical with
// the pydantic models there. The slice tags exist on every payload so the
// client can detect contract version skew without re-typing the literal at
// every consumption site.

export type Source = "linkedin" | "github";

export type WorkerState = "missing" | "alive" | "stale";

export type StopResponseState = "stopping" | "missing" | "stale";

export interface RunSummary {
  id: number | null;
  status: string | null;
  stop_reason: string | null;
  mode: string | null;
  started_at: string | null;
  ended_at: string | null;
}

export interface StateDirEntry {
  source: Source;
  state_key: string;
  state_dir: string;
  runtime_state_present: boolean;
  latest_run: RunSummary | null;
  brief_id_from_run: string | null;
  brief_path_from_worker: string | null;
  worker_json_present: boolean;
  worker_pid: number | null;
  worker_alive: boolean | null;
  worker_mode: string | null;
  worker_input_mode: string | null;
  resumable: boolean | null;
  worker_state: WorkerState;
}

export interface StatusResponse {
  slice: "v0-shell-slice-4";
  entries: StateDirEntry[];
}

export interface LaunchResponse {
  slice: "v0-shell-slice-3";
  source: "linkedin";
  input_mode: "concurrent";
  pid: number;
  state_dir: string;
  worker_json_path: string;
}

export interface ResumeResponse {
  slice: "v0-shell-slice-4";
  source: "linkedin";
  mode: "resume";
  input_mode: "concurrent";
  pid: number;
  state_dir: string;
  worker_json_path: string;
}

export interface StopResponse {
  slice: "v0-shell-slice-4";
  source: Source;
  state_key: string;
  state_dir: string;
  worker_state: StopResponseState;
  pid: number | null;
}
