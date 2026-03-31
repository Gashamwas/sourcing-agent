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

---

## What “Second-Generation” Means Here

A second-generation version of this agent should have:

- one canonical candidate lifecycle
- one shared failure model across all judge/parser/orchestrator layers
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

## Phase 1: Stabilize Failure Semantics

### Objective
Make all failure cases explicit and non-destructive.

### Why
Right now, malformed model output and exceptions can still become terminal candidate outcomes.

### Deliverables
- Introduce a shared failure model:
  - `PARSE_FAILURE`
  - `JUDGMENT_FAILURE`
  - optional future: `RECOVERABLE_ERROR`, `TERMINAL_ERROR`
- Ensure parsers return explicit failure decisions instead of terminal business outcomes like `REJECT` or `FACIAL_SKIP`
- Ensure orchestrators never treat failures as true candidate judgments
- Normalize GitHub and LinkedIn behavior to the same failure policy

### Success Criteria
- No malformed model output can silently produce `SAVE`, `REJECT`, or terminal skip behavior
- Failure decisions are auditable and consistent across all paths

---

## Phase 2: Introduce a Canonical Candidate Lifecycle

### Objective
Replace implicit state transitions with an explicit lifecycle.

### Why
Today, “seen,” “in progress,” and “done” are spread across files and conventions. That makes resume behavior fragile.

### Deliverables
Define a canonical lifecycle such as:

- `discovered`
- `snippet_extracted`
- `facial_started`
- `facial_terminal`
- `full_started`
- `full_terminal`
- `failed_retryable`
- `failed_terminal`

Apply it across both LinkedIn and GitHub.

### Success Criteria
- A candidate cannot become permanently deduped before reaching a true terminal state
- Resume behavior is deterministic
- Interruptions mid-run do not silently lose candidates

---

## Phase 3: Create One Durable Source of Truth

### Objective
Stop using multiple JSONL artifacts as overlapping state stores.

### Why
Artifacts are currently doing double duty as both logs and operational state. That causes subtle bugs.

### Deliverables
- Choose one canonical state store for durable candidate execution state
- Keep JSONL outputs as artifacts/logs, not as state reconstruction inputs
- Make dedup read from the canonical state store only
- Make restart/resume logic operate against that same source

### Success Criteria
- `snippets.jsonl`, `facial_judgments.jsonl`, and `final.jsonl` are no longer silently driving lifecycle state
- Rebuilding execution state no longer depends on artifact interpretation

---

## Phase 4: Separate Core Concerns

### Objective
Untangle orchestration logic into clearer layers.

### Why
Right now, browser automation, judgment logic, persistence, and recovery behavior are tightly coupled.

### Target Architecture
Split responsibilities into modules like:

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
- `policy`
  - brief interpretation
  - permanent filters
  - geography rules
  - save classification

### Success Criteria
- Orchestrators become thinner and easier to reason about
- Business rules can be tested without requiring browser execution
- New sourcing surfaces can reuse shared execution primitives

---

## Phase 5: Harden Production Safety

### Objective
Make the system safe under real operating conditions.

### Deliverables
- Enforce governor lifecycle during actual execution
- Harden URL fetching against SSRF and redirect abuse
- Standardize retry behavior and retryable vs terminal errors
- Reduce import-time fragility
- Add clearer guardrails around browser recovery and save actions

### Success Criteria
- Operational safety rules are active in the real pipeline, not just conceptually present
- Hostile or malformed external input cannot trigger unsafe network behavior
- Long-running sessions fail predictably and recover cleanly

---

## Phase 6: Expand Regression Coverage Around Behavior

### Objective
Test the system where it is most likely to break.

### Priority Test Areas
- Resume after interruption
- Mid-candidate failure recovery
- Dedup correctness
- Parser failure handling
- Governor enforcement
- Query validation/repair
- Restart-string behavior
- URL blocking and redirect handling
- Save classification consistency
- History/state migration behavior

### Success Criteria
- A passing test suite means something operationally meaningful
- High-risk regressions are caught before production use

---

## Phase 7: Unify Shared Execution Patterns Across LinkedIn and GitHub

### Objective
Reduce branch-specific architecture drift.

### Deliverables
- Shared decision/failure handling primitives
- Shared candidate-state abstractions
- Shared persistence interfaces
- Shared retry/dedup semantics
- Shared metrics vocabulary

### Success Criteria
- LinkedIn and GitHub feel like two adapters on top of one core engine
- New sources could be added without re-inventing orchestration logic

---

## Suggested Execution Order

1. Stabilize failure semantics
2. Fix GitHub interruption safety and governor enforcement
3. Fix LinkedIn resume/dedup semantics
4. Harden GitHub outbound URL fetching
5. Introduce canonical lifecycle/state model
6. Move to one durable source of truth
7. Separate orchestration concerns into clearer modules
8. Expand regression coverage
9. Unify shared execution architecture across sources

---

## Guiding Principles

- Do not rewrite the whole system at once
- Prefer explicit state over inferred state
- Prefer parser-layer truth over downstream string sniffing
- Prefer one source of truth over many derived truths
- Treat artifacts as logs, not control state
- Make failures visible, non-terminal by default, and easy to retry
- Keep side effects isolated from evaluation logic

---

## Definition of Done for “Second-Generation”

The agent should feel second-generation when:

- failures never masquerade as real judgments
- interruptions do not lose candidates
- dedup is correct and explainable
- state transitions are explicit
- LinkedIn and GitHub share the same execution principles
- tests cover real operational risks
- adding a new source feels like plugging into a framework, not copying an orchestrator

---

## Final Note

This is not a roadmap from “bad” to “good.”
It is a roadmap from “impressive first autonomous system” to “credible production architecture.”
The hard part — product intuition, workflow design, and systems intent — is already there.
