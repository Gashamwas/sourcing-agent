import asyncio
import json
from unittest.mock import AsyncMock
from unittest.mock import MagicMock
from unittest.mock import patch

from github.reconciliation_input import (
    GitHubReconciliationLead,
    load_saved_github_reconciliation_batch_with_fallback,
)
from linkedin.recruiter_identity_resolver import (
    RecruiterIdentityResolver,
    RecruiterResolverConfig,
)
from shared.reconciliation_schemas import LinkedInIdentityHints, LinkedInMatchResult
from shared.schemas import CandidateProfileSummary, OpusDecision


def _make_lead() -> GitHubReconciliationLead:
    hints = LinkedInIdentityHints(
        candidate_name="Ada Lovelace",
        github_username="ada",
        github_url="https://github.com/ada",
        company="JPMorgan Chase",
        location="New York",
        title="Head of AI Platform",
    )
    return GitHubReconciliationLead(
        username="ada",
        candidate_name="Ada Lovelace",
        github_url="https://github.com/ada",
        company="JPMorgan Chase",
        location="New York",
        title="Head of AI Platform",
        decision="SAVE",
        confidence=0.94,
        rationale="Strong fit",
        source_query="fde",
        source_channel="code_search",
        linkedin_hints=hints,
    )


def test_load_saved_github_reconciliation_batch_with_fallback_uses_saves(tmp_path):
    candidates = [
        {
            "username": "ada",
            "source_query": "fde",
            "source_strategy": "code_search",
            "synthesized_headline": "Head of AI Platform",
            "user": {
                "username": "ada",
                "name": "Ada Lovelace",
                "profile_url": "https://github.com/ada",
                "company": "JPMorgan Chase",
                "location": "New York",
                "bio": "Head of AI Platform",
            },
            "contact": {},
        }
    ]
    saves = [
        {
            "username": "ada",
            "github_url": "https://github.com/ada",
            "decision": "SAVE",
            "rationale": "Strong fit",
        }
    ]
    (tmp_path / "candidates.jsonl").write_text(
        "\n".join(json.dumps(item) for item in candidates),
        encoding="utf-8",
    )
    (tmp_path / "saves.jsonl").write_text(
        "\n".join(json.dumps(item) for item in saves),
        encoding="utf-8",
    )
    (tmp_path / "outreach.jsonl").write_text("", encoding="utf-8")

    batch = load_saved_github_reconciliation_batch_with_fallback(tmp_path)

    assert batch.stats.leads_loaded == 1
    assert batch.leads[0].candidate_name == "Ada Lovelace"
    assert batch.leads[0].linkedin_hints is not None
    assert batch.leads[0].linkedin_hints.candidate_name == "Ada Lovelace"


def test_resolve_lead_high_confidence_without_profile_open_is_manual_tool_failure():
    browser = AsyncMock()
    browser.get_card_slot_count.return_value = 1
    browser.get_card_snapshot.return_value = {
        "innertext": "\n".join(
            [
                "Ada Lovelace",
                "Head of AI Platform at JPMorgan Chase",
                "New York · 2nd",
            ]
        ),
        "name": "Ada Lovelace",
        "url": "/talent/profile/ada",
        "already_saved": False,
        "recruiter_activity": {"message_count": 1, "project_count": 0, "view_count": 1},
    }
    resolver = RecruiterIdentityResolver(
        browser=browser,
        project_url="https://www.linkedin.com/talent/hire/123/search",
        config=RecruiterResolverConfig(max_cards=3, open_profile_on_likely_match=False),
        linkedin_brief=MagicMock(),
    )
    asyncio.run(resolver.prepare_search("New York"))

    result = asyncio.run(resolver.resolve_lead(_make_lead()))

    assert result.final_action == "MANUAL_REVIEW"
    assert result.final_subreason == "tool_failure"
    assert result.identity_classification == "high_confidence_match"
    browser.enter_search_string.assert_awaited_once_with("Ada Lovelace")
    browser.focus_card_for_review.assert_awaited_once_with(0)


