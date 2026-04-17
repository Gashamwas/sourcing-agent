"""Regression tests pinning reconciliation onto the canonical path.

The canonical GitHub→LinkedIn reconciliation contract is defined in
``GitHub-LinkedIn-Reconciliation-Source-of-Truth.md``. There is exactly
one permitted implementation (``RecruiterIdentityResolver`` driven by
``tools/run_recruiter_identity_resolver.py``).

This file used to exercise the legacy ``LinkedInReconciliationService``
action taxonomy (``promote`` / ``drop_already_worked`` / etc.). That
service violates the Source-of-Truth rules, so it is now deprecated.
These tests pin the deprecation and enforce the redirection to the
canonical path, so that no future change silently revives the legacy
contract.
"""

from __future__ import annotations

import importlib
import subprocess
import sys
import warnings
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from linkedin.reconciliation import (
    LEGACY_RECONCILIATION_DEPRECATION_MESSAGE,
    LinkedInReconciliationService,
)


REPO_ROOT = Path(__file__).resolve().parent.parent


def test_linkedin_reconciliation_service_construction_is_deprecated():
    browser = AsyncMock()
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        LinkedInReconciliationService(
            browser=browser,
            project_url="https://www.linkedin.com/talent/search",
        )

    deprecations = [w for w in caught if issubclass(w.category, DeprecationWarning)]
    assert deprecations, "constructing LinkedInReconciliationService must emit DeprecationWarning"
    assert any(
        "RecruiterIdentityResolver" in str(w.message)
        and "run_recruiter_identity_resolver" in str(w.message)
        for w in deprecations
    ), "deprecation message must redirect callers to the canonical implementation"


def test_deprecation_message_names_canonical_entry_points():
    assert "RecruiterIdentityResolver" in LEGACY_RECONCILIATION_DEPRECATION_MESSAGE
    assert "run_recruiter_identity_resolver" in LEGACY_RECONCILIATION_DEPRECATION_MESSAGE


def test_retired_cli_exits_non_zero_and_redirects(tmp_path, monkeypatch):
    script = REPO_ROOT / "tools" / "reconcile_github_to_linkedin.py"
    assert script.is_file(), "retired CLI file must remain on disk as a redirection shim"

    env = {
        **{k: v for k, v in __import__("os").environ.items()},
        "PYTHONPATH": str(REPO_ROOT),
    }
    result = subprocess.run(
        [sys.executable, str(script), "--help"],
        capture_output=True,
        text=True,
        cwd=str(tmp_path),
        env=env,
        check=False,
    )

    assert result.returncode != 0, (
        "retired CLI must exit non-zero so automation cannot silently consume its output"
    )
    combined = (result.stdout or "") + (result.stderr or "")
    assert "retired" in combined.lower()
    assert "run_recruiter_identity_resolver" in combined


def test_canonical_cli_entry_point_is_importable():
    module = importlib.import_module("tools.run_recruiter_identity_resolver")
    assert hasattr(module, "main"), (
        "canonical CLI must expose a main() function; Source-of-Truth doc names it as the runtime entry point"
    )


def test_canonical_resolver_module_is_importable():
    module = importlib.import_module("linkedin.recruiter_identity_resolver")
    assert hasattr(module, "RecruiterIdentityResolver")
    assert hasattr(module, "RecruiterResolverConfig")


def test_canonical_decision_gate_exposes_source_of_truth_actions():
    """Pin that the canonical gate still emits the SoT action taxonomy."""
    module = importlib.import_module("shared.recruiter_reconciliation_decision")
    source = Path(module.__file__).read_text(encoding="utf-8")
    for action in ("SAVE", "MANUAL_REVIEW", "REJECT"):
        assert action in source, (
            f"canonical decision module must reference the {action!r} action from the Source-of-Truth doc"
        )


@pytest.mark.filterwarnings("ignore::DeprecationWarning")
def test_legacy_service_still_loadable_for_migration_grace_period():
    """The class must remain importable so orphaned callers hit DeprecationWarning, not ImportError."""
    browser = AsyncMock()
    service = LinkedInReconciliationService(
        browser=browser,
        project_url="https://www.linkedin.com/talent/search",
    )
    assert service.project_url == "https://www.linkedin.com/talent/search"
