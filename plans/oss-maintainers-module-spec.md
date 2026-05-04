# oss-maintainers-module-spec

Status: ready-to-implement
Owner: Sam
Last updated: 2026-05-03

> **Supersession notice.** This spec replaces [plans/oss-maintainers-build.md](plans/oss-maintainers-build.md). That plan framed V1 as registry-adapter breadth (npm + PyPI + crates.io). This spec inverts the order: evaluation depth first, registry adapters move to §16 Follow-ups gated on Phase 2 customer demand. Rationale in §6.

## 1. Status / Provenance

- File: [plans/oss-maintainers-module-spec.md](plans/oss-maintainers-module-spec.md). This file.
- Supersedes: [plans/oss-maintainers-build.md](plans/oss-maintainers-build.md). That plan's slice 2-7 registry-adapter work becomes Phase 3 follow-up.
- Sliced into 10 PR-sized slices. Slice 1 is this audit (`zero code`); Slices 2-9 are code; Slice 10 is customer launch + held-out classifier regression check.
- Slice 4 and Slice 10 gate on a hand-classified ground-truth fixture with explicit agreement-rate thresholds (see §13.1). Slice 4 does not ship until the gate is green.
- Estimated 10-14 business days at dedicated focus. Slice 4 includes 2-5 hours of hand-classification work to build the fixture.
- Owner: Sam. Status on write: `ready-to-implement` after Slice 1 ratification.

## 2. Problem

[github/](github/) ships today but its evaluation floor is commit-count-and-bio. For senior IC roles where OSS maintainership is load-bearing (Staff Engineer at a dev-tools company hiring from its own ecosystem; infra role needing merge authority on a relevant project), the module over-returns drive-by contributors and under-distinguishes them from actual maintainers. Three concrete gaps, file:line cited:

- **Evaluation prompt references signals the code never delivers.** [github/judgment_templates.py:143](github/judgment_templates.py) says evidence "includes repo commit activity summaries," but [github/schemas.py:346-443](github/schemas.py) `to_evidence_text()` omits `contribution_months` even though `GitHubCandidate` carries the field. [github/judgment_templates.py:151-154](github/judgment_templates.py) mentions "Merged PRs or substantive issues" and [github/judgment_templates.py:191-194](github/judgment_templates.py) mentions "org memberships," but [github/client.py:226-513](github/client.py) has no PR-review, issue, or `/users/{login}/orgs` endpoints. The LLM is asked to weigh evidence it cannot see.
- **No brief-level concept of a named project.** `target_repo` exists on `GitHubSearchQuery` at [github/schemas.py:487-489](github/schemas.py) but is query-plumbing, not recruiter-authored brief content. [shared/brief_v2_schema.py:187](shared/brief_v2_schema.py) `SOURCE_CONFIG_RECOGNIZED_KEYS_BY_SOURCE["github"] = frozenset()` — github's source-config is deliberately empty. A recruiter saying "we want a Kubernetes maintainer" has no brief field to encode it.
- **Brief-polish + reflection never reach github briefs.** Brief polish ([market_intelligence/brief_polish.py:463-513](market_intelligence/brief_polish.py)) hard-preserves `role_title`, `source_config.linkedin.project_id`, and `target_modules` — nothing maintainership-specific. Reflection gates on LinkedIn: [market_intelligence/engine.py:1621-1626](market_intelligence/engine.py) `maybe_build_and_persist_research_packet` runs only when `batch.source == "linkedin"`.

## 3. Goal

After this ships, a recruiter authors a brief naming three target projects and a `maintainership_level="maintainer"`, runs the github module, and receives candidates ranked by a classified maintainership-level (contributor / maintainer / project_lead) with evidence citing merge authority, release cadence, review activity, and CONTRIBUTORS/MAINTAINERS mentions. Brief polish preserves the named projects through iteration. Post-run reflection narrates ecosystem momentum for the named projects.

## 4. Non-goals

- Registry adapters (npm / PyPI / crates.io). Moves to Phase 3 follow-up gated on customer demand. Named-project evaluation is sufficient for V1.
- Live OpenSSF Criticality Score computation. V1 uses weekly snapshots.
- Private-repo signal acquisition (per-customer GitHub App install). Phase 3.
- Compensation / availability inference from public signals.
- Cloris-contributes-to-OSS. Not a product feature.
- Graph expansion from confirmed maintainer saves. V2 if customer signal.
- Fork or parallel-module architecture. Tier 2 extends [github/](github/) in place.

## 5. Assumptions

