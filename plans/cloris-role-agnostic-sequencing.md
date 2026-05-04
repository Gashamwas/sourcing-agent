# Cloris Sequencing Around Role-Agnostic Refactor

Status: ready-to-implement
Owner: Codex
Last updated: 2026-04-27

## Problem

Cloris now has a UI spec, a control-plane spec, and a shell v0 plan, but there is an active refactor making the agent more role-agnostic by moving recruiting vocabulary and calibration semantics out of code and into the brief (`shared/brief_schema.py`, `shared/brief_loader.py`, `linkedin/strategy.py`, `linkedin/judgment_templates.py`). Without an explicit sequencing plan, the team can either wait too long and block shell work unnecessarily, or start semantic UI work too early and bake unstable brief semantics into the product.

## Goal

Ship Cloris in two deliberate tracks: build the shell/control plane now, while deferring semantically rich authoring/review surfaces until the role-agnostic refactor crosses an explicit readiness gate.

## Non-goals

- Finishing the role-agnostic refactor itself
- Revising `docs/cloris-ui-spec.md` or `docs/cloris-control-plane-spec.md`
- Implementing the full Authoring Loop, Run Review, or Next Run Learning in this plan
- Redesigning the brief schema
- Rewriting `linkedin/orchestrator.py` or `shared/runtime_state/store.py`

## Assumptions

- The current role-agnostic work is primarily changing brief semantics and prompt consumers, not runtime topology.
- `runtime_state.sqlite3` remains canonical per state dir, and shell/control-plane work can proceed without waiting for brief-schema stabilization.
- Cloris v0 should be operational first: truthful launch, status, stop, resume, and reopen behavior matter more than semantic polish.
- The existing shell plan in `plans/cloris-shell-v0.md` remains the implementation base for Track A.
- The role-agnostic refactor is not “done” until missing V2 calibration fields are no longer merely a warning in `shared/brief_loader.py:458-486`.

## Seam

This plan splits work across two boundaries:

- **Track A: shell / control plane now**
  - `plans/cloris-shell-v0.md`
  - `docs/cloris-control-plane-spec.md`
  - runtime wrappers and state aggregation around `shared/output_paths.py`, `shared/runtime_state/store.py`, `shared/runtime_state/lock.py`, `linkedin/session_orchestrator.py`, `linkedin/run.py`

- **Track B: semantic surfaces later**
  - brief semantics and calibration consumers in `shared/brief_schema.py`, `shared/brief_loader.py`, `linkedin/strategy.py`, `linkedin/judgment_templates.py`, `shared/judger.py`, `shared/preflight_v2.py`, `shared/brief_iteration.py`

The operational rule is simple: do not let Track B block Track A.

## Proposed change

Run Cloris development in three phases.

### Phase 1: Ship the shell against stable runtime boundaries

Start implementation from `plans/cloris-shell-v0.md` immediately.

Scope:

- detached worker lifecycle
- `worker.json` sidecar
- product-level status aggregation across per-source/per-brief state dirs
- LinkedIn-only launch path
- graceful stop
- truthful reopen behavior
- minimal Ambient Home and Launch Gate shell

Why this is safe now:

- runtime execution is already Python-native and inline in `linkedin/run.py:160-194`
- session ownership already lives in `linkedin/session_orchestrator.py:310-369`
- canonical runtime truth already lives in `shared/runtime_state/store.py:82-90`
- single-writer semantics already exist in `shared/runtime_state/lock.py:16-25`

None of those depend on whether calibration vocabulary is fully role-agnostic.

### Phase 2: Freeze semantic UI scope while the refactor is still transitional

Do not build rich semantic surfaces yet. Keep only thin, operational placeholders where needed.

Explicitly defer:

- full Authoring Loop
- rich Brief Review that claims to expose the “real” role model
- Run Review explanations that depend on stable calibration semantics
- Next Run Learning / feedback-to-brief synthesis UX

Why they are not ready:

