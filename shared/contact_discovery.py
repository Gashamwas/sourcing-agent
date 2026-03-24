"""Contact information discovery from GitHub profiles.

Extracts emails from:
    1. User profile (public email field)
    2. Commit history (git author email)
    3. Social links (Twitter, LinkedIn, blog)

Filters out noreply@github.com and other bot/service addresses.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from github.schemas import ContactInfo, GitHubRepo

if TYPE_CHECKING:
    from github.client import GitHubClient


# Addresses to filter out
_NOREPLY_PATTERNS = [
    "noreply@github.com",
    "users.noreply.github.com",
    "noreply@",
    "no-reply@",
    "github-actions",
    "dependabot",
    "greenkeeper",
    "renovate",
]


def _is_real_email(email: str) -> bool:
    """Check if an email looks like a real person's address."""
    if not email or "@" not in email:
        return False
    email_lower = email.lower().strip()
    for pattern in _NOREPLY_PATTERNS:
        if pattern in email_lower:
            return False
    # Basic format check
    if not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email_lower):
        return False
    return True


async def discover_contacts(
    client: "GitHubClient",
    username: str,
    top_repos: list[GitHubRepo],
) -> ContactInfo:
    """Discover contact information for a GitHub user.

    Checks profile email, commit history, and social links.
    Returns ContactInfo with deduplicated, validated addresses.
    """
    emails: set[str] = set()
    contact = ContactInfo()

    # 1. Profile email (from get_user, already fetched)
    # The caller should have the user data; we check commit emails here

    # 2. Commit emails from their repos
    for repo in top_repos[:3]:  # Limit API calls
        if repo.is_fork:
            continue
        try:
            commits = await client.get_user_commits(
                repo.full_name or f"{username}/{repo.name}",
                author=username,
            )
            for commit in commits:
                commit_data = commit.get("commit", {})
                author_data = commit_data.get("author", {})
                email = author_data.get("email", "")
                if _is_real_email(email):
                    emails.add(email.lower().strip())
        except Exception:
            # Not fatal — commit fetch can fail for many reasons
            continue

    contact.emails = sorted(emails)

    # 3. Social links are extracted from the user profile by the enricher
    # (twitter_username, blog fields) — we just format them here if present

    return contact


def merge_profile_contact(contact: ContactInfo, user_email: str, twitter: str, blog: str) -> ContactInfo:
    """Merge additional contact info from the user profile into ContactInfo."""
    # Add profile email
    if _is_real_email(user_email):
        email_lower = user_email.lower().strip()
        if email_lower not in contact.emails:
            contact.emails = [email_lower] + contact.emails  # Profile email first

    # Twitter
    if twitter:
        contact.twitter_url = f"https://twitter.com/{twitter}"

    # Blog/website
    if blog:
        url = blog if blog.startswith("http") else f"https://{blog}"
        contact.website = url

        # Check if blog is a LinkedIn URL
        if "linkedin.com" in blog.lower():
            contact.linkedin_url = url

    return contact
