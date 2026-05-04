# AGENTS.md

Canonical guide for AI coding agents (and new humans) working in this repo. Read this before making changes.

## What this repo is

A sourcing platform with three main layers:

1. **Source adapters**
   - LinkedIn sourcing flow (`linkedin/`)
   - GitHub sourcing flow (`github/`)

2. **Shared execution and runtime state** (`shared/`)
   - canonical candidate / run / work-unit state
   - resume semantics
   - compatibility projections

3. **Post-run intelligence** (`market_intelligence/`, `shared/brief_*`, `tools/iterate_brief.py`)
   - run snapshots
   - market intelligence
   - brief iteration and strategy artifacts

## Hard boundaries

This repo is the Sourcing Agent only. It is **not**:

- TA Ops Agent
- Rosie
- Analytics Hub
- the whole recruiting AI stack

Do not add stack-level architecture docs, cross-repo integration plans, or
platform-wide roadmaps here without explicit instruction.

## Canonical truths

- `runtime_state.sqlite3` is **canonical** for sourcing runtime state.
- JSON/JSONL files in live state dirs are **compatibility projections**, not source-of-truth control state.
- If SQLite and projection files disagree, **trust SQLite**.
- `output/runs/...` is immutable finalized run output.
- `output/market_intelligence/...` is market-scoped synthesis, separate from live per-project runtime state.

When investigating complexity, distinguish: canonical state / projections / snapshots / in-memory working state. They behave differently and a bug in one does not imply a bug in the others.

## High-risk files

Edit with elevated care. Scoped rules under `.cursor/rules/high-risk-files.mdc` fire when any of these are open.

| File | Why it's high-risk |
|------|--------------------|
| `shared/runtime_state/store.py` | shared persistence + lifecycle + reconciliation hot spot |
| `shared/runtime_state/linkedin.py` | LinkedIn resume/progress bridge semantics |
| `linkedin/orchestrator.py` | large, policy-heavy; casual broad edits cause regressions |
| `linkedin/browser.py` | brittle browser/runtime behavior; small targeted changes only |
| `market_intelligence/engine.py` | large orchestration surface; refactor carefully |

## Working norms

- **Targeted edits** over broad cleanup.
- **Preserve behavior** unless the task explicitly calls for changing it.
- When refactoring, **add or strengthen tests first** when feasible.
- Keep changes narrow and commit slices intentional.
- Do not casually mix runtime-state work with unrelated strategy, reconciliation, or config work in one diff.
- Prefer **behavior-preserving extraction** over giant rewrites.
- Cross-cutting changes should be staged deliberately across multiple commits.

## Brief / config discipline

- **Do not edit draft briefs unless explicitly asked.** Files matching `config/brief-*-draft.json` are scratch/in-flight; a pre-edit hook (`.cursor/hooks/guard-protected-paths.sh`) blocks edits unless the user names the file.
- Treat brief churn carefully — config files often encode product truth.
- Do not make scratch briefs look runnable by accident.

## Output / artifact discipline

- **Avoid editing `output/` directly.** Hand-editing is blocked by the same pre-edit hook.
- Rebuild projections or artifacts through code paths or tools — never hand-edit under `output/`.
- If a bug looks like it lives in `output/`, the real fix is almost always upstream in the code path that wrote it.

## Testing expectations

- After targeted runtime-state changes, run the narrowest relevant band first:
  - `pytest tests/test_linkedin_runtime_state.py -q`
  - `pyproject.toml` sets `pythonpath = ["."]` so no manual `PYTHONPATH=` prefix is needed.
- Expand outward only if the change crosses boundaries.
- Full-suite gate before declaring done: `make validate` (runs hygiene + default green suite).
- Prefer proving behavior with tests **before** "cleanup" refactors.

## Search / inspection defaults

- Prefer `rg` for finding code or text quickly.
- Ask for file-cited explanations when tracing architecture.

## Commit hygiene

- Only commit when explicitly asked.
- When asked, slice intentionally: separate behavior-preserving refactors from behavior changes; do not blob unrelated concerns together.
- Surface adjacent issues rather than silently expanding scope.

## Workflow artifact: `plans/`

Non-trivial work uses a shared plan file at `plans/<topic>.md`. Template and conventions: `plans/README.md`. This is how the strategist (Codex or Claude Code) and Cursor hand work back and forth without losing context.

## How to work

- Before substantive edits, list assumptions and every file you will touch.
- For non-trivial work, start from a plan file under `plans/` before editing.
- Prefer slice-sized plans and commit-sized implementation. If the seam is
  already clear and the slice is a clean whole-file change, Cursor can often
  implement, test, stage, and commit in one loop.
- Slow down into staged-diff review only when selective staging, mixed dirty
  files, high-risk surfaces, or ambiguous boundaries make that extra ceremony
  necessary.
- In Cursor, open **Plan mode** first when the task touches runtime state,
  high-risk files, or crosses boundaries between `linkedin/`, `github/`,
  `shared/`, and `market_intelligence/`.

## Cursor-specific setup

- Scoped rules live in `.cursor/rules/`:
  - `sourcing-agent.mdc` — always-on identity + boundaries
  - `runtime-state.mdc` — canonical vs projection discipline
  - `high-risk-files.mdc` — elevated care on policy-heavy files
  - `briefs-and-output.mdc` — draft brief and artifact discipline
  - `commit-hygiene.mdc` — scope and commit slicing
- The `sourcing-implementer` subagent in `.cursor/agents/` handles spec-first
  or plan-first implementation against this repo. Invoke it when implementing
  from a named plan or spec, especially for multi-file work.
- The `runtime-state-auditor` subagent in `.cursor/agents/` is a read-only
  diagnostic for resume/projection/canonical-state questions. Use it when the
  job is explanation and safe next-step selection rather than patching.
- The `brief-boundary-auditor` subagent in `.cursor/agents/` is a read-only
  diagnostic for brief drift: evaluation criteria vs search guidance vs snippet
  triage.
- The `execution-boundary-auditor` subagent in `.cursor/agents/` is a read-only
  ownership check for shared execution vs runtime-state bridges vs source
  adapters.
- The `market-intel-provenance-auditor` subagent in `.cursor/agents/` is a
  read-only provenance check for internal run evidence vs external research in
  market intelligence artifacts.
- Team playbook for pairing Cursor with the strategist (Codex or Claude Code):
  `docs/cursor-codex-workflow.md`.

## Repo biases

- Runtime-state-first thinking is preferred.
- Behavior-preserving extraction is preferred over giant rewrites.
- Clean commit hygiene matters.
- Cross-cutting changes should be staged deliberately.

## Related docs

- `CODEX.md` — Codex operating stance and Codex↔Cursor workflow contract (tool-level; this file is repo-level).
- `CLAUDE.md` — Claude Code operating stance; co-tenant of the strategist seat alongside Codex.
- `docs/cursor-codex-workflow.md` — repo-specific playbook for pairing the strategist (Codex or Claude Code) planning/review with Cursor implementation.
- `.cursor/rules/` — scoped rules that fire based on which files are open.
- `.cursor/agents/sourcing-implementer.md` — spec-first implementer subagent for this repo.
- `.cursor/agents/runtime-state-auditor.md` — read-only runtime-state diagnostic subagent.
- `.cursor/agents/brief-boundary-auditor.md` — read-only brief judgment vs search-guidance diagnostic.
- `.cursor/agents/execution-boundary-auditor.md` — read-only execution ownership diagnostic.
- `.cursor/agents/market-intel-provenance-auditor.md` — read-only internal-vs-external evidence diagnostic for market intelligence.
- `plans/README.md` — the shared plan-file artifact convention.
