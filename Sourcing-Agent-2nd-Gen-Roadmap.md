# Sourcing Agent Roadmap: From First-Gen Autonomy to Second-Gen System

## Goal

Evolve the agent from a powerful but brittle autonomous workflow into a system that is:

- failure-aware
- interruption-safe
- auditable
- modular
- easier to extend
- safer to operate in production

The objective is not to rebuild everything. It is to keep the current strengths while tightening the execution model underneath them.

This roadmap is ordered by dependency and operational risk, not by calendar estimates.

---

## Roadmap Status

As of the refactor-closure phase, this roadmap is complete.

The implemented sequence ended up looking like this:

- Phase 0: contract freeze and characterization coverage
- Phase 1: shared failure and retry semantics
- Phase 2A/2B: canonical runtime-state store plus compatibility projections
- Phase 2C: GitHub runtime-state proving slice
- Phase 2D: LinkedIn runtime-state readiness boundary
- Phase 3/4: shared candidate execution engine across GitHub and LinkedIn
- Phase 5: boundary-first adapter decomposition
- Phase 6: production safety hardening
- Closure pass: runtime-state-first enforcement, shared bridge/artifact contracts, operator runbook, and roadmap freeze

That means the architecture described below is no longer aspirational. It is the
current operating model for normal GitHub and LinkedIn runs.

What remains after this document is not more refactor debt. It is product work:

- stronger LinkedIn search intelligence and in-string experimentation
- historical engagement/prior-touch awareness
- richer LinkedIn filter surfaces
- more explicit pedigree and trajectory-quality modifiers

---

## What “Second-Generation” Means Here

A second-generation version of this agent should have:

- one canonical brief and policy contract
- one canonical candidate lifecycle
- one shared failure model across all judge/parser/orchestrator layers
- one shared retry classification model across network/model/browser failures
- one durable source of truth for candidate state
- clean separation between acquisition, judgment, persistence, and side effects
- strong regression coverage around operational behavior
- explicit safety boundaries for network access, browser actions, and retries

---

## Current Strengths to Preserve

- Multi-stage evaluation flow
- Cross-session resume capability
- Brief-driven behavior
- Multi-source sourcing across LinkedIn and GitHub
- Bias controls and operational artifacts
- High-agency autonomous workflow design

These are real advantages and should remain intact through the refactor.

---

## Phase 0: Freeze Contracts and Capture Current Behavior (Completed)

### Objective
Stabilize what the system is allowed to mean before changing how it runs.

### Why
The current codebase has strong ideas but a lot of implicit coupling. Refactoring without fixed contracts will turn every migration into an argument about what the system "really" does.

### Deliverables
- Freeze the canonical contracts for:
  - brief/policy shape
  - decision enums
  - failure enums
  - candidate lifecycle states
  - event vocabulary
- Stop expanding compatibility bridges except where they are strictly needed for migration safety
- Add characterization tests around the current high-value behaviors:
  - resume
  - dedup
  - parser/judger outputs
  - save classification
  - restart semantics
- Make "current behavior" explicit enough to port source by source

### Success Criteria
- We can say exactly what a parser, judger, orchestrator, and state layer are allowed to emit
- Major refactors can be evaluated against explicit contracts rather than memory
- A test harness exists before major runtime/state changes begin

---

## Phase 1: Stabilize Failure Semantics and Retry Classification (Completed)

### Objective
Make all failure cases explicit, non-destructive, and consistently classified as retryable or terminal.

### Why
Lifecycle design depends on this. If retry behavior is still split across clients, parsers, and orchestrators, candidate-state design will stay ambiguous.

### Deliverables
- Introduce a shared failure model:
  - `PARSE_FAILURE`
  - `JUDGMENT_FAILURE`
  - `RECOVERABLE_ERROR`
  - `TERMINAL_ERROR`
- Define one shared retry classification layer for:
  - LLM/provider failures
  - network failures
  - browser/session failures
  - parsing failures
- Ensure parsers return explicit failure decisions instead of terminal business outcomes like `REJECT` or `FACIAL_SKIP`
- Ensure orchestrators never treat failures as true candidate judgments
- Normalize GitHub and LinkedIn behavior to the same failure policy

### Success Criteria
- No malformed model output can silently produce `SAVE`, `REJECT`, or terminal skip behavior
- Retryable vs terminal failure policy is explicit and shared
- Failure decisions are auditable and consistent across all paths

---

## Phase 2: Introduce a Canonical Candidate Lifecycle and One Durable Source of Truth (Completed)

### Objective
Make candidate execution state explicit and durable in the same workstream.

### Why
Lifecycle without a real state store still leaves too much state inferred from artifacts, progress files, and in-memory sets. These two concerns should move together.

