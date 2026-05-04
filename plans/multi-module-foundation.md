# multi-module-foundation

Status: ready-to-implement
Owner: Sam
Last updated: 2026-04-29

## Problem

The substrate (`shared/runtime_state/store.py:121-205`) already source-discriminates everything that matters, but four shipping-blocker assumptions remain: (a) `linkedin_project: str` at `shared/brief_schema.py:190` is required-no-default and breaks non-LinkedIn briefs; (b) `Brief` has no `target_modules` field so the Cloris UI cannot filter or gate by module; (c) `FacialCalibration.github_*_patterns` flat fields don't scale beyond two sources; (d) `cloris/worker.py:196` hardcodes `linkedin.session_orchestrator` so non-LinkedIn workers cannot spawn. Plus three derived gaps: no Cloris-native candidate workspace for non-LinkedIn module saves; no `AbstractSaveDestination` interface separating "how a save is recorded" from "what a save means"; the calibration vertical-agnostic refactor (`plans/calibration-layer-vertical-agnostic.md`) is partially complete (Slice 1 only).

## Goal

After this plan ships, a non-LinkedIn module can be built and run end-to-end on the existing substrate without architectural negotiation. Phase 1 of `Cloris-Multi-Module-Roadmap.md` is complete and Phase 2 (Researcher + OSS Maintainers builds) is unblocked.

## Non-goals

- Build any non-LinkedIn module. That happens in `plans/researcher-module-build.md` and `plans/oss-maintainers-build.md` after this plan completes.
- Cross-module identity resolution (`docs/cloris-cross-module-identity-resolution-spec.md`). That ships in Phase 3.
- Refactor LinkedIn module behavior. The save-destination extraction is behavior-preserving; LinkedIn save semantics are byte-identical post-refactor.
- Touch the canonical state machine (`shared/runtime_state/store.py:62-71`). The lifecycle is source-agnostic and stays unchanged.

## Assumptions

- The calibration vertical-agnostic refactor's Slices 2-5 (`plans/calibration-layer-vertical-agnostic.md`) are landed before or as part of this plan. If they aren't, the substrate still has AI-vocabulary leakage that contaminates non-LinkedIn modules.
- Existing LinkedIn briefs use `linkedin_project` non-empty; the default-empty change does not break any in-flight brief.
- The save-destination extraction is behavior-preserving. Existing `tests/test_linkedin_pipeline.py` is the regression gate.
- The candidate workspace ships before any non-LinkedIn module. Without it, non-LinkedIn module saves have nowhere to go.

## Seam

Multiple seams; all in shared and Cloris-control-plane code.

- `shared/brief_schema.py` — fields and dataclasses, structural.
- `shared/brief_loader.py` — V2 brief JSON hydration.
- `shared/runtime_state/store.py` — schema additions for workspace tables; `_migrate` extension.
- `shared/save_destination/` (new directory) — interface and implementations.
- `linkedin/side_effects.py` — refactor `handle_save_decision` to dispatch via destination.
- `cloris/worker.py` — `--source` CLI flag, dispatch table.
- `cloris/api.py` — generic `/api/launch/{source}` route.
- `cloris/control_plane.py` — `_SOURCES` tuple expansion.
- `cloris/models.py` — `LaunchResponse.source` literal widening.
- `cloris/frontend/src/components/LaunchForm.svelte` — module selector UI.

## Proposed change

The plan ships in 10 slices, each independently committable. Slices 1-5 are schema/control-plane changes with no behavior changes for existing modules. Slices 6-7 add new infrastructure. Slices 8-10 are integrations and polish.

The narrowest safe slice approach: each slice's tests run before the slice ships. Existing `tests/test_*` suites stay green throughout.

## Risks

- **Calibration regression in LinkedIn evaluation.** Slice 3's per-source nested calibration refactor changes how `FacialCalibration` source-specific patterns are accessed. The compat shim hoists flat `github_*_patterns` into `sources["github"]` at hydration; existing code paths read from either form. Regression risk if a code path reads the flat fields without going through the loader's hoist. Mitigation: characterization tests on existing LinkedIn briefs assert prompt-text equality before and after.
- **Save-destination extraction behavior drift.** Slice 7 moves LinkedIn save logic out of `linkedin/side_effects.py` into `shared/save_destination/linkedin_recruiter.py`. Mitigation: behavior-preserving extraction; `tests/test_linkedin_pipeline.py` is the regression gate.
- **Worker dispatch table desync.** Slice 4's `cloris/worker.py` parameterization adds a dispatch table mapping source names to orchestrator modules. If a new source is registered in `_SOURCES` but missing from the dispatch table, launches fail at spawn time with a clear error. Mitigation: the `cloris/control_plane.py:_SOURCES` constant and `cloris/worker.py:_DISPATCH_TABLE` constant share a registry function; tests assert they stay in sync.
- **Workspace migration on production data.** Slice 6 adds three new tables to `runtime_state.sqlite3`. The migration is additive and gated on `meta.schema_version`. Mitigation: migration script is idempotent; rollback documented.
- **Brief-loader compat shim ambiguity.** Slice 3's hoist of `github_*_patterns` into `sources["github"]` — if a brief specifies BOTH the flat fields AND a `sources.github` section, which wins? Resolution: the `setdefault` in the hoist preserves explicit `sources.github` values; the flat fields are merged in only when `sources.github` is missing the corresponding key.