def test_resolve_lead_returns_manual_review_for_plausible_but_unconfirmed_card():
    browser = AsyncMock()
    browser.get_card_slot_count.return_value = 1
    browser.get_card_snapshot.return_value = {
        "innertext": "\n".join(
            [
                "Ada Lovelace",
                "Engineering Leader",
                "San Francisco · 3rd",
            ]
        ),
        "name": "Ada Lovelace",
        "url": "/talent/profile/ada2",
        "already_saved": False,
        "recruiter_activity": {"message_count": 0, "project_count": 0, "view_count": 0},
    }
    resolver = RecruiterIdentityResolver(
        browser=browser,
        project_url="https://www.linkedin.com/talent/hire/123/search",
        config=RecruiterResolverConfig(open_profile_on_likely_match=True),
        linkedin_brief=MagicMock(),
    )
    asyncio.run(resolver.prepare_search(""))

    result = asyncio.run(resolver.resolve_lead(_make_lead()))

    assert result.final_action == "MANUAL_REVIEW"
    assert result.final_subreason == "identity_ambiguous"
    browser.open_profile_by_url.assert_not_awaited()


@patch("linkedin.recruiter_identity_resolver.full_judge")
@patch("linkedin.recruiter_identity_resolver.extract_profile_from_innertext")
def test_resolve_lead_save_path_triggers_recruiter_save(mock_extract, mock_judge):
    browser = AsyncMock()
    browser.get_card_slot_count.return_value = 1
    browser.get_card_snapshot.return_value = {
        "innertext": "\n".join(
            [
                "Ada Lovelace",
                "Head of AI Platform at JPMorgan Chase",
                "New York · 2nd",
            ]
        ),
        "name": "Ada Lovelace",
        "url": "/talent/profile/ada",
        "already_saved": False,
        "recruiter_activity": {"message_count": 1, "project_count": 0, "view_count": 1},
    }
    browser.get_profile_status_summary.return_value = {
        "message_count": 1,
        "project_count": 0,
        "view_count": 1,
        "saved_by": "",
        "last_outbound_contact": "",
    }
    browser.save_candidate.return_value = True

    summary = CandidateProfileSummary(
        name="Ada Lovelace",
        profile_url="/talent/profile/ada",
        headline="Head of AI Platform",
    )
    mock_extract.return_value = summary
    mock_judge.return_value = OpusDecision(
        stage="full",
        decision="SAVE",
        path="DIRECT:1.Test",
        confidence=0.9,
        rationale="Strong",
        candidate_name="Ada Lovelace",
        profile_url="/talent/profile/ada",
    )

    resolver = RecruiterIdentityResolver(
        browser=browser,
        project_url="https://www.linkedin.com/talent/hire/123/search",
        config=RecruiterResolverConfig(open_profile_on_likely_match=True, dry_run_save=False),
        linkedin_brief=MagicMock(),
    )
    asyncio.run(resolver.prepare_search("New York"))

    result = asyncio.run(resolver.resolve_lead(_make_lead()))

    assert result.final_action == "SAVE"
    assert result.recruiter_save_attempted is True
    assert result.recruiter_save_succeeded is True
    assert browser.open_profile_by_url.await_count == 2
    browser.open_profile_by_url.assert_awaited_with("/talent/profile/ada")
    browser.simulate_profile_read.assert_awaited_once()
    browser.save_candidate.assert_awaited_once()
    assert browser.go_back_to_results.await_count == 2


@patch("linkedin.recruiter_identity_resolver.full_judge")
@patch("linkedin.recruiter_identity_resolver.extract_profile_from_innertext")
def test_resolve_lead_dry_run_skips_save_click(mock_extract, mock_judge):
    browser = AsyncMock()
    browser.get_card_slot_count.return_value = 1
    browser.get_card_snapshot.return_value = {
        "innertext": "Ada Lovelace\nHead of AI Platform at JPMorgan Chase\nNew York · 2nd",
        "name": "Ada Lovelace",
        "url": "/talent/profile/ada",
        "already_saved": False,
        "recruiter_activity": {"message_count": 0, "project_count": 0, "view_count": 0},
    }
    browser.get_profile_status_summary.return_value = {}
    mock_extract.return_value = CandidateProfileSummary(
        name="Ada Lovelace", profile_url="/talent/profile/ada", headline="x"
    )
    mock_judge.return_value = OpusDecision(
        stage="full",
        decision="SAVE",
        path="DIRECT:1.Test",
        confidence=0.9,
        rationale="Strong",
        candidate_name="Ada",
        profile_url="/talent/profile/ada",
    )

    resolver = RecruiterIdentityResolver(
        browser=browser,
        project_url="https://www.linkedin.com/talent/hire/123/search",
        config=RecruiterResolverConfig(open_profile_on_likely_match=True, dry_run_save=True),
        linkedin_brief=MagicMock(),
    )
    asyncio.run(resolver.prepare_search("New York"))
    result = asyncio.run(resolver.resolve_lead(_make_lead()))

    assert result.final_action == "SAVE"
    browser.save_candidate.assert_not_awaited()


