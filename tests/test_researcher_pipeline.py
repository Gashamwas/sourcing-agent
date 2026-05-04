"""Researcher Slice 6 — pipeline coverage.

End-to-end test that wires:
- form_strategy (with stub LLM caller)
- ResearcherPipeline (with stub OpenAlex client)
- ResearcherRuntimeStateBridge (writes through real RuntimeStateStore)

Asserts:
- Each query lands as a work_unit (status="done" after the run).
- Saved candidates land in the candidates table with terminal_decision
  in the SAVE family.
- The terminal payload carries `full_decision.rationale` +
  `full_decision.confidence` (the wire contract per Spec Opinion 6).
- The workspace API (`aggregate_workspace`) finds the saved candidates
  source-agnostically.
- Resume re-running the pipeline doesn't crash (idempotency at the
  persistence boundary).
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from cloris.control_plane import aggregate_workspace
from researcher.orchestrator import ResearcherPipeline
from researcher.schemas import ResearcherCandidate, ResearcherPaper
from researcher.sources.openalex import OpenAlexClient
from shared.runtime_state.read_models import (
    candidate_terminal_payload,
    extract_save_reason_and_confidence,
)
from shared.runtime_state.researcher import ResearcherRuntimeStateBridge
from shared.runtime_state.store import (
    RESEARCHER_AUTHOR_QUERY_KIND,
    RuntimeStateStore,
)


# ---------------------------------------------------------------------------
# Stubs
# ---------------------------------------------------------------------------


class _StubOpenAlexClient:
    def __init__(self, responses_by_concept: dict[str, list[dict]]) -> None:
        self.responses = responses_by_concept
        self.calls: list[dict] = []

    def search_authors(self, **kwargs: Any) -> dict:
        self.calls.append(kwargs)
        concepts = kwargs.get("concept_ids") or []
        key = ",".join(concepts) if concepts else ""
        results = self.responses.get(key, [])
        return {"meta": {"next_cursor": ""}, "results": results}


def _author_payload(
    *,
    author_id: str,
    name: str,
    orcid: str = "",
    h_index: int = 12,
    citation_count: int = 200,
    works_count: int = 25,
    institutions: list[dict] | None = None,
    x_concepts: list[dict] | None = None,
) -> dict:
    return {
        "id": f"https://openalex.org/{author_id}",
        "display_name": name,
        "orcid": orcid,
        "summary_stats": {"h_index": h_index},
        "cited_by_count": citation_count,
        "works_count": works_count,
        "counts_by_year": [
            {"year": 2024, "works_count": 4},
            {"year": 2023, "works_count": 4},
            {"year": 2022, "works_count": 3},
        ],
        "last_known_institutions": institutions
        or [{"display_name": "MIT", "country_code": "US"}],
        "x_concepts": x_concepts or [{"id": "https://openalex.org/C1"}],
    }


def _stub_brief() -> SimpleNamespace:
    return SimpleNamespace(
        id="researcher-pipeline-test",
        role_title="Frontier-lab Researcher",
        capability_areas=[
            SimpleNamespace(
                name="Post-training",
                description="RLHF / DPO / SFT.",
            )
        ],
        depth_distinction=SimpleNamespace(
            builder_definition="First-author publications.",
            user_definition="Cites without publishing.",
            edge_case_guidance="Borderline = full eval.",
        ),
        _new_brief={"source_config": {"researcher": {"discipline": "ml_general"}}},
    )


def _strategy_response() -> dict:
    """Two queries; the stub OpenAlex client returns different sets per
    concept so we can verify the pipeline calls the client per query."""

    return {
        "strategy_rationale": "Cover post-training axes",
        "generated_strings": [
            {
                "id": 1,
                "name": "Post-training: NeurIPS",
                "topic_concepts": ["C1"],
                "venue_filter": ["NeurIPS"],
                "min_year": 2023,
                "min_citations": 10,
                "ror_country_filter": ["US"],
            },
            {
                "id": 2,
                "name": "Post-training: ICML",
                "topic_concepts": ["C2"],
                "venue_filter": ["ICML"],
                "min_year": 2023,
                "min_citations": 10,
                "ror_country_filter": ["US"],
            },
        ],
        "architecture": "concept_first",
    }


def _facial_yes(_system: str, _user: str) -> dict:
    return {
        "decision": "FACIAL_YES",
        "rationale": "Recent work in capability area",
        "confidence": 0.9,
    }


def _full_save(_system: str, _user: str) -> dict:
    return {
        "decision": "SAVE",
        "path": "first_author_at_canonical_venue",
        "confidence": 0.92,
        "rationale": (
            "Strong first-author at canonical venues; aligns with "
            "post-training capability area."
        ),
    }


# ---------------------------------------------------------------------------
# End-to-end pipeline run
# ---------------------------------------------------------------------------


def test_pipeline_end_to_end_writes_saves_to_runtime_state(tmp_path: Path) -> None:
    state_dir = tmp_path / "researcher" / "key"
    state_dir.mkdir(parents=True)
    store = RuntimeStateStore(state_dir / "runtime_state.sqlite3")
    brief = _stub_brief()
    bridge = ResearcherRuntimeStateBridge(
        store=store,
        output_dir=state_dir,
        brief_id=brief.id,
        brief_name=brief.role_title,
    )
    run_id = bridge.start_or_resume_run(resume=False)

    client = _StubOpenAlexClient(
        {
            "C1": [
                _author_payload(
                    author_id="A1",
                    name="Alice One",
                    orcid="0000-0001-1111-1111",
                    x_concepts=[{"id": "https://openalex.org/C1"}],
                ),
                _author_payload(
                    author_id="A2",
                    name="Bob Two",
                    x_concepts=[{"id": "https://openalex.org/C1"}],
                ),
            ],
            "C2": [
                _author_payload(
                    author_id="A3",
                    name="Carol Three",
                    orcid="0000-0003-3333-3333",
                    x_concepts=[{"id": "https://openalex.org/C2"}],
                ),
            ],
        }
    )
    pipeline = ResearcherPipeline(
        brief=brief,
        bridge=bridge,
        openalex_client=client,
        facial_llm_caller=_facial_yes,
        full_llm_caller=_full_save,
        strategy_llm_caller=lambda _s, _u: _strategy_response(),
    )
    stats = pipeline.run(run_id=run_id)

    assert stats.queries_total == 2
    assert stats.queries_completed == 2
    assert stats.candidates_discovered == 3
    assert stats.facial_yes == 3
    assert stats.facial_no == 0
    assert stats.saves == 3
    assert stats.rejects == 0

    # Verify work_units land with status="done".
    work_units = store.list_work_units(run_id, kind=RESEARCHER_AUTHOR_QUERY_KIND)
    assert len(work_units) == 2
    assert all(wu["status"] == "done" for wu in work_units)

    # Verify candidates land with terminal_decision SAVE.
    workspace = aggregate_workspace(brief_id=brief.id, state_root=tmp_path)
    assert workspace is not None
    assert workspace.total_saves == 3
    assert "researcher" in workspace.sources

    # Verify the wire contract: save_reason + confidence on each card.
    for card in workspace.candidates:
        assert card.source == "researcher"
        assert card.save_reason
        assert card.save_reason.startswith("Strong first-author")
        assert card.confidence == 0.92


def test_pipeline_writes_full_decision_at_canonical_terminal_payload_path(
    tmp_path: Path,
) -> None:
    """Spec Opinion 6: the full-evaluator output MUST land at
    ``terminal_payload_json["full_decision"]`` with rationale +
    confidence. This is the wire contract every module shares.
    """

    state_dir = tmp_path / "researcher" / "key"
    state_dir.mkdir(parents=True)
    store = RuntimeStateStore(state_dir / "runtime_state.sqlite3")
    brief = _stub_brief()
    bridge = ResearcherRuntimeStateBridge(
        store=store,
        output_dir=state_dir,
        brief_id=brief.id,
        brief_name=brief.role_title,
    )
    run_id = bridge.start_or_resume_run(resume=False)

    client = _StubOpenAlexClient(
        {"C1": [_author_payload(author_id="A1", name="Solo Author")]}
    )
    pipeline = ResearcherPipeline(
        brief=brief,
        bridge=bridge,
        openalex_client=client,
        facial_llm_caller=_facial_yes,
        full_llm_caller=_full_save,
        strategy_llm_caller=lambda _s, _u: {
            "generated_strings": [
                {
                    "id": 1,
                    "name": "q1",
                    "topic_concepts": ["C1"],
                    "ror_country_filter": ["US"],
                }
            ]
        },
    )
    pipeline.run(run_id=run_id)

    # Read the candidate row directly to inspect the terminal payload.
    import sqlite3

    conn = sqlite3.connect(str(store.db_path))
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT terminal_payload_json FROM candidates WHERE source='researcher'"
    ).fetchone()
    conn.close()

    assert row is not None
    payload = candidate_terminal_payload(row["terminal_payload_json"] or "{}")
    assert payload is not None
    assert "full_decision" in payload
    full_decision = payload["full_decision"]
    assert full_decision["decision"] == "SAVE"
    assert full_decision["confidence"] == 0.92
    assert "Strong first-author" in full_decision["rationale"]

    # And the source-agnostic read model returns the same.
    save_reason, confidence = extract_save_reason_and_confidence(payload)
    assert save_reason and "Strong first-author" in save_reason
    assert confidence == 0.92


def test_pipeline_facial_no_does_not_escalate_to_full_eval(tmp_path: Path) -> None:
    """A FACIAL_NO outcome should NOT trigger a full-eval LLM call;
    candidate gets terminal_decision=FACIAL_NO."""

    state_dir = tmp_path / "researcher" / "key"
    state_dir.mkdir(parents=True)
    store = RuntimeStateStore(state_dir / "runtime_state.sqlite3")
    brief = _stub_brief()
    bridge = ResearcherRuntimeStateBridge(
        store=store,
        output_dir=state_dir,
        brief_id=brief.id,
        brief_name=brief.role_title,
    )
    run_id = bridge.start_or_resume_run(resume=False)

    client = _StubOpenAlexClient(
        {"C1": [_author_payload(author_id="A1", name="X", h_index=20)]}
    )

    full_calls: list[tuple[str, str]] = []

    def full_llm_unused(s: str, u: str) -> dict:
        full_calls.append((s, u))
        return _full_save(s, u)

    pipeline = ResearcherPipeline(
        brief=brief,
        bridge=bridge,
        openalex_client=client,
        facial_llm_caller=lambda _s, _u: {
            "decision": "FACIAL_NO",
            "rationale": "Off-thesis.",
            "confidence": 0.95,
        },
        full_llm_caller=full_llm_unused,
        strategy_llm_caller=lambda _s, _u: {
            "generated_strings": [
                {
                    "id": 1,
                    "name": "q1",
                    "topic_concepts": ["C1"],
                    "ror_country_filter": ["US"],
                }
            ]
        },
    )
    stats = pipeline.run(run_id=run_id)

    assert stats.facial_no == 1
    assert stats.facial_yes == 0
    assert stats.saves == 0
    assert full_calls == []  # No full-eval LLM call for FACIAL_NO


def test_pipeline_resume_does_not_duplicate_saves(tmp_path: Path) -> None:
    """Running the pipeline twice against the same brief should not
    duplicate candidate rows (UNIQUE constraint on
    (brief_id, source, identity_key) at store.py:182).
    """

    state_dir = tmp_path / "researcher" / "key"
    state_dir.mkdir(parents=True)
    store = RuntimeStateStore(state_dir / "runtime_state.sqlite3")
    brief = _stub_brief()

    def _build_pipeline(resume: bool) -> tuple[ResearcherPipeline, int]:
        bridge = ResearcherRuntimeStateBridge(
            store=store,
            output_dir=state_dir,
            brief_id=brief.id,
            brief_name=brief.role_title,
        )
        run_id = bridge.start_or_resume_run(resume=resume)
        client = _StubOpenAlexClient(
            {"C1": [_author_payload(author_id="A1", name="Dup Author")]}
        )
        pipeline = ResearcherPipeline(
            brief=brief,
            bridge=bridge,
            openalex_client=client,
            facial_llm_caller=_facial_yes,
            full_llm_caller=_full_save,
            strategy_llm_caller=lambda _s, _u: {
                "generated_strings": [
                    {
                        "id": 1,
                        "name": "q1",
                        "topic_concepts": ["C1"],
                        "ror_country_filter": ["US"],
                    }
                ]
            },
        )
        return pipeline, run_id

    # First run.
    pipeline1, run_id1 = _build_pipeline(resume=False)
    pipeline1.run(run_id=run_id1)

    # Second run (resume=True).
    pipeline2, run_id2 = _build_pipeline(resume=True)
    pipeline2.run(run_id=run_id2)

    # The candidates table should still have exactly one row for A1
    # (the UNIQUE constraint dedups across runs).
    import sqlite3

    conn = sqlite3.connect(str(store.db_path))
    rows = conn.execute(
        "SELECT identity_key FROM candidates WHERE source='researcher'"
    ).fetchall()
    conn.close()
    assert len(rows) == 1
    assert rows[0][0].startswith("openalex:A1")  # ORCID absent → openalex fallback


def test_session_orchestrator_main_returns_2_on_missing_brief(
    tmp_path: Path,
    capsys,
) -> None:
    """Smoke check the CLI entry rejects a missing brief path."""

    from researcher.session_orchestrator import main

    rc = main(
        [
            "--brief",
            str(tmp_path / "no_such_brief.json"),
            "--state-dir",
            str(tmp_path / "state"),
        ]
    )
    assert rc == 2
    err = capsys.readouterr().err
    assert "brief not found" in err