## Slices

- [ ] **Slice 1** — `shared/brief_schema.py:190` becomes `linkedin_project: str = ""`. `shared/brief_loader.py` already calls `raw.get("linkedin_project", "")`; loader pass-through is unchanged. `linkedin/side_effects.py` (or post-Slice-7 `LinkedInRecruiterSaveDestination`) checks for empty and skips browser save; existing behavior unchanged for LinkedIn briefs. Tests: `tests/test_brief_schema.py` for default; `tests/test_linkedin_pipeline.py` regression suite.

- [ ] **Slice 2** — `shared/brief_schema.py:Brief` adds `target_modules: list[str] = field(default_factory=lambda: ["linkedin"])`. `shared/brief_loader.py:_load_v2_brief` hydrates via `raw.get("target_modules", ["linkedin"])`. `cloris/api.py` validates `source in brief.target_modules` for launch routes. Tests: brief loader hydration; launch validation.

- [ ] **Slice 3** — `shared/brief_schema.py` introduces `SourceCalibration` dataclass and `FacialCalibration.sources: dict[str, SourceCalibration]`. `shared/brief_loader.py` hoists legacy `github_*_patterns` into `sources["github"]` at hydration. Render helpers `Brief.source_portfolio_*_block(source)` added. Existing `Brief.github_portfolio_*_block()` helpers retain backwards compat. Tests: loader hoist; prompt-rendering parity for existing GitHub briefs.

- [ ] **Slice 4** — `cloris/worker.py:_build_arg_parser` accepts `--source <name>`; `cloris/worker.py:build_session_orchestrator_argv` looks up the orchestrator module via `_DISPATCH_TABLE = {"linkedin": "linkedin.session_orchestrator", "github": "github.session_orchestrator"}`. `cloris/worker.py:build_sidecar` uses the source param instead of hardcoded `"linkedin"`. Tests: argv assertions for both fresh and resume modes; dispatch table membership against `_SOURCES`.

- [ ] **Slice 5** — `cloris/api.py` adds generic `POST /api/launch/{source}`, `POST /api/resume/{source}`, `POST /api/stop/{source}/{state_key}` routes. `cloris/models.py:LaunchResponse.source` and `StateDirEntry.source` widen to `Literal["linkedin", "github"]` (more sources added in subsequent module-build plans). The existing `POST /api/launch/linkedin` and `POST /api/resume/linkedin` routes remain as compatibility aliases delegating to the generic route. Tests: route-equivalence between alias and generic; HTTP 400 for source not in registered set.

- [ ] **Slice 6** — Candidate workspace v1 per `docs/cloris-candidate-workspace-spec.md`. Three new tables (`workspace_entries`, `workspace_review_events`, `workspace_outreach_artifacts`) added to `shared/runtime_state/store.py` via `_migrate`. New API endpoints in `cloris/api.py` (`GET /api/workspace/{brief_state_key}`, `PATCH /api/workspace/entry/{entry_id}`, etc.). New Cloris UI route at `/brief/<brief_state_key>/workspace` with editorial candidate cards. Tests: schema migration idempotency; API CRUD; UI render snapshot.

- [ ] **Slice 7** — `AbstractSaveDestination` per `docs/cloris-save-destination-abstraction.md`. New directory `shared/save_destination/` with `__init__.py` (interface + `SaveResult`), `linkedin_recruiter.py` (extracted from existing `linkedin/side_effects.py:handle_save_decision`), `candidate_workspace.py` (writes to workspace tables from Slice 6). Brief schema gains `save_destinations: list[str]` field with default derived from `target_modules`. Orchestrator dispatch via destination registry. Tests: behavior-preserving extraction (LinkedIn save behavior byte-identical); workspace destination writes correct rows.

