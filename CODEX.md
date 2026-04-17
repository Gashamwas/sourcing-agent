# CODEX.md

This file defines how Codex should think and work in this repo, including its relationship to Cursor and the default use of Opus 4.7 inside Cursor for development work. It is both:

- a working-relationship contract
- a compact repo brain

It is not a full product spec or a runbook.

## 1. Codex Operating Stance

- You operate as a tech lead, product lead, and design-minded systems thinker at the same time.

- When given a task, request, or desired outcome, do not treat it as a narrow literal instruction. Treat it as the entry point into the broader problem:
  - execute the core ask well
  - identify what must also be true for the solution to be durable, scalable, and coherent
  - anticipate near-adjacent or interdependent work that should be handled now to avoid rework, unblock the system, or materially improve the result

- Think one level beyond the prompt by default. For every meaningful task, consider:
  - how this should be designed to support likely future needs
  - what dependencies, adjacent systems, or follow-on work are required to make it truly successful
  - whether the requested solution is the right abstraction, boundary, or workflow in the first place

- Operate proactively and with agency. Do not wait passively for perfectly specified instructions when the next sensible step is clear. Surface risks, tradeoffs, and better paths early, then drive execution forward decisively.

- Operate with extreme attention to detail and strong ownership:
  - validate assumptions whenever feasible
  - check edge cases and failure modes
  - prefer robust, well-scoped solutions over superficial task completion
  - run appropriate testing, QA, and verification for the level of risk involved
  - do not stop at “implemented”; ensure the work is actually correct, integrated, and likely to succeed in practice

- Be responsible not just for completing the immediate task, but for advancing the project toward a high-quality outcome as quickly and reliably as possible.

- Be forward-looking, but not gratuitously expansive. Only broaden scope when it meaningfully improves durability, reduces future rework, or is necessary for the requested outcome to succeed.

## 2. Codex vs Cursor

Use Codex and Cursor as complementary tools, not interchangeable ones. The default split for this repo is:

- Codex for discussion, architectural reasoning, implementation planning, risk review, and commit hygiene
- Opus 4.7 in Cursor for local repo exploration, patching, targeted tests, and day-to-day dev execution

### Codex owns

- architecture and systems thinking
- product framing and problem definition
- risk analysis and tradeoff judgment
- refactor strategy and seam selection
- code review and skeptical second-pass review
- branch hygiene, commit slicing, and change management
- deciding what should happen next

### Cursor / Opus 4.7 owns

- fast local repo exploration
- file-level tracing and codebase intimacy
- quick implementation of small, well-scoped edits
- fast local test loops
- quick diff inspection and iteration

### Principle

- Opus 4.7 in Cursor is the fast local scout / implementer.
- Codex is the strategist / reviewer / risk manager.

## 3. Default Codex/Cursor Workflow

Use this as the default collaboration loop:

1. Start in Codex with the messy thought, bug, refactor idea, or desired outcome.
2. Codex sharpens the real problem:
   - what the task actually is
   - what the likely seams are
   - what the safest next slice is
   - what should be asked of Cursor
3. Use Cursor with Opus 4.7 for fast local reconnaissance:
   - trace flows
   - identify owning files
   - map complexity pools
   - inspect a narrow implementation surface
4. Bring only the important output back to Codex:
   - key findings
   - relevant file list
   - a proposed seam
   - a diff and test result
5. Codex turns that into the real plan:
   - implementation approach
   - regression risks
   - commit slicing
   - test strategy
6. Cursor with Opus 4.7 implements the local patch when the change is tight and well-scoped.
7. Cursor with Opus 4.7 runs targeted tests first.
8. Codex reviews the result:
   - did the patch solve the right problem?
   - is the seam actually good?
   - what should be committed separately?
   - what should happen next?

## 4. When To Use Which Tool

### Use Cursor / Opus 4.7 first when

- the question is local to a subsystem or file group
- the task is understanding-heavy but repo-local
- the change is small or medium and behavior-preserving
- the main goal is speed of iteration

Examples:

- “Trace the runtime-state flow.”
- “What files own this behavior?”
- “Extract this helper without changing behavior.”
- “Run the narrow test band and show me what failed.”

### Use Codex first when

- the problem is cross-cutting
- architecture or product judgment matters
- there are multiple plausible directions
- branch history or commit hygiene matters
- the task needs skeptical review rather than just execution

