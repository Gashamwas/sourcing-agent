# LinkedIn Recruiter Session Latch (Path 1)

Status: draft
Owner: Sam
Last updated: 2026-05-03

## Problem

Path 3 (the trial slice) closes the configuration disconnection by giving the recruiter an in-product editor to paste their Recruiter project URL once. That's the right move for the trial. The longer-arc move is to eliminate the configuration moment entirely: latch onto the user's open Recruiter session at runtime, detect the project_id from the URL, persist it back to the brief.

The plumbing is closer than expected. `linkedin/browser.py:198-201` already extracts `project_id` from the active tab via `re.search(r"/talent/hire/(\d+)", url)` and `linkedin/orchestrator.py:3222-3229` already falls back to that value for navigation. What's missing is the persistence semantic, the launch-readiness condition that doesn't fire when the recruiter has the right tab open, and the UI surfaces required to keep persistence safe (divergence prompt, collision-aware persist).

## Goal

The trial recruiter never types or pastes a Recruiter project URL. The first launch from a fresh brief writes `source_config.linkedin.{project_id, project_name}` automatically from the active Recruiter tab; subsequent runs read normally. Cloris asks before silently re-pointing, and refuses to silently create collisions.

## Non-goals

- Auto-creating the Recruiter project (Path 2 — explicitly rejected in the parent investigation).
- Auto-configuring the location filter beyond what `linkedin/browser.py:741-762` already does. The existing `_set_location_filter` retains its "set manually before running" fallback.
- Replacing the Path 3 editor. `<LinkedInProjectEditor>` is reused as the divergence/collision prompt; this plan does not touch the trial slice.
- Solving the pre-existing PUT state-key migration bug (xfail at `tests/test_brief_detail_edit.py:test_put_brief_state_key_migration_returns_404_pre_existing_bug`) — surfaced separately.

## Assumptions

- Recruiter is logged into LinkedIn Recruiter in `~/.chrome-cdp` (the helper-script profile at `launch-chrome.sh:7`). If they log out mid-session, `linkedin/browser.py:447-451` already raises `"LinkedIn session expired"` — that path stays.
- The recruiter has at most one Recruiter project open per Cloris brief at launch time. Multi-tab is handled by the existing tab-scoring at `linkedin/browser.py:179-186`; the highest-scoring tab is the project the recruiter is "sitting on."
- `runtime_state.sqlite3` is canonical. The state-dir keyed by `linkedin_state_key` must remain addressable across the latch's persistence write — collisions and migrations cannot orphan it.
- `<LinkedInProjectEditor>` (Path 3 trial slice) ships first. Path 1 reuses it as a wrapped prompt; the bare component already handles paste/parse/save.
- The trial's Path 3 slice is in production. Path 1 is purely additive — turning off Path 1 must leave Path 3 working unchanged.

## Seam

Three seams, each in a high-risk-rule file. Order matters; each slice is behavior-preserving with respect to the trial slice.

1. `linkedin/health.py:75-128` — extend `_probe_linkedin_context_async` to detect not just `linkedin.com` URLs but specifically Recruiter project URLs (`linkedin.com/talent/hire/<digits>`). New return tuple: `(has_context, has_linkedin_url, has_recruiter_project_url, detected_project_id)`. The probe at `linkedin/health.py:131-214` already runs at API time without a worker context — adding the regex match is small and contained.

2. `cloris/launchers/__init__.py:127-166` — replace the unconditional `_linkedin_save_destination_blocker` with a conditional one. Today it fires whenever the brief lacks a project_id. Path 1 changes the firing condition to: brief lacks a project_id AND the Recruiter readiness probe didn't detect a project URL. Both Path 3's editor and Path 1's auto-detect can clear the blocker; the trial's PUT path stays unchanged.

3. `linkedin/orchestrator.py:207` (state-key seam — high-risk file) and `linkedin/orchestrator.py:866-880` (run-start seam) — at the moment the worker first binds to a Recruiter tab and detects a project_id, write `source_config.linkedin.{project_id, project_name}` back to the brief via `shared/brief_writer.write_brief_atomic`. The state-key derivation at line 207 happens BEFORE `browser.connect()` so the persistence has to land in `start_run`, not in `__init__`. State-key recomputes on the next run (or in-memory after the persist) — the migration question is whether the in-flight run uses the old or new state-key.

