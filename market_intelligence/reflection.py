"""HITL Market-Intelligence engine phases — The Reflection.

Splits the monolithic :func:`market_intelligence.engine.update_market_intel`
pipeline into four phases that pause/resume around two HITL gates:

    Gate 1 — The Read:    plan          → user reviews + steers
    (in-flight)           research       → no HITL, long-running
    Gate 2 — The Diff:    propose        → user reviews diff
    (terminal)            commit         → brief written

The existing :func:`update_market_intel` function stays intact (used by
the LinkedIn post-run auto-trigger and the `update_market_intel` Tier-A
tool) so no behaviour-change risk to those callers. The phase functions
here re-use the engine's helpers (``_collect_evidence_batches``,
``_build_deterministic_summary``, the backends, ``_build_artifact``,
``_build_agent_state``, ``_merge_external_research_into_sections``)
without touching them.

State persistence model:
- Each phase function is pure with respect to the database — it returns
  a JSON-serializable dict that the API layer persists to
  ``reflection_sessions.state_json``.
- Each phase reads its prior phase's output from the same dict shape.
- This avoids serializing complex internal types (``MarketEvidenceBatch``,
  ``CriticResult``, ``MarketIntelArtifact``) across the wire — instead
  each phase re-derives them from disk when needed.

Trial-day scope (per the implementation plan):
- ``reflection_phase_propose`` ships **structured `brief_recommendations`
  → hunks** only. Full LLM brief rewrite via ``iterate_brief_draft`` is
  a follow-up enhancement.
- The editorial briefing surfaced in Gate 1 is derived **deterministically**
  from ``planner_summary``. A separate LLM-polish call is a follow-up.
- Steering refinement does re-run the planner with the steering note
  woven into ``previous_agent_state``.
"""

from __future__ import annotations

import dataclasses
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from market_intelligence.agent_backends import (
    HeuristicCriticBackend,
    HeuristicPlannerBackend,
    LLMCriticBackend,
    LLMInternalSynthesisBackend,
    LLMPlannerBackend,
    PlannerResult,
)
from market_intelligence.briefing_polish import (
    BriefingPolishBackend,
    EditorialBriefing,
    HeuristicBriefingBackend,
)
from market_intelligence.engine import (
    ExternalResearchResult,
    _build_agent_state,
    _build_artifact,
    _build_deterministic_summary,
    _collect_evidence_batches,
    _emit_stage,
    _explicit_linkedin_batch_is_incomplete,
    _load_previous_agent_state,
    _load_previous_artifact,
    _maybe_build_external_research_backend,
    _merge_external_research_into_sections,
    _merge_external_results,
    _normalize_text,
    derive_market_key,
    resolve_market_intel_agent_state_path,
    resolve_market_intel_artifact_path,
    _resolve_market_intel_run_dir,
    _role_level_from_brief,
    _geography_from_brief,
)
from market_intelligence.schema import (
    MarketIdentity,
    render_market_intel_markdown,
    render_market_intel_technical_markdown,
)
from shared.brief_loader import load_brief
from shared.brief_writer import write_brief_atomic
from shared.llm_usage import llm_usage_session
from shared.storage import read_json, write_json


MAX_STEERING_ITERATIONS = 3


# ---------------------------------------------------------------------------
# Editorial briefing — superseded by market_intelligence.briefing_polish.
# ---------------------------------------------------------------------------
#
# The original v1 path called _build_editorial_briefing (which truncated
# planner_summary) and _build_intentions (which translated
# external_research_focus). Both are now folded into the
# BriefingPolishBackend / HeuristicBriefingBackend pair in briefing_polish.py.
#
# Module-level singleton: cheap to construct (just the fallback wiring)
# and reused per-call so the polish stage doesn't re-instantiate per
# session.
_BRIEFING_BACKEND = BriefingPolishBackend(fallback=HeuristicBriefingBackend())


def _truncate(text: str, max_len: int = 240) -> str:
    """Word-boundary truncation with ellipsis, used by _hunk_label.

    Survived the editorial-helper removal because hunk labels still
    need a short-form rendering of long proposal strings.
    """

    text = _normalize_text(text)
    if len(text) <= max_len:
        return text
    return text[: max_len - 1].rsplit(" ", 1)[0].rstrip(",.;:") + "…"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Phase 1 — PLAN
# ---------------------------------------------------------------------------


