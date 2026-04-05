"""GitHub strategy formation and adaptation — Opus plans and adjusts search execution.

Mirrors strategy.py but generates GitHub search queries instead of LinkedIn Booleans.
The brief is the primary input. Opus synthesizes GitHub API queries across four channels:
user search, code search, repo mining, and org exploration.

Two main functions:
1. form_github_strategy() — ONE Opus call to generate GitHub search queries from brief
2. adapt_after_batch() — ONE Opus call after each batch to adapt based on results
"""

from __future__ import annotations

import json
import sys
from typing import Optional

from github.schemas import GitHubSearchQuery, GitHubBatchReport
from github.query_validator import validate_batch
from shared.llm_clients import opus_llm_cached
from shared.brief_loader import Brief
import github.config as gc


# ---------------------------------------------------------------------------
# Strategy formation (run start)
# ---------------------------------------------------------------------------

def form_github_strategy(
    brief: Brief,
    prior_run_data: Optional[dict] = None,
    include_default_repos: bool = True,
    include_default_orgs: bool = True,
) -> tuple[list[GitHubSearchQuery], str]:
    """Ask Opus to generate GitHub search queries from the sourcing brief.

    Returns (queries, rationale) tuple.
    """
    system = _build_strategy_system(brief)
    user_prompt = _build_strategy_user(brief, prior_run_data)

    try:
        result = opus_llm_cached(system, user_prompt, expect_json=True, max_tokens=16384)
    except Exception as e:
        return _default_queries(brief, include_default_repos, include_default_orgs), f"Fallback: {e}"

    rationale = result.get("strategy_rationale", "")
    queries = _parse_strategy_response(result)

    # Validate and repair LLM-generated queries
    queries, _validation_results = validate_batch(queries, brief, set())

    # Append default repo mining and org exploration queries if configured
    next_id = max((q.id for q in queries), default=0) + 1
    if include_default_repos:
        for repo in gc.FRONTIER_AI_REPOS:
            queries.append(GitHubSearchQuery(
                id=next_id,
                name=f"Mine contributors: {repo}",
                query="",
                channel="repo_mining",
                target_repo=repo,
            ))
            next_id += 1

    if include_default_orgs:
        for org in gc.FRONTIER_AI_ORGS:
            queries.append(GitHubSearchQuery(
                id=next_id,
                name=f"Explore org: {org}",
                query="",
                channel="org_exploration",
                target_org=org,
            ))
            next_id += 1

    # Add default stargazer mining for discriminating repos
    for repo in gc.DISCRIMINATING_REPOS:
        queries.append(GitHubSearchQuery(
            id=next_id,
            name=f"Stargazer mining: {repo}",
            query="",
            channel="stargazer_mining",
            target_repo=repo,
        ))
        next_id += 1

    return queries, rationale


