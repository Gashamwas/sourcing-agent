"""Tests for V2 brief hydration in `shared.brief_loader._load_v2_brief`.

Pins the contract Slice 1 of the executive-search module depends on:

- A V2 brief carrying `confidentiality_class` + `prior_search` +
  `board_signals` + `executive_movement_window_days` +
  `executive_calibration` round-trips through `load_brief()` into the
  structured `_new_brief` dataclass AND mirrors onto the compat
  `Brief` so non-V2 consumers can read the values without spelunking.
- A V2 brief WITHOUT those keys hydrates to the dataclass defaults
  (no behavior change; Slice 1's "no behavior changes" mandate).
"""

from __future__ import annotations

import json
from pathlib import Path

from shared.brief_loader import load_brief
from shared.brief_schema import (
    BoardSignalRules,
    ExecutiveCalibration,
    PriorSearchContext,
)


def _minimal_v2_brief() -> dict:
    return {
        "role_title": "VP Engineering",
        "role_summary": "Owns engineering org for a series-C company.",
        "geography": "United States",
        "linkedin_project": "exec-search-vp-eng",
        "minimum_years_experience": 12,
        "minimum_bar_description": "10+ years engineering leadership.",
        "capability_areas": [
            {
                "name": "Org leadership",
                "description": "Builds and runs 50+ person engineering orgs.",
                "builder_signals": ["VP-level scope", "headcount growth"],
                "user_signals": ["IC-level work primarily"],
            }
        ],
        "depth_distinction": {
            "builder_definition": "Owns engineering strategy + delivery.",
            "user_definition": "Manages individual teams without org-wide scope.",
            "edge_case_guidance": "Borderline = full eval.",
        },
    }


def _write_brief(tmp_path: Path, payload: dict) -> Path:
    brief_path = tmp_path / "brief.json"
    brief_path.write_text(json.dumps(payload))
    return brief_path


def test_load_brief_hydrates_default_exec_search_fields(tmp_path: Path) -> None:
    """A V2 brief without exec_search keys gets the dataclass defaults."""

    brief_path = _write_brief(tmp_path, _minimal_v2_brief())
    brief = load_brief(brief_path)

    assert brief.confidentiality_class == "open"
    assert isinstance(brief.prior_search, PriorSearchContext)
    assert brief.prior_search.ruled_out_urls == []
    assert brief.prior_search.ruled_out_notes == ""
    assert brief.prior_search.earlier_run_ids == []
    assert isinstance(brief.board_signals, BoardSignalRules)
    assert brief.board_signals.relevant_board_companies == []
    assert brief.board_signals.relevant_executive_alumni_companies == []
    assert brief.executive_movement_window_days == 180
    assert brief.executive_calibration is None


def test_load_brief_hydrates_full_exec_search_fields(tmp_path: Path) -> None:
    """A V2 brief carrying every exec_search key hydrates onto compat Brief AND _new_brief."""

    payload = _minimal_v2_brief()
    payload["confidentiality_class"] = "blind"
    payload["prior_search"] = {
        "ruled_out_urls": [
            "https://linkedin.com/in/cand-a",
            "https://linkedin.com/in/cand-b",
        ],
        "ruled_out_notes": "Both passed in 2024 search; client moved on.",
        "earlier_run_ids": ["run_2024_q3"],
    }
    payload["board_signals"] = {
        "relevant_board_companies": ["AcmeCorp", "BetaInc"],
        "relevant_executive_alumni_companies": ["AlphaCo"],
        "adjacency_rationale": "Client board has 2 AcmeCorp alums.",
    }
    payload["board_signals"]
    payload["executive_movement_window_days"] = 90
    payload["executive_calibration"] = {
        "sector": "Healthcare",
        "stage": "Series D",
        "pnl_scale_usd": "$200M ARR",
        "register_notes": "Operator-builder bias.",
    }

    brief_path = _write_brief(tmp_path, payload)
    brief = load_brief(brief_path)

    # Compat Brief mirror.
    assert brief.confidentiality_class == "blind"
    assert brief.prior_search.ruled_out_urls == [
        "https://linkedin.com/in/cand-a",
        "https://linkedin.com/in/cand-b",
    ]
    assert brief.prior_search.ruled_out_notes == (
        "Both passed in 2024 search; client moved on."
    )
    assert brief.prior_search.earlier_run_ids == ["run_2024_q3"]
    assert brief.board_signals.relevant_board_companies == ["AcmeCorp", "BetaInc"]
    assert brief.board_signals.relevant_executive_alumni_companies == ["AlphaCo"]
    assert brief.board_signals.adjacency_rationale == (
        "Client board has 2 AcmeCorp alums."
    )
    assert brief.executive_movement_window_days == 90
    assert isinstance(brief.executive_calibration, ExecutiveCalibration)
    assert brief.executive_calibration.sector == "Healthcare"
    assert brief.executive_calibration.stage == "Series D"
    assert brief.executive_calibration.pnl_scale_usd == "$200M ARR"
    assert brief.executive_calibration.register_notes == "Operator-builder bias."

    # Structured _new_brief carries the same.
    assert brief.has_v2_schema
    new_brief = brief._new_brief
    assert new_brief.confidentiality_class == "blind"
    assert new_brief.prior_search.ruled_out_urls == [
        "https://linkedin.com/in/cand-a",
        "https://linkedin.com/in/cand-b",
    ]
    assert new_brief.board_signals.relevant_board_companies == ["AcmeCorp", "BetaInc"]
    assert new_brief.executive_movement_window_days == 90
    assert isinstance(new_brief.executive_calibration, ExecutiveCalibration)


