import json
import shutil
from pathlib import Path

import pytest

from shared.recruiter_brief_resolution import resolve_linkedin_brief_path_for_github_run

REPO_ROOT = Path(__file__).resolve().parents[1]
FDE_DIR = REPO_ROOT / "config/Forward-Deployed-Engineer-NYC"
GITHUB_BRIEF = FDE_DIR / "brief-forward-deployed-engineer-us-github-v1.json"
LINKEDIN_BRIEF = FDE_DIR / "brief-forward-deployed-engineer-us-v1.4.json"


@pytest.mark.skipif(not GITHUB_BRIEF.is_file(), reason="FDE GitHub brief fixture missing")
@pytest.mark.skipif(not LINKEDIN_BRIEF.is_file(), reason="FDE LinkedIn brief fixture missing")
def test_resolve_linkedin_brief_from_run_manifest_sibling(tmp_path):
    gh_copy = tmp_path / GITHUB_BRIEF.name
    li_copy = tmp_path / LINKEDIN_BRIEF.name
    shutil.copy(GITHUB_BRIEF, gh_copy)
    shutil.copy(LINKEDIN_BRIEF, li_copy)

    manifest = {"brief_path": str(gh_copy.resolve())}
    (tmp_path / "run-manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    resolved = resolve_linkedin_brief_path_for_github_run(tmp_path)
    assert resolved.resolve() == li_copy.resolve()


@pytest.mark.skipif(not LINKEDIN_BRIEF.is_file(), reason="FDE LinkedIn brief fixture missing")
def test_resolve_linkedin_brief_explicit_override(tmp_path):
    resolved = resolve_linkedin_brief_path_for_github_run(
        tmp_path,
        explicit_linkedin_brief=LINKEDIN_BRIEF,
    )
    assert resolved.resolve() == LINKEDIN_BRIEF.resolve()
