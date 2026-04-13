# Implementation Sequence: Reviewed-Candidate Memory + HITL Outreach Feedback

This document converts the higher-level roadmap in [REVIEWED_CANDIDATE_MEMORY_AND_HITL_OUTREACH_ROADMAP.md](/Users/sam.vangelos/Projects/recruiting-tools/sourcing-agent/REVIEWED_CANDIDATE_MEMORY_AND_HITL_OUTREACH_ROADMAP.md) into a tactical execution plan with milestones, dependencies, rollout gates, and acceptance criteria.

## Goal
Ship two new LinkedIn feedback loops without destabilizing current sourcing:

1. **Reviewed-candidate memory**
   Exact-profile memory for candidates who already received full Opus review.

2. **HITL outreach feedback**
   Recruiter action labels that tell us whether a saved candidate was actually worth outreach.

## Delivery Principles
- Keep **same-project dedupe** exactly as-is.
- Treat **same-market reviewed memory** as advisory before it becomes behavioral.
- Keep **outreach feedback** separate from sourcing-stage terminal decisions.
- Prefer **exact `profile_url` identity** over fuzzy matching.
- Make each phase independently shippable and easy to roll back.

## Milestone Overview

| Milestone | Outcome | Behavior Change | Risk |
|---|---|---|---|
| M0 | Contracts and storage spine exist | None | Low |
| M1 | Reviewed-memory capture + backfill | None | Low |
| M2 | Shadow lookup during LinkedIn runs | Logging/reporting only | Low |
| M3 | Advisory lookup in operator-facing artifacts | Context only | Low-Medium |
| M4 | Outreach feedback import + projection | Market-intel signal added | Medium |
| M5 | Market-intel consumption of both loops | Recommendation quality changes | Medium |
| M6 | Exact same-market auto-skip for fresh matches | Real run behavior changes | Medium-High |
| M7 | Optional search-intelligence weighting | Adaptation policy changes | High |

## Milestone Details

### M0: Contracts and Storage Spine
**Objective**
- Establish the canonical data shapes and persistence surfaces before any behavior changes.

**Work**
- Define `ReviewedCandidateMemoryRecord`.
- Define `LinkedInOutreachFeedbackRecord`.
- Add runtime-state storage for `reviewed_candidate_memory`.
- Reserve the LinkedIn feedback side-effect type, e.g. `linkedin_outreach_feedback`.
- Add materialized artifact contracts for:
  - market-level `reviewed-candidate-memory.jsonl`
  - project-level `outreach.jsonl` projection

**Acceptance**
- Schema and storage are stable.
- Migration is idempotent.
- No LinkedIn run behavior changes yet.

**Dependencies**
- None.

**Rollback**
- Safe to keep storage in place even if later milestones are paused.

### M1: Reviewed-Memory Capture and Historical Backfill
**Objective**
- Start collecting exact-profile reviewed memory from current and past full reviews.

**Work**
- Upsert reviewed-memory records from the existing full-review success path.
- Include both save and reject full-review outcomes.
- Build a backfill job from existing runtime-state/full-judgment history.
- Derive `market_key` from each originating brief during backfill.

**Acceptance**
- New full reviews populate reviewed-memory records automatically.
- Historical runs can be backfilled without duplicates.
- Latest exact-profile snapshot wins within a market.

**Dependencies**
- M0 complete.

**Rollback**
- Leave stored data in place; simply stop writing new reviewed-memory records.

### M2: Shadow Lookup During LinkedIn Runs
**Objective**
- Verify the exact-match lookup path in production-like runs without changing candidate handling.

**Work**
- Batch-lookup exact `profile_url` matches for facial survivors before full Opus review.
- Distinguish:
  - same-project exact match
  - same-market exact match
- Log and report matches, but do not alter review flow yet.

**Acceptance**
- Exact matches appear in logs/debug artifacts.
- Precision is effectively perfect.
- No candidates are skipped because of shadow lookup.

**Dependencies**
- M1 complete.

**Rollback**
- Disable the lookup read path; all stored data remains intact.

### M3: Advisory Lookup in Operator-Facing Artifacts
**Objective**
- Surface prior-review continuity to the operator without yet making hard automation decisions.

**Work**
- Show same-market prior-review context in:
  - run reports
  - debug artifacts
  - market-intel provenance summaries
- Include prior decision, confidence, timestamp, and rationale excerpt.
- Keep same-project dedupe authoritative and unchanged.

**Acceptance**
- Operators can see prior-review provenance cleanly.
- Advisory context is useful and not noisy.
- No harmful over-suppression occurs because behavior is still non-blocking.

**Dependencies**
- M2 validated.

**Rollback**
- Remove artifact/report rendering while leaving capture and lookup intact.

### M4: Outreach Feedback Import and Projection
**Objective**
- Create the first human-truth loop for saved candidates.

**Work**
- Build a lightweight CSV/JSONL importer keyed by `profile_url`.
- Normalize statuses to:
  - `reached_out`
  - `not_reached_out_low_quality`
  - `not_reached_out_capacity_or_timing`
- Store recruiter feedback as side effects, not terminal sourcing decisions.
- Project current per-project feedback into `outreach.jsonl`.

**Acceptance**
- Imports are idempotent and replaceable.
- Invalid statuses are rejected cleanly.
- Projected artifacts are readable and stable.