def test_load_brief_tolerates_malformed_exec_search_blocks(tmp_path: Path) -> None:
    """Defensive coercion: bad shapes degrade to defaults without crashing."""

    payload = _minimal_v2_brief()
    payload["prior_search"] = "not a dict"  # garbage
    payload["board_signals"] = ["also wrong"]
    payload["executive_calibration"] = "should be a dict"
    payload["executive_movement_window_days"] = "not an int"

    brief_path = _write_brief(tmp_path, payload)
    brief = load_brief(brief_path)

    assert brief.prior_search.ruled_out_urls == []
    assert brief.board_signals.relevant_board_companies == []
    assert brief.executive_calibration is None
    assert brief.executive_movement_window_days == 180


def test_load_brief_compat_mirror_isolated_from_new_brief(tmp_path: Path) -> None:
    """`prior_search` mirror on compat Brief must not share mutable state with `_new_brief`.

    Mirrors the `_detach` pattern used for vertical-agnostic calibration
    fields. Mutating the compat Brief's lists must not affect the
    structured `_new_brief`.
    """

    payload = _minimal_v2_brief()
    payload["prior_search"] = {"ruled_out_urls": ["a", "b"]}

    brief_path = _write_brief(tmp_path, payload)
    brief = load_brief(brief_path)

    brief.prior_search.ruled_out_urls.append("c")

    assert brief._new_brief.prior_search.ruled_out_urls == ["a", "b"]


# ---------------------------------------------------------------------------
# OSS Maintainers module Slice 2 — V2 brief hydration
# ---------------------------------------------------------------------------


def test_load_brief_hydrates_default_oss_maintainer_fields(tmp_path: Path) -> None:
    """A V2 brief without OSS Maintainer keys gets the dataclass defaults.

    Behavior-preserving for classic github briefs per spec §11:
    `target_projects` empty ⇒ classifier and full-eval block are
    no-ops in Slice 6.
    """

    brief_path = _write_brief(tmp_path, _minimal_v2_brief())
    brief = load_brief(brief_path)

    assert brief.target_projects == []
    assert brief.target_stacks == []
    assert brief.maintainership_level == "contributor"
    assert brief._new_brief.target_projects == []
    assert brief._new_brief.target_stacks == []
    assert brief._new_brief.maintainership_level == "contributor"


def test_load_brief_hydrates_full_oss_maintainer_fields(tmp_path: Path) -> None:
    """A V2 brief carrying every OSS Maintainer key hydrates onto compat AND _new_brief."""

    payload = _minimal_v2_brief()
    payload["target_projects"] = ["kubernetes/kubernetes", "etcd-io/etcd"]
    payload["target_stacks"] = ["go", "container-orchestration"]
    payload["maintainership_level"] = "maintainer"

    brief_path = _write_brief(tmp_path, payload)
    brief = load_brief(brief_path)

    assert brief.target_projects == ["kubernetes/kubernetes", "etcd-io/etcd"]
    assert brief.target_stacks == ["go", "container-orchestration"]
    assert brief.maintainership_level == "maintainer"

    assert brief._new_brief.target_projects == [
        "kubernetes/kubernetes",
        "etcd-io/etcd",
    ]
    assert brief._new_brief.target_stacks == ["go", "container-orchestration"]
    assert brief._new_brief.maintainership_level == "maintainer"


def test_load_brief_oss_maintainer_compat_mirror_isolated_from_new_brief(
    tmp_path: Path,
) -> None:
    """`target_projects` mirror on compat Brief must not share mutable state.

    Mirrors the `_detach` pattern used for vertical-agnostic
    calibration fields and exec_search blocks. Mutating the compat
    Brief's lists must not affect the structured `_new_brief`.
    """

    payload = _minimal_v2_brief()
    payload["target_projects"] = ["kubernetes/kubernetes", "rust-lang/rust"]

    brief_path = _write_brief(tmp_path, payload)
    brief = load_brief(brief_path)

    brief.target_projects.append("etcd-io/etcd")

    assert brief._new_brief.target_projects == [
        "kubernetes/kubernetes",
        "rust-lang/rust",
    ]


def test_load_brief_filters_malformed_oss_maintainer_entries(
    tmp_path: Path,
) -> None:
    """Defensive coercion: non-string list entries drop, garbage levels degrade."""

    payload = _minimal_v2_brief()
    # Intentionally seed garbage; validate_v2_brief WOULD reject this,
    # but the loader's defensive coercion should still produce a sane
    # Brief if it ever bypasses validation (e.g., legacy raw load).
    payload["target_projects"] = ["kubernetes/kubernetes", None, ""]
    payload["target_stacks"] = ["go"]
    payload["maintainership_level"] = ""

    brief_path = _write_brief(tmp_path, payload)
    brief = load_brief(brief_path)

    assert brief.target_projects == ["kubernetes/kubernetes"]
    assert brief.target_stacks == ["go"]
    # Empty string degrades to default per loader coercion.
    assert brief.maintainership_level == "contributor"
