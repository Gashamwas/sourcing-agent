"""Recruiter-first reconciliation for GitHub-sourced leads (identity + holistic fit + engagement)."""

from __future__ import annotations

import asyncio
import random
from dataclasses import dataclass

from github.reconciliation_input import GitHubReconciliationLead
from linkedin.browser import LinkedInBrowser
from shared.brief_loader import Brief
from shared.extractors import extract_profile_from_innertext
from shared.identity_resolution import (
    build_person_lookup_name,
    canonicalize_location_label,
    choose_best_match,
    classify_recruiter_activity_pressure,
    infer_reachout_status,
    score_linkedin_identity_match,
)
from shared.human_timing import human_delay_correlated
from shared.judger import full_judge
from shared.recruiter_ambiguity_resolution import (
    MultiProfileOutcome,
    consolidate_multi_profile_reviews,
    dedupe_plausible_by_profile_url,
    is_plausible_recruiter_candidate,
    is_single_strong_plausible_for_profile_open,
    single_plausible_is_safely_dominant,
)
from shared.reconciliation_schemas import (
    LinkedInIdentityHints,
    LinkedInMatchResult,
    RecruiterActivitySnapshot,
)
from shared.recruiter_identity_schemas import (
    PlausibleProfileReview,
    RecruiterIdentityCandidate,
    RecruiterIdentityResolution,
)
from shared.recruiter_reconciliation_decision import decide_final_reconciliation_action
from shared.schemas import CandidateProfileSummary, OpusDecision


@dataclass(frozen=True)
class RecruiterResolverConfig:
    max_cards: int = 5
    open_profile_on_likely_match: bool = True
    dry_run_save: bool = False
    max_ambiguity_profiles: int = 3


def _extract_card_identity(snapshot: dict) -> dict:
    innertext = str(snapshot.get("innertext", "") or "")
    lines = [line.strip() for line in innertext.splitlines() if line.strip()]
    name = str(snapshot.get("name", "") or "").strip()
    headline = ""
    location = ""
    current_title = ""
    current_company = ""

    for line in lines:
        lowered = line.lower()
        if (
            not headline
            and line != name
            and "save to pipeline" not in lowered
            and "change stage" not in lowered
        ):
            headline = line
        if not location and " · " in line and " at " not in line:
            location = line.split(" · ", 1)[0].strip()
        if not current_title and " at " in line:
            current_title, current_company = [part.strip() for part in line.split(" at ", 1)]
            break

    return {
        "name": name,
        "headline": headline,
        "current_title": current_title,
        "current_company": current_company,
        "location": location,
        "profile_url": str(snapshot.get("url", "") or "").strip(),
        "already_saved": bool(snapshot.get("already_saved", False)),
        "raw_card_text": innertext,
    }