@patch("linkedin.recruiter_identity_resolver.full_judge")
@patch("linkedin.recruiter_identity_resolver.extract_profile_from_innertext")
def test_resolve_lead_fit_reject_skips_save(mock_extract, mock_judge):
    browser = AsyncMock()
    browser.get_card_slot_count.return_value = 1
    browser.get_card_snapshot.return_value = {
        "innertext": "Ada Lovelace\nHead of AI Platform at JPMorgan Chase\nNew York · 2nd",
        "name": "Ada Lovelace",
        "url": "/talent/profile/ada",
        "already_saved": False,
        "recruiter_activity": {"message_count": 0, "project_count": 0, "view_count": 0},
    }
    browser.get_profile_status_summary.return_value = {}
    mock_extract.return_value = CandidateProfileSummary(
        name="Ada Lovelace", profile_url="/talent/profile/ada", headline="x"
    )
    mock_judge.return_value = OpusDecision(
        stage="full",
        decision="REJECT",
        path="none",
        confidence=0.2,
        rationale="Weak",
        candidate_name="Ada",
        profile_url="/talent/profile/ada",
    )

    resolver = RecruiterIdentityResolver(
        browser=browser,
        project_url="https://www.linkedin.com/talent/hire/123/search",
        config=RecruiterResolverConfig(open_profile_on_likely_match=True),
        linkedin_brief=MagicMock(),
    )
    asyncio.run(resolver.prepare_search("New York"))
    result = asyncio.run(resolver.resolve_lead(_make_lead()))

    assert result.final_action == "REJECT"
    assert result.final_subreason == "fit_reject"
    browser.save_candidate.assert_not_awaited()


def _card_snapshot(url: str, rank_suffix: str = "2nd") -> dict:
    return {
        "innertext": "\n".join(
            [
                "Ada Lovelace",
                "Head of AI Platform at JPMorgan Chase",
                f"New York · {rank_suffix}",
            ]
        ),
        "name": "Ada Lovelace",
        "url": url,
        "already_saved": False,
        "recruiter_activity": {"message_count": 0, "project_count": 0, "view_count": 0},
    }


@patch("linkedin.recruiter_identity_resolver.full_judge")
@patch("linkedin.recruiter_identity_resolver.extract_profile_from_innertext")
def test_multi_plausible_unique_save_winner(mock_extract, mock_judge):
    browser = AsyncMock()
    browser.get_card_slot_count.return_value = 2
    browser.get_card_snapshot.side_effect = [
        _card_snapshot("/talent/profile/p1", "2nd"),
        _card_snapshot("/talent/profile/p2", "1st"),
    ]
    browser.get_profile_status_summary.return_value = {}

    def _extract(_innertext: str, profile_url: str):
        return CandidateProfileSummary(name="Ada Lovelace", profile_url=profile_url, headline="h")

    mock_extract.side_effect = _extract
    mock_judge.side_effect = [
        OpusDecision(
            stage="full",
            decision="REJECT",
            path="none",
            confidence=0.3,
            rationale="no",
            candidate_name="Ada",
            profile_url="/talent/profile/p1",
        ),
        OpusDecision(
            stage="full",
            decision="SAVE",
            path="DIRECT:1.Test",
            confidence=0.9,
            rationale="yes",
            candidate_name="Ada",
            profile_url="/talent/profile/p2",
        ),
    ]
    browser.save_candidate.return_value = True

    resolver = RecruiterIdentityResolver(
        browser=browser,
        project_url="https://www.linkedin.com/talent/hire/123/search",
        config=RecruiterResolverConfig(
            open_profile_on_likely_match=True,
            max_cards=3,
            max_ambiguity_profiles=3,
        ),
        linkedin_brief=MagicMock(),
    )
    asyncio.run(resolver.prepare_search("New York"))
    result = asyncio.run(resolver.resolve_lead(_make_lead()))

    assert result.ambiguity_multi_review is True
    assert len(result.plausible_profile_reviews) == 2
    assert result.plausible_profile_reviews[0].gate_final_action == "REJECT"
    assert result.plausible_profile_reviews[1].gate_final_action == "SAVE"
    assert result.final_action == "SAVE"
    assert result.selected_profile_url == "/talent/profile/p2"
    assert browser.open_profile_by_url.await_count == 3
    assert browser.go_back_to_results.await_count == 3