def reflection_phase_plan(
    *,
    brief_path: str | Path,
    run_dir: str | Path | None = None,
    mode: str = "post_run",
    steering_notes: list[str] | None = None,
) -> dict:
    """Run pre-LLM setup + planner. Idempotent across steering refinements.

    Returns a JSON-serializable dict the API layer writes to
    ``reflection_sessions.state_json``. The dict carries everything
    later phases need to re-derive evidence + execute research +
    build the proposed diff: brief_path, run_dir, mode, market
    identity, planner result (full structured), the editorial
    briefing, intentions list, and steering history.

    A steering re-run is a fresh call with ``steering_notes`` populated.
    The notes get woven into the planner's ``previous_agent_state``
    addendum so the LLM sees them as additional context. The planner
    then produces a new ``planner_result`` whose ``external_research_focus``
    reflects the steering ask.
    """

    brief_path = Path(brief_path)
    if not brief_path.exists():
        raise FileNotFoundError(f"Brief file not found: {brief_path}")

    run_dir_path = _resolve_market_intel_run_dir(
        brief_path=brief_path,
        mode=mode,
        run_dir=run_dir,
        run_id=None,
        legacy_output_dir=None,
        output_dir=None,
        report_path=None,
        allow_live_state_dir=False,
        reconstruct_report_analysis=False,
    )
    if mode in {"post_run", "backfill"} and run_dir_path is None:
        raise ValueError(
            "post_run/backfill reflection requires a finalized run_dir under output/runs/."
        )

    raw = read_json(brief_path)
    brief = load_brief(str(brief_path))
    market_identity = MarketIdentity(
        market_key=derive_market_key(brief, raw),
        role_title=brief.role_title,
        role_level=_role_level_from_brief(brief, raw),
        geography=_geography_from_brief(brief, raw),
        channels_seen=[],
        brief_ids_seen=[],
        brief_versions_seen=[],
    )

    artifact_path = resolve_market_intel_artifact_path(
        brief_path, output_dir=run_dir_path
    )
    agent_state_path = resolve_market_intel_agent_state_path(
        brief_path, output_dir=run_dir_path
    )
    previous_artifact = _load_previous_artifact(artifact_path)
    previous_agent_state = _load_previous_agent_state(agent_state_path)

    evidence_batches = _collect_evidence_batches(
        brief_path=brief_path,
        brief=brief,
        raw=raw,
        mode=mode,
        run_dir=run_dir_path,
        report_path=None,
        previous_artifact=previous_artifact,
        reconstruct_report_analysis=mode == "backfill",
    )
    if not evidence_batches:
        raise RuntimeError("No market-intelligence evidence batches could be resolved")

    deterministic_summary = _build_deterministic_summary(
        market_identity=market_identity,
        evidence_batches=evidence_batches,
        previous_artifact=previous_artifact,
    )

    # Weave steering notes into the planner's view of previous_agent_state.
    # The planner's user prompt dumps previous_agent_state as JSON; an
    # extra "operator_steering_notes" key surfaces naturally there. This
    # is additive — when steering_notes is empty the call is identical
    # to the baseline planner invocation.
    steering_notes = list(steering_notes or [])
    planner_input_state: Any = previous_agent_state
    if steering_notes:
        if previous_agent_state is None:
            base_state_dict: dict = {}
        else:
            base_state_dict = dict(previous_agent_state.to_dict())
        base_state_dict["operator_steering_notes"] = [
            {"iteration": idx + 1, "note": note}
            for idx, note in enumerate(steering_notes)
            if _normalize_text(note)
        ]
        # Wrap back into the dataclass so the planner backend's signature
        # is unchanged. MarketIntelAgentState.from_dict is forgiving and
        # ignores unknown top-level keys — the steering addendum survives
        # because the planner serializes the agent state with json.dumps,
        # not via from_dict.
        try:
            from market_intelligence.schema import MarketIntelAgentState

            planner_input_state = MarketIntelAgentState.from_dict(base_state_dict)
            # Stash the addendum onto the dataclass for the prompt builder
            # to find. Acceptable because the planner's user prompt dumps
            # ``previous_agent_state.to_dict()`` and to_dict is defined
            # on the dataclass, but to_dict only serializes declared
            # fields. So we fall back to a lightweight wrapper.
            planner_input_state = _AgentStateWithSteering(
                inner=planner_input_state,
                steering_notes=base_state_dict["operator_steering_notes"],
            )
        except Exception:
            # If schema reconstruction fails for any reason, fall through
            # to the unmodified previous_agent_state — the steering note
            # is lost for that iteration but the planner still runs.
            planner_input_state = previous_agent_state

    planner_backend = LLMPlannerBackend(fallback=HeuristicPlannerBackend())
    artifact_dir = artifact_path.parent
    token_cost_log_path = artifact_dir / "token-cost-log.jsonl"

    with llm_usage_session(
        token_cost_log_path,
        pipeline="market_intel_reflection",
        market_key=market_identity.market_key,
        mode=mode,
        brief_path=str(brief_path),
        phase="plan",
    ):
        _emit_stage(
            f"reflection.plan:start backend={planner_backend.__class__.__name__} "
            f"steering_iterations={len(steering_notes)}"
        )
        planner_result = planner_backend.plan(
            market_identity=market_identity,
            deterministic_summary=deterministic_summary,
            evidence_batches=evidence_batches,
            previous_artifact=previous_artifact,
            previous_agent_state=planner_input_state,
        )
        _emit_stage(
            "reflection.plan:done "
            f"focus={len(planner_result.external_research_focus)} "
            f"edge_case_focus={len(planner_result.edge_case_research_focus)}"
        )

        # The recruiter-facing briefing is computed from STRUCTURED signals
        # via the polish backend — not from planner_result.planner_summary
        # which is engineer narrative ("Tracking N hypotheses..."). The
        # polish backend handles its own four-route failure cascade and
        # emits its own start/done/fallback _emit_stage logs (see
        # market_intelligence/briefing_polish.py). Lives inside the
        # llm_usage_session block so its tokens land in the same cost log.
        briefing: EditorialBriefing = _BRIEFING_BACKEND.polish(
            market_identity=market_identity,
            deterministic_summary=deterministic_summary,
            planner_result=planner_result,
            steering_notes=steering_notes,
        )

    return {
        "phase_outputs": {
            "plan": {
                "planner_result": planner_result.to_dict(),
                "briefing": briefing.to_dict(),
                "should_collect_external": bool(
                    planner_result.should_collect_external_research
                ),
                "should_collect_edge_case": bool(
                    planner_result.should_collect_edge_case_research
                ),
            }
        },
        "context": {
            "brief_path": str(brief_path),
            "run_dir": str(run_dir_path) if run_dir_path else None,
            "mode": mode,
            "market_identity": market_identity.to_dict(),
        },
        "steering_history": [
            {"iteration": idx + 1, "note": note, "timestamp": _utc_now()}
            for idx, note in enumerate(steering_notes)
        ],
    }


