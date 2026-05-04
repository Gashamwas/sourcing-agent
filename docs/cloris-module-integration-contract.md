# Cloris Module Integration Contract

Status: living
Owner: Sam
Last updated: 2026-04-29

This document specifies the contract every Cloris module must satisfy. It is the SDK. A new module is correctly built when it follows this contract; a module that diverges from this contract has either chosen incorrectly or surfaced a missing platform abstraction (in which case this contract is updated, not the module).

For architectural invariants modules must respect see `Cloris-Architecture-North-Star.md`. For per-module specs see `docs/<module>-module-spec.md`. For implementation plans see `plans/<module>-module-build.md`.

The canonical reference modules are `linkedin/` and `github/`. New modules mirror their structure exactly. When this contract and the existing code disagree, the contract is what new modules implement; the existing code is updated to match in scheduled refactor work.

## 1. Required directory structure

Every module lives at `<module>/` at the repo root, paralleling `linkedin/` and `github/`. The required files are:

```
<module>/
  __init__.py
  orchestrator.py              # The Pipeline class equivalent
  session_orchestrator.py      # Day-cycle wrapper, governor integration
  client.py                    # External API client (or thin wrapper if multiple sources)
  acquisition.py               # Discovery / candidate enumeration
  enricher.py                  # Light + full enrichment passes
  strategy.py                  # form_strategy + adapt_after_batch
  judgment_templates.py        # Per-source facial + full eval prompts
  schemas.py                   # ModuleCandidate dataclass + helpers
  work_units.py                # ModuleWorkUnitService
  side_effects.py              # Save handling, outreach generation, exports
  governor.py                  # Per-module rate limit / session limits
  recruiter_identity_resolver.py  # Cross-source identity resolution to LinkedIn
```

Some files may be thin (e.g., `governor.py` for an API-only module may just configure rate limits and session-duration caps). Each must exist so the integration surface is uniform across modules. Every line of every module file follows the established voice: source-agnostic where the substrate allows, source-specific where the source genuinely demands it.

For modules with multiple data sources (e.g., Researcher pulls from OpenAlex + Semantic Scholar + dblp + arXiv), `client.py` is a thin facade and the per-source clients live at `<module>/sources/<source>.py`. The Researcher module spec is the canonical example.

## 2. Required exports in `shared/judger.py`

Every module exports two judgment functions in the shared dispatch surface:

```python
def <module>_facial_judge(<evidence_text_or_snippet>: <Type>, brief: Brief | None = None) -> OpusDecision:
    ...

def <module>_full_judge(<evidence_text_or_summary>: <Type>, brief: Brief | None = None) -> OpusDecision:
    ...
```

The shape mirrors `github_facial_judge` and `github_full_judge` at `shared/judger.py:776-869`. Each function:

- Takes the evidence appropriate to the module (string for text-based modules, dataclass for typed-evidence modules).
- Loads `_brief` if not provided, raises `RuntimeError` if neither.
- Asserts V2 brief schema (`b.has_v2_schema`) — modules do not support legacy briefs.
- Calls the module's `judgment_templates.assemble_<module>_<stage>_system` to build the prompt.
- Calls `facial_llm` or `opus_llm_cached` for inference.
- Wraps errors via `judgment_failure_decision`.
- Parses the response via the module's parser, mapping to `OpusDecision`.

Batch variants (`<module>_facial_judge_batch`) are added when the module does facial triage in batches. The pattern is in `shared/judger.py:876-1019`.

## 3. Required `RuntimeStateBridge` in `shared/runtime_state/<module>.py`

Each module owns a runtime-state bridge mirroring `LinkedInRuntimeStateBridge` (`shared/runtime_state/linkedin.py`) and `GitHubRuntimeStateBridge` (`shared/runtime_state/github.py`). The bridge:

- Wraps `RuntimeStateStore` operations the orchestrator and side-effects service need.
- Owns module-specific projection writes (e.g., progress JSON shape, stage JSONLs).
- Pins brief identity at run-start via `start_run_with_brief_pinning` (passes `brief_path`, computes hash + canonical snapshot).
- Records module-specific events with the module's vocabulary.

Export the bridge from `shared/runtime_state/__init__.py`.

## 4. Required work-unit `KIND` constant in `shared/runtime_state/store.py`

Each module declares its work-unit kind(s) at the top of `shared/runtime_state/store.py:37-39`:

```python
LINKEDIN_STRING_KIND = "linkedin_string"
GITHUB_QUERY_KIND = "github_query"
GITHUB_GRAPH_SEED_KIND = "github_graph_seed"
RESEARCHER_AUTHOR_QUERY_KIND = "researcher_author_query"  # new
MAINTAINER_PACKAGE_QUERY_KIND = "maintainer_package_query"  # new
```

The constant is used by:

- `<module>/work_units.py` when creating work units.
- `cloris/control_plane.py:_progress_kind_for_source` when summarizing per-module progress for the UI.
- Module projections when filtering work units by kind.

A module may declare multiple kinds when its discovery pattern uses multiple work-unit shapes (GitHub uses both `GITHUB_QUERY_KIND` for searches and `GITHUB_GRAPH_SEED_KIND` for graph expansion).

## 5. Required `resolve_<module>_state_dir` in `shared/output_paths.py`

Each module owns a state-directory resolver mirroring `resolve_linkedin_state_dir` and `resolve_github_state_dir`. The resolver:

- Computes the per-brief state directory under `output/state/<module>/<brief_state_key>/`.
- Creates the directory if missing.
- Returns the canonical `Path`.

Used by the orchestrator's `__init__` and by the Cloris control plane when enumerating state directories.

The state-key derivation is module-specific but should be stable across runs of the same brief (LinkedIn uses `linkedin_project_id`; GitHub uses `brief.id`; new modules pick a stable key from brief content).

## 6. Required Cloris control plane registration

Each module registers itself with the Cloris control plane in five places:

1. **`cloris/control_plane.py:175`** — add module name to `_SOURCES`.
2. **`cloris/control_plane.py:_progress_kind_for_source`** — return the module's primary work-unit kind.
3. **`cloris/api.py`** — module is dispatched by the generic `POST /api/launch/{source}` and `POST /api/resume/{source}` endpoints (post-foundation work). Pre-foundation, module-specific endpoints exist; post-foundation, dispatch is generic.
4. **`cloris/models.py:LaunchResponse.source` and `cloris/models.py:StateDirEntry.source`** — module name added to the `Literal` type.
5. **`cloris/worker.py` dispatch table** — maps module name to `<module>.session_orchestrator` for spawn (`build_session_orchestrator_argv`).

The post-foundation pattern is: module name strings are the registration key everywhere; no per-module hardcoding outside the dispatch tables.

## 7. Reuse the shared candidate execution engine

Modules consume `CandidateExecutionEngine` (`shared/execution/runtime.py`) for stage-attempt tracking and side-effect recording. Modules do not implement parallel state-management logic.

The minimum integration is:

- Construct a `CandidateExecutionEnvelope` (`shared/execution/types.py`) per candidate with: `run_id`, `source`, `brief_id`, `identity_key`, `display_name`, `profile_url`, `work_unit_kind`, `work_unit_source_id`, `source_cursor` (free-form module-specific dict for resume context), and optional `snippet`.
- Call `engine.record_discovery(envelope, payload=...)` when a candidate is first observed.
- Call `engine.start_stage(envelope, stage="facial", payload=...)` to begin a stage attempt; receive `attempt_id`.
- Call `engine.finish_stage_success(attempt_id=..., envelope=..., stage="facial", decision=...)` on success.
- Call `engine.finish_stage_failure(attempt_id=..., envelope=..., stage="facial", error_or_failure_decision=...)` on failure.
- Call `engine.record_side_effect_result(envelope=..., attempt_id=..., effect_type=..., status=..., payload=...)` after side effects complete.

The pattern is in `github/orchestrator.py` from line 148; `linkedin/orchestrator.py` is similar but predates the engine in some places (legacy compatibility paths).

## 8. Reuse the shared safety layer

Each module instantiates `RunSafetyCoordinator` (`shared/safety/coordinator.py`) at orchestrator init:

```python
self._safety = RunSafetyCoordinator(
    store=self._runtime_state,
    output_dir=self.output_dir,
    source="<module>",
    brief_id=self._brief_id,
)
```

The coordinator handles run-finish, governor-limit recording, browser-recovery events (for browser-based modules), and stop-reason normalization. Modules do not implement parallel safety logic. Module-specific recovery (e.g., `LinkedInRecoveryService` for browser disconnect) is allowed but plugs into the coordinator, not around it.

## 9. Reuse the brief loader and judger init

