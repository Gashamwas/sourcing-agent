"""Strategy formation and adaptation — Opus plans and adjusts search execution.

Kit strings are VOCABULARY — raw Boolean terms organized by competency domain
that Opus uses as building blocks. Kit strings NEVER appear in the execution queue.
Opus synthesizes its own compound search strings from this vocabulary.

Two main functions:
1. form_strategy() — ONE Opus call at run start to synthesize compound search strings
2. adapt_after_block() — ONE Opus call after each block to generate new strings from vocabulary
"""

from __future__ import annotations
import json
import re
import sys
from shared.schemas import KitString, ExecutionPlan, BlockReport, AdaptationResponse, SearchString
from shared.llm_clients import opus_llm
from shared.brief_loader import Brief


_CANONICAL_FRAMEWORK_PATTERNS = (
    "langgraph",
    "pydanticai",
    "dspy",
    "crewai",
    "autogen",
    "semantic kernel",
    "model context protocol",
    "mcp",
    "browser-use",
    "browser use",
    "playwright",
    "litellm",
    "langsmith",
    "ragas",
    "deepeval",
)

_CANONICAL_COMPANY_PATTERNS = (
    "palantir",
    "scale ai",
    "snorkel",
    "anthropic",
    "openai",
    "cohere",
    "cognition",
    "cursor",
    "anduril",
    "dataiku",
    "datarobot",
    "c3 ai",
    "c3.ai",
)

_CANONICAL_TITLE_PATTERNS = (
    "forward deployed",
    "forward-deployed",
    "customer engineer",
    "customer engineering",
    "solutions engineer",
    "solutions engineering",
    "implementation engineer",
    "implementation engineering",
    "delivery engineer",
    "delivery engineering",
    "field engineer",
    "field engineering",
)

_CANONICAL_BROAD_PATTERNS = (
    "agentic workflow",
    "agentic workflows",
    "agentic system",
    "agentic systems",
    "agent orchestration",
    "tool calling",
    "function calling",
)

_EDGE_CASE_PATTERNS = (
    "copilot",
    "co-pilot",
    "internal copilot",
    "knowledge management",
    "knowledge assistant",
    "intelligent search",
    "semantic search",
    "document processing",
    "document understanding",
    "document intelligence",
    "contract analysis",
    "compliance workflow",
    "support automation",
    "developer productivity",
    "internal tools",
    "technical discovery",
    "solution design",
    "solutions delivery",
    "requirements gathering",
    "trusted advisor",
    "technical consulting",
    "reference architecture",
    "reference implementation",
    "deployment toolkit",
    "accelerator",
    "reusable module",
    "reusable modules",
    "delivery playbook",
    "workflow engine",
    "human in the loop",
    "human-in-the-loop",
    "semantic cache",
    "evaluation harness",
    "eval harness",
    "observability",
    "tracing",
    "prompt logging",
    "latency optimization",
    "cost optimization",
    "agent routing",
    "event-driven",
    "event driven",
    "temporal",
    "fastapi",
)

_EDGE_CASE_COMPANY_PATTERNS = (
    "deloitte",
    "accenture",
    "bcg",
    "bcg x",
    "mckinsey",
    "quantumblack",
    "slalom",
    "thoughtworks",
    "epam",
    "globant",
    "ci&t",
    "harvey",
    "casetext",
    "ironclad",
    "robin ai",
    "evenup",
    "notion",
    "glean",
    "moveworks",
    "writer",
    "hebbia",
    "vellum",
)

_MAX_PROMOTED_EDGE_CASE_GAPS = 3


def _brief_targets_edge_case_opening(brief: Brief) -> bool:
    """Whether the brief explicitly calls for a tapped-market edge-case opening."""
    haystack = " ".join(
        [brief.role_description, brief.intake_notes, *(brief.instructions or [])]
    ).lower()
    triggers = (
        "tapped",
        "exhausted",
        "heavily worked",
        "already been worked",
        "obvious pool",
        "edge-case",
        "edge case",
        "nooks and crannies",
    )
    return any(trigger in haystack for trigger in triggers)


def _opening_priority(boolean: str, rationale: str = "") -> tuple[int, int]:
    """Classify how suitable a string is for an edge-case opening sequence.

    Returns (bucket, score):
      bucket 0 = edge-case / adjacent opening string
      bucket 1 = neutral / mixed
      bucket 2 = canonical cleanup string
    """
    text = f"{boolean} {rationale}".lower()

    framework_hits = sum(1 for pattern in _CANONICAL_FRAMEWORK_PATTERNS if pattern in text)
    company_hits = sum(1 for pattern in _CANONICAL_COMPANY_PATTERNS if pattern in text)
    title_hits = sum(1 for pattern in _CANONICAL_TITLE_PATTERNS if pattern in text)
    broad_hits = sum(1 for pattern in _CANONICAL_BROAD_PATTERNS if pattern in text)
    edge_hits = sum(1 for pattern in _EDGE_CASE_PATTERNS if pattern in text)
    edge_hits += sum(1 for pattern in _EDGE_CASE_COMPANY_PATTERNS if pattern in text)

    has_exact_fde = bool(
        re.search(r"\bforward deployed\b|\bforward-deployed\b|\bfde\b|\bfdse\b", text)
    )
    framework_first = framework_hits >= 2 and edge_hits == 0
    company_first = company_hits >= 2 and edge_hits == 0
    title_first = (title_hits >= 1 or has_exact_fde) and edge_hits == 0
    broad_core = broad_hits >= 2 and edge_hits == 0

    canonical = has_exact_fde or framework_first or company_first or title_first or broad_core
    edge_case = edge_hits >= 2 or (edge_hits >= 1 and not canonical)

    if edge_case and not canonical:
        bucket = 0
    elif canonical and edge_hits <= 1:
        bucket = 2
    else:
        bucket = 1

    score = (
        edge_hits * 5
        - framework_hits * 4
        - company_hits * 3
        - title_hits * 3
        - broad_hits * 2
        - (4 if has_exact_fde else 0)
    )
    return bucket, score


