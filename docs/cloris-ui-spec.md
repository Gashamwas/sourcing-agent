# Cloris UI Spec

Last updated: 2026-04-27
Status: draft

## 1. Product Thesis

Cloris is the standalone sourcing product for this repo.

For this codebase, Cloris is not a pane in a larger recruiting suite and not a placeholder for a future OS. The repo boundary is explicit: this repo is the Sourcing Agent only, not TA Ops Agent, Rosie, Analytics Hub, or the whole recruiting stack (`AGENTS.md:23-33`).

The product thesis is:

> Cloris does the boring part of sourcing in the background so the recruiter can do the judgment part.

This spec codifies three product commitments for the implementation:

- one agent with specialized surfaces, one shared data layer, one closed loop
- the boring operational work runs in the background; judgment work goes back to humans
- every surface reads from one substrate and writes back to the same substrate

Inside this repo, that shared substrate is the sourcing runtime layer centered on `runtime_state.sqlite3` (`shared/runtime_state/store.py:73-120`).

## 2. Form Factor

Cloris is a local desktop app with a Python-first stack:

- app shell: `pywebview`
- local API/UI host: `FastAPI`
- worker: detached Python subprocess
- frontend: Svelte + hand-written CSS

Reason:

- current execution is Python-native and inline today in `linkedin/run.py:160-194` and `github/orchestrator.py:167-287`
- there was no existing JS frontend or desktop-runtime investment before the Cloris shell (`requirements.txt:1-7`, `pyproject.toml:1-7`)
- the implementation-facing spec cares about typography, editorial layout, and calm materiality, not about a JS-heavy desktop ecosystem

The worker must outlive the window. Closing the UI must not kill an active sourcing run.

## 3. Process Model

### 3.1 App process

One process owns:

- embedded `FastAPI` server
- `pywebview` native window
- local asset serving for the frontend bundle

This process is disposable. The user can close the window and reopen later without ending a run.

### 3.2 Worker process

One detached Python subprocess owns the active run.

It should wrap the current session orchestrators rather than bypass them:

- LinkedIn: `linkedin/session_orchestrator.py:522-601`
- GitHub: `github/session_orchestrator.py:164-204`

The worker is the only active writer for a running state directory. The UI/API process should be read-only against active run state whenever possible.

### 3.3 State discovery on reopen

On reopen, Cloris reconstructs state from:

- source-scoped state dirs in `shared/output_paths.py:198-228`
- canonical run records from `shared/runtime_state/store.py:245-358`
- compatibility projections only when needed for legacy-shaped read models (`shared/runtime_state/projections.py:1-180`)
- worker sidecar metadata (`worker.json`, new) for PID/liveness, because a crashed worker can leave a run row stuck at `status='running'` until reconciliation

## 4. Canonical UX Rules

### 4.1 Editorial, not dashboard-native

Cloris must not look like default SaaS software.

Use editorial primitives instead of dashboard primitives:

- numbered sections
- prose-width columns
- hairline rules
- pullquote-like emphasis blocks
- mono metadata labels
- generous vertical rhythm

Avoid:

- dense left-nav dashboard chrome
- shadow-card grids as the default organizing primitive
- generic toast-heavy product language
- “AI-native,” “powered by,” and other costume copy

### 4.2 Cloris is the subject

Voice, when present, is about Cloris, not about the user:

- good: “Let me find my glasses.”
- bad: “Don’t forget to take a break, dear.”

The governing test is explicit in the spec:

> Is this Cloris being a person, or is this Cloris being weird about the user?

### 4.3 Voice is sparse

Lore/character voice appears:

- rarely
- on long operations, not short ones
- at transitions, not inside focused work
- never in high-stakes moments
- never explained

### 4.4 High-stakes moments are plain

In broken, blocked, or correctness-sensitive states, Cloris drops the grandmother voice entirely.

Examples:

- active lock conflict from `shared/runtime_state/lock.py:16-25`
- fatal runtime error path in `linkedin/orchestrator.py:1252-1266`
- GitHub fatal pipeline error path in `github/orchestrator.py:256-261`
- browser/session expiry and recovery failures
- state inconsistency or unreadable DB

These states must be direct, legible, and actionable.

## 5. Design Tokens

Use the Cloris tokens directly as the base visual system:

- `--cream: #f5efe1`
- `--cream-deep: #ebe2cd`
- `--mustard: #d4a53a`
- `--mustard-deep: #b88a28`
- `--wood: #6b4a2b`
- `--wood-deep: #4a3220`
- `--peach: #e39a76`
- `--peach-deep: #c67d5a`
- `--ink: #2a1f14`
- `--ink-soft: #5c4a38`

Source: the repo-local Cloris frontend tokens in `cloris/frontend/src/styles/tokens.css`.

Typography:

- body / primary reading: Fraunces
- display accents / italic emphasis: Instrument Serif
- metadata / labels / section numbering: JetBrains Mono

Bundle fonts locally. Do not depend on Google-hosted fonts in production. The current bundles live under `cloris/frontend/public/assets/fonts/` and `cloris/frontend/dist/assets/fonts/`.

Surface treatment:

- paper-grain texture layer
- rules and borders over shadows
- warm contrast, never pure black on pure white

## 6. Information Architecture

Cloris has five product surfaces.

### 6.1 Authoring Loop

Purpose:

- turn a role / JD / hiring intent into a runnable sourcing brief
- let the user review and edit what Cloris understood

Why this is one loop:

- preflight already assumes machine draft + human review in `shared/preflight_v2.py:9-17`
- brief loading already distinguishes runnable V2 briefs from briefs that still need preflight in `shared/brief_loader.py:142-149`

UI shape:

- calm, document-like working surface
- step framing without wizard-hell
- prose summaries with structured fields beneath the surface

### 6.2 Launch Gate

Purpose:

- answer one question: is this run actually ready to start?

UI shape:

- a single readiness page
- clear blockers and remediations
- no mixing with authoring

Key backing systems:

- brief readiness from `shared/brief_loader.py`
- runtime lock from `shared/runtime_state/lock.py:16-25`
- LinkedIn browser/session readiness from `linkedin/session_orchestrator.py:344-369`
- env/config loading from `shared/config.py:11-35`

### 6.3 Ambient Home

Purpose:

- default landing state when no action is urgently required

UI shape:

- recent runs
- current run summary if active
- quiet “working in the background” posture
- monitor details available, but not the default emotional tone

This is where Cloris feels most like herself.

### 6.4 Run Review

Purpose:

- show who Cloris surfaced, why, and what happened

UI shape:

- editorial candidate entries, not tables-first
- rationale-forward cards
- save/reject outcome summaries
- reviewer marks and later feedback attachment

Data source:

- canonical runtime state, not `output/` artifacts

### 6.5 Next Run Learning

Purpose:

- convert reviewer feedback into the next brief revision

UI shape:

- feedback summary
- proposed brief diff
- explicit approval before the next version becomes runnable

Backing machinery:

- brief iteration context builder in `shared/brief_iteration.py:862-910`
- future feedback table and run-to-brief pinning prerequisites

## 7. Screen Primitives

These are the reusable frontend primitives Cloris should be built from.

### 7.1 Section header

- mono section number
- serif headline
- optional short framing sentence

### 7.2 Rule block

- bordered or ruled container for operational details
- used for readiness checks, process details, and diff summaries

### 7.3 Prose banner

- high-signal status block written as typeset prose
- used for completions, resumable interruptions, and contextual summaries

### 7.4 Candidate entry

- candidate name / source / confidence / decision
- rationale as readable prose
- evidence and actions below the fold

### 7.5 Marginal metadata

- mono labels for timestamps, run ids, source, status, and counts

## 8. UI State Taxonomy

Every user-facing state must be classified before copy is written.

### 8.1 Quiet background

Examples:

- run active and healthy
- routine long-running processing
- no user action needed

Allowed voice:

- sometimes
- only at transitions or long-run openings/completions

### 8.2 Transitional

Examples:

- run started
- run completed
- run resumed cleanly after interruption

Allowed voice:

- yes, sparingly

### 8.3 Attention required

Examples:

- LinkedIn needs re-authentication
- another run is already active
- provider degradation persisted long enough to matter

Allowed voice:

- no character garnish
- clear explanation + remediation only

### 8.4 High stakes / correctness risk

Examples:

- illegal lifecycle transition (`shared/runtime_state/store.py:41-50`, `shared/runtime_state/store.py:1688-1694`)
- unreadable or corrupted runtime DB
- brief modified mid-run before pinning exists
- unrecovered browser/session failure

Allowed voice:

- none
- this copy should read like a precise operator message

## 9. Live Run Philosophy

The live monitor exists, but it is not the product’s home screen.

Reason:

- Cloris is defined by background work, not by making the user supervise her
- LinkedIn already models long autonomous sessions and dormant periods in `linkedin/session_orchestrator.py:310-479`

Implication:

- default view = ambient summary
- deep monitor = opened on demand
- monitor page can expose more structured operational state without forcing the whole app into dashboard grammar

## 10. Source Support

Cloris is one product with two sourcing backends:

- LinkedIn
- GitHub

The UX should feel unified above the runtime substrate, but LinkedIn deserves first-class treatment in v1 because:

- it is the more complex and user-visible source path
- it has browser/session constraints GitHub does not
- it already has richer session orchestration (`linkedin/session_orchestrator.py:2-15`) than GitHub’s simpler cycle (`github/session_orchestrator.py:2-12`)

## 11. Implementation Guidance

Frontend implementation should follow these rules:

- use Svelte
- no React
- no Tailwind
- no shadcn
- no visual component library imposing default SaaS patterns
- hand-write CSS against the Cloris tokens
- treat every label, status, and empty state as part of the design system

Backend/UI integration rules:

- active run launch spawns a detached worker subprocess
- UI/API process reads canonical state from `runtime_state.sqlite3`
- the worker is the active writer for the run
- use process signals for stop/pause semantics, not DB queue writes

## 12. Prerequisites For Full-Value UX

These are not UI ideas; they are required system conditions for the UX to be correct.

- run-to-brief pinning on `runs`, because current rows only store `brief_id` (`shared/runtime_state/store.py:82-95`)
- first-class feedback artifact table
- worker sidecar metadata for liveness / heartbeat
- UI-facing read models over runtime state for review surfaces

## 13. Non-goals

This spec does not define:

- cross-product navigation for a larger recruiting OS
- ATS-wide workflow surfaces
- Analytics Hub, Rosie, or TA Ops features
- hosted multi-tenant infrastructure

Those are outside this repo and outside this version of Cloris.