class RecruiterIdentityResolver:
    """Resolve a GitHub lead inside a prepared Recruiter search (identity + fit + engagement)."""

    def __init__(
        self,
        *,
        browser: LinkedInBrowser,
        project_url: str = "",
        config: RecruiterResolverConfig | None = None,
        linkedin_brief: Brief | None = None,
        linkedin_brief_path: str = "",
    ):
        self.browser = browser
        self.project_url = project_url
        self.config = config or RecruiterResolverConfig()
        self.linkedin_brief = linkedin_brief
        self.linkedin_brief_path = linkedin_brief_path or ""
        self.search_location = ""
        self._prepared = False

    async def prepare_search(self, search_location: str = "") -> None:
        """Open the Recruiter search surface and optionally set a fixed location filter."""
        self.search_location = canonicalize_location_label(search_location)
        if not self.project_url:
            raise ValueError("project_url is required when the resolver is expected to navigate")
        await self.browser.navigate_to_search(self.project_url)
        if self.search_location:
            await self.browser.apply_permanent_filters({"location": self.search_location})
        self._prepared = True

    async def use_existing_search(self, search_location: str = "") -> None:
        """Use the Recruiter search page that the operator has already prepared manually."""
        self.search_location = canonicalize_location_label(search_location)
        await self.browser.go_back_to_results()
        self._prepared = True

    @staticmethod
    def _opus_from_review(review: PlausibleProfileReview) -> OpusDecision | None:
        if not (review.holistic_fit_decision or "").strip():
            return None
        return OpusDecision(
            stage="full",
            decision=review.holistic_fit_decision,
            path=review.holistic_fit_path,
            confidence=review.holistic_fit_confidence,
            rationale=review.holistic_fit_rationale,
            candidate_name=str(review.holistic_profile_summary.get("name", "") or ""),
            profile_url=review.profile_url,
        )

    def _apply_terminal_outcome(
        self,
        resolution: RecruiterIdentityResolution,
        *,
        identity_classification: str,
        identity_high_confidence: bool,
        identity_name_mismatch: bool,
        had_plausible_cards: bool,
        holistic_decision: OpusDecision | None,
        profile_summary: CandidateProfileSummary | None,
        already_saved_card: bool,
        profile_status: RecruiterActivitySnapshot | None,
        novelty_pressure: str,
        reachout_status: str,
        extraction_failed: bool,
    ) -> None:
        resolution.identity_classification = identity_classification
        resolution.had_plausible_cards = had_plausible_cards
        if holistic_decision is not None:
            resolution.holistic_fit_decision = holistic_decision.decision
            resolution.holistic_fit_confidence = float(holistic_decision.confidence or 0.0)
            resolution.holistic_fit_rationale = str(holistic_decision.rationale or "")
            resolution.holistic_fit_path = str(holistic_decision.path or "")
        gate = decide_final_reconciliation_action(
            identity_high_confidence=identity_high_confidence,
            identity_name_mismatch=identity_name_mismatch,
            had_plausible_cards=had_plausible_cards,
            holistic_decision=holistic_decision,
            profile_summary=profile_summary,
            already_saved_card=already_saved_card,
            profile_status=profile_status,
            novelty_pressure=novelty_pressure,
            reachout_status=reachout_status,
            extraction_failed=extraction_failed,
        )
        resolution.final_action = gate.final_action
        resolution.final_subreason = gate.final_subreason

    def _hydrate_resolution_from_review(
        self,
        resolution: RecruiterIdentityResolution,
        candidate: RecruiterIdentityCandidate,
        review: PlausibleProfileReview,
        had_plausible_cards: bool,
        *,
        identity_classification: str,
    ) -> None:
        resolution.selected_candidate_rank = candidate.rank
        resolution.selected_profile_url = candidate.profile_url
        resolution.already_saved = candidate.already_saved
        resolution.profile_status = RecruiterActivitySnapshot.from_dict(review.profile_status)
        resolution.holistic_profile_summary = dict(review.holistic_profile_summary)
        resolution.novelty_pressure = review.novelty_pressure
        resolution.reachout_status = review.reachout_status
        resolution.extraction_failed = review.extraction_failed

        summary: CandidateProfileSummary | None = None
        if review.holistic_profile_summary:
            try:
                summary = CandidateProfileSummary.from_dict(review.holistic_profile_summary)
            except Exception:
                summary = None

        self._apply_terminal_outcome(
            resolution,
            identity_classification=identity_classification,
            identity_high_confidence=True,
            identity_name_mismatch=False,
            had_plausible_cards=had_plausible_cards,
            holistic_decision=self._opus_from_review(review),
            profile_summary=summary,
            already_saved_card=candidate.already_saved,
            profile_status=resolution.profile_status,
            novelty_pressure=review.novelty_pressure,
            reachout_status=review.reachout_status,
            extraction_failed=review.extraction_failed,
        )

    @staticmethod
    def _clear_ambiguous_resolution_selection_fields(resolution: RecruiterIdentityResolution) -> None:
        """No-winner multi-review: top-level row must not imply a single chosen profile or one review's holistic outcome."""
        resolution.selected_candidate_rank = 0
        resolution.selected_profile_url = ""
        resolution.already_saved = False
        resolution.holistic_fit_decision = ""
        resolution.holistic_fit_confidence = 0.0
        resolution.holistic_fit_rationale = ""
        resolution.holistic_fit_path = ""
        resolution.holistic_profile_summary = {}
        resolution.profile_status = None
        resolution.novelty_pressure = ""
        resolution.reachout_status = ""
        resolution.extraction_failed = False

    @staticmethod
    def _format_multi_profile_ambiguity_note(
        reviews: list[PlausibleProfileReview],
        outcome: MultiProfileOutcome,
    ) -> str:
        parts = [
            f"rank{r.rank} {r.profile_url or '(no url)'}: gate {r.gate_final_action or 'unknown'}"
            + (f"/{r.gate_final_subreason}" if (r.gate_final_subreason or "").strip() else "")
            for r in reviews
        ]
        joined = "; ".join(parts)
        reason = (
            f"No unique SAVE winner after opening {len(reviews)} plausible profile(s). "
            f"Consolidation outcome: {outcome.final_action}"
            + (f" ({outcome.final_subreason}). " if outcome.final_subreason else ". ")
            + f"Per-profile gates: {joined}"
        )
        return reason

    async def _read_one_plausible_profile_review(
        self,
        candidate: RecruiterIdentityCandidate,
    ) -> PlausibleProfileReview:
        """Open one plausible card, run full profile read + holistic judge, then dismiss slide-in."""
        await self.browser.focus_card_for_review(candidate.rank - 1)
        await self.browser.open_profile_by_url(candidate.profile_url)

        extraction_failed = False
        holistic_decision: OpusDecision | None = None
        profile_summary: CandidateProfileSummary | None = None
        profile_status: RecruiterActivitySnapshot | None = None
        novelty_pressure = ""
        reachout_status = ""

        try:
            profile_status = RecruiterActivitySnapshot.from_dict(
                await self.browser.get_profile_status_summary()
            )
            if profile_status is not None:
                candidate.recruiter_activity = profile_status
            novelty_pressure = classify_recruiter_activity_pressure(profile_status)
            reachout_status = infer_reachout_status(profile_status)

            await self.browser.simulate_profile_read()
            profile_text = await self.browser.get_profile_innertext()
            if self.linkedin_brief is None:
                raise RuntimeError("linkedin_brief is required for holistic evaluation")
            profile_summary = extract_profile_from_innertext(profile_text, candidate.profile_url)
            holistic_decision = full_judge(profile_summary, self.linkedin_brief)
        except Exception:
            extraction_failed = True
            profile_summary = None
            holistic_decision = None

        gate = decide_final_reconciliation_action(
            identity_high_confidence=True,
            identity_name_mismatch=False,
            had_plausible_cards=True,
            holistic_decision=holistic_decision,
            profile_summary=profile_summary,
            already_saved_card=candidate.already_saved,
            profile_status=profile_status,
            novelty_pressure=novelty_pressure,
            reachout_status=reachout_status,
            extraction_failed=extraction_failed,
        )

        status_dict = profile_status.to_dict() if profile_status else None
        review = PlausibleProfileReview(
            rank=candidate.rank,
            profile_url=candidate.profile_url,
            card_name=candidate.name,
            match_confidence=candidate.match_confidence,
            extraction_failed=extraction_failed,
            holistic_fit_decision=holistic_decision.decision if holistic_decision else "",
            holistic_fit_confidence=float(holistic_decision.confidence or 0.0) if holistic_decision else 0.0,
            holistic_fit_rationale=str(holistic_decision.rationale or "") if holistic_decision else "",
            holistic_fit_path=str(holistic_decision.path or "") if holistic_decision else "",
            holistic_profile_summary=profile_summary.to_dict() if profile_summary else {},
            profile_status=status_dict,
            novelty_pressure=novelty_pressure,
            reachout_status=reachout_status,
            gate_final_action=gate.final_action,
            gate_final_subreason=gate.final_subreason,
        )

        try:
            await self.browser.go_back_to_results()
        except Exception:
            pass
        return review

    async def _reopen_and_save_if_save(
        self,
        candidate: RecruiterIdentityCandidate,
        resolution: RecruiterIdentityResolution,
    ) -> None:
        if resolution.final_action != "SAVE":
            return
        if self.config.dry_run_save:
            resolution.notes.append("Dry-run: skipped Recruiter save click.")
            return
        resolution.recruiter_save_attempted = True
        try:
            await self.browser.focus_card_for_review(candidate.rank - 1)
            await self.browser.open_profile_by_url(candidate.profile_url)
            ok = await self.browser.save_candidate()
            resolution.recruiter_save_succeeded = bool(ok)
            if not resolution.recruiter_save_succeeded:
                resolution.final_action = "MANUAL_REVIEW"
                resolution.final_subreason = "tool_failure"
                resolution.notes.append("Recruiter save did not persist after click.")
        except Exception as exc:
            resolution.recruiter_save_succeeded = False
            resolution.final_action = "MANUAL_REVIEW"
            resolution.final_subreason = "tool_failure"
            resolution.notes.append(f"Recruiter save failed: {exc}")
        try:
            await self.browser.go_back_to_results()
        except Exception:
            pass

    async def _resolve_ambiguity_among_plausible(
        self,
        to_review: list[RecruiterIdentityCandidate],
        resolution: RecruiterIdentityResolution,
        *,
        had_plausible_cards: bool,
    ) -> None:
        resolution.ambiguity_multi_review = True
        self._clear_ambiguous_resolution_selection_fields(resolution)
        queued = [c for c in to_review if (c.profile_url or "").strip()]
        reviews: list[PlausibleProfileReview] = []
        resolution.opened_profile = False
        for candidate in queued:
            review = await self._read_one_plausible_profile_review(candidate)
            reviews.append(review)
            resolution.plausible_profile_reviews.append(review)
            resolution.opened_profile = True

        outcome = consolidate_multi_profile_reviews([r.to_dict() for r in reviews])

        if outcome.winner_index is not None:
            winner = queued[outcome.winner_index]
            winner_review = reviews[outcome.winner_index]
            resolution.rationale = (
                "Multi-profile review: one candidate uniquely passed holistic fit plus engagement gates "
                f"(rank {winner.rank})."
            )
            self._hydrate_resolution_from_review(
                resolution,
                winner,
                winner_review,
                had_plausible_cards,
                identity_classification="ambiguity_multi_review",
            )
            if resolution.final_action == "SAVE":
                await self._reopen_and_save_if_save(winner, resolution)
            return

        resolution.final_action = outcome.final_action
        resolution.final_subreason = outcome.final_subreason
        resolution.identity_classification = "ambiguity_multi_review"
        resolution.had_plausible_cards = bool(had_plausible_cards or reviews)
        self._clear_ambiguous_resolution_selection_fields(resolution)
        resolution.rationale = (
            f"Multi-profile review ({len(reviews)} candidates): outcome {outcome.final_action}"
            + (f" ({outcome.final_subreason})." if outcome.final_subreason else ".")
            + " Holistic and engagement outcomes are recorded per entry in plausible_profile_reviews; "
            "no single profile is selected at the row level."
        )
        resolution.notes.append(self._format_multi_profile_ambiguity_note(reviews, outcome))

    async def _evaluate_confirmed_identity_profile(
        self,
        *,
        selected_candidate: RecruiterIdentityCandidate,
        resolution: RecruiterIdentityResolution,
        had_plausible_cards: bool,
        identity_classification: str = "high_confidence_match",
    ) -> None:
        review = await self._read_one_plausible_profile_review(selected_candidate)
        resolution.opened_profile = True
        resolution.plausible_profile_reviews = [review]
        resolution.ambiguity_multi_review = False
        self._hydrate_resolution_from_review(
            resolution,
            selected_candidate,
            review,
            had_plausible_cards,
            identity_classification=identity_classification,
        )
        await self._reopen_and_save_if_save(selected_candidate, resolution)

    async def resolve_lead(self, lead: GitHubReconciliationLead) -> RecruiterIdentityResolution:
        if not self._prepared:
            await self.prepare_search("")

        hints = lead.linkedin_hints or LinkedInIdentityHints(
            candidate_name=lead.candidate_name,
            github_username=lead.username,
            github_url=lead.github_url,
            company=lead.company,
            location=lead.location,
            title=lead.title,
            source_query=lead.source_query,
            source_channel=lead.source_channel,
        )
        lookup_name = build_person_lookup_name(lead.candidate_name, lead.username)
        if not lookup_name:
            raise ValueError(f"Lead {lead.username} is missing a usable lookup name")

        resolution = RecruiterIdentityResolution(
            github_username=lead.username,
            candidate_name=lead.candidate_name,
            lookup_name=lookup_name,
            github_url=lead.github_url,
            github_company=lead.company,
            github_location=lead.location,
            github_title=lead.title,
            search_location=self.search_location,
            query=lookup_name,
            linkedin_brief_path=self.linkedin_brief_path,
        )
        if self.search_location:
            expected_location = canonicalize_location_label(lead.location)
            if expected_location and expected_location != self.search_location:
                resolution.notes.append(
                    f"Lead location '{expected_location}' does not match fixed search location '{self.search_location}'"
                )

        await self.browser.enter_search_string(lookup_name)
        scored_candidates = await self._read_top_candidates(hints)
        candidates = [candidate for candidate, _match in scored_candidates]
        resolution.top_candidates = candidates

        if not candidates:
            resolution.identity_classification = "no_results"
            resolution.rationale = "No Recruiter result cards surfaced for the name search."
            self._apply_terminal_outcome(
                resolution,
                identity_classification="no_results",
                identity_high_confidence=False,
                identity_name_mismatch=False,
                had_plausible_cards=False,
                holistic_decision=None,
                profile_summary=None,
                already_saved_card=False,
                profile_status=None,
                novelty_pressure="",
                reachout_status="",
                extraction_failed=False,
            )
            return resolution

        ranked_matches = [match for _candidate, match in scored_candidates]
        classification, best_match = choose_best_match(ranked_matches)
        selected_candidate = next(
            (
                candidate
                for candidate, match in scored_candidates
                if match.matched_profile_url == (best_match.matched_profile_url if best_match else "")
            ),
            candidates[0],
        )
        resolution.selected_candidate_rank = selected_candidate.rank
        resolution.selected_profile_url = selected_candidate.profile_url
        resolution.already_saved = selected_candidate.already_saved
        self._apply_activity_summary(
            resolution=resolution,
            activity=selected_candidate.recruiter_activity,
        )

        name_mismatch_selected = any(
            "name mismatch" in reason.lower() for reason in selected_candidate.ambiguity_reasons
        )
        plausible_full = dedupe_plausible_by_profile_url(
            [c for c in candidates if is_plausible_recruiter_candidate(c)]
        )
        cap = max(self.config.max_ambiguity_profiles, 1)
        ambiguity_slice = plausible_full[:cap]
        had_plausible_for_artifact = bool(plausible_full) or classification == "manual_review"

        identity_high = classification == "high_confidence_match" and not name_mismatch_selected

        resolution.rationale = self._build_rationale(
            selected_candidate,
            prefix=(
                "Top Recruiter card looks like the same person as the GitHub lead."
                if identity_high
                else "Recruiter surfaced candidates; identity requires review."
            ),
        )

        if (
            len(plausible_full) >= 2
            and self.config.open_profile_on_likely_match
            and self.linkedin_brief is not None
        ):
            resolution.rationale = (
                "Multiple plausible Recruiter matches for this name; reviewing top candidates in rank order."
            )
            await self._resolve_ambiguity_among_plausible(
                ambiguity_slice,
                resolution,
                had_plausible_cards=had_plausible_for_artifact,
            )
            return resolution

        if (
            len(plausible_full) == 1
            and self.config.open_profile_on_likely_match
            and self.linkedin_brief is not None
            and not identity_high
            and is_single_strong_plausible_for_profile_open(plausible_full[0])
            and single_plausible_is_safely_dominant(
                lone=plausible_full[0],
                all_scored=scored_candidates,
            )
        ):
            only = plausible_full[0]
            resolution.rationale = (
                "Single plausible match with strong identity anchor (tier-1 score+structure or tier-2 "
                "exact name + two of company/title/location); no competing plausible cards and clear "
                "score gap vs next result — opening profile for holistic evaluation."
            )
            resolution.selected_candidate_rank = only.rank
            resolution.selected_profile_url = only.profile_url
            resolution.already_saved = only.already_saved
            self._apply_activity_summary(
                resolution=resolution,
                activity=only.recruiter_activity,
            )
            await self._evaluate_confirmed_identity_profile(
                selected_candidate=only,
                resolution=resolution,
                had_plausible_cards=True,
                identity_classification="single_strong_plausible_profile",
            )
            return resolution

        if (
            identity_high
            and self.config.open_profile_on_likely_match
            and selected_candidate.profile_url
            and self.linkedin_brief is not None
        ):
            await self._evaluate_confirmed_identity_profile(
                selected_candidate=selected_candidate,
                resolution=resolution,
                had_plausible_cards=had_plausible_for_artifact,
            )
            return resolution

        if identity_high and not self.config.open_profile_on_likely_match:
            resolution.identity_classification = "high_confidence_match"
            resolution.notes.append("Holistic fit skipped because profile open is disabled for this run.")
            self._apply_terminal_outcome(
                resolution,
                identity_classification="high_confidence_match",
                identity_high_confidence=True,
                identity_name_mismatch=False,
                had_plausible_cards=had_plausible_for_artifact,
                holistic_decision=None,
                profile_summary=None,
                already_saved_card=selected_candidate.already_saved,
                profile_status=None,
                novelty_pressure=resolution.novelty_pressure,
                reachout_status=resolution.reachout_status,
                extraction_failed=False,
            )
            return resolution

        if identity_high and self.linkedin_brief is None:
            resolution.identity_classification = "high_confidence_match"
            resolution.notes.append("Holistic fit skipped: no LinkedIn brief was configured.")
            self._apply_terminal_outcome(
                resolution,
                identity_classification="high_confidence_match",
                identity_high_confidence=True,
                identity_name_mismatch=False,
                had_plausible_cards=had_plausible_for_artifact,
                holistic_decision=None,
                profile_summary=None,
                already_saved_card=selected_candidate.already_saved,
                profile_status=None,
                novelty_pressure=resolution.novelty_pressure,
                reachout_status=resolution.reachout_status,
                extraction_failed=False,
            )
            return resolution

        if classification == "manual_review" or plausible_full:
            resolution.identity_classification = classification
            self._apply_terminal_outcome(
                resolution,
                identity_classification=classification,
                identity_high_confidence=False,
                identity_name_mismatch=name_mismatch_selected,
                had_plausible_cards=had_plausible_for_artifact,
                holistic_decision=None,
                profile_summary=None,
                already_saved_card=False,
                profile_status=None,
                novelty_pressure="",
                reachout_status="",
                extraction_failed=False,
            )
            return resolution

        resolution.identity_classification = "no_confident_match"
        resolution.rationale = "Recruiter results did not surface a plausible same-person candidate."
        self._apply_terminal_outcome(
            resolution,
            identity_classification="no_confident_match",
            identity_high_confidence=False,
            identity_name_mismatch=name_mismatch_selected,
            had_plausible_cards=False,
            holistic_decision=None,
            profile_summary=None,
            already_saved_card=False,
            profile_status=None,
            novelty_pressure="",
            reachout_status="",
            extraction_failed=False,
        )
        return resolution

    async def _read_top_candidates(
        self,
        hints: LinkedInIdentityHints,
    ) -> list[tuple[RecruiterIdentityCandidate, LinkedInMatchResult]]:
        slot_count = await self.browser.get_card_slot_count()
        if slot_count == 0:
            slot_count = await self.browser.get_card_count()
        candidate_count = min(slot_count, max(self.config.max_cards, 1))
        candidates: list[tuple[RecruiterIdentityCandidate, LinkedInMatchResult]] = []
        for card_index in range(candidate_count):
            await self.browser.focus_card_for_review(card_index)
            await asyncio.sleep(
                human_delay_correlated(
                    random.uniform(0.35, 0.9),
                    channel="recruiter_identity_card_glance",
                )
            )
            snapshot = await self.browser.get_card_snapshot(card_index)
            parsed = _extract_card_identity(snapshot)
            activity = RecruiterActivitySnapshot.from_dict(snapshot.get("recruiter_activity"))
            match = score_linkedin_identity_match(
                hints,
                matched_name=parsed["name"],
                matched_company=parsed["current_company"],
                matched_title=parsed["current_title"] or parsed["headline"],
                matched_location=parsed["location"],
                matched_profile_url=parsed["profile_url"],
                recruiter_activity=activity,
                match_method="recruiter_name_search",
            )
            candidate = RecruiterIdentityCandidate(
                rank=card_index + 1,
                profile_url=parsed["profile_url"],
                name=parsed["name"],
                headline=parsed["headline"],
                current_title=parsed["current_title"],
                current_company=parsed["current_company"],
                location=parsed["location"],
                already_saved=parsed["already_saved"],
                match_confidence=match.match_confidence,
                evidence=list(match.evidence),
                ambiguity_reasons=list(match.ambiguity_reasons),
                recruiter_activity=activity,
                raw_card_text=parsed["raw_card_text"],
            )
            candidates.append((candidate, match))
        return candidates

    @staticmethod
    def _build_rationale(
        candidate: RecruiterIdentityCandidate,
        *,
        prefix: str,
    ) -> str:
        details: list[str] = []
        if candidate.evidence:
            details.append("; ".join(candidate.evidence[:3]))
        if candidate.already_saved:
            details.append("profile is already saved in Recruiter")
        if candidate.ambiguity_reasons:
            details.append("; ".join(candidate.ambiguity_reasons[:2]))
        if not details:
            return prefix
        return f"{prefix} Evidence: {'; '.join(details)}."

    @staticmethod
    def _apply_activity_summary(
        *,
        resolution: RecruiterIdentityResolution,
        activity: RecruiterActivitySnapshot | None,
    ) -> None:
        resolution.novelty_pressure = classify_recruiter_activity_pressure(activity)
        resolution.reachout_status = infer_reachout_status(activity)