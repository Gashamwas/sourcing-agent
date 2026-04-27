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
from shared.schemas import KitString, ExecutionPlan, BlockReport, AdaptationResponse, SearchString
from shared.llm_clients import opus_llm
from shared.brief_loader import Brief
from shared.retrieval_design import (
    RetrievalDesign,
    render_retrieval_design,
    summarize_retrieval_design,
)
from shared.search_memory import (
    format_search_memory_summary,
    get_search_memory_families,
    infer_domain_lane,
    normalize_family_key,
    normalize_novelty_bucket,
)
from shared.strict_seniority import (
    classify_search_string_seniority,
    is_strict_seniority_brief,
)


_MAX_PROMOTED_EDGE_CASE_GAPS = 3


def _iter_brief_patterns(brief: Brief, attr: str) -> tuple[str, ...]:
    """Return the lowercased non-empty patterns under ``attr`` on the compat brief."""
    values = getattr(brief, attr, None) or ()
    return tuple(
        str(value).strip().lower()
        for value in values
        if str(value or "").strip()
    )


def _design_from_brief(brief: Brief) -> RetrievalDesign:
    return RetrievalDesign.from_dict(getattr(brief, "retrieval_design", {}) or {})


def _explicit_design_from_brief(brief: Brief) -> RetrievalDesign:
    design = _design_from_brief(brief)
    if design.is_explicit():
        return design
    return RetrievalDesign()


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


def _opening_priority(brief: Brief, boolean: str, rationale: str = "") -> tuple[int, int]:
    """Classify how suitable a string is for an edge-case opening sequence.

    The classification draws its vocabulary entirely from the calibration
    mirror on the compat ``Brief`` (canonical_*_patterns, edge_case_patterns,
    edge_case_company_patterns). When those mirrors are empty the function
    degrades to ``(1, 0)`` for every input — neutral / mixed.

    Returns (bucket, score):
      bucket 0 = edge-case / adjacent opening string
      bucket 1 = neutral / mixed
      bucket 2 = canonical cleanup string
    """
    text = f"{boolean} {rationale}".lower()

    framework_patterns = _iter_brief_patterns(brief, "canonical_framework_patterns")
    company_patterns = _iter_brief_patterns(brief, "canonical_company_patterns")
    title_patterns = _iter_brief_patterns(brief, "canonical_title_patterns")
    broad_patterns = _iter_brief_patterns(brief, "canonical_broad_patterns")
    edge_patterns = _iter_brief_patterns(brief, "edge_case_patterns")
    edge_company_patterns = _iter_brief_patterns(brief, "edge_case_company_patterns")

    framework_hits = sum(1 for pattern in framework_patterns if pattern in text)
    company_hits = sum(1 for pattern in company_patterns if pattern in text)
    title_hits = sum(1 for pattern in title_patterns if pattern in text)
    broad_hits = sum(1 for pattern in broad_patterns if pattern in text)
    edge_hits = sum(1 for pattern in edge_patterns if pattern in text)
    edge_hits += sum(1 for pattern in edge_company_patterns if pattern in text)

    framework_first = framework_hits >= 2 and edge_hits == 0
    company_first = company_hits >= 2 and edge_hits == 0
    title_first = title_hits >= 1 and edge_hits == 0
    broad_core = broad_hits >= 2 and edge_hits == 0

    canonical = framework_first or company_first or title_first or broad_core
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
    )
    return bucket, score


def _sort_strings_for_edge_case_opening(brief: Brief, strings: list[dict]) -> list[dict]:
    annotated: list[tuple[tuple[int, int, int], dict]] = []
    for idx, item in enumerate(strings):
        bucket, score = _opening_priority(
            brief,
            item.get("boolean", ""),
            item.get("rationale", "") or item.get("gap", ""),
        )
        annotated.append(((bucket, -score, idx), item))
    annotated.sort(key=lambda pair: pair[0])
    return [item for _, item in annotated]


