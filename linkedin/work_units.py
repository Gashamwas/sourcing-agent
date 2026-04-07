"""LinkedIn work-unit coordination service."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from shared.execution import WorkUnitCheckpoint
from shared.search_memory import update_search_memory
from shared.schemas import Progress, SearchString
from shared.storage import read_json, read_jsonl, write_json

if TYPE_CHECKING:
    from linkedin.orchestrator import Pipeline
    from shared.schemas import Progress, SearchString


class LinkedInWorkUnitService:
    """Owns LinkedIn progress, search-memory, and restart semantics."""

    def __init__(self, pipeline: "Pipeline"):
        self.pipeline = pipeline

    def load_search_memory(self) -> dict:
        pipeline = self.pipeline
        if pipeline._runtime_bridge and pipeline._runtime_bridge.has_runtime_state():
            memory = pipeline._runtime_bridge.load_search_memory()
            families = len(memory.get("families", {}))
            print(f"  [memory] Loaded runtime search memory ({families} families)")
            return memory
        if not pipeline.search_memory_path.exists():
            return {}
        memory = read_json(pipeline.search_memory_path)
        families = len(memory.get("families", {}))
        print(f"  [memory] Loaded search family memory ({families} families)")
        return memory

    def save_search_memory(self) -> dict:
        pipeline = self.pipeline
        if pipeline._runtime_bridge and getattr(pipeline, "_runtime_run_id", None):
            pipeline._runtime_bridge.rebuild_artifacts(pipeline._runtime_run_id)
            return pipeline._runtime_bridge.load_search_memory()
        write_json(pipeline.search_memory_path, pipeline._search_memory)
        return pipeline._search_memory

    def update_search_memory_from_block(self, block_strings: list["SearchString"]) -> dict:
        pipeline = self.pipeline
        if pipeline._runtime_bridge and getattr(pipeline, "_runtime_run_id", None) and pipeline._progress:
            pipeline._runtime_bridge.sync_progress(pipeline._runtime_run_id, pipeline._progress)
            return pipeline._runtime_bridge.load_search_memory()
        updated = update_search_memory(
            pipeline._search_memory,
            pipeline._brief_id,
            block_strings,
        )
        pipeline._search_memory = updated
        return self.save_search_memory()

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
        if pipeline._runtime_bridge and getattr(pipeline, "_runtime_run_id", None):
            pipeline._runtime_bridge.sync_progress(pipeline._runtime_run_id, progress)
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

        progress.save(str(pipeline.progress_path))
        return WorkUnitCheckpoint(
            status="saved",
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
        if pipeline._runtime_bridge and pipeline._runtime_bridge.has_runtime_state():
            pipeline._runtime_run_id, progress = pipeline._runtime_bridge.start_or_resume_run(resume=True)
            return progress
        if pipeline.progress_path.exists():
            existing = Progress.from_file(str(pipeline.progress_path))
            if existing.brief_name == pipeline.brief_obj.id:
                print("  Resuming from existing progress file...")
                return existing
            print(f"  Progress file is for '{existing.brief_name}', not '{pipeline.brief_obj.id}'. Starting fresh.")

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
        )
        return progress

    def restart_string(self, progress: "Progress", string_id: int) -> None:
        pipeline = self.pipeline
        if pipeline._runtime_bridge and getattr(pipeline, "_runtime_run_id", None):
            pipeline._runtime_bridge.restart_string(
                run_id=pipeline._runtime_run_id,
                progress=progress,
                string_id=string_id,
            )
            pipeline._seen_urls = set()
            pipeline._in_flight_urls = set()
            pipeline._prior_outcomes = {}
            pipeline._load_candidate_history()
            pipeline._search_memory = self.load_search_memory()
            print(f"  String #{string_id} reset to page 1. Ready for re-evaluation.")
            return

        target = next((search_string for search_string in progress.strings if search_string.id == string_id), None)
        if not target:
            print(f"  [warn] String #{string_id} not found in progress — ignoring --restart-string")
            return

        print(f"\n  --- Restarting String #{string_id}: {target.name[:60]} ---")
        print(
            f"  Previous state: status={target.status}, pages_reviewed={target.pages_reviewed}, saves={len(target.saves)}"
        )

        target.status = "queued"
        target.pages_reviewed = 1
        target.phase = "scout"
        target.saves = []
        target.notes = ""
        target.refinement_stack = []

        urls_to_remove = set()
        if pipeline.snippets_path.exists():
            all_snippets = read_jsonl(pipeline.snippets_path)
            kept_snippets = []
            for snippet in all_snippets:
                if snippet.get("source_string_id") == string_id:
                    url = snippet.get("profile_url", "")
                    if url:
                        urls_to_remove.add(url)
                else:
                    kept_snippets.append(snippet)
            self._rewrite_jsonl(pipeline.snippets_path, kept_snippets)
            print(f"  Removed {len(urls_to_remove)} snippets for string #{string_id}")

        for path in [pipeline.facial_path, pipeline.final_path, pipeline.profiles_path]:
            if path.exists():
                records = read_jsonl(path)
                kept = [record for record in records if record.get("profile_url", "") not in urls_to_remove]
                removed = len(records) - len(kept)
                if removed > 0:
                    self._rewrite_jsonl(path, kept)
                    print(f"  Removed {removed} entries from {path.name}")

        if pipeline.history_path.exists():
            history_records = read_jsonl(pipeline.history_path)

            def _should_remove(record: dict) -> bool:
                if record.get("source_string_id") == string_id:
                    return True
                if "source_string_id" not in record and record.get("profile_url", "") in urls_to_remove:
                    return True
                return False

            kept_history = [record for record in history_records if not _should_remove(record)]
            removed = len(history_records) - len(kept_history)
            if removed > 0:
                self._rewrite_jsonl(pipeline.history_path, kept_history)
                print(f"  Removed {removed} entries from {pipeline.history_path.name}")

        for url in urls_to_remove:
            pipeline._seen_urls.discard(url)
            pipeline._prior_outcomes.pop(url, None)
            pipeline._in_flight_urls.discard(url)

        if string_id in progress.pending_block_string_ids or progress.pending_block_name == target.block:
            self.clear_pending_block_adaptation(progress)
        if progress.current_string_id == string_id:
            progress.current_string_id = None
            progress.current_page = 0
        self.checkpoint_progress(progress)
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

    @staticmethod
    def _rewrite_jsonl(path, records: list[dict]) -> None:
        with open(path, "w") as handle:
            for record in records:
                handle.write(json.dumps(record) + "\n")