class _AgentStateWithSteering:
    """Tiny wrapper that lets the planner prompt see steering notes.

    The :func:`build_planner_user_prompt` helper calls
    ``previous_agent_state.to_dict()`` to dump the prior state into the
    LLM prompt. By passing a wrapper whose ``to_dict()`` returns the
    inner dataclass dict + an ``operator_steering_notes`` addendum, we
    surface the recruiter's steering input to the planner without
    modifying the prompt builder or the dataclass schema.
    """

    def __init__(self, *, inner: Any, steering_notes: list[dict]) -> None:
        self._inner = inner
        self._steering_notes = steering_notes

    def to_dict(self) -> dict:
        base = self._inner.to_dict() if self._inner is not None else {}
        base["operator_steering_notes"] = self._steering_notes
        return base

    def __getattr__(self, name: str) -> Any:
        # Delegation so anything else the planner reads off the agent
        # state continues to work transparently. ``__getattr__`` only
        # fires for names not found on the wrapper itself, which is
        # what we want.
        return getattr(self._inner, name)


# ---------------------------------------------------------------------------
# Phase 2 — RESEARCH
# ---------------------------------------------------------------------------


def reflection_phase_research(*, state: dict) -> dict:
    """Execute external research using the approved planner focus.

    Long-running. The API layer kicks this off in a background thread
    after Gate 1 approval; on completion the API patches the session
    with the new state.

    Returns the input ``state`` dict plus a new ``research`` block
    under ``phase_outputs``. The block carries the
    ``ExternalResearchResult`` as a dict (via ``dataclasses.asdict``),
    plus stage_errors and a summary count for the polling status
    surface.

    If no external research backend is configured (no Perplexity /
    Anthropic key), the research phase is a no-op that records the
    skip reason and lets the propose phase synthesize from internal
    evidence only.
    """

    plan_block = (state.get("phase_outputs") or {}).get("plan") or {}
    context = state.get("context") or {}
    if not plan_block:
        raise ValueError("research phase requires a completed plan phase")
    brief_path = Path(context["brief_path"])
    run_dir = Path(context["run_dir"]) if context.get("run_dir") else None
    mode = context.get("mode", "post_run")

    raw = read_json(brief_path)
    brief = load_brief(str(brief_path))
    market_identity = MarketIdentity.from_dict(context["market_identity"])
    planner_result = _planner_result_from_dict(plan_block["planner_result"])

    artifact_path = resolve_market_intel_artifact_path(brief_path, output_dir=run_dir)
    agent_state_path = resolve_market_intel_agent_state_path(
        brief_path, output_dir=run_dir
    )
    previous_artifact = _load_previous_artifact(artifact_path)
    previous_agent_state = _load_previous_agent_state(agent_state_path)
    evidence_batches = _collect_evidence_batches(
        brief_path=brief_path,
        brief=brief,
        raw=raw,
        mode=mode,
        run_dir=run_dir,
        report_path=None,
        previous_artifact=previous_artifact,
        reconstruct_report_analysis=mode == "backfill",
    )

    external_backend = _maybe_build_external_research_backend()
    artifact_dir = artifact_path.parent
    token_cost_log_path = artifact_dir / "token-cost-log.jsonl"
    external_result: ExternalResearchResult | None = None
    stage_errors: list[str] = []
    skip_reason: str | None = None

    if external_backend is None:
        skip_reason = "no_backend"
    else:
        batch_incomplete = _explicit_linkedin_batch_is_incomplete(
            evidence_batches=evidence_batches, output_dir=None
        )
        if batch_incomplete:
            skip_reason = "incomplete_run"
        elif not (
            planner_result.should_collect_external_research
            or planner_result.should_collect_edge_case_research
        ):
            skip_reason = "planner_disabled"

    if skip_reason is None and external_backend is not None:
        with llm_usage_session(
            token_cost_log_path,
            pipeline="market_intel_reflection",
            market_key=market_identity.market_key,
            mode=mode,
            brief_path=str(brief_path),
            phase="research",
        ):
            if planner_result.should_collect_external_research:
                try:
                    _emit_stage(
                        "reflection.research:start "
                        f"backend={external_backend.__class__.__name__} "
                        f"focus={len(planner_result.external_research_focus)}"
                    )
                    external_result = external_backend.collect(
                        market_identity=market_identity,
                        previous_artifact=previous_artifact,
                        previous_agent_state=previous_agent_state,
                        evidence_batches=evidence_batches,
                        planner_result=planner_result,
                        research_focus=planner_result.external_research_focus,
                        research_mode="general",
                    )
                    _emit_stage(
                        "reflection.research:done "
                        f"sources={len(external_result.sources)} "
                        f"findings={len(external_result.market_findings)} "
                        f"implications={len(external_result.sourcing_implications)}"
                    )
                except Exception as exc:
                    stage_errors.append(f"external_research:{exc}")
                    _emit_stage(f"reflection.research:error {exc}")
            if planner_result.should_collect_edge_case_research:
                try:
                    _emit_stage(
                        "reflection.research:edge_case_start "
                        f"focus={len(planner_result.edge_case_research_focus)}"
                    )
                    edge_case_result = external_backend.collect(
                        market_identity=market_identity,
                        previous_artifact=previous_artifact,
                        previous_agent_state=previous_agent_state,
                        evidence_batches=evidence_batches,
                        planner_result=planner_result,
                        research_focus=planner_result.edge_case_research_focus,
                        research_mode="edge_case",
                        edge_case_reasoning=planner_result.edge_case_research_reasoning,
                    )
                    edge_case_result.edge_case_triggered = True
                    edge_case_result.edge_case_reasoning = (
                        planner_result.edge_case_research_reasoning
                    )
                    edge_case_result.edge_case_focus = list(
                        planner_result.edge_case_research_focus
                    )
                    external_result = _merge_external_results(
                        external_result, edge_case_result
                    )
                except Exception as exc:
                    stage_errors.append(f"edge_case_research:{exc}")
                    _emit_stage(f"reflection.research:edge_case_error {exc}")

    research_payload: dict[str, Any]
    if external_result is None:
        research_payload = {
            "external_result": None,
            "skip_reason": skip_reason or "no_focus",
            "stage_errors": stage_errors,
            "summary": {
                "sources": 0,
                "findings": 0,
                "implications": 0,
            },
        }
    else:
        research_payload = {
            "external_result": dataclasses.asdict(external_result),
            "skip_reason": None,
            "stage_errors": stage_errors,
            "summary": {
                "sources": len(external_result.sources),
                "findings": len(external_result.market_findings),
                "implications": len(external_result.sourcing_implications),
            },
        }

    next_state = dict(state)
    outputs = dict(state.get("phase_outputs") or {})
    outputs["research"] = research_payload
    next_state["phase_outputs"] = outputs
    return next_state