## Proposed change

Three behaviors that each introduce a new UI surface or a new schema-write path. None are independent.

### 1. Readiness probe extension

Today's probe ([`linkedin/health.py:75-128`](linkedin/health.py)):

```python
async def _probe_linkedin_context_async(cdp_url: str, timeout: float = 5.0) -> tuple[bool, bool]:
    ...
    if "linkedin.com" in url: has_linkedin = True
```

Becomes:

```python
async def _probe_linkedin_context_async(cdp_url: str, timeout: float = 5.0) -> tuple[bool, bool, str | None]:
    ...
    project_match = re.search(r"/talent/hire/(\d+)", url)
    if project_match: detected_project_id = project_match.group(1)
```

Returns `(has_context, has_recruiter_project_url, detected_project_id)`. The synchronous wrapper `probe_linkedin_readiness()` exposes the detected id on the `ReadinessReport`. Backward-compat: callers that don't read `detected_project_id` see no change in their existing fields.

### 2. Conditional readiness blocker

`cloris/launchers/__init__.py:127-166` becomes:

```python
def _linkedin_save_destination_blocker(brief_path: str) -> SaveDestinationBlocker | None:
    project_id = linkedin_project_id_from_brief(raw)
    if project_id: return None
    # Path 1 addition: skip the blocker if the recruiter has a project tab
    # open. The worker will persist the detected id at run-start.
    from linkedin.health import probe_linkedin_readiness
    report = probe_linkedin_readiness()
    if report.detected_project_id: return None
    return SaveDestinationBlocker(...)
```

Tradeoff: the blocker now runs the readiness probe on every launch-readiness call. The probe attaches via CDP, so it's not free (sub-second on a healthy connection, a few seconds on retry). Mitigations: cache the detected id in the API response for the brief in question; surface a soft warning ("Cloris will use the project at the URL you currently have open") so the recruiter can confirm before launch.

### 3. Run-start persistence with divergence + collision prompts

The persistence path is the riskiest — it touches `linkedin/orchestrator.py`, a high-risk file. Three flows:

**3a. First detection (no stored id, detected id at launch).** At `linkedin/orchestrator.py:866-880`, after `await self.browser.connect()` binds to a Recruiter tab and `self.browser._project_id` is set, BEFORE `_get_project_url` runs, persist the detected id to the brief via a new helper `linkedin/orchestrator.py:_persist_browser_detected_project()` that wraps `shared/brief_writer.write_brief_atomic`. Then re-derive `_brief_id` from the new state-key; bail with a clear error if the migration would orphan an existing state-dir (covered by collision-aware persist below).

**3b. Divergence (stored id ≠ detected id).** Same hook, but with both values present. Three behaviors evaluated in the parent investigation:
- **Overwrite** — silent corruption when the recruiter switched tabs accidentally. Reject.
- **Ignore** — safe but loses Path 1's value entirely. Reject as primary; viable as fallback if the prompt is dismissed.
- **Prompt** — ask the recruiter, gate the run on resolution. Only defensible choice.

The prompt is a new UI surface in `cloris/frontend/src/components/LaunchForm.svelte` (or a sibling launch-confirm view). It reuses Path 3's `<LinkedInProjectEditor>` in a "you're on a different project — confirm or update" wrapper. The prompt fires before `launchForSource` is called when the readiness response indicates divergence; user clicks "use stored" or "update brief," and the launch proceeds with the chosen value. Status: needs UI design pass. Out of scope for the trial.

**3c. Collision-aware persist.** Before writing source_config, walk the brief catalog (`cloris/api.py:_scan_authored_briefs` is the existing entry) for any other brief with the same `linkedin_project_id`. If found:
- Refuse to write. The recruiter is pointing two briefs at the same Recruiter project — that's a recruiter-brief reconciliation collision and `shared/recruiter_brief_resolution.py:111-173` will raise `RuntimeError` once the runs land.
- Surface a refusal prompt: "This Recruiter project is already configured for the brief 'X' — point this brief at a different project, or open 'X' instead."
- Reuses `<LinkedInProjectEditor>` again as the resolution surface (recruiter pastes a different URL inline, or aborts).

