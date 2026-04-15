from shared.identity_resolution import (
    build_candidate_lookup_queries,
    choose_best_match,
    classify_recruiter_activity_pressure,
    resolve_direct_linkedin_hint,
    score_linkedin_identity_match,
)
from shared.reconciliation_schemas import LinkedInIdentityHints, RecruiterActivitySnapshot


def test_build_candidate_lookup_queries_is_stable_and_bounded():
    hints = LinkedInIdentityHints(
        candidate_name="Ada Lovelace",
        company="JPMorgan Chase & Co.",
        location="New York City Metropolitan Area",
        title="Head of Applied AI Platform",
    )

    queries = build_candidate_lookup_queries(hints)

    assert queries
    assert queries == build_candidate_lookup_queries(hints)
    assert len(queries) <= 5
    assert queries[0].startswith('"Ada Lovelace" AND')


def test_resolve_direct_linkedin_hint_returns_high_confidence_match():
    hints = LinkedInIdentityHints(
        candidate_name="Ada Lovelace",
        linkedin_url_hint="https://www.linkedin.com/in/ada-lovelace/",
        company="Anthropic",
        title="Research Engineer",
    )

    match = resolve_direct_linkedin_hint(hints)

    assert match is not None
    assert match.match_method == "direct_linkedin_hint"
    assert match.match_confidence == 0.96
    assert "Direct LinkedIn URL hint present" in match.evidence


def test_score_linkedin_identity_match_does_not_credit_unrelated_cards_for_url_hint():
    hints = LinkedInIdentityHints(
        candidate_name="Ada Lovelace",
        linkedin_url_hint="https://www.linkedin.com/in/ada-lovelace/",
        company="Anthropic",
    )

    match = score_linkedin_identity_match(
        hints,
        matched_name="Grace Hopper",
        matched_company="Anthropic",
        matched_profile_url="/talent/profile/grace",
    )

    assert "Direct LinkedIn URL hint present" not in match.evidence
    assert match.match_confidence < 0.6


def test_score_linkedin_identity_match_uses_activity_and_buckets_confidence():
    hints = LinkedInIdentityHints(
        candidate_name="Ada Lovelace",
        company="JPMorgan Chase",
        location="New York",
        title="Head of AI Platform",
    )
    activity = RecruiterActivitySnapshot(message_count=7, project_count=3, view_count=2)

    match = score_linkedin_identity_match(
        hints,
        matched_name="Ada Lovelace",
        matched_company="JPMorgan Chase & Co.",
        matched_title="Head of AI Platform",
        matched_location="New York, New York, United States",
        matched_profile_url="/talent/profile/ada",
        recruiter_activity=activity,
    )

    assert match.match_confidence >= 0.85
    assert match.novelty_pressure == "high"


def test_choose_best_match_returns_manual_review_for_close_candidates():
    strong = score_linkedin_identity_match(
        LinkedInIdentityHints(candidate_name="Ada Lovelace", company="Anthropic"),
        matched_name="Ada Lovelace",
        matched_company="Anthropic",
        matched_profile_url="/talent/profile/ada-1",
    )
    close = score_linkedin_identity_match(
        LinkedInIdentityHints(candidate_name="Ada Lovelace", company="Anthropic"),
        matched_name="Ada Lovelace",
        matched_company="Anthropic",
        matched_profile_url="/talent/profile/ada-2",
    )

    classification, best = choose_best_match([strong, close])

    assert classification == "manual_review"
    assert best is not None


def test_choose_best_match_returns_none_for_low_confidence_pool():
    weak = score_linkedin_identity_match(
        LinkedInIdentityHints(candidate_name="Ada Lovelace"),
        matched_name="Grace Hopper",
        matched_company="Different Corp",
        matched_profile_url="/talent/profile/grace",
    )

    classification, best = choose_best_match([weak])

    assert classification == "no_confident_match"
    assert best is None


def test_classify_recruiter_activity_pressure_is_explainable():
    assert classify_recruiter_activity_pressure(None) == "low"
    assert classify_recruiter_activity_pressure(
        RecruiterActivitySnapshot(message_count=2, project_count=1, view_count=1)
    ) == "low"
    assert classify_recruiter_activity_pressure(
        RecruiterActivitySnapshot(message_count=4, project_count=1, view_count=1)
    ) == "medium"
    assert classify_recruiter_activity_pressure(
        RecruiterActivitySnapshot(message_count=7, project_count=3, view_count=3)
    ) == "high"
