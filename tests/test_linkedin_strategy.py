"""Tests for LinkedIn strategy prompt assembly and edge-case rebalancing."""

from pathlib import Path
from unittest.mock import patch

from shared.brief_loader import load_brief
from shared.schemas import BlockReport, SearchString
from linkedin.strategy import _build_strategy_user, adapt_after_block, form_strategy


HEAD_AI_V2_BRIEF_PATH = str(
    Path(__file__).parent.parent / "config" / "brief-head-ai-lab-nyc-v2.json"
)


def test_build_strategy_user_includes_search_family_memory():
    brief = load_brief(HEAD_AI_V2_BRIEF_PATH)
    prompt = _build_strategy_user(
        brief,
        [],
        prior_run_data={
            "search_memory_summary": {
                "overall": {
                    "families_tracked": 2,
                    "save_rate": 0.04,
                    "duplicate_rate": 0.47,
                    "novelty_mix": {
                        "edge_case_saves": 3,
                        "canonical_saves": 8,
                    },
                },
                "families": [
                    {
                        "family_key": "canonical_bank_company_first",
                        "novelty_bucket": "canonical",
                        "domain_lane": "capital_markets",
                        "status": "exhausted",
                        "status_reason": "Repeated family with high duplicate overlap.",
                        "save_rate": 0.01,
                        "duplicate_rate": 0.58,
                        "dominant_anchors": ["goldman", "jpmorgan", "capital markets"],
                    }
                ],
            }
        },
    )

    assert "Search Family Memory" in prompt
    assert "canonical_bank_company_first" in prompt
    assert "Repeated family with high duplicate overlap." in prompt
    assert "goldman, jpmorgan, capital markets" in prompt


def test_build_strategy_user_includes_market_intel_lanes_and_cleanup_rule():
    brief = load_brief(HEAD_AI_V2_BRIEF_PATH)
    prompt = _build_strategy_user(brief, [], prior_run_data={})

    assert "regulatory reporting" in prompt.lower()
    assert "payment orchestration" in prompt.lower()
    assert "founder or cto populations" in prompt.lower()
    assert "archetype-first executive-builder strings are cleanup only" in prompt.lower()


def test_form_strategy_reorders_head_ai_opening_toward_edge_case():
    brief = load_brief(HEAD_AI_V2_BRIEF_PATH)
    mock_plan = {
        "architecture": "dragnet",
        "architecture_rationale": "mock",
        "architecture_success_criteria": [],
        "architecture_pivot_triggers": [],
        "strategy_rationale": "mock",
        "generated_strings": [
            {
                "boolean": "(\"Goldman Sachs\" OR \"JPMorgan\") AND (\"GenAI\" OR \"LLM\")",
                "rationale": "Canonical bank company-first cleanup string",
                "vocabulary_sources": "mock",
            },
            {
                "boolean": "(\"banking\" OR \"financial services\" OR \"BFSI\") AND (\"GenAI\" OR \"RAG\")",
                "rationale": "Broad generic BFSI cleanup string",
                "vocabulary_sources": "mock",
            },
            {
                "boolean": "(\"trade surveillance workflow\" OR \"market surveillance workflow\") AND (\"agentic\" OR \"retrieval pipeline\")",
                "rationale": "Trade surveillance edge-case population",
                "vocabulary_sources": "mock",
            },
            {
                "boolean": "(\"collateral workflow\" OR \"post-trade workflow\") AND (\"document intelligence\" OR \"orchestration\")",
                "rationale": "Collateral and post-trade edge-case population",
                "vocabulary_sources": "mock",
            },
            {
                "boolean": "(\"research copilot\" OR \"investment memo automation\") AND (\"production\" OR \"deployed\")",
                "rationale": "Asset management and research workflow builders",
                "vocabulary_sources": "mock",
            },
            {
                "boolean": "(\"underwriting workbench\" OR \"claims intake\") AND (\"production\" OR \"deployed\")",
                "rationale": "Insurance workflow builders",
                "vocabulary_sources": "mock",
            },
            {
                "boolean": "(\"model risk review\" OR \"regulatory response\") AND (\"applied AI\" OR \"evaluation framework\")",
                "rationale": "Risk and compliance workflow builders",
                "vocabulary_sources": "mock",
            },
            {
                "boolean": "(\"custody workflow\" OR \"market data workflow\") AND (\"agentic\" OR \"document intelligence\")",
                "rationale": "BFSI vendor workflow builders",
                "vocabulary_sources": "mock",
            },
        ],
        "coverage_gaps": [],
        "noise_predictions": [],
    }

    with patch("linkedin.strategy.opus_llm", return_value=mock_plan):
        plan = form_strategy(brief, [], prior_run_data={})

    assert len(plan.generated_strings) == 8
    first_eight = plan.generated_strings[:8]
    edge_case_count = sum(
        1 for item in first_eight if item.get("novelty_bucket") == "edge_case"
    )
    assert edge_case_count >= 5
    assert first_eight[0]["domain_lane"] != "general"


