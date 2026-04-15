import asyncio
from unittest.mock import AsyncMock

from github.reconciliation_input import GitHubReconciliationLead
from linkedin.reconciliation import LinkedInReconciliationService
from shared.reconciliation_schemas import (
    LinkedInIdentityHints,
    LinkedInMatchResult,
    RecruiterActivitySnapshot,
)


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
        rationale="Strong GitHub fit",
        linkedin_hints=hints,
    )


def test_reconcile_lead_returns_manual_review_when_no_confident_match():
    browser = AsyncMock()
    service = LinkedInReconciliationService(browser=browser, project_url="https://www.linkedin.com/talent/search")
    service.lookup_candidate_by_identity = AsyncMock(return_value=[])

    decision = asyncio.run(service.reconcile_lead(_make_lead()))

    assert decision.action == "manual_review"
    assert decision.assessment is not None
    assert decision.assessment.same_person == "unknown"


def test_assess_match_marks_low_novelty_when_recruiter_activity_is_heavy():
    browser = AsyncMock()
    service = LinkedInReconciliationService(browser=browser, project_url="https://www.linkedin.com/talent/search")
    lead = _make_lead()
    match = LinkedInMatchResult(
        matched_profile_url="/talent/profile/ada",
        matched_name="Ada Lovelace",
        matched_company="JPMorgan Chase & Co.",
        matched_title="Head of AI Platform",
        matched_location="New York",
        match_confidence=0.91,
        match_method="recruiter_search",
        recruiter_activity=RecruiterActivitySnapshot(message_count=7, project_count=3, view_count=4),
        novelty_pressure="high",
    )

    assessment = service._assess_match(lead, match, "high_confidence_match")

    assert assessment.same_person == "yes"
    assert assessment.novelty_value == "low"
    assert assessment.summary.startswith("LinkedIn appears to confirm the candidate")


def test_assess_match_does_not_overclaim_when_classification_is_manual_review():
    browser = AsyncMock()
    service = LinkedInReconciliationService(browser=browser, project_url="https://www.linkedin.com/talent/search")
    lead = _make_lead()
    match = LinkedInMatchResult(
        matched_profile_url="/talent/profile/ada",
        matched_name="Ada Lovelace",
        matched_company="JPMorgan Chase & Co.",
        matched_title="Head of AI Platform",
        matched_location="New York",
        match_confidence=0.72,
        match_method="recruiter_search",
    )

    assessment = service._assess_match(lead, match, "manual_review")

    assert assessment.same_person == "possible"
    assert assessment.fit_confirmation == "unclear"
    assert assessment.summary.startswith("LinkedIn surfaced a plausible candidate match")


def test_decide_action_prefers_drop_already_worked_over_promote():
    browser = AsyncMock()
    service = LinkedInReconciliationService(browser=browser, project_url="https://www.linkedin.com/talent/search")
    assessment = service._assess_match(
        _make_lead(),
        LinkedInMatchResult(
            matched_profile_url="/talent/profile/ada",
            matched_name="Ada Lovelace",
            matched_company="JPMorgan Chase",
            matched_title="Head of AI Platform",
            matched_location="New York",
            match_confidence=0.92,
            match_method="recruiter_search",
            recruiter_activity=RecruiterActivitySnapshot(
                message_count=3,
                project_count=1,
                view_count=1,
                last_outbound_contact="1 month ago",
            ),
            novelty_pressure="medium",
        ),
        "high_confidence_match",
    )
    action = service._decide_action(
        match=LinkedInMatchResult(matched_profile_url="/talent/profile/ada"),
        classification="high_confidence_match",
        assessment=assessment,
    )

    assert action == "drop_already_worked"


def test_direct_linkedin_hint_takes_precedence_over_search_match():
    browser = AsyncMock()
    service = LinkedInReconciliationService(browser=browser, project_url="https://www.linkedin.com/talent/search")
    lead = _make_lead()
    lead.linkedin_hints.linkedin_url_hint = "https://www.linkedin.com/in/ada-lovelace/"
    service.lookup_candidate_by_identity = AsyncMock(
        return_value=[
            type(
                "LookupCandidate",
                (),
                {
                    "query": "\"Ada Lovelace\"",
                    "match": LinkedInMatchResult(
                        matched_profile_url="/talent/profile/wrong-person",
                        matched_name="Ada Lovelace",
                        matched_company="Different Bank",
                        matched_title="VP",
                        matched_location="New York",
                        match_confidence=0.61,
                        match_method="recruiter_search",
                    ),
                },
            )()
        ]
    )

    decision = asyncio.run(service.reconcile_lead(lead))

    assert decision.match_result is not None
    assert decision.match_result.match_method.startswith("direct_linkedin_hint")
    assert decision.action == "manual_review"
    assert "Direct LinkedIn URL hint present" in decision.match_result.evidence
    assert decision.match_result.matched_profile_url == "https://www.linkedin.com/in/ada-lovelace/"
    browser.navigate_to_search.assert_not_awaited()


def test_name_mismatch_never_promotes():
    browser = AsyncMock()
    service = LinkedInReconciliationService(browser=browser, project_url="https://www.linkedin.com/talent/search")
    match = LinkedInMatchResult(
        matched_profile_url="/talent/profile/grace",
        matched_name="Grace Hopper",
        matched_company="JPMorgan Chase",
        matched_title="Head of AI Platform",
        matched_location="New York",
        match_confidence=0.91,
        match_method="recruiter_search",
        ambiguity_reasons=["Name mismatch"],
    )

    assessment = service._assess_match(_make_lead(), match, "high_confidence_match")
    action = service._decide_action(
        match=match,
        classification="high_confidence_match",
        assessment=assessment,
    )

    assert assessment.same_person == "no"
    assert assessment.fit_confirmation == "contradicted"
    assert action == "drop_wrong_person"
