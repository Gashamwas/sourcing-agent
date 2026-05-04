# Exec Search Workflow Spec

Status: ready-to-implement
Owner: Sam
Last updated: 2026-04-29

The Exec Search workflow is a premium mode of the LinkedIn module, not a separate source module. It wires the existing `market_intelligence/` infrastructure into the LinkedIn run-launch flow so that senior executive searches begin with investigation (market structure, named candidates, hiring signals) before candidate identification and evaluation.

This spec follows the shape in `docs/cloris-module-template.md` adapted for a workflow rather than a discovery module. For why this is a workflow not a module, see `Cloris-Module-Strategy.md` §2.7.

## 1. Target population

C-suite and SVP-level executives evaluable through LinkedIn whose career trajectory and organizational evidence (rather than direct technical artifact evidence) drive hiring decisions:

- CTOs, VPs of Engineering, Heads of AI, Chief Data Officers at companies in defined growth stages.
- Founder-CEOs of companies in target stages, when the buyer is a search firm placing CEO-as-a-replacement candidates.
- General Managers and SVPs at large companies where the role is "build a new function" rather than "execute a defined function."

The cohort is identical to the LinkedIn module's senior-role calibration target population (`shared/brief_schema.py:454`'s `is_senior_role()`). What changes is the *workflow* — investigation precedes identification.

Excluded: roles below VP that don't exhibit the L7+ evidence-hierarchy patterns; pure individual-contributor senior roles where the technical-artifact evidence model from the standard LinkedIn flow works better.

## 2. Buyer persona

Executive search firms doing C-suite and SVP-level placements. Specifically:

- AI-focused exec search practices (Daversa, Riviera Partners, ZRG AI practice, Heidrick AI practice, True Search AI practice).
- Generalist exec search firms with a tech vertical (Spencer Stuart, Russell Reynolds, Egon Zehnder, Boyden — when their tech practice uses Cloris).
- In-house talent partners at PE-backed companies doing exec hiring at the C-suite.
- Founder-led searches where the founder is recruiting their own first executive hire and wants the investigation done before the candidate conversations.

Pricing: per-placement value is the highest of any Cloris use case (exec placements command 25-35% of first-year compensation, often $200K-$500K per placement). Workflow-mode pricing supplements the standard LinkedIn module pricing — typically a per-search supplemental ($300-$1,000) or a higher-tier annual license including the workflow ($75K-$150K annual).

Why these buyers cannot solve the problem with existing tools: investigative pre-search work is currently manual (junior associate spends 10-20 hours doing market research, building target lists, identifying competitive moves) before the senior partner does the candidate work. Cloris's workflow mode automates the investigation phase, freeing the partner to spend their time on candidate conversations rather than research.

## 3. Differentiation thesis

The investigation-before-identification workflow already exists as code in `market_intelligence/engine.py`, `market_intelligence/research_agent.py`, and `market_intelligence/live_advisory.py`. The Perplexity-based public-web research tooling (`shared/external_evidence/`) provides the substrate. The senior-role evaluation pipeline already exists in `shared/brief_schema.py:454-544` (`is_senior_role`, `seniority_calibration_block`, `executive_builder_block`, three-tier evidence hierarchy, post-evaluation safety net).

The differentiation is not new infrastructure — it is the integration: surfacing investigation output to the recruiter before the run starts, giving them a chance to confirm or refine the run's direction based on the investigation findings. No exec search firm has a tool that does this; the closest analog is bespoke research databases that are read-only and don't integrate with sourcing.

## 4. Strategic priority and roadmap fit

Priority **#3** in `Cloris-Module-Strategy.md` §4. Build alongside Researcher in Phase 2.

Roadmap fit: ships in Phase 2 (June-August 2026). Prerequisites:

- Phase 1 foundation work complete.
- LinkedIn module's senior-role calibration is already in production (no new infrastructure needed there).
- `market_intelligence/` modules are already in the codebase but not currently wired into the run-launch flow — that is the integration work.

## 5. Data foundation

### 5.1 `market_intelligence/engine.py` (existing)

Pre-existing infrastructure. Reads brief context plus current run-state, generates structured market intelligence output via Perplexity-augmented research. Output shape includes:

- Market structure summary (key players, recent moves, hiring trends).
- Named candidate pool (specific people the brief should consider).
- Competitive intelligence (which firms are also recruiting in this space).
- Hiring signals (companies that announced restructures, departures, expansions).

This is the current canonical implementation of the "investigative research" capability. The workflow integrates it into the run launch rather than running it post-hoc.

### 5.2 `market_intelligence/research_agent.py` (existing)

Iterative research-agent pattern that drills into specific questions surfaced by the engine. Used during investigation to pursue follow-up questions on a specific named candidate or specific market segment.

### 5.3 `market_intelligence/live_advisory.py` (existing)

Real-time advisory pattern for in-run guidance. Less central to the exec search workflow — the workflow runs investigation pre-run, not during. `live_advisory.py` may be useful for adjusting candidate evaluation mid-run as new context emerges, but that is a v2 enhancement.

