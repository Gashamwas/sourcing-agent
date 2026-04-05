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