# ---------------------------------------------------------------------------
# Phase 3 — PROPOSE
# ---------------------------------------------------------------------------


def reflection_phase_propose(*, state: dict) -> dict:
    """Run synthesis + critic + build the artifact + compute brief hunks.

    Does NOT write the canonical artifact to disk — that happens at
    commit time. The artifact is held in ``state_json`` as the source
    for the brief diff hunks the user reviews at Gate 2.

    The hunks are derived from the artifact's ``brief_recommendations``
    structured list (the engine's existing taxonomy of brief-mutation
    proposals) projected onto a UI-friendly per-hunk schema. Trial-day
    scope: every recommendation becomes one hunk; the propose phase
    does not call ``iterate_brief_draft`` for a full brief rewrite.
    """

    plan_block = (state.get("phase_outputs") or {}).get("plan") or {}
    research_block = (state.get("phase_outputs") or {}).get("research") or {}
    context = state.get("context") or {}
    if not plan_block:
        raise ValueError("propose phase requires a completed plan phase")

    brief_path = Path(context["brief_path"])
    run_dir = Path(context["run_dir"]) if context.get("run_dir") else None
    mode = context.get("mode", "post_run")

    raw = read_json(brief_path)
    brief = load_brief(str(brief_path))
    market_identity = MarketIdentity.from_dict(context["market_identity"])
    planner_result = _planner_result_from_dict(plan_block["planner_result"])

    artifact_path = resolve_market_intel_artifact_path(brief_path, output_dir=run_dir)
    agent_state_path = resolve_market_intel_agent_state_path(
        brief_path, output_dir=run_dir
    )
    previous_artifact = _load_previous_artifact(artifact_path)
    previous_agent_state = _load_previous_agent_state(agent_state_path)
    evidence_batches = _collect_evidence_batches(
        brief_path=brief_path,
        brief=brief,
        raw=raw,
        mode=mode,
        run_dir=run_dir,
        report_path=None,
        previous_artifact=previous_artifact,
        reconstruct_report_analysis=mode == "backfill",
    )
    deterministic_summary = _build_deterministic_summary(
        market_identity=market_identity,
        evidence_batches=evidence_batches,
        previous_artifact=previous_artifact,
    )

    external_result_dict = research_block.get("external_result")
    external_result: ExternalResearchResult | None = None
    if external_result_dict is not None:
        try:
            external_result = ExternalResearchResult(**external_result_dict)
        except Exception:
            # Defensive: if the persisted dict has unexpected keys
            # (schema drift between phases), fall back to None and let
            # the propose phase synthesize from internal evidence.
            external_result = None

    artifact_dir = artifact_path.parent
    token_cost_log_path = artifact_dir / "token-cost-log.jsonl"
    synthesis_backend = LLMInternalSynthesisBackend(
        fallback_backend=_HeuristicSynthesisBackendShim()
    )
    critic_backend = LLMCriticBackend(fallback=HeuristicCriticBackend())
    stage_errors: list[str] = list(research_block.get("stage_errors") or [])
    preserve_previous_narrative = False

    with llm_usage_session(
        token_cost_log_path,
        pipeline="market_intel_reflection",
        market_key=market_identity.market_key,
        mode=mode,
        brief_path=str(brief_path),
        phase="propose",
    ):
        try:
            generated_sections = synthesis_backend.synthesize(
                market_identity=market_identity,
                deterministic_summary=deterministic_summary,
                evidence_batches=evidence_batches,
                previous_artifact=previous_artifact,
                planner_result=planner_result,
                external_research=external_result,
            )
            generated_sections = _merge_external_research_into_sections(
                generated_sections, external_result
            )
        except Exception as exc:
            preserve_previous_narrative = True
            stage_errors.append(f"synthesis:{exc}")
            _emit_stage(f"reflection.propose:synthesis_error {exc}")
            generated_sections = _merge_external_research_into_sections({}, external_result)

        try:
            critic_result = critic_backend.critique(
                market_identity=market_identity,
                deterministic_summary=deterministic_summary,
                evidence_batches=evidence_batches,
                previous_artifact=previous_artifact,
                planner_result=planner_result,
                draft_sections=generated_sections,
                external_research=external_result,
            )
        except Exception as exc:
            preserve_previous_narrative = True
            stage_errors.append(f"critic:{exc}")
            _emit_stage(f"reflection.propose:critic_error {exc}")
            critic_result = HeuristicCriticBackend().critique(
                market_identity=market_identity,
                deterministic_summary=deterministic_summary,
                evidence_batches=evidence_batches,
                previous_artifact=previous_artifact,
                planner_result=planner_result,
                draft_sections=generated_sections,
                external_research=external_result,
            )

    artifact = _build_artifact(
        brief=brief,
        market_identity=market_identity,
        deterministic_summary=deterministic_summary,
        evidence_batches=evidence_batches,
        previous_artifact=previous_artifact,
        generated_sections=critic_result.keep_sections or generated_sections,
        preserve_previous_narrative=preserve_previous_narrative,
        external_result=external_result,
        section_generation_metadata=critic_result.section_generation_metadata,
        delta_since_last_run=critic_result.delta_since_last_run,
    )
    agent_state = _build_agent_state(
        market_identity=market_identity,
        evidence_batches=evidence_batches,
        previous_agent_state=previous_agent_state,
        planner_result=planner_result,
        critic_result=critic_result,
        external_result=external_result,
    )

    artifact_dict = artifact.to_dict()
    hunks = _build_hunks_from_artifact(artifact_dict, brief_raw=raw)

    next_state = dict(state)
    outputs = dict(state.get("phase_outputs") or {})
    outputs["propose"] = {
        "artifact": artifact_dict,
        "agent_state": agent_state.to_dict(),
        "critic_summary": critic_result.critique_summary,
        "stage_errors": stage_errors,
        "hunks": hunks,
        "brief_at_propose": raw,  # snapshot for diff/commit reference
    }
    next_state["phase_outputs"] = outputs
    return next_state


