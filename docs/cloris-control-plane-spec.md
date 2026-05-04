# Cloris Control-Plane Spec

Last updated: 2026-04-27
Status: draft

This document is the runtime/control-plane companion to `docs/cloris-ui-spec.md`.

The UI spec defines what Cloris should feel like. This document defines the operational substrate and contracts the app shell must respect so the UI stays honest.

## 1. Scope

This document is about:

- runtime-state topology
- worker lifecycle
- state discovery and aggregation
- launch / stop / status contracts
- source-specific readiness semantics
- UI-facing control states

It is not about:

- typography, color, or visual design
- copywriting beyond operational-state rules
- the broader recruiting stack outside this repo

## 2. Runtime Topology As It Exists Today

### 2.1 Canonical truth is local, per state directory

There is no single global sourcing database.

Each source/brief state directory owns its own canonical SQLite file:

- LinkedIn pipeline sets `self.runtime_db_path = self.output_dir / "runtime_state.sqlite3"` in `linkedin/orchestrator.py:181-201`
- GitHub pipeline sets `self.runtime_db_path = self.output_dir / "runtime_state.sqlite3"` in `github/orchestrator.py:83-100`
- each pipeline instantiates its own `RuntimeStateStore` from that path in `linkedin/orchestrator.py:242-256` and `github/orchestrator.py:138-150`

State directories are source-scoped and key-scoped:

- root per source: `shared/output_paths.py:103-107`
- LinkedIn keying and directory resolution: `shared/output_paths.py:146-157`, `shared/output_paths.py:198-212`
- GitHub keying and directory resolution: `shared/output_paths.py:160-167`, `shared/output_paths.py:215-228`

Implication:

Cloris is one product over many canonical stores, not one product over one global store.

### 2.2 Canonical vs projections

Inside each state dir:

- `runtime_state.sqlite3` is canonical
- JSON / JSONL artifacts are projections or compatibility artifacts

The runtime model itself is centered on:

- `runs`
- `work_units`
- `candidates`
- `candidate_attempts`
- `events`
- `side_effects`

in `shared/runtime_state/store.py:73-202`.

Compatibility projections are rebuilt from that canonical runtime state in `shared/runtime_state/projections.py:1-180`.

Implication:

Cloris should read canonical SQLite first and only fall back to projections when it explicitly needs legacy-shaped read models.

## 3. Product-Level Read Model

Because Cloris is one product over many state dirs, it needs a product-level read model above per-run/per-brief stores.

### 3.1 Enumeration contract

Cloris must enumerate candidate state dirs by walking:

- `output/state/linkedin/*`
- `output/state/github/*`

using the source roots defined by `shared/output_paths.py:103-107` and the per-source resolve functions in `shared/output_paths.py:198-228`.

The product shell must not assume a single DB.

### 3.2 Aggregation layer

The app should build a read-only aggregation layer that:

- discovers state dirs
- opens each `runtime_state.sqlite3`
- reads latest runs using `RuntimeStateStore.get_latest_run()` from `shared/runtime_state/store.py:347-358`
- reads run history using `list_runs()` from `shared/runtime_state/store.py:360-371`
- normalizes source-specific summaries into one product-shaped list

This aggregation layer is the real “one substrate” from the product’s point of view.

It is a Cloris-owned read model, not a change to the canonical runtime schema.

### 3.3 UI consequence

The following surfaces depend on this aggregator:

- Ambient Home
- recent runs
- cross-brief recent activity
- run picker / reopen
- any source-agnostic Run Review entry list

Without this layer, the UI will collapse into a browser over directories and files.

## 4. Worker Model

### 4.1 Worker ownership

The worker owns active execution.

Cloris should wrap the existing session orchestration entrypoints:

- LinkedIn day-cycle orchestration: `linkedin/session_orchestrator.py:310-479`
- GitHub day-cycle orchestration: `github/session_orchestrator.py:81-157`

The `main()` argparse wrappers in those files (`linkedin/session_orchestrator.py:522-601`, `github/session_orchestrator.py:164-204`) are CLI shims, not the orchestration logic themselves.

### 4.2 Lock boundary

The runtime lock is not held by the session orchestrators.

It is acquired inside the actual pipelines:

- LinkedIn: `linkedin/orchestrator.py:845-858`
- GitHub: `github/orchestrator.py:194-204`

