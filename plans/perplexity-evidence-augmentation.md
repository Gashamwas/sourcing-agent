# perplexity-evidence-augmentation

Status: draft
Owner: Codex
Last updated: 2026-04-24

## Problem

LinkedIn full evaluation currently sends Opus a thin `CandidateProfileSummary`
and asks it to infer the meaning of employer pedigree, academic context, thesis
significance, and adjacent public work from sparse first-party evidence alone.
This creates a real false-negative risk on research-heavy and sparse profiles.

## Goal

Add a bounded external evidence augmentation step that enriches selected
candidates with cited public-web context before final Opus judgment, while
preserving a strict separation between retrieval, evidence normalization, and
judgment.

## Non-goals

- Add web research to facial triage.
- Change runtime-state authority or projection semantics.
- Reuse the market-intelligence research flow wholesale.
- Turn Perplexity into a candidate judge.
- Roll this out to GitHub and LinkedIn in one slice.

## Assumptions

- The current LinkedIn insertion point is after profile extraction and before
  `full_judge()`.
- Candidate-level external evidence should be public-web only.
- Perplexity can return enough exact source URLs to support a useful evidence
  layer.
- Cheap-model normalization is needed between raw Perplexity output and Opus.
- Failure of the new step must fall back to the current baseline full-eval path.

## Seam

Primary seam:

- `linkedin/orchestrator.py` between extracted `CandidateProfileSummary` and
  final judgment

Supporting seams:

- `shared/schemas.py` for an `ExternalCandidateEvidence` contract
- `shared/judger.py` for an enriched full-judge path
- `shared/llm_clients.py` for a candidate-evidence Perplexity wrapper

Reference-only seam:

- `market_intelligence/research_agent.py` for Perplexity client and citation
  handling patterns

## Proposed change

Introduce a gated candidate-evidence pipeline:

1. Evaluate whether the candidate should trigger external evidence lookup.
2. If triggered, send a bounded retrieval request to Perplexity using safe
   identity hints and the extracted profile summary.
3. Normalize the raw Perplexity output into a strict schema with:
   - sourced facts
   - model inferences
   - ambiguities
   - exact source URLs
4. Pass both first-party profile evidence and normalized external evidence to
   Opus for final judgment.
5. If any new step fails or returns weak evidence, log it and fall back to the
   current full-eval path.

This wins over the alternatives because it preserves provenance and keeps the
judgment boundary explicit.

## Risks

- identity mismatch on common names, papers, or theses
- prestige halo effects if prompts over-index on pedigree context
- citation-poor Perplexity output that sounds useful but is not trustworthy
- prompt growth that degrades Opus judgment quality
- latency/cost drift if gating is too loose
- hidden coupling if market-intelligence research helpers are reused without
  pruning candidate-specific assumptions

## Slices

- [ ] Slice 1: define the external evidence schema and candidate-level provider
      wrapper without touching judgment behavior
- [ ] Slice 2: add trigger gating and orchestrator integration with safe
      fallback to baseline full eval
- [ ] Slice 3: add enriched full-judge input path with prompt updates that keep
      fact vs inference separation explicit
- [ ] Slice 4: add offline comparison tooling/tests for baseline vs augmented
      evaluation quality

## Test strategy

- Narrowest relevant test band to run first:
  - `pytest tests/test_linkedin_pipeline.py -q`
- Tests to add/strengthen:
  - candidate external-evidence schema validation
  - trigger gate behavior
  - Perplexity parse/citation failure fallback
  - enriched full-judge prompt construction
  - identity ambiguity handling
- Full-suite gate before declaring done: `make validate`

## Open questions

- Should the normalized external evidence be persisted, or remain an ephemeral
  judgment input in the first slice?
- Should the trigger gate be heuristic-only first, or prompt-assisted?
- Should borderline reroute to external evidence before the first Opus full
  call, or only after a low-confidence initial judgment?
- Which exact source classes should be allowed in v1 beyond papers, school/lab
  pages, employer pages, and candidate websites?

## Decisions

- 2026-04-24 — Perplexity is an evidence augmentation layer, not a judge —
  keeps provenance and accountability intact
- 2026-04-24 — Cheap-model normalization sits between Perplexity and Opus —
  avoids passing noisy retrieval prose directly into the final judge
- 2026-04-24 — The first implementation target is LinkedIn full evaluation only
  — smallest safe slice with clear current weakness

## Follow-ups (not in this plan)

- Extend the same evidence contract to GitHub where it materially improves thin
  public profiles.
- Add observability dashboards for trigger rate, citation quality, and latency.
- Explore whether external evidence should inform post-run market intelligence
  without leaking candidate-level ambiguity into market artifacts.