class _HeuristicSynthesisBackendShim:
    """Minimal heuristic synthesis when no LLM is available.

    The LLM synthesis backend's fallback is the engine's
    ``HeuristicMarketIntelSynthesisBackend``. To avoid a circular
    import (engine → reflection → engine), we re-import lazily here.
    """

    def synthesize(self, **kwargs: Any) -> dict:
        from market_intelligence.engine import HeuristicMarketIntelSynthesisBackend

        return HeuristicMarketIntelSynthesisBackend().synthesize(**kwargs)


# ---------------------------------------------------------------------------
# Phase 4 — COMMIT
# ---------------------------------------------------------------------------


def reflection_commit(
    *,
    state: dict,
    accepted_hunk_ids: list[str],
    edited_hunks: dict[str, dict] | None = None,
) -> dict:
    """Apply accepted (and optionally edited) hunks; persist artifact + brief.

    Steps:
    1. Apply each accepted (and edited-if-present) hunk to the brief
       snapshot taken at propose-time; produce ``next_brief``.
    2. Write the proposed market-intel artifact to disk (canonical +
       history snapshot), matching what ``update_market_intel`` does.
    3. Write the new brief via ``write_brief_atomic`` so a ``versions/``
       snapshot is created.
    4. Return ``{"brief_version_path": <path>, "applied_hunks": [...]}``
       so the API layer can record it on the session row.
    """

    propose_block = (state.get("phase_outputs") or {}).get("propose") or {}
    context = state.get("context") or {}
    if not propose_block:
        raise ValueError("commit requires a completed propose phase")

    brief_path = Path(context["brief_path"])
    run_dir = Path(context["run_dir"]) if context.get("run_dir") else None
    artifact_payload = propose_block.get("artifact") or {}
    hunks = propose_block.get("hunks") or []
    base_brief = dict(propose_block.get("brief_at_propose") or read_json(brief_path))

    accepted_set = set(accepted_hunk_ids or [])
    edited_hunks = dict(edited_hunks or {})

    applied: list[dict] = []
    next_brief = dict(base_brief)
    for hunk in hunks:
        hunk_id = hunk.get("hunk_id")
        if hunk_id not in accepted_set:
            continue
        effective = dict(hunk)
        if hunk_id in edited_hunks:
            effective["after"] = edited_hunks[hunk_id].get(
                "after", effective.get("after")
            )
        try:
            next_brief = _apply_hunk_to_brief(next_brief, effective)
            applied.append(
                {
                    "hunk_id": hunk_id,
                    "section": effective.get("section"),
                    "kind": effective.get("kind"),
                    "edited": hunk_id in edited_hunks,
                }
            )
        except Exception as exc:
            # Skip hunks we can't safely apply — surface in the commit
            # response so the API layer can include them in a soft
            # warning. The brief still commits with the hunks that
            # applied cleanly.
            applied.append(
                {
                    "hunk_id": hunk_id,
                    "section": effective.get("section"),
                    "kind": effective.get("kind"),
                    "skipped_reason": f"apply_failed: {exc}",
                }
            )

    # Persist the market-intel artifact (canonical + history snapshot).
    artifact_path = resolve_market_intel_artifact_path(brief_path, output_dir=run_dir)
    agent_state_path = resolve_market_intel_agent_state_path(
        brief_path, output_dir=run_dir
    )
    artifact_dir = artifact_path.parent
    history_dir = artifact_dir / "history"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    history_dir.mkdir(parents=True, exist_ok=True)
    write_json(artifact_path, artifact_payload)
    if propose_block.get("agent_state"):
        write_json(agent_state_path, propose_block["agent_state"])
    history_stem = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    write_json(history_dir / f"{history_stem}.json", artifact_payload)

    # Write the new brief atomically. write_brief_atomic creates a
    # versions/<stamp>.json snapshot as a side effect — that path is
    # what we surface to the recruiter as "the new brief version".
    write_brief_atomic(abs_path=brief_path, payload=next_brief)
    versions_dir = brief_path.parent / "versions"
    new_versions = sorted(
        versions_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True
    )
    brief_version_path = (
        str(new_versions[0]) if new_versions else str(brief_path)
    )

    return {
        "brief_version_path": brief_version_path,
        "applied_hunks": applied,
        "next_brief": next_brief,
    }