The lock object is per output directory:

- constructed with `RuntimeStateLock(self.output_dir)` in `linkedin/orchestrator.py:242-243`
- constructed with `RuntimeStateLock(self.output_dir)` in `github/orchestrator.py:138-139`

Implication:

“Wrap the session orchestrator” is the right product move, but the control-plane contract must still respect the deeper lock-acquire boundary inside the pipelines.

### 4.3 Worker detachment

The worker must run out of process.

This is required because current execution is inline:

- LinkedIn `_launch()` directly calls `asyncio.run(...)` in `linkedin/run.py:160-194`
- GitHub pipeline runs inline via the orchestrator/session wrapper path in `github/session_orchestrator.py:68-75`, `github/orchestrator.py:167-287`

Closing the app window must not terminate a run.

## 5. Worker Sidecar Contract

SQLite alone is not enough to tell whether a worker is alive.

Reason:

- `start_run()` inserts a row with `status='running'` in `shared/runtime_state/store.py:245-325`
- `finish_run()` clears it only on orderly completion/failure in `shared/runtime_state/store.py:327-338`

A crashed worker can leave a stale running row behind until reconciliation.

### 5.1 Required sidecar

Each active state dir should also contain a Cloris-owned sidecar file, e.g. `worker.json`.

Minimum fields:

- `pid`
- `source`
- `brief_id`
- `brief_path`
- `output_dir`
- `run_id`
- `started_at`
- `heartbeat_at`
- `mode`
- `input_mode`
- `launcher_version`

### 5.2 Sidecar responsibility

The worker updates `heartbeat_at` periodically.

The app uses the sidecar to answer:

- is a worker process probably alive?
- which run row should the UI bind to?
- is this an active run, stale run, or crashed run awaiting reconciliation?

### 5.3 Lock relationship

The lock file itself cannot answer “who owns the run?” because `RuntimeStateLock` only exposes advisory flock semantics (`shared/runtime_state/lock.py:16-25`).

The OS will release the flock on process death. That means there is no stale-lock cleanup problem, but there is also no owner identity available from the lock file alone.

The sidecar fills that gap.

## 6. Launch Contract

### 6.1 Launch action

When the user clicks Launch, the app does not write a job into SQLite.

It spawns a detached subprocess with a Cloris-owned wrapper that:

- resolves source + brief + state dir
- writes/initializes the worker sidecar
- delegates to the appropriate session orchestrator

SQLite remains the canonical run state store, not the work queue.

### 6.2 Why not SQLite as queue

The current runtime model is already single-writer per state dir:

- lock acquisition in `shared/runtime_state/lock.py:16-25`
- active write paths in the pipelines

Using the canonical runtime DB as a queue would blur:

- product control intent
- active run state
- reconciliation semantics

Cloris should keep those separate.

## 7. Stop / Pause / Resume Contract

### 7.1 Stop exists now

Graceful stop already exists as a process-level concept:

- LinkedIn session orchestrator traps SIGINT/SIGTERM and treats first signal as graceful shutdown in `linkedin/session_orchestrator.py:328-338`
- GitHub session orchestrator does similar SIGINT handling in `github/session_orchestrator.py:93-101`

Cloris can map “Stop run” to process signaling in v1.

### 7.2 Pause does not exist cross-process yet

Today, LinkedIn pause/resume is intra-process only:

- `pause_requested` / `resume_event` are `asyncio.Event` instances created in `linkedin/session_orchestrator.py:168-175`
- they are used for decoy interleaving inside the same process

This is not a cross-process control protocol.

### 7.3 V1 recommendation

V1 control-plane contract should support:

- `launch`
- `status`
- `stop`
- `resume` by starting a new worker against the existing state dir

It should **not** promise a true out-of-process pause unless that protocol is explicitly built.

## 8. Readiness Semantics

### 8.1 Brief readiness

There is a real brief-level distinction today:

- briefs needing preflight vs runnable structured briefs in `shared/brief_loader.py:142-149`
- preflight itself is still prompt assembly / parse / merge logic in `shared/preflight_v2.py:101-170`

Implication:

Authoring readiness and operational readiness are separate checks.

### 8.2 LinkedIn readiness is only partly probeable

The session orchestrator can verify CDP reachability:

- `linkedin/session_orchestrator.py:344-369`

