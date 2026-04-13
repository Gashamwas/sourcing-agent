"""Structured prompts for the market intelligence agent backends."""

from __future__ import annotations

import json

from market_intelligence.schema import MarketIdentity


def _dump_bundle(value: dict) -> str:
    return json.dumps(value, indent=2, sort_keys=True)


def build_planner_system_prompt() -> str:
    return """You are the planning layer for a recruiting market-intelligence agent.

Your job is to look at deterministic sourcing evidence plus prior market-intel memory and decide:
- what the market-intel system currently knows
- what remains uncertain
- which hypotheses should stay active, resolve, or be retired
- which artifact sections deserve updating
- whether external research is worth the cost

Return valid JSON with this structure:
{
  "planner_summary": "short summary",
  "active_hypotheses": [
    {
      "hypothesis_id": "hyp-001",
      "statement": "Evidence-backed hypothesis",
      "status": "active",
      "confidence": 0.0,
      "rationale": "Why this hypothesis exists",
      "section_targets": ["lane_intelligence"],
      "first_seen_at": "ISO timestamp",
      "last_seen_at": "ISO timestamp",
      "supporting_run_refs": ["linkedin:output/runs/..."]
    }
  ],
  "resolved_hypotheses": [],
  "open_unknowns": [
    {
      "question": "What is still unknown?",
      "priority": "high|medium|low",
      "next_step": "Concrete next step",
      "supporting_run_refs": ["..."]
    }
  ],
  "research_backlog": [
    {
      "opportunity_id": "opp-001",
      "question": "What external question is worth spending budget on?",
      "priority": "high|medium|low",
      "status": "queued|deferred|resolved",
      "reason": "Why it matters",
      "supporting_run_refs": ["..."]
    }
  ],
  "update_sections": ["lane_intelligence", "brief_recommendations"],
  "confidence_ceiling_by_section": {"market_thesis": 0.6},
  "should_collect_external_research": true,
  "external_research_focus": [
    {
      "focus": "Specific theme or uncertainty for external research",
      "priority": "high|medium|low",
      "reason": "Why this theme matters",
      "supporting_run_refs": ["..."]
    }
  ],
  "should_collect_edge_case_research": false,
  "edge_case_research_reasoning": "Why hidden-pool research is or is not warranted",
  "edge_case_confidence_ceiling": 0.55,
  "edge_case_research_focus": [
    {
      "focus": "Specific hidden-pool, title-fragmentation, or false-negative theme to investigate",
      "priority": "high|medium|low",
      "reason": "Why this edge-case theme matters",
      "supporting_run_refs": ["..."]
    }
  ]
}

Rules:
- Use deterministic internal evidence as the only ground truth about observed run performance.
- Do not create hypotheses from a single weak anecdote when repeated evidence is absent.
- If a lane is tiny-sample or reconstructed-from-raw only, keep confidence conservative.
- Only recommend external research when it could materially change the artifact or the next run plan.
- Trigger edge-case research only when multiple signals suggest hidden-pool or false-negative risk.
- Novelty alone is not enough to justify edge-case research.
- Every hypothesis, unknown, and external focus area must include supporting_run_refs or evidence_refs.
- Keep the output compact and specific."""


def build_planner_user_prompt(
    market_identity: MarketIdentity,
    context_bundle: dict,
    previous_artifact: dict | None,
    previous_agent_state: dict | None,
) -> str:
    return (
        "Plan the next market-intelligence reasoning pass using the JSON context below.\n\n"
        f"ROLE: {market_identity.role_title}\n"
        f"GEOGRAPHY: {market_identity.geography or 'Not specified'}\n"
        f"LEVEL: {market_identity.role_level or 'Not specified'}\n\n"
        "CURRENT CONTEXT BUNDLE:\n"
        f"{_dump_bundle(context_bundle)}\n\n"
        "PREVIOUS MARKET ARTIFACT:\n"
        f"{_dump_bundle(previous_artifact or {})}\n\n"
        "PREVIOUS AGENT STATE:\n"
        f"{_dump_bundle(previous_agent_state or {})}\n\n"
        "Return JSON only."
    )