# ---------------------------------------------------------------------------
# Hunk computation + application
# ---------------------------------------------------------------------------


_HUNK_TARGET_TO_SECTION = {
    "additional_search_terms": "additional_search_terms",
    "employer_signal_rules": "employer_signal_rules",
    "search_priorities": "search_priorities",
    "instructions": "instructions",
    "notes": "notes",
}


def _build_hunks_from_artifact(artifact: dict, *, brief_raw: dict) -> list[dict]:
    """Project artifact ``brief_recommendations`` onto UI hunks.

    Each recommendation becomes one hunk. The hunk schema:

    .. code-block:: json

        {
          "hunk_id": "rec-...",
          "section": "additional_search_terms" | "employer_signal_rules" | ...,
          "kind": "add" | "modify",
          "label": "Short editorial label for the hunk",
          "before": "current value (string or null)",
          "after": "proposed value (string)",
          "rationale": "why Cloris wants this change",
          "confidence": 0.0-1.0,
          "default_approved": true | false
        }

    For trial-day scope only the most common ``target_field`` values
    are surfaced. Unknown targets fall through with ``section="notes"``.
    Hunks where the proposed value is already present in the brief
    are dropped (no-op recommendations).
    """

    recommendations = artifact.get("brief_recommendations") or []
    hunks: list[dict] = []
    for raw_rec in recommendations:
        if not isinstance(raw_rec, dict):
            continue
        rec_id = _normalize_text(raw_rec.get("recommendation_id"))
        target = _normalize_text(raw_rec.get("target_field")).lower()
        proposal = _normalize_text(raw_rec.get("proposal"))
        rationale = _normalize_text(raw_rec.get("reason"))
        confidence = _coerce_confidence(raw_rec.get("confidence"))
        if not proposal:
            continue
        section = _HUNK_TARGET_TO_SECTION.get(target, "notes")
        before, kind = _hunk_before_and_kind(brief_raw, section, proposal)
        if before == proposal:
            # No-op recommendation; skip.
            continue
        hunks.append(
            {
                "hunk_id": rec_id or f"hunk-{len(hunks) + 1}",
                "section": section,
                "kind": kind,
                "label": _hunk_label(section, kind, proposal),
                "before": before,
                "after": proposal,
                "rationale": rationale,
                "confidence": confidence,
                "default_approved": confidence >= 0.65,
                "target_field": target or section,
            }
        )
    return hunks


