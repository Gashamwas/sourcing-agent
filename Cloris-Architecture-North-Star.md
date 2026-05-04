# Cloris Architecture North Star

Status: living
Owner: Sam
Last updated: 2026-04-29

This document defines the architectural invariants that bound every module, surface, and runtime change in Cloris. It is the technical complement to `Cloris-Product-North-Star.md`. Implementation specs and plans inherit their contracts from here.

For control-plane semantics see `docs/cloris-control-plane-spec.md`. For the shared candidate execution engine see `docs/shared-candidate-execution-engine.md`. For the completed runtime/state migration history see `Sourcing-Agent-2nd-Gen-Roadmap.md`. For module integration mechanics see `docs/cloris-module-integration-contract.md`.

The invariants below are normative. New work either preserves them, formally extends them through this document, or is rejected.

## 1. The substrate is `runtime_state.sqlite3` per state directory

The canonical durable state for every Cloris run lives in a per-state-directory SQLite database (`shared/runtime_state/store.py:73-243`). The schema covers `runs`, `work_units`, `candidates`, `candidate_attempts`, `events`, `side_effects`, with foreign-key cascades and an enforced lifecycle transition table (`shared/runtime_state/store.py:62-71`).

The invariants the substrate enforces and the rest of the platform must respect:

- **Canonical-first.** `progress.json`, stage JSONLs (`snippets.jsonl`, `facial_judgments.jsonl`, `final_judgments.jsonl`), candidate history files, and search-memory files are projections owned by the projection layer (`shared/runtime_state/projections.py`). They are reconstruction outputs, not control inputs (`Sourcing-Agent-2nd-Gen-Roadmap.md:381-393`). New code must not read from projections to make runtime decisions.
- **One canonical writer per state directory.** The detached worker process is the only authorized writer for an active state directory (`docs/cloris-ui-spec.md:62-63`). The Cloris UI/API process opens the SQLite file read-only via `sqlite3.connect(f"file:{path}?mode=ro", uri=True)` (`cloris/control_plane.py:8-17`). Two writers in the same state directory is an invariant violation, not a configuration option.
- **Schema migration is gated and idempotent.** Migrations live in `shared/runtime_state/store.py:_migrate` and are gated on `meta.schema_version`. New columns get sensible defaults so legacy rows survive; one-shot normalizations are idempotent across mixed-version writers.
- **Read-only aggregation is its own seam.** `cloris/control_plane.py` is the single seam between Cloris and per-state-directory disk artifacts. It does not import the canonical store class in production paths to avoid running unconditional DDL on every API request.

These invariants mean the Cloris substrate is operationally trustable across crash-recovery, schema evolution, multi-process operation, and external observability. They also mean that adding a module does not get to reinvent state.

## 2. Source discrimination is universal

Every relevant table in the substrate carries `source` as a column (`shared/runtime_state/store.py:121-205`). `runs.source`, `work_units.source`, `candidates.source`, `candidate_attempts` indirectly through `candidate_id`. The `candidates` table enforces `UNIQUE(brief_id, source, identity_key)` (`shared/runtime_state/store.py:182`) so the same person discovered by two sources is two rows under the discrimination contract.

The implications and limits:

- **Multi-module concurrent operation is supported at the storage layer.** Two workers writing to two different state directories under the same brief, one for `linkedin`, one for `researcher`, is a supported pattern. The state directories live at `output/state/<source>/<brief_state_key>/` (`shared/output_paths.py:resolve_<source>_state_dir`). Each worker holds its own `RuntimeStateLock` for its own state directory; no cross-state-directory locking is required.
- **Cross-source candidate dedup is not provided by the substrate.** It is a separate layer. The substrate stores per-source rows; reconciling them into person records is the job of `shared/cross_module_identity/` (described in `docs/cloris-cross-module-identity-resolution-spec.md`).
- **Work-unit kinds are source-namespaced.** `LINKEDIN_STRING_KIND`, `GITHUB_QUERY_KIND`, `GITHUB_GRAPH_SEED_KIND` (`shared/runtime_state/store.py:37-39`) plus future module-specific kinds (`RESEARCHER_AUTHOR_QUERY_KIND`, `MAINTAINER_PACKAGE_QUERY_KIND`, etc.). Each module owns its own KIND constant declared in `shared/runtime_state/store.py`.
- **Decision vocabulary is source-agnostic.** `DEDUP_BLOCKING_LINKEDIN_DECISIONS` is misnamed (`shared/runtime_state/store.py:49-57`) — the decisions in that set (`SAVE`, `REJECT`, `INFERENTIAL_SAVE`, `TRANSFERABLE_SAVE`, `SIGNAL_SAVE`) are not LinkedIn-specific. The constant should be renamed `DEDUP_BLOCKING_TERMINAL_DECISIONS` as part of the multi-module foundation work.

