"""Tests for bounded draft-brief iteration from structured run reports."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from shared.brief_iteration import iterate_brief_draft
from shared.brief_loader import load_brief
from shared.storage import read_json, write_json


ROOT = Path(__file__).parent.parent
SOURCE_BRIEF = ROOT / "config" / "brief-head-ai-lab-nyc-v2.json"


def _report_dict() -> dict:
    return {
        "schema_version": 1,
        "run_metadata": {
            "role_title": "Head of Applied AI Lab",
            "brief_name": "head-ai-lab",
            "brief_version": "2.1",
            "linkedin_project": "Head of Applied AI Lab",
            "linkedin_project_id": "1957683706",
            "generated_at": "2026-04-06T12:00:00+00:00",
            "overall_summary": "Structured debrief input for draft-brief generation.",
        },
        "metrics_summary": {
            "strings_executed": 8,
            "strings_skipped": 3,
            "total_results": 2200,
            "total_pages_reviewed": 19,
            "candidates_evaluated": 180,
            "facial_yes": 40,
            "facial_no": 140,
            "saved": 12,
            "rejected": 28,
            "overall_save_rate": 0.0667,
            "facial_yes_rate": 0.2222,
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
                "facial_yes_count": 10,
                "facial_no_count": 12,
                "candidates_count": 22,
                "duplicates_count": 1,
                "family_key": "research_copilot_asset_mgmt",
                "novelty_bucket": "edge_case",
                "domain_lane": "asset_management",
            }
        ],
        "winning_lanes": [
            {
                "lane": "Research copilot / asset management",
                "string_ids": [2],
                "candidate_examples": ["Mithun Azhagappan"],
                "evidence": "Highest absolute save count in the run.",
                "why_it_worked": "Specific workflow language filtered for real builders.",
                "recommended_action": "Promote this lane earlier.",
            }
        ],
        "underperforming_lanes": [
            {
                "lane": "Surveillance",
                "string_ids": [8],
                "issue": "Mostly traditional compliance-tech noise.",
                "evidence": "Zero saves after two pages.",
                "recommended_action": "Only retry with an explicit GenAI AND-gate.",
            }
        ],
        "coverage_gaps": [
            {
                "gap": "Payments",
                "why_it_matters": "The run never explicitly targeted payments or transaction banking.",
                "suggested_search_strategy": "Add payment-orchestration, RTP, and merchant-risk strings.",
            }
        ],
        "noise_patterns": [
            {
                "pattern": "Product-heavy AI leadership",
                "evidence": "Several product/strategy AI officers failed the builder bar.",
                "mitigation": "Strengthen builder-authorship and systems language.",
            }
        ],
        "saved_candidate_patterns": {
            "standout_candidates": [{"name": "Mithun Azhagappan", "why": "Goldman AI platform architect."}],
            "common_employers": [{"employer": "JPMorgan", "count": 3, "note": "Strong bank GenAI-convert population."}],
            "common_titles": [{"title_family": "Executive Director", "count": 2, "note": "Right scope band."}],
            "archetype_distribution": [{"archetype": "BFSI-native GenAI converts", "count": 6, "note": "Dominant save archetype."}],
            "seniority_notes": ["VP bank builders were often technically strong but below the final scope bar."],
        },
        "adaptation_assessment": {
            "summary": "Tight workflow strings outperformed broad archetype-first strings.",
            "effective_refinements": ["Research-copilot phrasing materially improved signal."],
            "questionable_or_skipped": ["Payments remained under-covered."],
            "operational_notes": ["Keep early strings narrow and workflow-specific."],
        },
        "recommendations": {
            "try_next": ["Payments and transaction-banking builders"],
            "avoid_next": ["Ungated surveillance strings"],
            "prioritize_pipeline": ["Mithun Azhagappan"],
        },
        "brief_iteration_hints": {
            "instructions": ["Cover payments and regulatory reporting in the first block."],
            "search_priorities": [
                "Payments / transaction-banking / fraud / real-time-payments builders",
                "Research copilot / asset-management / investment-workflow builders",
            ],
            "additional_search_terms": ["payment orchestration", "transaction banking", "FedNow"],
            "intake_notes": "The latest run validated research-copilot lanes and exposed a payments gap.",
            "depth_distinction": {
                "builder_definition": "This remains a BFSI executive-builder search.",
                "user_definition": "Strategy and product-only AI leaders remain out of scope.",
                "edge_case_guidance": "VP bank builders need extra scope scrutiny before saving.",
            },
            "non_fit_patterns": [
                {
                    "label": "Product-heavy AI officer",
                    "description": "Executive AI product leadership without system-builder authorship.",
                    "why_not": "Wrong depth for this role.",
                    "examples": ["Chief Product & AI Officer"],
                }
            ],
            "minimum_bar_description": "Maintain the executive-builder bar while making payments a first-class lane.",
            "facial_calibration": {
                "expected_yes_rate_low": 0.02,
                "expected_yes_rate_high": 0.95,
                "fast_exit_patterns": ["Pure product history"],
                "trajectory_yes_patterns": ["Big-bank GenAI convert"],
                "trajectory_ambiguous_patterns": ["VP at smaller firm"],
                "trajectory_no_patterns": ["Vendor field CTO without build ownership"],
            },
            "employer_signal_rules": [
                {
                    "tier": "payments_builder",
                    "employer_patterns": ["Visa", "Mastercard", "Fiserv"],
                    "evidence_required": "Still requires production builder evidence.",
                    "save_on_employer_alone": False,
                }
            ],
            "calibration_examples": {
                "strong_saves": [{"name": "Mithun Azhagappan", "why": "Top save from the run."}],
                "incorrect_saves": [{"name": "Deepinder Gulati", "why": "Product-heavy AI leadership without builder depth."}],
                "borderline_verify": [{"name": "Peter Chung", "why": "Scope needs verification despite strong builder evidence."}],
            },
            "notes": "Promote payments in the next revision.",
            "locked_field_cautions": ["Do not relax geography or years-of-experience gates."],
        },
    }


def test_iterate_brief_generates_valid_draft_and_preserves_locked_fields():
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        brief_path = td_path / SOURCE_BRIEF.name
        report_path = td_path / "run-report.json"
        output_dir = td_path / "output"

        brief_raw = read_json(SOURCE_BRIEF)
        write_json(brief_path, brief_raw)
        write_json(report_path, _report_dict())

        proposal = {
            "summary": "Promote payments while preserving the hard bar.",
            "proposed_changes": {
                "instructions": [
                    "Cover payments and regulatory reporting in the first block.",
                    "Cover payments and regulatory reporting in the first block.",
                ],
                "search_priorities": [
                    "Payments / transaction-banking / fraud / real-time-payments builders",
                    "Research copilot / asset-management / investment-workflow builders",
                    "Payments / transaction-banking / fraud / real-time-payments builders",
                ],
                "additional_search_terms": [
                    "payment orchestration",
                    "payment orchestration",
                    "transaction banking",
                ],
                "minimum_bar_description": "Maintain the executive-builder bar while widening payments coverage.",
                "facial_calibration": {
                    "expected_yes_rate_low": 0.0,
                    "expected_yes_rate_high": 0.95,
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
                        "save_on_employer_alone": True,
                    }
                ],
                "notes": "Drafted from market intel.",
                "version": "999",
                "geography": "London",
            },
            "changed_fields": [
                {
                    "field": "search_priorities",
                    "why": "Payments was a clear coverage gap.",
                    "evidence": ["Run report identified payments as a high-priority gap."],
                    "expected_effects": ["Earlier coverage of payments and transaction-banking builders."],
                }
            ],
            "warnings": ["Model-side warning placeholder."],
        }

        with patch("shared.brief_iteration.opus_llm", return_value=proposal):
            result = iterate_brief_draft(
                brief_path=brief_path,
                report_path=str(report_path),
                output_dir=str(output_dir),
            )

        draft_raw = read_json(result.draft_brief_path)
        draft_brief = load_brief(result.draft_brief_path)

        assert result.draft_brief_path.exists()
        assert result.rationale_path.exists()
        assert draft_raw["version"] == "2.2-draft"
        assert result.draft_brief_path.name == "brief-head-ai-lab-nyc-v2.2-draft.json"
        assert draft_raw["geography"] == brief_raw["geography"]
        assert draft_raw["minimum_years_experience"] == brief_raw["minimum_years_experience"]
        assert draft_raw["market_density"] == brief_raw["market_density"]
        assert draft_raw["search_priorities"][0].startswith("Payments / transaction-banking")
        assert draft_raw["additional_search_terms"].count("payment orchestration") == 1
        assert all(rule["save_on_employer_alone"] is False for rule in draft_raw["employer_signal_rules"])
        assert abs(
            draft_raw["facial_calibration"]["expected_yes_rate_low"] - brief_raw["facial_calibration"]["expected_yes_rate_low"]
        ) <= 0.10
        assert abs(
            draft_raw["facial_calibration"]["expected_yes_rate_high"] - brief_raw["facial_calibration"]["expected_yes_rate_high"]
        ) <= 0.10
        assert draft_brief.has_v2_schema is True
        assert "Locked Fields Preserved" in result.rationale_markdown
        assert "Facial calibration deltas were clamped" in result.rationale_markdown


def test_iterate_brief_emits_heuristic_gap_warnings_for_unrecognized_terms():
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        brief_path = td_path / SOURCE_BRIEF.name
        report_path = td_path / "run-report.json"
        output_dir = td_path / "output"

        write_json(brief_path, read_json(SOURCE_BRIEF))
        write_json(report_path, _report_dict())

        proposal = {
            "summary": "Test heuristic gap warnings.",
            "proposed_changes": {
                "additional_search_terms": ["novel workflow lattice"],
                "search_priorities": ["Exotic ledger lattice builders"],
                "notes": "Testing warnings.",
            },
            "changed_fields": [],
            "warnings": [],
        }

        with patch("shared.brief_iteration.opus_llm", return_value=proposal):
            result = iterate_brief_draft(
                brief_path=brief_path,
                report_path=str(report_path),
                output_dir=str(output_dir),
            )

        assert any("novel workflow lattice" in warning for warning in result.warnings)
        assert any("Exotic ledger lattice builders" in warning for warning in result.warnings)
        assert "Warnings" in result.rationale_markdown