- **mfm-foundation absorption.** [plans/multi-module-foundation.md](plans/multi-module-foundation.md) is partially complete. Verified state as of 2026-05-03:
  - mfm Slice 1 (`linkedin_project: str = ""` default) — **NOT shipped**. [shared/brief_schema.py:190](shared/brief_schema.py) is still `linkedin_project: str` no default.
  - mfm Slice 2 (`target_modules: list[str]` Brief field) — **NOT shipped**. The key is recognized in `RECOGNIZED_V2_KEYS` at [shared/brief_v2_schema.py:97](shared/brief_v2_schema.py) but absent from the `Brief` dataclass at [shared/brief_schema.py:185-190](shared/brief_schema.py).
  - mfm Slice 3 (per-source nested calibration `FacialCalibration.sources: dict[str, SourceCalibration]`) — **NOT shipped**.
  - mfm Slices 4-5 (worker `--source` dispatch + generic `/api/launch/{source}`) — **SHIPPED** via Phase F1.
  - mfm Slices 6-7 (workspace tables + `AbstractSaveDestination`) — **NOT shipped**.
  - **Decision (2026-05-03):** Slice 2 of this plan absorbs mfm Slice 1 and Slice 2 substrate (`linkedin_project` default + `target_modules` Brief field). It does NOT absorb mfm Slice 3, 6, or 7 — none are reached by this module's slices. The other three parallel module threads (Researcher, Designer, Exec Search) sit on the same precondition; whichever thread's Slice 2 lands first absorbs the cost. This plan is defensive: existing-field setdefault semantics so a parallel thread that already absorbed the work doesn't conflict on rebase.
- GitHub authenticated rate limit is 5000 req/hr; code search 30/min. Tier 2 evaluation must respect this.
- GitHub `contents` API returns plaintext for CONTRIBUTORS / MAINTAINERS / GOVERNANCE.md under 1MB.
- Downstream-dependents count via `/network/dependents` page scrape is an honest signal despite being non-API (GitHub publishes it publicly; throttle conservatively).
- The user workspace ([docs/cloris-candidate-workspace-spec.md](docs/cloris-candidate-workspace-spec.md)) ships alongside or before Slice 10 as the native save destination for github-sourced candidates.

## 6. Reconciliation with [plans/oss-maintainers-build.md](plans/oss-maintainers-build.md)

This spec supersedes that plan. Rationale:

- That plan's V1 scope (npm + PyPI + crates.io registry adapters) is *acquisition breadth* — "find maintainers of high-download packages." Useful, but sits after a harder problem: the evaluator cannot distinguish maintainer-grade from contributor-grade *even on candidates it already has*. Evaluation depth is the blocker.
- Named-project evaluation (recruiter says "Kubernetes maintainer") is a better match for recruiter mental model than download-velocity ranking (recruiter rarely says "find me a maintainer of a package with > 10M monthly downloads").
- Registry adapters add ~5 API integrations, ClickPy / BigQuery cost, and cross-registry username collision handling. None of that is required for evaluation-depth to ship and deliver customer value.

Registry adapters move to §16 Follow-ups, gated on Phase 2 customer signal. If a customer in Phase 2 explicitly needs bulk discovery across package registries, the existing plan's slices 2-7 become the Phase 3 work.

## 7. Current state of [github/](github/) (Slice 1 deliverable)

### What exists

- **Pipeline.** `GitHubPipeline` at [github/orchestrator.py:68-69](github/orchestrator.py); outer loop iterates `GitHubSearchQuery` objects, inner loop is github login strings returned per channel. Entry at [github/session_orchestrator.py:180-216](github/session_orchestrator.py); run at [github/orchestrator.py:168-296](github/orchestrator.py).
- **Channels.** user_search, code_search, topic_search, stargazer_mining, graph_expansion ([github/strategy.py:303-352](github/strategy.py)).
- **Evaluation.** Facial (`github_facial_judge` / `_batch` at [shared/judger.py:776-816](shared/judger.py)) → Full (`github_full_judge` at [shared/judger.py:819-869](shared/judger.py)). Decision vocabulary at [github/judgment_templates.py:302-303](github/judgment_templates.py): `SAVE | REJECT | INFERENTIAL_SAVE | TRANSFERABLE_SAVE | SIGNAL_SAVE`.
- **Evidence surface.** `GitHubCandidate.to_evidence_text()` at [github/schemas.py:346-443](github/schemas.py). Includes: profile fields, up-to-10 repos with README excerpts, `portfolio_summary`, `frontier_contributions` (fork-name + contributors-list match at [github/enricher.py:396-427](github/enricher.py)), `repo_analysis`, website/arXiv, profile README, languages, builder/user strings, emails + website (not `linkedin_url`).
- **API surface.** [github/client.py:226-513](github/client.py): `/rate_limit`, `/search/{users,code,repositories}`, `/users/{username}` + repos + followers + following, `/repos/{owner}/{repo}` + `/languages` + `/contributors` + `/readme` + `/stargazers` + `/commits`, `/orgs/{org}/members`, profile README. ETag caching at [github/client.py:63,115-136](github/client.py). Rate limiter with Retry-After at [github/client.py:119-174](github/client.py).
- **Runtime bridge.** `GitHubRuntimeStateBridge` at [shared/runtime_state/github.py:14-124](shared/runtime_state/github.py); work-unit kinds `github_query` + `github_graph_seed` at [shared/runtime_state/store.py:37-38](shared/runtime_state/store.py).
- **Launcher + save.** Registered at [cloris/launchers/__init__.py:223-235](cloris/launchers/__init__.py) with `save_destination_blocker_fn=None` (comment at [cloris/launchers/__init__.py:217-222](cloris/launchers/__init__.py): "saves land in the run folder"). Saves written to `saves.jsonl` + optional CSV export ([github/side_effects.py:127-150](github/side_effects.py), [github/export.py](github/export.py)).
- **Identity resolution partial.** `_extract_signals` for github rows reads `contact.linkedin_url` at [shared/identity_resolution_service.py:147-160](shared/identity_resolution_service.py); `merge_profile_contact` sets `contact.linkedin_url` only when `blog` parses as LinkedIn at [shared/contact_discovery.py:109-111](shared/contact_discovery.py).
- **Read-model contract.** `extract_save_reason_and_confidence` at [shared/runtime_state/read_models.py:742-806](shared/runtime_state/read_models.py) is source-agnostic; github already populates `full_decision.rationale` + `confidence` via the shared write path ([shared/execution/runtime.py:340-357](shared/execution/runtime.py), [shared/runtime_state/store.py:1326-1341](shared/runtime_state/store.py)). No contract work needed.