## 3. Briefs are the role contract

The V2 brief (`shared/brief_schema.py:179-260`) is the single source of truth for what a role is. Brief authoring is the work of calibrating a role; running a brief is the work of executing against that calibration. The split is rigorous: nothing role-specific lives outside the brief.

Architectural commitments for briefs:

- **The structural fields are paradigm-neutral.** `capability_areas`, `depth_distinction`, `non_fit_patterns`, `employer_signal_rules`, `facial_calibration`, `bias_controls`, `retrieval_design`, the calibration vocabulary fields (`domain_verbs`, `transferability_examples`, `canonical_*_patterns`, `term_blacklist_categories`, `abbreviation_collisions`, `example_compounds`) — all of these describe roles, not sources. They work for ML researchers, defense engineers, biotech computational scientists, designers, and sales leaders without structural change.
- **Source-specific calibration is nested, not flat.** The current bolt-on of `github_*_patterns` onto `FacialCalibration` (`shared/brief_schema.py:104-107`) is an artifact of two-source operation and does not scale. The multi-module foundation work (`docs/cloris-brief-multi-module-extensions.md`) replaces this with per-source nested calibration so a brief can carry calibration for any number of sources without flattening every field name.
- **`linkedin_project: str` defaults to empty.** The required-no-default declaration at `shared/brief_schema.py:190` predates non-LinkedIn modules and breaks them. The fix is `linkedin_project: str = ""`. LinkedIn side-effects handle empty gracefully. See `docs/cloris-brief-multi-module-extensions.md`.
- **`target_modules: list[str]` is part of the brief.** A brief declares which discovery modules it targets. The default is `["linkedin"]`. The Cloris UI uses this to filter brief lists, validate brief authoring, and gate launch options. See `docs/cloris-brief-multi-module-extensions.md`.
- **The dual-brief bridge stays.** `shared/brief_loader.py` will continue to expose both the structured `_new_brief` (`shared.brief_schema.Brief`) and the compat `Brief` for legacy strategy/orchestration code. Rewriting orchestrators around a single brief model is higher-risk than mirroring calibration onto the compat brief (`plans/calibration-layer-vertical-agnostic.md:97-99`).
- **Brief identity is pinned at run-start.** `runs.brief_path_at_launch`, `runs.brief_content_hash`, `runs.brief_snapshot_json` (`shared/runtime_state/store.py:303-317`) capture the brief as it was when the run executed. Drift detection (`cloris/control_plane.py:_detect_brief_drift`) tells the UI whether the on-disk brief has changed since.

## 4. Evaluation is a structural template, not a per-source pipeline

The four-step structural procedure — capability mapping, depth test, transferability test, decision — is the durable substrate. Source-specific judgment templates instantiate the procedure with source-specific evidence framing.

Architectural commitments for evaluation:

