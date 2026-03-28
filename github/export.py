"""CSV export for Gem/Greenhouse import.

Reads pipeline JSONL output, joins by username, filters to saved candidates,
and writes a CSV with columns that auto-map to Gem's field names.

Usage:
    python github_export.py output/github/
    python github_export.py output/github/ --out custom_path.csv
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path
from shared.storage import read_jsonl
from shared.judger import extract_priority_rank


# Column order — Gem standard fields first, then GitHub-specific custom fields
CSV_COLUMNS = [
    # Gem auto-map fields
    "First Name",
    "Last Name",
    "Email",
    "LinkedIn URL",
    "Company",
    "Title",
    "Location",
    "Source",
    # GitHub-specific (Gem custom fields)
    "GitHub URL",
    "GitHub Username",
    "Decision",
    "Confidence",
    "Capability Area",
    "Evaluation Summary",
    "Top Repos",
    "Toolchain",
    "ML Signal",
    "Papers",
    "Website",
    "Outreach Subject",
    "Outreach Message",
    "Priority Rank",
    "Source Query",
    "Source Channel",
]

SAVE_DECISIONS = {"SAVE", "INFERENTIAL_SAVE", "TRANSFERABLE_SAVE", "SIGNAL_SAVE"}


def _split_name(full_name: str, username: str = "") -> tuple[str, str]:
    """Split a full name into first and last. Falls back to username."""
    name = full_name.strip()
    if not name:
        return (username, "")
    parts = name.split(None, 1)
    if len(parts) == 1:
        return (parts[0], "")
    return (parts[0], parts[1])


def _extract_username(record: dict) -> str:
    """Extract username from a candidate or judgment record."""
    # candidates.jsonl has top-level "username" and nested user.username
    if "username" in record:
        return record["username"]
    if "user" in record and isinstance(record["user"], dict):
        return record["user"].get("username", "")
    # judgments have candidate_name but we join on username from candidates
    return record.get("candidate_name", "")


def export_saved_candidates_csv(
    output_dir: str | Path,
    csv_path: str | Path | None = None,
) -> Path:
    """Export saved candidates as a Gem/Greenhouse-compatible CSV.

    Returns the path to the written CSV file.
    """
    output_dir = Path(output_dir)
    if csv_path is None:
        csv_path = output_dir / "saved_candidates.csv"
    csv_path = Path(csv_path)

    # Read pipeline outputs
    candidates = read_jsonl(output_dir / "candidates.jsonl")
    judgments = read_jsonl(output_dir / "final_judgments.jsonl")
    outreach_records = read_jsonl(output_dir / "outreach.jsonl")

    # Build lookup tables by username
    candidate_by_username: dict[str, dict] = {}
    for c in candidates:
        username = _extract_username(c)
        if username:
            candidate_by_username[username] = c

    # Judgments: keep the last full-stage judgment per candidate
    judgment_by_name: dict[str, dict] = {}
    for j in judgments:
        name = j.get("candidate_name", "")
        if name and j.get("stage") == "full":
            judgment_by_name[name] = j

    # Outreach by username
    outreach_by_username: dict[str, dict] = {}
    for o in outreach_records:
        username = o.get("username", "")
        if username:
            outreach_by_username[username] = o

    # Match judgments to candidates
    # Judgments use candidate_name (display name), candidates use username
    # Build a name->username mapping from candidates
    name_to_username: dict[str, str] = {}
    for username, c in candidate_by_username.items():
        user = c.get("user", {})
        name = user.get("name", "") or user.get("username", username)
        name_to_username[name] = username
        # Also map username directly
        name_to_username[username] = username

    # Build rows for saved candidates
    rows: list[dict[str, str]] = []

    for candidate_name, judgment in judgment_by_name.items():
        decision = judgment.get("decision", "")
        if decision not in SAVE_DECISIONS:
            continue

        username = name_to_username.get(candidate_name, candidate_name)
        candidate = candidate_by_username.get(username, {})
        outreach = outreach_by_username.get(username, {})

        user = candidate.get("user", {})
        contact = candidate.get("contact", {})
        portfolio = candidate.get("portfolio_summary", {})

        # Name splitting
        full_name = user.get("name", "") or username
        first_name, last_name = _split_name(full_name, username)

        # Email: first non-noreply
        emails = contact.get("emails", [])
        email = emails[0] if emails else ""

        # Title: synthesized headline > bio
        title = candidate.get("synthesized_headline", "") or user.get("bio", "")
        # Truncate long bios
        if len(title) > 200:
            title = title[:197] + "..."

        # Top repos
        top_repos_list = candidate.get("top_repos", [])[:3]
        top_repos = ", ".join(
            f"{r.get('name', '')} ({r.get('stars', 0)} stars)"
            for r in top_repos_list
        )

        # Toolchain from portfolio summary
        toolchain_data = portfolio.get("toolchain_detected", {})
        toolchain = ", ".join(toolchain_data.get("frameworks", []))

        # ML signal
        ml_signal = portfolio.get("ml_signal_strength", "")

        # Papers
        paper_titles = candidate.get("paper_titles", [])
        papers = "; ".join(paper_titles) if paper_titles else ""

        # Website
        website = contact.get("website", "") or user.get("blog", "")

        # Capability area from judgment path
        path = judgment.get("path", "")
        # path format: "DIRECT:Area Name" or "DIRECT:Area|TRANSFERABLE"
        cap_area = ""
        if ":" in path:
            cap_area = path.split(":", 1)[1].split("|")[0]

        # Priority rank from capability area path
        priority_rank = extract_priority_rank(path)

        rows.append({
            "First Name": first_name,
            "Last Name": last_name,
            "Email": email,
            "LinkedIn URL": contact.get("linkedin_url", ""),
            "Company": user.get("company", ""),
            "Title": title,
            "Location": user.get("location", ""),
            "Source": "GitHub Sourcing Agent",
            "GitHub URL": user.get("profile_url", ""),
            "GitHub Username": username,
            "Decision": decision,
            "Confidence": f"{judgment.get('confidence', 0):.2f}",
            "Capability Area": cap_area,
            "Evaluation Summary": judgment.get("rationale", ""),
            "Top Repos": top_repos,
            "Toolchain": toolchain,
            "ML Signal": ml_signal,
            "Papers": papers,
            "Website": website,
            "Outreach Subject": outreach.get("subject_line", ""),
            "Outreach Message": outreach.get("message", ""),
            "Priority Rank": str(priority_rank) if priority_rank else "",
            "Source Query": candidate.get("source_query", ""),
            "Source Channel": candidate.get("source_strategy", ""),
        })

    # Sort by confidence descending
    rows.sort(key=lambda r: float(r.get("Confidence", "0")), reverse=True)

    # Write CSV
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)

    return csv_path


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python github_export.py <output_dir> [--out <csv_path>]")
        sys.exit(1)

    output_dir = sys.argv[1]
    csv_out = None
    if "--out" in sys.argv:
        idx = sys.argv.index("--out")
        if idx + 1 < len(sys.argv):
            csv_out = sys.argv[idx + 1]

    path = export_saved_candidates_csv(output_dir, csv_out)
    print(f"Exported to: {path}")
