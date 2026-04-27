# Workflow Docs Fast-Path Clarification

## Problem

The current Codex↔Cursor workflow docs correctly emphasize plans, narrow seams,
and commit hygiene, but they do not say clearly enough when the team should
take the faster path. That leaves room for a too-cautious pattern where every
slice turns into multiple review loops even when the remaining work is a clean
whole-file commit.

## Goal

Clarify the intended philosophy:

- plan at the slice level
- implement at the commit level
- use Cursor Plan mode to validate or sharpen the next slice, not to generate a
  giant all-at-once roadmap by default
- use the faster implement/test/stage/commit loop when the slice is whole-file
  and the seam is already clear
- reserve extra dry-run and selective-staging ceremony for mixed dirty files,
  partial-file commits, high-risk surfaces, or ambiguous ownership

## Seam

Docs only:

- `docs/cursor-codex-workflow.md`
- `CODEX.md`
- `AGENTS.md`

No code or config changes.

## Risks

- Over-correcting toward speed and weakening the repo's emphasis on plans and
  commit hygiene
- Duplicating too much workflow guidance across the three documents

## Slices

1. Add the philosophy explicitly to the repo-specific workflow playbook.
2. Reinforce the same distinction in the Codex/Cursor operating contract.
3. Add a short repo-level note in `AGENTS.md` so the fast path is visible from
   the canonical guide.

## Narrowest Review Band

- Review the doc diff for consistency with the existing contract:
  - plans remain required for non-trivial work
  - Codex still owns seam selection and review
  - Cursor still owns repo-grounded implementation
  - fast path is allowed only when the seam is already clean
