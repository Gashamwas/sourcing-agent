# Cursor + Codex for the Sourcing Agent Repo

This document is the practical playbook for using **Codex** and **Cursor**
together in this repo.

The goal is not to create more ceremony. The goal is to reduce context thrash:
Codex shapes the problem and reviews the result, Cursor stays grounded in the
repo and executes the local change, and the shared artifact between them is a
plan file under `plans/`.

## What each tool is best at

**Codex** is strongest when the work is judgment-heavy:

- clarifying the real engineering problem
- comparing architecture options
- picking a seam
- writing or tightening a design note
- reviewing a diff skeptically
- checking whether a proposed solution actually matches the goal

**Cursor** is strongest when the answer must stay grounded in *this repo*:

- tracing owning files
- reading local code quickly
- implementing a plan against the actual codebase
- running targeted tests
- iterating on a small or medium patch

**Rule of thumb:** if the task must land cleanly in git and survive the test
band, bias toward **Cursor**. If the task is still "what exactly are we trying
to do?" bias toward **Codex** first.

## The shared artifact: `plans/`

For non-trivial work, the handoff artifact is `plans/<topic>.md`.

That file is how the Codex ↔ Cursor loop avoids starting from zero each time.
Template and conventions live in `plans/README.md`.

Use a plan when the work is any of:

- a multi-file change
- a runtime-state change
- a change touching a high-risk file
- a cross-boundary change across `linkedin/`, `github/`, `shared/`, or
  `market_intelligence/`
- a refactor where commit slicing matters

## Plan at the slice level, execute at the commit level

The default loop here is **not** "make every patch microscopic." The default
loop is:

- make the plan large enough to define the next real slice
- make the implementation small enough to land cleanly in git

In practice:

- a plan should usually describe the next **slice** of work, not the whole
  initiative
- a Cursor implementation pass should usually target **one reviewable commit**
  or, at most, one tightly-coupled commit pair
- if the seam is already clear and the remaining work is a clean whole-file
  slice, Cursor can often implement, test, stage, and commit in one local loop
- if the slice requires selective staging, partial-file commits, or separation
  from unrelated dirty worktree changes, slow down and review the staged diff
  before committing

The goal is to avoid two failure modes at once:

- giant all-at-once prompts that blur boundaries and create messy commits
- over-cautious "micropatch" loops where every safe whole-file change turns
  into several rounds of ceremony

## A workflow that works well here

1. **Codex — shape the problem**

   Start with the messy idea, bug, refactor, or desired outcome. Codex should
   help answer:

   - what the actual problem is
   - which layer is involved: canonical / projection / snapshot / in-memory
   - what the smallest safe slice is
   - whether a plan or spec needs to be written first

2. **Write or update `plans/<topic>.md`**

   Keep it tight. The plan should state:

   - the problem
   - the goal
   - the seam
   - the risks
   - the slices
   - the narrowest test band

3. **Cursor — scout the repo**

   Use Cursor to trace the files named in the plan. Before editing, ask it to
   list assumptions, touched files, and test coverage.

4. **Cursor — implement against the plan**

   For spec-first or plan-first work, invoke `sourcing-implementer`. It is the
   repo-local implementer that already understands:

   - runtime-state-first discipline
   - high-risk files
   - protected paths
   - narrow test bands
   - commit-slicing expectations

   If Cursor Plan mode is used, use it to **validate or sharpen the next
   slice** against the real repo surface. Do not default to asking Cursor to
   invent a multi-commit roadmap from scratch when the plan file already exists.

5. **Codex — review the result**

   Bring back the important output only:

   - the file-touch plan
   - the diff
   - the targeted test results
   - the question "is this actually the right seam?"

6. **Cursor — finish the local loop**

   Apply final refinements, run the agreed test band, then run `make validate`
   if the change is ready to close.

### Fast path vs slow path

Use the **fast path** when all of these are true:

- the seam is already clear
- the change is confined to the approved slice
- the diff is whole-file or otherwise easy to stage cleanly
- there is no risk of mixing in unrelated dirty worktree changes

In that case, Cursor can usually:

1. implement the slice
2. run the narrow test band
3. stage the approved files
4. commit directly

Use the **slow path** when any of these are true:

- selective staging is required
- a high-risk file is involved and the boundary is still debatable
- the working tree contains adjacent unrelated changes in the same file
- the slice is likely to split into multiple commits

In that case, stop before commit and review the staged diff first.

## When to open Cursor Plan mode first

For this repo, open Cursor **Plan mode** first when the task touches:

- `shared/runtime_state/**`
- `shared/execution/**`
- `linkedin/orchestrator.py`
- `linkedin/browser.py`
- `market_intelligence/engine.py`
- any change that crosses runtime-state and projections
- any cross-cutting change likely to need multiple commits

Plan mode is for **slice validation**, not for turning every straightforward
whole-file doc or code change into a multi-step ceremony loop.

## Grounding work in Cursor

Attach the owning paths so Cursor does not invent the seam.

Common anchors:

| If you are working on… | Attach… |
|------------------------|---------|
| Runtime-state / resume / projections | `@shared/runtime_state/`, `@docs/runtime-state-operator-runbook.md`, `@docs/shared-candidate-execution-engine.md` |
| LinkedIn evaluation / orchestration | `@linkedin/orchestrator.py`, `@shared/judger.py`, `@tests/test_linkedin_pipeline.py` |
| LinkedIn browser behavior | `@linkedin/browser.py`, `@tests/test_linkedin_browser_recovery.py` |
| GitHub enrichment / evaluation | `@github/enricher.py`, `@shared/judger.py`, `@tests/test_github_pipeline.py` |
| Market intelligence / external research | `@market_intelligence/`, `@tests/test_market_intelligence.py` |
| Brief iteration / brief lifecycle | `@shared/brief_iteration.py`, `@tests/test_brief_iteration.py`, `@tests/test_brief_lifecycle.py` |

## Useful prompts for Cursor

- "Before you edit, list assumptions, touched files, and the narrowest test
  band."
- "Trace this subsystem end to end and cite the owning files."
- "Validate the next slice against `plans/<topic>.md` and tell me if the seam
  is clean."
- "Implement only Slice 1 from `plans/<topic>.md`."
- "If this is a clean whole-file slice, implement, test, stage, and commit in
  one pass."
- "Flag any high-risk file in the touch plan before editing."
- "Run the matching tests and show the real output."

## Useful prompts for Codex

- "What is the actual engineering problem here?"
- "What is the smallest safe slice?"
- "Is this a runtime-state bug, a projection bug, or a snapshot interpretation
  bug?"
- "Review this diff like a skeptical senior engineer."
- "How should this be split into commits?"

## Narrow subagents worth using

This repo should stay conservative about subagents. Use them only when the job
is repeated and the output contract is clear.

- `sourcing-implementer`
  - use for plan-first or spec-first implementation
- `runtime-state-auditor`
  - use for read-only diagnosis when resume/progress/projection behavior looks
    wrong
- `brief-boundary-auditor`
  - use when a brief, brief diff, or prompt-related change may be mixing
    evaluation criteria with search guidance or overloading snippet triage
- `execution-boundary-auditor`
  - use when a bug or design may be crossing the boundary between shared
    execution, runtime-state bridges, and source adapters
- `market-intel-provenance-auditor`
  - use when reviewing market-intelligence artifacts or changes that may be
    outrunning internal run evidence or over-leaning on external research

If a proposed subagent does not end in a diff, a test result, or a concrete
diagnostic artifact, it is probably adding ceremony more than leverage.

## Success metric

The setup is working when:

- Codex reduces ambiguity before editing starts
- Cursor changes the right files instead of wandering
- plan files preserve context between turns
- subagents are narrow and output-driven rather than theatrical
- the final result is a better diff with fewer false starts