def _build_strategy_system(brief: Brief) -> str:
    noise_section = ""
    if brief.noise_archetypes:
        noise_section = f"\n## Noise Archetypes (people to avoid)\n{json.dumps(brief.noise_archetypes, indent=2)}"

    toolchain_section = "\n## Frontier Toolchain (practitioner fingerprints)\n"
    for area, frameworks in gc.FRONTIER_TOOLCHAIN.items():
        toolchain_section += f"  {area}: {', '.join(frameworks)}\n"

    return f"""You are a senior technical sourcing strategist planning a GitHub-based candidate search.

Role: {brief.role_title}
{brief.role_description}

## Minimum Bar
{brief.minimum_bar}

## Archetypes (target candidate profiles)
{json.dumps(brief.archetypes, indent=2)}
{noise_section}
{toolchain_section}
## Geography
{json.dumps(brief.permanent_filters, indent=2)}

## Your Task

Generate GitHub search queries across FIVE channels to find candidates matching this role.
GitHub is NOT LinkedIn — the signal comes from what people BUILD, not their job titles.

### Channel 1: User Search Queries
GitHub user search syntax: `GET /search/users?q=...`

Available filters:
- `language:python` — primary programming language
- `location:Brazil` or `location:"São Paulo"` — profile location (free text, ~30% fill rate)
- `followers:>50` or `followers:10..100` — follower count range
- `repos:>10` — minimum public repo count
- `created:>2015-01-01` or `created:2018..2022` — account creation date
- `type:user` — exclude orgs
- Free text terms match against username, name, bio, and README

CRITICAL CONSTRAINT: GitHub search returns max 1,000 results per query.
For broad queries that would return >1,000, you MUST segment by follower ranges or date ranges.

Example segmentation:
- `language:python location:Brazil followers:>100` (narrower, likely <1000)
- `language:python location:Brazil followers:50..100` (narrower)
- `language:python location:Brazil followers:20..50 created:>2020-01-01` (very narrow)

Generate 15-30 user search queries covering:
- Geographic segments (by location variants: country, major cities)
- Skill segments (by language: Python, Rust, C++, Julia)
- Seniority segments (by follower/repo count bands)
- Topic segments (free text terms in bio: "reinforcement learning", "RLHF", "LLM", etc.)

### Channel 2: Code Search Queries
GitHub code search syntax: `GET /search/code?q=...`

Searches code content inside repositories. Returns repos, not users — we extract contributors afterward.
VERY rate-limited: 10 requests/minute. Generate 5-10 high-value queries only.

Available filters:
- `language:python` — file language
- `extension:py` — file extension
- `repo:owner/name` — limit to specific repo
- `path:src/` — limit to path
- Free text matches code content

Best for: finding practitioners by what they've actually built. Search for specific imports,
function calls, or config patterns that only real practitioners would have.

Examples:
- `"from trl import" language:python` — people using TRL for RLHF
- `"PPOTrainer" extension:py` — people implementing PPO training
- `"reward_model" "train" language:python` — reward model training code
- `"SFTTrainer" language:python` — supervised fine-tuning practitioners
- `"grpo" OR "group_relative_policy" language:python` — GRPO implementers

Generate code search queries that surface repos with domain-specific code.
Each repo's top contributors become candidates.

### Channel 3: Repo Topic Search Queries
GitHub repo search syntax: `GET /search/repositories?q=...`

Search for repos tagged with capability-area topics. Extract owner usernames as candidates.
High signal — people who tag repos with `rlhf` or `reward-model` are self-identifying as practitioners.

Available filters:
- `topic:reinforcement-learning` — repo topics
- `language:python` — primary language
- `stars:>20` — minimum stars (filters noise)
- `pushed:>2024-01-01` — recently active
- Free text matches repo name and description

Generate 5-10 topic search queries targeting repos in capability area domains.

### Tapped-Market / Edge-Case Opening

If the brief says the obvious pool is tapped, exhausted, or already heavily worked, then your opening GitHub queries should prioritize non-obvious adjacent builders rather than the canonical framework crowd.

Use this mental loop:
1. First ask what a strong but standard technical sourcer would search on GitHub for this role.
2. Then ask which same-caliber builders that standard pass would miss because their repos emphasize product/problem language, delivery tooling, internal platforms, or adjacent systems work instead of canonical framework names.
3. Generate your opening queries primarily for those missed populations.

For the initial query slate:
- Prefer profiles and repos that signal delivery accelerators, reference architectures, eval harnesses, tracing/observability, internal tools, product/problem-language AI systems, or consultancy/vertical-SaaS builders
- Do NOT over-concentrate the opening set on exact canonical framework imports or frontier-brand clusters alone
- Treat direct framework-name and obvious frontier-repo mining as cleanup/completion passes, not the only opening move

NOVELTY ACCOUNTING:
- In a tapped market, direct framework-import hits and frontier-brand repo hits are useful confirmation but low-novelty signal.
- Do not treat a strong yield from those obvious pools as proof the opening query mix is correct.
- Aim for the opening slate to surface adjacent but same-caliber builders whose repos emphasize delivery tooling, product/problem language, internal platforms, or reusable implementation patterns.

### Channel 4: Stargazer Mining
For discriminating repos — niche ML training/eval repos where STARRING itself is a signal.
Not for popular general repos (too noisy). Target repos like OpenRLHF/OpenRLHF,
axolotl-ai-cloud/axolotl, EleutherAI/lm-evaluation-harness, etc.

Generate 3-5 discriminating repos to mine stargazers from.

### Channel 5: Seed Experts for Graph Expansion
Nominate 3-5 known experts in the target domain whose followers/following should be mined.
These should be well-known figures in the specific capability areas (e.g., RLHF researchers,
eval framework authors, training infrastructure leads). Their social graph will be expanded
to discover practitioners who are invisible to keyword search.

### Output Format

Return JSON:
{{
    "strategy_rationale": "Overall approach explanation",
    "user_search_queries": [
        {{
            "query": "language:python location:Brazil followers:>50 reinforcement learning",
            "name": "Python RL engineers in Brazil (high followers)",
            "rationale": "Why this query targets the right population"
        }}
    ],
    "code_search_queries": [
        {{
            "query": "\\"from trl import\\" language:python",
            "name": "TRL library users",
            "rationale": "Why this code pattern signals frontier AI practitioners"
        }}
    ],
    "topic_search_queries": [
        {{
            "query": "topic:reinforcement-learning topic:rlhf language:python stars:>20",
            "name": "RLHF repos",
            "rationale": "Why this topic combination targets practitioners"
        }}
    ],
    "stargazer_repos": [
        {{
            "repo": "OpenRLHF/OpenRLHF",
            "rationale": "Why stargazers of this repo are high-signal candidates"
        }}
    ],
    "seed_experts": [
        {{
            "username": "expert_username",
            "rationale": "Why this person's network contains candidates"
        }}
    ],
    "coverage_gaps": ["Populations this strategy might miss"],
    "noise_predictions": ["Expected false positive patterns"]
}}

Guidelines:
- Bio text search is fuzzy — use distinctive terms ("RLHF", "reward model", "post-training") not generic ones ("AI", "machine learning")
- Location field is free text — include country name AND major cities as separate queries
- Portuguese/Spanish bios are common in LATAM — include both English and local-language terms where relevant
- Follower count correlates with seniority but not perfectly — don't over-filter
- Account age filters help target experienced engineers (created before 2020) vs newer accounts

Return valid JSON only."""