But real auth/session validity only emerges when the browser path inspects live LinkedIn state:

- target page selection skips `/login` pages in `linkedin/browser.py:177-186`
- emergency recovery detects login redirect and raises session-expired in `linkedin/browser.py:446-451`

Implication:

LinkedIn Launch Gate cannot honestly promise “fully ready” from a pure preflight probe today.

It can promise:

- Chrome/CDP reachable
- a Recruiter-ish page is discoverable
- config/env look present

But session validity remains best-effort until the worker actually attaches and navigates.

### 8.3 GitHub readiness

GitHub readiness is more probeable because it is API-driven, not browser-driven.

The main unresolved readiness risks are:

- token/config presence
- output dir / state dir availability
- lock conflict

## 9. UI-Facing Control States

The UI spec defines calm vs high-stakes voice behavior. The control plane needs a more operational state taxonomy.

### 9.1 Quiet background

Definition:

- worker alive
- run active
- no user action required
- machine remains usable

Examples:

- LinkedIn concurrent mode
- GitHub active session

### 9.2 Input takeover

Definition:

- run active
- Cloris is intentionally using the user’s input devices
- not a failure state, but not background in the human sense

Evidence in current code:

- LinkedIn exposes `input_mode="away"` and describes it as taking over the real mouse/keyboard in `linkedin/run.py:143-147`
- session orchestrator exposes `--input-mode {concurrent, away}` in `linkedin/session_orchestrator.py:545-549`

Implication:

This must be its own UI state. It cannot inherit the same calm/background posture as concurrent mode.

### 9.3 Transitional

Definition:

- run starting
- run finishing
- resume beginning
- dormant period entered between sessions

These states are eligible for sparse Cloris voice if they are not urgent.

### 9.4 Attention required

Definition:

- Cloris cannot proceed without a user intervention, but the system is not internally broken

Examples:

- another run already active for the same state dir
- LinkedIn needs re-authentication
- API credits exhausted
- daily/session budget reached

Current evidence:

- lock conflict path in `shared/runtime_state/lock.py:16-25`, `linkedin/orchestrator.py:850-858`, `github/orchestrator.py:196-204`
- LinkedIn session redirect in `linkedin/browser.py:446-451`
- LinkedIn governor/status messaging in `linkedin/session_orchestrator.py:386-456`

### 9.5 High-stakes / correctness risk

Definition:

- internal state may be wrong, incomplete, or unsafe to continue from without explanation

Examples:

- illegal lifecycle transition
- unreadable runtime DB
- stale run/worker mismatch
- brief modified mid-run without run pinning

These states get direct operational copy only.

## 10. Status Contract

`status` must be a first-class control-plane operation.

It should report, per discovered state dir:

- source
- brief id
- brief path if known
- latest run id
- latest run status
- stop reason
- worker liveness from sidecar
- resumability
- input mode

This operation is what lets the window reopen and reconstruct the product view.

## 11. Surface Readiness By Backend Maturity

### 11.1 Buildable now with wrapper/backend work

- Launch Gate
- Ambient Home
- live status / monitor shell
- run picker / resume

### 11.2 Buildable after control-plane additions

- Run Review, once Cloris-owned read models over canonical runtime state exist

### 11.3 Blocked on deeper backend work

- full Authoring Loop, because current preflight code is mostly prompt assembly / parse / merge (`shared/preflight_v2.py:101-170`)
- full Next Run Learning, because current cited machinery is prompt-building context only (`shared/brief_iteration.py:862-910`) and still needs feedback storage + run-to-brief pinning

## 12. V1 Recommendations

For v1, Cloris should commit to:

- product-level aggregation over per-state-dir SQLite stores
- detached worker subprocesses
- worker sidecar metadata
- launch / status / stop / resume
- LinkedIn concurrent mode as the default
- explicit `input takeover` treatment when `away` mode is selected

For v1, Cloris should avoid promising:

- true cross-process pause
- perfect LinkedIn auth verification before launch
- full authoring loop maturity if only prompt plumbing exists

## 13. Relationship To The UI Spec

`docs/cloris-ui-spec.md` should remain the clean product/design document.

This document is the implementation-facing runtime companion. When the two conflict:

- product mood and visual rules come from the UI spec
- runtime truth, liveness, lock, and aggregation constraints come from this control-plane spec
