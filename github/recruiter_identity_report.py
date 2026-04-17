"""Writers for Recruiter-first reconciliation artifacts."""

from __future__ import annotations

import csv
import json
from pathlib import Path

from shared.recruiter_identity_schemas import RecruiterIdentityResolution


def build_recruiter_identity_row(result: RecruiterIdentityResolution) -> dict:
    row = result.to_dict()
    row["plausible_profile_reviews_count"] = len(result.plausible_profile_reviews)
    row["ambiguity_multi_review"] = result.ambiguity_multi_review
    top1 = result.top_candidates[0] if result.top_candidates else None
    row["top_candidate_name"] = top1.name if top1 else ""
    row["top_candidate_profile_url"] = top1.profile_url if top1 else ""
    row["top_candidate_company"] = top1.current_company if top1 else ""
    row["top_candidate_location"] = top1.location if top1 else ""
    row["top_candidate_confidence"] = top1.match_confidence if top1 else 0.0
    profile_status = row.get("profile_status") if isinstance(row.get("profile_status"), dict) else {}
    row["profile_saved_by"] = str(profile_status.get("saved_by", "") or "")
    row["profile_message_count"] = int(profile_status.get("message_count", 0) or 0)
    row["profile_project_count"] = int(profile_status.get("project_count", 0) or 0)
    row["profile_view_count"] = int(profile_status.get("view_count", 0) or 0)
    row["profile_last_outbound_contact"] = str(profile_status.get("last_outbound_contact", "") or "")
    return row


def write_recruiter_identity_jsonl(path: str | Path, rows: list[dict]) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row) + "\n")
    return path


def write_recruiter_reconciliation_saved_jsonl(path: str | Path, rows: list[dict]) -> Path:
    saved = [row for row in rows if str(row.get("final_action", "") or "").strip() == "SAVE"]
    return write_recruiter_identity_jsonl(path, saved)


def write_recruiter_identity_csv(path: str | Path, rows: list[dict]) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "github_username",
        "candidate_name",
        "lookup_name",
        "search_location",
        "query",
        "final_action",
        "final_subreason",
        "identity_classification",
        "linkedin_brief_path",
        "holistic_fit_decision",
        "holistic_fit_confidence",
        "holistic_fit_path",
        "holistic_fit_rationale",
        "rationale",
        "selected_candidate_rank",
        "selected_profile_url",
        "already_saved",
        "opened_profile",
        "recruiter_save_attempted",
        "recruiter_save_succeeded",
        "had_plausible_cards",
        "extraction_failed",
        "ambiguity_multi_review",
        "plausible_profile_reviews_count",
        "novelty_pressure",
        "reachout_status",
        "top_candidate_name",
        "top_candidate_profile_url",
        "top_candidate_company",
        "top_candidate_location",
        "top_candidate_confidence",
        "profile_saved_by",
        "profile_message_count",
        "profile_project_count",
        "profile_view_count",
        "profile_last_outbound_contact",
        "github_company",
        "github_location",
        "github_title",
        "notes",
    ]
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "github_username": row.get("github_username", ""),
                    "candidate_name": row.get("candidate_name", ""),
                    "lookup_name": row.get("lookup_name", ""),
                    "search_location": row.get("search_location", ""),
                    "query": row.get("query", ""),
                    "final_action": row.get("final_action", ""),
                    "final_subreason": row.get("final_subreason", ""),
                    "identity_classification": row.get("identity_classification", ""),
                    "linkedin_brief_path": row.get("linkedin_brief_path", ""),
                    "holistic_fit_decision": row.get("holistic_fit_decision", ""),
                    "holistic_fit_confidence": row.get("holistic_fit_confidence", 0.0),
                    "holistic_fit_path": row.get("holistic_fit_path", ""),
                    "holistic_fit_rationale": row.get("holistic_fit_rationale", ""),
                    "rationale": row.get("rationale", ""),
                    "selected_candidate_rank": row.get("selected_candidate_rank", 0),
                    "selected_profile_url": row.get("selected_profile_url", ""),
                    "already_saved": row.get("already_saved", False),
                    "opened_profile": row.get("opened_profile", False),
                    "recruiter_save_attempted": row.get("recruiter_save_attempted", False),
                    "recruiter_save_succeeded": row.get("recruiter_save_succeeded", False),
                    "had_plausible_cards": row.get("had_plausible_cards", False),
                    "extraction_failed": row.get("extraction_failed", False),
                    "ambiguity_multi_review": row.get("ambiguity_multi_review", False),
                    "plausible_profile_reviews_count": row.get("plausible_profile_reviews_count", 0),
                    "novelty_pressure": row.get("novelty_pressure", ""),
                    "reachout_status": row.get("reachout_status", ""),
                    "top_candidate_name": row.get("top_candidate_name", ""),
                    "top_candidate_profile_url": row.get("top_candidate_profile_url", ""),
                    "top_candidate_company": row.get("top_candidate_company", ""),
                    "top_candidate_location": row.get("top_candidate_location", ""),
                    "top_candidate_confidence": row.get("top_candidate_confidence", 0.0),
                    "profile_saved_by": row.get("profile_saved_by", ""),
                    "profile_message_count": row.get("profile_message_count", 0),
                    "profile_project_count": row.get("profile_project_count", 0),
                    "profile_view_count": row.get("profile_view_count", 0),
                    "profile_last_outbound_contact": row.get("profile_last_outbound_contact", ""),
                    "github_company": row.get("github_company", ""),
                    "github_location": row.get("github_location", ""),
                    "github_title": row.get("github_title", ""),
                    "notes": " | ".join(row.get("notes", [])),
                }
            )
    return path