- **The procedure is in the brief, not the code.** `Brief.capability_area_block()`, `Brief.depth_block()`, `Brief.non_fit_block()`, `Brief.decision_matrix_block()`, etc. (`shared/brief_schema.py:266-530`) render the procedure into prompt text from brief content. Code does not embed role-specific vocabulary; it composes brief-supplied vocabulary into the procedure.
- **Per-source judgment templates are thin.** `linkedin/judgment_templates.py` and `github/judgment_templates.py` differ from each other in evidence framing (snippet vs. portfolio text) and source-specific calibration (LinkedIn trajectory patterns vs. GitHub portfolio patterns), not in evaluation logic. New modules add `<module>/judgment_templates.py` following the same shape.
- **`shared/judger.py` is the dispatch surface.** It exposes `facial_judge`, `full_judge`, `github_facial_judge`, `github_full_judge`, etc. (`shared/judger.py:776-869`). New modules add `<module>_facial_judge` and `<module>_full_judge` following the GitHub pattern. The dispatch surface is flat, not hierarchical.
- **Failure decisions are non-terminal and source-agnostic.** `PARSE_FAILURE` and `JUDGMENT_FAILURE` (`shared/contracts.py:43`) are recoverable. Parsers must not emit terminal business outcomes (`SAVE`, `REJECT`) on parse failure (`Sourcing-Agent-2nd-Gen-Roadmap.md:107-134`). This rule binds every per-source judgment template.
- **External evidence augmentation is a sibling path.** `shared/external_evidence/` provides Perplexity-augmented full evaluation (`shared/judger.py:649-769`). The system prompt is identical to the non-augmented path so prompt-cache hits on the static prefix are preserved; only the user message carries the external evidence block.

## 5. Candidate lifecycle is source-agnostic

The lifecycle states defined at `shared/runtime_state/store.py:62-71` are paradigm-neutral despite their LinkedIn-vocabulary names:

```
discovered → snippet_extracted → facial_started → facial_terminal
                                                  ↓
                                                 full_started → full_terminal
                       failed_retryable, failed_terminal (terminal sinks)
```

Architectural commitments for the lifecycle:

- **Names are LinkedIn-vocabulary; semantics are source-agnostic.** "snippet_extracted" means "light evidence acquired"; "facial_terminal" means "triage decision recorded"; "full_terminal" means "deep evidence evaluated, decision recorded." Every module maps onto these states without renaming. Renaming the states is not on the roadmap; renaming would break every existing test and projection without changing the structure.
- **Allowed transitions are enforced at the store layer.** `ALLOWED_LIFECYCLE_TRANSITIONS` (`shared/runtime_state/store.py:62-71`) is enforced on every state mutation. New modules cannot invent transitions; they map onto the existing graph.
- **Failure transitions are universal.** `failed_retryable` is recoverable from `discovered`, `snippet_extracted`, `facial_started`, `full_started`. `failed_terminal` is reachable from any non-terminal state. New modules use the same recovery semantics; they do not declare their own failure-state model.

## 6. Worker model: one detached worker per state directory

The Cloris worker (`cloris/worker.py`) spawns a detached Python subprocess that owns the active run. The process model is documented in `docs/cloris-control-plane-spec.md` and `docs/cloris-ui-spec.md:54-72`.

Architectural commitments for workers:

- **One worker per `(source, brief_state_key)` pair.** The state directory layout (`output/state/<source>/<brief_state_key>/`) plus `RuntimeStateLock` per state directory (`shared/runtime_state/lock.py`) enforces this. Two concurrent workers in the same state directory is a lock conflict; the second is rejected.
- **The worker outlives the UI window.** Closing the Cloris UI does not kill an active run. The worker writes a `worker.json` sidecar (`cloris/worker.py:70-117`) atomically; the UI re-discovers active runs on reopen.
- **Workers are source-parameterized at spawn.** Today `cloris/worker.py:196` hardcodes `linkedin.session_orchestrator`. The multi-module foundation work parameterizes this via a CLI flag and dispatch table; the spawned orchestrator module name comes from the launch request, not from a hardcoded import.
- **Multi-module operation = multiple workers.** A brief targeting LinkedIn + Researcher + GitHub spawns three workers in three state directories. There is no shared-state-directory multi-module worker model in v1; that's a v2 architectural decision if it ever becomes necessary.
- **Cross-worker rate budgets need explicit coordination.** Each worker today has its own governor (`shared/governor.py`); LLM API budget is not coordinated across modules. Process-pool-level governing (`shared/safety/cross_module_governor.py`, future) becomes urgent at module #3. Until then, the workload-per-day limits per worker are the budget control.

## 7. The five UI surfaces

`docs/cloris-ui-spec.md:163-251` defines five canonical UI surfaces. They are the surface contract for every module.