def _annotate_string_metadata(
    brief: Brief,
    item: dict,
    *,
    boolean_key: str = "boolean",
) -> dict:
    """Ensure generated strings carry stable family/novelty/domain labels."""
    boolean = item.get(boolean_key, "") or ""
    rationale = item.get("rationale", "") or item.get("gap", "") or ""
    bucket, _score = _opening_priority(brief, boolean, rationale)
    retrieval_recipe = item.get("retrieval_recipe", {}) if isinstance(item.get("retrieval_recipe"), dict) else {}
    hypothesis_ids = [
        str(hypothesis_id).strip()
        for hypothesis_id in retrieval_recipe.get("applied_hypothesis_ids", [])
        if str(hypothesis_id).strip()
    ]

    item["family_key"] = normalize_family_key(
        item.get("family_key") or retrieval_recipe.get("family_id"),
        boolean,
        rationale,
    )
    item["novelty_bucket"] = normalize_novelty_bucket(
        item.get("novelty_bucket")
        or ("edge_case" if hypothesis_ids or bucket == 0 else "canonical"),
        boolean,
        rationale,
        brief=brief,
    )
    item["domain_lane"] = infer_domain_lane(
        item.get("domain_lane")
        or retrieval_recipe.get("target_markets", [None])[0],
        boolean,
        rationale,
        brief=brief,
    )
    seniority = classify_search_string_seniority(
        boolean,
        rationale,
        domain_lane=item["domain_lane"],
    )
    item["seniority_risk"] = seniority["seniority_risk"]
    item["title_bucket_risk"] = seniority["title_bucket_risk"]
    item["opening_eligible"] = bool(seniority["opening_eligible"])
    if retrieval_recipe:
        item["retrieval_recipe"] = retrieval_recipe
    if hypothesis_ids:
        item["retrieval_hypothesis_ids"] = hypothesis_ids
    return item


def _materialize_retrieval_plan(
    plan: ExecutionPlan,
    *,
    base_design: RetrievalDesign | None = None,
    prefer_rendered_strings: bool = False,
) -> None:
    if not plan.retrieval_families:
        return
    design_payload = (base_design.to_dict() if base_design else {})
    design_payload["families"] = plan.retrieval_families
    rendered_design = RetrievalDesign.from_dict(design_payload)
    rendered_families, rendered_strings = render_retrieval_design(rendered_design)
    if rendered_families:
        plan.retrieval_families = rendered_families
    if not rendered_strings:
        return
    if not prefer_rendered_strings and plan.generated_strings:
        return

    merged: list[dict] = []
    seen_booleans: set[str] = set()
    for item in rendered_strings + list(plan.generated_strings):
        boolean = str(item.get("boolean", "")).strip()
        if not boolean:
            continue
        key = boolean.lower()
        if key in seen_booleans:
            continue
        seen_booleans.add(key)
        merged.append(item)
    plan.generated_strings = merged


def _materialize_retrieval_adaptation(
    adaptation: AdaptationResponse,
    *,
    base_design: RetrievalDesign | None = None,
    prefer_rendered_strings: bool = False,
) -> None:
    if not adaptation.new_retrieval_families:
        return
    design_payload = (base_design.to_dict() if base_design else {})
    design_payload["families"] = adaptation.new_retrieval_families
    rendered_design = RetrievalDesign.from_dict(design_payload)
    _rendered_families, rendered_strings = render_retrieval_design(rendered_design)
    if rendered_strings and (prefer_rendered_strings or not adaptation.new_strings):
        adaptation.new_strings = rendered_strings + list(adaptation.new_strings)


def _annotate_plan_metadata(brief: Brief, plan: ExecutionPlan) -> None:
    plan.generated_strings = [
        _annotate_string_metadata(brief, dict(item))
        for item in plan.generated_strings
    ]

    annotated_gaps = []
    for gap in plan.coverage_gaps:
        gap_item = dict(gap)
        if gap_item.get("suggested_boolean"):
            gap_item = _annotate_string_metadata(
                brief, gap_item, boolean_key="suggested_boolean"
            )
        annotated_gaps.append(gap_item)
    plan.coverage_gaps = annotated_gaps


def _annotate_adaptation_metadata(brief: Brief, adaptation: AdaptationResponse) -> None:
    adaptation.new_strings = [
        _annotate_string_metadata(brief, dict(item))
        for item in adaptation.new_strings
    ]


def _strict_seniority_opening_sort_key(item: dict, idx: int) -> tuple[int, int, int, int, int, int]:
    lane = str(item.get("domain_lane", "") or "").strip().lower()
    preferred_lane_rank = {
        "capital_markets": 0,
        "market_infra": 1,
        "market_data": 2,
        "risk_compliance": 3,
        "bfsi_vendors": 4,
        "general": 5,
        "asset_management": 6,
        "payments": 7,
        "insurance": 8,
    }.get(lane, 9)
    novelty_rank = 0 if item.get("novelty_bucket") == "edge_case" else 1
    title_risk_rank = {"low": 0, "medium": 1, "high": 2}.get(
        str(item.get("title_bucket_risk", "low")).lower(),
        0,
    )
    seniority_risk_rank = {"low": 0, "medium": 1, "high": 2}.get(
        str(item.get("seniority_risk", "low")).lower(),
        0,
    )
    return (
        0 if item.get("opening_eligible", True) else 1,
        0 if (lane in {"capital_markets", "market_infra", "market_data", "risk_compliance"} or "executive director" in str(item.get("boolean", "")).lower()) else 1,
        preferred_lane_rank,
        title_risk_rank,
        seniority_risk_rank,
        idx,
    )