**Dependencies**
- M0 complete.
- Can ship independently of M2/M3 if needed.

**Rollback**
- Disable importer entrypoints and leave prior feedback records untouched.

### M5: Market-Intel Consumption
**Objective**
- Turn both new loops into usable market-level intelligence.

**Work**
- Add reviewed-memory metrics:
  - prior-review hit rate
  - avoided re-reviews
  - same-project vs same-market reuse
- Add outreach metrics:
  - outreach rate by lane/family/employer cluster
  - low-quality non-outreach rate
  - explicitly exclude capacity/timing from negative quality scoring
- Update market-intel recommendations to cite these signals.

**Acceptance**
- Market-intel artifacts become more actionably specific.
- Recommendations remain provenance-backed.
- Capacity/timing does not accidentally depress lane quality.

**Dependencies**
- M3 and M4 complete.

**Rollback**
- Revert market-intel consumption while preserving raw memory/feedback capture.

### M6: Exact Same-Market Auto-Skip for Fresh Matches
**Objective**
- Convert advisory exact-match memory into bounded automation where confidence is highest.

**Work**
- Add a runtime toggle for same-market auto-skip.
- Only skip when:
  - exact `profile_url` match
  - same market
  - prior full review is fresh, default `<= 90 days`
- Older records remain advisory.

**Acceptance**
- Manual review of several shadow/advisory runs shows no harmful suppressions.
- Operators trust the provenance shown with each auto-skip.
- Auto-skip is easy to disable globally.

**Dependencies**
- M3 complete and validated over multiple runs.

**Rollback**
- Turn off the runtime toggle and return to advisory-only behavior.

### M7: Optional Search-Intelligence Weighting
**Objective**
- Let outreach-quality feedback influence future prioritization and adaptation only after enough data exists.

**Work**
- Add optional outreach-weighted lane/family scoring for analytics first.
- Only later allow search-intelligence policy to consume those scores for:
  - block prioritization
  - proven-lane exploitation
  - search-intel summaries

**Acceptance**
- Sufficient feedback volume exists to avoid noisy overfitting.
- Capacity/timing is excluded from negative weighting.
- Policy changes are clearly measured against baseline behavior.

**Dependencies**
- M5 complete with a meaningful amount of outreach feedback.

**Rollback**
- Revert to reporting-only weighting and keep raw feedback available.

## Suggested Build Order
If we want the safest path with the highest early value, build in this order:

1. `M0` Contracts and storage spine
2. `M1` Reviewed-memory capture + backfill
3. `M2` Shadow lookup
4. `M3` Advisory operator context
5. `M4` Outreach feedback import
6. `M5` Market-intel consumption
7. `M6` Auto-skip
8. `M7` Search-intelligence weighting

This order gives us continuity and provenance first, then recruiter truth, then behavioral automation.

## Phase Gates

### Gate A: Safe to Leave Shadow Mode
- Exact `profile_url` matching is stable.
- Same-project vs same-market scope is always correct.
- No confusing false matches appear in artifacts.

### Gate B: Safe to Add Market-Intel Consumption
- Feedback imports are clean and repeatable.
- The `outreach.jsonl` projection is trustworthy.
- Capacity/timing labels are not leaking into negative quality scoring.

### Gate C: Safe to Enable Auto-Skip
- Advisory mode has been reviewed across several real runs.
- Prior-review age logic is working.
- Operators are comfortable with the provenance shown for each skip.
- Toggle-based rollback is confirmed.

### Gate D: Safe to Weight Search Intelligence
- Enough recruiter feedback exists to avoid premature overfitting.
- Lane-level outreach signal is materially more informative than raw save rate alone.
- Baseline comparison is available.

## Recommended Testing by Milestone

### M0-M1
- migration tests
- runtime-state round-trip tests
- backfill idempotency tests
- exact latest-record-wins tests

### M2-M3
- lookup classification tests
- no-behavior-change shadow tests
- advisory artifact rendering tests
- freshness-window tests

### M4
- importer validation tests
- replacement/invalidation tests
- projection tests
- malformed-row rejection tests

### M5
- metric aggregation tests
- market-intel schema/output tests
- provenance rendering tests
- exclusion of capacity/timing from negative scoring

### M6
- exact-match auto-skip tests
- stale-record advisory fallback tests
- runtime-toggle rollback tests
- regression tests for same-project dedupe

### M7
- weighted-scoring analytics tests
- policy-guard tests
- regression tests around exploitation/search-intelligence behavior

## Recommended Ownership Split
- **Runtime-state / storage**
  - reviewed-memory table
  - side-effect storage/projection
  - backfill/import commands

- **LinkedIn run loop**
  - exact-match lookup
  - shadow/advisory/auto-skip read path
  - operator-facing provenance rendering

- **Market intelligence**
  - reuse metrics
  - outreach-quality metrics
  - recommendation language updates

- **Search intelligence**
  - hold until M7 unless a reporting-only hook is needed earlier

## Defaults and Decisions
- Identity is exact `profile_url` only in v1.
- Same-project remains authoritative; same-market starts advisory.
- Recruiter feedback statuses are fixed to the three labels in the roadmap.
- `not_reached_out_duplicate_or_already_known` is intentionally not part of recruiter feedback.
- Semantic/RAG retrieval is explicitly deferred until deterministic memory proves valuable.