### What does NOT exist

| Capability | Status | Evidence |
|---|---|---|
| PR review / merge endpoints on `GitHubClient` | absent | [github/client.py:226-513](github/client.py) |
| Release-tag endpoint | absent | same |
| `/users/{login}/orgs` endpoint | absent (only org public-members) | [github/client.py:478-493](github/client.py) |
| CONTRIBUTORS / MAINTAINERS / GOVERNANCE.md parse | absent | no file-fetch of those paths in [github/](github/) |
| `contribution_months` in evidence | absent (field exists; not rendered) | [github/schemas.py:134,346-443](github/schemas.py) |
| `linkedin_url` in evidence | absent | [github/schemas.py:436-441](github/schemas.py) |
| `target_projects` / `target_stacks` / `maintainership_level` brief fields | absent | grep returns zero |
| `source_config.github.*` recognized keys | empty set | [shared/brief_v2_schema.py:187](shared/brief_v2_schema.py) |
| Brief polish preservation of github-named projects | absent | [market_intelligence/brief_polish.py:463-513](market_intelligence/brief_polish.py) |
| Reflection for github runs | LinkedIn-gated | [market_intelligence/engine.py:1621-1626](market_intelligence/engine.py) |
| Maintainership classification | absent | no `maintainership*` files |
| Project-quality sub-index | absent | no `project_quality*` files |
| Save destination abstraction for github workspace | partial / pending mfm 6-7 | [cloris/launchers/__init__.py:217-222](cloris/launchers/__init__.py) |

## 8. Schema additions

### Brief top-level (V2)

Recommendation: **top-level V2 fields**, not nested under `source_config.github`. Rationale:

- `source_config.*` is for save-destination semantics ([shared/brief_v2_schema.py:168-178](shared/brief_v2_schema.py) comment is explicit). `target_projects` is an *evaluation + acquisition* input, not a save destination.
- `target_modules: list[str]` is already top-level at [shared/brief_v2_schema.py:97](shared/brief_v2_schema.py) (recognized; absorbed onto the Brief dataclass in Slice 2 per §5). Direct precedent. Brief polish preservation uses it as a drift anchor — `target_projects` gets the same treatment trivially.
- Per-capability-area nesting (on `CapabilityArea.target_projects`) was considered and rejected: most briefs name 1-3 projects for the whole role ("find a Kubernetes maintainer"), not per-capability. If a future brief needs per-capability project scoping, add it then.

Fields added to `RECOGNIZED_V2_KEYS` at [shared/brief_v2_schema.py:76-126](shared/brief_v2_schema.py):

```python
"target_projects",        # list[str]: GitHub repos e.g. ["kubernetes/kubernetes", "rust-lang/rust"]
"target_stacks",          # list[str]: language/framework/domain e.g. ["rust", "kubernetes", "container-orchestration"]
"maintainership_level",   # Literal["contributor", "maintainer", "project_lead"]
```

`validate_v2_brief` ([shared/brief_v2_schema.py:192-264](shared/brief_v2_schema.py)) gains type checks: lists of strings for the two lists; enum check on `maintainership_level`.

`Brief` dataclass at [shared/brief_schema.py:185-190](shared/brief_schema.py) gains the three fields (plus the absorbed `target_modules: list[str] = field(default_factory=lambda: ["linkedin"])` and `linkedin_project: str = ""` default per §5). Hydration in `_load_v2_brief` at [shared/brief_loader.py:166-453](shared/brief_loader.py) reads them with sensible defaults (`[]`, `[]`, `"contributor"`).

### Candidate payload

`GitHubCandidate` at [github/schemas.py](github/schemas.py) gains:

```python
maintainership: MaintainershipClassification | None = None
# where:
@dataclass
class MaintainershipClassification:
    level: Literal["contributor", "maintainer", "project_lead"]
    confidence: float  # 0.0-1.0
    evidence_sources: list[str]  # e.g. ["merge_authority:kubernetes/kubernetes", "release_tags:3/12mo", "CONTRIBUTORS_listed:kubernetes/kubernetes"]
    signals: dict[str, Any]  # raw per-signal scores for debugging
```

Rendered in `to_evidence_text()` ONLY when `brief.target_projects` is non-empty (behavior-preserving: classic github briefs render identically).

### `source_config.github`

**Stays empty** at [shared/brief_v2_schema.py:187](shared/brief_v2_schema.py). Target projects are evaluation inputs, not save-destination config. GitHub saves continue to land in the run folder + workspace (no per-brief github destination to configure). This explicitly honors the user guardrail: "anything the recruiter must enter at intake belongs in the wizard, not in JSON."

## 9. Maintainership-signal acquisition strategy (rate-limit honest)

### Per-candidate API budget

Tier 2 adds ~15-20 API calls per candidate on top of current ~8-12 for light+full enrich. Hard cap at 40 per candidate; abort maintainership classification at cap and record `evidence_sources` truncated.

At 5000 req/hr authenticated:

- ~125 candidates/hr fully classified at 40 calls each (conservative).
- Current ~15 calls/candidate: ~333 candidates/hr.
- So Tier 2 halves throughput. This is the tradeoff to make explicit to the user.

### Signal → source table