def _apply_strict_seniority_plan_guardrails(brief: Brief, plan: ExecutionPlan) -> str:
    if not is_strict_seniority_brief(brief):
        return ""

    kept: list[dict] = []
    suppressed: list[dict] = []
    for item in plan.generated_strings:
        if (
            item.get("title_bucket_risk") == "high"
            and not item.get("opening_eligible", True)
        ):
            suppressed.append(item)
            continue
        kept.append(item)

    if suppressed and (len(kept) >= 3 or len(kept) >= max(1, len(plan.generated_strings) // 2)):
        plan.generated_strings = kept
    else:
        suppressed = []

    plan.generated_strings = [
        item
        for _, item in sorted(
            enumerate(plan.generated_strings),
            key=lambda pair: _strict_seniority_opening_sort_key(pair[1], pair[0]),
        )
    ]

    if plan.coverage_gaps:
        reordered_gaps = []
        for idx, gap in enumerate(plan.coverage_gaps):
            if not gap.get("suggested_boolean"):
                reordered_gaps.append((idx, gap))
                continue
            risk = classify_search_string_seniority(
                gap.get("suggested_boolean", ""),
                gap.get("rationale", "") or gap.get("gap", ""),
                domain_lane=gap.get("domain_lane", ""),
            )
            gap["seniority_risk"] = risk["seniority_risk"]
            gap["title_bucket_risk"] = risk["title_bucket_risk"]
            gap["opening_eligible"] = risk["opening_eligible"]
            reordered_gaps.append((idx, gap))
        plan.coverage_gaps = [
            gap
            for _, gap in sorted(
                reordered_gaps,
                key=lambda pair: _strict_seniority_opening_sort_key(pair[1], pair[0]),
            )
        ]

    if not suppressed:
        return ""
    return f"strict-seniority lint suppressed {len(suppressed)} broad title-bucket strings"


def _apply_strict_seniority_adaptation_guardrails(
    brief: Brief,
    adaptation: AdaptationResponse,
    remaining_strings: list[SearchString],
) -> str:
    if not is_strict_seniority_brief(brief):
        return ""

    kept: list[dict] = []
    suppressed = 0
    for item in adaptation.new_strings:
        if (
            item.get("title_bucket_risk") == "high"
            and not item.get("opening_eligible", True)
        ):
            suppressed += 1
            continue
        kept.append(item)
    adaptation.new_strings = [
        item
        for _, item in sorted(
            enumerate(kept),
            key=lambda pair: _strict_seniority_opening_sort_key(pair[1], pair[0]),
        )
    ]

    remaining_by_id = {ss.id: ss for ss in remaining_strings}
    for reorder in adaptation.reorder:
        if reorder.get("move_to") != "next":
            continue
        ss = remaining_by_id.get(reorder.get("string_id"))
        if not ss:
            continue
        if ss.opening_eligible is False or ss.title_bucket_risk == "high":
            reorder["move_to"] = "last"
            reason = reorder.get("reason", "").strip()
            suffix = "Demoted by strict-seniority guardrail because this string uses a broad title bucket."
            reorder["reason"] = f"{reason} {suffix}".strip()

    if suppressed == 0:
        return ""
    return f"strict-seniority lint suppressed {suppressed} adaptive broad title-bucket strings"


def _apply_search_memory_to_plan(
    plan: ExecutionPlan,
    search_memory: dict | None,
) -> str:
    """Demote exhausted search families so prior overlap does not lead the run again."""
    family_records = get_search_memory_families(search_memory)
    if not family_records:
        return ""

    family_status = {
        family.get("family_key", ""): family
        for family in family_records
    }
    annotated: list[tuple[tuple[int, int], dict]] = []
    demoted = 0

    for idx, item in enumerate(plan.generated_strings):
        family = family_status.get(item.get("family_key", ""), {})
        exhausted = family.get("status") == "exhausted"
        if exhausted:
            demoted += 1
        annotated.append(
            (
                (
                    1 if exhausted else 0,
                    idx,
                ),
                item,
            )
        )

    annotated.sort(key=lambda pair: pair[0])
    plan.generated_strings = [item for _, item in annotated]
    if demoted == 0:
        return ""
    return f"demoted {demoted} strings from exhausted families"


def _apply_search_memory_to_adaptation(
    adaptation: AdaptationResponse,
    remaining_strings: list[SearchString],
    search_memory: dict | None,
) -> None:
    family_records = get_search_memory_families(search_memory)
    if not family_records:
        return

    family_status = {
        family.get("family_key", ""): family
        for family in family_records
    }

    adaptation.new_strings.sort(
        key=lambda item: (
            1
            if family_status.get(item.get("family_key", ""), {}).get("status") == "exhausted"
            else 0,
            0 if item.get("novelty_bucket") == "edge_case" else 1,
        )
    )

    remaining_by_id = {ss.id: ss for ss in remaining_strings}
    for reorder in adaptation.reorder:
        if reorder.get("move_to") != "next":
            continue
        ss = remaining_by_id.get(reorder.get("string_id"))
        if not ss:
            continue
        family = family_status.get(ss.family_key or "", {})
        if family.get("status") == "exhausted":
            reorder["move_to"] = "last"
            reason = reorder.get("reason", "").strip()
            suffix = "Demoted because this family is exhausted from prior runs."
            reorder["reason"] = f"{reason} {suffix}".strip()


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


def _rebalance_execution_plan_for_edge_case_opening(brief: Brief, plan: ExecutionPlan) -> str:
    """Promote edge-case coverage gaps and demote canonical opening strings."""
    promoted_gaps: list[dict] = []
    remaining_gaps: list[dict] = []

    for gap in plan.coverage_gaps:
        boolean = gap.get("suggested_boolean")
        if not boolean:
            remaining_gaps.append(gap)
            continue

        bucket, score = _opening_priority(
            brief, boolean, f"{gap.get('gap', '')} {gap.get('rationale', '')}"
        )
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
    plan.generated_strings = _sort_strings_for_edge_case_opening(brief, combined)
    plan.coverage_gaps = remaining_gaps
    _augment_novelty_metrics(plan)

    canonical_early = sum(
        1
        for item in plan.generated_strings[:8]
        if _opening_priority(brief, item.get("boolean", ""), item.get("rationale", ""))[0] == 2
    )
    return (
        f"promoted {len(promoted_gaps)} edge-case coverage gaps; "
        f"reordered opening to reduce canonical cleanup strings "
        f"(canonical in first 8: {canonical_early})"
    )


def _rebalance_adaptation_for_edge_case_opening(
    brief: Brief,
    adaptation: AdaptationResponse,
    remaining_strings: list[SearchString],
) -> AdaptationResponse:
    adaptation.new_strings = _sort_strings_for_edge_case_opening(brief, adaptation.new_strings)

    remaining_by_id = {ss.id: ss for ss in remaining_strings}
    for reorder in adaptation.reorder:
        if reorder.get("move_to") != "next":
            continue
        ss = remaining_by_id.get(reorder.get("string_id"))
        if not ss:
            continue
        bucket, _score = _opening_priority(brief, ss.boolean, ss.name)
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
    explicit_design = _explicit_design_from_brief(brief)
    use_layered_retrieval = explicit_design.is_explicit()
    system = _build_strategy_system(
        brief,
        has_kit=bool(kit_strings),
        use_layered_retrieval=use_layered_retrieval,
    )
    user_prompt = _build_strategy_user(
        brief,
        kit_strings,
        prior_run_data,
        use_layered_retrieval=use_layered_retrieval,
    )

    print("  Strategizing... (Opus is synthesizing compound search strings)")
    try:
        result = opus_llm(system, user_prompt, expect_json=True, max_tokens=16384)
        plan = ExecutionPlan.from_dict(result)
        _materialize_retrieval_plan(
            plan,
            base_design=explicit_design if use_layered_retrieval else None,
            prefer_rendered_strings=use_layered_retrieval,
        )
        _annotate_plan_metadata(brief, plan)
        strict_summary = _apply_strict_seniority_plan_guardrails(brief, plan)
        if strict_summary:
            print(f"  Strict-seniority guardrail: {strict_summary}")
        if _brief_targets_edge_case_opening(brief):
            summary = _rebalance_execution_plan_for_edge_case_opening(brief, plan)
            _annotate_plan_metadata(brief, plan)
            strict_summary = _apply_strict_seniority_plan_guardrails(brief, plan)
            if strict_summary:
                print(f"  Strict-seniority guardrail: {strict_summary}")
            print(f"  Edge-case rebalance: {summary}")
        memory_summary = _apply_search_memory_to_plan(
            plan,
            (prior_run_data or {}).get("search_memory_summary"),
        )
        if memory_summary:
            print(f"  Search-memory rebalance: {memory_summary}")
        plan.original_architecture = plan.architecture  # Set once, never updated on pivot
        if plan.architecture:
            print(f"  Architecture: {plan.architecture} — {plan.architecture_rationale[:120]}")
        print("  Strategy complete.")
        return plan
    except Exception as e:
        # Try to salvage a partial JSON response
        plan = _try_salvage_strategy(e)
        if plan:
            _materialize_retrieval_plan(
                plan,
                base_design=explicit_design if use_layered_retrieval else None,
                prefer_rendered_strings=use_layered_retrieval,
            )
            _annotate_plan_metadata(brief, plan)
            strict_summary = _apply_strict_seniority_plan_guardrails(brief, plan)
            if strict_summary:
                print(f"  Strict-seniority guardrail: {strict_summary}")
            print(f"  [warn] Strategy JSON was truncated — salvaged partial plan", file=sys.stderr)
            return plan

        # Fall back — no kit strings to queue, just an empty plan
        print(f"  [warn] Strategy formation failed ({e}) — no strings to execute", file=sys.stderr)
        return _default_strategy(kit_strings)


def _build_strategy_system(
    brief: Brief,
    has_kit: bool = True,
    *,
    use_layered_retrieval: bool = False,
) -> str:
    total_count_guidance = "Generate 8-18 retrieval families total." if use_layered_retrieval else "Generate 15-30 search strings total."
    mix_label = "family types" if use_layered_retrieval else "string types"
    recall_label = "Recall families (4-10 families)" if use_layered_retrieval else "Recall strings (10-15 strings)"
    precision_label = (
        "Precision \"sniper\" families (3-8 families)"
        if use_layered_retrieval
        else "Precision \"sniper\" strings (5-15 strings)"
    )
    architecture_override_note = (
        "Apply the constraints for your selected architecture. These override the base family counts above — both the total family count (8-18) and the recall/precision mix."
        if use_layered_retrieval
        else "Apply the constraints for your selected architecture. These override ALL default string counts above — both the total count (15-30) and the per-type counts (Type A: 10-15, Type B: 5-15). The ratio below supersedes those base counts:"
    )
    architecture_modifiers = (
        """
- **sniper**: 10-14 families, 60%+ Type B. Tight AND-gates, 20-500 expected results per rendered variant.
- **dragnet**: 8-12 families, 70%+ Type A. Broad recall openings, with each family allowed to emit multiple rendered variants.
- **titration**: Only 4-6 broad recon families for this first block. Hold remaining family budget for post-block-1 adaptation when you'll have real data.
- **negative_space**: 8-12 families with anti-noise overlays. Structure: (entry_signals) AND (capability_proxies) AND (reality_filters) [NOT anti_noise].
- **company_first**: 8-14 families by company cluster, not skill cluster. Company names as primary constraints inside entry/context layers.
- **title_first**: 5-8 families with exact quoted title phrases as entry_signals. Minimal extra capability layers."""
        if use_layered_retrieval
        else """
- **sniper**: 15-20 strings, 60%+ Type B. Tight AND-gates, 20-500 results each.
- **dragnet**: 10-15 strings, 70%+ Type A. Fat OR groups (7+ variants). 500-5000 results. Noise expected.
- **titration**: Only 5-8 broad recon strings for this first block. Hold remaining budget for post-block-1 adaptation when you'll have real data.
- **negative_space**: 10-15 strings with NOT operators from noise_archetypes. Structure: (skills) AND (domain) NOT (noise_title OR noise_keyword).
- **company_first**: 10-20 strings by company cluster, not skill cluster. Company names as primary AND constraints.
- **title_first**: 5-10 strings with exact quoted title phrases. Minimal skill keywords."""
    )
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

Your job: design targeted {"layered retrieval families and rendered search strings" if use_layered_retrieval else "compound Boolean search strings"} {"by combining terms from multiple kit clusters with domain qualifiers from the brief" if has_kit else "from the role requirements, using LinkedIn-compatible Boolean syntax"}.

{"Every search family should be expressed as:\n- entry_signals\n- capability_proxies\n- reality_filters\n- optional context_constraints\n- optional anti_noise\n- optional edge-case hypothesis overlays\n\nThe deterministic renderer downstream will convert these into executable booleans. retrieval_families are the primary planning contract for this brief." if use_layered_retrieval else "You may optionally include retrieval_families as structured metadata, but generated_strings remain the primary planning contract for this brief. Preserve the proven broad-to-narrow Boolean mechanics: cohort or adjacent-population doorway AND capability/workflow signals AND execution or production proof."}

### 1. DESIGN {"layered retrieval families" if use_layered_retrieval else "compound Boolean searches"}
{"The kit provides terms organized by skill cluster. This" if has_kit else "This"} role requires an INTERSECTION of skills.
Create {"retrieval families that AND-gate high-signal layers" if use_layered_retrieval else "compound searches that AND-gate high-signal concepts"} {"from different kit clusters with" if has_kit else "with"} domain/seniority qualifiers from the brief.

Example rendered compound: ("agentic" OR "LLM agent") AND ("financial services" OR "banking" OR "BFSI") AND ("production" OR "deployment" OR "enterprise")

{total_count_guidance} {"Each family may emit one or more concrete booleans." if use_layered_retrieval else ""} You MUST include a mix of TWO {mix_label}:

**Type A: {recall_label}**
Broad searches that surface the general cohort. 500-5000 expected results.
- AND-gate 2-3 clusters: skill terms AND domain terms AND seniority/depth signals
- Keep each clause to 3-6 OR'd terms

**Type B: {precision_label}**
Narrow searches using specific tool names, framework names, benchmark names, or niche technical terms that only genuine practitioners would have on their profile. 20-500 expected results.
- {"Use the kit's Precision cluster terms — specific tools, libraries, benchmarks, methods" if has_kit else "Use specific tool names, framework names, benchmark names, or method-specific terms from the JD and role description"}
- Cross with minimal domain qualifiers (or none — the tool name IS the qualifier)
- Examples of precision signals: specific framework names (Axolotl, vLLM, DeepSpeed), benchmark names (SWE-bench, MMLU, HumanEval), method-specific terms (Constitutional AI, GRPO), infrastructure (TRL, PEFT)
- These strings may return few results but nearly every result is a real practitioner
- {"Look through the kit vocabulary for the most specific, least ambiguous terms and USE them" if has_kit else "Mine the JD for the most specific, least ambiguous terms and USE them"}

Order: alternate between Type A and Type B so precision-oriented families run early, not just as an afterthought.

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

{architecture_override_note}
{architecture_modifiers}

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
- "retrieval_families": Array of structured family objects in priority order. Each object:
  - "family_id": Stable id for the family (string)
  - "label": Human label (string)
  - "objective": Why this family exists (string)
  - "priority": Priority score (int)
  - "enabled": Whether to execute this family (bool)
  - "variants_to_emit": How many rendered variants to emit (int)
  - "entry_signals": Array of objects with "item_id", "label", "terms", optional "priority"
  - "capability_proxies": Array of objects with "item_id", "label", "terms", optional "priority"
  - "reality_filters": Array of objects with "item_id", "label", "terms", optional "priority"
  - "context_constraints": Array of objects with "item_id", "label", "terms", optional "priority"
  - "anti_noise": Array of objects with "item_id", "label", "terms", optional "priority"
  - "target_employers": Optional employer targets (array of strings)
  - "target_markets": Optional market/lane labels (array of strings)
  - "hypothesis_ids": Optional applied edge-case hypotheses (array of strings)
- "generated_strings": Array of compound strings to execute, in priority order. Each object:
  - "boolean": The full Boolean string (string)
  - "rationale": Why this compound is likely to surface strong candidates for the role (string)
  - "vocabulary_sources": {"Which kit blocks/clusters the terms come from" if has_kit else "Which JD sections or capability areas the terms derive from"} (string) — this is for traceability only, NOT for scoping evaluation
  - "family_key": Short stable label for this search family (string) — use the same label for close variants of the same idea
  - "novelty_bucket": "edge_case" or "canonical" (string)
  - "domain_lane": Primary lane this string targets (string, e.g. capital_markets, risk_compliance, asset_management, insurance, bfsi_vendors, general)
  - "retrieval_recipe": Optional structured recipe describing the layer ids and applied hypotheses used to render this string
- "coverage_gaps": Array of gaps identified. Each object:
  - "gap": Description of the missing coverage (string)
  - "suggested_boolean": Optional Boolean string to fill the gap, or null (string|null)
  - "rationale": Why this population matters for this role (string)
  - "family_key": Optional stable label for the gap string family (string)
  - "novelty_bucket": Optional "edge_case" or "canonical" (string)
  - "domain_lane": Optional primary lane label (string)
- "noise_predictions": Array of objects with "term" (string), "expected_collision" (string), "mitigation" (string)

Return valid JSON only."""


def _build_strategy_user(
    brief: Brief,
    kit_strings: list[KitString],
    prior_run_data: dict | None = None,
    *,
    use_layered_retrieval: bool = False,
) -> str:
    retrieval_design = _explicit_design_from_brief(brief) if use_layered_retrieval else RetrievalDesign()
    semantic_hint_mode = use_layered_retrieval or is_strict_seniority_brief(brief)
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

    if use_layered_retrieval and not retrieval_design.is_empty():
        prompt += (
            "\n## Layered Retrieval Design\n"
            f"{json.dumps(summarize_retrieval_design(retrieval_design), indent=2)}\n"
            "\nPrefer using this structured retrieval design as the primary planning interface. "
            "If you expand or revise it, keep the same layered model: entry_signals, "
            "capability_proxies, reality_filters, optional context_constraints, optional anti_noise, "
            "and edge-case hypothesis overlays.\n"
        )

    if prior_run_data:
        raw_prior = dict(prior_run_data)
        raw_prior.pop("search_memory_summary", None)
        prompt += f"\n## Prior Run Data\n{json.dumps(raw_prior, indent=2)}\n"

        if prior_run_data.get("noise_discoveries"):
            noise_text = "\n## Noise Patterns Discovered in Prior Sessions\n"
            for nd in prior_run_data["noise_discoveries"]:
                noise_text += f"- {nd['term']}: [{nd['status']}] {nd.get('note', '')}\n"
            noise_text += "\nAvoid generating strings that primarily target confirmed_noise patterns.\n"
            prompt += noise_text

        if prior_run_data.get("search_memory_summary"):
            prompt += (
                "\n## Search Family Memory\n"
                f"{format_search_memory_summary(prior_run_data['search_memory_summary'])}\n"
                "\nAvoid reopening exhausted families early in the run. If you reuse them at all, "
                "treat them as later cleanup passes rather than opening bets.\n"
            )

    if brief.search_priorities:
        prompt += f"\n## User Hints\nSearch priorities: {', '.join(brief.search_priorities)}\n"
        if semantic_hint_mode:
            prompt += (
                "Treat these priorities as semantic guidance, not as a checklist of phrases to restate. "
                "Infer the target populations and generate your own discriminative search vocabulary.\n"
            )
            if is_strict_seniority_brief(brief):
                prompt += (
                    "For this strict-seniority brief, prefer technical-authority concepts, ED-scope signals, "
                    "architecture-deep language, and builder proof over broad management-title coverage.\n"
                )

    if brief.additional_search_terms:
        prompt += f"\n## Additional Search Terms\nThese terms should be used for search string generation but are NOT evaluation criteria:\n{', '.join(brief.additional_search_terms)}\n"
        if semantic_hint_mode:
            prompt += (
                "These terms are anchors and hints, not a mandate to repeat them verbatim. "
                "Use them to infer adjacent practitioner language, hidden title variants, workflow language, "
                "and more discriminative phrasing.\n"
            )
            if is_strict_seniority_brief(brief):
                prompt += (
                    "Do not turn these hints into broad OR groups of generic titles, company inventories, or loose seniority ladders.\n"
                )

    if brief.instructions:
        prompt += f"\n## Sourcing Instructions\n" + "\n".join(f"- {i}" for i in brief.instructions) + "\n"

    prompt += (
        "\nSynthesize layered retrieval families and rendered search strings"
        if use_layered_retrieval
        else "\nSynthesize compound Boolean search strings"
    ) + (" from this vocabulary." if kit_strings else " from the JD and role context.")
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
    search_memory_summary: dict | None = None,
    checkpoint_mode: str = "normal_block_checkpoint",
    market_intel_advisory_context: str = "",
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

    opening_checkpoint_guidance = ""
    if checkpoint_mode == "opening_checkpoint":
        opening_checkpoint_guidance = """

This is the OPENING CHECKPOINT. Treat it differently from a normal later-stage block adaptation:
- prioritize exploitation of productive institution/lane patterns over novelty-chasing
- skip dead hidden-population hypotheses sooner
- use new_strings to pull proven direct BFSI / market-institution lanes forward
- do NOT spend this checkpoint rediscovering adjacent edge-case populations that already failed
- only recommend a pivot if the opening block is uniformly dead and coherently wrong
"""

    explicit_design = _explicit_design_from_brief(brief)
    use_layered_retrieval = explicit_design.is_explicit()

    system = f"""You are a sourcing strategist adapting a search plan mid-run.

Role: {brief.role_title}
{brief.role_description}

You've just received a report on a batch of completed Boolean searches. Based on the results:
1. Generate NEW {"layered retrieval families and/or rendered Boolean strings" if use_layered_retrieval else "rendered Boolean strings"} that target signal patterns you observed — use the kit vocabulary below as building blocks
2. Identify remaining queued strings to skip (redundant, similar to zero-save strings)
3. Suggest reordering of remaining queued strings based on observed signal
4. Update noise pattern knowledge

IMPORTANT: Each Boolean string is a NET that catches candidates for ANY archetype, not just one.
A string built from post-training terms might surface a STEM reasoning engineer. That's expected and good.
Evaluate string productivity by total saves across ALL archetypes, not just the archetype the string was "designed for."

{"When generating new retrieval families, use the layered retrieval model:\n- entry_signals\n- capability_proxies\n- reality_filters\n- optional context_constraints\n- optional anti_noise\n- optional edge-case hypothesis overlays\n\nRendered booleans should still follow the same broad-to-narrow pattern:\n(entry_signals) AND (capability_proxies) AND (reality_filters) [AND context_constraints] [NOT anti_noise]" if use_layered_retrieval else "Continue using the proven broad-to-narrow pattern: cohort or adjacent-population doorway AND capability or workflow signals AND execution or production proof. You may optionally include new_retrieval_families as traceability metadata, but new_strings remain primary."}

When generating new strings or families, combine terms from the kit vocabulary with domain qualifiers. The most valuable updates will target the specific intersection of skills and domain this role requires.

Include BOTH broad recall strings AND narrow precision "sniper" strings that use specific tool/framework/benchmark names from the kit vocabulary — terms only real practitioners would have on their profiles.

If the brief says the obvious pool is tapped, prefer generating new strings that expand productive edge-case populations before emitting direct framework-name cleanup strings or exact-title cleanup strings.

When adapting, continue using the same loop: identify what a standard sourcer would search next, then push one layer outward toward adjacent but same-caliber populations that the standard next step would still miss.

{opening_checkpoint_guidance}

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
{market_intel_advisory_context}

Return JSON with this structure:
- "new_strings": Array of objects with "boolean" (string), "rationale" (string), "family_key" (string), "novelty_bucket" ("edge_case"|"canonical"), "domain_lane" (string)
- "new_retrieval_families": Optional array of structured family objects using the same schema as strategy formation
- "hypothesis_updates": Optional array of objects with "hypothesis_id", "status", "reason", and optional "promote_to_family_id"
- "skip_remaining": Array of objects with "string_id" (int), "reason" (string)
- "reorder": Array of objects with "string_id" (int), "move_to" ("next" | "last"), "reason" (string)
- "noise_updates": Array of objects with "term" (string), "status" ("confirmed_signal" | "confirmed_noise" | "mixed"), "note" (string)
- "pivot_to_architecture": (optional) New architecture name if recommending a pivot (string)
- "pivot_rationale": (optional) Why the current architecture failed and why the new one will work (string)

Return valid JSON only."""

    remaining_text = ""
    for ss in remaining_strings:
        metadata = (
            f"family={ss.family_key or 'unknown'} "
            f"novelty={ss.novelty_bucket or 'unknown'} "
            f"lane={ss.domain_lane or 'general'}"
        )
        remaining_text += f"  #{ss.id} [{metadata}]: {ss.boolean[:200]}\n"

    user_prompt = f"""{block_report.to_summary_text()}

## Remaining Queued Strings ({len(remaining_strings)})
{remaining_text}
"""
    if search_memory_summary:
        user_prompt += (
            "\n## Search Family Memory\n"
            f"{format_search_memory_summary(search_memory_summary)}\n"
        )
    if vocab_section:
        user_prompt += f"""
## Kit Vocabulary (building blocks for new strings)
{vocab_section}
"""
    if use_layered_retrieval and not explicit_design.is_empty():
        user_prompt += (
            "\n## Current Layered Retrieval Design\n"
            f"{json.dumps(summarize_retrieval_design(explicit_design), indent=2)}\n"
        )

    user_prompt += "\nSuggest adaptations."

    result = opus_llm(system, user_prompt, expect_json=True)
    adaptation = AdaptationResponse.from_dict(result)
    _materialize_retrieval_adaptation(
        adaptation,
        base_design=explicit_design if use_layered_retrieval else None,
        prefer_rendered_strings=use_layered_retrieval,
    )
    _annotate_adaptation_metadata(brief, adaptation)
    _apply_strict_seniority_adaptation_guardrails(brief, adaptation, remaining_strings)
    if checkpoint_mode != "opening_checkpoint" and _brief_targets_edge_case_opening(brief):
        adaptation = _rebalance_adaptation_for_edge_case_opening(
            brief, adaptation, remaining_strings
        )
        _annotate_adaptation_metadata(brief, adaptation)
        _apply_strict_seniority_adaptation_guardrails(brief, adaptation, remaining_strings)
    _apply_search_memory_to_adaptation(adaptation, remaining_strings, search_memory_summary)
    return adaptation