- `shared/brief_schema.py:231-235` still says the new vocabulary is transitional and “inert until Slice 2”
- `shared/brief_schema.py:667-669` says helper renderers exist before consumers are fully wired
- `shared/brief_loader.py:458-486` still treats missing calibration fields as Stage 0 warnings, not hard failures
- `shared/judger.py:101-124` still builds calibration sections from the older `brief.raw["calibration_examples"]` shape

This means the shell can be truthful today, but semantic UI would still be partly speculative.

### Phase 3: Open semantic surfaces only after a refactor readiness gate

Before starting semantic Cloris surfaces, require all of the following to be true:

1. **Validator gate**
   - V2 calibration is no longer warning-only in `shared/brief_loader.py:458-486`.
   - Missing required calibration fields either hard-fail, or the team intentionally narrows which fields are truly required.

2. **Consumer gate**
   - The intended field set is actually consumed by the runtime paths that shape candidate evaluation and search behavior.
   - At minimum, confirm the final consumer set across:
     - `linkedin/strategy.py:163-179`, `linkedin/strategy.py:788-800`
     - `linkedin/judgment_templates.py:394-425`, `linkedin/judgment_templates.py:497-504`
     - any remaining calibration paths in `shared/judger.py`

3. **Authoring gate**
   - The system has a credible way to produce and edit the new brief semantics, not just parse them.
   - Today `shared/preflight_v2.py:101-170` is prompt/parse/merge plumbing, not a product-grade authoring backend.

4. **Naming gate**
   - Cloris screen labels and copy are updated to use role-agnostic language, not legacy role-specific assumptions.

Only after those gates should Track B begin.

## Risks

- If the shell team waits for semantic stability, Cloris loses months on the wrong dependency.
- If the semantic UI starts too early, the product will encode transitional brief semantics and need expensive rewrites.
- If Track A accidentally reaches into brief semantics for convenience, it will inherit refactor churn and stop being a stable wrapper.
- If Track B launches before the validator gate, Cloris will present partial or misleading “understanding of the role” as if it were authoritative.

## Slices

- [ ] Slice 1: Treat `plans/cloris-shell-v0.md` as active implementation plan and begin Track A immediately.
- [ ] Slice 2: Add a short “semantic freeze” note to implementation kickoff docs / tickets: no Authoring Loop, rich Brief Review, or rich Run Review in shell v0.
- [ ] Slice 3: Define the refactor readiness checklist as a blocking issue for semantic surfaces, using the four gates in this plan.
- [ ] Slice 4: Reassess after the role-agnostic refactor crosses the validator and consumer gates; only then open a new plan for semantic Cloris surfaces.

## Test strategy

- For Track A, follow `plans/cloris-shell-v0.md`:
  - `pytest tests/test_output_paths.py -q`
  - `pytest tests/test_runtime_state.py -q`
  - `pytest tests/test_linkedin_session_orchestrator.py -q`
- For the refactor gate itself, require focused verification of the actual semantic consumer paths before opening Track B:
  - narrow tests around `linkedin/strategy.py`
  - narrow tests around `linkedin/judgment_templates.py`
  - any calibration-shape tests around `shared/brief_loader.py` and `shared/judger.py`
- Full-suite gate before declaring any Track A slice done:
  - `make validate`

## Open questions

- Which exact semantic fields are truly mandatory for Cloris v1 surfaces, versus merely nice-to-have once the refactor settles?
- Whether `shared/judger.py` should be migrated to the new calibration vocabulary before any Run Review UX work starts, or whether Run Review should initially stay closer to canonical runtime evidence and avoid synthesized calibration language.

## Decisions

- 2026-04-27 — Do not wait for the role-agnostic refactor to start Cloris shell work — Shell/control-plane concerns are runtime-topology work, not brief-semantics work.
- 2026-04-27 — Freeze semantically rich surfaces until the refactor crosses an explicit readiness gate — Avoid baking transitional brief semantics into the product.
- 2026-04-27 — Use `shared/brief_loader.py:458-486` as the clearest current gate signal — Stage 0 warning means “not stable enough for authoritative semantic UI.”

## Follow-ups (not in this plan)

- New implementation plan for Cloris semantic surfaces once the readiness gate is met.
- Run-to-brief pinning work before full Run Review / feedback UX.
- Feedback-table schema work before Next Run Learning.
