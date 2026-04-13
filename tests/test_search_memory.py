"""Tests for brief-scoped search family memory."""

from shared.schemas import SearchString
from shared.search_memory import build_search_memory_summary, update_search_memory


def test_search_memory_marks_repeated_high_duplicate_canonical_family_exhausted():
    memory = {}

    first = SearchString(
        id=1,
        name="canonical bank cleanup",
        boolean='("Goldman Sachs" OR "JPMorgan") AND ("GenAI" OR "LLM")',
        pages_reviewed=2,
        candidates_count=18,
        duplicates_count=16,
        saves=["A"],
        family_key="canonical_bank_company_first",
        novelty_bucket="canonical",
        domain_lane="capital_markets",
    )
    second = SearchString(
        id=2,
        name="canonical bank cleanup variant",
        boolean='("Morgan Stanley" OR "Goldman Sachs") AND ("GenAI" OR "RAG")',
        pages_reviewed=2,
        candidates_count=15,
        duplicates_count=18,
        saves=[],
        family_key="canonical_bank_company_first",
        novelty_bucket="canonical",
        domain_lane="capital_markets",
    )

    memory = update_search_memory(memory, "1957683706", [first])
    memory = update_search_memory(memory, "1957683706", [second])

    family = memory["families"]["canonical_bank_company_first"]
    assert family["status"] == "exhausted"
    assert "duplicate overlap" in family["status_reason"].lower()

    summary = build_search_memory_summary(memory)
    assert summary["families"][0]["family_key"] == "canonical_bank_company_first"
    assert summary["families"][0]["status"] == "exhausted"
    assert summary["families"][0]["duplicate_rate"] > 0.4


def test_search_memory_tracks_layer_items_and_edge_case_hypotheses():
    memory = {}
    search_string = SearchString(
        id=3,
        name="delivery builders",
        boolean='("deployment engineer") AND ("workflow orchestration") AND ("production")',
        pages_reviewed=2,
        candidates_count=12,
        duplicates_count=2,
        saves=["Ada", "Grace"],
        family_key="fde_delivery_builders",
        novelty_bucket="edge_case",
        domain_lane="general",
        retrieval_recipe={
            "family_id": "fde_delivery_builders",
            "used_layer_item_ids": {
                "entry_signals": ["entry_delivery"],
                "capability_proxies": ["cap_orchestration"],
                "reality_filters": ["real_production"],
            },
            "applied_hypothesis_ids": ["post_sale_builders"],
        },
        retrieval_hypothesis_ids=["post_sale_builders"],
    )

    memory = update_search_memory(memory, "1990251114", [search_string, search_string])
    summary = build_search_memory_summary(memory)

    assert "entry_delivery" in memory["layer_items"]
    assert memory["hypotheses"]["post_sale_builders"]["status"] == "validated"
    assert summary["layer_items"][0]["layer_item_id"] == "entry_delivery"
    assert summary["hypotheses"][0]["hypothesis_id"] == "post_sale_builders"
