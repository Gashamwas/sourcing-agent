# Roadmap: Reviewed-Candidate Memory + HITL Outreach Feedback for LinkedIn

## Summary
Build two separate but connected loops for LinkedIn sourcing:

1. **Reviewed-candidate memory**
   Persist every candidate who received a full Opus review so future runs can recognize prior exact-profile adjudications and reuse that cognition.

2. **HITL outreach feedback**
   Capture the recruiter’s actual action on saved candidates as the core quality signal for the sourcing agent: `reached_out`, `not_reached_out_low_quality`, or `not_reached_out_capacity_or_timing`.

This roadmap keeps those loops separate on purpose:
- **Duplicate/already-known** stays in the memory/dedupe layer, not the recruiter-feedback vocabulary.
- **Downstream recruiting outcomes** stay out of scope for v1.
- **Same-project dedupe** stays exactly as it works today.
- **No separate RAG sub-agent in v1**. First ship a deterministic, role-scoped memory service. Semantic retrieval is a later phase.

## Phase 1: Design and Contracts
1. **Lock the identity and scope model**
   - Use exact `profile_url` as the only authoritative candidate identity in v1.
   - Treat `linkedin_project_id` as the authoritative **same-project** scope.
   - Treat the existing derived `market_key` as the advisory **same-market / same-role-family** scope.
   - Do not implement name-only or fuzzy matching in v1.

2. **Define the two canonical record types**
   - `ReviewedCandidateMemoryRecord`
     - `profile_url`, `candidate_name`, `market_key`, `origin_brief_id`, `origin_project_id`, `reviewed_at`
     - `full_decision`, `confidence`, `profile_summary_excerpt`, `rationale_excerpt`
     - `source_string_id`, optional `employer`, optional `title`
   - `LinkedInOutreachFeedbackRecord`
     - `profile_url`, `origin_project_id`, `market_key`, `feedback_at`, `actor`
     - `status` in `{reached_out, not_reached_out_low_quality, not_reached_out_capacity_or_timing}`
     - optional `note`

3. **Choose the canonical persistence locations**
   - Add a new runtime-state-backed reviewed-memory index, rather than trying to infer same-market memory from the current brief-scoped candidate table.
   - Reuse runtime-state **side effects** for recruiter outreach feedback.
   - Materialize inspectable artifacts:
     - per-project `outreach.jsonl`
     - per-market `reviewed-candidate-memory.jsonl`

4. **Lock the behavior boundaries**
   - Same-project saved-candidate dedupe remains unchanged.
   - Same-market reviewed memory is advisory in the first rollout.
   - Cross-market memory is out of scope.
   - Capacity/timing non-outreach must not count as a quality miss.

## Phase 2: Engineer the Reviewed-Candidate Memory Layer
1. **Add a market-scoped reviewed-memory index**
   - Create a canonical runtime-state table for reviewed LinkedIn candidates keyed by `(source, market_key, profile_url)`.
   - Store the latest full-review snapshot per exact profile URL within that market key.
   - Preserve provenance fields so later artifacts can explain where the prior review came from.

2. **Populate the index from the existing full-review path**
   - On every successful LinkedIn full review, upsert the reviewed-memory record.
   - Include both saves and rejects.
   - Pull rationale/profile-summary content from the existing full-review payloads instead of inventing a parallel summary path.

3. **Backfill historical reviewed candidates**
   - Add a one-time backfill command that seeds the reviewed-memory index from existing LinkedIn runtime-state/full-judgment artifacts.
   - Derive `market_key` from the originating brief for each historical run.
   - Do not backfill recruiter outreach feedback.

4. **Expose a deterministic lookup service**
   - Add a small read API that returns:
     - `same_project_exact_match`
     - `same_market_exact_match`
     - the prior decision/rationale snapshot
   - Keep same-project matches authoritative and same-market matches advisory.

## Phase 3: Engineer the HITL Outreach Feedback Loop
1. **Use side effects as the source of truth**
   - Introduce a LinkedIn-specific outreach feedback side-effect type, for example `linkedin_outreach_feedback`.
   - Keep feedback out of the candidate terminal-decision lifecycle.
   - Treat recruiter feedback as a separate append-and-replace action history, not as a sourcing-stage decision rewrite.

2. **Ship a practical v1 ingestion path**
   - Add a lightweight admin/import command that accepts CSV or JSONL keyed by `profile_url`.
   - Required fields: `profile_url`, `status`
   - Optional fields: `note`, `actor`, `feedback_at`
   - If feedback is re-imported for the same candidate/project, invalidate the previous “current” feedback side effect and write the new one.

3. **Project recruiter feedback into artifacts**
   - Continue using `outreach.jsonl` as the readable per-project artifact.
   - Include the normalized feedback status, note, actor, and timestamps.
   - Keep duplicate/already-known out of this file entirely.

4. **Set the interpretation rules**
   - `reached_out` is a positive quality signal.
   - `not_reached_out_low_quality` is a negative quality signal.
   - `not_reached_out_capacity_or_timing` is operational only and must be excluded from negative calibration.