def _build_strategy_user(
    brief: Brief,
    prior_run_data: Optional[dict] = None,
) -> str:
    prompt = ""

    if brief.jd_text:
        prompt += f"## Job Description\n{brief.jd_text}\n\n"

    if brief.intake_notes:
        prompt += f"## Intake Notes\n{brief.intake_notes}\n\n"

    if prior_run_data:
        prompt += f"## Prior Run Data\n{json.dumps(prior_run_data, indent=2)}\n\n"

    if brief.search_priorities:
        prompt += f"## Search Priorities\n{', '.join(brief.search_priorities)}\n\n"

    if brief.additional_search_terms:
        prompt += (
            "## Additional Search Terms\n"
            "These terms should be used for search query generation but are NOT evaluation criteria:\n"
            f"{', '.join(brief.additional_search_terms)}\n\n"
        )

    if brief.instructions:
        prompt += "## Sourcing Instructions\n" + "\n".join(f"- {i}" for i in brief.instructions) + "\n\n"

    prompt += "Generate GitHub search queries for this role."
    return prompt


def _parse_strategy_response(result: dict) -> list[GitHubSearchQuery]:
    """Parse Opus strategy response into GitHubSearchQuery objects."""
    queries = []
    query_id = 1

    for uq in result.get("user_search_queries", []):
        queries.append(GitHubSearchQuery(
            id=query_id,
            name=uq.get("name", f"User search #{query_id}"),
            query=uq.get("query", ""),
            channel="user_search",
        ))
        query_id += 1

    for cq in result.get("code_search_queries", []):
        queries.append(GitHubSearchQuery(
            id=query_id,
            name=cq.get("name", f"Code search #{query_id}"),
            query=cq.get("query", ""),
            channel="code_search",
        ))
        query_id += 1

    for tq in result.get("topic_search_queries", []):
        queries.append(GitHubSearchQuery(
            id=query_id,
            name=tq.get("name", f"Topic search #{query_id}"),
            query=tq.get("query", ""),
            channel="topic_search",
        ))
        query_id += 1

    for sr in result.get("stargazer_repos", []):
        queries.append(GitHubSearchQuery(
            id=query_id,
            name=f"Stargazer mining: {sr.get('repo', '')}",
            query="",
            channel="stargazer_mining",
            target_repo=sr.get("repo", ""),
        ))
        query_id += 1

    for se in result.get("seed_experts", []):
        queries.append(GitHubSearchQuery(
            id=query_id,
            name=f"Graph expansion: {se.get('username', '')}",
            query=se.get("username", ""),
            channel="graph_expansion",
        ))
        query_id += 1

    return queries