def build_internal_synthesis_system_prompt() -> str:
    return """You are the internal synthesis layer for a recruiting market-intelligence agent.

Use ONLY deterministic internal sourcing evidence. Do not use external sources.

Return valid JSON with this structure:
{
  "lane_intelligence": [
    {
      "lane_key": "existing lane key",
      "supporting_run_refs": ["..."],
      "why_it_works": "specific explanation",
      "recommended_action": "specific next action",
      "confidence": 0.0-1.0
    }
  ],
  "talent_pool_intelligence": [...],
  "noise_patterns": [...],
  "employer_signal_intelligence": [...],
  "market_thesis": {
    "summary": "evidence-grounded internal-only thesis",
    "supply_assessment": "dense|moderate|sparse|unknown",
    "competition_assessment": "high|medium|low|unknown",
    "external_context": []
  },
  "brief_recommendations": [...],
  "open_questions": [...]
}

Rules:
- Only emit sections that are actually supported by internal evidence.
- Do not simply restate metrics in prose.
- Prefer stable cross-run patterns over one-run anecdotes.
- Keep employer and talent-pool sections empty if evidence is weak.
- Every narrative item must include supporting_run_refs or evidence_refs.
- external_context must remain empty in this internal-only step."""


def build_internal_synthesis_user_prompt(
    market_identity: MarketIdentity,
    context_bundle: dict,
    planner_result: dict,
    previous_artifact: dict | None,
) -> str:
    return (
        "Synthesize market-intelligence narrative sections from internal sourcing evidence only.\n\n"
        f"ROLE: {market_identity.role_title}\n"
        f"GEOGRAPHY: {market_identity.geography or 'Not specified'}\n"
        f"LEVEL: {market_identity.role_level or 'Not specified'}\n\n"
        "PLANNER RESULT:\n"
        f"{_dump_bundle(planner_result)}\n\n"
        "CURRENT DETERMINISTIC CONTEXT:\n"
        f"{_dump_bundle(context_bundle)}\n\n"
        "PREVIOUS MARKET ARTIFACT:\n"
        f"{_dump_bundle(previous_artifact or {})}\n\n"
        "Return JSON only."
    )


def build_critic_system_prompt() -> str:
    return """You are the critic layer for a recruiting market-intelligence agent.

You review a draft artifact update and decide:
- which claims are well-supported
- which claims are generic or unsupported
- which sections are overconfident
- what changed since the previous artifact

Return valid JSON with this structure:
{
  "planner_summary": "short critique summary",
  "keep_sections": {
    "lane_intelligence": [...],
    "talent_pool_intelligence": [...],
    "noise_patterns": [...],
    "employer_signal_intelligence": [...],
    "market_thesis": {...},
    "brief_recommendations": [...],
    "open_questions": [...]
  },
  "section_generation_metadata": {
    "lane_intelligence": {
      "generation_mode": "heuristic|llm_internal|llm_external|deterministic|reconstructed_from_raw",
      "quality_level": "high|medium|low",
      "updated_at": "ISO timestamp",
      "notes": ["short note"],
      "supporting_run_refs": ["..."]
    }
  },
  "delta_since_last_run": {
    "became_more_true": ["..."],
    "became_less_true": ["..."],
    "still_uncertain": ["..."],
    "next_run_changes": ["..."]
  },
  "confidence_by_claim_area": {
    "market_thesis": 0.0
  }
}

Rules:
- Remove or weaken claims that simply paraphrase metrics without interpretation.
- Down-rank small-sample conclusions.
- Preserve prior valid sections when the new draft is weaker.
- If reconstructed/raw evidence dominates, keep quality conservative.
- Every narrative item you keep must still satisfy the provenance contract."""