def _sort_strings_for_edge_case_opening(strings: list[dict]) -> list[dict]:
    annotated: list[tuple[tuple[int, int, int], dict]] = []
    for idx, item in enumerate(strings):
        bucket, score = _opening_priority(
            item.get("boolean", ""),
            item.get("rationale", "") or item.get("gap", ""),
        )
        annotated.append(((bucket, -score, idx), item))
    annotated.sort(key=lambda pair: pair[0])
    return [item for _, item in annotated]


def _augment_novelty_metrics(plan: ExecutionPlan) -> None:
    success_metric = (
        "At least 50% of saves from the first 2 blocks come from adjacent or edge-case "
        "pools rather than exact-title FDE, framework-first, or canonical frontier-company strings"
    )
    pivot_trigger = (
        "Early saves cluster in exact-title FDE, framework-first, or canonical frontier-company "
        "pools without surfacing adjacent populations"
    )
    sequencing_trigger = (
        "The opening block relies mainly on broad 'agentic + production' or direct framework-name "
        "strings instead of edge-case transfer populations"
    )

    if success_metric not in plan.architecture_success_criteria:
        plan.architecture_success_criteria.append(success_metric)
    if pivot_trigger not in plan.architecture_pivot_triggers:
        plan.architecture_pivot_triggers.append(pivot_trigger)
    if sequencing_trigger not in plan.architecture_pivot_triggers:
        plan.architecture_pivot_triggers.append(sequencing_trigger)


def _rebalance_execution_plan_for_edge_case_opening(plan: ExecutionPlan) -> str:
    """Promote edge-case coverage gaps and demote canonical opening strings."""
    promoted_gaps: list[dict] = []
    remaining_gaps: list[dict] = []

    for gap in plan.coverage_gaps:
        boolean = gap.get("suggested_boolean")
        if not boolean:
            remaining_gaps.append(gap)
            continue

        bucket, score = _opening_priority(boolean, f"{gap.get('gap', '')} {gap.get('rationale', '')}")
        if bucket != 2 and score >= 20 and len(promoted_gaps) < _MAX_PROMOTED_EDGE_CASE_GAPS:
            promoted_gaps.append(
                {
                    "boolean": boolean,
                    "rationale": f"Promoted coverage gap — {gap.get('gap', gap.get('rationale', 'edge-case population'))}",
                    "vocabulary_sources": "coverage_gap",
                }
            )
        else:
            remaining_gaps.append(gap)

    combined = promoted_gaps + list(plan.generated_strings)
    plan.generated_strings = _sort_strings_for_edge_case_opening(combined)
    plan.coverage_gaps = remaining_gaps
    _augment_novelty_metrics(plan)

    canonical_early = sum(
        1
        for item in plan.generated_strings[:8]
        if _opening_priority(item.get("boolean", ""), item.get("rationale", ""))[0] == 2
    )
    return (
        f"promoted {len(promoted_gaps)} edge-case coverage gaps; "
        f"reordered opening to reduce canonical cleanup strings "
        f"(canonical in first 8: {canonical_early})"
    )


def _rebalance_adaptation_for_edge_case_opening(
    adaptation: AdaptationResponse,
    remaining_strings: list[SearchString],
) -> AdaptationResponse:
    adaptation.new_strings = _sort_strings_for_edge_case_opening(adaptation.new_strings)

    remaining_by_id = {ss.id: ss for ss in remaining_strings}
    for reorder in adaptation.reorder:
        if reorder.get("move_to") != "next":
            continue
        ss = remaining_by_id.get(reorder.get("string_id"))
        if not ss:
            continue
        bucket, _score = _opening_priority(ss.boolean, ss.name)
        if bucket == 2:
            reorder["move_to"] = "last"
            reason = reorder.get("reason", "").strip()
            suffix = "Demoted because this is a canonical cleanup string in a tapped market."
            reorder["reason"] = f"{reason} {suffix}".strip()

    return adaptation


# ---------------------------------------------------------------------------
# Strategy formation (run start)
# ---------------------------------------------------------------------------