def _default_queries(
    brief: Brief,
    include_repos: bool = True,
    include_orgs: bool = True,
) -> list[GitHubSearchQuery]:
    """Fallback queries when strategy formation fails."""
    queries = []
    query_id = 1

    # Extract location from permanent_filters
    locations = []
    for f in brief.permanent_filters:
        if isinstance(f, dict):
            loc = f.get("location", f.get("value", ""))
            if loc:
                locations.append(loc)
        elif isinstance(f, str):
            locations.append(f)
    if not locations:
        locations = ["Brazil"]

    # Basic user search queries
    for loc in locations:
        for lang in ["python", "rust", "cpp"]:
            queries.append(GitHubSearchQuery(
                id=query_id,
                name=f"Fallback: {lang} engineers in {loc}",
                query=f"language:{lang} location:{loc} followers:>20",
                channel="user_search",
            ))
            query_id += 1

    # Default repo mining
    if include_repos:
        for repo in gc.FRONTIER_AI_REPOS[:5]:
            queries.append(GitHubSearchQuery(
                id=query_id,
                name=f"Mine contributors: {repo}",
                query="",
                channel="repo_mining",
                target_repo=repo,
            ))
            query_id += 1

    # Default org exploration
    if include_orgs:
        for org in gc.FRONTIER_AI_ORGS[:4]:
            queries.append(GitHubSearchQuery(
                id=query_id,
                name=f"Explore org: {org}",
                query="",
                channel="org_exploration",
                target_org=org,
            ))
            query_id += 1

    return queries


# ---------------------------------------------------------------------------
# Adaptation after batch completion
# ---------------------------------------------------------------------------