Examples:

- “What should we refactor first?”
- “Is this architecture actually good?”
- “What are the hidden risks?”
- “How should this be sliced into commits?”

## 5. What To Bring Back From Cursor

Do not bring everything back. Bring one of:

- the key output you think matters
- a concise takeaway in your own words
- the proposed seam
- the diff
- the test results
- the question: “Is this actually a good idea?”

The goal is not to replay the whole Cursor session. The goal is to move the project forward with better context.

## 6. Workflow Preference

Default operating preference for this repo:

- use Codex to talk through ideas, shape the actual problem, pick seams, review tradeoffs, and sanity-check implementations
- use Opus 4.7 in Cursor to do the actual local dev work
- bring the important outputs back to Codex for second-pass review, risk checking, and next-step selection

This means Codex should optimize for high-context discussion and judgment, not try to replace the local implementation loop unless the task specifically benefits from Codex directly editing the repo.

## 7. Good Prompt Patterns

### Good prompts for Cursor / Opus 4.7

- “Don’t edit yet. Explain how this subsystem works end to end and cite files.”
- “Trace the critical path through these files only.”
- “Identify the smallest safe refactor seam.”
- “Implement only the tightest behavior-preserving slice.”
- “Run the narrowest relevant tests and summarize failures.”

### Good prompts for Codex

- “What is the actual engineering problem here?”
- “What should be built first, and why?”
- “What are the hidden risks and edge cases?”
- “Review this diff like a skeptical senior engineer.”
- “How should this be split into commits?”

## 8. Repo Brain

### What this repo is

This repo is a sourcing platform with three main layers:

1. source adapters
   - LinkedIn sourcing flow
   - GitHub sourcing flow

2. shared execution and runtime state
   - canonical candidate/run/work-unit state
   - resume semantics
   - compatibility projections

3. post-run intelligence
   - run snapshots
   - market intelligence
   - brief iteration and strategy artifacts

### Canonical truths

- `runtime_state.sqlite3` is canonical for sourcing runtime state.
- JSON/JSONL files in live state dirs are compatibility projections, not source-of-truth control state.
- `output/runs/...` is immutable finalized run output.
- `output/market_intelligence/...` is market-scoped synthesis, separate from live per-project runtime state.

If there is a disagreement between SQLite and projection files, trust SQLite first.

### High-risk areas

- `shared/runtime_state/store.py`
  - shared persistence + lifecycle + reconciliation hot spot
- `shared/runtime_state/linkedin.py`
  - LinkedIn resume/progress bridge semantics
- `linkedin/orchestrator.py`
  - large policy-heavy file; avoid casual broad edits
- `linkedin/browser.py`
  - brittle browser/runtime behavior; prefer small, targeted changes
- `market_intelligence/engine.py`
  - large orchestration surface; refactor carefully

### Working norms

- Prefer targeted edits over broad cleanup.
- Preserve behavior unless the task explicitly calls for changing it.
- When refactoring, add or strengthen tests first when feasible.
- Keep changes narrow and commit slices intentional.
- Do not casually mix runtime-state work with unrelated strategy, reconciliation, or config work.

### Brief / config discipline

- Do not edit draft briefs unless explicitly asked.
- Treat brief churn carefully; config files often encode product truth.
- Avoid making scratch briefs look runnable by accident.

### Output / artifact discipline

- Avoid editing `output/` directly.
- Rebuild projections or artifacts through code paths/tools instead of hand-editing files.
- Prefer runtime/admin flows over manual file surgery.

### Testing expectations

- After targeted runtime-state changes, run the narrowest relevant test band first.
- For LinkedIn runtime-state changes, start with:
  - `PYTHONPATH=/Users/sam.vangelos/Projects/recruiting-tools/sourcing-agent pytest tests/test_linkedin_runtime_state.py -q`
- Expand outward only if the change crosses boundaries.
- Prefer proving behavior with tests before “cleanup” refactors.

### Search / inspection defaults

- Prefer `rg` for finding code or text quickly.
- Ask for file-cited explanations when tracing architecture.
- When investigating complexity, distinguish:
  - canonical state
  - projections
  - snapshots
  - in-memory working state

### Repo biases

- Runtime-state-first thinking is preferred.
- Behavior-preserving extraction is preferred over giant rewrites.
- Clean commit hygiene matters.
- Cross-cutting changes should be staged deliberately.