def _hunk_before_and_kind(
    brief_raw: dict, section: str, proposal: str
) -> tuple[Any, str]:
    """Return (before_value, kind) for a recommendation against a section.

    For list-shaped brief sections (``additional_search_terms``,
    ``employer_signal_rules``, ``search_priorities``), the kind is
    always ``add`` and ``before`` is ``None`` (we're appending).
    For string-shaped sections (``instructions``, ``notes``), if the
    section already has content we treat it as ``modify`` (the
    proposal extends or replaces the prose); otherwise ``add``.
    """

    LIST_SECTIONS = {"additional_search_terms", "employer_signal_rules", "search_priorities"}
    if section in LIST_SECTIONS:
        return None, "add"
    existing = brief_raw.get(section)
    if isinstance(existing, str) and existing.strip():
        return existing, "modify"
    return None, "add"


def _hunk_label(section: str, kind: str, proposal: str) -> str:
    section_labels = {
        "additional_search_terms": "additional search terms",
        "employer_signal_rules": "employer signal rule",
        "search_priorities": "search priority",
        "instructions": "search instructions",
        "notes": "brief notes",
    }
    label = section_labels.get(section, section.replace("_", " "))
    verb = "Add to" if kind == "add" else "Refine"
    short = _truncate(proposal, max_len=80)
    return f"{verb} {label} — {short}"