## Phase 4: Integrate Both Loops Into the Sourcing System
1. **Hook reviewed-memory lookup into the LinkedIn run loop**
   - After each bulk facial-review pass and before full Opus review, batch-lookup all exact-profile survivors against reviewed memory.
   - If the exact profile was already reviewed in the same project, keep current hard dedupe behavior.
   - If the exact profile was reviewed in the same market but a different project, surface the prior decision/rationale as advisory context.

2. **Roll out same-market behavior in three steps**
   - **Shadow mode:** log and report same-market exact matches, but do not alter behavior.
   - **Advisory mode:** show prior decision/rationale in run logs, reports, and debug artifacts; still let the agent continue unless the operator chooses otherwise.
   - **Auto-skip mode:** only after shadow validation, allow exact same-market matches to short-circuit full re-review when the prior review is newer than 90 days. Older matches stay advisory.

3. **Feed the new signals into market intelligence**
   - Add reviewed-memory reuse metrics:
     - prior-review hit rate
     - avoided re-reviews
     - same-project vs same-market reuse
   - Add outreach-quality metrics:
     - outreach rate by family, lane, and employer cluster
     - low-quality non-outreach rate by lane/archetype
     - exclude capacity/timing from negative-quality scoring
   - Make market-intel recommendations explicitly reference these new signals.

4. **Do not let v1 feedback directly rewire search intelligence**
   - In the first deployment, use outreach feedback to inform market intelligence and operator review.
   - Only after enough data volume exists should search intelligence begin to use outreach-weighted lane scores for adaptation or prioritization.

## Phase 5: Deployment and Rollout
1. **Deploy in a low-risk order**
   - Deploy the reviewed-memory index and backfill first.
   - Then deploy shadow-mode lookup in LinkedIn runs.
   - Then deploy the outreach-feedback importer and artifact projection.
   - Then add market-intel consumption.
   - Only then consider same-market auto-skip.

2. **Add operational gates for promotion**
   - Promote from shadow to advisory once exact-URL match precision is effectively perfect and the artifacts are readable.
   - Promote from advisory to auto-skip only after manual review of several runs confirms there are no harmful suppressions and the 90-day freshness rule feels safe.

3. **Keep rollback simple**
   - All same-market memory behavior must be behind a single runtime toggle.
   - If anything feels off, disable read-path influence and keep only passive capture plus artifacts.
   - Outreach feedback import must be safe to replay and safe to invalidate.

4. **Treat semantic retrieval as a later phase**
   - Only after deterministic exact-match memory and HITL feedback are working should you add embeddings/RAG over prior rationales.
   - Even then, semantic retrieval should remain advisory and must never replace exact `profile_url` matching.

## Important Interfaces and Additions
- New internal runtime-state table: `reviewed_candidate_memory`
- New materialized market artifact: `output/market_intelligence/<market-key>/reviewed-candidate-memory.jsonl`
- New LinkedIn outreach feedback side-effect type: `linkedin_outreach_feedback`
- New admin/import interface for recruiter feedback:
  - CSV/JSONL input
  - keyed by `profile_url`
  - no UI in v1
- No brief-schema change required.
- No change to the current same-project save dedupe contract.

## Test Plan
- **Reviewed-memory persistence**
  - full-review save creates a reviewed-memory record
  - full-review reject creates a reviewed-memory record
  - later full reviews of the same exact URL update the latest record for that market
  - backfill correctly seeds historical records without duplicating them

- **Lookup semantics**
  - same-project exact matches remain authoritative
  - same-market exact matches are returned separately from same-project matches
  - no match occurs for name-only candidates without exact `profile_url`
  - records older than 90 days stay advisory when auto-skip is enabled

- **Outreach feedback**
  - valid CSV/JSONL imports create normalized feedback records
  - re-import replaces the current feedback cleanly
  - invalid statuses are rejected
  - `capacity_or_timing` does not affect negative-quality aggregates

- **Run-loop integration**
  - facial survivors are batch-looked-up before full review
  - shadow mode produces logs/artifacts but no behavior changes
  - advisory mode surfaces prior rationale cleanly
  - auto-skip mode suppresses only fresh exact same-market matches

- **Market-intel integration**
  - reviewed-memory reuse stats appear in artifacts
  - outreach rate and low-quality non-outreach rate appear by lane/family
  - capacity/timing is excluded from negative scoring
  - recommendations remain provenance-backed

- **Regression coverage**
  - existing same-project dedupe still works
  - resume/runtime-state rebuilds still work
  - no regression in search-memory, search-intelligence, or market-intel finalization

## Assumptions and Defaults
- V1 uses exact `profile_url` only; fuzzy candidate matching is intentionally deferred.
- Same-project memory is authoritative; same-market memory is advisory first.
- Recruiter feedback vocabulary is exactly:
  - `reached_out`
  - `not_reached_out_low_quality`
  - `not_reached_out_capacity_or_timing`
- Duplicate/already-known is handled by the memory/dedupe system, not the recruiter-feedback system.
- No separate RAG sub-agent is built in v1.
- Same-market auto-skip, if enabled, applies only to exact URL matches reviewed within 90 days.
