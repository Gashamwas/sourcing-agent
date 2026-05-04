# Calibration Layer Audit: Vertical-Agnostic Readiness

Date: 2026-04-26

## Scope

This audit verifies where the repo is already vertical-agnostic and where domain-specific recruiting assumptions still leak into live code. The focus is the calibration surface: prompt text, strategy heuristics, brief loading, preflight authoring, and adapter-level shortcuts that influence candidate retrieval or judgment.

## Executive Summary

The repo's runtime backbone is substantially cleaner than its current product positioning suggests. The canonical runtime state, execution lifecycle, and layered retrieval abstractions are reusable across verticals. The system stops being vertical-agnostic in the calibration layer: prompt examples, novelty heuristics, search-memory inference, fallback defaults, preflight guidance, and a few adapter heuristics still teach the system to think like an AI/ML recruiter.

The biggest architectural lesson is that the repo already has the right abstraction boundary, but the boundary is only half-enforced. `shared/brief_schema.py` implies “all role-specific content lives in the brief,” while `linkedin/strategy.py`, `shared/search_memory.py`, `shared/preflight*.py`, and legacy prompt paths still carry hidden domain priors in code.

## Reference Architecture Confirmed Generic

These files are functioning as reusable infrastructure and should be treated as the reference architecture for the refactor.

- `shared/runtime_state/store.py`
  - Canonical SQLite lifecycle state, transition guards, and work-unit bookkeeping are domain-free.
- `shared/execution/runtime.py`
  - Shared candidate-stage envelope and attempt lifecycle are domain-free.
- `shared/retrieval_design.py`
  - The layered retrieval model (`entry_signals`, `capability_proxies`, `reality_filters`, `context_constraints`, `anti_noise`) is domain-free.
- `linkedin/search_intelligence.py`
  - Variant lineage, drift assessment, and mutation bookkeeping are domain-free.
- Most of `shared/brief_schema.py`
  - Container dataclasses like `CapabilityArea`, `NonFitPattern`, `EmployerSignalRule`, `DepthDistinction`, `FacialCalibration`, and `PostSaveModifier` are generic shapes even when some examples in comments are AI-specific.

## Architectural Constraint Discovered

The repo uses two brief models:

- `shared/brief_schema.Brief`
  - Structured V2 brief used by `linkedin/judgment_templates.py`, the bias monitor, and other newer components.
- `shared/brief_loader.Brief`
  - Legacy/compat brief used by `linkedin/strategy.py`, `shared/judger.py`, orchestrators, and older flows.

For V2 briefs, `shared/brief_loader.py` creates both and stores the structured object on `Brief._new_brief`.

Implication:

- Any vertical-agnostic schema change that only touches `shared/brief_schema.py` is incomplete.
- The compatibility bridge in `shared/brief_loader.py` is the real integration seam for this refactor.

## Confirmed Findings

### F1. LinkedIn full-evaluation prompt still teaches AI/ML semantics

Evidence:

- `linkedin/judgment_templates.py:257`
- `linkedin/judgment_templates.py:267`
- `linkedin/judgment_templates.py:288`
- `linkedin/judgment_templates.py:295-326`

Manifestation:

- The evidence hierarchy uses AI examples (`PyTorch`, `QLoRA`).
- Sparse-profile examples are AI-specific (`PhD + ML title + QLoRA`).
- The “adjacent” example is ML-specific.
- Step 2 and Step 3 explicitly define depth and transferability using ML/LLM/RL vocabulary.

Why it matters:

- Even if the brief is generic, the judge is still being shown what “real depth” looks like in AI.
- A non-AI brief would be evaluated through the wrong ontology before brief content is even considered.

Required action:

- Keep the four-step procedure.
- Replace every embedded example and lexicon item with brief-driven blocks or neutral role-agnostic prose.

### F2. LinkedIn facial templates still assume “AI buzzword filtering”

Evidence:

- `linkedin/judgment_templates.py:81`
- `linkedin/judgment_templates.py:117`

Manifestation:

- The facial gate says “Generic seniority + generic AI keywords is NOT sufficient.”

Why it matters:

- This is lower-severity than F1, but it still leaks domain assumptions into the highest-volume gate in the system.
- The right rule is generic: generic seniority plus generic buzzwords is insufficient.

Required action:

- Rewrite this guidance to be domain-neutral or brief-driven.

### F3. Seniority calibration in the structured brief is AI-specific

Evidence:

- `shared/brief_schema.py:382-461`

Manifestation:

- `seniority_calibration_block()`, `executive_builder_block()`, and `post_evaluation_safety_net()` hardcode “Head of AI,” “Agentic AI paradigms,” “AI function,” and AI-leadership trajectory examples.

Why it matters:

- These blocks are executed for L7+ roles.
- A non-AI executive search would inherit the wrong idea of what organizational builder evidence looks like.

Required action:

- Move senior-role titles, paradigms, and function naming into brief fields.
- Keep the tiered evidence procedure but externalize the senior-role lexicon.

### F4. GitHub fallback patterns in the structured brief silently inject AI defaults

Evidence:

- `shared/brief_schema.py:300-339`

Manifestation:

- If GitHub-specific patterns are missing, the brief object supplies AI/ML defaults for YES, AMBIGUOUS, and NO portfolio patterns.

Why it matters:

- This is silent contamination.
- Missing calibration becomes “assume frontier ML recruiting,” which is the worst possible default for a supposedly generic system.

Required action:

- Remove the AI fallback lists or make them empty-plus-warning.
- Do not silently invent GitHub calibration.

### F5. Strategy novelty bucketing is hardcoded to AI/FDE taxonomy

Evidence:

- `linkedin/strategy.py:37-226`
- `linkedin/strategy.py:260-303`

Manifestation:

- `_CANONICAL_FRAMEWORK_PATTERNS`, `_CANONICAL_COMPANY_PATTERNS`, `_CANONICAL_TITLE_PATTERNS`, `_CANONICAL_BROAD_PATTERNS`, `_EDGE_CASE_PATTERNS`, and `_EDGE_CASE_COMPANY_PATTERNS` are all code constants.
- `_opening_priority()` scores strings against those hardcoded sets to determine whether a string is “edge-case” or “canonical.”

Why it matters:

- This drives opening-sequence order, novelty accounting, and cleanup-vs-discovery judgment.
- For a new vertical, the system would literally misclassify “obvious pool” versus “adjacent pool.”

Required action:

- Move these pattern lists into the brief.
- Add a new brief field for `_CANONICAL_BROAD_PATTERNS`, which the original audit did not call out but the code uses.

### F6. Strategy formation prompt is full of AI-specific planning examples

Evidence:

- `linkedin/strategy.py:928-1054`

Manifestation:

- Example compound uses `agentic` and `LLM agent`.
- Precision-signal examples are AI frameworks, benchmarks, and post-training methods.
- Sequencing guidance is explicitly RL/RLHF-specific.
- Abbreviation collisions are AI-specific.
- Blacklist categories are AI/ML/tool-specific.

Why it matters:

- This prompt is what teaches the planner how to think.
- Even if the Boolean mechanics are universal, the planner is still being taught the wrong search instincts.

Required action:

- Split infrastructure rules from domain rules.
- Keep LinkedIn mechanics in static prose.
- Push sequencing, blacklist categories, abbreviation collisions, and example compounds into brief fields.

### F7. Strategy adaptation prompt repeats the same AI-specific framing mid-run

Evidence:

- `linkedin/strategy.py:1363-1394`

Manifestation:

- Adaptation guidance references post-training terms, exact-title FDEs, framework-first strings, frontier-company pools, and qualified terms like `AI agent`.

Why it matters:

- Cleaning only the initial planner prompt is insufficient.
- After block 1, the agent would reintroduce domain-specific reasoning during adaptation.

Required action:

- Refactor the adaptation prompt in the same slice as the initial strategy prompt.

### F8. Search-memory heuristics are still hardcoded to BFSI/AI lanes

Evidence:

- `shared/search_memory.py:13-119`
- `shared/search_memory.py:121-186`
- `shared/search_memory.py:188-268`
- `shared/search_memory.py:300-332`

Manifestation:

- `_STOPWORDS` includes `genai`, `ai`, `llm`, `rag`, `banking`, `bfsi`.
- `_ANCHOR_PHRASES`, `_BIG_BANK_TERMS`, `_EDGE_CASE_TERMS`, and `_DOMAIN_LANE_HINTS` encode finance-market language and AI-adjacent novelty hints.
- `normalize_novelty_bucket()` and `infer_domain_lane()` reclassify strings based on those terms when explicit metadata is absent.

Why it matters:

- Even if `linkedin/strategy.py` becomes brief-driven, stored family memory can still be reinterpreted through hardcoded finance/AI heuristics.
- This is a latent architecture bug because memory should aggregate explicit metadata, not re-author the taxonomy.

Required action:

- Remove domain-specific fallback inference.
- Trust explicit strategy metadata and fall back to neutral values like `canonical` and `general`.

### F9. Legacy prompt builders in `shared/judger.py` remain AI-biased and are still reachable

Evidence:

- `shared/judger.py:183-211`
- `shared/judger.py:272-314`
- `shared/judger.py:378-469`
- `linkedin/orchestrator.py:5245-5255`

Manifestation:

- Old facial/full prompt builders still carry AI-specific inference rules.
- V2 flows use `linkedin/judgment_templates.py`, but the orchestrator still falls back to old preflight and reinitializes the old judger path on failure.

Why it matters:

- This is dead-but-live behavior.
- A new vertical can route through legacy AI logic if preflight or brief selection takes the wrong path.

Required action:

- Ensure V2 flows never fall back into old AI-biased prompt generation.
- Delete legacy prompt builders only after old brief callers are migrated or explicitly deprecated.

### F10. Preflight authoring is still AI/technical-recruiting flavored

Evidence:

- `shared/preflight.py:69-182`
- `shared/preflight_v2.py:31-98`
- `linkedin/orchestrator.py:5235-5255`

Manifestation:

- Old preflight explicitly instructs a “senior technical recruiter” and uses AI/ML examples for archetypes, noise, and inference.
- V2 preflight still uses AI-specific employer tiers and trajectory examples (`frontier_lab`, `strong_ai`, “positions at frontier labs”).
- On V2 failure, the orchestrator falls back to the older AI-biased preflight.

Why it matters:

- If new vertical launches depend on JD-only bootstrapping, the authoring pipeline will still hallucinate AI recruiting priors into the generated brief.

Required action:

- Neutralize both preflight prompts.
- Remove or gate the fallback from V2 preflight to legacy preflight.

### F11. LinkedIn adapter heuristics still contain AI-title assumptions

Evidence:

- `linkedin/orchestrator.py:2330-2370`
- `linkedin/orchestrator.py:3907-3914`

Manifestation:

- `_snippet_is_clearly_compelling()` hardcodes “head of ai,” “head of ml,” and related titles.
- The facial-tightening prefix uses AI-specific example copy.

Why it matters:

- These heuristics influence opening behavior and bias-monitor guidance outside the prompt layer.
- They are small compared with the strategy/judgment leaks, but they are still live policy.

Required action:

- Replace hardcoded title sets with brief-driven senior-role titles.
- Rewrite tightening copy to be generic.

### F12. GitHub adapter is structurally specialized for ML/code recruiting

Evidence:

- `github/judgment_templates.py:136-280`
- `github/judgment_templates.py:313-344`
- `github/orchestrator.py:1087-1107`

Manifestation:

- Full GitHub evaluation is explicitly a technical/ML-depth judge.
- Default GitHub facial patterns are AI/ML-specific.
- GitHub prefilter falls back to generic ML/research bio keywords.

Why it matters:

- This is not just “latent coupling.” The GitHub adapter is functionally specialized around code evidence and ML signals.
- A non-technical executive search can still use the platform if GitHub is optional, but the GitHub adapter itself is not currently vertical-agnostic.

Required action:

- In the first slice, remove silent AI defaults and generic ML fallback keywords.
- Treat “fully generic GitHub sourcing for non-code roles” as a separate product decision.

## Secondary / Deferred Findings

These are real but are not the first blockers to fix.

- `shared/brief_iteration.py`
  - Authoring/iteration tooling still contains BFSI/GenAI assumptions. This matters after runtime behavior is fixed, not before.
- Example comments/docstrings in `shared/brief_schema.py`, `shared/preflight_v2.py`, and related files
  - These do not directly affect runtime, but they will bias future maintainers and operators if left untouched.

## Brief Inventory Impact

Current config inventory from `config/**/*.json`:

- 20 V2 brief JSON files load through the structured V2 path.
- 18 of those are non-draft/non-backup files.
- 10 JSON files are old-format or non-brief support configs.

Implication:

- The final state can and should fail loudly for incomplete V2 calibration.
- The rollout should stage through a migration pass first, because multiple active V2 briefs need the new fields populated.

## Recommended Boundary for the First Refactor

The first implementation slice should cover:

- `shared/brief_schema.py`
- `shared/brief_loader.py`
- `linkedin/judgment_templates.py`
- `linkedin/strategy.py`
- `shared/search_memory.py`
- `shared/preflight.py`
- `shared/preflight_v2.py`
- `shared/judger.py`
- `linkedin/orchestrator.py`

The GitHub adapter should be included only for:

- removal of silent AI defaults
- explicit neutral behavior when GitHub calibration is absent

It should not be treated as “fully generalized for any recruiting context” in the same slice unless the product explicitly wants GitHub evidence for non-code roles.

## Bottom Line

The repo is closer to vertical-agnostic than it looks. The core execution and retrieval architecture already support the abstraction. The remaining work is concentrated in the calibration layer and the compatibility bridge.

Once the hidden AI/BFSI vocabulary is moved into the brief and the brief loader becomes the only place where role-specific calibration enters the runtime, the product can honestly claim:

- core platform logic is domain-agnostic
- the brief is the full calibration surface
- new verticals require domain authoring and calibration, not code changes