def test_form_strategy_promotes_market_intel_gap_lanes_ahead_of_cleanup():
    brief = load_brief(HEAD_AI_V2_BRIEF_PATH)
    mock_plan = {
        "architecture": "dragnet",
        "architecture_rationale": "mock",
        "architecture_success_criteria": [],
        "architecture_pivot_triggers": [],
        "strategy_rationale": "mock",
        "generated_strings": [
            {
                "boolean": "(\"Head of Applied AI\" OR \"Executive Director AI\") AND (\"banking\" OR \"financial services\") AND (\"GenAI\" OR \"LLM\")",
                "rationale": "Archetype-first executive-builder cleanup string",
                "vocabulary_sources": "mock",
                "family_key": "executive_builder_cleanup",
            },
            {
                "boolean": "(\"regulatory reporting\" OR \"regulatory filing\" OR \"transaction monitoring\") AND (\"LLM\" OR \"agentic\" OR \"RAG\")",
                "rationale": "Regulatory reporting and compliance GenAI builders",
                "vocabulary_sources": "mock",
                "family_key": "reg_reporting_genai",
            },
            {
                "boolean": "(\"payment orchestration\" OR \"transaction banking\" OR \"FedNow\") AND (\"LLM\" OR \"agentic\" OR \"document intelligence\")",
                "rationale": "Payments and transaction-banking builders",
                "vocabulary_sources": "mock",
                "family_key": "payments_builder",
            },
            {
                "boolean": "(\"founder\" OR \"co-founder\" OR \"CTO\") AND (\"fintech\" OR \"insurtech\" OR \"regtech\") AND (\"GenAI\" OR \"agentic\")",
                "rationale": "Founder and CTO edge-case population",
                "vocabulary_sources": "mock",
                "family_key": "founder_cto_bfsi",
            },
        ],
        "coverage_gaps": [],
        "noise_predictions": [],
    }

    with patch("linkedin.strategy.opus_llm", return_value=mock_plan):
        plan = form_strategy(brief, [], prior_run_data={})

    family_order = [item.get("family_key") for item in plan.generated_strings]
    cleanup_index = family_order.index("executive_builder_cleanup")
    assert family_order.index("reg_reporting_genai") < cleanup_index
    assert family_order.index("payments_builder") < cleanup_index
    assert family_order.index("founder_cto_bfsi") < cleanup_index
    assert all(
        item.get("novelty_bucket") == "edge_case"
        for item in plan.generated_strings[:3]
    )


def test_form_strategy_demotes_exhausted_families_from_search_memory():
    brief = load_brief(HEAD_AI_V2_BRIEF_PATH)
    mock_plan = {
        "architecture": "dragnet",
        "architecture_rationale": "mock",
        "architecture_success_criteria": [],
        "architecture_pivot_triggers": [],
        "strategy_rationale": "mock",
        "generated_strings": [
            {
                "boolean": "(\"Goldman Sachs\" OR \"JPMorgan\") AND (\"GenAI\" OR \"LLM\")",
                "rationale": "Canonical bank company-first cleanup string",
                "vocabulary_sources": "mock",
                "family_key": "canonical_bank_company_first",
                "novelty_bucket": "canonical",
                "domain_lane": "capital_markets",
            },
            {
                "boolean": "(\"trade surveillance workflow\" OR \"market surveillance workflow\") AND (\"agentic\" OR \"retrieval pipeline\")",
                "rationale": "Trade surveillance edge-case population",
                "vocabulary_sources": "mock",
                "family_key": "trade_surveillance_workflow",
                "novelty_bucket": "edge_case",
                "domain_lane": "risk_compliance",
            },
            {
                "boolean": "(\"research copilot\" OR \"investment memo automation\") AND (\"production\" OR \"deployed\")",
                "rationale": "Research copilot edge-case population",
                "vocabulary_sources": "mock",
                "family_key": "research_copilot_asset_mgmt",
                "novelty_bucket": "edge_case",
                "domain_lane": "asset_management",
            }
        ],
        "coverage_gaps": [],
        "noise_predictions": [],
    }

    prior_run_data = {
        "search_memory_summary": {
            "overall": {
                "families_tracked": 2,
                "save_rate": 0.02,
                "duplicate_rate": 0.51,
                "novelty_mix": {"edge_case_saves": 2, "canonical_saves": 10},
            },
            "families": [
                {
                    "family_key": "canonical_bank_company_first",
                    "novelty_bucket": "canonical",
                    "domain_lane": "capital_markets",
                    "status": "exhausted",
                    "status_reason": "Repeated family with high duplicate overlap.",
                    "save_rate": 0.01,
                    "duplicate_rate": 0.58,
                    "dominant_anchors": ["goldman", "jpmorgan"],
                }
            ],
        }
    }

    with patch("linkedin.strategy.opus_llm", return_value=mock_plan):
        plan = form_strategy(brief, [], prior_run_data=prior_run_data)

    assert plan.generated_strings[-1]["family_key"] == "canonical_bank_company_first"