### Deliverables
- Define a canonical lifecycle such as:
  - `discovered`
  - `snippet_extracted`
  - `facial_started`
  - `facial_terminal`
  - `full_started`
  - `full_terminal`
  - `failed_retryable`
  - `failed_terminal`
- Choose one canonical state store for durable candidate execution state
- Keep JSONL outputs as artifacts/logs, not as state reconstruction inputs
- Make dedup read from the canonical state store only
- Make restart/resume logic operate against that same source
- Persist candidate/work-unit/event state explicitly rather than reconstructing from `snippets.jsonl`, `facial_judgments.jsonl`, and `final.jsonl`

### Success Criteria
- A candidate cannot become permanently deduped before reaching a true terminal state
- Resume behavior is deterministic
- Interruptions mid-run do not silently lose candidates
- Rebuilding execution state no longer depends on artifact interpretation

---

## Phase 3: Build the Shared Execution Engine and Port GitHub First (Completed)

### Objective
Prove the new execution model on the lower-risk source first.

### Why
GitHub already fits normalized evidence more naturally and does not depend on browser recovery. It is the best place to validate the new engine before moving the more operationally fragile adapter.

### Deliverables
- Create a shared execution engine with explicit stages such as:
  - discover
  - acquire evidence
  - evaluate
  - persist
  - side effects
- Move shared retry, dedup, and checkpoint semantics into the engine
- Port GitHub to the engine while preserving:
  - current search/adaptation behavior
  - query validation and repair
  - exhaustion tracking
  - GitHub-specific enrichment strengths

### Success Criteria
- GitHub runs end-to-end through the new lifecycle/state model
- GitHub resume and dedup no longer depend on source-specific progress conventions
- Engine abstractions are real and tested, not just described

---

## Phase 4: Port LinkedIn onto the Shared Engine (Completed)

### Objective
Move LinkedIn onto the same execution principles without destabilizing the sourcing behavior that already works.

### Why
LinkedIn is the more operationally fragile adapter. It should inherit a proven state/runtime model rather than define one.

### Deliverables
- Adapt browser extraction and profile acquisition to emit normalized evidence into the shared engine
- Move per-candidate state, dedup, and restart/resume to the canonical state store
- Preserve current brief-driven strategy and adaptation logic
- Keep session/decoy choreography as thin wrappers where needed during migration, rather than treating them as the primary execution model

### Success Criteria
- LinkedIn candidate crash/retry/resume behavior is deterministic
- Browser adapters no longer own candidate truth
- Current sourcing behavior is preserved while the runtime substrate simplifies

---

## Phase 5: Separate Core Concerns into Cleaner Layers (Completed)

### Objective
Untangle orchestration logic into clearer layers once both sources are running through the shared engine.

### Why
Right now, browser automation, judgment logic, persistence, and recovery behavior are tightly coupled. This gets easier to separate cleanly after the lifecycle/store migration is real.

### Target Architecture
Split responsibilities into modules like:

- `policy`
  - brief interpretation
  - permanent filters
  - geography rules
  - save classification
- `planner`
  - strategy formation
  - adaptation
  - query validation
- `acquisition`
  - browser scraping
  - GitHub fetching
  - snippet/profile extraction
- `evaluation`
  - facial/full judgment
  - bias monitoring
  - decision normalization
- `state`
  - candidate lifecycle
  - progress tracking
  - dedup
  - restart/resume
- `side_effects`
  - LinkedIn save actions
  - logging
  - artifact writing
  - outbound fetches
  - exports / ATS / outreach hooks
- `runtime`
  - governor
  - session control
  - browser recovery
  - observability

### Success Criteria
- Orchestrators become thinner and easier to reason about
- Business rules can be tested without requiring browser execution
- New sourcing surfaces can reuse shared execution primitives

---

## Phase 6: Harden Production Safety Boundaries (Completed)

### Objective
Make the system safe under real operating conditions once the execution path is consolidated.

### Deliverables
- Enforce governor lifecycle through explicit runtime hooks rather than scattered wrapper logic
- Harden URL fetching against SSRF and redirect abuse
- Add clearer guardrails around browser recovery and save actions
- Make side effects idempotent where possible
- Reduce import-time fragility and hidden initialization assumptions

### Success Criteria
- Operational safety rules are active in the real pipeline, not just conceptually present
- Hostile or malformed external input cannot trigger unsafe network behavior
- Long-running sessions fail predictably and recover cleanly

---

## Cross-Cutting Discipline: Expand Regression Coverage Continuously

### Objective
Test the system where it is most likely to break as each migration lands, not as a late cleanup phase.

### Priority Test Areas
- Resume after interruption
- Mid-candidate failure recovery
- Dedup correctness
- Parser failure handling
- Failure classification and retry behavior
- Governor enforcement
- Query validation/repair
- Restart-string behavior
- URL blocking and redirect handling
- Save classification consistency
- History/state migration behavior