def form_strategy(
    brief: Brief,
    kit_strings: list[KitString],
    prior_run_data: dict | None = None,
) -> ExecutionPlan:
    """Ask Opus to synthesize compound search strings from kit vocabulary.

    Kit strings are vocabulary — building blocks organized by competency domain.
    Opus uses them to create targeted compound Boolean strings for execution.

    Args:
        brief: Normalized Brief dataclass.
        kit_strings: Boolean vocabulary extracted from the kit.
        prior_run_data: Optional — performance data from a previous run for resume.

    Returns:
        ExecutionPlan with generated compound strings and coverage gaps.
    """
    system = _build_strategy_system(brief, has_kit=bool(kit_strings))
    user_prompt = _build_strategy_user(brief, kit_strings, prior_run_data)

    print("  Strategizing... (Opus is synthesizing compound search strings)")
    try:
        result = opus_llm(system, user_prompt, expect_json=True, max_tokens=16384)
        plan = ExecutionPlan.from_dict(result)
        if _brief_targets_edge_case_opening(brief):
            summary = _rebalance_execution_plan_for_edge_case_opening(plan)
            print(f"  Edge-case rebalance: {summary}")
        plan.original_architecture = plan.architecture  # Set once, never updated on pivot
        if plan.architecture:
            print(f"  Architecture: {plan.architecture} — {plan.architecture_rationale[:120]}")
        print("  Strategy complete.")
        return plan
    except Exception as e:
        # Try to salvage a partial JSON response
        plan = _try_salvage_strategy(e)
        if plan:
            print(f"  [warn] Strategy JSON was truncated — salvaged partial plan", file=sys.stderr)
            return plan

        # Fall back — no kit strings to queue, just an empty plan
        print(f"  [warn] Strategy formation failed ({e}) — no strings to execute", file=sys.stderr)
        return _default_strategy(kit_strings)


