from shared.run_report_schema import (
    RunDebriefAnalysis,
    StructuredRunReport,
    render_run_report_markdown,
)


def _snapshot() -> dict:
    return {
        "schema_version": 1,
        "run_metadata": {
            "role_title": "Head of Applied AI Lab",
            "brief_name": "head-ai",
            "brief_version": "2.1",
            "linkedin_project": "Head of Applied AI Lab",
            "linkedin_project_id": "1957683706",
            "generated_at": "2026-04-06T12:00:00+00:00",
            "overall_summary": "Strong BFSI run with clear winning lanes.",
        },
        "metrics_summary": {
            "strings_executed": 8,
            "strings_skipped": 9,
            "total_results": 12137,
            "total_pages_reviewed": 25,
            "candidates_evaluated": 295,
            "facial_yes": 74,
            "facial_no": 221,
            "saved": 14,
            "rejected": 57,
            "overall_save_rate": 0.047,
            "facial_yes_rate": 0.251,
        },
        "string_performance": [
            {
                "string_id": 2,
                "name": "Research copilot lane",
                "status": "done",
                "result_count": 526,
                "pages_reviewed": 4,
                "saves": 8,
                "save_rate": 0.08,
                "saved_candidates": ["Mithun Azhagappan"],
                "notes": "Strong lane",
                "family_key": "research_copilot_asset_mgmt",
                "novelty_bucket": "edge_case",
                "domain_lane": "asset_management",
            }
        ],
    }


def _analysis_dict() -> dict:
    return {
        "winning_lanes": [
            {
                "lane": "Research Copilot",
                "string_ids": [2],
                "candidate_examples": ["Mithun Azhagappan"],
                "evidence": "Highest absolute save count.",
                "why_it_worked": "Workflow-specific product language gated for real builders.",
                "recommended_action": "Promote this lane early.",
            }
        ],
        "underperforming_lanes": [
            {
                "lane": "Surveillance",
                "string_ids": [8],
                "issue": "Traditional rules-engine noise.",
                "evidence": "Zero saves across two pages.",
                "recommended_action": "Only run with explicit GenAI AND-gate.",
            }
        ],
        "coverage_gaps": [
            {
                "gap": "Payments",
                "why_it_matters": "No explicit payments string was run.",
                "suggested_search_strategy": "Add transaction-banking and payment-orchestration strings.",
            }
        ],
        "noise_patterns": [
            {
                "pattern": "Product leadership without builder depth",
                "evidence": "Multiple CPTO and product-heavy AI officer profiles rejected.",
                "mitigation": "Strengthen builder verb gating.",
            }
        ],
        "saved_candidate_patterns": {
            "standout_candidates": [{"name": "Mithun Azhagappan", "why": "Goldman AI platform architect."}],
            "common_employers": [{"employer": "JPMorgan", "count": 5, "note": "Strong GenAI convert population."}],
            "common_titles": [{"title_family": "Executive Director", "count": 2, "note": "Right seniority band."}],
            "archetype_distribution": [{"archetype": "BFSI-native GenAI converts", "count": 6, "note": "Most common save type."}],
            "seniority_notes": ["Many VP-level bank builders were interesting but below full lab-leadership scope."],
        },
        "adaptation_assessment": {
            "summary": "Adaptation concentrated effort on productive workflow language.",
            "effective_refinements": ["Narrowing workflow strings improved precision."],
            "questionable_or_skipped": ["Regulatory reporting was skipped and should return."],
            "operational_notes": ["Keep tight strings over broad archetype-first nets."],
        },
        "recommendations": {
            "try_next": ["Payments and transaction-banking builders"],
            "avoid_next": ["Ungated surveillance strings"],
            "prioritize_pipeline": ["Engage Mithun Azhagappan immediately"],
        },
        "brief_iteration_hints": {
            "instructions": ["Cover payments and regulatory reporting in the first block."],
            "search_priorities": ["Payments and transaction-banking builders"],
            "additional_search_terms": ["payment orchestration", "transaction banking"],
            "intake_notes": "The latest run validated research-copilot lanes and exposed a payments gap.",
            "depth_distinction": {
                "builder_definition": "Still a BFSI executive-builder role.",
                "user_definition": "Product and strategy leaders remain non-fits.",
                "edge_case_guidance": "Bank VP profiles require extra scope scrutiny.",
            },
            "non_fit_patterns": [
                {
                    "label": "Product-heavy AI officer",
                    "description": "Executive AI product leadership without builder authorship.",
                    "why_not": "Wrong depth for the role.",
                    "examples": ["Chief Product & AI Officer"],
                }
            ],
            "minimum_bar_description": "NYC, 15+ years, BFSI, and post-2022 GenAI remain hard requirements.",
            "facial_calibration": {
                "expected_yes_rate_low": 0.1,
                "expected_yes_rate_high": 0.22,
                "fast_exit_patterns": ["Pure product history"],
                "trajectory_yes_patterns": ["Big-bank GenAI convert"],
                "trajectory_ambiguous_patterns": ["VP at smaller firm"],
                "trajectory_no_patterns": ["Vendor field CTO without build ownership"],
            },
            "employer_signal_rules": [
                {
                    "tier": "payments_builder",
                    "employer_patterns": ["Visa", "Mastercard"],
                    "evidence_required": "Still requires production builder evidence.",
                    "save_on_employer_alone": False,
                }
            ],
            "calibration_examples": {
                "strong_saves": [{"name": "Mithun Azhagappan", "why": "Strong fit."}],
                "incorrect_saves": [{"name": "Deepinder Gulati", "why": "Product-heavy."}],
                "borderline_verify": [{"name": "Peter Chung", "why": "Check scope carefully."}],
            },
            "notes": "Promote payments in the next revision.",
            "locked_field_cautions": ["Do not relax geography or years-of-experience gates."],
        },
    }


def test_run_report_schema_round_trips_and_renders_markdown():
    analysis = RunDebriefAnalysis.from_dict(_analysis_dict())
    report = StructuredRunReport.from_parts(_snapshot(), analysis)
    round_tripped = StructuredRunReport.from_dict(report.to_dict())

    markdown = render_run_report_markdown(round_tripped)

    assert round_tripped.run_metadata["role_title"] == "Head of Applied AI Lab"
    assert round_tripped.winning_lanes[0]["lane"] == "Research Copilot"
    assert "Mithun Azhagappan" in markdown
    assert "Payments" in markdown
    assert "Ungated surveillance strings" in markdown


def test_run_debrief_analysis_rejects_missing_required_keys():
    try:
        RunDebriefAnalysis.from_dict({"winning_lanes": []})
    except ValueError as exc:
        assert "missing keys" in str(exc)
    else:
        raise AssertionError("Expected RunDebriefAnalysis.from_dict to reject incomplete data")
