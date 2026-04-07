"""LinkedIn acquisition service."""

from __future__ import annotations

import asyncio
import random
from typing import TYPE_CHECKING

from shared.execution import AcquisitionResult
from shared.extractors import extract_profile_from_dom, extract_snippet_from_card_innertext
from shared.governor import GovernorLimitReached
from shared.human_timing import human_delay_correlated
from shared.storage import log_event

if TYPE_CHECKING:
    from linkedin.orchestrator import Pipeline
    from shared.schemas import CandidateSnippet, SearchString


_BROWSER_DISCONNECT_PATTERNS = (
    "target crashed",
    "target closed",
    "connection closed",
    "session closed",
    "broken pipe",
    "browser has been closed",
    "page closed",
    "context closed",
    "page.createisolatedworld",
    "page.addscripttoevaluateonnewdocument",
    "cannot get world",
)


def _is_browser_disconnect_error(error: BaseException | str) -> bool:
    text = str(error).lower()
    return any(pattern in text for pattern in _BROWSER_DISCONNECT_PATTERNS)


class LinkedInAcquisitionService:
    """Owns LinkedIn candidate snippet and profile acquisition behavior."""

    def __init__(self, pipeline: "Pipeline"):
        self.pipeline = pipeline

    async def extract_card_snippet(
        self,
        search_string: "SearchString",
        page_num: int,
        card_index: int,
    ) -> AcquisitionResult | None:
        pipeline = self.pipeline
        try:
            await pipeline.browser.focus_card_for_review(card_index)
            await asyncio.sleep(
                human_delay_correlated(random.uniform(0.7, 1.8), channel="card_glance")
            )
            snapshot = await pipeline.browser.get_card_snapshot(card_index)
        except Exception as exc:
            print(f"    [warn] Card {card_index + 1} could not be extracted: {exc}")
            log_event(
                pipeline.log_path,
                "card_extract_error",
                string_id=search_string.id,
                page=page_num,
                card_index=card_index + 1,
                error=str(exc),
            )
            try:
                await pipeline.browser.go_back_to_results()
            except Exception:
                pass
            return None

        innertext = (snapshot.get("innertext") or "").strip()
        if not innertext and not snapshot.get("name"):
            print(f"    [warn] Card {card_index + 1} rendered without readable text")
            return None

        snippet = extract_snippet_from_card_innertext(
            innertext,
            string_id=search_string.id,
            string_name=search_string.name,
            page=page_num,
            result_rank=card_index + 1,
            dom_name=(snapshot.get("name") or "").strip(),
            dom_url=(snapshot.get("url") or "").strip(),
        )
        if snippet is None:
            print(f"    [warn] Could not extract snippet from card {card_index + 1}")
            return None

        if snapshot.get("name"):
            snippet.name = snapshot["name"]
        if snapshot.get("url"):
            snippet.profile_url = snapshot["url"]
        snippet.card_index = card_index
        snippet.already_saved = bool(snapshot.get("already_saved", False))
        return AcquisitionResult(snippet=snippet, metadata={"snapshot": snapshot})

    async def extract_profile_summary(self, snippet: "CandidateSnippet") -> AcquisitionResult:
        pipeline = self.pipeline
        await pipeline._ensure_browser_healthy()

        print("    Opening profile for full evaluation...")
        scan_time = random.uniform(0.8, 2.2)
        await asyncio.sleep(human_delay_correlated(scan_time, channel="snippet_scan"))

        if snippet.card_index >= 0:
            await pipeline.browser.ensure_card_rendered(snippet.card_index)

        opened = False
        if snippet.profile_url:
            try:
                self._check_governor_before_open()
                await pipeline.browser.open_profile_by_url(snippet.profile_url)
                self._record_governor_open()
                opened = True
            except GovernorLimitReached:
                raise
            except Exception as url_err:
                if _is_browser_disconnect_error(url_err):
                    raise
                print(f"    [warn] URL-based open failed ({url_err}), falling back to name match...")
        if not opened:
            self._check_governor_before_open()
            await pipeline.browser.open_profile(snippet.name)
            self._record_governor_open()

        await pipeline.browser.simulate_profile_read()
        profile_text = await pipeline.browser.get_profile_innertext()
        print(f"    Profile text size: {len(profile_text) / 1024:.0f} KB")
        summary = extract_profile_from_dom(profile_text, snippet.profile_url)
        return AcquisitionResult(
            profile_summary=summary,
            metadata={"profile_text_size": len(profile_text)},
        )

    def _check_governor_before_open(self) -> None:
        governor = getattr(self.pipeline, "_governor", None)
        if governor:
            governor.check_profile_open_or_raise()

    def _record_governor_open(self) -> None:
        governor = getattr(self.pipeline, "_governor", None)
        if governor:
            governor.record_profile_open()