def _build_strategy_system(brief: Brief, has_kit: bool = True) -> str:
    noise_section = ""
    if brief.noise_archetypes:
        noise_section = f"\n## Noise Archetypes\n{json.dumps(brief.noise_archetypes, indent=2)}"

    known_noise_section = ""
    if brief.known_noise_patterns:
        known_noise_section = f"\n## Known Noise Patterns\n{json.dumps(brief.known_noise_patterns, indent=2)}"

    key_terms_section = ""
    if brief.key_terms_by_area:
        kt_lines = ["\n## Discriminating Vocabulary by Capability Area"]
        for area, terms in brief.key_terms_by_area.items():
            kt_lines.append(f"- {area}: {', '.join(terms)}")
        kt_lines.append("\nUse these terms as anchors for Type B precision strings. They are the specific technical vocabulary that distinguishes qualified candidates in each area.")
        key_terms_section = "\n".join(kt_lines)

    market_hint = f" Brief specifies: **{brief.market_density}**." if brief.market_density else ""

    return f"""You are a senior sourcing strategist planning a Boolean search execution for LinkedIn Recruiter.

Role: {brief.role_title}
{brief.role_description}

## Minimum Bar
{brief.minimum_bar}

## Archetypes
{json.dumps(brief.archetypes, indent=2)}
{noise_section}
{known_noise_section}
{key_terms_section}

## Permanent Filters
{json.dumps(brief.permanent_filters, indent=2)}

## Stage 0: Select Search Architecture

Before generating any strings, analyze the role and market to select a search ARCHITECTURE. This governs your entire approach — how many strings, what ratio of recall to precision, and how aggressively to filter.

Consider:
1. **Title distinctiveness:** Is the role title specific and reliably used, or ambiguous/variable?
2. **Market vocabulary consistency:** Do practitioners describe themselves consistently, or in many different ways?
3. **Market density:** Large pool (thousands in this geo) or sparse (dozens)?{market_hint}
4. **Company concentration:** Talent concentrated in known companies, or widely distributed?
5. **Noise landscape:** Easier to define what you want, or what you don't want?
6. **Your familiarity:** Strong kit vocabulary for this role, or general JD terms?

Available architectures:

1. **sniper** — Distinctive titles, large market. 15-20 tight strings, 60%+ precision (Type B). Low noise tolerance. Best when: the role title is specific, the market is large enough for exact matches, and false positives are expensive.

2. **dragnet** — Ambiguous titles, inconsistent vocabulary. 10-15 fat OR-group strings, 70%+ recall (Type A). High noise tolerance (up to 70% facial_no acceptable). Best when: practitioners lack standard titles, vocabulary is fragmented, over-include rather than miss people.

3. **titration** — Unknown market. 5-8 broad recon strings first, then 15-20 targeted strings generated at the first block adaptation (after recon data comes back). First block is data collection, not candidate collection. Best when: vocabulary is uncertain, role is novel, or geography is unfamiliar.

4. **negative_space** — Broad pool, easier to define what you DON'T want. 10-15 strings using NOT operators derived from noise_archetypes. Best when: the base pool is huge but contains a large, predictable non-fit population excludable by title/keyword.

5. **company_first** — Talent concentrated in known companies. 10-20 strings organized by company cluster AND skill. Best when: the brief identifies specific employer targets and the employer signal is the key differentiator.

6. **title_first** — Distinctive job title that practitioners actually use. 5-10 strings anchored to exact title phrases. Best when: there IS a standard title specific enough to be a strong filter.

Select ONE architecture and explain your reasoning. Include in your JSON output:
- "architecture": one of "sniper", "dragnet", "titration", "negative_space", "company_first", "title_first"
- "architecture_rationale": Why this architecture fits this role/market (2-3 sentences)
- "architecture_success_criteria": Array of 2-4 measurable criteria (e.g., "save rate > 5% across first block")
- "architecture_pivot_triggers": Array of 2-3 signals that would indicate this architecture is wrong (e.g., ">50% of strings return <20 results")

## Your Task
{"You are given a Search Kit — a library of Boolean search terms organized by competency domain. These kit strings are YOUR VOCABULARY — raw building blocks, NOT executable queries. Do NOT include kit strings directly in the execution queue." if has_kit else "No pre-built search kit is available. You will generate compound Boolean strings directly from the role description, archetypes, JD context, and any sourcing instructions provided."}

Your job: synthesize targeted compound Boolean strings {"by combining terms from multiple kit clusters with domain qualifiers from the brief" if has_kit else "from the role requirements, using LinkedIn-compatible Boolean syntax"}.

### 1. GENERATE compound Boolean strings
{"The kit provides terms organized by skill cluster. This" if has_kit else "This"} role requires an INTERSECTION of skills.
Create compound Boolean strings that AND-gate high-signal terms {"from different kit clusters with" if has_kit else "with"} domain/seniority qualifiers from the brief.

Example compound: ("agentic" OR "LLM agent") AND ("financial services" OR "banking" OR "BFSI") AND ("production" OR "deployment" OR "enterprise")

Generate 15-30 compound strings. You MUST include a mix of TWO string types:

**Type A: Recall strings (10-15 strings)**
Broad searches that surface the general cohort. 500-5000 expected results.
- AND-gate 2-3 clusters: skill terms AND domain terms AND seniority/depth signals
- Keep each clause to 3-6 OR'd terms

**Type B: Precision "sniper" strings (5-15 strings)**
Narrow searches using specific tool names, framework names, benchmark names, or niche technical terms that only genuine practitioners would have on their profile. 20-500 expected results.
- {"Use the kit's Precision cluster terms — specific tools, libraries, benchmarks, methods" if has_kit else "Use specific tool names, framework names, benchmark names, or method-specific terms from the JD and role description"}
- Cross with minimal domain qualifiers (or none — the tool name IS the qualifier)
- Examples of precision signals: specific framework names (Axolotl, vLLM, DeepSpeed), benchmark names (SWE-bench, MMLU, HumanEval), method-specific terms (Constitutional AI, GRPO), infrastructure (TRL, PEFT)
- These strings may return few results but nearly every result is a real practitioner
- {"Look through the kit vocabulary for the most specific, least ambiguous terms and USE them" if has_kit else "Mine the JD for the most specific, least ambiguous terms and USE them"}

Order: alternate between Type A and Type B so precision strings run early, not just as an afterthought.

SEQUENCING — BACKLOAD RL/RLHF STRINGS:
Place strings anchored primarily to RL/RLHF/post-training vocabulary in the SECOND HALF of the execution sequence. Front-load strings targeting other capability areas first (agentic systems, data quality/evaluation, coding agents, STEM/multimodal, embodied AI, general fine-tuning). Rationale:
- RL/RLHF strings surface the densest, most well-trodden talent pool — they will still run, but later
- Thinner capability area pools are faster to work through and surface more net-new candidates per string
- RL practitioners also appear in non-RL strings (someone building RL environments shows up on "simulation" or "agent" strings too — and that incidental RL signal is often stronger than the boilerplate RLHF keyword match)
- By the time RL strings execute, the adaptation loop will have learned from earlier strings' signal/noise patterns, producing more strategic RL searches than the obvious keyword combinations
This is NOT deprioritization — all RL strings still execute. It is sequencing for maximum marginal yield.

### Tapped-Market / Edge-Case Opening (MANDATORY when the brief says the obvious pool is exhausted)

If the brief's instructions or intake notes say the market is tapped, exhausted, or already heavily worked, then your OPENING SEQUENCE must prioritize non-obvious adjacent populations rather than the canonical role vocabulary.

Use this mental loop:
1. First ask: what would a generally solid technical sourcer search if they were doing a competent but standard pass for this role?
2. Then ask: which same-caliber candidates would that standard pass systematically miss because they use different titles, different product language, or sit in adjacent org structures?
3. Generate your opening strings primarily for THOSE missed populations.

For the FIRST 8 strings:
- At least 5 must target edge-case or transfer populations
- Prefer intersections like backend/platform + copilots, internal AI platforms, delivery accelerators, reference architectures, observability/tracing/evals, product/problem-language AI builders, consultancy ICs with build evidence, or vertical SaaS builders
- Do NOT front-load exact-title strings, company-first canonical employer strings, or framework-first strings where a fashionable tool/library name is the main qualifier
- Do NOT front-load broad core strings like ("LLM" OR "GenAI" OR "agentic") AND ("production" OR "deployed") unless they are crossed with a non-obvious adjacent population qualifier

The canonical pool still matters, but it belongs in later cleanup passes once the edge-case populations have been tested.

NOVELTY ACCOUNTING (MANDATORY for tapped markets):
- In a tapped market, productivity alone is not enough. Saves from exact-title FDEs, direct frontier-company pools, and framework-first strings are useful confirmation but LOW-NOVELTY signal.
- Do NOT interpret a high save rate from those canonical pools as proof the opening sequence is correct.
- When you set architecture success criteria and pivot triggers, include at least one metric about novelty or pool mix, not just save rate and result count.

### Architecture-Specific Modifiers

Apply the constraints for your selected architecture. These override ALL default string counts above — both the total count (15-30) and the per-type counts (Type A: 10-15, Type B: 5-15). The ratio below supersedes those base counts:
- **sniper**: 15-20 strings, 60%+ Type B. Tight AND-gates, 20-500 results each.
- **dragnet**: 10-15 strings, 70%+ Type A. Fat OR groups (7+ variants). 500-5000 results. Noise expected.
- **titration**: Only 5-8 broad recon strings for this first block. Hold remaining budget for post-block-1 adaptation when you'll have real data.
- **negative_space**: 10-15 strings with NOT operators from noise_archetypes. Structure: (skills) AND (domain) NOT (noise_title OR noise_keyword).
- **company_first**: 10-20 strings by company cluster, not skill cluster. Company names as primary AND constraints.
- **title_first**: 5-10 strings with exact quoted title phrases. Minimal skill keywords.

Guidelines for all strings:
- {"Pull skill terms from the kit's high-value clusters" if has_kit else "Pull skill terms from the JD's capability areas and technical requirements"}
- Pull domain terms from the brief's archetypes, minimum bar, and role description
- Use LinkedIn-compatible Boolean syntax: parenthetical groups joined by AND

### LinkedIn Search Behavior (MANDATORY — governs every OR group)

LinkedIn Recruiter search has three properties that dictate how you construct every OR group:

1. **Case-insensitive.** "AgentBench" and "agentbench" return identical results. NEVER include case-only variants — they waste OR slots and add zero coverage.

2. **No stemming.** Every character difference is a different search token. "model" does NOT match "models." "fine-tuning" does NOT match "fine-tuned." You MUST include all morphological variants as separate OR terms:
   - Singular AND plural: "reward model" AND "reward models"
   - Base AND past tense: "fine-tuning" AND "fine-tuned"
   - Noun AND gerund: "reward model" AND "reward modeling"
   - Spacing/hyphenation variants: "fine-tuning" AND "fine tuning" AND "finetuning"
   - Common truncations practitioners use: "evals" for "evaluations", "env" for "environment"
   - Acronym + expansion: "RLHF" AND "reinforcement learning from human feedback"
   No penalty for long OR strings — 8 well-chosen variants is better than 3. Every missing variant is a missing candidate.

3. **Substring-embedded.** "reward model" DOES match "reward model development" because the exact character sequence is embedded. NEVER add superstrings of existing terms — they add zero coverage.

### Signal Test (every OR group must pass)

- **Recall groups:** "Does this group anchor me to the right general population for this role?" It should return people plausibly in the right space, even if not all are perfect fits.
  - PASS: ("RLHF" OR "reinforcement learning from human feedback") → returns post-training practitioners
  - FAIL: ("machine learning") → too broad, returns everyone in ML
  - FAIL: ("Python") → returns all of software engineering

- **Precision groups:** "Does this group confirm specific expertise that distinguishes specialists from generalists?"
  - PASS: ("SWE-bench" OR "SWE bench" OR "swebench") → specific benchmark, only builders know it
  - FAIL: ("code" OR "coding") → everyone codes
  - FAIL: ("trajectory") → matches "career trajectory" on every profile

### Disambiguation — No Bare Generic Terms

A bare single-word term with a dominant non-technical meaning on LinkedIn MUST NOT appear in any OR group. Test: if a recruiter pastes this word alone into LinkedIn search, would the majority of results be non-ML? If yes, use only qualified compound forms.

Wrong: ("alignment" OR "AI alignment" OR "model alignment") — bare "alignment" matches organizational alignment, strategic alignment, etc.
Right: ("AI alignment" OR "model alignment" OR "LLM alignment") — every form is qualified.

Common traps: trajectory, episode, agent, alignment, grounding, planning, reflection, oracle, sandbox, rollout, simulation, curriculum, exploration — all have dominant everyday meanings. Use only compound forms: "agent trajectory", "RL episode", "AI agent", "model alignment", etc.

### Abbreviation Collision Filter

An abbreviation MUST NOT appear standalone if it has a more common non-ML meaning on LinkedIn.

- "IPO" → Initial Public Offering. FAIL — use only "identity preference optimization"
- "ORM" → Object-Relational Mapping. FAIL — use only "outcome reward model"
- "CAI" → various non-ML meanings. FAIL — use only "constitutional AI"
- "PPO" → Preferred Provider Organization. Borderline — "proximal policy optimization" is safer
- "RLHF" → No dominant non-ML meaning. PASS.
- "DPO" → Data Protection Officer in some markets. Acceptable if paired with expansion: ("DPO" OR "direct preference optimization")

Rule: an abbreviation that fails alone IS acceptable when paired with its full expansion in the same OR group.

### Blacklist — NEVER Include

**Universal infrastructure:** PyTorch, TensorFlow, JAX, Keras, Docker, Kubernetes, AWS, GCP, Azure, Spark, Airflow, Kafka, Redis, PostgreSQL, MongoDB, Git, GitHub, pandas, NumPy, SciPy, scikit-learn

**Universal ML:** machine learning, deep learning, neural network, gradient descent, backpropagation, cross-validation, hyperparameter, training (alone), inference (alone), model (alone), transformer (alone), encoder, decoder

**Generic software:** CI/CD, GitHub Actions, Jenkins, unit testing, code review, API integration, microservices, REST, GraphQL

**User tools (not builder tools):** GitHub Copilot, Cursor, ChatGPT, Claude (product), Gemini, LangChain, LlamaIndex, AutoGPT, BabyAGI

**Buzzwords:** AI-powered, intelligent automation, cutting-edge, generative AI (alone), autonomous (alone), automation (alone), data-driven, next-generation

### Tool/Library Names Are Proper Nouns

Do NOT fabricate compound expansions for tool names. No practitioner writes "playwright automation" or "MuJoCo physics" on their profile.

Valid expansions: package/repo names ("mujoco-py", "axolotl-ai"), version identifiers ("SWE-bench Lite"), known alternate names ("OpenDevin" for OpenHands), spacing/hyphenation variants ("SWE-bench" / "SWE bench" / "swebench").

A single-term group is valid. If a tool has no variants, the group is just ("Tianshou") and that is correct.

### Mandatory Self-Review Before Output

Execute these checks on every OR group in your output:

1. **Case dedup:** Do any two terms differ ONLY by capitalization? Delete one.
2. **Disambiguation:** Any bare single-word terms that fail the recruiter-paste test? Replace with compound forms.
3. **Abbreviation check:** Any standalone abbreviations with non-ML meanings without their expansion paired? Remove or expand.
4. **Lexical expansion:** Does each group include all necessary variants — singular/plural, base/past tense, noun/gerund, spacing/hyphenation, common truncations? Every missing variant is a missing candidate. But never add superstrings (substring embedding handles those). Tool names are proper nouns — do not invent variants.

### 2. IDENTIFY coverage gaps
What candidate populations {"does the kit vocabulary NOT reach" if has_kit else "might your generated strings miss"}? Examples:
- People who describe their work differently {"than the kit's terminology" if has_kit else "than the JD's terminology"}
- Adjacent skill sets {"not represented in any kit block" if has_kit else "not covered by your generated strings"}
- Domain-specific terms the kit misses
- Title patterns or employer patterns that could surface candidates

For each gap, provide a ready-to-execute Boolean string if possible.

### 3. PREDICT noise collisions
Based on the vocabulary and this geography/role, predict which terms will produce noise and what the collision patterns will be.

IMPORTANT: Each string you generate is a NET — it catches whoever matches the Boolean, regardless of archetype.
A string built from post-training vocabulary might surface a STEM reasoning engineer or an RL environment builder.
That's good. The evaluator downstream judges every candidate against ALL archetypes, not just the one the string was "designed for."
Your strings are search tools, not archetype filters. Label them descriptively but do NOT treat them as archetype-scoped.

Return JSON with this structure:
- "architecture": Your selected architecture (string — one of the six listed above)
- "architecture_rationale": Why this architecture fits (string)
- "architecture_success_criteria": Array of 2-4 measurable success criteria (array of strings)
- "architecture_pivot_triggers": Array of 2-3 pivot trigger signals (array of strings)
- "strategy_rationale": Overall strategy explanation (string)
- "generated_strings": Array of compound strings to execute, in priority order. Each object:
  - "boolean": The full Boolean string (string)
  - "rationale": Why this compound is likely to surface strong candidates for the role (string)
  - "vocabulary_sources": {"Which kit blocks/clusters the terms come from" if has_kit else "Which JD sections or capability areas the terms derive from"} (string) — this is for traceability only, NOT for scoping evaluation
- "coverage_gaps": Array of gaps identified. Each object:
  - "gap": Description of the missing coverage (string)
  - "suggested_boolean": Optional Boolean string to fill the gap, or null (string|null)
  - "rationale": Why this population matters for this role (string)
- "noise_predictions": Array of objects with "term" (string), "expected_collision" (string), "mitigation" (string)

Return valid JSON only."""