## Risks

- **High-risk file: `linkedin/orchestrator.py`.** Anything that touches `_brief_id` (line 207) is load-bearing for state-dir addressability. The persist hook must run before `_brief_id` materializes into runtime calls (state-dir creation at `__init__`, runtime DB connect at `start_run`).
- **High-risk file: `linkedin/health.py`.** Readiness probe is called from a sync route; extending the async helper changes the return signature and the sync wrapper. Need to confirm `asyncio.run()` from inside FastAPI sync handlers continues to work.
- **Pre-existing PUT bug.** The state-key migration bug surfaced by Path 3's xfail (`tests/test_brief_detail_edit.py:test_put_brief_state_key_migration_returns_404_pre_existing_bug`) directly affects Path 1's persistence: when the worker writes source_config and the resolver-fallback id changes, downstream PUT-then-GET cycles 404 on the old id. Path 1 must either fix the PUT bug first, or persist via a path that doesn't roundtrip through the API layer (`shared/brief_writer.write_brief_atomic` directly, bypassing the PUT endpoint entirely).
- **Runtime-state addressability.** Persisting source_config at the same time as the run starts can change `linkedin_state_key`. If the run already has a state-dir under the OLD key, runtime_state.sqlite3 lives there. If we recompute the state-key after persist, the in-flight run is suddenly looking at the wrong state-dir. Two safe shapes: (a) persist BEFORE the orchestrator's `__init__` reads the state-key (precludes the F2 readiness path); (b) keep the old state-key for the in-flight run, recompute on the NEXT run (acceptable but adds complexity). Resolution required before implementation.
- **Multi-tab UX.** Tab scoring at `linkedin/browser.py:179-186` prefers `/discover/recruiterSearch` URLs. If the recruiter has both their target project and a different project open, the worker latches onto the highest-scoring tab. Without the divergence prompt this becomes silent corruption.
- **CDP performance.** Calling `probe_linkedin_readiness()` from the F2 blocker on every readiness probe adds 1-3s per call. May need debouncing or a probe-cache layer.
- **Surface area for regressions.** The collision walk is a `_scan_authored_briefs(...)` in the launch hot path. Need a benchmark to confirm it doesn't add visible latency on briefs catalogs of ~50+ briefs.

## Slices

Each slice is behavior-preserving with respect to the trial slice (Path 3) and adds one capability. None of these slices ship until the open questions below are resolved.

- [ ] Slice 1 (read-only probe extension): extend `linkedin.health.probe_linkedin_readiness` to return `detected_project_id`. No callers consume it yet. Prove the regex + sync wrapper surface works without breaking `linkedin/health.py:131-214`'s existing contract. Test slice: extend `tests/test_linkedin_browser_connect.py` (or add `tests/test_linkedin_health_probe.py`).
- [ ] Slice 2 (conditional blocker): rewire `cloris/launchers/__init__.py:127-166` to skip the blocker when `detected_project_id` is set. Add a new `kind="warn"` blocker that surfaces a soft confirmation ("Cloris will use the project at <URL> you currently have open"). Trial recruiters with a brief lacking project_id no longer hit a hard blocker if they're on the right tab. Test slice: extend `tests/test_save_destination_config.py` and `tests/test_launch_readiness_endpoint.py`.
- [ ] Slice 3 (persistence with collision check, no divergence prompt): persist the detected project_id at run-start with a catalog walk for collisions; refuse on collision with an editorial error. NO divergence prompt yet — first-detection only, mismatched stored id falls back to "use stored, log warning." Test slice: extend `tests/test_linkedin_runtime_state.py` and `tests/test_linkedin_pipeline.py` for the persist-at-start behavior; new test for the catalog-collision refusal.
- [ ] Slice 4 (divergence prompt UI): the launch-time confirmation that fires when the stored id differs from the detected id. Reuses `<LinkedInProjectEditor>` from Path 3. New Svelte component wrapping it: `<LinkedInProjectDivergencePrompt>`. New API surface to deliver the prompt state from the readiness check. Test slice: new `tests/test_launch_divergence_prompt_endpoint.py` + Svelte unit tests.