def test_form_strategy_accepts_raw_search_memory_artifact():
    brief = load_brief(HEAD_AI_V2_BRIEF_PATH)
    mock_plan = {
        "architecture": "dragnet",
        "architecture_rationale": "mock",
        "architecture_success_criteria": [],
        "architecture_pivot_triggers": [],
        "strategy_rationale": "mock",
        "generated_strings": [
            {
                "boolean": "(\"Goldman Sachs\" OR \"JPMorgan\") AND (\"GenAI\" OR \"LLM\")",
                "rationale": "Canonical bank company-first cleanup string",
                "vocabulary_sources": "mock",
                "family_key": "canonical_bank_company_first",
                "novelty_bucket": "canonical",
                "domain_lane": "capital_markets",
            },
            {
                "boolean": "(\"trade surveillance workflow\" OR \"market surveillance workflow\") AND (\"agentic\" OR \"retrieval pipeline\")",
                "rationale": "Trade surveillance edge-case population",
                "vocabulary_sources": "mock",
                "family_key": "trade_surveillance_workflow",
                "novelty_bucket": "edge_case",
                "domain_lane": "risk_compliance",
            },
        ],
        "coverage_gaps": [],
        "noise_predictions": [],
    }

    prior_run_data = {
        "search_memory_summary": {
            "project_id": "1957683706",
            "overall": {
                "strings_seen": 1,
                "candidates_seen": 7,
                "duplicates": 4,
                "saves": 1,
                "edge_case_saves": 1,
                "canonical_saves": 0,
            },
            "families": {
                "canonical_bank_company_first": {
                    "family_key": "canonical_bank_company_first",
                    "novelty_bucket": "canonical",
                    "domain_lane": "capital_markets",
                    "status": "exhausted",
                    "status_reason": "Repeated family with high duplicate overlap.",
                    "dominant_anchors": ["goldman", "jpmorgan"],
                }
            },
        }
    }

    with patch("linkedin.strategy.opus_llm", return_value=mock_plan):
        plan = form_strategy(brief, [], prior_run_data=prior_run_data)

    assert plan.generated_strings[-1]["family_key"] == "canonical_bank_company_first"


def test_adapt_after_block_accepts_raw_search_memory_artifact():
    brief = load_brief(HEAD_AI_V2_BRIEF_PATH)
    report = BlockReport(
        block_name="Compound Batch 1",
        strings_run=1,
        strings_with_saves=1,
        total_results=99,
        total_saves=1,
        string_details=[
            {
                "string_id": 5,
                "name": "Insurance string",
                "boolean": "(\"underwriting automation\")",
                "original_boolean": "(\"underwriting\")",
                "result_count": 99,
                "pages_reviewed": 1,
                "candidates": 7,
                "duplicates": 0,
                "saves": 1,
                "save_names": ["Devasis Bassu"],
                "saved_profiles": [],
                "facial_yes": 2,
                "facial_no": 7,
                "family_key": "insurance_ai_builder",
                "novelty_bucket": "edge_case",
                "domain_lane": "insurance",
                "notes": "Abandoned after page 1.",
            }
        ],
    )
    remaining = [
        SearchString(
            id=6,
            name="Vendor cleanup string",
            boolean="(\"Broadridge\" OR \"FIS\") AND (\"GenAI\")",
            block="Compound Batch 2",
            family_key="canonical_bank_company_first",
            novelty_bucket="canonical",
            domain_lane="capital_markets",
        )
    ]
    raw_memory = {
        "project_id": "1957683706",
        "overall": {
            "strings_seen": 1,
            "candidates_seen": 7,
            "duplicates": 4,
            "saves": 1,
            "edge_case_saves": 1,
            "canonical_saves": 0,
        },
        "families": {
            "canonical_bank_company_first": {
                "family_key": "canonical_bank_company_first",
                "novelty_bucket": "canonical",
                "domain_lane": "capital_markets",
                "status": "exhausted",
                "status_reason": "Repeated family with high duplicate overlap.",
                "dominant_anchors": ["goldman", "jpmorgan"],
            }
        },
    }
    mock_adaptation = {
        "new_strings": [],
        "skip_remaining": [],
        "reorder": [
            {
                "string_id": 6,
                "move_to": "next",
                "reason": "Move this closer to the top.",
            }
        ],
        "noise_updates": [],
    }

    with patch("linkedin.strategy.opus_llm", return_value=mock_adaptation):
        adaptation = adapt_after_block(
            brief,
            report,
            remaining,
            search_memory_summary=raw_memory,
        )

    assert adaptation.reorder[0]["move_to"] == "last"
