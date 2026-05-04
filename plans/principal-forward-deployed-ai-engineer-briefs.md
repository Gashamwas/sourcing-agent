# principal-forward-deployed-ai-engineer-briefs

Status: shipped
Owner: Codex
Last updated: 2026-04-21

## Problem

The repo has mature briefs for `config/Forward-Deployed-Engineer-NYC/` and `config/Head-of-FDE/`, but no dedicated brief artifacts for the new principal/staff GenAI delivery role captured in the two intake templates under `/Users/sam.vangelos/Downloads/`. We need repo-native brief files that preserve existing FDE calibration where it still fits while reflecting the new geography-specific intake differences.

## Goal

Add geography-specific brief artifacts for this role in the repo, with the New York version explicitly calibrated as a senior/principal FDE-style brief and the India version calibrated as the adjacent GenAI-delivery variant described in the intake.

## Non-goals

- Reworking the existing `config/Forward-Deployed-Engineer-NYC/` or `config/Head-of-FDE/` briefs.
- Iterating search-memory or run-report-driven retrieval design.
- Editing draft briefs unrelated to this role.

## Assumptions

- The two intake markdown files are the intended source material for this task.
- The Greenhouse job pages surfaced from the intake/JD links are sufficient to verify the posted role framing.
- These briefs should follow the heavyweight JSON pattern used by the existing FDE and head-of-FDE configs.

## Seam

Add a new role-specific folder under `config/` with brief JSONs and supporting JD text files. Validation should flow through `shared/brief_loader.py` and existing brief-loading tests/utilities without changing runtime code.

## Proposed change

Create a new `config/Principal-Forward-Deployed-AI-Engineer/` directory.

Add:
- a New York brief derived from the existing FDE brief, but recalibrated upward for principal scope and the recruiter intake emphasis on small-pod leadership plus recent hands-on coding
- an India brief derived from the same role family, but broadened to reflect the intake's IC5/IC6 GenAI-delivery framing rather than strict forward-deployed-title matching
- JD text snapshots for both geographies using the current Greenhouse postings

Keep the schema legacy-compatible by using the established full brief format rather than introducing a new shape.

## Risks

- Over-copying existing FDE assumptions like BFSI gating where the intake/JD now points to broader enterprise GenAI delivery.
- Accidentally drifting into the `Head-of-FDE` level instead of senior IC / pod-lead calibration.
- Creating briefs that load as JSON but violate implicit recruiter expectations because the geography-specific scope differences are under-modeled.

## Slices

- [x] Slice 1: Confirm role framing from intake + posted JDs and decide inheritance model from existing FDE briefs.
- [x] Slice 2: Add role directory, JD artifacts, and geography-specific brief JSONs.
- [x] Slice 3: Validate new briefs via `load_brief` / targeted tests and summarize the role-framing decision.

## Test strategy

- Narrowest relevant test band to run first:
  - `pytest tests/test_retrieval_design.py -q`
- Tests to add/strengthen:
  - Only if the new briefs expose loader/schema issues not already covered.
- Full-suite gate before declaring done: `make validate`

## Open questions

- Whether the India brief should keep explicit forward-deployed language in the title or follow the intake's `Staff GenAI Engineer (IC5)` / `Principal GenAI Engineer (IC6)` framing more closely.

## Decisions

- 2026-04-21 — Treat the New York role as a principal/senior FDE-style brief, not a head-of-function brief — The intake plus Greenhouse JD describe hands-on coding, technical roadmap ownership, client-facing delivery, and small-pod leadership rather than org-scale leadership.
- 2026-04-21 — Keep India as a sibling brief in the same role family but not a pure clone of the New York FDE brief — The intake explicitly broadens the title family to Staff/Principal GenAI Engineer and emphasizes production RAG/agents more than forward-deployed branding.
- 2026-04-21 — Import mid-level FDE market intel at the search-family level, not the leveling level — The productive hidden lanes (knowledge-product language, LLM observability, workflow orchestration) should inform these briefs, while the mid-level years band and evaluation bar should not.
- 2026-04-21 — Keep `additional_search_terms` concept-heavy and novelty-oriented — Generic stack terms, cloud terms, seniority titles, and implied delivery behaviors were pruned so the brief primes the agent toward hidden terminology and search criteria rather than baseline qualifications.
- 2026-04-21 — Validation passed via `load_brief` and `pytest tests/test_retrieval_design.py -q` — The new briefs are JSON-valid, schema-loadable, and did not break the targeted retrieval-design band.

## Follow-ups (not in this plan)

- Add a GitHub-specific variant if the sourcing workflow for this role later expands to code-signal-first search.
- Iterate retrieval design after the first live run if search-memory shows repeated false negatives by title family or geography.
