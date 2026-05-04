"""Researcher pipeline orchestrator — Slice 6.

Composes Slices 2–5 into one runnable pipeline:

  brief → form_strategy → for each query:
      acquire → disambiguate → for each kept candidate:
          build snippet → facial judge
          if FACIAL_YES / FACIAL_BORDERLINE: full judge → record terminal
          else: record FACIAL_NO terminal

Per Researcher Module Spec Slice 6:

- Mirrors :class:`linkedin.orchestrator.LinkedInPipeline._process_string`
  shape: the outer loop iterates queries (the substrate's work_units),
  the inner loop is per-candidate.
- Resume semantics: re-read ``work_units WHERE status IN ('queued',
  'in_progress')``; pagination cursor lives in ``checkpoint_json``.
- Saves stay in the ``candidates`` table with SAVE-class
  ``terminal_decision`` per Spec Opinion 4 (workspace-only saves).

The orchestrator is dependency-injectable so tests don't require real
OpenAlex / Opus calls — pass stub `OpenAlexClient` and `llm_caller`s.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from researcher.acquisition import execute_query
from researcher.discipline_defaults import resolve_floors
from researcher.identity import disambiguate
from researcher.schemas import (
    ResearcherCandidate,
    ResearcherSnippet,
)
from researcher.sources.openalex import OpenAlexClient
from researcher.strategy import form_strategy
from shared.brief_loader import Brief, load_brief
from shared.brief_v2_schema import source_config_for
from shared.execution import CandidateExecutionEngine  # noqa: F401  (used via bridge)
from shared.judger import (
    researcher_facial_judge_batch,
    researcher_full_judge,
)
from shared.runtime_state.researcher import ResearcherRuntimeStateBridge
from shared.runtime_state.store import RuntimeStateStore
from shared.schemas import OpusDecision


logger = logging.getLogger(__name__)


@dataclass
class PipelineRunStats:
    """Per-run aggregate counters."""

    queries_total: int = 0
    queries_completed: int = 0
    candidates_discovered: int = 0
    facial_yes: int = 0
    facial_no: int = 0
    facial_borderline: int = 0
    saves: int = 0
    rejects: int = 0
    per_query: list[dict] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "queries_total": self.queries_total,
            "queries_completed": self.queries_completed,
            "candidates_discovered": self.candidates_discovered,
            "facial_yes": self.facial_yes,
            "facial_no": self.facial_no,
            "facial_borderline": self.facial_borderline,
            "saves": self.saves,
            "rejects": self.rejects,
            "per_query": self.per_query,
        }


@dataclass
class ResearcherPipeline:
    """Synchronous pipeline that drives a researcher run end-to-end.

    Construction is dependency-injectable so tests can swap in stubs:
    - ``openalex_client``: any object with ``search_authors(**kwargs)``
    - ``facial_llm_caller`` / ``full_llm_caller``: callables passed
      through to the judges
    """

    brief: Brief
    bridge: ResearcherRuntimeStateBridge
    openalex_client: OpenAlexClient
    facial_llm_caller: Callable[[str, str], Any] | None = None
    full_llm_caller: Callable[[str, str], Any] | None = None
    strategy_llm_caller: Callable[[str, str], dict] | None = None
    max_authors_per_query: int = 200

    def run(self, *, run_id: int, prior_data: dict | None = None) -> PipelineRunStats:
        """Execute the full pipeline; return aggregate stats.

        ``run_id`` is the run row created by
        :meth:`ResearcherRuntimeStateBridge.start_or_resume_run`.
        """

        source_config = source_config_for(self._brief_raw(), "researcher")
        floors = resolve_floors(source_config)

        plan = form_strategy(
            self.brief,
            prior_data=prior_data,
            llm_caller=self.strategy_llm_caller,
        )

        queries = list(plan.generated_strings)
        stats = PipelineRunStats(queries_total=len(queries))

        for ordering_index, query in enumerate(queries, start=1):
            self.bridge.upsert_query_work_unit(
                run_id=run_id,
                query=query,
                status="in_progress",
                ordering_index=ordering_index,
            )
            per_query_stats = self._run_one_query(
                run_id=run_id,
                query=query,
                source_config=source_config,
                floors=floors,
            )
            stats.candidates_discovered += per_query_stats["candidates_discovered"]
            stats.facial_yes += per_query_stats["facial_yes_count"]
            stats.facial_no += per_query_stats["facial_no_count"]
            stats.facial_borderline += per_query_stats["facial_borderline_count"]
            stats.saves += per_query_stats["saves_count"]
            stats.rejects += per_query_stats["rejected_count"]
            stats.per_query.append(per_query_stats)
            self.bridge.upsert_query_work_unit(
                run_id=run_id,
                query=query,
                status="done",
                ordering_index=ordering_index,
                cursor="exhausted",
                **per_query_stats,
            )
            stats.queries_completed += 1

        return stats

    # -----------------------------------------------------------------
    # Per-query execution
    # -----------------------------------------------------------------

    def _run_one_query(
        self,
        *,
        run_id: int,
        query: dict,
        source_config: dict,
        floors: dict[str, int],
    ) -> dict:
        """Execute one researcher query end-to-end; return per-query stats."""

        result = execute_query(
            query=query,
            client=self.openalex_client,
            papers_in_window_months=floors["papers_in_window_months"],
            max_authors=self.max_authors_per_query,
            now=datetime.now(timezone.utc),
        )

        # Disambiguate against the brief's hard constraints.
        disambiguation = disambiguate(
            result.candidates,
            allowed_country_codes=list(query.get("ror_country_filter") or []),
            required_concept_ids=list(query.get("topic_concepts") or []),
            papers_in_window_floor=floors["papers_in_window_floor"],
        )

        kept_results = [r for r in disambiguation.results if r.kept]

        # Discover all kept candidates (so the workspace surfaces them
        # even if facial cuts them — useful for triage telemetry).
        for kept in kept_results:
            self.bridge.record_candidate_discovery(
                run_id=run_id,
                query_id=int(query.get("id") or 0),
                candidate=kept.candidate,
            )

        # Facial triage in batch.
        snippets = [_snippet_from_candidate(r.candidate, query) for r in kept_results]
        facial_decisions = researcher_facial_judge_batch(
            snippets,
            brief=self.brief,
            source_config=source_config,
            llm_caller=self.facial_llm_caller,
        )

        facial_yes = facial_no = facial_borderline = 0
        saves = rejects = 0

        for kept_result, snippet, decision in zip(kept_results, snippets, facial_decisions):
            self.bridge.record_facial_decision(
                run_id=run_id,
                snippet=snippet,
                decision=decision,
            )
            if decision.decision == "FACIAL_YES":
                facial_yes += 1
            elif decision.decision == "FACIAL_BORDERLINE":
                facial_borderline += 1
            else:
                facial_no += 1
                continue

            # Escalate to full eval.
            full_decision = researcher_full_judge(
                kept_result.candidate,
                brief=self.brief,
                llm_caller=self.full_llm_caller,
            )
            self.bridge.record_full_decision(
                run_id=run_id,
                candidate=kept_result.candidate,
                decision=full_decision,
            )
            if full_decision.decision in {
                "SAVE",
                "INFERENTIAL_SAVE",
                "TRANSFERABLE_SAVE",
                "SIGNAL_SAVE",
            }:
                saves += 1
            elif full_decision.decision == "REJECT":
                rejects += 1

        return {
            "candidates_discovered": len(kept_results),
            "facial_yes_count": facial_yes,
            "facial_no_count": facial_no,
            "facial_borderline_count": facial_borderline,
            "saves_count": saves,
            "rejected_count": rejects,
        }

    # -----------------------------------------------------------------
    # Helpers
    # -----------------------------------------------------------------

    def _brief_raw(self) -> dict:
        raw = getattr(self.brief, "_new_brief", None)
        if isinstance(raw, dict):
            return raw
        if hasattr(raw, "raw_dict"):
            try:
                candidate = raw.raw_dict()
                if isinstance(candidate, dict):
                    return candidate
            except Exception:  # noqa: BLE001 - defensive
                pass
        return {}


def _snippet_from_candidate(
    candidate: ResearcherCandidate,
    query: dict,
) -> ResearcherSnippet:
    """Build the facial-input view from a hydrated candidate."""

    return ResearcherSnippet(
        name=candidate.name,
        current_affiliation=candidate.affiliations[0] if candidate.affiliations else "",
        h_index=candidate.h_index,
        citation_count=candidate.citation_count,
        papers_in_window=candidate.papers_in_window,
        top_paper_titles=[p.title for p in candidate.top_papers[:5]],
        arxiv_categories=[],  # Slice 2's arXiv client supplies these in Slice 8 wiring.
        profile_url=candidate.profile_url,
        source_query_id=int(query.get("id") or 0),
        source_query_name=str(query.get("name") or ""),
    )


# ---------------------------------------------------------------------------
# Convenience constructor
# ---------------------------------------------------------------------------


def build_pipeline(
    *,
    brief_path: str | Path,
    state_dir: str | Path,
    openalex_polite_pool_email: str = "",
    facial_llm_caller: Callable[[str, str], Any] | None = None,
    full_llm_caller: Callable[[str, str], Any] | None = None,
    strategy_llm_caller: Callable[[str, str], dict] | None = None,
) -> tuple[ResearcherPipeline, int]:
    """Convenience constructor used by the session orchestrator.

    Loads the brief, opens the runtime state store, builds the bridge,
    and returns ``(pipeline, run_id)`` so the caller just calls
    :meth:`ResearcherPipeline.run`.
    """

    brief = load_brief(str(brief_path))
    state_dir_path = Path(state_dir)
    state_dir_path.mkdir(parents=True, exist_ok=True)
    db_path = state_dir_path / "runtime_state.sqlite3"
    store = RuntimeStateStore(db_path)
    bridge = ResearcherRuntimeStateBridge(
        store=store,
        output_dir=state_dir_path,
        brief_id=brief.id or brief.role_title or Path(brief_path).stem,
        brief_name=brief.role_title or brief.id,
        brief_path=str(brief_path),
    )
    run_id = bridge.start_or_resume_run(resume=False)

    client = OpenAlexClient(polite_pool_email=openalex_polite_pool_email)
    pipeline = ResearcherPipeline(
        brief=brief,
        bridge=bridge,
        openalex_client=client,
        facial_llm_caller=facial_llm_caller,
        full_llm_caller=full_llm_caller,
        strategy_llm_caller=strategy_llm_caller,
    )
    return pipeline, run_id