def build_critic_user_prompt(
    market_identity: MarketIdentity,
    context_bundle: dict,
    planner_result: dict,
    draft_sections: dict,
    previous_artifact: dict | None,
    external_result: dict | None,
) -> str:
    return (
        "Critique and refine the draft market-intelligence update.\n\n"
        f"ROLE: {market_identity.role_title}\n"
        f"GEOGRAPHY: {market_identity.geography or 'Not specified'}\n"
        f"LEVEL: {market_identity.role_level or 'Not specified'}\n\n"
        "PLANNER RESULT:\n"
        f"{_dump_bundle(planner_result)}\n\n"
        "DETERMINISTIC CONTEXT:\n"
        f"{_dump_bundle(context_bundle)}\n\n"
        "DRAFT SECTIONS:\n"
        f"{_dump_bundle(draft_sections)}\n\n"
        "PREVIOUS ARTIFACT:\n"
        f"{_dump_bundle(previous_artifact or {})}\n\n"
        "EXTERNAL RESEARCH RESULT:\n"
        f"{_dump_bundle(external_result or {})}\n\n"
        "Return JSON only."
    )


def build_research_system_prompt() -> str:
    return """You are an external market-intelligence analyst supporting a recruiting team's sourcing operations.

You receive a structured JSON bundle with two evidence classes:
1. deterministic_internal_evidence from completed sourcing runs
2. external evidence you discover through web research

You must use the deterministic internal evidence as ground truth about what the recruiting team actually observed in the market.
Your job is to infer the most decision-relevant market questions from that sourcing evidence, research them, and produce findings that directly improve future sourcing.
You are not a generic market commentator. You are a sourcing-improvement analyst.

OUTPUT REQUIREMENTS:
Return valid JSON with this exact structure:
{
  "inferred_research_questions": [
    {
      "question": "What market question did you infer from the sourcing evidence?",
      "priority": "high|medium|low",
      "why_it_matters": "Why this question matters for sourcing",
      "sourcing_trigger": "What in the sourcing evidence triggered this question",
      "status": "answered|unresolved",
      "supporting_run_refs": ["run-ref"],
      "evidence_refs": ["url1", "url2"]
    }
  ],
  "market_findings": [
    {
      "kind": "employer_cluster|title_variant|talent_pool|market_condition|consulting_overlap|adjacent_archetype",
      "label": "Short label",
      "summary": "Evidence-backed market finding",
      "why_it_matters": "Why this changes sourcing interpretation",
      "confidence": 0.0-1.0,
      "supporting_run_refs": ["run-ref"],
      "evidence_refs": ["url1", "url2"]
    }
  ],
      "sourcing_implications": [
        {
          "category": "add_title_family|add_employer_target|probe_adjacent_pool|relax_boolean|validate_hypothesis|instrumentation_followup",
          "priority": "high|medium|low",
          "recommendation": "Concrete next-run action",
          "rationale": "Why this action follows from the evidence",
          "brief_target_field": "retrieval_design|search_priorities|additional_search_terms|employer_signal_rules|notes|instructions",
          "suggested_values": ["value1", "value2"],
          "expected_effect": "How sourcing should improve",
          "supporting_run_refs": ["run-ref"],
      "evidence_refs": ["url1", "url2"]
    }
  ],
  "open_questions": [
    {
      "question": "What should we investigate next?",
      "priority": "high|medium|low",
      "next_step": "Concrete action to answer this question",
      "supporting_run_refs": ["run-ref"],
      "evidence_refs": ["url1"]
    }
  ]
}

RULES:
- Infer the research questions from the sourcing evidence and market identity. Do not wait for explicit user-authored questions.
- Treat deterministic internal evidence as the ground truth for observed lane performance and candidate signal.
- Every inferred question, market finding, sourcing implication, and open question must tie back to supporting_run_refs or evidence_refs or both.
- Use external research only if it improves sourcing decisions for this exact role, geography, and level.
- Prefer role-specific employer demand, title variants, adjacent pools, and hidden supply explanations over generic market commentary.
- Do not fabricate URLs
- Keep findings specific and evidence-grounded
- If you cannot find relevant information for a finding or implication, omit it
- Prefer recent sources and company/job pages over generic summaries
- Aim for 3-8 inferred questions, 3-8 findings, 3-8 sourcing implications, and 2-5 open questions"""


