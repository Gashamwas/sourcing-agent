# Perplexity Evidence Augmentation for Candidate Evaluation

See also: `docs/perplexity-evidence-bakeoff-runbook.md` for the operator
workflow that aggregates shadow data produced by this design.

## Purpose

This document is the durable design spec for adding a bounded Perplexity-backed
external evidence step into candidate evaluation.

It is intentionally written in a workflow shape analogous to the Codex/Cursor
playbook: Codex sharpens the problem and the policy, Cursor implements against
the repo, and durable decisions live in repo docs rather than in chat.

In conversation shorthand, the idea is:

`Haiku -> Perplexity -> Haiku -> Opus`

In repo-native terms, that maps more precisely to:

`cheap extraction -> external evidence retrieval -> cheap evidence normalization -> Opus judgment`

The key constraint is that Perplexity is not a judge. It is an evidence
augmentation layer.

## Outcome

When this ships, selected high-value or ambiguous candidates can carry a
structured, cited layer of outside-world context into full evaluation without
collapsing the boundary between first-party profile evidence and model
inference. Opus should spend its expensive judgment tokens on synthesis, not on
implicit retrieval.

## Users

- recruiters and operators consuming final save/reject decisions
- prompt/model maintainers shaping evaluation behavior
- engineers implementing and testing the evaluation pipeline
- future Cursor/Codex sessions that need a stable design artifact

## Workflow Fit

This design should be used in the following loop:

1. Codex shapes the problem, the evidence policy, and the success criteria.
2. Cursor explores the narrow repo seam and implements the smallest safe slice.
3. Codex reviews the diff, checks whether provenance and bias rules survived,
   and decides what should happen next.
4. Durable decisions are recorded in this doc and the active plan under
   `plans/`.

This mirrors the intended split in `CODEX.md` without importing any file-path
assumptions from other repos.

## Inputs and Outputs

### Inputs

- first-party extracted LinkedIn profile evidence:
  - `CandidateSnippet`
  - `CandidateProfileSummary`
- sourcing brief / evaluation criteria
- trigger metadata explaining why external evidence is being requested
- candidate identity hints safe to use for public-web retrieval:
  - name
  - current company
  - current title
  - school / degree snippets
  - public profile URL if appropriate for matching

### Outputs

- a structured `ExternalCandidateEvidence` payload
- exact external source URLs used to support claims
- explicit separation of:
  - profile facts
  - sourced external facts
  - model inferences
  - unresolved ambiguities
- a final `OpusDecision`
- usage / observability records for the external evidence step

## Constraints

- External evidence augments first-party profile evidence. It does not replace
  it.
- Perplexity must never emit the final save/reject judgment.
- Facts from retrieved sources must be separated from model interpretation.
- Exact source URLs are required for any sourced claim that reaches the final
  judge.
- The system must degrade safely to the current baseline full-eval path if
  external evidence fails, times out, or is low-confidence.
- The step should be gated. It must not run on every `FACIAL_YES`.
- Public-web evidence must remain identity-bound. If the system cannot tell
  whether a paper, thesis, or biography belongs to the candidate, it should log
  ambiguity rather than promote the claim.
- This feature must not alter canonical runtime-state semantics. It is an
  evaluation-input enhancement, not a control-state change.

## Edge Cases

- sparse but promising profile with no reliable external matches
- academic candidate with many publications under a common name
- company context available but candidate-specific evidence missing
- Perplexity returns relevant prose but weak or noisy citations
- retrieved sources contradict the LinkedIn profile
- thesis / publication titles are found but authorship is ambiguous
- rate limiting, parse failure, or provider outage
- candidate already clearly qualifies from first-party evidence and does not
  justify extra latency or spend

## Current System Constraint This Addresses

The current LinkedIn full-eval path gives Opus a relatively thin summary:

- experience bullets
- education entries
- skills snippet

That is enough for many candidates, but it under-specifies cases where the real
signal lives in the meaning of employers, labs, advisors, theses, publication
areas, or adjacent public work.

The GitHub side already uses a richer evidence model before judgment. LinkedIn
does not.

## Proposed Pipeline

### 1. First-party extraction

The current flow remains the entry point:

- snippet extraction
- facial triage
- profile open
- `CandidateProfileSummary` extraction

This remains the canonical first-party evidence layer.

### 2. Trigger gate

Before full judgment, the system decides whether external evidence is likely to
change the decision enough to justify the cost.

Likely positive triggers:

- sparse but intriguing profile
- research-heavy / academic background
- unfamiliar but potentially important employer or lab pedigree
- thesis / publications likely material to fit
- borderline save/reject call
- high-value role where false negatives are especially expensive

Likely suppressors:

- already-obvious strong save from first-party evidence
- already-obvious reject from first-party evidence
- poor identity confidence for web matching
- repeated trigger on the same candidate without new query surface

### 3. Perplexity retrieval

Perplexity receives a bounded candidate evidence request, not a judgment prompt.
Its job is to retrieve and summarize relevant outside-world facts such as:

- what the employer or lab is known for
- what a thesis or paper topic suggests
- whether a school, advisor, or research group is meaningfully relevant
- what public artifacts indicate about domain depth

It should not be asked whether the candidate should be saved.

### 4. Cheap evidence normalization

The raw Perplexity result is normalized into a strict evidence contract by the
cheap model layer. This step compresses noisy web output into a consistent
payload that Opus can consume without treating the retrieval system itself as an
oracle.

### 5. Final Opus judgment

Opus receives:

- first-party profile evidence
- structured external evidence
- explicit uncertainty / ambiguity markers
- exact source URLs

Opus remains the only layer allowed to produce the final recruiting judgment.

## External Evidence Contract

The external payload should be structured roughly like this:

```json
{
  "trigger_reason": "academic_context",
  "identity_confidence": 0.0,
  "profile_facts_used_for_matching": [],
  "external_fact_blocks": [
    {
      "topic": "phd_thesis",
      "facts": [],
      "evidence_refs": [],
      "source_quality": "high|medium|low"
    }
  ],
  "external_inferences": [
    {
      "claim": "",
      "basis_refs": [],
      "confidence": 0.0
    }
  ],
  "unresolved_ambiguities": [],
  "do_not_use_for_judgment": []
}
```

The important contract rules are:

- `external_fact_blocks` contain sourced facts only
- `external_inferences` contain model synthesis derived from sourced facts
- ambiguous matches are explicitly called out
- weakly-supported claims are preserved as uncertainty, not upgraded into fact
- the final judge sees the separation clearly

## Winning Design Choice

The winning construction is:

- Perplexity as retrieval and contextual evidence
- cheap model as normalizer / compressor
- Opus as final judge

The following alternatives are rejected:

### Rejected: Perplexity as hidden evaluator

If Perplexity is asked to contextualize the candidate in a way that already
implies fit judgment, Opus is no longer judging raw evidence. It is judging a
previous model's evaluation.

### Rejected: always-on external research

This would improve some difficult calls but would likely destroy the latency and
cost profile of the current pipeline.

### Rejected: let Opus browse implicitly

That would blur provenance, make citations inconsistent, and make evaluation
quality harder to audit.

## Repo Seams

Primary likely seams:

- `linkedin/orchestrator.py`
  - insert the trigger + evidence augmentation step after profile extraction
    and before final judgment
- `shared/schemas.py`
  - define a durable schema for external candidate evidence
- `shared/judger.py`
  - add an enriched full-judge path or generalize the current full judge to
    accept both first-party and external evidence
- `shared/llm_clients.py`
  - add a repo-native Perplexity client wrapper for candidate evidence, or
    safely factor shared provider code

Potential reuse surface:

- `market_intelligence/research_agent.py`
  - useful as a reference for Perplexity client usage, structured response
    handling, and exact URL extraction

Potential caution:

- do not import the market-intelligence research flow wholesale
- market-level research and candidate-level evidence have different failure and
  trust characteristics

## Data and Provenance Rules

- First-party LinkedIn evidence remains the anchor.
- External evidence can enrich, contextualize, confirm, or challenge that
  anchor.
- External evidence cannot silently overwrite first-party evidence.
- Contradictions should be surfaced explicitly to Opus.
- Any final rationale that depends on external evidence should be traceable back
  to source URLs and the normalized evidence contract.

## Risks

### Halo risk

Prestigious employers, schools, labs, or thesis titles can create inflated
positive bias if the prompt overweights pedigree.

### Provenance collapse

If facts, interpretations, and final judgment are not separated, the system
gets harder to audit and harder to calibrate.

### Identity mismatch

Common names, thin profiles, and noisy publication search can cause the system
to attach the wrong evidence to the candidate.

### Cost and latency drift

Without gating, the new step will quietly become the dominant cost center.

### Prompt bloat

If raw Perplexity prose is passed directly to Opus, the full-eval prompt will
get longer, noisier, and less reliable.

## Evaluation Plan

This should be tested as an offline comparison before wide rollout.

Suggested bakeoff:

- baseline LinkedIn full eval
- augmented eval with trigger gate
- compare on:
  - save precision
  - false-negative recovery on sparse profiles
  - rationale specificity
  - citation quality
  - cost per evaluated candidate
  - latency per full eval

The standard is not “does the writeup sound smarter.” The standard is “does the
decision quality improve without collapsing trust or cost discipline.”

## Definition Of Done

- a candidate-level external evidence schema exists in code and tests
- the LinkedIn full-eval flow can optionally request external evidence for
  triggered candidates
- the external evidence payload preserves fact / inference / ambiguity
  separation
- exact source URLs are carried through the payload
- the system falls back cleanly to baseline full eval on failure
- targeted tests cover trigger gating, parse failure, and no-citation handling
- an offline comparison path exists to evaluate whether the augmentation
  improves save/reject quality enough to justify rollout

## Not In Scope For The First Slice

- changing runtime-state persistence semantics
- adding web research to facial triage
- rewriting the market-intelligence research stack
- turning this into a universal research layer across LinkedIn and GitHub in one
  pass
- auto-updating briefs from candidate-level external evidence
