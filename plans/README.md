# plans/

Shared plan artifacts for the Codex ↔ Cursor workflow described in `CODEX.md` §3.

## What goes here

- **Active plans**: `plans/<topic>.md` — one file per in-flight piece of work (refactor, bug investigation, feature). Written by Codex (or a planning pass in Cursor), read and executed by Cursor / a repo implementer subagent, then reviewed back in Codex.
- **Completed plans**: move to `plans/archive/` (or delete, if trivial) once the work ships.

## Why this exists

`CODEX.md` §3 describes a handoff loop (Codex plans → Cursor scouts → Cursor implements → Codex reviews) but without a shared artifact each crossing of the bridge starts from zero context. A plan file is the artifact. Keep it tight, keep it honest, update it as you learn.

## Rules

- One concern per plan. If you find yourself writing two different problem statements, split the file.
- Update the plan as the work evolves. A stale plan is worse than no plan.
- Plans are not specs. Specs live in `docs/`. A plan is the shape of *this* piece of work right now.
- Do not check secrets, tokens, PII, candidate names, or raw bundle contents into plan files.

## Template

Use [`_template.md`](./_template.md) as the starting point. Copy it to `plans/<topic>.md` and fill it in.

## Conventions

- Filenames: kebab-case (`plans/linkedin-progress-bridge-refactor.md`).
- Keep plans under ~200 lines. If yours is larger, the scope is probably wrong.
- Reference files with backtick paths (`shared/runtime_state/store.py`), not clickable links — plans are read by both humans and agents.
- Prefer "the narrowest safe slice" over "the complete fix." If the work is multi-slice, name each slice.
