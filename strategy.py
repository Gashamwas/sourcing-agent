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
import sys
from schemas import KitString, ExecutionPlan, BlockReport, AdaptationResponse, SearchString
from llm_clients import opus_llm
from brief_loader import Brief


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
    system = _build_strategy_system(brief)
    user_prompt = _build_strategy_user(brief, kit_strings, prior_run_data)

    print("  Strategizing... (Opus is synthesizing compound search strings)")
    try:
        result = opus_llm(system, user_prompt, expect_json=True, max_tokens=16384)
        plan = ExecutionPlan.from_dict(result)
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


def _build_strategy_system(brief: Brief) -> str:
    noise_section = ""
    if brief.noise_archetypes:
        noise_section = f"\n## Noise Archetypes\n{json.dumps(brief.noise_archetypes, indent=2)}"

    known_noise_section = ""
    if brief.known_noise_patterns:
        known_noise_section = f"\n## Known Noise Patterns\n{json.dumps(brief.known_noise_patterns, indent=2)}"

    return f"""You are a senior sourcing strategist planning a Boolean search execution for LinkedIn Recruiter.

Role: {brief.role_title}
{brief.role_description}

## Minimum Bar
{brief.minimum_bar}

## Archetypes
{json.dumps(brief.archetypes, indent=2)}
{noise_section}
{known_noise_section}

## Permanent Filters
{json.dumps(brief.permanent_filters, indent=2)}

## Your Task
You are given a Search Kit — a library of Boolean search terms organized by competency domain.
These kit strings are YOUR VOCABULARY — raw building blocks, NOT executable queries.
Do NOT include kit strings directly in the execution queue.

Your job: synthesize targeted compound Boolean strings by combining terms from multiple kit clusters with domain qualifiers from the brief.

### 1. GENERATE compound Boolean strings
The kit provides terms organized by skill cluster. This role requires an INTERSECTION of skills.
Create compound Boolean strings that AND-gate high-signal terms from different kit clusters with domain/seniority qualifiers from the brief.

Example compound: ("agentic" OR "LLM agent") AND ("financial services" OR "banking" OR "BFSI") AND ("production" OR "deployment" OR "enterprise")

Generate 10-25 compound strings, ordered from highest to lowest expected signal density.

Guidelines for compound generation:
- AND-gate 2-3 clusters: skill terms AND domain terms AND seniority/depth signals
- Pull skill terms from the kit's high-value clusters
- Pull domain terms from the brief's archetypes, minimum bar, and role description
- Keep each clause to 3-6 OR'd terms to avoid over-constraining
- Use LinkedIn-compatible Boolean syntax: parenthetical groups joined by AND
- Start with the tightest, most specific compounds (highest precision)
- Progress to broader compounds that sacrifice precision for recall

### 2. IDENTIFY coverage gaps
What candidate populations does the kit vocabulary NOT reach? Examples:
- People who describe their work differently than the kit's terminology
- Adjacent skill sets not represented in any kit block
- Domain-specific terms the kit misses
- Title patterns or employer patterns that could surface candidates

For each gap, provide a ready-to-execute Boolean string if possible.

### 3. PREDICT noise collisions
Based on the vocabulary and this geography/role, predict which terms will produce noise and what the collision patterns will be.

Return JSON with this structure:
- "strategy_rationale": Overall strategy explanation (string)
- "generated_strings": Array of compound strings to execute, in priority order. Each object:
  - "boolean": The full Boolean string (string)
  - "rationale": Why this compound targets the role's intersection (string)
  - "source_clusters": Which kit blocks/clusters the terms come from (string)
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

    prompt = f"""## Boolean Search Vocabulary ({len(kit_strings)} terms across {len(blocks)} competency blocks)
These are your raw building blocks. Combine terms from multiple blocks to create targeted compound searches.
{vocab_text}
"""
    if prior_run_data:
        prompt += f"\n## Prior Run Data\n{json.dumps(prior_run_data, indent=2)}\n"

    if brief.search_priorities:
        prompt += f"\n## User Hints\nSearch priorities: {', '.join(brief.search_priorities)}\n"

    prompt += "\nSynthesize compound search strings from this vocabulary."
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
) -> AdaptationResponse:
    """Ask Opus to adapt after a block completes — generate new strings from vocabulary.

    Args:
        brief: Normalized Brief dataclass.
        block_report: Summary of the completed block's performance.
        remaining_strings: SearchStrings not yet executed (generated compounds still queued).
        kit_vocabulary: Full kit vocabulary available for synthesizing new strings.

    Returns:
        AdaptationResponse with new strings, skips, reorders, noise updates.
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

    system = f"""You are a sourcing strategist adapting a search plan mid-run.

Role: {brief.role_title}
{brief.role_description}

You've just received a report on a completed block of Boolean searches. Based on the results:
1. Generate NEW compound Boolean strings that target signal patterns you observed — use the kit vocabulary below as building blocks
2. Identify remaining queued strings to skip (redundant, similar to zero-save strings)
3. Suggest reordering of remaining queued strings based on observed signal
4. Update noise pattern knowledge

When generating new strings, combine terms from the kit vocabulary with domain qualifiers. The most valuable new strings will target the specific intersection of skills and domain this role requires.

Return JSON with this structure:
- "new_strings": Array of objects with "boolean" (string), "rationale" (string)
- "skip_remaining": Array of objects with "string_id" (int), "reason" (string)
- "reorder": Array of objects with "string_id" (int), "move_to" ("next" | "last"), "reason" (string)
- "noise_updates": Array of objects with "term" (string), "status" ("confirmed_signal" | "confirmed_noise" | "mixed"), "note" (string)

Return valid JSON only."""

    remaining_text = ""
    for ss in remaining_strings:
        remaining_text += f"  #{ss.id} [{ss.block}]: {ss.boolean[:100]}\n"

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

    return AdaptationResponse.from_dict(result)