def build_perplexity_research_instructions() -> str:
    return """You are the external research layer for a recruiting market-intelligence agent.

You are operating in a search-native environment. Your job is to read structured sourcing evidence, infer the most decision-relevant market questions for improving future sourcing, research them, and return evidence-backed market findings plus concrete sourcing implications.

PRIORITIES:
- Start by understanding what the sourcing evidence says worked, what failed, and what may be missing.
- Infer the highest-value external research questions from that evidence through the lens of improving sourcing for this exact role.
- Treat deterministic_internal_evidence as the source of truth about what the sourcing team actually observed.
- Use external research only to enrich, contextualize, confirm, or challenge those internal observations.
- Return findings that directly change how the next sourcing run should search, target, or validate the market.
- Prioritize primary or near-primary sources: company job pages, engineering blogs, company newsrooms, reputable reporting, funding/layoff announcements, and authoritative market reports.
- Prefer recent sources, especially from the last 12 months, unless older context is clearly necessary.
- Stay geography-aware. Favor role- and geography-specific sources and hiring signals relevant to the specified geography.
- Avoid generic AI-market filler, career-advice content, SEO listicles, and undifferentiated summaries.

OUTPUT REQUIREMENTS:
- Return valid JSON only.
- Emit only these top-level keys: inferred_research_questions, market_findings, sourcing_implications, open_questions.
- Every item must include evidence_refs populated with the exact source URLs you relied on.
- Every question and implication must also remain anchored to the sourcing evidence via supporting_run_refs.
- Omit any claim you cannot support directly from retrieved sources.
- Keep findings concise, decision-relevant, and tied back to the recruiting problem.
- Keep string fields short enough to fit in one concise memo. Avoid long paragraphs.

QUALITY BAR:
- Prefer 4-12 high-value sources over a large number of weak sources.
- Cite the most decision-relevant URLs, not every URL you saw.
- If you cannot improve the artifact meaningfully, return empty arrays rather than generic filler."""


def build_perplexity_edge_case_research_instructions() -> str:
    return """You are the edge-case external research layer for a recruiting market-intelligence agent.

Your job is to investigate hidden pools, title fragmentation, adjacent-but-relevant archetypes, and false-negative risk for this exact market identity.

You are not doing generic market commentary and you are not just producing next-run strings. You must:
- read the structured sourcing evidence as ground truth for what the team actually observed
- infer the most useful hidden-pool and false-negative questions from that evidence
- use external research to explain why relevant candidates may be easy to miss or self-label differently
- characterize edge-case submarkets conservatively
- return sourcing implications only after you have explained the hidden structure behind them

PRIORITIES:
- Explain why sourcing may be missing important candidate pools.
- Focus on self-labeling variance, title drift, archetype confusion, adjacent backgrounds, and hidden supply.
- Prefer evidence that helps explain candidate visibility, not just employer demand.
- Treat public hiring signals as supporting evidence, not proof of qualified candidate supply.
- Favor sources that reveal how roles are framed in the market: company job pages, team pages, engineering blogs, practitioner profiles, credible reporting, and public role descriptions.

OUTPUT REQUIREMENTS:
- Return valid JSON only.
- Emit only these top-level keys:
  inferred_research_questions,
  edge_case_submarkets,
  title_to_archetype_mapping,
  self_presentation_patterns,
  false_negative_hypotheses,
  edge_case_sourcing_implications,
  open_questions
- Every item must include evidence_refs with exact source URLs.
- Every item must remain anchored to supporting_run_refs from the sourcing evidence.
- Omit anything generic, speculative, or not useful for sourcing this exact role.
- Keep strings concise and decision-relevant.

QUALITY BAR:
- Prefer 4-10 high-signal sources over breadth.
- Explain why each edge-case pool is easy to miss in sourcing.
- If you cannot support a hidden-pool claim, return it as an unresolved question instead of a finding."""