- **Authoring Loop** — turn a role/JD into a runnable brief. Machine draft + human review (`shared/preflight_v2.py`). Multi-module-aware: a single brief carries calibration for every module it targets.
- **Launch Gate** — the readiness check. Per-module readiness probes (LinkedIn: browser session; GitHub: token; Researcher: API keys; etc.). Module-specific blockers must be surfaced here, not deferred to the worker.
- **Ambient Home** — default landing. Recent runs, current run summary if active, calm posture. Multi-module: visually segmented by source but unified in the ledger.
- **Run Review** — who Cloris surfaced, why, what happened. Person-first when cross-module identity resolution lands; per-source until then. Reads from canonical state, not from `output/` artifacts.
- **Next Run Learning** — feedback to brief revision. The closed-loop surface. The longest-pole UI investment and the platform's long-term moat.

Each surface reads from the same canonical substrate. None of them have private state.

## 8. Module integration contract (summary)

Every new module follows the same shape. The full contract is in `docs/cloris-module-integration-contract.md`; the architectural invariants the contract enforces are:

- **Module directory structure mirrors `linkedin/` and `github/`.** Required files: `orchestrator.py`, `session_orchestrator.py`, `client.py`, `acquisition.py`, `enricher.py`, `strategy.py`, `judgment_templates.py`, `schemas.py`, `work_units.py`, `side_effects.py`, `governor.py`, `recruiter_identity_resolver.py`. Some are thin (e.g., `governor.py` may just configure rate limits) but each must exist so the integration surface is uniform.
- **Module declares one or more `KIND` constants** in `shared/runtime_state/store.py`. Used by work-unit creation and projections.
- **Module exports `<module>_facial_judge` and `<module>_full_judge`** in `shared/judger.py`. Dispatch is flat; one function per (module, stage) pair.
- **Module owns a `RuntimeStateBridge` in `shared/runtime_state/<module>.py`.** Mirrors `LinkedInRuntimeStateBridge` (`shared/runtime_state/linkedin.py`) and `GitHubRuntimeStateBridge` (`shared/runtime_state/github.py`).
- **Module owns a `resolve_<module>_state_dir` in `shared/output_paths.py`.** Returns the per-brief state directory under `output/state/<module>/`.
- **Module registers with the Cloris control plane.** `_SOURCES` in `cloris/control_plane.py:175` includes the module name; `cloris/api.py` exposes launch/resume/stop endpoints (or, post-foundation work, the generic `/api/launch/{source}` endpoint dispatches to it); `cloris/models.py:LaunchResponse.source` literal includes the module name; `cloris/worker.py` dispatch table maps the module to its session orchestrator.
- **Module reuses the shared execution engine.** `CandidateExecutionEngine` (`shared/execution/runtime.py`) and `CandidateExecutionEnvelope` (`shared/execution/types.py`) are the shared primitives for stage attempts and side effects. Modules consume them, do not bypass them.
- **Module reuses the shared safety layer.** `RunSafetyCoordinator` (`shared/safety/coordinator.py`) handles attempt tracking, governor limit recording, and stop-reason normalization. Modules instantiate it; they do not implement parallel safety logic.

## 9. Save destination is an abstraction, not a click

Today, "SAVE" for LinkedIn means a browser click in `linkedin/side_effects.py:handle_save_decision`. This is a LinkedIn-Recruiter-platform-specific side effect. For non-LinkedIn modules there is no LinkedIn Recruiter to click; the module needs a destination.

The architectural commitment: there is one `AbstractSaveDestination` interface, and per-destination implementations:

- `LinkedInRecruiterSaveDestination` — browser click (existing behavior).
- `CandidateWorkspaceSaveDestination` — writes to the Cloris-native saved-candidate workspace described in `docs/cloris-candidate-workspace-spec.md`.
- Future destinations (webhook, CSV export, ATS API) are added by implementing the interface.

A brief declares its save destination(s) per module. The orchestrator dispatches to the configured destination on `SAVE` decisions. Sister artifact: `docs/cloris-save-destination-abstraction.md`.

## 10. Cross-module identity resolution is its own layer

The substrate's `UNIQUE(brief_id, source, identity_key)` constraint means a person in two sources is two candidate rows. This is correct at the storage layer. Aggregating those rows into a single person view is the job of a separate layer.

Architectural commitments:

- **`person` and `person_candidate` tables** added to the substrate (`shared/runtime_state/store.py` migration). Per-brief person records; many-to-one mapping from candidates to persons.
- **`shared/cross_module_identity/` directory** holds adapter functions per `(source_a, source_b)` pair. Researcher↔LinkedIn uses ORCID + name + affiliation. GitHub↔LinkedIn uses commit-author email + name. Defense↔LinkedIn uses inventor-on-patent + name + employer. Each adapter declares confidence and resolution method.
- **Resolution runs as a post-stage**, not real-time. Real-time cross-source matching adds latency and is unnecessary for v1; offline reconciliation against the canonical store is sufficient.
- **The Run Review UI surface presents persons, not rows**, once cross-module identity resolution lands. Until then, per-source rows with manual cross-references.

Spec: `docs/cloris-cross-module-identity-resolution-spec.md`.

## 11. Anti-detection and safety are source-specific within a shared shell

LinkedIn-specific anti-detection (humanized timing, profile-read simulation, decoy interleaving, browser recovery) lives in `linkedin/browser.py`, `shared/human_timing.py`, `shared/safety/linkedin_recovery.py`, and the decoy module. These are LinkedIn-coupled by design.

For other modules, anti-detection is a per-source concern:

- **API-only modules** (Researcher with OpenAlex/Semantic Scholar/dblp/arXiv/PubMed; OSS Maintainers with npm/PyPI/crates.io) have no detection risk and no recovery layer. They have rate limits, which are a different problem handled by the per-module governor.
- **Cloudflare-hostile modules** (Designer with Behance scraping; Defense with IEEE Xplore in some access modes) need carefully-bounded scraping with rendering and pacing. The shared `RunSafetyCoordinator` provides the attempt/recovery contract; per-module recovery logic implements the source-specific reconnect.

The shared shell is `RunSafetyCoordinator`, `RuntimeStateLock`, governor pattern, and stop-reason normalization. The per-source filling-in is allowed and expected.

## 12. The architectural roadmap inside this north star

This document lists architectural invariants that already hold or will hold after foundation work. The temporal sequencing — when each invariant lands, in what order, gated by what dependencies — lives in `Cloris-Multi-Module-Roadmap.md` and the implementation plans under `plans/`. The two artifacts together (this north star + the roadmap) are the architectural source of truth for the platform's evolution.

Specifically:

- The substrate invariants in §1-2 are already in place. They do not need new work to support multi-module operation.
- The brief-schema invariants in §3 require the foundation work in `plans/multi-module-foundation.md` (`linkedin_project` default fix, `target_modules` field, per-source nested calibration).
- The evaluation invariants in §4 require the calibration vertical-agnostic refactor (`plans/calibration-layer-vertical-agnostic.md`) to land Slices 2-5 before any non-LinkedIn module is shippable to a paying customer.
- The save-destination invariants in §9, candidate-workspace invariants implicit in §10, and cross-module identity invariants in §10 are all foundation work landing alongside the first non-LinkedIn module.
- The five-surface invariants in §7 have varying maturity: Ambient Home and Launch Gate are partially built (Cloris v0 shell); Authoring Loop, Run Review, and Next Run Learning are scoped but not built.

## 13. Decisions captured here

- 2026-04-29 — `runtime_state.sqlite3` is the canonical control-state. Stage JSONLs and progress files are projections, not control state. Confirmed (`Sourcing-Agent-2nd-Gen-Roadmap.md:381-393`).
- 2026-04-29 — Cross-module candidate identity is a separate layer over the substrate's per-source rows; the substrate's `UNIQUE(brief_id, source, identity_key)` stays.
- 2026-04-29 — Save destination becomes an abstraction; LinkedIn Recruiter is one implementation, candidate workspace is another, future destinations slot in via the same interface.
- 2026-04-29 — Lifecycle states keep their LinkedIn-vocabulary names; renaming would break tests and projections without changing semantics. Modules map onto the existing state graph.
- 2026-04-29 — Multi-module operation in v1 = multiple workers in multiple state directories. Shared-state-directory multi-module workers is a v2 architectural decision if ever needed.
- 2026-04-29 — `cloris/worker.py:196` parameterization is a foundation-work prerequisite for any non-LinkedIn module shipping. Scoped in `plans/multi-module-foundation.md`.
