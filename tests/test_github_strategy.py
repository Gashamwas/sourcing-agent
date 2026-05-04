"""Tests for OSS Maintainers Slice 7 — target-project strategy seeding.

Pins the contract for ``_append_target_project_queries``:

- Empty ``brief.target_projects`` ⇒ no queries appended (byte-
  identical strategy for classic github briefs).
- Each entry seeds two queries: one ``repo_mining`` and one
  ``stargazer_mining``, both with the project as ``target_repo``.
- Stack hint surfaces in stargazer query name when ``target_stacks``
  is set; absent when not.
- Dedups against existing ``target_repo`` entries (so LLM-emitted +
  default repo seeding can't collide with target-project seeds).
- Returns the post-append ``next_id`` so the caller can continue
  numbering.

The wider :func:`form_github_strategy` requires Opus access for the
LLM call path; testing it would mean mocking that pipeline
end-to-end. The helper is the load-bearing seam for Slice 7's
behavior contract — testing it directly is the narrowest gate.
"""

from __future__ import annotations

from github.schemas import GitHubSearchQuery
from github.strategy import _append_target_project_queries


class _FakeBrief:
    """Minimal Brief-shaped object for the helper.

    The helper only reads ``target_projects`` and ``target_stacks``;
    constructing a full Brief through the loader would need a JSON
    fixture. This stub matches the dataclass surface the helper
    actually uses.
    """

    def __init__(
        self,
        *,
        target_projects: list[str] | None = None,
        target_stacks: list[str] | None = None,
    ) -> None:
        self.target_projects = list(target_projects or [])
        self.target_stacks = list(target_stacks or [])


def test_no_target_projects_appends_nothing() -> None:
    """Behavior-preserving: classic github briefs are byte-identical."""

    queries: list[GitHubSearchQuery] = []
    new_id = _append_target_project_queries(_FakeBrief(), queries, next_id=10)
    assert queries == []
    assert new_id == 10


def test_seeds_two_queries_per_target_project() -> None:
    queries: list[GitHubSearchQuery] = []
    new_id = _append_target_project_queries(
        _FakeBrief(target_projects=["kubernetes/kubernetes"]),
        queries,
        next_id=1,
    )

    assert len(queries) == 2
    channels = sorted(q.channel for q in queries)
    assert channels == ["repo_mining", "stargazer_mining"]
    assert all(q.target_repo == "kubernetes/kubernetes" for q in queries)
    # IDs are sequential and the returned next_id is past them.
    assert {q.id for q in queries} == {1, 2}
    assert new_id == 3


def test_seeds_per_target_in_order() -> None:
    queries: list[GitHubSearchQuery] = []
    new_id = _append_target_project_queries(
        _FakeBrief(
            target_projects=["kubernetes/kubernetes", "etcd-io/etcd"]
        ),
        queries,
        next_id=1,
    )

    assert len(queries) == 4
    # Order: repo_mining for k/k, stargazer for k/k, repo_mining for
    # etcd, stargazer for etcd.
    assert queries[0].target_repo == "kubernetes/kubernetes"
    assert queries[0].channel == "repo_mining"
    assert queries[1].target_repo == "kubernetes/kubernetes"
    assert queries[1].channel == "stargazer_mining"
    assert queries[2].target_repo == "etcd-io/etcd"
    assert queries[2].channel == "repo_mining"
    assert queries[3].target_repo == "etcd-io/etcd"
    assert queries[3].channel == "stargazer_mining"
    assert new_id == 5


def test_stack_hint_surfaces_in_stargazer_name() -> None:
    queries: list[GitHubSearchQuery] = []
    _append_target_project_queries(
        _FakeBrief(
            target_projects=["kubernetes/kubernetes"],
            target_stacks=["go", "container-orchestration"],
        ),
        queries,
        next_id=1,
    )

    stargazer = next(q for q in queries if q.channel == "stargazer_mining")
    assert "stack: go" in stargazer.name


def test_no_stack_hint_when_target_stacks_empty() -> None:
    queries: list[GitHubSearchQuery] = []
    _append_target_project_queries(
        _FakeBrief(target_projects=["kubernetes/kubernetes"]),
        queries,
        next_id=1,
    )

    stargazer = next(q for q in queries if q.channel == "stargazer_mining")
    assert "stack:" not in stargazer.name


def test_dedups_against_existing_target_repos() -> None:
    """If LLM strategy or default seeding already named the repo, skip it."""

    existing = [
        GitHubSearchQuery(
            id=99,
            name="LLM-emitted: Mine contributors of kubernetes/kubernetes",
            query="",
            channel="repo_mining",
            target_repo="kubernetes/kubernetes",
        )
    ]
    new_id = _append_target_project_queries(
        _FakeBrief(target_projects=["kubernetes/kubernetes"]),
        existing,
        next_id=100,
    )

    # No new queries appended (target already in the set).
    assert len(existing) == 1
    assert new_id == 100


def test_dedups_case_insensitively() -> None:
    """GitHub treats owner/repo case-insensitively; so does our dedup."""

    existing = [
        GitHubSearchQuery(
            id=1,
            name="Existing",
            query="",
            channel="repo_mining",
            target_repo="Kubernetes/Kubernetes",
        )
    ]
    _append_target_project_queries(
        _FakeBrief(target_projects=["kubernetes/kubernetes"]),
        existing,
        next_id=2,
    )

    # Still just the one existing entry.
    assert len(existing) == 1


def test_skips_blank_target_entries() -> None:
    queries: list[GitHubSearchQuery] = []
    _append_target_project_queries(
        _FakeBrief(target_projects=["", "  ", "kubernetes/kubernetes"]),
        queries,
        next_id=1,
    )
    assert len(queries) == 2
    assert queries[0].target_repo == "kubernetes/kubernetes"


def test_skips_non_string_entries() -> None:
    queries: list[GitHubSearchQuery] = []
    _append_target_project_queries(
        _FakeBrief(target_projects=["kubernetes/kubernetes", 42, None]),  # type: ignore[list-item]
        queries,
        next_id=1,
    )
    assert len(queries) == 2
    assert queries[0].target_repo == "kubernetes/kubernetes"