def adapt_after_batch(
    brief: Brief,
    batch_report: GitHubBatchReport,
    remaining_queries: list[GitHubSearchQuery],
    executed_queries: set[str] | None = None,
    exhaustion_context: str = "",
) -> tuple[list[GitHubSearchQuery], str, list[int]]:
    """Ask Opus to adapt after a batch of queries — generate new queries from results.

    Returns (new_queries, rationale, skipped_ids) tuple.
    """
    geo = brief.permanent_filters.get("Location", "")
    geo_constraint = ""
    if geo:
        geo_constraint = f"""
GEOGRAPHY CONSTRAINT: This search is restricted to {geo}. ALL new user_search queries MUST include 'location:{geo}' in the query string. Do NOT generate queries targeting other geographies (India, Europe, etc.). Code search, repo mining, stargazer mining, and topic search are global by design — the geo filter is applied post-hoc — but user_search queries MUST be geo-scoped."""

    exhaustion_section = ""
    if exhaustion_context:
        exhaustion_section = f"""

## Channel Exhaustion Status
{exhaustion_context}

Do NOT generate new queries for EXHAUSTED channels. For DEGRADED channels,
only generate queries that meaningfully differ from previous attempts."""

    system = f"""You are a sourcing strategist adapting a GitHub search plan mid-run.

Role: {brief.role_title}
{brief.role_description}
{geo_constraint}

You've received a report on a batch of completed GitHub searches. Based on the results:
1. Generate NEW GitHub search queries that target signal patterns you observed
2. Identify remaining queued queries to skip (redundant or similar to zero-save queries)

## CRITICAL: GitHub Search API Syntax

Every query you generate must be a valid GitHub search API `q` parameter string,
NOT a natural language description.

### Valid user_search examples:
- `language:python location:Brazil followers:>50`
- `"reinforcement learning" location:Brazil language:python`
- `language:rust location:"São Paulo" repos:>10`
- `"RLHF" location:Brazil followers:20..100`

### INVALID user_search examples (DO NOT generate these):
- `ML ultra-low followers highly active Brazil` ← natural language, not API syntax
- `experienced Python developers in São Paulo` ← no qualifiers
- `ML exact pattern that saved v3` ← meta-description, not a query

### Valid code_search examples:
- `"from trl import" language:python`
- `"PPOTrainer" extension:py`
- `"reward_model" "train" language:python`

### Valid topic_search examples:
- `topic:reinforcement-learning language:python stars:>20`
- `topic:rlhf pushed:>2024-01-01`

Focus on:
- Queries that produced saves → generate adjacent/deeper queries in the same vein
- Languages and repos common in saved candidates → mine those repos, search those language+topic combos
- Queries that hit the 1,000 result cap → suggest narrower segmentations
- Zero-save queries → avoid similar patterns
- If the brief says the obvious pool is tapped, prefer extending productive edge-case populations before adding more canonical framework-name or frontier-brand cleanup queries
- Keep asking which same-caliber builders a standard technical sourcer would still miss, and bias new queries toward those adjacent populations first
{exhaustion_section}

Return JSON:
{{
    "new_user_queries": [
        {{"query": "...", "name": "...", "rationale": "..."}}
    ],
    "new_code_queries": [
        {{"query": "...", "name": "...", "rationale": "..."}}
    ],
    "new_topic_queries": [
        {{"query": "...", "name": "...", "rationale": "..."}}
    ],
    "new_stargazer_repos": ["owner/repo"],
    "new_repos_to_mine": ["owner/repo"],
    "skip_query_ids": [1, 2],
    "rationale": "Overall adaptation reasoning"
}}

Return valid JSON only."""

    remaining_text = "\n".join(
        f"  #{q.id} [{q.channel}]: {q.name}" for q in remaining_queries
    )

    user_prompt = f"""{batch_report.to_summary_text()}

## Remaining Queued Queries ({len(remaining_queries)})
{remaining_text}

Suggest adaptations."""

    try:
        result = opus_llm_cached(system, user_prompt, expect_json=True)
    except Exception as e:
        return [], f"Adaptation failed: {e}", []

    # Parse new queries
    new_queries = []
    next_id = max((q.id for q in remaining_queries), default=100) + 1

    for uq in result.get("new_user_queries", []):
        new_queries.append(GitHubSearchQuery(
            id=next_id,
            name=uq.get("name", f"Adapted user search #{next_id}"),
            query=uq.get("query", ""),
            channel="user_search",
        ))
        next_id += 1

    for cq in result.get("new_code_queries", []):
        new_queries.append(GitHubSearchQuery(
            id=next_id,
            name=cq.get("name", f"Adapted code search #{next_id}"),
            query=cq.get("query", ""),
            channel="code_search",
        ))
        next_id += 1

    for repo in result.get("new_repos_to_mine", []):
        new_queries.append(GitHubSearchQuery(
            id=next_id,
            name=f"Mine contributors: {repo}",
            query="",
            channel="repo_mining",
            target_repo=repo,
        ))
        next_id += 1

    for tq in result.get("new_topic_queries", []):
        new_queries.append(GitHubSearchQuery(
            id=next_id,
            name=tq.get("name", f"Adapted topic search #{next_id}"),
            query=tq.get("query", ""),
            channel="topic_search",
        ))
        next_id += 1

    for repo in result.get("new_stargazer_repos", []):
        new_queries.append(GitHubSearchQuery(
            id=next_id,
            name=f"Stargazer mining: {repo}",
            query="",
            channel="stargazer_mining",
            target_repo=repo,
        ))
        next_id += 1

    # Cap adaptation output at 10 queries per cycle
    if len(new_queries) > 10:
        new_queries = new_queries[:10]

    # Validate adapted queries
    new_queries, _validation_results = validate_batch(
        new_queries, brief, executed_queries or set()
    )

    # Mark skipped queries
    skip_ids = list(result.get("skip_query_ids", []))
    for q in remaining_queries:
        if q.id in set(skip_ids):
            q.status = "skipped"
            q.notes = "Skipped by adaptation"

    rationale = result.get("rationale", "")
    return new_queries, rationale, skip_ids