| Signal | GitHub API derivable? | Endpoint / approach | Cost |
|---|---|---|---|
| PR merge authority (who merged what) | yes | `/repos/{o}/{r}/pulls?state=closed&sort=updated` + `merged_by.login` | ~5 calls per target project (paginated) |
| Release tag authorship | yes | `/repos/{o}/{r}/releases` | 1 call per target project |
| Commit cadence over time | yes | existing `/repos/{o}/{r}/commits?author={u}` | 1-2 calls per target project |
| Reviewer on others' PRs | yes | `/repos/{o}/{r}/pulls/{n}/reviews` | sampled; 3-5 calls per target project |
| Name in CONTRIBUTORS / MAINTAINERS | yes (text mine) | `/repos/{o}/{r}/contents/CONTRIBUTORS.md` + variants | 1-3 calls per target project |
| Name in GOVERNANCE.md (BDFL / lead) | yes (text mine) | `/repos/{o}/{r}/contents/GOVERNANCE.md` | 1 call per target project |
| Named lead in README | yes (text mine) | existing `/repos/{o}/{r}/readme` | 0 calls (cached) |
| Downstream dependents count | no (API) / yes (HTML) | `/network/dependents` HTML scrape | 1 throttled HTTP per target project |
| Release cadence regularity | yes | derived from `/releases` | 0 extra calls |
| Contributor diversity | yes | `/contributors` (already called) | 0 extra |
| OpenSSF criticality | no (live) | weekly snapshot CSV from [github.com/ossf/criticality_score](https://github.com/ossf/criticality_score) | local cache lookup |

### Caching strategy

- Disk-backed cache at `output/cache/github/maintainer_signals/{owner}/{repo}/{signal}.json` with TTL = 7 days for release lists, governance files, CONTRIBUTORS; 24h for PR merge signals; 30 days for downstream-dependents page.
- Cache is shared across briefs/runs — two briefs targeting "kubernetes/kubernetes" only incur the API cost once per TTL window.
- ETag where GitHub supports it ([github/client.py:63,115-136](github/client.py) pattern). `/contents/*` and `/releases` return ETags; use them.

## 10. Seam

Extension points, ordered by the slice that touches them:

- [shared/brief_v2_schema.py](shared/brief_v2_schema.py) — three new top-level keys (Slice 2)
- [shared/brief_schema.py](shared/brief_schema.py) — three new fields on `Brief` + absorbed `target_modules` + absorbed `linkedin_project=""` default (Slice 2; see §5)
- [shared/brief_loader.py](shared/brief_loader.py) — hydration for the three fields + absorbed `target_modules` (Slice 2)
- [market_intelligence/brief_polish.py](market_intelligence/brief_polish.py) — preservation contracts + `_target_projects_drift` helper mirroring `_path3_drift` / `_role_title_drift` at [market_intelligence/brief_polish.py:605-640](market_intelligence/brief_polish.py) (Slice 2)
- [github/client.py](github/client.py) — new endpoints + maintainer-signal cache (Slice 3)
- `github/maintainership.py` (new file) — classifier (Slice 4)
- `github/project_quality.py` (new file) — sub-index (Slice 5)
- [github/schemas.py](github/schemas.py) — `GitHubCandidate.maintainership` field + `to_evidence_text()` extension; `MaintainershipClassification` + `ProjectQualityScore` dataclasses (Slice 6)
- [github/judgment_templates.py](github/judgment_templates.py) — `assemble_github_full_evaluation_system` at [github/judgment_templates.py:433-449](github/judgment_templates.py) gains maintainership block (Slice 6)
- [github/strategy.py](github/strategy.py) — `form_github_strategy` at [github/strategy.py:29-38](github/strategy.py) seeds queries from `target_projects` (Slice 7)
- [shared/contact_discovery.py](shared/contact_discovery.py) — `merge_profile_contact` at [shared/contact_discovery.py:104-113](shared/contact_discovery.py) scans bio + README for LinkedIn URL (Slice 8)
- [shared/identity_resolution_service.py](shared/identity_resolution_service.py) — extend `_extract_signals` github branch (Slice 8)
- [market_intelligence/engine.py](market_intelligence/engine.py) — un-gate or generalize `maybe_build_and_persist_research_packet` at [market_intelligence/engine.py:1621-1626](market_intelligence/engine.py); add github ecosystem narrative (Slice 9)

## 11. Proposed change

Two behavioral pillars:

1. **Named-project, level-classified evaluation.** The recruiter names target projects + desired maintainership level. The evaluator receives maintainership evidence keyed to those projects. Classic github briefs (no `target_projects`) run byte-identically.
2. **Polish + reflection reach github briefs.** `target_projects` preserved through brief polish with a drift contract. Reflection un-gated for github runs; ecosystem-momentum narrative surfaces per named project.

Both land without forking the module. The launcher entry at [cloris/launchers/__init__.py:230-234](cloris/launchers/__init__.py) is unchanged; the pipeline shape is unchanged; the runtime-state contract is unchanged. This is behavior-preserving extension.

## 12. Risks / failure modes

- **Rate-limit exhaustion at scale.** Tier 2 halves throughput. At a burst of 200 candidates/hr the token hits the ceiling. Mitigation: maintainer-signal cache (shared across briefs); per-candidate hard cap at 40 calls; governor emits STOP recommendation when <500 req/hr remaining.
- **Maintainership inference false-positives.** Someone who merged 3 PRs in a fork looks like "merge authority" without the repo-scope filter. Mitigation: (a) all merge-authority + release signals are *keyed to `target_projects`* — you cannot be a "maintainer" without the recruiter-named project attesting it; (b) Slice 4 ships with a 20-30-entry hand-classified ground-truth fixture and an explicit agreement-rate gate (exact-level match ≥0.80, within-one-level ≥0.95, non-adjacent confusion ≤0.02) that the classifier must clear before merging; (c) Slice 10 re-runs the gate on 3-5 held-out fixtures to guard against integration drift during Slices 5-9. See §13.1 for details.
- **Ground-truth fixture small-N overfitting.** A 20-30-entry calibration set can produce a classifier that clears the Slice-4 agreement gate by luck rather than by learning the right signals. Mitigation: held-out 3-5-entry check in Slice 10 (fixtures NOT seen during Slice-4 tuning); fixture expands to 50-100 entries in V2 once Phase 2 customer saves produce corroborating evidence; classifier logs per-signal contribution for every prediction so "right for the wrong reason" cases surface by inspection rather than hiding inside an aggregate agreement number.
- **Project-prestige blindness.** A niche but technically critical project (e.g. a kernel subsystem maintained by 3 people) scores low on star-based signals. Mitigation: project-quality sub-index weights *criticality* (OpenSSF) and *downstream dependents* over stars. `target_projects` + recruiter prior overrides the sub-index — named projects skip prestige scoring.
- **CONTRIBUTORS/MAINTAINERS text-mining name-matching errors.** A candidate named "John Smith" vs a CONTRIBUTORS entry for "jsmith" — name disambiguation is hard. Mitigation: require GitHub-username match (not display-name match) in the primary matcher; display-name as corroborating only; confidence capped at 0.7 for display-name-only matches.
- **Identity-resolution false-positives across github + linkedin.** Bio-scraped LinkedIn URLs can be stale or wrong. Mitigation: existing confidence bands in [shared/identity_resolution_service.py](shared/identity_resolution_service.py); bio-derived URLs carry lower confidence than blog-field URLs; recruiter workspace surfaces confidence.
- **Brief-polish drift.** LLM polish could drop `target_projects` silently. Mitigation: `_target_projects_drift` helper in [market_intelligence/brief_polish.py](market_intelligence/brief_polish.py) analogous to `_role_title_drift`; polish fails closed if named projects are dropped.
- **Downstream-dependents HTML scrape brittleness.** GitHub's page markup can change. Mitigation: parse defensively (regex on the count label, not DOM path); fail-soft (drop the signal for that candidate with a logged warning; don't crash).
- **Reflection coupling to LinkedIn assumptions.** `_explicit_linkedin_batch_is_incomplete` at [market_intelligence/reflection.py:415-419](market_intelligence/reflection.py) treats non-linkedin batches as complete; un-gating the research packet means writing a github variant or a shared variant that doesn't assume LinkedIn-shaped evidence. Mitigation: Slice 9 ships the github variant explicitly; shared abstraction is Phase 3.
- **mfm-foundation absorption conflict.** Researcher and Exec Search both audit the same precondition and may absorb the same `target_modules` / `linkedin_project=""` substrate in their Slice 2. Mitigation: defensive `setdefault` semantics on the Brief dataclass — if a parallel thread lands first, this slice's diff narrows to a no-op on those fields. Standard rebase discipline.

