# Vertical-Agnostic Calibration Spec

Date: 2026-04-26

## Objective

Refactor the calibration layer so every domain-specific recruiting vocabulary item that materially shapes retrieval, judgment, novelty accounting, or executive calibration comes from the brief rather than from code constants or template prose.

## Design Goals

- Preserve the generic runtime and retrieval architecture.
- Preserve the structural evaluation procedure in LinkedIn and GitHub prompt templates where it is already sound.
- Minimize risk by keeping the dual-brief bridge and extending it rather than rewriting strategy/orchestration around a single brief model.
- Make incomplete V2 calibration explicit and auditable.
- Preserve AI-role behavior by migrating existing AI briefs to carry the vocabulary currently hardcoded in code.

## Non-goals

- Full unification of `shared.brief_loader.Brief` and `shared.brief_schema.Brief`.
- Full genericization of the GitHub adapter for non-code roles.
- Changes to runtime-state persistence, projections, or lifecycle semantics.

## Design Decisions

- The brief remains the only role-specific calibration artifact.
- Strategy and search-memory should consume explicit metadata rather than infer vertical taxonomy from hardcoded phrases.
- V2 is the only supported path for new vertical launches.
- Final state should hard-fail incomplete V2 calibration, but migration should stage through temporary warnings.

## Schema Contract

### New helper dataclasses

Add to `shared/brief_schema.py`:

```python
@dataclass
class TransferabilityExample:
    result: str  # "transfers" | "does_not_transfer"
    source_context: str
    target_context: str
    rationale: str

@dataclass
class BlacklistCategory:
    label: str
    rationale: str
    terms: list[str] = field(default_factory=list)

@dataclass
class AbbreviationCollision:
    abbreviation: str
    expansion: str
    standalone_allowed: bool = False
    note: str = ""

@dataclass
class ExampleCompound:
    boolean: str
    purpose: str
    novelty_bucket: str = ""

@dataclass
class DomainLaneHint:
    lane: str
    patterns: list[str] = field(default_factory=list)
```

### New brief fields

Add to `shared.brief_schema.Brief`:

```python
domain_verbs: list[str] = field(default_factory=list)
domain_depth_objects: list[str] = field(default_factory=list)
transferability_examples: list[TransferabilityExample] = field(default_factory=list)

canonical_framework_patterns: list[str] = field(default_factory=list)
canonical_company_patterns: list[str] = field(default_factory=list)
canonical_title_patterns: list[str] = field(default_factory=list)
canonical_broad_patterns: list[str] = field(default_factory=list)
edge_case_patterns: list[str] = field(default_factory=list)
edge_case_company_patterns: list[str] = field(default_factory=list)

sequencing_heuristics: str = ""
term_blacklist_categories: list[BlacklistCategory] = field(default_factory=list)
abbreviation_collisions: list[AbbreviationCollision] = field(default_factory=list)
example_compounds: list[ExampleCompound] = field(default_factory=list)
domain_lane_hints: list[DomainLaneHint] = field(default_factory=list)

senior_role_titles: list[str] = field(default_factory=list)
senior_role_paradigms: list[str] = field(default_factory=list)
senior_role_function_name: str = ""
```

### New brief formatting helpers

Add rendering helpers on `shared.brief_schema.Brief`:

- `domain_verbs_block()`
- `domain_depth_objects_block()`
- `transferability_examples_block(result: str | None = None)`
- `term_blacklist_block()`
- `abbreviation_collisions_block()`
- `example_compounds_block()`
- `domain_lane_hints_map()`
- `strategy_pattern_sets()` or equivalent simple accessors

### Validation rules

Add a V2 calibration validator that checks:

- `domain_verbs`
- `domain_depth_objects`
- `transferability_examples`
- `canonical_*` plus `edge_case_*`
- `sequencing_heuristics`
- `term_blacklist_categories`
- `abbreviation_collisions`
- `example_compounds`
- `senior_role_titles`, `senior_role_paradigms`, `senior_role_function_name` when `is_senior_role()`

Rollout behavior:

- Stage 1: emit warnings on missing fields for V2 briefs.
- Stage 2: raise `ValueError` for missing required fields on V2 briefs.
- Old-format briefs remain legacy/compat and are not part of the new vertical-agnostic contract.

## Compatibility Bridge

### `shared/brief_loader.py`

Extend both the structured and compat paths.

For the structured brief:

- Parse the new V2 JSON fields into the new dataclasses.
- Attach them to `shared.brief_schema.Brief`.

For the compat brief:

- Mirror strategy-relevant fields directly onto `shared.brief_loader.Brief` so `linkedin/strategy.py` can read them without reaching through `_new_brief` everywhere.
- Keep the raw JSON copy for debugging and migration tooling.

Recommended compat additions:

- `domain_verbs`
- `domain_depth_objects`
- `transferability_examples`
- `canonical_framework_patterns`
- `canonical_company_patterns`
- `canonical_title_patterns`
- `canonical_broad_patterns`
- `edge_case_patterns`
- `edge_case_company_patterns`
- `sequencing_heuristics`
- `term_blacklist_categories`
- `abbreviation_collisions`
- `example_compounds`
- `domain_lane_hints`
- `senior_role_titles`
- `senior_role_paradigms`
- `senior_role_function_name`

Why:

- This localizes the bridge logic to the loader instead of teaching every consumer how to spelunk `_new_brief`.

## Consumer Refactors

### 1. `linkedin/judgment_templates.py`

Keep:

- overall prompt structure
- evidence hierarchy concept
- capability mapping / depth / transferability / decision procedure

Change:

- Remove AI-specific examples from the evidence hierarchy, sparse-profile examples, adjacent examples, Step 2, and Step 3.
- Replace hardcoded verb/object lists with brief-rendered blocks.
- Replace hardcoded transferability examples with `brief.transferability_examples_block()`.
- Rewrite “generic seniority + AI keywords is insufficient” to generic wording.

Important:

- Many of the leaked examples can be replaced with neutral prose rather than new fields. Do not add brief fields where neutral infrastructure text is enough.

### 2. `shared/brief_schema.py` seniority helpers

Refactor:

- `seniority_calibration_block()`
- `executive_builder_block()`
- `post_evaluation_safety_net()`

New behavior:

- Use `senior_role_titles`, `senior_role_paradigms`, and `senior_role_function_name`.
- Preserve the evidence-tier logic.
- Remove AI-specific examples and role labels.

### 3. `linkedin/strategy.py`

Refactor:

- Remove module-level canonical/edge-case constants.
- Replace `_opening_priority()` scoring inputs with brief-provided pattern sets.
- Refactor the initial planner prompt and the mid-run adaptation prompt to:
  - keep LinkedIn Boolean mechanics static
  - source sequencing heuristics, blacklist categories, abbreviation collisions, and example compounds from the brief

Important discovery:

- `_CANONICAL_BROAD_PATTERNS` is live logic and must be externalized even though it was not listed in the original audit memo.

### 4. `shared/search_memory.py`

Refactor philosophy:

- Search memory should aggregate and normalize explicit metadata, not infer vertical taxonomy.

Change:

- Remove `_BIG_BANK_TERMS`, `_EDGE_CASE_TERMS`, `_DOMAIN_LANE_HINTS`, and AI/BFSI-specific stopwords from live inference paths.
- `normalize_novelty_bucket()` should normalize explicit values and otherwise default to `canonical`.
- `infer_domain_lane()` should normalize explicit values and otherwise default to `general`.
- `extract_dominant_anchors()` should use generic lexical extraction only.

Why:

- `linkedin/strategy.py` already annotates strings with `family_key`, `novelty_bucket`, and `domain_lane`.
- Reclassification in memory is unnecessary and domain-coupling-prone.

### 5. `shared/judger.py`

Required outcome:

- V2 flows never use the older AI-biased prompt builders.

Implementation options:

- Preferred: route all active V2 calls through the structured template path only, then deprecate legacy builders.
- Transitional: keep legacy builders only for old-format briefs and clearly label them legacy/unsupported for vertical-agnostic launches.

Do not:

- Delete the old path until old-format callers are accounted for.

### 6. `shared/preflight.py` and `shared/preflight_v2.py`

Change:

- Rewrite prompts to be domain-neutral.
- Remove AI/ML/frontier-lab examples and employer-tier names.
- When the JD lacks enough information, instruct the model to leave fields sparse and let the operator fill them in.

Critical runtime change:

- `linkedin/orchestrator.py:_run_preflight_v2()` should stop falling back to the older AI-biased preflight for vertical-agnostic mode.

Recommended behavior:

- If V2 preflight fails, surface the failure and require operator review/manual brief completion.

### 7. `linkedin/orchestrator.py`

Refactor:

- `_snippet_is_clearly_compelling()` should use brief-driven senior role titles instead of AI title lists.
- Facial-tightening example copy should be generic and capability-based rather than AI-based.

### 8. GitHub path

Immediate requirement:

- Remove silent AI defaults in `github/judgment_templates.py`.
- Remove generic ML fallback keywords in `github/orchestrator.py`.

First-slice target behavior:

- If GitHub-specific calibration is absent, behavior is explicit and neutral.
- The system should not silently convert “missing GitHub calibration” into “frontier ML GitHub search.”

Deferred:

- Fully generic GitHub evaluation for non-code roles.

## Brief Authoring JSON Shape

Expected new V2 brief fragment:

```json
{
  "domain_verbs": ["owned", "launched", "scaled"],
  "domain_depth_objects": ["campaigns with measurable lift", "budget ownership over $10M"],
  "transferability_examples": [
    {
      "result": "transfers",
      "source_context": "Indie distribution marketing",
      "target_context": "Studio marketing leadership",
      "rationale": "Channel strategy, release positioning, and campaign measurement transfer cleanly."
    },
    {
      "result": "does_not_transfer",
      "source_context": "Consumer influencer marketing with no release ownership",
      "target_context": "Film slate marketing",
      "rationale": "Audience growth alone does not demonstrate launch orchestration or P&A ownership."
    }
  ],
  "canonical_company_patterns": ["A24", "Neon", "Searchlight"],
  "canonical_title_patterns": ["Head of Marketing", "VP Marketing", "EVP Marketing"],
  "canonical_broad_patterns": ["film marketing", "release campaign", "awards campaign"],
  "edge_case_patterns": ["festival programming", "indie distribution", "manager-producer"],
  "sequencing_heuristics": "Lead with senior title and campaign ownership; backload festival-specific and awards-specific language.",
  "term_blacklist_categories": [
    {
      "label": "viewer-side language",
      "rationale": "These terms describe fandom or audience behavior, not operator-side work.",
      "terms": ["fan community", "film lover", "movie buff"]
    }
  ],
  "abbreviation_collisions": [
    {
      "abbreviation": "P&A",
      "expansion": "prints and advertising",
      "standalone_allowed": false,
      "note": "Pair with expansion in mixed geographies."
    }
  ],
  "example_compounds": [
    {
      "boolean": "(\"head of marketing\" OR \"vp marketing\") AND (film OR studio OR distribution) AND (launch OR campaign OR release)",
      "purpose": "broad recall",
      "novelty_bucket": "canonical"
    }
  ],
  "domain_lane_hints": [
    {
      "lane": "distribution",
      "patterns": ["distribution", "release", "theatrical", "P&A"]
    }
  ],
  "senior_role_titles": ["Head of Marketing", "VP Marketing", "EVP Marketing"],
  "senior_role_paradigms": ["release strategy", "awards positioning", "P&A allocation"],
  "senior_role_function_name": "marketing function"
}
```

## Migration Plan

### Stage 0. Land schema and warning-only validation

- Add the fields and rendering helpers.
- Loader accepts them and warns when missing on V2 briefs.

### Stage 1. Migrate AI briefs mechanically

- Populate the new fields by extracting current code constants and prompt examples into the AI briefs.
- Verify prompt/strategy parity for active AI briefs.

### Stage 2. Flip consumers

- Switch LinkedIn judgment/strategy/search-memory/orchestrator consumers to the new brief surface.
- Remove hardcoded constants and prose.

### Stage 3. Remove unsafe fallbacks

- Stop V2 preflight fallback into the old AI preflight.
- Quarantine or remove legacy AI-biased prompt builders.
- Strip GitHub AI defaults.

### Stage 4. Enforce validation

- Missing required V2 calibration fields become load failures.

### Stage 5. Cross-vertical proof

- Add a non-AI fixture brief and verify rendered prompts/strategy output contain no leaked AI vocabulary.

## Acceptance Criteria

The refactor is complete when all of the following are true:

- No live LinkedIn strategy/judgment/search-memory code path contains hardcoded AI/ML/BFSI calibration vocabulary.
- A V2 brief contains the full calibration surface needed for judgment, novelty bucketing, sequencing, and senior-role interpretation.
- `shared/brief_loader.py` loads the new fields and exposes them consistently to both structured and compat consumers.
- AI briefs preserve equivalent behavior after migration.
- A synthetic non-AI brief renders:
  - no AI/ML/LLM/RLHF/frontier-lab examples in LinkedIn prompts
  - no BFSI lane defaults in search memory
  - no AI-specific senior-role copy
- GitHub paths do not silently inject AI defaults when calibration is absent.

## Test Plan

Add or strengthen:

- `tests/test_extractors.py`
  - prompt rendering from V2 briefs
  - leakage checks for non-AI fixture briefs
- `tests/test_linkedin_strategy.py`
  - brief-driven novelty bucketing
  - planner/adaptation prompt assembly using example compounds, blacklist categories, and collisions
- `tests/test_search_memory.py`
  - no domain-specific fallback inference
- `tests/test_retrieval_design.py`
  - loader integration remains valid
- `tests/test_token_efficiency.py`
  - prompt-size changes remain within intended bounds
- New preflight tests
  - ensure `shared/preflight_v2.py` and `shared/preflight.py` prompts are neutral

Suggested narrow band:

- `pytest tests/test_extractors.py tests/test_linkedin_strategy.py tests/test_search_memory.py -q`

Full gate:

- `make validate`

## Rollout Notes

- Do not edit `config/brief-*-draft.json` in this slice without explicit instruction.
- Migrate active V2 briefs first, then turn warnings into hard failures.
- Keep the change set deliberately sliced: schema/loader first, consumer refactor second, migration/cleanup last.

## Residual Product Constraint

After this spec ships, the LinkedIn path can honestly be called vertical-agnostic. The GitHub path cannot yet be called universal for any recruiting context; it can only be called safe for multi-vertical deployment if missing GitHub calibration no longer silently injects AI priors.
