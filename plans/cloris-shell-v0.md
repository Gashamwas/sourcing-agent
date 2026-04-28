# Cloris Shell V0

Status: ready-to-implement
Owner: Codex
Last updated: 2026-04-27

## Problem

We have a Cloris UI spec and a Cloris control-plane spec, but no implementation plan for the first shippable desktop shell. Today sourcing still runs from Python CLIs and inline orchestrators (`linkedin/run.py`, `linkedin/session_orchestrator.py`, `github/session_orchestrator.py`), while canonical runtime state is fragmented across many per-source/per-brief `runtime_state.sqlite3` files (`shared/output_paths.py`, `shared/runtime_state/store.py`).

## Goal

Ship a Cloris shell v0 that can discover runs, launch a detached LinkedIn worker, stop it cleanly, and reopen onto truthful run state without mutating the canonical runtime model.

## Non-goals

- Full Cloris frontend polish or final editorial UI
- Authoring Loop or Run Review implementation
- Cross-process pause semantics
- Run-to-brief pinning or feedback-table schema work
- GitHub launch UI in v0
- Any rewrite of `linkedin/orchestrator.py`, `github/orchestrator.py`, or `shared/runtime_state/store.py`

## Assumptions

- `runtime_state.sqlite3` remains canonical inside each state dir; JSON/JSONL remain derived artifacts.
- The shell is local-first: one app process (`FastAPI` + `pywebview`) and one detached worker process.
- The worker should wrap existing orchestrator flows instead of reimplementing sourcing execution.
- Cloris v0 should expose only LinkedIn launch in the UI. This is deliberate: LinkedIn is the harder, more user-visible path and forces the right control-plane decisions first.
- `away` input mode should not be exposed in Cloris v0. It breaks the background-work thesis and adds control-state complexity we do not need in the first slice.

## Seam

This work should land mostly in a new top-level `cloris/` package, with wrapper-level integration around:

- runtime topology and enumeration: `shared/output_paths.py`, `shared/runtime_state/store.py`
- existing run control paths: `linkedin/session_orchestrator.py`, `github/session_orchestrator.py`
- current lock semantics: `shared/runtime_state/lock.py`
- LinkedIn readiness limits: `linkedin/browser.py`, `linkedin/session_orchestrator.py`

The plan should avoid casual edits to high-risk files. Prefer wrapper files and read-only aggregation over changes inside the current pipelines.

## Proposed change

Build Cloris shell v0 as a thin product shell over the existing sourcing runtime, with four concrete subsystems:

1. **Cloris app package**
   - Add `cloris/cli.py`, `cloris/app.py`, `cloris/api.py`, `cloris/control_plane.py`, `cloris/models.py`, `cloris/worker.py`.
   - `cloris start` launches one local app process that hosts `FastAPI` and opens `pywebview`.
   - The app process is disposable; it can exit without killing an active run.

2. **Product-level aggregation service**
   - Enumerate `output/state/linkedin/*` and `output/state/github/*` using `shared/output_paths.py`.
   - Open each `runtime_state.sqlite3` read-only through `RuntimeStateStore`.
   - Normalize latest-run status, source, brief id, stop reason, resumability, and state-dir metadata into one Cloris read model.
   - This is the product “substrate” from the shell’s perspective. Do not invent a global DB in v0.

3. **Detached LinkedIn worker wrapper**
   - `POST /api/launch/linkedin` spawns a detached subprocess that wraps `linkedin/session_orchestrator.run_day_cycle(...)`.
   - The wrapper owns a `worker.json` sidecar in the state dir with: `pid`, `source`, `brief_id`, `brief_path`, `output_dir`, `run_id` when known, `started_at`, `heartbeat_at`, `mode`, `input_mode`, `launcher_version`.
   - The worker wrapper also enables a shell-owned live console log for GitHub parity if needed later, but v0 does not need GitHub launch.
   - Do not use SQLite as a queue. Spawning a subprocess is the correct v0 launch contract.