### 5.4 `shared/external_evidence/provider.py` (existing)

Perplexity-augmented external evidence for individual-candidate evaluation. Already used in the standard LinkedIn flow per `linkedin/orchestrator.py`. The workflow does not change this; it adds an upstream investigation phase.

### 5.5 LinkedIn (via existing module)

The candidate identification and evaluation phase remains the standard LinkedIn module flow. The workflow's pre-run investigation phase informs and refines the strategy formation but does not replace it.

### 5.6 Sources considered and rejected

- **Pitchbook / Crunchbase / Tracxn integration.** Useful for company-stage and funding context but commercially expensive ($10K+/year minimum). Defer to v2; Perplexity-based research surfaces enough company context for v1.
- **News API integration.** Useful for tracking executive moves (TechCrunch hire announcements, etc.). Perplexity covers this in the investigation prompt; direct news-API integration is v2.

## 6. Source-specific brief calibration

The workflow does not require new brief calibration fields beyond what the LinkedIn module already supports for senior roles. The brief's `target_modules` field declares LinkedIn; the `Brief.is_senior_role()` method (`shared/brief_schema.py:454`) gates the workflow mode.

A new brief field declares whether to run investigation pre-launch:

```python
@dataclass
class Brief:
    # ...existing fields...
    enable_pre_launch_investigation: bool = False  # True for exec search briefs
```

Default False so existing briefs are unchanged. Exec search briefs set it to True, triggering the investigation API endpoint at run-launch time.

Pre-built executive brief templates in `config/brief-templates/exec-search/` populate the V2 brief schema's senior-role calibration fields with worked exemplars:

- `head-of-ai.json`
- `cto-series-b.json`
- `vp-engineering-growth-stage.json`
- `chief-data-officer.json`
- `head-of-data-platform.json`

Each template demonstrates the L7+ three-tier evidence hierarchy in `seniority_calibration_block` (`shared/brief_schema.py:465-481`) with concrete examples calibrated to the role.

## 7. Evaluation pipeline mapping

The candidate evaluation pipeline is unchanged. The workflow adds Stage 0 (pre-launch investigation) before strategy formation:

- **Stage 0 (new).** Cloris UI calls `POST /api/exec-search/investigate` with the brief. Backend invokes `market_intelligence/engine.py` to produce the investigation packet. UI renders the packet for recruiter review.
- **Stage 0.5 (new, recruiter action).** Recruiter reviews the investigation. Optionally edits the brief based on findings (e.g., adds named candidates the investigation surfaced as `additional_search_terms`; adjusts geography or capability-area framing). Confirms readiness to launch.
- **Stage 1.** Standard strategy formation (`linkedin/strategy.py:form_strategy`), informed by the now-refined brief.
- **Stages 2-N.** Standard LinkedIn run flow.