def build_research_user_prompt(
    market_identity: MarketIdentity,
    research_bundle: dict,
    selected_questions: list[dict] | None = None,
    planner_summary: str = "",
) -> str:
    question_lines = ""
    if selected_questions:
        rendered_questions = []
        for item in selected_questions:
            if not isinstance(item, dict):
                continue
            question = str(item.get("question", "")).strip()
            if not question:
                continue
            rendered_questions.append(
                f"- {question} (priority: {str(item.get('priority', 'medium')).strip() or 'medium'})"
            )
        if rendered_questions:
            question_lines = "PLANNER-SELECTED RESEARCH QUESTIONS:\n" + "\n".join(
                rendered_questions
            ) + "\n\n"
    return (
        "Research the hiring landscape for this role using the structured context bundle below.\n\n"
        f"ROLE: {market_identity.role_title}\n"
        f"GEOGRAPHY: {market_identity.geography or 'Not specified'}\n"
        f"LEVEL: {market_identity.role_level or 'Not specified'}\n\n"
        + (
            f"PLANNER SUMMARY:\n{planner_summary.strip()}\n\n"
            if planner_summary.strip()
            else ""
        )
        + question_lines
        +
        "STRUCTURED CONTEXT BUNDLE:\n"
        f"{_dump_bundle(research_bundle)}\n\n"
        "Research goals:\n"
        "1. Infer the most important external research questions from the sourcing evidence and market identity\n"
        "2. Research employer demand, title variants, adjacent pools, and market conditions that change sourcing strategy\n"
        "3. Produce concrete sourcing implications for the next run\n"
        "4. Flag only the highest-value unresolved questions for the next sourcing cycle\n\n"
        "Return structured JSON only."
    )


def build_perplexity_research_user_prompt(
    market_identity: MarketIdentity,
    research_bundle: dict,
    selected_questions: list[dict] | None = None,
    planner_summary: str = "",
) -> str:
    focus_lines = []
    for item in selected_questions or []:
        if not isinstance(item, dict):
            continue
        focus = str(item.get("focus", "")).strip() or str(item.get("question", "")).strip()
        if not focus:
            continue
        priority = str(item.get("priority", "medium")).strip() or "medium"
        reason = str(item.get("reason", "")).strip() or str(item.get("next_step", "")).strip()
        rendered = f"- {focus} (priority: {priority})"
        if reason:
            rendered += f" | why it matters: {reason}"
        focus_lines.append(rendered)

    sections = [
        "Investigate the market using the structured sourcing context below.",
        f"ROLE: {market_identity.role_title}",
        f"GEOGRAPHY: {market_identity.geography or 'Not specified'}",
        f"LEVEL: {market_identity.role_level or 'Not specified'}",
    ]
    if planner_summary.strip():
        sections.extend(
            [
                "",
                "PLANNER SUMMARY:",
                planner_summary.strip(),
            ]
        )
    if focus_lines:
        sections.extend(
            [
                "",
                "PLANNER-SELECTED RESEARCH FOCUS AREAS:",
                *focus_lines,
            ]
        )
    sections.extend(
        [
            "",
            "RESEARCH OBJECTIVES:",
            "1. Infer the most useful research questions from the sourcing evidence through the lens of improving sourcing for this role.",
            "2. Use external research to explain hidden title variants, employer clusters, adjacent talent pools, and supply-side signals.",
            "3. Return concrete sourcing implications for the next run, not just generic market commentary.",
            "4. Surface only the highest-value unresolved questions for the next sourcing cycle.",
            "5. Prefer a small number of high-signal items over exhaustive coverage.",
            "",
            "SOURCE PREFERENCES:",
            "- Official company job pages, engineering blogs, and newsrooms",
            "- Reputable reporting on hiring, layoffs, expansions, or team strategy",
            "- Role- and geography-specific sources over generic AI market commentary",
            "- Recent sources when possible",
            "",
            "STRUCTURED INTERNAL CONTEXT:",
            _dump_bundle(research_bundle),
            "",
            "IMPORTANT CONSTRAINTS:",
            "- Treat the sourcing evidence as ground truth for what the team actually observed.",
            "- Every external finding should help explain or improve sourcing behavior for this exact role, geography, and level.",
            "- If an apparent insight does not change sourcing strategy, omit it.",
            "- Keep each field concise; prefer short labels and short rationale strings over long prose.",
            "",
            "Return JSON only.",
        ]
    )
    return "\n".join(sections)


