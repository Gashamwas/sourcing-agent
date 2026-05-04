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
    FACIAL_DECISIONS,
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
import shared.judger as _judger
from shared.judger import is_failure_decision
from shared.runtime_state.store import (
    DEDUP_BLOCKING_DECISIONS,
    DEDUP_BLOCKING_LINKEDIN_DECISIONS,
    DEDUP_BLOCKING_RUNTIME_DECISIONS,
)
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
        ROOT / "linkedin" / "run_report.py",
        ROOT / "linkedin" / "search_mutation.py",
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


# ---------------------------------------------------------------------------
# FACIAL_BORDERLINE -- Step A of the slice 12 promotion plan.
#
# At Step A the constant is a *type-system widening* only. The parser,
# validator, orchestrator, runtime-state store, projections, and persistence
# layer must NOT yet recognize FACIAL_BORDERLINE. The tests below pin the
# shape of that boundary so the type-system widening cannot accidentally
# leak into runtime behavior, and so a future drive-by promotion is forced
# to think first.
# ---------------------------------------------------------------------------


def test_facial_borderline_is_active_decision():
    assert "FACIAL_BORDERLINE" in ACTIVE_FACIAL_DECISIONS


def test_facial_borderline_is_not_compat_decision():
    assert "FACIAL_BORDERLINE" not in COMPAT_FACIAL_DECISIONS


def test_facial_borderline_is_facial_decision():
    assert "FACIAL_BORDERLINE" in FACIAL_DECISIONS


def test_facial_borderline_is_not_failure_decision():
    assert "FACIAL_BORDERLINE" not in FAILURE_DECISIONS
    assert is_failure_decision("FACIAL_BORDERLINE") is False


def test_facial_borderline_is_not_dedup_blocking():
    assert "FACIAL_BORDERLINE" not in DEDUP_BLOCKING_LINKEDIN_DECISIONS
    assert "FACIAL_BORDERLINE" not in DEDUP_BLOCKING_DECISIONS
    assert "FACIAL_BORDERLINE" not in DEDUP_BLOCKING_RUNTIME_DECISIONS


def test_facial_borderline_parallels_facial_yes_dedup_status():
    assert "FACIAL_YES" in ACTIVE_FACIAL_DECISIONS
    assert "FACIAL_YES" not in DEDUP_BLOCKING_LINKEDIN_DECISIONS
    assert "FACIAL_BORDERLINE" in ACTIVE_FACIAL_DECISIONS
    assert "FACIAL_BORDERLINE" not in DEDUP_BLOCKING_LINKEDIN_DECISIONS
    assert "FACIAL_NO" in ACTIVE_FACIAL_DECISIONS
    assert "FACIAL_NO" in DEDUP_BLOCKING_LINKEDIN_DECISIONS


def test_facial_borderline_is_valid_in_judger():
    """Step B widens ``_VALID_FACIAL`` to include ``FACIAL_BORDERLINE``.

    Step A's prior pin (``not in _VALID_FACIAL``) guarded the dark-constant
    invariant. Step B is the slice where that invariant flips: the parser
    and the validator gate both widen, while persistence stays binary
    because the orchestrator translates ``FACIAL_BORDERLINE`` to
    ``FACIAL_YES`` upstream of any persistence call.
    """
    assert "FACIAL_BORDERLINE" in _judger._VALID_FACIAL