def _build_strategy_user(
    brief: Brief,
    kit_strings: list[KitString],
    prior_run_data: dict | None = None,
) -> str:
    # Group kit strings by block for clearer vocabulary presentation
    blocks: dict[str, list[KitString]] = {}
    for ks in kit_strings:
        blocks.setdefault(ks.block, []).append(ks)

    vocab_text = ""
    for block_name, strings in blocks.items():
        vocab_text += f"\n### {block_name}\n"
        for ks in strings:
            vocab_text += f"  [{ks.subblock} / {ks.string_type}]: {ks.boolean}\n"

    if kit_strings:
        prompt = f"""## Boolean Search Vocabulary ({len(kit_strings)} terms across {len(blocks)} competency blocks)
These are your raw building blocks. Combine terms from multiple blocks to create targeted compound searches.
{vocab_text}
"""
    else:
        prompt = """## No Kit Vocabulary Available
No pre-built search kit was provided. Generate compound Boolean strings directly from
the role description, archetypes, and JD context below. Apply all LinkedIn Boolean rules.
"""

    # Include JD text if available (supplementary context for string generation)
    if brief.jd_text:
        prompt += f"\n## Job Description (source material for search vocabulary)\n{brief.jd_text}\n"

    if brief.intake_notes:
        prompt += f"\n## Intake Notes\n{brief.intake_notes}\n"

    if prior_run_data:
        prompt += f"\n## Prior Run Data\n{json.dumps(prior_run_data, indent=2)}\n"

        if prior_run_data.get("noise_discoveries"):
            noise_text = "\n## Noise Patterns Discovered in Prior Sessions\n"
            for nd in prior_run_data["noise_discoveries"]:
                noise_text += f"- {nd['term']}: [{nd['status']}] {nd.get('note', '')}\n"
            noise_text += "\nAvoid generating strings that primarily target confirmed_noise patterns.\n"
            prompt += noise_text

    if brief.search_priorities:
        prompt += f"\n## User Hints\nSearch priorities: {', '.join(brief.search_priorities)}\n"

    if brief.additional_search_terms:
        prompt += f"\n## Additional Search Terms\nThese terms should be used for search string generation but are NOT evaluation criteria:\n{', '.join(brief.additional_search_terms)}\n"

    if brief.instructions:
        prompt += f"\n## Sourcing Instructions\n" + "\n".join(f"- {i}" for i in brief.instructions) + "\n"

    prompt += "\nSynthesize compound search strings" + (" from this vocabulary." if kit_strings else " from the JD and role context.")
    return prompt