## 13. Test strategy

Narrowest test band per slice listed in slice plan. Cross-cutting:

- `tests/test_brief_schema_target_projects.py` (new) — round-trip hydration of the three new fields; default values; validation errors.
- `tests/test_brief_polish_target_projects.py` (new) — drift detection mirroring existing polish tests.
- `tests/test_github_maintainership_classifier.py` (new) — per-signal unit tests + agreement-rate test against the calibration fixture (see §13.1).
- `tests/test_github_project_quality.py` (new) — sub-index scoring on fixtures.
- `tests/test_github_pipeline.py` (extend) — Tier 2 end-to-end with mocked endpoints.
- `tests/test_github_identity_resolution.py` (new) — bio-scrape for LinkedIn URL.
- `tests/test_github_reflection.py` (new) — ecosystem-narrative shape for github batches.
- Full-suite gate: `make validate`.

### 13.1 Classification quality gate

Pipeline throughput ("≥10 saves with maintainership evidence") measures that saves happen, not that they're *correct*. The classifier is the single highest-leverage correctness surface in the module, so it gets a dedicated calibration-driven quality gate at two checkpoints: before Slice 4 ships (primary gate) and again in Slice 10 (regression guard after Slices 5-9 integrate).

**Calibration fixture — Slice 4, Part A.**

- Location: `tests/fixtures/github_maintainership_ground_truth.json`.
- Size: 20-30 entries.
- Entry shape: `{username, target_project, ground_truth_level, evidence_notes, classified_by, classified_at}`.
- Span (deliberate): infrastructure (kubernetes/kubernetes, etcd-io/etcd), systems (rust-lang/rust, torvalds/linux), devtools (pytorch/pytorch, astral-sh/uv), web (facebook/react, vercel/next.js). Mix of levels — roughly 8-12 contributors, 8-12 maintainers, 4-6 project_leads.
- Build cost: ~5-10 min per entry (read github profile, verify merged PRs, cross-check CONTRIBUTORS file) = 2-5 hr for a run of 20-30. Real work, not background.
- `classified_by` + `classified_at` fields make it reviewable; someone else can re-hand-classify a sample to check the labels are sane.

**Agreement gate — Slice 4 ship condition.**

