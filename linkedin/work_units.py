"""LinkedIn work-unit coordination service."""

from __future__ import annotations

from typing import TYPE_CHECKING

from shared.execution import WorkUnitCheckpoint
from shared.schemas import Progress, SearchString

if TYPE_CHECKING:
    from linkedin.orchestrator import Pipeline
    from shared.schemas import Progress, SearchString


class LinkedInWorkUnitService:
    """Owns LinkedIn progress, search-memory, and restart semantics."""

    def __init__(self, pipeline: "Pipeline"):
        self.pipeline = pipeline

    def load_search_memory(self) -> dict:
        pipeline = self.pipeline
        if not pipeline._runtime_bridge or not pipeline._runtime_bridge.has_runtime_state():
            return {}
        memory = pipeline._runtime_bridge.load_search_memory()
        families = len(memory.get("families", {}))
        print(f"  [memory] Loaded runtime search memory ({families} families)")
        return memory

    def save_search_memory(self) -> dict:
        pipeline = self.pipeline
        if not pipeline._runtime_bridge:
            return pipeline._search_memory
        run_id = self._ensure_runtime_run(progress=pipeline._progress)
        pipeline._runtime_bridge.rebuild_artifacts(run_id)
        return pipeline._runtime_bridge.load_search_memory()

    def update_search_memory_from_block(self, block_strings: list["SearchString"]) -> dict:
        pipeline = self.pipeline
        if not pipeline._runtime_bridge:
            return pipeline._search_memory
        if getattr(pipeline, "_runtime_run_id", None) is None and pipeline._progress is None:
            return pipeline._search_memory
        run_id = self._ensure_runtime_run(progress=pipeline._progress)
        if pipeline._progress:
            pipeline._runtime_bridge.sync_progress(
                run_id,
                pipeline._progress,
                experiment_states=pipeline._experiment_states,
            )
        return pipeline._runtime_bridge.load_search_memory()

    def checkpoint_progress(
        self,
        progress: "Progress" | None,
        *,
        search_string: "SearchString" | None = None,
        page_num: int | None = None,
    ) -> WorkUnitCheckpoint | None:
        pipeline = self.pipeline
        if not progress:
            return None

        if search_string is not None:
            progress.current_string_id = search_string.id
            if page_num is not None:
                progress.current_page = page_num
                search_string.pages_reviewed = max(search_string.pages_reviewed, page_num)

        progress.candidates_saved = pipeline.stats.get("saved", progress.candidates_saved)
        progress.candidates_rejected = pipeline.stats.get("rejected", progress.candidates_rejected)
        run_id = self._ensure_runtime_run(progress=progress)
        pipeline._runtime_bridge.sync_progress(
            run_id,
            progress,
            experiment_states=pipeline._experiment_states,
        )
        pipeline._search_memory = pipeline._runtime_bridge.load_search_memory()
        return WorkUnitCheckpoint(
            status="synced",
            cursor={
                "current_string_id": progress.current_string_id,
                "current_page": progress.current_page,
            },
            metrics={
                "candidates_saved": progress.candidates_saved,
                "candidates_rejected": progress.candidates_rejected,
            },
        )

    def set_pending_block_adaptation(
        self,
        progress: "Progress" | None,
        block_name: str,
        block_strings: list["SearchString"],
        *,
        ready: bool,
    ) -> None:
        if not progress:
            return
        progress.pending_block_name = block_name
        progress.pending_block_string_ids = [search_string.id for search_string in block_strings]
        progress.pending_block_ready = ready

    def clear_pending_block_adaptation(self, progress: "Progress" | None) -> None:
        if not progress:
            return
        progress.pending_block_name = ""
        progress.pending_block_string_ids = []
        progress.pending_block_ready = False

    def load_or_create_progress(self):
        pipeline = self.pipeline
        pipeline._ensure_runtime_state()
        existing_states = dict(pipeline._experiment_states)
        if pipeline._runtime_bridge and (
            pipeline._runtime_bridge.has_runtime_state()
            or pipeline._runtime_bridge.has_legacy_state()
        ):
            pipeline._runtime_run_id, progress = pipeline._runtime_bridge.start_or_resume_run(resume=True)
            loaded_states = pipeline._runtime_bridge.load_experiment_states(
                pipeline._runtime_run_id,
                progress=progress,
            )
            pipeline._experiment_states = {**loaded_states, **existing_states}
            return progress

        strings = []
        for item in pipeline.search_config.get("strings", []):
            strings.append(
                SearchString(
                    id=item["id"],
                    name=item["name"],
                    boolean=item["boolean"],
                )
            )

        progress = Progress(
            brief_name=pipeline.brief_obj.id,
            strings=strings,
        )
        pipeline._runtime_run_id, progress = pipeline._runtime_bridge.start_or_resume_run(
            resume=False,
            initial_progress=progress,
            experiment_states=pipeline._experiment_states,
        )
        loaded_states = pipeline._runtime_bridge.load_experiment_states(
            pipeline._runtime_run_id,
            progress=progress,
        )
        pipeline._experiment_states = {**loaded_states, **existing_states}
        return progress

    def restart_string(self, progress: "Progress", string_id: int) -> None:
        pipeline = self.pipeline
        if not pipeline._runtime_bridge:
            raise RuntimeError("LinkedIn runtime bridge is required for restart semantics")
        run_id = self._ensure_runtime_run(progress=progress, prefer_resume=True)
        pipeline._runtime_bridge.sync_progress(
            run_id,
            progress,
            experiment_states=pipeline._experiment_states,
        )
        pipeline._runtime_bridge.restart_string(
            run_id=run_id,
            progress=progress,
            string_id=string_id,
        )
        pipeline._experiment_states = pipeline._runtime_bridge.load_experiment_states(
            run_id,
            progress=progress,
        )
        pipeline._seen_urls = set()
        pipeline._in_flight_urls = set()
        pipeline._prior_outcomes = {}
        pipeline._load_candidate_history()
        pipeline._search_memory = self.load_search_memory()
        print(f"  String #{string_id} reset to page 1. Ready for re-evaluation.")

    def restart_strings(self, progress: "Progress", string_ids: list[int]) -> None:
        seen_ids: set[int] = set()
        ordered_ids: list[int] = []
        for string_id in string_ids:
            if string_id in seen_ids:
                continue
            seen_ids.add(string_id)
            ordered_ids.append(string_id)
        for string_id in ordered_ids:
            self.restart_string(progress, string_id)

    def _ensure_runtime_run(
        self,
        *,
        progress: "Progress" | None,
        prefer_resume: bool = False,
    ) -> int:
        pipeline = self.pipeline
        if getattr(pipeline, "_runtime_run_id", None):
            return int(pipeline._runtime_run_id)
        if not pipeline._runtime_bridge:
            raise RuntimeError("runtime_state is required for LinkedIn work-unit operations")
        existing_states = dict(pipeline._experiment_states)
        if prefer_resume and (
            pipeline._runtime_bridge.has_runtime_state()
            or pipeline._runtime_bridge.has_legacy_state()
        ):
            pipeline._runtime_run_id, loaded_progress = pipeline._runtime_bridge.start_or_resume_run(resume=True)
            loaded_states = pipeline._runtime_bridge.load_experiment_states(
                pipeline._runtime_run_id,
                progress=loaded_progress,
            )
            pipeline._experiment_states = {**loaded_states, **existing_states}
            if pipeline._progress is None:
                pipeline._progress = loaded_progress
            return int(pipeline._runtime_run_id)
        if progress is None:
            raise RuntimeError("runtime_state run has not been initialized")
        pipeline._runtime_run_id, loaded_progress = pipeline._runtime_bridge.start_or_resume_run(
            resume=False,
            initial_progress=progress,
            experiment_states=pipeline._experiment_states,
        )
        loaded_states = pipeline._runtime_bridge.load_experiment_states(
            pipeline._runtime_run_id,
            progress=loaded_progress,
        )
        pipeline._experiment_states = {**loaded_states, **existing_states}
        if pipeline._progress is None:
            pipeline._progress = loaded_progress
        return int(pipeline._runtime_run_id)