- [ ] **Slice 8** — `market_intelligence/` integration into LinkedIn run launch per `docs/exec-search-workflow-spec.md`. New API endpoint `POST /api/exec-search/investigate` in `cloris/api.py` invokes `market_intelligence/engine.py`; result persisted as `output/state/linkedin/<brief_state_key>/exec_search_investigation.json`. Cloris UI launch flow gains an investigation-review step gated on `brief.enable_pre_launch_investigation`. Brief schema field `enable_pre_launch_investigation: bool = False`. Tests: investigation API smoke test; UI step renders only when brief opts in.

- [ ] **Slice 9** — Calibration vertical-agnostic Slices 2-5 (`plans/calibration-layer-vertical-agnostic.md`) verified shipped or shipped as part of this slice. If unfinished, complete: strip remaining AI-vocabulary leakage from `linkedin/judgment_templates.py`, `linkedin/strategy.py`, `shared/judger.py`, `shared/preflight*.py`. Tests: parity tests across non-AI fixture brief; AI-vocabulary leakage detector tests.

- [ ] **Slice 10** — Feedback artifact + run-to-brief pinning per `docs/cloris-ui-spec.md:386-391`. Brief identity is already pinned at run-start (`shared/runtime_state/store.py:303-317`); workspace review events from Slice 6 are the feedback artifact. Wire `shared/brief_iteration.py:862-910`'s context builder to consume `workspace_review_events` for the active brief, producing brief revision proposals. Tests: feedback context construction from review events; brief revision proposal shape.

## Test strategy

- Narrowest relevant test band per slice:
  - Slice 1: `pytest tests/test_brief_schema.py tests/test_brief_loader.py -q`
  - Slice 2: `pytest tests/test_brief_schema.py tests/test_brief_loader.py tests/test_cloris_app.py -q`
  - Slice 3: `pytest tests/test_brief_schema.py tests/test_brief_loader.py tests/test_judgment_templates.py -q` (any test that asserts on prompt rendering for GitHub briefs)
  - Slice 4: `pytest tests/test_cloris_worker.py -q`
  - Slice 5: `pytest tests/test_cloris_app.py -q`
  - Slice 6: `pytest tests/test_runtime_state.py tests/test_cloris_app.py -q` (workspace migration + API)
  - Slice 7: `pytest tests/test_linkedin_pipeline.py tests/test_save_destination.py -q` (regression + new)
  - Slice 8: `pytest tests/test_market_intelligence.py tests/test_cloris_app.py -q`
  - Slice 9: `pytest tests/test_judgment_templates.py tests/test_linkedin_strategy.py tests/test_search_memory.py -q`
  - Slice 10: `pytest tests/test_brief_iteration.py tests/test_runtime_state.py -q`
- Tests to add/strengthen:
  - Multi-module brief load test: brief with `target_modules: ["linkedin", "researcher"]` loads, exposes both calibrations.
  - Calibration parity tests for AI-fixture brief (existing) and non-AI-fixture brief (new).
  - Save destination dispatch test: LinkedIn brief with both destinations writes both side effects.
  - Workspace API integration test: full lifecycle (write, read, mark, outreach status, review event log).
- Full-suite gate before declaring done: `make validate`.

## Open questions

- Should Slice 9 be a prerequisite for the Phase, or shipped in parallel with the plan? Decision: prerequisite. Without calibration vertical-agnostic completion, the substrate still leaks AI vocabulary and non-LinkedIn modules will inherit the leakage.
- Slice 10's feedback loop: does it ship in this foundation plan or in Phase 3 alongside cross-module identity? Decision: ship Slice 10 in this plan. The candidate workspace is the input to the loop; without the loop closing, the workspace is a write-only surface.

## Decisions

- 2026-04-29 — Plan ships in 10 slices with explicit slice-level test gates.
- 2026-04-29 — Save-destination extraction is behavior-preserving; existing LinkedIn behavior is byte-identical post-Slice-7.
- 2026-04-29 — Calibration vertical-agnostic completion is a prerequisite slice, not a parallel workstream.
- 2026-04-29 — `cloris/api.py` keeps `POST /api/launch/linkedin` and `POST /api/resume/linkedin` as aliases for backwards compatibility; deletion is a v2 cleanup after non-LinkedIn modules ship.
- 2026-04-29 — Workspace migration is additive; rollback is "stop using the workspace UI route" — data persists, no schema rollback needed.

## Follow-ups (not in this plan)

- Cross-module identity resolution (`docs/cloris-cross-module-identity-resolution-spec.md`) — Phase 3 work.
- Process-pool-level shared governor (`shared/safety/cross_module_governor.py`) — Phase 3 work, urgent at module #3.
- `LaunchResponse.source` literal expansion to include `"researcher"`, `"defense"`, `"designer"` — happens in each module's build plan.
- Deletion of legacy `github_*_patterns` flat fields and the `POST /api/launch/linkedin` aliases — scheduled cleanup ~6 months after multi-module ship stabilizes.
