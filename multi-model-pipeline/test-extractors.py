"""Tests for extractors. Run with: python -m pytest tests/ -v

To generate test fixtures, save DOM samples from LinkedIn Recruiter:
1. Open browser console on a results page
2. Run: copy(document.querySelector('main').innerHTML)
3. Paste into tests/fixtures/sample_results.html

Then run these tests against the saved DOM.
"""

import json
from pathlib import Path

# Uncomment and adapt once you have DOM fixtures:
#
# from extractors import extract_snippets_from_list_dom, extract_profile_from_dom
# from hard_filters import hard_filter
# from schemas import CandidateSnippet
#
# FIXTURES = Path(__file__).parent / "fixtures"
#
#
# def test_extract_snippets():
#     dom = (FIXTURES / "sample_results.html").read_text()
#     snippets = extract_snippets_from_list_dom(dom, string_id=1, string_name="test", page=1)
#     assert len(snippets) > 0
#     assert all(s.name for s in snippets)
#     assert all(s.profile_url for s in snippets)
#
#
# def test_hard_filter_annotation_company():
#     snippet = CandidateSnippet(
#         name="Test Person",
#         headline="AI Trainer at Outlier",
#         current_title="AI Trainer",
#         current_company="Outlier",
#         location="São Paulo, Brazil",
#         education_snippet="",
#         profile_url="/talent/profile/test",
#         source_string_id=1,
#         source_string_name="test",
#         page=1,
#         result_rank=1,
#     )
#     should_skip, reason = hard_filter(snippet)
#     assert should_skip is True
#     assert "Annotation company" in reason
#
#
# def test_hard_filter_passes_ml_engineer():
#     snippet = CandidateSnippet(
#         name="Good Candidate",
#         headline="Senior ML Engineer at MercadoLibre",
#         current_title="Senior ML Engineer",
#         current_company="MercadoLibre",
#         location="São Paulo, Brazil",
#         education_snippet="MSc Computer Science, USP",
#         profile_url="/talent/profile/good",
#         source_string_id=1,
#         source_string_name="test",
#         page=1,
#         result_rank=1,
#     )
#     should_skip, reason = hard_filter(snippet)
#     assert should_skip is False


def test_placeholder():
    """Placeholder test — remove once real tests are uncommented."""
    assert True
