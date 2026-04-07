"""Phase 0 characterization tests for frozen contracts."""

from __future__ import annotations

from dataclasses import fields
from pathlib import Path
import re

from github.schemas import GitHubProgress, GitHubSearchQuery
from shared.bias_controls import SAVE_DECISIONS as BIAS_SAVE_DECISIONS
from shared.brief_loader import Brief as NormalizedBrief, load_brief
from shared.brief_schema import Brief as V2Brief
from shared.contracts import (
    ACTIVE_FACIAL_DECISIONS,
    BRIEF_FAMILIES,
    COMPAT_FACIAL_DECISIONS,
    FAILURE_DECISIONS,
    FULL_DECISIONS,
    GITHUB_QUERY_STATUSES,
    LINKEDIN_STRING_STATUSES,
    NORMALIZED_BRIEF_REQUIRED_FIELDS,
    RUN_LOG_EVENTS,
    SAVE_DECISIONS,
    TARGET_CANDIDATE_LIFECYCLE,
    V2_BRIEF_REQUIRED_FIELDS,
)
from shared.judger import is_failure_decision
from shared.schemas import Progress, SearchString


ROOT = Path(__file__).parent.parent


def test_brief_family_contract_is_frozen():
    assert BRIEF_FAMILIES == {"legacy", "v2"}


def test_normalized_brief_contract_fields_exist():
    actual_fields = {f.name for f in fields(NormalizedBrief)}
    assert NORMALIZED_BRIEF_REQUIRED_FIELDS <= actual_fields


def test_v2_brief_contract_fields_exist():
    actual_fields = {f.name for f in fields(V2Brief)}
    assert V2_BRIEF_REQUIRED_FIELDS <= actual_fields


def test_legacy_and_v2_briefs_load_under_current_contracts():
    legacy = load_brief(ROOT / "config" / "FDL-Brazil" / "brief-brazil-real.json")
    v2 = load_brief(ROOT / "config" / "Head-of-FDE" / "brief-head-fde-enterprise-ai-nyc-v5.json")

    assert legacy.has_v2_schema is False
    assert v2.has_v2_schema is True

    for field_name in NORMALIZED_BRIEF_REQUIRED_FIELDS:
        assert hasattr(legacy, field_name)
        assert hasattr(v2, field_name)

    for field_name in V2_BRIEF_REQUIRED_FIELDS:
        assert hasattr(v2._new_brief, field_name)


def test_decision_contracts_align_with_current_helpers():
    for decision in FAILURE_DECISIONS:
        assert is_failure_decision(decision) is True

    for decision in ACTIVE_FACIAL_DECISIONS | COMPAT_FACIAL_DECISIONS | SAVE_DECISIONS | {"REJECT"}:
        assert is_failure_decision(decision) is False

    assert SAVE_DECISIONS == BIAS_SAVE_DECISIONS
    assert SAVE_DECISIONS <= FULL_DECISIONS


def test_current_status_defaults_fit_frozen_contracts():
    assert SearchString(id=1, name="x", boolean="y").status in LINKEDIN_STRING_STATUSES
    assert Progress(brief_name="test").strings == []

    assert GitHubSearchQuery(id=1, name="x", query="y", channel="user_search").status in GITHUB_QUERY_STATUSES
    assert GitHubProgress(brief_name="test").queries == []


def test_target_candidate_lifecycle_is_frozen_for_phase2():
    assert TARGET_CANDIDATE_LIFECYCLE == (
        "discovered",
        "snippet_extracted",
        "facial_started",
        "facial_terminal",
        "full_started",
        "full_terminal",
        "failed_retryable",
        "failed_terminal",
    )


def test_run_log_event_vocabulary_matches_current_emitters():
    source_paths = [
        ROOT / "linkedin" / "orchestrator.py",
        ROOT / "linkedin" / "acquisition.py",
        ROOT / "linkedin" / "side_effects.py",
        ROOT / "github" / "orchestrator.py",
        ROOT / "github" / "acquisition.py",
        ROOT / "github" / "side_effects.py",
    ]
    event_pattern = re.compile(r'log_event\(\s*[^,]+,\s*"([^"]+)"', re.DOTALL)

    discovered = set()
    for path in source_paths:
        discovered.update(event_pattern.findall(path.read_text()))

    assert discovered == RUN_LOG_EVENTS