- Exact-level match ≥ 0.80 (classifier and ground-truth agree on contributor / maintainer / project_lead).
- Within-one-level match ≥ 0.95 (off-by-one is acceptable; contributor ↔ maintainer or maintainer ↔ project_lead).
- Non-adjacent confusion ≤ 0.02 (project_lead predicted as contributor, or reverse, is almost never allowed — that's the classifier fundamentally misreading the signals).
- Slice 4 does not ship until all three thresholds are green. Thresholds are tunable but the gate is mandatory.

**Held-out regression check — Slice 10.**

- 3-5 fresh fixtures hand-classified *after* Slice 4 is frozen. Not used to tune the classifier.
- Same thresholds.
- Catches drift that gets introduced by the evidence-rendering layer (Slice 6), strategy changes (Slice 7), or identity resolution (Slice 8) — any of which could perturb the classifier's input distribution even if the classifier code itself is unchanged.

**Per-signal contribution logging.**

- Classifier emits `signals: dict[str, Any]` on `MaintainershipClassification` (per §8). Tests inspect it to confirm the classifier is right *for the right reasons* on fixture entries, not just right on the aggregate. A project_lead correctly predicted because of a random lucky merge pattern rather than the MAINTAINERS-file mention is caught here.

**Expansion cadence.**

- V1 fixture is 20-30 entries. V2 expands to 50-100 once Phase 2 customer saves provide corroborating evidence. Small-N overfitting is a real risk (see Risks §12); the expansion is the answer.

## 14. Open questions

- Should `maintainership_level` be Literal-enum or list-of-levels (acceptable set)? Literal is simpler; list allows "maintainer OR project_lead" saves. Default recommendation: Literal for V1; list-of-levels in V2 if recruiters ask.
- Downstream-dependents HTML scrape: acceptable for V1 or should we skip entirely and rely on OpenSSF criticality? Default recommendation: ship with scrape + conservative throttle; demote to OpenSSF-only if brittleness observed.
- Reflection: write a github-specific research packet or generalize the LinkedIn one? Default recommendation: write github-specific in Slice 9; generalize as a Phase 3 cleanup.
- Confidence-threshold for maintainership classification impacting SAVE vs INFERENTIAL_SAVE routing — does the classifier feed the judger's confidence, or sit alongside it? Default recommendation: sit alongside; judger reads it from evidence as additional input. No routing change in V1.

## 15. Slices

10 slices. Each independently committable. Slice 1 is audit-only; Slices 2-9 are code; Slice 10 is customer-launch readiness.

- [x] **Slice 1 — Audit + spec ratify.** This file. Section 7 audit inline. Verification of file:line claims against current code. mfm-foundation honesty surfaced in §5. Zero code.
- [ ] **Slice 2 — Brief schema + polish preservation.** Add `target_projects`, `target_stacks`, `maintainership_level` to `RECOGNIZED_V2_KEYS` ([shared/brief_v2_schema.py:76-126](shared/brief_v2_schema.py)), `validate_v2_brief` ([shared/brief_v2_schema.py:192-264](shared/brief_v2_schema.py)), `Brief` dataclass ([shared/brief_schema.py:185-190](shared/brief_schema.py)), and `_load_v2_brief` ([shared/brief_loader.py:166-453](shared/brief_loader.py)). **Absorbs mfm Slice 1 + 2 substrate** (see §5): `linkedin_project: str = ""` default and `target_modules: list[str] = field(default_factory=lambda: ["linkedin"])` field on `Brief` + loader hydration. Add `_target_projects_drift` helper in [market_intelligence/brief_polish.py](market_intelligence/brief_polish.py) mirroring `_path3_drift` ([market_intelligence/brief_polish.py:605-624](market_intelligence/brief_polish.py)); wire it into the cascade after `_role_title_drift`. **Named, not numbered:** the cascade route is `_target_projects_drift` so a parallel module thread can append `_research_topics_drift` / `_design_rubric_drift` / `_confidentiality_class_drift` at the next position without renumbering. Update the polish system prompt at [market_intelligence/brief_polish.py:719-777](market_intelligence/brief_polish.py) with a new HARD CONTRACT preservation line for `target_projects`. Tests narrowest band: `pytest tests/test_brief_schema.py tests/test_brief_loader.py tests/test_brief_polish*.py -q`.
- [ ] **Slice 3 — `GitHubClient` API extensions + maintainer-signal cache.** Add endpoints to [github/client.py](github/client.py): PR list/search filtered by author/merged, PR reviews, releases, repo contents for CONTRIBUTORS / MAINTAINERS / GOVERNANCE.md, `/users/{login}/orgs`. Disk-backed cache at `output/cache/github/maintainer_signals/`. Per-candidate 40-call cap. Tests: endpoint smoke + cache TTL.
- [ ] **Slice 4 — Maintainership classifier + calibration ground-truth fixture.**
  - **Part A:** build `tests/fixtures/github_maintainership_ground_truth.json` — 20-30 hand-classified entries spanning infrastructure / systems / devtools / web (per §13.1).
  - **Part B:** `github/maintainership.py` with `MaintainershipClassification` dataclass + `classify(username, target_projects, client)`. Signals: merge authority, release tag authorship, commit cadence, reviewer activity, CONTRIBUTORS / MAINTAINERS text-mine, GOVERNANCE.md text-mine, README lead mention. Confidence scoring.
  - **Agreement gate:** exact-level ≥ 0.80, within-one-level ≥ 0.95, non-adjacent confusion ≤ 0.02. Slice does NOT ship until gate is green.
  - Tests: per-signal unit tests + `tests/test_github_maintainership_classifier.py` runs classifier against fixture and asserts agreement thresholds.
- [ ] **Slice 5 — `github/project_quality.py` (new file).** `ProjectQualityScore` dataclass. GitHub-derivable signals only (no registry adapters): downstream-dependents HTML scrape (throttled), release cadence, contributor diversity, age × sustained activity, OpenSSF criticality snapshot lookup. Tests: fixture-based scoring.
- [ ] **Slice 6 — Evidence + evaluation integration.** Extend `GitHubCandidate` with `maintainership` field. Extend `to_evidence_text()` at [github/schemas.py:346-443](github/schemas.py) with a MAINTAINERSHIP EVIDENCE section gated on `brief.target_projects` non-empty. Extend `assemble_github_full_evaluation_system` at [github/judgment_templates.py:433-449](github/judgment_templates.py) with a maintainership block. Tests: prompt rendering parity for non-maintainer briefs (byte-identical); maintainership block renders when set.
- [ ] **Slice 7 — Target-projects acquisition strategy.** Extend `form_github_strategy` at [github/strategy.py:29-38](github/strategy.py) to seed queries from `target_projects` (contributor channel on named repos; stargazer_mining filtered by `target_stacks`). Extend adapt-after-batch logic. Tests: strategy emits target-project queries when set; strategy unchanged when unset.
- [ ] **Slice 8 — Cross-source identity resolution extension.** Extend `merge_profile_contact` at [shared/contact_discovery.py:104-113](shared/contact_discovery.py) to scan bio + profile README for LinkedIn URL patterns (not just blog). Ensure `to_evidence_text` emits `linkedin_url` when present ([github/schemas.py:436-441](github/schemas.py)). Extend [shared/identity_resolution_service.py:147-160](shared/identity_resolution_service.py) to accept bio-derived URLs with lower confidence band. Tests: bio-scrape fixtures; resolver cross-links github+linkedin rows.
- [ ] **Slice 9 — Reflection / market intelligence integration.** Un-gate [market_intelligence/engine.py:1621-1626](market_intelligence/engine.py) OR write a github-specific research packet variant. Add ecosystem-momentum narrative (maintainer-mass gain/loss per `target_project`) derived from finalized run evidence. Tests: github batch produces reflection artifacts; narrative structure valid.
- [ ] **Slice 10 — Customer-launch readiness + regression quality gate.**
  - **Part A:** held-out calibration check — 3-5 fresh hand-classified maintainers NOT in the Slice-4 fixture; agreement rate must still clear the Slice-4 thresholds. Guards against Slice 5-9 integration drift.
  - **Part B:** author a real github brief with `target_projects` + `maintainership_level` against a real company's hiring need. End-to-end run. Verify workspace surfaces maintainer candidates with cited evidence. Telemetry: classification confidence distribution per brief; save-rate by maintainership level; per-signal contribution analysis. Demo playbook + onboarding guide update.
  - Tests: held-out agreement rate clears gate + end-to-end pipeline produces ≥10 saves with maintainership evidence at the target level.

## 16. Follow-ups (not in this plan)

- Registry adapters (npm / PyPI / crates.io) per the superseded [plans/oss-maintainers-build.md](plans/oss-maintainers-build.md). Phase 3 if a customer explicitly demands bulk cross-registry discovery.
- Graph expansion from confirmed maintainer saves. V2.
- Private-repo signal acquisition via per-customer GitHub App install. Phase 3.
- Shared reflection abstraction (source-agnostic research packet). Phase 3 cleanup after Slice 9.
- `maintainership_level` as list-of-levels. V2 if recruiters ask.
- mfm Slice 3 (per-source nested calibration), mfm Slice 6 (workspace tables), mfm Slice 7 (`AbstractSaveDestination`). None of these are reached by OSS Maintainers. Leave to whoever picks up mfm.

## 17. Cross-thread coordination

OSS Maintainers ships in parallel with Researcher, Designer, and Exec Search module specs. The user's framing names the shared collision points; this section records OSS Maintainers' posture at each.

**Files this module touches that other threads also touch:**

- [shared/brief_v2_schema.py](shared/brief_v2_schema.py) `RECOGNIZED_V2_KEYS` — append-only addition of `target_projects`, `target_stacks`, `maintainership_level`. No reorder. Researcher and Exec Search will append their own keys here too; this is an additive merge.
- [shared/brief_v2_schema.py](shared/brief_v2_schema.py) `SOURCE_CONFIG_RECOGNIZED_KEYS_BY_SOURCE` — OSS Maintainers leaves `["github"]` empty per §8. Researcher will populate `["researcher"]`; Exec Search will populate `["exec_search"]`. No collision.
- [market_intelligence/brief_polish.py](market_intelligence/brief_polish.py) cascade — append `_target_projects_drift` helper + cascade route. **Named, not numbered**, per the user's instruction. Researcher will append `_research_topics_drift`; Designer `_design_rubric_drift`; Exec Search `_confidentiality_class_drift`. Whoever rebases later picks up the previous appender's hunk; no renumbering.
- [shared/brief_schema.py](shared/brief_schema.py) `Brief` dataclass — Slice 2 absorbs the mfm Slice 1-2 substrate (`linkedin_project: str = ""` default, `target_modules: list[str]` field). Researcher and Exec Search may try to absorb the same. Defensive posture: this Slice's diff is narrowed by `setdefault`-style additions if a parallel thread lands first.

**Files this module does NOT touch (despite being on the user's collision list):**

- [cloris/frontend/src/lib/types.ts:8](cloris/frontend/src/lib/types.ts) `Source` TS literal — extends `github` in place per §11; no new source. Researcher / Designer / Exec Search widen this; OSS Maintainers does not.
- [cloris/models.py:586-587](cloris/models.py) `CandidateCardSummary.source` Pydantic literal — same reason.
- [cloris/launchers/__init__.py](cloris/launchers/__init__.py) `LAUNCHERS` dict — extends the existing `github` launcher behaviorally; entry stays as-is.
- [shared/runtime_state/store.py](shared/runtime_state/store.py) work-unit kinds — extends `github_query` in place at [shared/runtime_state/store.py:37-38](shared/runtime_state/store.py); no new kind.
- [cloris/frontend/src/components/CandidateDetail.svelte](cloris/frontend/src/components/CandidateDetail.svelte) `surface_type` rendering branches — `CandidateDetail` does not currently branch on `source` (designer spec confirmed this); the maintainership block flows through the existing full-eval rationale wire contract ([shared/runtime_state/read_models.py:742-806](shared/runtime_state/read_models.py)).

**Standard rebase discipline applies on file conflicts.** This module's collision footprint is the smallest of the four (no new source registration; no Pydantic / TS literal widening; no launcher entry; no work-unit kind addition).