def _try_salvage_strategy(original_error: Exception) -> ExecutionPlan | None:
    """Try to salvage a partial strategy from a truncated JSON response."""
    err_msg = str(original_error)
    # Look for partial JSON in the error message
    for start_char, end_char in [("{", "}"), ("[", "]")]:
        start = err_msg.find(start_char)
        if start == -1:
            continue
        # Walk backwards from the end, trying progressively shorter substrings
        text = err_msg[start:]
        for i in range(len(text) - 1, 0, -1):
            if text[i] == end_char:
                try:
                    data = json.loads(text[: i + 1])
                    if isinstance(data, dict):
                        return ExecutionPlan.from_dict(data)
                except json.JSONDecodeError:
                    continue
    return None


def _default_strategy(kit_strings: list[KitString]) -> ExecutionPlan:
    """Return an empty plan when strategy formation fails.

    Kit strings are vocabulary only — they are never queued directly.
    Without Opus-generated compounds, there are no strings to execute.
    """
    return ExecutionPlan(
        strategy_rationale="Strategy formation failed — no compound strings generated. Re-run to retry.",
        noise_predictions=[],
        generated_strings=[],
        coverage_gaps=[],
    )


# ---------------------------------------------------------------------------
# Adaptation after block completion
# ---------------------------------------------------------------------------