@patch("linkedin.recruiter_identity_resolver.full_judge")
@patch("linkedin.recruiter_identity_resolver.extract_profile_from_innertext")
def test_multi_plausible_two_saves_is_manual_ambiguous(mock_extract, mock_judge):
    browser = AsyncMock()
    browser.get_card_slot_count.return_value = 2
    browser.get_card_snapshot.side_effect = [
        _card_snapshot("/talent/profile/p1"),
        _card_snapshot("/talent/profile/p2", "1st"),
    ]
    browser.get_profile_status_summary.return_value = {}
    mock_extract.side_effect = lambda _t, profile_url: CandidateProfileSummary(
        name="Ada Lovelace", profile_url=profile_url, headline="h"
    )
    save = OpusDecision(
        stage="full",
        decision="SAVE",
        path="DIRECT:1.A",
        confidence=0.9,
        rationale="ok",
        candidate_name="Ada",
        profile_url="",
    )
    mock_judge.side_effect = [save, save]

    resolver = RecruiterIdentityResolver(
        browser=browser,
        project_url="https://www.linkedin.com/talent/hire/123/search",
        config=RecruiterResolverConfig(open_profile_on_likely_match=True, max_cards=3),
        linkedin_brief=MagicMock(),
    )
    asyncio.run(resolver.prepare_search("New York"))
    result = asyncio.run(resolver.resolve_lead(_make_lead()))

    assert result.ambiguity_multi_review is True
    assert result.final_action == "MANUAL_REVIEW"
    assert result.final_subreason == "identity_ambiguous"
    assert len(result.plausible_profile_reviews) == 2
    assert result.had_plausible_cards is True
    assert result.selected_candidate_rank == 0
    assert result.selected_profile_url == ""
    assert result.holistic_fit_decision == ""
    browser.save_candidate.assert_not_awaited()
    assert any("Per-profile gates" in note for note in result.notes)


@patch("linkedin.recruiter_identity_resolver.full_judge")
@patch("linkedin.recruiter_identity_resolver.extract_profile_from_innertext")
def test_multi_ambiguity_unresolved_clears_row_holistic_fields(mock_extract, mock_judge):
    browser = AsyncMock()
    browser.get_card_slot_count.return_value = 2
    browser.get_card_snapshot.side_effect = [
        _card_snapshot("/talent/profile/p1"),
        _card_snapshot("/talent/profile/p2", "1st"),
    ]
    browser.get_profile_status_summary.return_value = {}
    mock_extract.side_effect = lambda _t, profile_url: CandidateProfileSummary(
        name="Ada Lovelace", profile_url=profile_url, headline="h"
    )
    borderline = OpusDecision(
        stage="full",
        decision="INFERENTIAL_SAVE",
        path="x",
        confidence=0.55,
        rationale="borderline",
        candidate_name="Ada",
        profile_url="",
    )
    mock_judge.side_effect = [borderline, borderline]

    resolver = RecruiterIdentityResolver(
        browser=browser,
        project_url="https://www.linkedin.com/talent/hire/123/search",
        config=RecruiterResolverConfig(open_profile_on_likely_match=True, max_cards=3),
        linkedin_brief=MagicMock(),
    )
    asyncio.run(resolver.prepare_search("New York"))
    result = asyncio.run(resolver.resolve_lead(_make_lead()))

    assert result.ambiguity_multi_review is True
    assert result.final_subreason == "ambiguity_unresolved"
    assert result.had_plausible_cards is True
    assert result.selected_candidate_rank == 0
    assert result.selected_profile_url == ""
    assert result.holistic_fit_decision == ""
    assert len(result.plausible_profile_reviews) == 2
    assert any("Per-profile gates" in note for note in result.notes)