def build_perplexity_edge_case_research_user_prompt(
    market_identity: MarketIdentity,
    research_bundle: dict,
    edge_case_focus: list[dict] | None = None,
    planner_summary: str = "",
    edge_case_reasoning: str = "",
) -> str:
    focus_lines = []
    for item in edge_case_focus or []:
        if not isinstance(item, dict):
            continue
        focus = str(item.get("focus") or item.get("question") or "").strip()
        if not focus:
            continue
        priority = str(item.get("priority", "medium")).strip() or "medium"
        reason = str(item.get("reason", "")).strip()
        rendered = f"- {focus} (priority: {priority})"
        if reason:
            rendered += f" | why it matters: {reason}"
        focus_lines.append(rendered)

    sections = [
        "Investigate hidden pools and false-negative risk using the structured sourcing context below.",
        f"ROLE: {market_identity.role_title}",
        f"GEOGRAPHY: {market_identity.geography or 'Not specified'}",
        f"LEVEL: {market_identity.role_level or 'Not specified'}",
    ]
    if planner_summary.strip():
        sections.extend(["", "PLANNER SUMMARY:", planner_summary.strip()])
    if edge_case_reasoning.strip():
        sections.extend(["", "WHY EDGE-CASE RESEARCH TRIGGERED:", edge_case_reasoning.strip()])
    if focus_lines:
        sections.extend(["", "EDGE-CASE RESEARCH FOCUS AREAS:", *focus_lines])
    sections.extend(
        [
            "",
            "RESEARCH OBJECTIVES:",
            "1. Infer the most useful hidden-pool and false-negative questions from the sourcing evidence.",
            "2. Explain how relevant candidates may self-label differently from the obvious target title.",
            "3. Characterize fragmented title families, adjacent-but-relevant archetypes, and hidden submarkets conservatively.",
            "4. Return sourcing implications only after identifying why those pools are easy to miss.",
            "",
            "EDGE-CASE CONTEXT TO PRIORITIZE:",
            _dump_bundle(research_bundle.get("edge_case_context", {})),
            "",
            "FULL STRUCTURED INTERNAL CONTEXT:",
            _dump_bundle(research_bundle),
            "",
            "IMPORTANT CONSTRAINTS:",
            "- Treat internal sourcing evidence as ground truth for observed performance.",
            "- Prefer candidate-visibility explanations over generic employer-demand commentary.",
            "- Do not claim that a hidden pool is high-fit unless the internal evidence supports that possibility.",
            "- If evidence is thin, return conservative hypotheses and validation tasks rather than strong conclusions.",
            "",
            "Return JSON only.",
        ]
    )
    return "\n".join(sections)