def adapt_after_block(
    brief: Brief,
    block_report: BlockReport,
    remaining_strings: list[SearchString],
    kit_vocabulary: list[KitString] | None = None,
    execution_plan: ExecutionPlan | None = None,
    pivot_count: int = 0,
    block_aggregate: str = "",
) -> AdaptationResponse:
    """Ask Opus to adapt after a block completes — generate new strings from vocabulary.

    Args:
        brief: Normalized Brief dataclass.
        block_report: Summary of the completed block's performance.
        remaining_strings: SearchStrings not yet executed (generated compounds still queued).
        kit_vocabulary: Full kit vocabulary available for synthesizing new strings.
        execution_plan: Current execution plan (for architecture context).
        pivot_count: Number of architecture pivots already used this run.

    Returns:
        AdaptationResponse with new strings, skips, reorders, noise updates, optional pivot.
    """
    # Build vocabulary section if available
    vocab_section = ""
    if kit_vocabulary:
        blocks: dict[str, list[KitString]] = {}
        for ks in kit_vocabulary:
            blocks.setdefault(ks.block, []).append(ks)
        vocab_lines = []
        for block_name, strings in blocks.items():
            vocab_lines.append(f"### {block_name}")
            for ks in strings:
                vocab_lines.append(f"  [{ks.subblock} / {ks.string_type}]: {ks.boolean}")
        vocab_section = "\n".join(vocab_lines)

    # Build architecture review section
    arch_review = ""
    if execution_plan and execution_plan.architecture:
        max_pivots = 2 if execution_plan.original_architecture == "titration" else 1
        pivots_remaining = max(0, max_pivots - pivot_count)
        criteria_text = "\n".join(f"  - {c}" for c in execution_plan.architecture_success_criteria) or "  (none set)"
        triggers_text = "\n".join(f"  - {t}" for t in execution_plan.architecture_pivot_triggers) or "  (none set)"
        pivot_note = f"\nNOTE: No pivots remaining. You cannot recommend an architecture change." if pivots_remaining == 0 else ""
        arch_review = f"""

## Architecture Review

Current architecture: {execution_plan.architecture}
Rationale: {execution_plan.architecture_rationale}

Success criteria:
{criteria_text}

Pivot triggers:
{triggers_text}

Pivots remaining this run: {pivots_remaining}

Based on the block report, evaluate whether the current architecture is meeting its success criteria.
If any pivot triggers are firing, you MAY recommend switching architectures by including:
- "pivot_to_architecture": the new architecture name (one of: sniper, dragnet, titration, negative_space, company_first, title_first)
- "pivot_rationale": detailed explanation of why the current approach failed and why the new one will work

A pivot clears remaining queued strings and replaces them with your new_strings (generated under the new architecture). Only recommend when evidence is clear.{pivot_note}"""

    system = f"""You are a sourcing strategist adapting a search plan mid-run.

Role: {brief.role_title}
{brief.role_description}

You've just received a report on a batch of completed Boolean searches. Based on the results:
1. Generate NEW compound Boolean strings that target signal patterns you observed — use the kit vocabulary below as building blocks
2. Identify remaining queued strings to skip (redundant, similar to zero-save strings)
3. Suggest reordering of remaining queued strings based on observed signal
4. Update noise pattern knowledge

IMPORTANT: Each Boolean string is a NET that catches candidates for ANY archetype, not just one.
A string built from post-training terms might surface a STEM reasoning engineer. That's expected and good.
Evaluate string productivity by total saves across ALL archetypes, not just the archetype the string was "designed for."

When generating new strings, combine terms from the kit vocabulary with domain qualifiers. The most valuable new strings will target the specific intersection of skills and domain this role requires.

Include BOTH broad recall strings AND narrow precision "sniper" strings that use specific tool/framework/benchmark names from the kit vocabulary — terms only real practitioners would have on their profiles.

If the brief says the obvious pool is tapped, prefer generating new strings that expand productive edge-case populations before emitting direct framework-name cleanup strings or exact-title cleanup strings.

When adapting, continue using the same loop: identify what a standard sourcer would search next, then push one layer outward toward adjacent but same-caliber populations that the standard next step would still miss.

In tapped markets, evaluate BLOCK QUALITY on two axes:
1. productivity: saves, facial pass rate, result quality
2. novelty: whether the saves came from adjacent populations versus exact-title FDEs, framework-first strings, or canonical frontier-company pools

If a string is productive but mostly confirms the obvious pool, treat it as cleanup signal, not as the template for what should come next. In that case:
- prefer reordering similar queued strings later
- prefer generating adjacent expansions instead of "more of the same"
- recommend a pivot if the opening sequence is succeeding only in low-novelty pools

## LinkedIn Boolean Rules (MANDATORY)
- LinkedIn does NOT stem: "model" ≠ "models" — include all morphological variants
- LinkedIn IS substring-embedded: "reward model" matches "reward model development" — never add superstrings
- LinkedIn IS case-insensitive: never add case-only variants
- Bare ambiguous terms MUST be qualified: "agent" → "AI agent"
- Abbreviations with non-domain meanings must include spelled-out form
- Tool/library names are proper nouns — do not fabricate compound expansions
{block_aggregate}
{arch_review}

Return JSON with this structure:
- "new_strings": Array of objects with "boolean" (string), "rationale" (string)
- "skip_remaining": Array of objects with "string_id" (int), "reason" (string)
- "reorder": Array of objects with "string_id" (int), "move_to" ("next" | "last"), "reason" (string)
- "noise_updates": Array of objects with "term" (string), "status" ("confirmed_signal" | "confirmed_noise" | "mixed"), "note" (string)
- "pivot_to_architecture": (optional) New architecture name if recommending a pivot (string)
- "pivot_rationale": (optional) Why the current architecture failed and why the new one will work (string)

Return valid JSON only."""

    remaining_text = ""
    for ss in remaining_strings:
        remaining_text += f"  #{ss.id}: {ss.boolean[:200]}\n"

    user_prompt = f"""{block_report.to_summary_text()}

## Remaining Queued Strings ({len(remaining_strings)})
{remaining_text}
"""
    if vocab_section:
        user_prompt += f"""
## Kit Vocabulary (building blocks for new strings)
{vocab_section}
"""

    user_prompt += "\nSuggest adaptations."

    result = opus_llm(system, user_prompt, expect_json=True)
    adaptation = AdaptationResponse.from_dict(result)
    if _brief_targets_edge_case_opening(brief):
        adaptation = _rebalance_adaptation_for_edge_case_opening(adaptation, remaining_strings)
    return adaptation