The senior-role evaluation infrastructure (`shared/brief_schema.py:465-501`'s `seniority_calibration_block` + `executive_builder_block`) is already in production for the `is_senior_role()` path. The workflow does not change evaluation; it changes the upstream brief refinement.

## 8. State machine fit

The investigation phase is not a candidate-lifecycle stage; it is a brief-revision phase that runs before any candidate exists. No new lifecycle states.

A new event type is added to the canonical event vocabulary: `pre_launch_investigation_completed`. Recorded in `runtime_state.sqlite3:events` against the brief's pending run row. The investigation packet itself is persisted as an artifact (`output/state/linkedin/<brief_state_key>/exec_search_investigation.json`) and referenced from the event payload.

## 9. Identity disambiguation

Investigation surfaces named candidates by name + employer. Identity is disambiguated at the standard LinkedIn-flow identity-resolution phase, not at investigation time. The investigation just provides leads; the LinkedIn module verifies them.

## 10. Reconciliation strategy

No additional reconciliation logic — the workflow operates entirely within the LinkedIn module's existing reconciliation contract. Saved candidates land in `linkedin_recruiter` and `candidate_workspace` per the brief's `save_destinations`.

The investigation packet is a separate artifact (referenced from Run Review) rather than a saved-candidate record. It is not subject to cross-module identity resolution.

## 11. Save destination

Standard LinkedIn save destinations: `["linkedin_recruiter", "candidate_workspace"]`. The investigation packet is rendered as a Run Review section (not a saved candidate); it does not go through `AbstractSaveDestination`.

Outreach generation is the standard LinkedIn flow plus optional executive-tier outreach templates (more formal, references specific prior leadership achievements, suggests phone-not-email).

## 12. Build effort estimate

Total: **2-3 weeks** at split-attention pace.

Breakdown:

- API endpoint `POST /api/exec-search/investigate` in `cloris/api.py`: 2 days. Wires `market_intelligence/engine.py` into the run-launch flow. Returns the investigation packet for UI rendering.
- API endpoint `POST /api/launch/linkedin` extension to accept `pre_launch_investigation_id` parameter: 1 day. Worker spawn proceeds normally; investigation context is passed through to the orchestrator.
- Brief schema addition (`enable_pre_launch_investigation: bool`): 0.5 day.
- Brief loader hydration: 0.5 day.
- Cloris UI step for investigation review and confirmation: 4 days. New screen in the launch flow that renders the investigation packet (market structure, named candidates, hiring signals) in editorial-card format per `docs/cloris-ui-spec.md`. Recruiter actions: edit brief inline, add named candidates to `additional_search_terms`, confirm and launch.
- Pre-built executive brief templates (5 templates): 3 days. Each template demonstrates the senior-role calibration for a specific common exec search.
- Tests: 3 days. Test that investigation runs, packet is persisted, brief edits propagate to the launched run, the worker receives the refined brief.

Total: ~14 person-days = ~2-3 calendar weeks at split-attention.

## 13. First-customer demonstration scope

Demo brief: "Head of AI for a Series B/C B2B SaaS company in horizontal product analytics, US East Coast or remote-US, expected to build the AI function from scratch with a $5M-$10M annual budget."

What the workflow produces:

- Investigation packet rendered before launch:
  - Market structure: top 8 companies in horizontal product analytics with current AI leadership; recent AI hires across the segment in the last 12 months.
  - Named candidate pool: 15-25 specific people identifiable via Perplexity research as plausible Head-of-AI candidates with the right background.
  - Competitive intelligence: 3-4 search firms also recruiting in this space; recent placements they've made.
  - Hiring signals: 4-6 companies that announced AI-related restructures or VP departures in the last 6 months.
- Recruiter reviews the packet, adds 5-10 named candidates to the brief's `additional_search_terms`, refines the capability areas based on what the market structure reveals, and launches.
- Standard LinkedIn run executes against the refined brief.
- Saves are evaluated using the existing senior-role evaluation pipeline.

What's missing in the demo (acceptable for first customer): in-run advisory updates as new evidence emerges (`market_intelligence/live_advisory.py` integration is v2); investigation packet auto-refresh on brief revision (manual re-trigger v1).

## 14. Ship-quality scope

Beyond the demo:

- Investigation results cached and re-runnable. Recruiter can re-trigger investigation with updated context without re-launching the run.
- Investigation packet versioning. Each investigation run is persisted with timestamp and brief-version pinning so Run Review can show "this is the investigation that informed this run."
- Pre-built brief templates for additional common exec search categories (CRO, Chief Marketing Officer, COO).
- Live advisory integration (`market_intelligence/live_advisory.py`) for mid-run re-evaluation when new market signal emerges. V2.
- Telemetry: investigation runtime, packet recruiter-edit rate, save-rate-difference between briefs that did vs. didn't use pre-launch investigation.

## 15. Failure modes and edge cases

- **Investigation API outage.** Perplexity rate limit or downtime causes investigation to fail. Recruiter sees a clear "investigation failed; you can launch without it or retry" prompt. Launch without investigation falls back to standard LinkedIn flow.
- **Investigation packet quality varies by market segment.** Niche markets may produce thin packets; the recruiter sees the thinness and decides whether to launch anyway.
- **Investigation surfaces protected information.** Edge case where Perplexity returns confidential information (e.g., a Glassdoor leak about a specific executive's compensation). The investigation prompt explicitly excludes seeking confidential info; if it returns anyway, the packet rendering filters known sensitive patterns.
- **Brief edits propagate to investigation but not to evaluation calibration.** Recruiter adds named candidates to `additional_search_terms` mid-investigation; this propagates correctly. They edit `non_fit_patterns` mid-investigation; this also propagates. They edit `depth_distinction` mid-investigation; the evaluation pipeline picks it up at run-launch.
- **Multiple concurrent investigations on the same brief.** Locking via `RuntimeStateLock` plus a per-brief investigation-in-progress flag. Only one investigation per brief at a time.

## 16. Open questions

- **Investigation as a separate billable surface.** Should exec search workflow customers see a per-investigation cost line item, or is it included in the workflow license? V1: included. V2: revisit if Perplexity costs become material.
- **Live advisory integration depth.** `market_intelligence/live_advisory.py` could fire mid-run when the current pass produces unexpected signal (e.g., a saved candidate's profile reveals a competitor's surprise hire). V1 doesn't include this. V2 if customer signal indicates value.
- **Investigation feedback loop.** Should investigation packet quality be tracked over time (recruiter approval rate, packet-edit rate, find-rate of named candidates surfaced in the packet)? V1: minimal telemetry. V2: full feedback loop.

## 17. Decisions captured here

- 2026-04-29 — Exec Search is a workflow mode of the LinkedIn module, not a separate source module.
- 2026-04-29 — `market_intelligence/engine.py` is the canonical investigation infrastructure. The workflow integrates it; it does not replace it.
- 2026-04-29 — Investigation runs as Stage 0 pre-launch, not in-run. Live advisory integration is v2.
- 2026-04-29 — Pre-built executive brief templates ship with the workflow. Five templates in v1; more added based on customer pull.
- 2026-04-29 — Investigation packet is an artifact, not a candidate. Not subject to cross-module identity resolution.
- 2026-04-29 — V1 build target is 2-3 calendar weeks at split-attention pace.
