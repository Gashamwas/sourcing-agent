"""Tests for bounded draft-brief iteration from structured run reports."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from market_intelligence.engine import resolve_market_intel_artifact_path
from shared.brief_iteration import (
    _build_iteration_user_prompt,
    _draft_brief_path,
    _derive_next_draft_version,
    iterate_brief_draft,
)
from shared.brief_loader import load_brief
from shared.llm_usage import record_llm_usage
from shared.run_report_schema import StructuredRunReport
from shared.storage import read_json, read_jsonl, write_json


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


def test_iterate_brief_writes_token_cost_log():
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        brief_path = td_path / SOURCE_BRIEF.name
        report_path = td_path / "run-report.json"
        output_dir = td_path / "output"

        write_json(brief_path, read_json(SOURCE_BRIEF))
        write_json(report_path, _report_dict())

        def _fake_opus(
            system_prompt: str,
            user_prompt: str,
            expect_json: bool = True,
            max_tokens: int = 12000,
            usage_context: dict | None = None,
        ):
            record_llm_usage(
                provider="anthropic",
                model="claude-opus-4-6",
                usage={"input_tokens": 1200, "output_tokens": 250},
                request={"system_prompt_chars": len(system_prompt), "user_prompt_chars": len(user_prompt)},
                usage_context=usage_context,
            )
            return {
                "summary": "Tighten the next draft.",
                "proposed_changes": {"additional_search_terms": ["payment orchestration"]},
                "changed_fields": ["additional_search_terms"],
                "warnings": [],
            }

        with patch("shared.brief_iteration.opus_llm", side_effect=_fake_opus):
            iterate_brief_draft(
                brief_path=brief_path,
                report_path=str(report_path),
                output_dir=str(output_dir),
            )

        usage_log = output_dir / "brief-iteration-token-cost-log.jsonl"
        records = read_jsonl(usage_log)
        assert records
        assert records[0]["pipeline"] == "brief_iteration"
        assert records[0]["stage"] == "brief_iteration_proposal"
        assert records[0]["input_tokens"] == 1200


def test_iterate_brief_retries_with_tighter_prompt_on_truncation():
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        brief_path = td_path / SOURCE_BRIEF.name
        report_path = td_path / "run-report.json"
        output_dir = td_path / "output"

        write_json(brief_path, read_json(SOURCE_BRIEF))
        write_json(report_path, _report_dict())

        calls: list[dict] = []

        def _fake_opus(
            system_prompt: str,
            user_prompt: str,
            expect_json: bool = True,
            max_tokens: int = 12000,
            usage_context: dict | None = None,
        ):
            calls.append(
                {
                    "chars": len(user_prompt),
                    "max_tokens": max_tokens,
                    "attempt": (usage_context or {}).get("attempt"),
                }
            )
            if len(calls) == 1:
                raise RuntimeError(
                    "Opus response truncated: stop_reason=max_tokens. Increase max_tokens or reduce prompt size."
                )
            return {
                "summary": "Retry succeeded.",
                "proposed_changes": {"additional_search_terms": ["payment orchestration"]},
                "changed_fields": ["additional_search_terms"],
                "warnings": [],
            }

        with patch("shared.brief_iteration.opus_llm", side_effect=_fake_opus):
            result = iterate_brief_draft(
                brief_path=brief_path,
                report_path=str(report_path),
                output_dir=str(output_dir),
            )

        assert result.draft_brief["additional_search_terms"] == ["payment orchestration"]
        assert len(calls) == 2
        assert calls[0]["attempt"] == "initial"
        assert calls[1]["attempt"] == "tight_retry"
        assert calls[1]["chars"] < calls[0]["chars"]
        assert calls[1]["max_tokens"] == 16000


def test_build_iteration_prompt_uses_compact_views():
    brief_raw = read_json(SOURCE_BRIEF)
    report = StructuredRunReport.from_dict(_report_dict())
    prompt = _build_iteration_user_prompt(
        brief_raw,
        report,
        search_memory=None,
        final_judgments_summary=None,
        market_intel_summary=None,
        allow_retrieval_design_edits=False,
        tight=False,
    )

    assert '"prompt_mode": "standard"' in prompt
    assert '"top_string_performance"' in prompt
    assert '"coverage_gaps"' in prompt
    assert '"depth_distinction"' in prompt
    assert '"non_fit_patterns"' in prompt
    assert '"facial_calibration"' in prompt
    assert '"employer_signal_rules"' in prompt
    assert '"calibration_examples"' in prompt
    assert len(prompt) < len(json.dumps(report.to_dict(), indent=2)) + len(json.dumps(brief_raw, indent=2))


def test_build_iteration_prompt_uses_derived_legacy_views_for_explicit_retrieval_design():
    brief_raw = read_json(SOURCE_BRIEF)
    brief_raw["search_priorities"] = ["stale raw priority"]
    brief_raw["additional_search_terms"] = ["stale raw term"]
    brief_raw["retrieval_design"] = {
        "families": [
            {
                "family_id": "payments_builders",
                "label": "Payments builders",
                "objective": "Open payments-adjacent builder lanes.",
                "priority": 90,
                "enabled": True,
                "variants_to_emit": 1,
                "entry_signals": [
                    {"item_id": "entry_payments", "label": "Payments", "terms": ["payments platform"]}
                ],
                "capability_proxies": [
                    {"item_id": "cap_orchestration", "label": "Orchestration", "terms": ["payment orchestration"]}
                ],
                "reality_filters": [
                    {"item_id": "real_prod", "label": "Reality", "terms": ["production"]}
                ],
                "context_constraints": [],
                "anti_noise": [],
            }
        ],
        "shared_layers": {},
        "edge_case_hypotheses": [],
    }
    report = StructuredRunReport.from_dict(_report_dict())
    prompt = _build_iteration_user_prompt(
        brief_raw,
        report,
        search_memory=None,
        final_judgments_summary=None,
        market_intel_summary=None,
        allow_retrieval_design_edits=True,
        tight=False,
    )

    assert "Payments builders" in prompt
    assert "payment orchestration" in prompt
    assert "stale raw priority" not in prompt
    assert "stale raw term" not in prompt


def test_run_report_prompt_summary_ranks_strings_by_signal_not_raw_order():
    payload = _report_dict()
    payload["string_performance"] = [
        {
            "string_id": 1,
            "name": "weak first",
            "status": "done",
            "result_count": 500,
            "pages_reviewed": 4,
            "saves": 0,
            "save_rate": 0.0,
            "candidates_count": 20,
            "family_key": "weak",
            "novelty_bucket": "canonical",
            "domain_lane": "general",
            "notes": "first by order only",
        },
        {
            "string_id": 99,
            "name": "strong later",
            "status": "done",
            "result_count": 120,
            "pages_reviewed": 3,
            "saves": 9,
            "save_rate": 0.12,
            "candidates_count": 30,
            "family_key": "strong",
            "novelty_bucket": "edge_case",
            "domain_lane": "payments",
            "notes": "should rank first",
        },
    ]
    report = StructuredRunReport.from_dict(payload)
    prompt = _build_iteration_user_prompt(
        read_json(SOURCE_BRIEF),
        report,
        search_memory=None,
        final_judgments_summary=None,
        market_intel_summary=None,
        allow_retrieval_design_edits=False,
        tight=False,
    )

    strong_idx = prompt.find("strong later")
    weak_idx = prompt.find("weak first")
    assert strong_idx != -1 and weak_idx != -1
    assert strong_idx < weak_idx


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
        expected_version = _derive_next_draft_version(str(brief_raw.get("version", "")))
        assert draft_raw["version"] == expected_version
        assert result.draft_brief_path.name == _draft_brief_path(brief_path, expected_version).name
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


def test_iterate_brief_includes_market_intel_summary_when_present():
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        brief_path = td_path / SOURCE_BRIEF.name
        report_path = td_path / "run-report.json"
        output_dir = td_path / "output"

        write_json(brief_path, read_json(SOURCE_BRIEF))
        write_json(report_path, _report_dict())
        artifact_path = resolve_market_intel_artifact_path(
            brief_path,
            output_dir=output_dir,
        )
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        write_json(
            artifact_path,
            {
                "schema_version": 1,
                "artifact_version": 1,
                "market_identity": {
                    "market_key": "head_of_applied_ai_lab__nyc__l8_l9",
                    "role_title": "Head of Applied AI Lab",
                    "role_level": "L8/L9",
                    "geography": "NYC",
                    "channels_seen": ["linkedin"],
                    "brief_ids_seen": ["1957683706"],
                    "brief_versions_seen": ["2.1"],
                },
                "freshness": {
                    "artifact_updated_at": "2026-04-10T12:00:00+00:00",
                    "internal_data_through": "2026-04-10T12:00:00+00:00",
                    "external_research_through": "2026-04-10T12:00:00+00:00",
                    "staleness_days": 0,
                },
                "evidence_index": {"runs": [], "external_sources": []},
                "aggregate_metrics": {
                    "run_count": 1,
                    "saved_count": 10,
                    "rejected_count": 20,
                    "facial_yes_rate": 0.2,
                    "save_rate": 0.05,
                    "candidate_volume_by_channel": {"linkedin": 200},
                },
                "channel_summaries": {},
                "lane_intelligence": [],
                "talent_pool_intelligence": [],
                "noise_patterns": [],
                "employer_signal_intelligence": [],
                "candidate_signal_summary": {
                    "standout_signals": [],
                    "borderline_signals": [],
                    "disqualifying_signals": [],
                },
                "market_thesis": {
                    "summary": "The latest run likely missed payments-adjacent builder titles.",
                    "supply_assessment": "moderate",
                    "competition_assessment": "high",
                    "external_context": [],
                },
                "brief_recommendations": [
                    {
                        "recommendation_id": "rec-payments-titles",
                        "target_field": "additional_search_terms",
                        "proposal": "Payments AI platform, transaction banking, real-time payments",
                        "reason": "Market intel found a payments-adjacent blind spot.",
                        "supporting_run_refs": ["linkedin:output"],
                        "confidence": 0.82,
                    }
                ],
                "open_questions": [
                    {
                        "question": "Are payments-platform builders a stronger adjacent pool than research-copilot builders?",
                        "priority": "high",
                        "next_step": "Run one payments-adjacent test lane.",
                        "supporting_run_refs": ["linkedin:output"],
                    }
                ],
                "section_generation_metadata": {},
                "delta_since_last_run": {
                    "became_more_true": [],
                    "became_less_true": [],
                    "still_uncertain": [],
                    "next_run_changes": [
                        "Add payments-adjacent title families to the next run."
                    ],
                },
            },
        )

        captured: dict[str, str] = {}

        def _fake_opus(
            system_prompt: str,
            user_prompt: str,
            expect_json: bool = True,
            max_tokens: int = 12000,
            usage_context: dict | None = None,
        ):
            captured["user_prompt"] = user_prompt
            return {
                "summary": "Use market intel in the draft.",
                "proposed_changes": {
                    "additional_search_terms": ["payment orchestration"],
                },
                "changed_fields": [],
                "warnings": [],
            }

        with patch("shared.brief_iteration.opus_llm", side_effect=_fake_opus):
            iterate_brief_draft(
                brief_path=brief_path,
                report_path=str(report_path),
                output_dir=str(output_dir),
            )

        assert '"market_intel_summary"' in captured["user_prompt"]
        assert "payments-adjacent blind spot" in captured["user_prompt"]


def test_iterate_brief_filters_internal_market_intel_next_run_changes():
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        brief_path = td_path / SOURCE_BRIEF.name
        report_path = td_path / "run-report.json"
        output_dir = td_path / "output"

        write_json(brief_path, read_json(SOURCE_BRIEF))
        write_json(report_path, _report_dict())
        artifact_path = resolve_market_intel_artifact_path(
            brief_path,
            output_dir=output_dir,
        )
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        write_json(
            artifact_path,
            {
                "schema_version": 1,
                "artifact_version": 1,
                "market_identity": {
                    "market_key": "head_of_applied_ai_lab__nyc__l8_l9",
                    "role_title": "Head of Applied AI Lab",
                    "role_level": "L8/L9",
                    "geography": "NYC",
                    "channels_seen": ["linkedin"],
                    "brief_ids_seen": ["1957683706"],
                    "brief_versions_seen": ["2.1"],
                },
                "freshness": {
                    "artifact_updated_at": "2026-04-10T12:00:00+00:00",
                    "internal_data_through": "2026-04-10T12:00:00+00:00",
                    "external_research_through": "2026-04-10T12:00:00+00:00",
                    "staleness_days": 0,
                },
                "evidence_index": {"runs": [], "external_sources": []},
                "aggregate_metrics": {
                    "run_count": 1,
                    "saved_count": 10,
                    "rejected_count": 20,
                    "facial_yes_rate": 0.2,
                    "save_rate": 0.05,
                    "candidate_volume_by_channel": {"linkedin": 200},
                },
                "channel_summaries": {},
                "lane_intelligence": [],
                "talent_pool_intelligence": [],
                "noise_patterns": [],
                "employer_signal_intelligence": [],
                "candidate_signal_summary": {
                    "standout_signals": [],
                    "borderline_signals": [],
                    "disqualifying_signals": [],
                },
                "market_thesis": {
                    "summary": "The latest run suggests a field-engineering blind spot.",
                    "supply_assessment": "moderate",
                    "competition_assessment": "high",
                    "external_context": [],
                },
                "brief_recommendations": [],
                "open_questions": [],
                "section_generation_metadata": {},
                "delta_since_last_run": {
                    "became_more_true": [],
                    "became_less_true": [],
                    "still_uncertain": [],
                    "next_run_changes": [
                        "CRITICAL: Restore lane_intelligence from both runs' deterministic data — the draft regression to empty must be fixed",
                        "Add field-engineering and technical-success title families to the next run.",
                    ],
                },
            },
        )

        captured: dict[str, str] = {}

        def _fake_opus(
            system_prompt: str,
            user_prompt: str,
            expect_json: bool = True,
            max_tokens: int = 12000,
            usage_context: dict | None = None,
        ):
            captured["user_prompt"] = user_prompt
            return {
                "summary": "Use only operator-actionable market intel.",
                "proposed_changes": {"additional_search_terms": ["field engineering"]},
                "changed_fields": [],
                "warnings": [],
            }

        with patch("shared.brief_iteration.opus_llm", side_effect=_fake_opus):
            iterate_brief_draft(
                brief_path=brief_path,
                report_path=str(report_path),
                output_dir=str(output_dir),
            )

        assert "field-engineering and technical-success title families" in captured["user_prompt"]
        assert "Restore lane_intelligence" not in captured["user_prompt"]


def test_iterate_brief_can_apply_retrieval_design_and_derive_legacy_views():
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        brief_path = td_path / SOURCE_BRIEF.name
        report_path = td_path / "run-report.json"
        output_dir = td_path / "output"

        brief_raw = read_json(SOURCE_BRIEF)
        brief_raw["retrieval_design"] = {
            "families": [
                {
                    "family_id": "existing_family",
                    "label": "Existing family",
                    "objective": "Explicit layered retrieval mode for this draft.",
                    "priority": 50,
                    "enabled": True,
                    "variants_to_emit": 1,
                    "entry_signals": [
                        {"item_id": "entry_existing", "label": "Existing", "terms": ["research copilot"]}
                    ],
                    "capability_proxies": [
                        {"item_id": "cap_existing", "label": "Capability", "terms": ["production ai workflow"]}
                    ],
                    "reality_filters": [],
                    "context_constraints": [],
                    "anti_noise": [],
                }
            ],
            "shared_layers": {},
            "edge_case_hypotheses": [],
        }
        write_json(brief_path, brief_raw)
        write_json(report_path, _report_dict())

        proposal = {
            "summary": "Switch to layered retrieval design.",
            "proposed_changes": {
                "retrieval_design": {
                    "families": [
                        {
                            "family_id": "payments_builders",
                            "label": "Payments builders",
                            "objective": "Open payments and transaction-banking builder lanes.",
                            "priority": 90,
                            "enabled": True,
                            "variants_to_emit": 1,
                            "entry_signals": [
                                {
                                    "item_id": "entry_payments",
                                    "label": "Payments personas",
                                    "terms": ["payments platform", "transaction banking"],
                                }
                            ],
                            "capability_proxies": [
                                {
                                    "item_id": "cap_orchestration",
                                    "label": "Workflow builders",
                                    "terms": ["payment orchestration", "fraud workflow"],
                                }
                            ],
                            "reality_filters": [
                                {
                                    "item_id": "real_go_live",
                                    "label": "Production proof",
                                    "terms": ["production", "go-live"],
                                }
                            ],
                            "context_constraints": [],
                            "anti_noise": [],
                            "hypothesis_ids": ["payments_hidden_pool"],
                        }
                    ],
                    "shared_layers": {},
                    "edge_case_hypotheses": [
                        {
                            "hypothesis_id": "payments_hidden_pool",
                            "label": "Payments hidden pool",
                            "hidden_cohort": "Payments-platform builders who do not use AI-leadership titles",
                            "why_missed": "They present through workflow and platform language rather than executive AI language.",
                            "entry_signal_variants": [
                                {
                                    "item_id": "hyp_entry_payments",
                                    "label": "Payments platform language",
                                    "terms": ["merchant acquiring", "payments modernization"],
                                }
                            ],
                            "capability_proxy_variants": [],
                            "reality_filter_variants": [],
                            "context_constraint_variants": [],
                            "anti_noise_variants": [],
                            "noise_risks": ["Pure operations leaders"],
                            "validation_rule": "Promote only after repeated strong saves.",
                        }
                    ],
                },
                "notes": "Use the retrieval-design path.",
            },
            "changed_fields": [
                {
                    "field": "retrieval_design",
                    "why": "The next run should operate in family/layer space.",
                    "evidence": [],
                    "expected_effects": [],
                }
            ],
            "warnings": [],
        }

        with patch("shared.brief_iteration.opus_llm", return_value=proposal):
            result = iterate_brief_draft(
                brief_path=brief_path,
                report_path=str(report_path),
                output_dir=str(output_dir),
            )

        draft_raw = read_json(result.draft_brief_path)
        assert "retrieval_design" in draft_raw
        assert draft_raw["retrieval_design"]["families"][0]["family_id"] == "payments_builders"
        assert any("Payments builders" in item for item in draft_raw["search_priorities"])
        assert "payment orchestration" in draft_raw["additional_search_terms"]


def test_iterate_brief_rejects_invalid_explicit_retrieval_design_proposals():
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        brief_path = td_path / SOURCE_BRIEF.name
        report_path = td_path / "run-report.json"
        output_dir = td_path / "output"

        brief_raw = read_json(SOURCE_BRIEF)
        brief_raw["retrieval_design"] = {
            "families": [
                {
                    "family_id": "existing_family",
                    "label": "Existing family",
                    "objective": "Explicit layered retrieval mode for this draft.",
                    "priority": 50,
                    "enabled": True,
                    "variants_to_emit": 1,
                    "entry_signals": [
                        {"item_id": "entry_existing", "label": "Existing", "terms": ["research copilot"]}
                    ],
                    "capability_proxies": [
                        {"item_id": "cap_existing", "label": "Capability", "terms": ["production ai workflow"]}
                    ],
                    "reality_filters": [
                        {"item_id": "real_existing", "label": "Reality", "terms": ["production"]}
                    ],
                    "context_constraints": [],
                    "anti_noise": [],
                }
            ],
            "shared_layers": {},
            "edge_case_hypotheses": [],
        }
        write_json(brief_path, brief_raw)
        write_json(report_path, _report_dict())

        proposal = {
            "summary": "Introduce a malformed hidden-pool hypothesis.",
            "proposed_changes": {
                "retrieval_design": {
                    "families": [
                        {
                            "family_id": "payments_builders",
                            "label": "Payments builders",
                            "objective": "Open payments and transaction-banking builder lanes.",
                            "priority": 90,
                            "enabled": True,
                            "variants_to_emit": 1,
                            "entry_signals": [
                                {
                                    "item_id": "entry_payments",
                                    "label": "Payments personas",
                                    "terms": ["payments platform", "transaction banking"],
                                }
                            ],
                            "capability_proxies": [
                                {
                                    "item_id": "cap_orchestration",
                                    "label": "Workflow builders",
                                    "terms": ["payment orchestration", "fraud workflow"],
                                }
                            ],
                            "reality_filters": [],
                            "context_constraints": [],
                            "anti_noise": [],
                            "hypothesis_ids": ["payments_hidden_pool"],
                        }
                    ],
                    "shared_layers": {},
                    "edge_case_hypotheses": [
                        {
                            "hypothesis_id": "payments_hidden_pool",
                            "label": "Payments hidden pool",
                            "hidden_cohort": "Payments-platform builders who do not use AI-leadership titles",
                            "why_missed": "They present through workflow and platform language rather than executive AI language.",
                            "entry_signal_variants": [],
                            "capability_proxy_variants": [],
                            "reality_filter_variants": [],
                            "context_constraint_variants": [],
                            "anti_noise_variants": [],
                            "noise_risks": ["Pure operations leaders"],
                            "validation_rule": "Promote only after repeated strong saves.",
                        }
                    ],
                }
            },
            "changed_fields": [],
            "warnings": [],
        }

        with patch("shared.brief_iteration.opus_llm", return_value=proposal):
            try:
                iterate_brief_draft(
                    brief_path=brief_path,
                    report_path=str(report_path),
                    output_dir=str(output_dir),
                )
            except ValueError as exc:
                assert "Invalid explicit retrieval_design" in str(exc)
                assert "does not perturb any retrieval layer" in str(exc)
            else:
                raise AssertionError("Expected invalid explicit retrieval_design to fail loudly")


def test_iterate_brief_explicit_retrieval_design_is_not_replaced_by_legacy_search_edits():
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        brief_path = td_path / SOURCE_BRIEF.name
        report_path = td_path / "run-report.json"
        output_dir = td_path / "output"

        brief_raw = read_json(SOURCE_BRIEF)
        explicit_design = {
            "families": [
                {
                    "family_id": "existing_family",
                    "label": "Existing family",
                    "objective": "Explicit layered retrieval mode for this draft.",
                    "priority": 50,
                    "enabled": True,
                    "variants_to_emit": 1,
                    "entry_signals": [
                        {"item_id": "entry_existing", "label": "Existing", "terms": ["research copilot"]}
                    ],
                    "capability_proxies": [
                        {"item_id": "cap_existing", "label": "Capability", "terms": ["production ai workflow"]}
                    ],
                    "reality_filters": [
                        {"item_id": "real_existing", "label": "Reality", "terms": ["production"]}
                    ],
                    "context_constraints": [],
                    "anti_noise": [],
                }
            ],
            "shared_layers": {},
            "edge_case_hypotheses": [],
        }
        brief_raw["retrieval_design"] = explicit_design
        write_json(brief_path, brief_raw)
        write_json(report_path, _report_dict())

        proposal = {
            "summary": "Try to update only legacy search fields.",
            "proposed_changes": {
                "search_priorities": [
                    "Payments / transaction-banking / fraud / real-time-payments builders",
                ],
                "additional_search_terms": [
                    "payment orchestration",
                    "FedNow",
                ],
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

        draft_raw = read_json(result.draft_brief_path)
        assert draft_raw["retrieval_design"]["families"][0]["family_id"] == "existing_family"
        assert any("Existing family" in item for item in draft_raw["search_priorities"])
        assert "research copilot" in draft_raw["additional_search_terms"]
        assert any(
            "explicit retrieval_design mode" in warning.lower()
            for warning in result.warnings
        )


def test_iterate_brief_legacy_brief_does_not_silently_upgrade_to_explicit_retrieval_design():
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        brief_path = td_path / SOURCE_BRIEF.name
        report_path = td_path / "run-report.json"
        output_dir = td_path / "output"

        write_json(brief_path, read_json(SOURCE_BRIEF))
        write_json(report_path, _report_dict())

        proposal = {
            "summary": "Try to switch to layered retrieval.",
            "proposed_changes": {
                "retrieval_design": {
                    "families": [
                        {
                            "family_id": "should_be_ignored",
                            "label": "Ignored family",
                            "objective": "Should not be accepted on a legacy brief.",
                            "priority": 90,
                            "enabled": True,
                            "variants_to_emit": 1,
                            "entry_signals": [
                                {"item_id": "entry_ignore", "label": "Ignore", "terms": ["payments platform"]}
                            ],
                            "capability_proxies": [
                                {"item_id": "cap_ignore", "label": "Ignore", "terms": ["payment orchestration"]}
                            ],
                            "reality_filters": [],
                            "context_constraints": [],
                            "anti_noise": [],
                        }
                    ],
                    "shared_layers": {},
                    "edge_case_hypotheses": [],
                },
                "search_priorities": [
                    "Payments / transaction-banking / fraud / real-time-payments builders",
                ],
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

        draft_raw = read_json(result.draft_brief_path)
        assert draft_raw.get("retrieval_design") is None
        assert draft_raw["search_priorities"][0].startswith("Payments / transaction-banking")
        assert any("ignored retrieval_design proposal" in warning.lower() for warning in result.warnings)
