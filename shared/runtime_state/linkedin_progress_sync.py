"""LinkedIn progress synchronization helpers."""

from __future__ import annotations

from typing import Any, Callable

from linkedin.search_intelligence import LinkedInExperimentState, bootstrap_experiment_state
from shared.schemas import Progress, SearchString

from .store import LINKEDIN_STRING_KIND, RuntimeStateStore


def sync_linkedin_progress(
    *,
    store: RuntimeStateStore,
    run_id: int,
    brief_id: str,
    progress: Progress,
    experiment_states: dict[int, LinkedInExperimentState] | None = None,
    rebuild_artifacts: Callable[[int], None],
    work_unit_metrics: Callable[[SearchString], dict[str, Any]],
) -> None:
    store.update_run_resume_state(run_id, _build_resume_state(progress))

    keep_ids: set[str] = set()
    for index, search_string in enumerate(progress.strings):
        keep_ids.add(str(search_string.id))
        experiment_state = (experiment_states or {}).get(search_string.id)
        if experiment_state is None:
            experiment_state = bootstrap_experiment_state(search_string)
        experiment_state.apply_shadow(search_string)
        experiment_summary = experiment_state.metrics_summary()
        metrics = work_unit_metrics(search_string)
        metrics.update(
            {
                "experiment_summary": experiment_summary,
                "variant_metrics": experiment_summary.get("variants", {}),
            }
        )
        counters = {
            "result_count": search_string.result_count,
            "candidates_discovered": search_string.candidates_count,
            "facial_yes_count": search_string.facial_yes_count,
            "facial_no_count": search_string.facial_no_count,
            "facial_borderline_count": search_string.facial_borderline_count,
            "saves_count": len(search_string.saves),
            "rejected_count": 0,
        }
        store.upsert_work_unit(
            run_id=run_id,
            source="linkedin",
            brief_id=brief_id,
            kind=LINKEDIN_STRING_KIND,
            source_unit_id=str(search_string.id),
            display_name=search_string.name,
            ordering_index=index,
            status=search_string.status,
            payload={
                **search_string.to_dict(),
                "search_intent": experiment_state.intent.to_dict(),
            },
            checkpoint={
                "pages_reviewed": search_string.pages_reviewed,
                "duplicates_count": search_string.duplicates_count,
                "phase": search_string.phase,
                "refinement_stack": list(search_string.refinement_stack),
                "experiment_state": experiment_state.to_dict(),
            },
            metrics=metrics,
            family_key=search_string.family_key,
            novelty_bucket=search_string.novelty_bucket,
            domain_lane=search_string.domain_lane,
            counters=counters,
            notes=search_string.notes or "",
        )
    store.delete_missing_work_units(run_id, kind=LINKEDIN_STRING_KIND, keep_source_unit_ids=keep_ids)
    rebuild_artifacts(run_id)


def _build_resume_state(progress: Progress) -> dict[str, Any]:
    return {
        "brief_name": progress.brief_name,
        "current_string_id": progress.current_string_id,
        "current_page": progress.current_page,
        "pending_block_name": progress.pending_block_name,
        "pending_block_string_ids": list(progress.pending_block_string_ids),
        "pending_block_ready": progress.pending_block_ready,
        "candidates_saved": progress.candidates_saved,
        "candidates_rejected": progress.candidates_rejected,
        "pivot_count": progress.pivot_count,
    }