def _coerce_confidence(value: Any) -> float:
    try:
        f = float(value)
    except (TypeError, ValueError):
        return 0.5
    return max(0.0, min(1.0, f))


def _apply_hunk_to_brief(brief: dict, hunk: dict) -> dict:
    """Apply one accepted hunk to the brief, returning the updated dict.

    Pure: does not mutate the input. Skips hunks whose ``after`` is
    empty after normalization.

    MERGE CONTRACT (mirrors
    cloris/frontend/src/components/RefreshBrief.svelte:buildMergedV2):

    - List sections (additional_search_terms, employer_signal_rules,
      search_priorities): dedupe-append. Compare incoming value to
      existing list entries case-insensitively (using ``_normalize_text``
      collapse for whitespace); skip if already present, append if new.
    - Prose sections (instructions, notes): append-with-newline. If
      existing prose is non-empty, append "\\n\\n" + new prose; else
      replace with new prose.
    - Other sections (legacy or future): structural replace.

    Drift between this and ``buildMergedV2`` (TS) produces silently-
    different brief writes across Reflection and RefreshBrief. Keep
    them in lockstep — when one moves, the other moves too.
    """

    section = hunk.get("section")
    after = hunk.get("after")
    kind = hunk.get("kind")
    if not section or not isinstance(after, str) or not after.strip():
        return brief
    next_brief = dict(brief)
    LIST_SECTIONS = {"additional_search_terms", "employer_signal_rules", "search_priorities"}
    if section in LIST_SECTIONS:
        existing = list(next_brief.get(section) or [])
        # De-dupe on normalized text so re-running a hunk doesn't
        # double-write.
        normalized_existing = {
            _normalize_text(item).lower() for item in existing if isinstance(item, str)
        }
        normalized_after = _normalize_text(after).lower()
        if normalized_after not in normalized_existing:
            existing.append(after.strip())
        next_brief[section] = existing
        return next_brief
    if kind == "add" or section in {"instructions", "notes"}:
        if section == "instructions" or section == "notes":
            existing = next_brief.get(section)
            if isinstance(existing, str) and existing.strip():
                next_brief[section] = existing.rstrip() + "\n\n" + after.strip()
            else:
                next_brief[section] = after.strip()
            return next_brief
    next_brief[section] = after.strip()
    return next_brief


# ---------------------------------------------------------------------------
# PlannerResult <-> dict round-trip
# ---------------------------------------------------------------------------


def _planner_result_from_dict(payload: dict) -> PlannerResult:
    """Reconstruct a PlannerResult from its to_dict() output.

    PlannerResult doesn't ship a from_dict, but its fields are all
    JSON-trivial (strings, lists, dicts, bools, optional float). This
    helper handles the round-trip so phases after PLAN can re-derive
    the typed object.
    """

    return PlannerResult(
        planner_summary=str(payload.get("planner_summary") or ""),
        active_hypotheses=list(payload.get("active_hypotheses") or []),
        resolved_hypotheses=list(payload.get("resolved_hypotheses") or []),
        open_unknowns=list(payload.get("open_unknowns") or []),
        research_backlog=list(payload.get("research_backlog") or []),
        update_sections=list(payload.get("update_sections") or []),
        confidence_ceiling_by_section=dict(
            payload.get("confidence_ceiling_by_section") or {}
        ),
        should_collect_external_research=bool(
            payload.get("should_collect_external_research") or False
        ),
        external_research_focus=list(payload.get("external_research_focus") or []),
        should_collect_edge_case_research=bool(
            payload.get("should_collect_edge_case_research") or False
        ),
        edge_case_research_reasoning=str(
            payload.get("edge_case_research_reasoning") or ""
        ),
        edge_case_research_focus=list(payload.get("edge_case_research_focus") or []),
        edge_case_confidence_ceiling=payload.get("edge_case_confidence_ceiling"),
    )