def write_recruiter_reconciliation_saved_csv(path: str | Path, rows: list[dict]) -> Path:
    saved = [row for row in rows if str(row.get("final_action", "") or "").strip() == "SAVE"]
    return write_recruiter_identity_csv(path, saved)


def build_recruiter_identity_summary(
    rows: list[dict],
    *,
    input_stats: dict | None = None,
) -> dict:
    total = len(rows)
    action_counts: dict[str, int] = {}
    subreason_counts: dict[str, int] = {}
    opened_profiles = 0
    top1_saved = 0
    novelty_counts: dict[str, int] = {}
    reachout_counts: dict[str, int] = {}
    for row in rows:
        action = str(row.get("final_action", "") or "").strip() or "unknown"
        action_counts[action] = action_counts.get(action, 0) + 1
        sub = str(row.get("final_subreason", "") or "").strip()
        if sub:
            subreason_counts[sub] = subreason_counts.get(sub, 0) + 1
        if row.get("opened_profile"):
            opened_profiles += 1
        novelty = str(row.get("novelty_pressure", "") or "").strip()
        if novelty:
            novelty_counts[novelty] = novelty_counts.get(novelty, 0) + 1
        reachout = str(row.get("reachout_status", "") or "").strip()
        if reachout:
            reachout_counts[reachout] = reachout_counts.get(reachout, 0) + 1
        top_candidates = row.get("top_candidates", [])
        if isinstance(top_candidates, list) and top_candidates:
            candidate = top_candidates[0]
            if isinstance(candidate, dict) and candidate.get("already_saved"):
                top1_saved += 1
    return {
        "total_leads": total,
        "action_counts": action_counts,
        "subreason_counts": subreason_counts,
        "opened_profile_count": opened_profiles,
        "top1_already_saved_count": top1_saved,
        "novelty_counts": novelty_counts,
        "reachout_counts": reachout_counts,
        "input_stats": input_stats or {},
    }


def write_recruiter_identity_summary(
    path: str | Path,
    rows: list[dict],
    *,
    input_stats: dict | None = None,
) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    summary = build_recruiter_identity_summary(rows, input_stats=input_stats)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(summary, handle, indent=2)
    return path
