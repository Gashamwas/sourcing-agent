"""LinkedIn side-effect service."""

from __future__ import annotations

import asyncio
import random
from typing import TYPE_CHECKING

from shared.execution import SideEffectOutcome
from shared.human_timing import human_delay_correlated
from shared.storage import log_event

if TYPE_CHECKING:
    from linkedin.orchestrator import Pipeline
    from shared.schemas import CandidateSnippet, SearchString


class LinkedInSideEffectsService:
    """Owns LinkedIn save-click behavior and durable side-effect events."""

    def __init__(self, pipeline: "Pipeline"):
        self.pipeline = pipeline

    async def handle_save_decision(
        self,
        *,
        snippet: "CandidateSnippet",
        runtime_search_string: "SearchString",
        attempt_id: int | None,
    ) -> SideEffectOutcome:
        pipeline = self.pipeline

        if pipeline.test_mode:
            pipeline.stats["saved"] += 1
            if pipeline._runtime_bridge and getattr(pipeline, "_runtime_run_id", None):
                pipeline._runtime_bridge.record_side_effect_result(
                    run_id=pipeline._runtime_run_id,
                    search_string=runtime_search_string,
                    snippet=snippet,
                    attempt_id=attempt_id,
                    effect_type="linkedin_save",
                    status="succeeded",
                    payload={"test_mode": True},
                )
            return SideEffectOutcome(
                effect_type="linkedin_save",
                status="succeeded",
                payload={"test_mode": True},
            )

        profile_url = getattr(snippet, "profile_url", None) or ""
        if profile_url in pipeline._saved_urls:
            print("    Already saved this session (skipping duplicate)")
            saved = True
        else:
            already_saved = await pipeline.browser.is_already_saved()
            if already_saved:
                print("    Already in LinkedIn pipeline (skipping save click)")
                saved = True
            else:
                saved = await pipeline.browser.save_candidate()
                if saved:
                    print("    Saved to LinkedIn pipeline")
                    pipeline._saved_urls.add(profile_url)
                else:
                    print("    [warn] LinkedIn save may have failed")
                linger = max(2.5, min(8.0, human_delay_correlated(4.5, channel="save_linger")))
                chunks_back = random.randint(1, 3)
                px = await pipeline.browser.scroll_for_linger(chunks_back)
                await asyncio.sleep(linger)
                print(f"    [profile-read] SAVE verdict → lingering {linger:.1f}s, scrolled back {chunks_back} chunks")
                await pipeline.browser.scroll_restore(px)

        if saved:
            pipeline.stats["saved"] += 1

        if pipeline._runtime_bridge and getattr(pipeline, "_runtime_run_id", None):
            pipeline._runtime_bridge.record_side_effect_result(
                run_id=pipeline._runtime_run_id,
                search_string=runtime_search_string,
                snippet=snippet,
                attempt_id=attempt_id,
                effect_type="linkedin_save",
                status="succeeded" if saved else "failed",
                payload={"test_mode": False},
            )
        log_event(pipeline.log_path, "candidate_saved", name=snippet.name, linkedin_save=saved)
        return SideEffectOutcome(
            effect_type="linkedin_save",
            status="succeeded" if saved else "failed",
            payload={"test_mode": False},
        )