@patch("linkedin.recruiter_identity_resolver.choose_best_match")
@patch("linkedin.recruiter_identity_resolver.single_plausible_is_safely_dominant", return_value=True)
@patch("linkedin.recruiter_identity_resolver.is_single_strong_plausible_for_profile_open", return_value=True)
@patch("linkedin.recruiter_identity_resolver.full_judge")
@patch("linkedin.recruiter_identity_resolver.extract_profile_from_innertext")
def test_single_strong_plausible_opens_profile_when_gates_allow(
    mock_extract,
    mock_judge,
    _mock_is_strong,
    _mock_dom,
    mock_choose,
):
    mock_choose.side_effect = lambda matches: (
        "manual_review",
        sorted(matches, key=lambda m: m.match_confidence, reverse=True)[0],
    )
    browser = AsyncMock()
    browser.get_card_slot_count.return_value = 2
    browser.get_card_snapshot.side_effect = [
        {
            "innertext": "Bob Smith\nEngineer at OtherCo\nLondon · 2nd",
            "name": "Bob Smith",
            "url": "/talent/profile/bob",
            "already_saved": False,
            "recruiter_activity": {"message_count": 0, "project_count": 0, "view_count": 0},
        },
        _card_snapshot("/talent/profile/ada-strong", "1st"),
    ]
    browser.get_profile_status_summary.return_value = {}
    mock_extract.return_value = CandidateProfileSummary(
        name="Ada Lovelace", profile_url="/talent/profile/ada-strong", headline="h"
    )
    mock_judge.return_value = OpusDecision(
        stage="full",
        decision="INFERENTIAL_SAVE",
        path="x",
        confidence=0.55,
        rationale="borderline",
        candidate_name="Ada",
        profile_url="/talent/profile/ada-strong",
    )

    resolver = RecruiterIdentityResolver(
        browser=browser,
        project_url="https://www.linkedin.com/talent/hire/123/search",
        config=RecruiterResolverConfig(open_profile_on_likely_match=True, max_cards=3),
        linkedin_brief=MagicMock(),
    )
    asyncio.run(resolver.prepare_search("New York"))
    result = asyncio.run(resolver.resolve_lead(_make_lead()))

    assert result.identity_classification == "single_strong_plausible_profile"
    assert result.opened_profile is True
    assert len(result.plausible_profile_reviews) == 1
    browser.open_profile_by_url.assert_awaited()


@patch("linkedin.recruiter_identity_resolver.choose_best_match")
@patch("linkedin.recruiter_identity_resolver.single_plausible_is_safely_dominant", return_value=False)
@patch("linkedin.recruiter_identity_resolver.is_single_strong_plausible_for_profile_open", return_value=True)
def test_single_strong_path_skipped_when_not_dominant_vs_next_card(
    _mock_strong,
    _mock_dom,
    mock_choose,
):
    mock_choose.side_effect = lambda matches: (
        "manual_review",
        sorted(matches, key=lambda m: m.match_confidence, reverse=True)[0],
    )
    browser = AsyncMock()
    browser.get_card_slot_count.return_value = 2
    browser.get_card_snapshot.side_effect = [
        {
            "innertext": "Bob Smith\nEngineer at OtherCo\nLondon · 2nd",
            "name": "Bob Smith",
            "url": "/talent/profile/bob",
            "already_saved": False,
            "recruiter_activity": {"message_count": 0, "project_count": 0, "view_count": 0},
        },
        _card_snapshot("/talent/profile/ada-strong", "1st"),
    ]

    resolver = RecruiterIdentityResolver(
        browser=browser,
        project_url="https://www.linkedin.com/talent/hire/123/search",
        config=RecruiterResolverConfig(open_profile_on_likely_match=True, max_cards=3),
        linkedin_brief=MagicMock(),
    )
    asyncio.run(resolver.prepare_search("New York"))
    result = asyncio.run(resolver.resolve_lead(_make_lead()))

    browser.open_profile_by_url.assert_not_awaited()
    assert result.opened_profile is False