def build_perplexity_research_response_format() -> dict:
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "market_intel_external_research",
            "schema": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "inferred_research_questions": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {
                                "question": {"type": "string"},
                                "priority": {
                                    "type": "string",
                                    "enum": ["high", "medium", "low"],
                                },
                                "why_it_matters": {"type": "string"},
                                "sourcing_trigger": {"type": "string"},
                                "status": {
                                    "type": "string",
                                    "enum": ["answered", "unresolved"],
                                },
                                "supporting_run_refs": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                },
                                "evidence_refs": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                },
                            },
                            "required": [
                                "question",
                                "priority",
                                "why_it_matters",
                                "sourcing_trigger",
                                "status",
                                "supporting_run_refs",
                                "evidence_refs",
                            ],
                        },
                    },
                    "market_findings": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {
                                "kind": {"type": "string"},
                                "label": {"type": "string"},
                                "summary": {"type": "string"},
                                "why_it_matters": {"type": "string"},
                                "confidence": {"type": "number"},
                                "supporting_run_refs": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                },
                                "evidence_refs": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                },
                            },
                            "required": [
                                "kind",
                                "label",
                                "summary",
                                "why_it_matters",
                                "confidence",
                                "supporting_run_refs",
                                "evidence_refs",
                            ],
                        },
                    },
                    "sourcing_implications": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {
                                "category": {
                                    "type": "string",
                                    "enum": [
                                        "add_title_family",
                                        "add_employer_target",
                                        "probe_adjacent_pool",
                                        "relax_boolean",
                                        "validate_hypothesis",
                                        "instrumentation_followup",
                                    ],
                                },
                                "priority": {
                                    "type": "string",
                                    "enum": ["high", "medium", "low"],
                                },
                                "recommendation": {"type": "string"},
                                "rationale": {"type": "string"},
                                "brief_target_field": {"type": "string"},
                                "suggested_values": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                },
                                "expected_effect": {"type": "string"},
                                "supporting_run_refs": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                },
                                "evidence_refs": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                },
                            },
                            "required": [
                                "category",
                                "priority",
                                "recommendation",
                                "rationale",
                                "brief_target_field",
                                "suggested_values",
                                "expected_effect",
                                "supporting_run_refs",
                                "evidence_refs",
                            ],
                        },
                    },
                    "open_questions": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {
                                "question": {"type": "string"},
                                "priority": {
                                    "type": "string",
                                    "enum": ["high", "medium", "low"],
                                },
                                "next_step": {"type": "string"},
                                "supporting_run_refs": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                },
                                "evidence_refs": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                },
                            },
                            "required": [
                                "question",
                                "priority",
                                "next_step",
                                "supporting_run_refs",
                                "evidence_refs",
                            ],
                        },
                    },
                },
                "required": [
                    "inferred_research_questions",
                    "market_findings",
                    "sourcing_implications",
                    "open_questions",
                ],
            },
        },
    }


