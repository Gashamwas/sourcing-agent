from github.recruiter_identity_report import (
    build_recruiter_identity_row,
    build_recruiter_identity_summary,
    write_recruiter_reconciliation_saved_jsonl,
)
from shared.recruiter_identity_schemas import PlausibleProfileReview, RecruiterIdentityResolution


def test_build_recruiter_identity_summary_counts_actions_and_saved_top_cards():
    rows = [
        {
            "final_action": "SAVE",
            "final_subreason": "",
            "opened_profile": True,
            "novelty_pressure": "medium",
            "reachout_status": "messaged",
            "top_candidates": [
                {"already_saved": True},
            ],
        },
        {
            "final_action": "MANUAL_REVIEW",
            "final_subreason": "identity_ambiguous",
            "opened_profile": False,
            "novelty_pressure": "low",
            "top_candidates": [
                {"already_saved": False},
            ],
        },
    ]

    summary = build_recruiter_identity_summary(rows, input_stats={"processed_leads": 2})

    assert summary["total_leads"] == 2
    assert summary["action_counts"]["SAVE"] == 1
    assert summary["action_counts"]["MANUAL_REVIEW"] == 1
    assert summary["subreason_counts"]["identity_ambiguous"] == 1
    assert summary["opened_profile_count"] == 1
    assert summary["top1_already_saved_count"] == 1
    assert summary["novelty_counts"]["medium"] == 1
    assert summary["reachout_counts"]["messaged"] == 1
    assert summary["input_stats"]["processed_leads"] == 2


def test_build_recruiter_identity_summary_counts_identity_classification_and_full_judge_calls():
    rows = [
        {
            "final_action": "REJECT",
            "final_subreason": "no_plausible_profile",
            "identity_classification": "no_confident_match",
            "opened_profile": False,
            "plausible_profile_reviews": [],
        },
        {
            "final_action": "REJECT",
            "final_subreason": "no_plausible_profile",
            "identity_classification": "no_confident_match",
            "opened_profile": False,
            "plausible_profile_reviews": [],
        },
        {
            "final_action": "REJECT",
            "final_subreason": "fit_reject",
            "identity_classification": "single_strong_plausible_profile",
            "opened_profile": True,
            "plausible_profile_reviews": [
                {"rank": 1, "extraction_failed": False},
            ],
        },
        {
            "final_action": "REJECT",
            "final_subreason": "fit_reject",
            "identity_classification": "ambiguity_multi_review",
            "opened_profile": True,
            "plausible_profile_reviews": [
                {"rank": 1, "extraction_failed": False},
                {"rank": 2, "extraction_failed": False},
                {"rank": 3, "extraction_failed": False},
            ],
        },
        {
            "final_action": "REJECT",
            "final_subreason": "fit_reject",
            "identity_classification": "single_strong_plausible_profile",
            "opened_profile": True,
            "plausible_profile_reviews": [
                {"rank": 1, "extraction_failed": False},
            ],
        },
    ]

    summary = build_recruiter_identity_summary(rows)

    assert summary["identity_classification_counts"] == {
        "no_confident_match": 2,
        "single_strong_plausible_profile": 2,
        "ambiguity_multi_review": 1,
    }
    assert summary["opened_profile_count"] == 3
    # 0 + 0 + 1 + 3 + 1 = 5 -- matches the on-disk 5-lead recruiter dry-run.
    assert summary["full_judge_call_count"] == 5


def test_build_recruiter_identity_summary_full_judge_excludes_failed_extractions():
    rows = [
        {
            "final_action": "MANUAL_REVIEW",
            "final_subreason": "tool_failure",
            "identity_classification": "single_strong_plausible_profile",
            "opened_profile": True,
            "plausible_profile_reviews": [
                {"rank": 1, "extraction_failed": True},
            ],
        },
        {
            "final_action": "REJECT",
            "final_subreason": "fit_reject",
            "identity_classification": "ambiguity_multi_review",
            "opened_profile": True,
            "plausible_profile_reviews": [
                {"rank": 1, "extraction_failed": False},
                {"rank": 2, "extraction_failed": True},
            ],
        },
    ]

    summary = build_recruiter_identity_summary(rows)

    # Extraction-failed reviews never reach full_judge, so they are not counted.
    assert summary["full_judge_call_count"] == 1


def test_build_recruiter_identity_summary_handles_rows_missing_classification_or_reviews():
    rows = [
        # legacy / partial row with no identity_classification and no reviews field
        {"final_action": "SAVE"},
        {"final_action": "REJECT", "final_subreason": "fit_reject"},
    ]

    summary = build_recruiter_identity_summary(rows)

    assert summary["identity_classification_counts"] == {}
    assert summary["full_judge_call_count"] == 0
    assert summary["total_leads"] == 2


def test_build_recruiter_identity_row_includes_plausible_profile_reviews():
    result = RecruiterIdentityResolution(
        github_username="ada",
        candidate_name="Ada Lovelace",
        lookup_name="Ada Lovelace",
    )
    result.ambiguity_multi_review = True
    result.plausible_profile_reviews = [
        PlausibleProfileReview(rank=1, profile_url="/p1", gate_final_action="REJECT"),
        PlausibleProfileReview(rank=2, profile_url="/p2", gate_final_action="SAVE"),
    ]
    row = build_recruiter_identity_row(result)
    assert row["plausible_profile_reviews_count"] == 2
    assert row["ambiguity_multi_review"] is True
    assert isinstance(row.get("plausible_profile_reviews"), list)
    assert len(row["plausible_profile_reviews"]) == 2


def test_write_recruiter_reconciliation_saved_jsonl_filters_rows(tmp_path):
    rows = [
        {"github_username": "a", "final_action": "SAVE"},
        {"github_username": "b", "final_action": "REJECT"},
    ]
    out = write_recruiter_reconciliation_saved_jsonl(tmp_path / "saved.jsonl", rows)
    lines = out.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    assert '"github_username": "a"' in lines[0]


def test_saved_jsonl_excludes_manual_multi_review_rows(tmp_path):
    rows = [
        {"github_username": "win", "final_action": "SAVE"},
        {
            "github_username": "lose",
            "final_action": "MANUAL_REVIEW",
            "final_subreason": "identity_ambiguous",
            "ambiguity_multi_review": True,
            "plausible_profile_reviews": [{"rank": 1}, {"rank": 2}],
        },
    ]
    out = write_recruiter_reconciliation_saved_jsonl(tmp_path / "s.jsonl", rows)
    lines = out.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    assert "win" in lines[0]