@patch("linkedin.recruiter_identity_resolver.score_linkedin_identity_match")
@patch("linkedin.recruiter_identity_resolver.choose_best_match")
@patch("linkedin.recruiter_identity_resolver.full_judge")
@patch("linkedin.recruiter_identity_resolver.extract_profile_from_innertext")
def test_resolve_anchor_single_plausible_live_shape_opens_without_strong_mocks(
    mock_extract,
    mock_judge,
    mock_choose,
    mock_score,
):
    """End-to-end: tier-2 anchor (0.69 + exact name + company + title) reaches profile open."""

    def _fake_score(_hints, **kwargs):
        url = str(kwargs.get("matched_profile_url") or "")
        if "decoy" in url:
            return LinkedInMatchResult(
                matched_profile_url=url,
                matched_name="Bob Smith",
                match_confidence=0.38,
                evidence=[],
                ambiguity_reasons=["Name mismatch"],
            )
        return LinkedInMatchResult(
            matched_profile_url=url,
            matched_name="Ada Lovelace",
            match_confidence=0.69,
            evidence=["Exact name match", "Company overlap", "Title overlap"],
            ambiguity_reasons=["Location mismatch"],
        )

    mock_score.side_effect = _fake_score
    mock_choose.side_effect = lambda matches: (
        "manual_review",
        sorted(matches, key=lambda m: m.match_confidence, reverse=True)[0],
    )
    browser = AsyncMock()
    browser.get_card_slot_count.return_value = 2
    browser.get_card_snapshot.side_effect = [
        {
            "innertext": "Bob Smith\nEngineer at OtherCo\nLondon · 2nd",
            "name": "Bob Smith",
            "url": "/talent/profile/decoy-bob",
            "already_saved": False,
            "recruiter_activity": {"message_count": 0, "project_count": 0, "view_count": 0},
        },
        _card_snapshot("/talent/profile/ada-anchor", "1st"),
    ]
    browser.get_profile_status_summary.return_value = {}
    mock_extract.return_value = CandidateProfileSummary(
        name="Ada Lovelace", profile_url="/talent/profile/ada-anchor", headline="h"
    )
    mock_judge.return_value = OpusDecision(
        stage="full",
        decision="INFERENTIAL_SAVE",
        path="x",
        confidence=0.55,
        rationale="borderline",
        candidate_name="Ada",
        profile_url="/talent/profile/ada-anchor",
    )

    resolver = RecruiterIdentityResolver(
        browser=browser,
        project_url="https://www.linkedin.com/talent/hire/123/search",
        config=RecruiterResolverConfig(open_profile_on_likely_match=True, max_cards=3),
        linkedin_brief=MagicMock(),
    )
    asyncio.run(resolver.prepare_search("New York"))
    result = asyncio.run(resolver.resolve_lead(_make_lead()))

    assert result.identity_classification == "single_strong_plausible_profile"
    assert result.opened_profile is True
    assert len(result.plausible_profile_reviews) == 1
    browser.open_profile_by_url.assert_awaited()


def test_resolve_lead_uses_username_derived_surname_when_candidate_name_is_single_token():
    """P0 fallback: "Michael" + github_username="mldangelo" must search
    "Michael Mldangelo" rather than the bare single-token "Michael"."""
    browser = AsyncMock()
    browser.get_card_slot_count.return_value = 0
    browser.get_card_count.return_value = 0
    resolver = RecruiterIdentityResolver(
        browser=browser,
        project_url="https://www.linkedin.com/talent/hire/123/search",
        config=RecruiterResolverConfig(max_cards=3, open_profile_on_likely_match=False),
        linkedin_brief=MagicMock(),
    )
    asyncio.run(resolver.prepare_search("New York City Metropolitan Area"))

    lead = GitHubReconciliationLead(
        username="mldangelo",
        candidate_name="Michael",
        github_url="https://github.com/mldangelo",
        company="@promptfoo",
        location="New York, NY",
        title="VP Engineering",
        decision="SAVE",
        confidence=0.9,
        rationale="",
        source_query="fde",
        source_channel="code_search",
        linkedin_hints=LinkedInIdentityHints(
            candidate_name="Michael",
            github_username="mldangelo",
            github_url="https://github.com/mldangelo",
            company="@promptfoo",
            location="New York, NY",
            title="VP Engineering",
        ),
    )

    result = asyncio.run(resolver.resolve_lead(lead))

    assert result.lookup_name == "Michael Mldangelo"
    assert result.query == "Michael Mldangelo"
    browser.enter_search_string.assert_awaited_once_with("Michael Mldangelo")
    # No cards surfaced, so the resolver terminates with no_results; this confirms the
    # query string was issued before the "no results" path and was not silently
    # rewritten downstream.
    assert result.identity_classification == "no_results"


def test_use_existing_search_does_not_navigate_or_apply_filters():
    browser = AsyncMock()
    resolver = RecruiterIdentityResolver(
        browser=browser,
        config=RecruiterResolverConfig(),
        linkedin_brief=MagicMock(),
    )

    asyncio.run(resolver.use_existing_search("New York City Metropolitan Area"))

    assert resolver.search_location == "New York City Metropolitan Area"
    browser.navigate_to_search.assert_not_awaited()
    browser.apply_permanent_filters.assert_not_awaited()
    browser.go_back_to_results.assert_awaited_once()