### Success Criteria
- A passing test suite means something operationally meaningful
- Each refactor adds coverage for at least one ugly-path failure mode
- High-risk regressions are caught before production use

---

## Phase 7: Unify Shared Execution Patterns Across LinkedIn and GitHub (Completed)

### Objective
Reduce branch-specific architecture drift after both sources are running on the same execution substrate.

### Deliverables
- Shared decision/failure handling primitives
- Shared candidate-state abstractions
- Shared persistence interfaces
- Shared retry/dedup semantics
- Shared metrics and event vocabulary
- Clear adapter boundaries so new sources can plug into the same engine

### Success Criteria
- LinkedIn and GitHub feel like two adapters on top of one core engine
- New sources can be added without re-inventing orchestration logic

---

## Suggested Execution Order

1. Freeze contracts and characterization coverage
2. Stabilize failure semantics and retry classification
3. Introduce the canonical lifecycle and durable state store together
4. Build the shared execution engine and port GitHub first
5. Port LinkedIn onto the shared engine
6. Separate remaining orchestration concerns into cleaner layers
7. Harden production safety boundaries
8. Unify shared execution architecture across sources

Regression coverage should advance continuously throughout every step above, not as a tail-end phase.

---

## Guiding Principles

- Do not rewrite the whole system at once
- Freeze contracts before moving internals
- Prefer explicit state over inferred state
- Lifecycle and durable state should move together
- Prefer one source of truth over many derived truths
- Treat artifacts as logs, not control state
- Make failures visible, non-terminal by default, and easy to retry
- Prove the new engine on GitHub before moving LinkedIn
- Keep side effects isolated from evaluation logic
- Treat regression coverage as continuous engineering work, not cleanup

---

## Definition of Done for “Second-Generation”

The agent should feel second-generation when:

- failures never masquerade as real judgments
- retryable vs terminal failures are explicit and shared
- interruptions do not lose candidates
- dedup is correct and explainable
- state transitions are explicit
- LinkedIn and GitHub share the same execution principles
- tests cover real operational risks
- adding a new source feels like plugging into a framework, not copying an orchestrator

This definition is now satisfied by the runtime-state, shared execution,
adapter-boundary, and safety layers in the current repo.

## Refactor Closure

The closure pass froze the final operational rules that make this roadmap
complete rather than merely advanced:

- normal GitHub and LinkedIn runs are `runtime_state.sqlite3`-first
- `progress.json`, stage JSONLs, candidate history, and search memory are
  projection-owned compatibility artifacts
- runtime bridges expose an explicit shared contract instead of ad hoc
  source-specific bootstrap behavior
- `tools/runtime_state_admin.py` is the official operator surface for rebuild,
  restart, replay, orphan inspection, and stop-reason inspection
- legacy compatibility remains only for one-time LinkedIn import and offline
  artifact-only utilities such as rejudge/report workflows

Once this phase landed, the roadmap stopped being an active migration sequence.
It became the historical record of how the second-generation architecture was
built.

---

## Post-Roadmap Product Queue

### A. Search Intelligence Phase

The first major post-refactor product phase should improve LinkedIn search
intelligence rather than change the runtime substrate.

Target outcomes:

- replace timid one-step narrowing with explicit multi-variant experimentation
- support aggressive narrowing, sibling precision/recall variants, and
  deliberate commit/revert behavior inside one root string family
- use page-1 and early-page observations as structured adaptation evidence
- persist variant lineage and experiment outcomes in runtime-state

### B. Historical Engagement / Prior-Touch Awareness

Future capability expansion.

Add a candidate engagement layer that can distinguish:

- net new
- previously viewed
- previously messaged
- previously pipelined
- repeatedly resurfaced

Initial value should be prioritization and reporting, not hard exclusion.

### C. LinkedIn Filter Surface Expansion

Future capability expansion.

Expand beyond Boolean keywords to first-class structured filters such as:

- titles
- companies
- skills
- assessments
- seniority / years / other sidebar filters

The advanced search modal should be modeled as a separate supported filter
surface with explicit runtime serialization and resume semantics.

### D. Pedigree / Trajectory-Quality Expansion

Future capability expansion.

Make pedigree and trajectory modifiers more explicit without turning them into
primary gates over actual builder evidence:

- company pedigree tiering
- educational pedigree tiering
- tenure / contract-pattern analysis
- “quality of builder environment” modifiers

---

## Final Note

This is not a roadmap from “bad” to “good.”
It is a roadmap from “impressive first autonomous system” to “credible production architecture.”
The hard part — product intuition, workflow design, and systems intent — is already there.