4. **Stop / status / resume contract**
   - `GET /api/status` returns the aggregated model over all discovered state dirs.
   - `POST /api/stop/{source}/{brief_id}` resolves the active worker from `worker.json`, sends a graceful termination signal, and reports state transitions.
   - `POST /api/resume/linkedin` launches a new detached worker against the same state dir with `resume=True`.
   - No pause endpoint in v0.

### Winning choices

- **Worker sidecar over DB/lock-only liveness**: use `worker.json`, because `runs.status='running'` can become stale after crashes and the lock file does not identify ownership.
- **Subprocess spawn over DB queue**: spawn detached workers directly. The current runtime model is single-writer per state dir already; queueing in SQLite would blur control and runtime truth.
- **LinkedIn-only launch over dual-source launch**: the harder path should define the shell contract first. GitHub launch can follow once the shell is stable.
- **Concurrent-only UI over exposing `away` mode**: keep the app honest to the background-work thesis in v0.

## Risks

- Multi-DB aggregation can drift into ad hoc per-screen queries if not centralized in one service.
- Stale `worker.json` sidecars can lie unless heartbeat and cleanup rules are explicit.
- LinkedIn readiness is only best-effort before the worker truly attaches and navigates; the Launch Gate must not overclaim.
- Wrapper code may accidentally bypass existing session-governor behavior if it calls the wrong entrypoint.
- Hidden dependency on high-risk files could creep in if the wrapper starts “just patching” orchestrator behavior instead of wrapping it.

## Slices

- [ ] Slice 1: Add `cloris/` package skeleton, CLI entrypoint, and app-process boot path (`FastAPI` + `pywebview`) with no worker control yet.
- [ ] Slice 2: Add aggregation service over discovered state dirs, plus status models and `GET /api/status`.
- [ ] Slice 3: Add detached LinkedIn worker wrapper and `worker.json` sidecar lifecycle; wire `POST /api/launch/linkedin`.
- [ ] Slice 4: Add graceful stop/resume endpoints and stale-worker detection rules.
- [ ] Slice 5: Add minimal shell UI screens for status, launch, active-run banner, and stop. Keep visual scope intentionally narrow; this is a shell, not the full Cloris UI buildout.

## Test strategy

- Narrowest relevant existing test bands to run first:
  - `pytest tests/test_output_paths.py -q`
  - `pytest tests/test_runtime_state.py -q`
  - `pytest tests/test_linkedin_session_orchestrator.py -q`
- Tests to add/strengthen:
  - `pytest tests/test_cloris_worker_sidecar.py -q`
  - `pytest tests/test_cloris_status_aggregation.py -q`
- Full-suite gate before declaring done:
  - `make validate`

## Open questions

- Whether `FastAPI` should be served via embedded `uvicorn` in-process or via `FastAPI`’s testable ASGI app plus a minimal server wrapper. I favor embedded `uvicorn` because it is straightforward and keeps the app process simple.
- Whether Cloris should expose GitHub runs in `status` immediately even if launch is LinkedIn-only. I think yes; the aggregator should be source-generic from day one.

## Decisions

- 2026-04-27 — Build the shell around wrappers, not orchestrator rewrites — Lower risk and consistent with repo norms.
- 2026-04-27 — Expose LinkedIn launch only in v0 — It is the forcing function for detached worker, readiness, and liveness semantics.
- 2026-04-27 — Do not expose `away` mode in v0 — It contradicts the background-work posture and complicates control-state handling.
- 2026-04-27 — No pause in v0 — Current pause semantics are intra-process only and should not be papered over with a fake API.

## Follow-ups (not in this plan)

- GitHub launch UI once the worker and sidecar contract are stable.
- Full Cloris shell visual design pass once the control plane is real.
- Run Review read models over canonical runtime state.
- Authoring Loop orchestration over `shared/preflight_v2.py`.