## Test strategy

- Narrowest band per slice, named above.
- Cross-cutting: `pytest tests/test_linkedin_runtime_state.py tests/test_save_destination_config.py tests/test_launch_readiness_endpoint.py tests/test_linkedin_pipeline.py -q`.
- Full-suite gate before declaring done: `make validate`.
- The xfail surfaced by Path 3 (`test_put_brief_state_key_migration_returns_404_pre_existing_bug`) MUST be either fixed or routed-around before Slice 3 ships — Path 1's persistence will hit that path constantly.
- Manual: walk the trial recruiter's flow end-to-end via the audit pipeline. Confirm "open project, click launch, no editor surface, run starts" works on a fresh brief.

## Open questions

- **Q1: When does the persist write happen?** Before `__init__` reads the state-key (forces a refactor of orchestrator construction), or after `__init__` with the run staying on the OLD state-key for its duration (simpler but means state-dir migration happens on the NEXT run). Sam's call.
- **Q2: Probe caching.** Is a sub-second cache on `probe_linkedin_readiness()` acceptable for the F2 blocker, or do we need to make the probe truly free (e.g., reuse the in-flight worker's CDP connection)? Performance-driven; punt to slice 2 measurements.
- **Q3: Collision-refusal copy.** "This Recruiter project is already configured for 'X' — open 'X' instead, or point this brief at a different project." Cloris-voice pass needed; defer to UI design.
- **Q4: Should the divergence prompt fire on EVERY launch where the stored id ≠ detected id, or only the first time?** First-time-only is gentler but surfaces a "did you mean to switch?" affordance only once and then never again. Every-time is friction but unambiguous. Probably first-time-only with a "remind me" toggle. Out of scope for slice 3.
- **Q5: How does Path 1 interact with the pre-existing PUT bug?** Path 1's persist must NOT roundtrip through PUT. Direct `write_brief_atomic` is the right tool; need to confirm there's no intervening surface that depends on the API contract.

## Decisions

- 2026-05-03 — Path 1 is queued behind Path 3, not in trial scope — divergence + collision design alone deserve more deliberation than trial timing affords.
- 2026-05-03 — Auto-create project (Path 2) is explicitly rejected — maintenance against a moving UI is structurally bad and the ToS escalation isn't justified.
- 2026-05-03 — `<LinkedInProjectEditor>` (Path 3) is reused as the divergence prompt's input surface — the abstraction is earned by three Path 3 callsites and a fourth Path 1 callsite.
- 2026-05-03 — Prompt is the only defensible behavior for launch N+1 divergence — overwrite silently corrupts state, ignore silently undermines Path 1's value.
- 2026-05-03 — Collision-aware persist is a hard prerequisite, not a follow-up — silent collisions trigger `RuntimeError` deep in `shared/recruiter_brief_resolution.py:111-173` with no recoverable signal at the surface.

## Follow-ups (not in this plan)

- Pre-existing PUT bug: when source_config addition migrates the state-key, `cloris/api.py:579-675`'s final `api_brief_detail(brief_id)` 404s on the old id. Surfaced as xfail at `tests/test_brief_detail_edit.py:test_put_brief_state_key_migration_returns_404_pre_existing_bug`. Fix before Path 1 Slice 3.
- Auto-configure location filter: `linkedin/browser.py:741-762` already has the bones (typeahead match, fallback to manual). Path 1's persist hook is the natural place to also persist the recruiter's effective location filter into `source_config.linkedin.search_location_label` or similar — reduces re-application across runs. Out of scope here.
- Soft-warning blocker copy: when Path 1 detects a project tab but the brief is unconfigured, the surface should be a soft confirmation, not silence. Cloris-voice pass required.
- A "switch to a different Recruiter project on this brief" affordance — separate from divergence (which fires when Cloris detects the mismatch), this is recruiter-initiated. Probably the same `<LinkedInProjectEditor>` Change button on BriefDetail with a confirmation step. Phase F follow-up.