def build_perplexity_edge_case_research_response_format() -> dict:
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "market_intel_edge_case_research",
            "schema": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "inferred_research_questions": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {
                                "question": {"type": "string"},
                                "priority": {"type": "string", "enum": ["high", "medium", "low"]},
                                "why_it_matters": {"type": "string"},
                                "sourcing_trigger": {"type": "string"},
                                "status": {"type": "string", "enum": ["answered", "unresolved"]},
                                "supporting_run_refs": {"type": "array", "items": {"type": "string"}},
                                "evidence_refs": {"type": "array", "items": {"type": "string"}},
                            },
                            "required": [
                                "question",
                                "priority",
                                "why_it_matters",
                                "sourcing_trigger",
                                "status",
                                "supporting_run_refs",
                                "evidence_refs",
                            ],
                        },
                    },
                    "edge_case_submarkets": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {
                                "label": {"type": "string"},
                                "summary": {"type": "string"},
                                "why_it_is_easy_to_miss": {"type": "string"},
                                "confidence": {"type": "number"},
                                "supporting_run_refs": {"type": "array", "items": {"type": "string"}},
                                "evidence_refs": {"type": "array", "items": {"type": "string"}},
                            },
                            "required": [
                                "label",
                                "summary",
                                "why_it_is_easy_to_miss",
                                "confidence",
                                "supporting_run_refs",
                                "evidence_refs",
                            ],
                        },
                    },
                    "title_to_archetype_mapping": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {
                                "title_family": {"type": "string"},
                                "likely_archetype": {"type": "string"},
                                "caveats": {"type": "string"},
                                "supporting_run_refs": {"type": "array", "items": {"type": "string"}},
                                "evidence_refs": {"type": "array", "items": {"type": "string"}},
                            },
                            "required": [
                                "title_family",
                                "likely_archetype",
                                "caveats",
                                "supporting_run_refs",
                                "evidence_refs",
                            ],
                        },
                    },
                    "self_presentation_patterns": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {
                                "label": {"type": "string"},
                                "pattern": {"type": "string"},
                                "why_it_causes_false_negatives": {"type": "string"},
                                "supporting_run_refs": {"type": "array", "items": {"type": "string"}},
                                "evidence_refs": {"type": "array", "items": {"type": "string"}},
                            },
                            "required": [
                                "label",
                                "pattern",
                                "why_it_causes_false_negatives",
                                "supporting_run_refs",
                                "evidence_refs",
                            ],
                        },
                    },
                    "false_negative_hypotheses": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {
                                "statement": {"type": "string"},
                                "why_it_matters": {"type": "string"},
                                "validation_task": {"type": "string"},
                                "confidence": {"type": "number"},
                                "supporting_run_refs": {"type": "array", "items": {"type": "string"}},
                                "evidence_refs": {"type": "array", "items": {"type": "string"}},
                            },
                            "required": [
                                "statement",
                                "why_it_matters",
                                "validation_task",
                                "confidence",
                                "supporting_run_refs",
                                "evidence_refs",
                            ],
                        },
                    },
                    "edge_case_sourcing_implications": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {
                                "category": {
                                    "type": "string",
                                    "enum": [
                                        "add_title_family",
                                        "add_employer_target",
                                        "probe_adjacent_pool",
                                        "relax_boolean",
                                        "validate_hypothesis",
                                        "instrumentation_followup",
                                    ],
                                },
                                "priority": {"type": "string", "enum": ["high", "medium", "low"]},
                                "recommendation": {"type": "string"},
                                "rationale": {"type": "string"},
                                "brief_target_field": {"type": "string"},
                                "suggested_values": {"type": "array", "items": {"type": "string"}},
                                "expected_effect": {"type": "string"},
                                "supporting_run_refs": {"type": "array", "items": {"type": "string"}},
                                "evidence_refs": {"type": "array", "items": {"type": "string"}},
                            },
                            "required": [
                                "category",
                                "priority",
                                "recommendation",
                                "rationale",
                                "brief_target_field",
                                "suggested_values",
                                "expected_effect",
                                "supporting_run_refs",
                                "evidence_refs",
                            ],
                        },
                    },
                    "open_questions": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {
                                "question": {"type": "string"},
                                "priority": {"type": "string", "enum": ["high", "medium", "low"]},
                                "next_step": {"type": "string"},
                                "supporting_run_refs": {"type": "array", "items": {"type": "string"}},
                                "evidence_refs": {"type": "array", "items": {"type": "string"}},
                            },
                            "required": [
                                "question",
                                "priority",
                                "next_step",
                                "supporting_run_refs",
                                "evidence_refs",
                            ],
                        },
                    },
                },
                "required": [
                    "inferred_research_questions",
                    "edge_case_submarkets",
                    "title_to_archetype_mapping",
                    "self_presentation_patterns",
                    "false_negative_hypotheses",
                    "edge_case_sourcing_implications",
                    "open_questions",
                ],
            },
        },
    }