Module orchestrators load briefs via `shared.brief_loader.load_brief` and initialize the judger via `shared.judger.init_judger(brief)` exactly as `linkedin/orchestrator.py:175,192` and `github/orchestrator.py:77,87` do. Modules do not parse briefs themselves.

V2 schema is required (`b.has_v2_schema` is asserted). Modules do not support legacy briefs.

## 10. Reuse the shared brief schema

Module-specific brief calibration goes in nested fields on the brief, not in the module's code. The pattern:

- Module declares a `<Module>Calibration` dataclass in `shared/brief_schema.py` (e.g., `ResearcherCalibration`, `MaintainerCalibration`).
- Brief carries `<module>_calibration: <Module>Calibration` field with default factory.
- Brief loader hydrates the field from V2 brief JSON.
- Module reads the calibration from `brief._new_brief.<module>_calibration` and passes it to the strategy and judgment template assemblers.

The detailed shape is in `docs/cloris-brief-multi-module-extensions.md`.

The capability_areas, depth_distinction, non_fit_patterns, employer_signal_rules, retrieval_design, and the calibration vocabulary fields are paradigm-neutral — modules consume them without modification. Source-specific patterns (e.g., `arxiv_category_signals` on `CapabilityArea`) are added as additive optional fields.

## 11. Save destination declaration

Each module's brief declares its save destination(s). The mechanism is in `docs/cloris-save-destination-abstraction.md`. Briefly:

- Brief has `save_destinations: list[str]` field (e.g., `["candidate_workspace"]` for a Researcher brief; `["linkedin_recruiter", "candidate_workspace"]` for a LinkedIn brief that also writes to the workspace).
- Module's side-effects service dispatches `SAVE` decisions to each declared destination via the `AbstractSaveDestination` interface.
- LinkedIn Recruiter destination is the existing browser-click behavior (`linkedin/side_effects.py:handle_save_decision`).
- Candidate Workspace destination writes to the shared workspace tables.

A module may declare a default save destination in its module-config, overridable in the brief.

## 12. Cross-module identity resolution

Each module ships a recruiter identity resolver in `<module>/recruiter_identity_resolver.py` that bridges the module's identity space to LinkedIn (and through LinkedIn, to the candidate workspace's `person` records). The resolver:

- Takes a module candidate (e.g., a Researcher with ORCID, name, affiliation).
- Searches LinkedIn (browser-based, humanized) for plausible matches.
- Resolves identity via the four-step pattern in `GitHub-LinkedIn-Reconciliation-Source-of-Truth.md` §4: review first N cards, identify plausible candidates, reject clearly wrong, open up to top K plausible profiles.
- Returns a `RecruiterIdentityResolution` per `shared/recruiter_identity_schemas.py`.

Cross-source identity reconciliation (Researcher↔GitHub, GitHub↔Defense, etc.) is handled by the shared layer in `shared/cross_module_identity/` per `docs/cloris-cross-module-identity-resolution-spec.md`. Modules do not implement cross-module identity directly.

## 13. Failure decision contract

Per `shared/contracts.py`:

- `PARSE_FAILURE` and `JUDGMENT_FAILURE` are non-terminal failure decisions. Parsers must not emit terminal business outcomes (`SAVE`, `REJECT`) on parse failure.
- `FACIAL_DECISIONS` are `FACIAL_YES`, `FACIAL_NO`, `FACIAL_BORDERLINE` (currently aliased to `FACIAL_YES` at orchestrator boundary), plus the failures.
- `FULL_DECISIONS` are `SAVE`, `REJECT`, `INFERENTIAL_SAVE`, `TRANSFERABLE_SAVE`, `SIGNAL_SAVE`, plus the failures.
- `SAVE_DECISIONS` is the subset that triggers side effects: `SAVE`, `INFERENTIAL_SAVE`, `TRANSFERABLE_SAVE`, `SIGNAL_SAVE`.

Modules do not invent new decision values. If a module believes it needs a new decision, it surfaces the case for review and updates `shared/contracts.py` rather than diverging unilaterally.

## 14. Event vocabulary

Modules emit events to `shared/storage.log_event` and to the canonical store via `record_event`. The shared event vocabulary is in `shared/contracts.py:RUN_LOG_EVENTS`.

Module-specific events use the convention `<module>_<event>` (e.g., `researcher_author_resolved`, `maintainer_package_indexed`). Module events are added to `RUN_LOG_EVENTS` so the contract is auditable.

## 15. Test contract

Every module ships with the following test coverage in `tests/`:

- **Pipeline characterization test** at `tests/test_<module>_pipeline.py` — covers end-to-end flow with mocked external clients. Pattern: `tests/test_linkedin_pipeline.py`, `tests/test_github_pipeline.py`.
- **Runtime-state test** at `tests/test_<module>_runtime_state.py` — covers state-machine transitions, dedup, resume. Pattern: `tests/test_linkedin_runtime_state.py`.
- **Judgment template test** at `tests/test_<module>_judgment_templates.py` — covers prompt assembly with calibrated briefs and parser behavior on all decision shapes (including failure cases).
- **Brief schema test extension** in `tests/test_phase0_contracts.py` (or a sibling) verifying the module's calibration fields hydrate from V2 brief JSON.
- **Cloris status aggregation test extension** in `tests/test_cloris_status_aggregation.py` covering the new `_SOURCES` entry.

The narrowest test band a module owner runs first is `pytest tests/test_<module>_*.py -q`. The full-suite gate before declaring a module shipped is `make validate`.

## 16. Module scaffolding checklist

A new module is correctly scaffolded when all of the following are true. This is the audit list for a new-module pull request.

- [ ] `<module>/` directory exists with all 12 required files.
- [ ] `<module>/__init__.py` does not import the orchestrator at module load (lazy imports inside functions per `linkedin/__init__.py`); avoids circular dependency on `shared/runtime_state/store.py`.
- [ ] `shared/judger.py` exports `<module>_facial_judge` and `<module>_full_judge` (and batch variants if applicable).
- [ ] `shared/runtime_state/<module>.py` defines `<Module>RuntimeStateBridge` and exports it from `shared/runtime_state/__init__.py`.
- [ ] `shared/runtime_state/store.py` declares the module's `KIND` constant(s).
- [ ] `shared/output_paths.py` declares `resolve_<module>_state_dir` and `<module>_state_key`.
- [ ] `shared/brief_schema.py` declares `<Module>Calibration` with default factory; brief carries the field.
- [ ] `shared/brief_loader.py` hydrates the calibration from V2 brief JSON.
- [ ] `cloris/control_plane.py:_SOURCES` includes the module.
- [ ] `cloris/control_plane.py:_progress_kind_for_source` returns the module's primary kind.
- [ ] `cloris/models.py` widens the `Literal` types to include the module name.
- [ ] `cloris/worker.py` dispatch table includes the module's session orchestrator.
- [ ] `cloris/api.py` (post-foundation work) routes generic `/api/launch/{source}` to the module via the dispatch table.
- [ ] `tests/test_<module>_*.py` exist with the four required test files.
- [ ] Per-module docs/spec exists at `docs/<module>-module-spec.md` (or workflow-spec.md).
- [ ] Implementation plan exists at `plans/<module>-build.md` (during build) or in `plans/archive/` (post-ship).

## 17. What modules do not own

Equally important. Modules do not own:

- Schema migrations to `shared/runtime_state/store.py`'s core tables. Only additive fields and new tables added through the canonical migration path.
- The brief-iteration / Next Run Learning surface (`shared/brief_iteration.py`). Modules consume it.
- The Cloris UI surfaces. Modules surface data; the UI is unified.
- The candidate workspace data model. Modules write through the save destination interface; the workspace is owned by the candidate workspace spec.
- Cross-module identity resolution algorithms. Per-source-pair adapters live in `shared/cross_module_identity/`, not in module directories.
- The decision contract (`shared/contracts.py`). Modules conform; they do not invent.
- Process-pool-level budgeting (`shared/safety/cross_module_governor.py`, future). Modules respect it.

## 18. Decisions captured here

- 2026-04-29 — Module directory structure mirrors `linkedin/` and `github/` exactly; each module ships all 12 required files even if some are thin.
- 2026-04-29 — `shared/judger.py` dispatch is flat (one function per (module, stage) pair); not hierarchical.
- 2026-04-29 — Modules cannot invent decision vocabulary. New decisions update `shared/contracts.py` through scheduled work.
- 2026-04-29 — Save destination is declared in the brief, not in module code. Modules implement `AbstractSaveDestination` for any new destinations they need.
- 2026-04-29 — Cross-module identity is shared infrastructure; modules ship the `recruiter_identity_resolver.py` for module→LinkedIn but do not implement cross-module-pair adapters in their own directory.
- 2026-04-29 — Test contract is mandatory. New modules ship with the four required test files; the full-suite `make validate` gate applies.
