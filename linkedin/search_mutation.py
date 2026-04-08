"""Humanized LinkedIn search-mutation executor."""

from __future__ import annotations

import asyncio
import random
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from shared import config
from shared.human_timing import human_delay_correlated
from shared.runtime_state.store import LINKEDIN_STRING_KIND
from shared.storage import log_event

if TYPE_CHECKING:
    from linkedin.orchestrator import Pipeline
    from linkedin.search_intelligence import LinkedInExperimentState, LinkedInSearchVariant
    from shared.schemas import SearchString


@dataclass
class SearchMutationResult:
    applied: bool
    result_count: int = 0
    result_count_text: str = ""
    blocked_reason: str = ""
    top_card_snapshot: dict[str, Any] | None = None


class LinkedInSearchMutationExecutor:
    """Applies keyword-only search mutations using the existing sidebar workflow."""

    def __init__(self, pipeline: "Pipeline"):
        self.pipeline = pipeline

    async def apply_variant(
        self,
        *,
        search_string: "SearchString",
        experiment_state: "LinkedInExperimentState",
        variant: "LinkedInSearchVariant",
    ) -> SearchMutationResult:
        pipeline = self.pipeline
        if not variant.structured_filters.is_empty():
            self._record_event(
                search_string=search_string,
                event_type="linkedin_search_mutation_rejected",
                payload={"reason": "experimental_structured_filters_not_supported", "variant_id": variant.variant_id},
            )
            return SearchMutationResult(applied=False, blocked_reason="experimental_structured_filters_not_supported")
        if experiment_state.consecutive_mutations >= config.SEARCH_EXPERIMENT_MAX_CONSECUTIVE_REWRITES:
            self._record_event(
                search_string=search_string,
                event_type="linkedin_search_mutation_blocked",
                payload={"reason": "consecutive_rewrite_limit", "variant_id": variant.variant_id},
            )
            return SearchMutationResult(applied=False, blocked_reason="consecutive_rewrite_limit")
        if pipeline._search_mutation_budget_used >= config.SEARCH_EXPERIMENT_MUTATION_BUDGET:
            self._record_event(
                search_string=search_string,
                event_type="linkedin_search_mutation_blocked",
                payload={"reason": "session_humanization_budget", "variant_id": variant.variant_id},
            )
            return SearchMutationResult(applied=False, blocked_reason="session_humanization_budget")

        self._record_event(
            search_string=search_string,
            event_type="linkedin_search_mutation_attempt",
            payload={
                "variant_id": variant.variant_id,
                "variant_kind": variant.variant_kind,
                "hypothesis": variant.hypothesis,
                "target_result_min": variant.target_result_min,
                "target_result_max": variant.target_result_max,
            },
        )
        log_event(
            pipeline.log_path,
            "linkedin_search_mutation_attempt",
            string_id=search_string.id,
            variant_id=variant.variant_id,
            variant_kind=variant.variant_kind,
            hypothesis=variant.hypothesis,
        )

        await pipeline.browser.go_back_to_results()
        await asyncio.sleep(human_delay_correlated(0.8, channel="search_mutation"))
        await pipeline.browser.enter_search_string(variant.boolean)
        await asyncio.sleep(human_delay_correlated(random.uniform(0.9, 1.6), channel="search_mutation"))
        result_count_text = await pipeline.browser.get_results_count_text()
        result_count = await pipeline.browser.get_results_count()
        top_card_snapshot = None
        try:
            top_card_snapshot = await pipeline.browser.get_card_snapshot(0)
        except Exception:
            top_card_snapshot = None

        pipeline._search_mutation_budget_used += 1
        experiment_state.activate_variant(variant.variant_id)

        payload = {
            "variant_id": variant.variant_id,
            "variant_kind": variant.variant_kind,
            "result_count": result_count,
            "result_count_text": result_count_text,
            "top_card_snapshot": top_card_snapshot or {},
        }
        self._record_event(
            search_string=search_string,
            event_type="linkedin_search_mutation_applied",
            payload=payload,
        )
        log_event(
            pipeline.log_path,
            "linkedin_search_mutation_applied",
            string_id=search_string.id,
            variant_id=variant.variant_id,
            result_count=result_count,
            result_count_text=result_count_text,
        )
        return SearchMutationResult(
            applied=True,
            result_count=result_count,
            result_count_text=result_count_text,
            top_card_snapshot=top_card_snapshot,
        )

    def _record_event(self, *, search_string: "SearchString", event_type: str, payload: dict[str, Any]) -> None:
        pipeline = self.pipeline
        if not pipeline._runtime_run_id:
            return
        work_unit_id = pipeline._runtime_state.get_work_unit_id(
            pipeline._runtime_run_id,
            kind=LINKEDIN_STRING_KIND,
            source_unit_id=str(search_string.id),
        )
        pipeline._runtime_state.record_event(
            run_id=pipeline._runtime_run_id,
            work_unit_id=work_unit_id,
            event_type=event_type,
            payload=payload,
        )
