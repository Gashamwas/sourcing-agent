"""GitHub→LinkedIn reconciliation workflow."""

from __future__ import annotations

from dataclasses import dataclass

from github.reconciliation_input import GitHubReconciliationLead
from linkedin.browser import LinkedInBrowser
from shared.identity_resolution import (
    build_candidate_lookup_queries,
    choose_best_match,
    classify_recruiter_activity_pressure,
    infer_reachout_status,
    normalize_company_name,
    resolve_direct_linkedin_hint,
    score_linkedin_identity_match,
)
from shared.reconciliation_schemas import (
    LinkedInIdentityHints,
    LinkedInMatchResult,
    ReconciliationAssessment,
    ReconciliationDecision,
    RecruiterActivitySnapshot,
)


@dataclass
class _LookupCandidate:
    query: str
    match: LinkedInMatchResult


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
        if not headline and line != name and "save to pipeline" not in lowered and "change stage" not in lowered:
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
    }


class LinkedInReconciliationService:
    """Resolve GitHub leads into LinkedIn Recruiter identities and novelty status."""

    def __init__(
        self,
        *,
        browser: LinkedInBrowser,
        project_url: str,
        max_queries: int = 5,
        max_results_per_query: int = 5,
    ):
        self.browser = browser
        self.project_url = project_url
        self.max_queries = max_queries
        self.max_results_per_query = max_results_per_query

    @staticmethod
    def _coerce_result_count(value: object) -> int:
        if isinstance(value, bool):
            return 0
        if isinstance(value, int):
            return max(value, 0)
        try:
            return max(int(str(value).strip()), 0)
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _match_has_name_mismatch(match: LinkedInMatchResult | None) -> bool:
        if match is None:
            return False
        return any("name mismatch" in item.lower() for item in match.ambiguity_reasons)

    @classmethod
    def _search_confirms_direct_hint(
        cls,
        search_classification: str,
        search_match: LinkedInMatchResult | None,
    ) -> bool:
        return (
            search_classification == "high_confidence_match"
            and search_match is not None
            and not cls._match_has_name_mismatch(search_match)
        )

    @staticmethod
    def _merge_direct_hint_with_search(
        direct_hint_match: LinkedInMatchResult,
        search_match: LinkedInMatchResult | None,
        *,
        search_confirmed: bool,
    ) -> LinkedInMatchResult:
        if search_match is None:
            return direct_hint_match
        evidence = list(direct_hint_match.evidence)
        ambiguity_reasons = list(direct_hint_match.ambiguity_reasons)
        evidence.extend(item for item in search_match.evidence if item not in evidence)
        ambiguity_reasons.extend(
            item for item in search_match.ambiguity_reasons if item not in ambiguity_reasons
        )
        if not search_confirmed:
            ambiguity_reasons.append("Recruiter search did not confidently confirm the direct LinkedIn hint")
        elif search_match.matched_profile_url:
            evidence.append("Recruiter search surfaced a likely matching Recruiter profile")
        canonical_url = direct_hint_match.matched_profile_url or search_match.matched_profile_url
        return LinkedInMatchResult(
            matched_profile_url=canonical_url,
            matched_name=search_match.matched_name if search_confirmed else direct_hint_match.matched_name,
            matched_company=search_match.matched_company if search_confirmed else direct_hint_match.matched_company,
            matched_title=search_match.matched_title if search_confirmed else direct_hint_match.matched_title,
            matched_location=search_match.matched_location if search_confirmed else direct_hint_match.matched_location,
            match_confidence=max(direct_hint_match.match_confidence, search_match.match_confidence),
            match_method="direct_linkedin_hint+recruiter_search",
            evidence=evidence,
            ambiguity_reasons=ambiguity_reasons,
            recruiter_activity=search_match.recruiter_activity if search_confirmed else direct_hint_match.recruiter_activity,
            novelty_pressure=search_match.novelty_pressure if search_confirmed else direct_hint_match.novelty_pressure,
        )

    async def lookup_candidate_by_identity(
        self,
        hints: LinkedInIdentityHints,
    ) -> list[_LookupCandidate]:
        queries = build_candidate_lookup_queries(hints)[: self.max_queries]
        results_by_url: dict[str, _LookupCandidate] = {}
        results_without_url: list[_LookupCandidate] = []

        await self.browser.navigate_to_search(self.project_url)
        for query in queries:
            await self.browser.enter_search_string(query)
            slot_count = self._coerce_result_count(await self.browser.get_card_slot_count())
            if slot_count == 0:
                slot_count = self._coerce_result_count(await self.browser.get_card_count())
            candidate_count = min(slot_count, self.max_results_per_query)
            for card_index in range(candidate_count):
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
                    match_method="recruiter_search",
                )
                candidate = _LookupCandidate(query=query, match=match)
                if match.matched_profile_url:
                    prior = results_by_url.get(match.matched_profile_url)
                    if not prior or prior.match.match_confidence < match.match_confidence:
                        results_by_url[match.matched_profile_url] = candidate
                else:
                    results_without_url.append(candidate)

            if any(item.match.match_confidence >= 0.9 for item in results_by_url.values()):
                break

        return list(results_by_url.values()) + results_without_url

    async def _enrich_match_activity(
        self,
        *,
        query: str,
        match: LinkedInMatchResult,
    ) -> RecruiterActivitySnapshot | None:
        if "/talent/profile/" not in (match.matched_profile_url or ""):
            return match.recruiter_activity

        await self.browser.navigate_to_search(self.project_url)
        await self.browser.enter_search_string(query)
        slot_count = self._coerce_result_count(await self.browser.get_card_slot_count())
        if slot_count == 0:
            slot_count = self._coerce_result_count(await self.browser.get_card_count())
        if slot_count == 0:
            match.ambiguity_reasons.append(
                "Matched Recruiter profile could not be reloaded for activity enrichment"
            )
            return match.recruiter_activity
        target_index = None
        for card_index in range(min(slot_count, self.max_results_per_query)):
            snapshot = await self.browser.get_card_snapshot(card_index)
            if snapshot.get("url") == match.matched_profile_url:
                target_index = card_index
                break
        if target_index is None:
            match.ambiguity_reasons.append(
                "Matched Recruiter profile was not rediscovered during activity enrichment"
            )
            return match.recruiter_activity

        await self.browser.focus_card_for_review(target_index)
        await self.browser.open_profile_by_url(match.matched_profile_url)
        try:
            status_summary = await self.browser.get_profile_status_summary()
            return RecruiterActivitySnapshot.from_dict(status_summary)
        finally:
            await self.browser.go_back_to_results()

    def _assess_match(
        self,
        lead: GitHubReconciliationLead,
        match: LinkedInMatchResult | None,
        classification: str,
    ) -> ReconciliationAssessment:
        if match is None:
            return ReconciliationAssessment(
                same_person="unknown",
                fit_confirmation="unclear",
                novelty_value="unknown",
                summary="No confident LinkedIn match found.",
            )

        activity = match.recruiter_activity
        novelty_pressure = match.novelty_pressure or classify_recruiter_activity_pressure(activity)
        reachout_status = infer_reachout_status(activity)
        has_name_mismatch = self._match_has_name_mismatch(match)

        if has_name_mismatch:
            same_person = "no"
        elif classification == "high_confidence_match":
            same_person = "yes"
        elif classification == "manual_review":
            same_person = "possible"
        else:
            same_person = "unknown"
        contradictions: list[str] = list(match.ambiguity_reasons)

        fit_confirmation = "confirmed" if classification == "high_confidence_match" else "unclear"
        if has_name_mismatch:
            fit_confirmation = "contradicted"
        expected_company = normalize_company_name(lead.company)
        actual_company = normalize_company_name(match.matched_company)
        if expected_company and actual_company and expected_company != actual_company and expected_company not in actual_company:
            contradictions.append("Current company does not align with GitHub lead")
            fit_confirmation = "contradicted"

        if same_person == "no":
            prefix = "LinkedIn surfaced a different person than the GitHub lead."
        elif classification == "manual_review":
            prefix = "LinkedIn surfaced a plausible candidate match, but the identity still needs review."
        else:
            prefix = "LinkedIn appears to confirm the candidate."

        if novelty_pressure == "high" and activity and activity.message_count >= 6:
            summary = f"{prefix} Recruiter activity suggests the profile is heavily worked."
            novelty_value = "low"
        elif novelty_pressure == "medium":
            summary = f"{prefix} Some prior recruiter activity is already visible."
            novelty_value = "medium"
        else:
            summary = f"{prefix} Visible recruiter activity is limited."
            novelty_value = "high"

        return ReconciliationAssessment(
            same_person=same_person,
            fit_confirmation=fit_confirmation,
            reachout_status=reachout_status,
            novelty_value=novelty_value,
            summary=summary,
            contradictions=contradictions,
        )

    def _decide_action(
        self,
        *,
        match: LinkedInMatchResult | None,
        classification: str,
        assessment: ReconciliationAssessment,
    ) -> str:
        if match is None or classification == "no_confident_match":
            return "manual_review"
        if assessment.same_person in {"unknown", "possible"} and classification != "high_confidence_match":
            return "manual_review"
        if any("name mismatch" in item.lower() for item in assessment.contradictions):
            return "drop_wrong_person"
        if assessment.fit_confirmation == "contradicted":
            return "manual_review"
        if assessment.reachout_status == "recent_outbound_contact":
            return "drop_already_worked"
        if assessment.novelty_value == "low":
            return "promote_low_novelty"
        if classification == "manual_review":
            return "manual_review"
        return "promote"

    async def reconcile_lead(self, lead: GitHubReconciliationLead) -> ReconciliationDecision:
        hints = lead.linkedin_hints
        if hints is None:
            raise ValueError("lead is missing LinkedIn identity hints")

        direct_hint_match = resolve_direct_linkedin_hint(hints)
        lookup_candidates = await self.lookup_candidate_by_identity(hints)
        search_matches = [item.match for item in lookup_candidates]
        search_classification, search_best_match = choose_best_match(search_matches)
        matched_lookup = None

        if direct_hint_match is not None:
            search_confirms_hint = self._search_confirms_direct_hint(
                search_classification,
                search_best_match,
            )
            if "/talent/profile/" in direct_hint_match.matched_profile_url or search_confirms_hint:
                classification = "high_confidence_match"
            else:
                classification = "manual_review"
            best_match = self._merge_direct_hint_with_search(
                direct_hint_match,
                search_best_match,
                search_confirmed=search_confirms_hint,
            )
            if search_confirms_hint and search_best_match is not None:
                matched_lookup = next(
                    (
                        item
                        for item in lookup_candidates
                        if item.match.matched_profile_url == search_best_match.matched_profile_url
                    ),
                    None,
                )
        else:
            classification = search_classification
            best_match = search_best_match
            if best_match is not None:
                matched_lookup = next(
                    (
                        item
                        for item in lookup_candidates
                        if item.match.matched_profile_url == best_match.matched_profile_url
                    ),
                    None,
                )

        if best_match and classification == "high_confidence_match" and matched_lookup is not None:
            if matched_lookup.match.matched_profile_url:
                recruiter_activity = await self._enrich_match_activity(
                    query=matched_lookup.query,
                    match=matched_lookup.match,
                )
                if recruiter_activity:
                    best_match.recruiter_activity = recruiter_activity
                    best_match.novelty_pressure = classify_recruiter_activity_pressure(
                        recruiter_activity
                    )
                for reason in matched_lookup.match.ambiguity_reasons:
                    if reason not in best_match.ambiguity_reasons:
                        best_match.ambiguity_reasons.append(reason)

        assessment = self._assess_match(lead, best_match, classification)
        action = self._decide_action(
            match=best_match,
            classification=classification,
            assessment=assessment,
        )
        rationale = assessment.summary
        if best_match and best_match.evidence:
            rationale = f"{rationale} Evidence: {'; '.join(best_match.evidence[:3])}."
        return ReconciliationDecision(
            action=action,
            rationale=rationale,
            match_result=best_match,
            assessment=assessment,
        )
