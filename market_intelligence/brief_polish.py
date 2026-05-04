"""Brief polish — Cloris-voice reshape over recruiter intake captures.

Owns the transformation from intake chapter captures (free-form prose)
to a polished, schema-correct V2 brief draft. Runs at intake time, not
at post-run analysis time — sibling of :mod:`market_intelligence.briefing_polish`
in pattern, distinct in domain.

Two backends:

- :class:`BriefPolishBackend`: Opus LLM rewrite. Falls through to
  heuristic on any of seven conditions (see :func:`BriefPolishBackend.polish`
  docstring).
- :class:`HeuristicBriefPolishBackend`: deterministic builder from
  chapter captures. Mirrors the frontend ``seedV2DraftFromChapters``
  scaffolder so server-side and client-side scaffolds are byte-identical
  on the structured fields. Always passes :func:`validate_v2_brief`.

Confidence is computed PROGRAMMATICALLY (not LLM self-rating):

- Heuristic: signal-density. ``populated_chapter_fields / 7``.
- LLM: flat ``1.0`` on success (no detected failure mode across the
  seven cascade routes). Acknowledged placeholder; post-trial calibration
  target uses the logged ``overlap_avg`` distribution.

Domain-leak note: this module sits under ``market_intelligence/`` for
clean sibling import of the helpers in :mod:`briefing_polish`
(``BANNED_BRIEFING_TOKENS``, ``SNAKE_CASE_IDENTIFIER_RE``,
``_has_llm_access``, ``_normalize_text``). Architectural debt against
``AGENTS.md``'s "post-run intelligence" scoping — tracked for week-2
cleanup (extract shared helpers into ``shared/llm_polish_common.py``
and move this module to its proper domain).
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from shared.brief_v2_schema import BriefSchemaError, validate_v2_brief
from shared.llm_clients import opus_llm

from market_intelligence.briefing_polish import (
    BANNED_BRIEFING_TOKENS,
    SNAKE_CASE_IDENTIFIER_RE,
    _has_llm_access,
)


# Hallucination guard threshold: minimum average lexical overlap between
# capability_areas[*].description and the recruiter's good_looks.prose.
# Below this, we treat the LLM as having invented capability areas and
# cascade to the heuristic seed. Starts at 0.30; tunable based on logged
# overlap_avg distribution post-trial. Threshold lives at module scope
# so it's a one-line tweak when telemetry tells us the cluster shifted.
HALLUCINATION_OVERLAP_THRESHOLD: float = 0.30

# Minimum prose length to count toward heuristic confidence's "populated"
# signal. Mirrors :data:`market_intelligence.briefing_polish.MIN_PARAGRAPH_CHARS`
# so the substantive-prose threshold is consistent across both polish
# surfaces.
MIN_SUBSTANTIVE_CHARS: int = 30

# Denominator for the heuristic confidence formula. The seven counted
# fields (see :class:`HeuristicBriefPolishBackend` docstring) yield
# 0.0 to 1.0 in 1/7 increments — enough granularity for the recruiter
# to distinguish "minimal capture" from "full capture" in the Reference
# Slip.
HEURISTIC_CONFIDENCE_DENOMINATOR: int = 7

# Polish prompt token budget. Modest because the recruiter's intake
# captures are bounded prose (a few paragraphs each), not an arbitrarily
# large run dump like the briefing polish's deterministic_summary.
POLISH_MAX_TOKENS: int = 4000

# Overlap-token regex: lowercased, alpha-only, ≥3 chars. The 3-char
# floor filters stop-word-ish tiny tokens ("a", "is", "of") that would
# inflate spurious overlap. Empirical cutoff; tunable post-trial along
# with HALLUCINATION_OVERLAP_THRESHOLD.
_OVERLAP_TOKEN_RE = re.compile(r"[a-z]{3,}")


# ---------------------------------------------------------------------------
# Telemetry — log every polish call with [intake] prefix
# ---------------------------------------------------------------------------


def _emit_stage(message: str) -> None:
    """Print a single-line stderr log with the ``[intake]`` prefix.

    Mirrors :func:`market_intelligence.briefing_polish._emit_stage` in
    shape (single line, stderr, flushed) but uses ``[intake]`` instead
    of ``[market-intel]`` because brief polish runs at intake time, not
    at post-run analysis. Operators grep ``brief.polish:`` (this module)
    or ``reflection.polish:`` (Thread A) to see each polish stream
    interleaved with the engine's other stage logs.
    """

    import sys

    print(f"[intake] {message}", file=sys.stderr, flush=True)


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------


@dataclass
class BriefPolishResult:
    """Polished V2 brief draft + provenance metadata.

    ``v2_draft`` is a schema-correct V2 brief dict (passes
    :func:`validate_v2_brief`). ``source`` is one of ``"llm"`` (LLM
    success path), ``"deterministic"`` (heuristic fallback path or no
    LLM access), or ``"empty"`` (no usable captures). ``confidence`` is
    programmatic — never LLM self-rating.
    """

    v2_draft: dict
    source: str = "deterministic"
    confidence: float = 0.0
    polished_at: str = field(default="")

    def __post_init__(self) -> None:
        if not self.polished_at:
            self.polished_at = datetime.now(timezone.utc).isoformat()

    def to_meta_dict(self) -> dict:
        """Return metadata for ``state_json["v2_draft_polish_meta"]``.

        Excludes ``v2_draft`` (which lives at ``state_json["v2_draft"]``,
        not nested under polish_meta — see plan's state_json schema
        bullets). The Reference Slip in the review chapter reads from
        this shape verbatim.
        """

        return {
            "source": self.source,
            "confidence": round(float(self.confidence), 2),
            "polished_at": self.polished_at,
        }


# ---------------------------------------------------------------------------
# Heuristic backend — Python port of frontend seedV2DraftFromChapters
# ---------------------------------------------------------------------------


class HeuristicBriefPolishBackend:
    """Deterministic V2 draft builder. Always passes ``validate_v2_brief``.

    Mirrors ``cloris/frontend/src/components/OnboardingFlow.svelte``'s
    :func:`seedV2DraftFromChapters` so the heuristic fallback produces
    the same structural shape the frontend already produces on chapter
    advance into review. The Path 3 promotion (linkedin_project_id
    into source_config.linkedin) matches the frontend behavior exactly,
    so a recruiter who never clicks Polish lands on the same v2_draft
    whether the seed came from the frontend or this backend's fallback.

    Confidence is the population fraction across seven scoring fields:

    1. ``role.title`` — any non-empty.
    2. ``role.framing`` — ``≥MIN_SUBSTANTIVE_CHARS`` (30) chars.
    3. ``good_looks.prose`` — ``≥MIN_SUBSTANTIVE_CHARS`` chars
       (load-bearing — capability areas come from here).
    4. ``lookalikes.exemplars_prose`` — ``≥MIN_SUBSTANTIVE_CHARS`` chars.
    5. ``lookalikes.non_fit_prose`` — ``≥MIN_SUBSTANTIVE_CHARS`` chars.
    6. ``where_to_look.target_modules`` — non-empty list of strings.
    7. ``where_to_look.linkedin_project_id`` — any non-empty (Path 3).

    Source is ``"deterministic"`` whenever ``role.title`` OR
    ``good_looks.prose`` carries content; ``"empty"`` when neither does
    (the Reference Slip surfaces this so the recruiter knows polish had
    nothing to work with).
    """

    def polish(
        self,
        *,
        chapter_captures: dict[str, Any],
        role_title: str | None = None,
    ) -> BriefPolishResult:
        role = _as_dict(chapter_captures.get("role"))
        good_looks = _as_dict(chapter_captures.get("good_looks"))
        lookalikes = _as_dict(chapter_captures.get("lookalikes"))
        where_to_look = _as_dict(chapter_captures.get("where_to_look"))

        # Mirror the frontend seeder's title fallback: prefer the
        # chapter capture, fall back to the session-level role_title
        # hint (set at session creation), default to empty string.
        title = _as_str(role.get("title")) or _as_str(role_title)

        # Description fallback matches the frontend literal so a
        # recruiter who never typed in good_looks lands on the same
        # placeholder text whether they were rendered server-side or
        # client-side.
        prose_value = good_looks.get("prose")
        description = (
            prose_value
            if isinstance(prose_value, str)
            else "What this person needs to be able to do."
        )

        # Sort target_modules so the brief disk-shape stays stable
        # across writes. Mirrors the frontend's toggleTargetModule
        # canonicalization at OnboardingFlow.svelte:516.
        target_modules = _as_str_list(where_to_look.get("target_modules"))
        if not target_modules:
            target_modules = ["linkedin"]
        target_modules = sorted(set(target_modules))

        v2_draft: dict[str, Any] = {
            "role_title": title,
            "capability_areas": [
                {
                    "name": "Capability area 1",
                    "description": description,
                }
            ],
            "depth_distinction": {
                "builder_definition": "",
                "user_definition": "",
                "edge_case_guidance": "",
            },
            "non_fit_patterns": [],
            "target_modules": target_modules,
        }

        # Path 3 — promote linkedin_project_id only when present so the
        # source_config block doesn't survive as an empty {} (which is
        # validate_v2_brief-clean but pointless).
        li_project_id = _as_str(where_to_look.get("linkedin_project_id"))
        li_project_name = _as_str(where_to_look.get("linkedin_project_name"))
        if li_project_id:
            linkedin: dict[str, Any] = {"project_id": li_project_id}
            if li_project_name:
                linkedin["project_name"] = li_project_name
            v2_draft["source_config"] = {"linkedin": linkedin}

        confidence = _heuristic_confidence(
            role=role,
            good_looks=good_looks,
            lookalikes=lookalikes,
            where_to_look=where_to_look,
            li_project_id=li_project_id,
        )

        # source=empty when the recruiter has nothing to polish from.
        # Without title or prose, the seed is pure placeholder; the
        # Reference Slip should say so honestly.
        if not title and not _as_str(good_looks.get("prose")):
            return BriefPolishResult(
                v2_draft=v2_draft,
                source="empty",
                confidence=0.0,
            )

        return BriefPolishResult(
            v2_draft=v2_draft,
            source="deterministic",
            confidence=confidence,
        )


def _heuristic_confidence(
    *,
    role: dict,
    good_looks: dict,
    lookalikes: dict,
    where_to_look: dict,
    li_project_id: str,
) -> float:
    """``populated_chapter_fields / 7``. See backend docstring for the seven."""

    populated = 0
    if _as_str(role.get("title")):
        populated += 1
    if len(_as_str(role.get("framing"))) >= MIN_SUBSTANTIVE_CHARS:
        populated += 1
    if len(_as_str(good_looks.get("prose"))) >= MIN_SUBSTANTIVE_CHARS:
        populated += 1
    if len(_as_str(lookalikes.get("exemplars_prose"))) >= MIN_SUBSTANTIVE_CHARS:
        populated += 1
    if len(_as_str(lookalikes.get("non_fit_prose"))) >= MIN_SUBSTANTIVE_CHARS:
        populated += 1
    if _as_str_list(where_to_look.get("target_modules")):
        populated += 1
    if li_project_id:
        populated += 1
    return round(populated / HEURISTIC_CONFIDENCE_DENOMINATOR, 2)


# ---------------------------------------------------------------------------
# LLM backend — Opus, with seven-route failure cascade to heuristic
# ---------------------------------------------------------------------------


class BriefPolishBackend:
    """Opus-driven brief polish. Falls through to heuristic on failure.

    Single entry point: :func:`polish`. Seven failure modes converge
    on :class:`HeuristicBriefPolishBackend`:

    1. ``opus_llm`` raises (network, rate-limit, timeout, parse error).
    2. JSON valid but :func:`validate_v2_brief` raises (schema invalid).
    3. Banned-token check fails: any of :data:`BANNED_BRIEFING_TOKENS`
       in ``capability_areas[*].name|description``,
       ``depth_distinction.*``, or ``non_fit_patterns[*].label|why_not``.
    4. Snake_case identifier check fails in the same set of fields.
    5. Path 3 drift: input had ``source_config.linkedin.project_id``
       but output dropped or changed it.
    6. Hallucination: average lexical overlap between
       ``capability_areas[*].description`` and ``good_looks.prose`` is
       below :data:`HALLUCINATION_OVERLAP_THRESHOLD`.
    7. Role-title drift: input had non-empty ``role.title`` but output
       dropped or changed it.

    Each cascade emits ``_emit_stage`` with ``reason=`` and route-specific
    detail so the cascade is traceable in logs. Telemetry log lines
    (start, hallucination_check, fallback, done) are documented in the
    Telemetry section of the slice plan. Routes 5 and 7 are the hard
    preservation contracts new for brief polish; the others transplant
    Thread A's pattern with brief-shaped target fields.
    """

    def __init__(
        self, fallback: HeuristicBriefPolishBackend | None = None
    ) -> None:
        self.fallback = fallback or HeuristicBriefPolishBackend()

    def polish(
        self,
        *,
        chapter_captures: dict[str, Any],
        role_title: str | None = None,
        session_id: int | None = None,
    ) -> BriefPolishResult:
        good_looks_dict = _as_dict(chapter_captures.get("good_looks"))
        lookalikes_dict = _as_dict(chapter_captures.get("lookalikes"))
        role_dict = _as_dict(chapter_captures.get("role"))
        wtl_dict = _as_dict(chapter_captures.get("where_to_look"))

        good_looks_chars = len(_as_str(good_looks_dict.get("prose")))
        exemplars_chars = len(_as_str(lookalikes_dict.get("exemplars_prose")))
        non_fit_chars = len(_as_str(lookalikes_dict.get("non_fit_prose")))
        has_role_title = bool(
            _as_str(role_dict.get("title")) or _as_str(role_title)
        )
        has_linkedin_project = bool(_as_str(wtl_dict.get("linkedin_project_id")))

        # Always emit the start line so cascade rates can be correlated
        # with input-richness during post-trial analysis.
        _emit_stage(
            f"brief.polish:start session_id={session_id} "
            f"good_looks_chars={good_looks_chars} "
            f"exemplars_chars={exemplars_chars} "
            f"non_fit_chars={non_fit_chars} "
            f"has_role_title={str(has_role_title).lower()} "
            f"has_linkedin_project={str(has_linkedin_project).lower()}"
        )

        t0 = time.monotonic()

        # The heuristic seed serves two purposes: (1) it's what we
        # fall back to on cascade, and (2) it gives the LLM a structural
        # starting point in the user prompt — including the preservation
        # contracts (role_title + source_config) the LLM is told to
        # respect verbatim.
        seeded = self.fallback.polish(
            chapter_captures=chapter_captures, role_title=role_title
        )

        # Empty captures: no point invoking the LLM with nothing to
        # polish from. Heuristic already marked source=empty.
        if seeded.source == "empty":
            elapsed_ms = int((time.monotonic() - t0) * 1000)
            _emit_stage(
                f"brief.polish:done source=empty confidence=0.00 "
                f"elapsed_ms={elapsed_ms}"
            )
            return seeded

        if not _has_llm_access():
            elapsed_ms_pre = int((time.monotonic() - t0) * 1000)
            _emit_stage(
                f"brief.polish:fallback reason=no_llm_access "
                f"elapsed_ms={elapsed_ms_pre}"
            )
            return self._cascade_done(seeded, t0)

        # Route 1: opus_llm raise.
        try:
            raw = opus_llm(
                build_brief_polish_system_prompt(),
                build_brief_polish_user_prompt(
                    chapter_captures=chapter_captures,
                    seeded_v2_draft=seeded.v2_draft,
                    role_title=role_title,
                ),
                expect_json=True,
                max_tokens=POLISH_MAX_TOKENS,
                usage_context={
                    "stage": "intake_brief_polish",
                    "session_id": session_id,
                },
            )
        except Exception as exc:
            elapsed_ms = int((time.monotonic() - t0) * 1000)
            _emit_stage(
                f"brief.polish:fallback reason=llm_raise "
                f"exc={exc.__class__.__name__} elapsed_ms={elapsed_ms}"
            )
            return self._cascade_done(seeded, t0)

        # Route 2: schema validity. We split the "not a dict" case from
        # the validate_v2_brief case so logs surface which kind of
        # malformation fired.
        if not isinstance(raw, dict):
            elapsed_ms = int((time.monotonic() - t0) * 1000)
            _emit_stage(
                f"brief.polish:fallback reason=schema_invalid "
                f"detail=not_dict elapsed_ms={elapsed_ms}"
            )
            return self._cascade_done(seeded, t0)
        try:
            validate_v2_brief(raw)
        except BriefSchemaError as exc:
            elapsed_ms = int((time.monotonic() - t0) * 1000)
            detail_keys = list(exc.missing_keys) + list(exc.invalid_keys)
            detail = ",".join(detail_keys) if detail_keys else "unknown"
            _emit_stage(
                f"brief.polish:fallback reason=schema_invalid "
                f"detail={detail} elapsed_ms={elapsed_ms}"
            )
            return self._cascade_done(seeded, t0)

        # Route 3: banned tokens (jargon recruiters shouldn't see).
        banned_hit = _banned_token_in_v2_draft(raw)
        if banned_hit is not None:
            elapsed_ms = int((time.monotonic() - t0) * 1000)
            path_label, token = banned_hit
            _emit_stage(
                f"brief.polish:fallback reason=banned_token "
                f"token={token!r} path={path_label} elapsed_ms={elapsed_ms}"
            )
            return self._cascade_done(seeded, t0)

        # Route 4: snake_case identifiers (engineer-vocab leak).
        snake_hit = _snake_case_in_v2_draft(raw)
        if snake_hit is not None:
            elapsed_ms = int((time.monotonic() - t0) * 1000)
            path_label, token = snake_hit
            _emit_stage(
                f"brief.polish:fallback reason=snake_case_token "
                f"token={token!r} path={path_label} elapsed_ms={elapsed_ms}"
            )
            return self._cascade_done(seeded, t0)

        # Route 5: Path 3 preservation. Hard contract — if the seed
        # carried a linkedin project_id, the LLM is not authorized to
        # drop or modify it.
        path3_drift = _path3_drift(seeded.v2_draft, raw)
        if path3_drift is not None:
            elapsed_ms = int((time.monotonic() - t0) * 1000)
            _emit_stage(
                f"brief.polish:fallback reason=path3_drift "
                f"detail={path3_drift} elapsed_ms={elapsed_ms}"
            )
            return self._cascade_done(seeded, t0)

        # Route 6: hallucination check. Always log overlap_avg + per-area
        # regardless of pass/fail — that's the post-trial calibration
        # data. Threshold is enforced only when good_looks.prose carries
        # content (otherwise there's nothing to ground against; the
        # empty-captures path catches the no-input case earlier).
        good_looks_prose = _as_str(good_looks_dict.get("prose"))
        overlap_avg, per_area = _capability_area_overlap(
            v2_draft=raw, good_looks_prose=good_looks_prose
        )
        per_area_str = "[" + ",".join(f"{x:.2f}" for x in per_area) + "]"
        _emit_stage(
            f"brief.polish:hallucination_check "
            f"overlap_avg={overlap_avg:.2f} "
            f"overlap_per_area={per_area_str} "
            f"threshold={HALLUCINATION_OVERLAP_THRESHOLD:.2f} "
            f"n_areas={len(per_area)}"
        )
        if good_looks_prose and overlap_avg < HALLUCINATION_OVERLAP_THRESHOLD:
            elapsed_ms = int((time.monotonic() - t0) * 1000)
            _emit_stage(
                f"brief.polish:fallback reason=hallucination "
                f"overlap_avg={overlap_avg:.2f} elapsed_ms={elapsed_ms}"
            )
            return self._cascade_done(seeded, t0)

        # Route 7: role_title preservation. Same posture as Path 3 —
        # the seed's role_title is the recruiter's word, not the LLM's
        # to rewrite.
        role_drift = _role_title_drift(
            seeded_role_title=seeded.v2_draft.get("role_title", ""),
            polished_role_title=raw.get("role_title", ""),
        )
        if role_drift:
            elapsed_ms = int((time.monotonic() - t0) * 1000)
            _emit_stage(
                f"brief.polish:fallback reason=role_title_drift "
                f"detail={role_drift} elapsed_ms={elapsed_ms}"
            )
            return self._cascade_done(seeded, t0)

        # Success: LLM produced a polished, schema-valid, in-voice,
        # path-3-preserving, non-hallucinated, role-title-preserving
        # v2_draft. Confidence is flat 1.0 for trial — see plan's
        # "Confidence formulas" subsection for the post-trial
        # calibration target.
        elapsed_ms = int((time.monotonic() - t0) * 1000)
        result = BriefPolishResult(
            v2_draft=raw,
            source="llm",
            confidence=1.0,
        )
        _emit_stage(
            f"brief.polish:done source={result.source} "
            f"confidence={result.confidence:.2f} elapsed_ms={elapsed_ms}"
        )
        return result

    def _cascade_done(
        self, seeded: BriefPolishResult, t0: float
    ) -> BriefPolishResult:
        """Emit the trailing ``done`` log for a cascade-fallback path."""

        elapsed_ms = int((time.monotonic() - t0) * 1000)
        _emit_stage(
            f"brief.polish:done source={seeded.source} "
            f"confidence={seeded.confidence:.2f} elapsed_ms={elapsed_ms}"
        )
        return seeded


# ---------------------------------------------------------------------------
# Cascade route helpers
# ---------------------------------------------------------------------------


def _scannable_text_fields(v2_draft: dict) -> list[tuple[str, str]]:
    """Yield ``(path_label, value)`` for every recruiter-facing string field.

    Scans capability areas (name + description), depth_distinction
    (three fields), non_fit_patterns (label + why_not). Excludes
    ``source_config`` and ``role_title`` because those have dedicated
    cascade routes (5 and 7); double-scanning them would surface the
    wrong route in logs.
    """

    out: list[tuple[str, str]] = []
    for idx, ca in enumerate(v2_draft.get("capability_areas") or []):
        if not isinstance(ca, dict):
            continue
        for key in ("name", "description"):
            value = ca.get(key)
            if isinstance(value, str) and value:
                out.append((f"capability_areas[{idx}].{key}", value))
    dd = v2_draft.get("depth_distinction")
    if isinstance(dd, dict):
        for key in ("builder_definition", "user_definition", "edge_case_guidance"):
            value = dd.get(key)
            if isinstance(value, str) and value:
                out.append((f"depth_distinction.{key}", value))
    for idx, nfp in enumerate(v2_draft.get("non_fit_patterns") or []):
        if not isinstance(nfp, dict):
            continue
        for key in ("label", "why_not"):
            value = nfp.get(key)
            if isinstance(value, str) and value:
                out.append((f"non_fit_patterns[{idx}].{key}", value))
    return out


def _banned_token_in_v2_draft(v2_draft: dict) -> tuple[str, str] | None:
    """First ``(path_label, token)`` hit for a banned token, else ``None``."""

    for path_label, value in _scannable_text_fields(v2_draft):
        lowered = value.lower()
        for token in BANNED_BRIEFING_TOKENS:
            if token in lowered:
                return path_label, token
    return None


def _snake_case_in_v2_draft(v2_draft: dict) -> tuple[str, str] | None:
    """First ``(path_label, token)`` hit for a snake_case identifier, else ``None``."""

    for path_label, value in _scannable_text_fields(v2_draft):
        match = SNAKE_CASE_IDENTIFIER_RE.search(value)
        if match is not None:
            return path_label, match.group(0)
    return None


def _path3_drift(seeded: dict, polished: dict) -> str | None:
    """Return drift descriptor when ``source_config.linkedin.project_id`` drifts.

    Contract: if the seeded draft (which mirrors the recruiter's intake
    state) carried a linkedin project_id, the polished output MUST carry
    the same project_id. Anything else (dropped, changed) cascades to
    Route 5. Returns ``None`` for no drift; a short string for diagnostic.
    """

    seed_li = _as_dict(_as_dict(seeded.get("source_config")).get("linkedin"))
    seed_pid = _as_str(seed_li.get("project_id"))
    if not seed_pid:
        return None
    polished_li = _as_dict(_as_dict(polished.get("source_config")).get("linkedin"))
    polished_pid = _as_str(polished_li.get("project_id"))
    if not polished_pid:
        return f"dropped seed_pid={seed_pid!r}"
    if polished_pid != seed_pid:
        return f"changed seed_pid={seed_pid!r} polished_pid={polished_pid!r}"
    return None


def _role_title_drift(
    *, seeded_role_title: Any, polished_role_title: Any
) -> str | None:
    """Return drift descriptor when seeded ``role_title`` was non-empty but polished differs."""

    seed = _as_str(seeded_role_title)
    polish = _as_str(polished_role_title)
    if not seed:
        return None
    if not polish:
        return "dropped"
    if polish != seed:
        return f"changed seed={seed!r} polished={polish!r}"
    return None


def _capability_area_overlap(
    *, v2_draft: dict, good_looks_prose: str
) -> tuple[float, list[float]]:
    """Compute lexical overlap of each capability_area description with prose.

    Returns ``(avg_overlap, per_area_overlap_list)``. Overlap is Jaccard:
    size of intersection of ≥3-char lowercased alpha tokens divided by
    union. Empty description or empty good_looks.prose => overlap=1.0
    for that area (we can't measure, so don't penalize).

    The per-area list is logged on every LLM call (see Telemetry) so
    post-trial analysis can decide between "average ≥ threshold,"
    "min ≥ threshold," or a length-weighted variant.
    """

    prose_tokens = set(_OVERLAP_TOKEN_RE.findall(good_looks_prose.lower()))
    capability_areas = v2_draft.get("capability_areas") or []

    if not prose_tokens:
        # No prose to ground against. Caller already gates this case
        # (Route 6 only enforces when good_looks_prose is non-empty);
        # this branch keeps the function total for the always-on
        # telemetry log line.
        per = [1.0 for _ in capability_areas]
        avg = 1.0 if not per else sum(per) / len(per)
        return avg, per

    per_area: list[float] = []
    for ca in capability_areas:
        if not isinstance(ca, dict):
            per_area.append(0.0)
            continue
        desc = _as_str(ca.get("description"))
        desc_tokens = set(_OVERLAP_TOKEN_RE.findall(desc.lower()))
        if not desc_tokens:
            per_area.append(1.0)
            continue
        intersection = desc_tokens & prose_tokens
        union = desc_tokens | prose_tokens
        per_area.append(len(intersection) / len(union) if union else 0.0)
    avg = sum(per_area) / len(per_area) if per_area else 1.0
    return avg, per_area


# ---------------------------------------------------------------------------
# Type-coercion helpers — defensive against state_json drift
# ---------------------------------------------------------------------------


def _as_dict(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


def _as_str(value: Any) -> str:
    if isinstance(value, str):
        return value
    if value is None:
        return ""
    # Defensive on numeric/bool: stringify so e.g. a project_id stored
    # as int still resolves to a non-empty string. Mirrors the
    # backward-compat coercion in
    # :func:`shared.brief_v2_schema.linkedin_project_id_from_brief`.
    return str(value)


def _as_str_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [v for v in value if isinstance(v, str) and v]


# ---------------------------------------------------------------------------
# Prompt builders
# ---------------------------------------------------------------------------


def build_brief_polish_system_prompt() -> str:
    """System prompt for the brief polish step.

    SOURCE OF TRUTH: ``docs/cloris-surface-design-rules.md`` R18 + R21
    (mirror of :func:`market_intelligence.research_prompts.build_briefing_polish_system_prompt`,
    which last verified on 2026-05-03). When updating this prompt,
    re-read the rules doc and update the date.

    Encodes voice rules (recruiter-readable, no engineer vocab, no
    snake_case), schema output spec (V2 brief shape), preservation
    contracts (role_title + source_config), the hallucination guard
    (overlap with good_looks.prose), and honesty about gaps.
    """

    return """You are Cloris's editorial voice. You read raw intake captures from a recruiter and reshape them into a polished, schema-correct V2 brief draft.

VOICE RULES (from docs/cloris-surface-design-rules.md R18 + R21):
- Recruiter-readable register. No engineer vocabulary, no snake_case identifiers, no internal jargon. The recruiter has never read the engine source code; they should never see its words.
- Calm, plain, editorial. Not shouty, not hypey, not "AI-native." This is a brief, not a dashboard.
- Operational copy and voice copy never overlap. Brief content is operational — clean, declarative, recruiter-readable. Don't write character voice into capability descriptions.

SCHEMA — return JSON ONLY with this exact shape:
{
  "role_title": "<string from input role.title — preserve exactly>",
  "capability_areas": [
    {"name": "<short editorial name, no snake_case>", "description": "<1-3 sentences grounded in the recruiter's good_looks.prose>"}
  ],
  "depth_distinction": {
    "builder_definition": "<what 'building it' looks like — 1-3 sentences, or empty string if the captures don't support a confident answer>",
    "user_definition": "<what 'using it' looks like — 1-3 sentences, or empty string>",
    "edge_case_guidance": "<edge cases and borderline calls — 1-3 sentences, or empty string>"
  },
  "non_fit_patterns": [
    {"label": "<short editorial label>", "why_not": "<1-2 sentences grounded in lookalikes.non_fit_prose>"}
  ],
  "target_modules": ["linkedin", ...],
  "source_config": {"linkedin": {"project_id": "<from input — preserve exactly>", "project_name": "<from input — preserve exactly>"}}
}

PRESERVATION RULES (HARD CONTRACTS — output is rejected and the recruiter's scaffolded draft is shown instead if you violate these):
- If the input contains `seeded_v2_draft.role_title` (non-empty), the output `role_title` MUST equal it character-for-character. Do not "improve" the title.
- If the input contains `seeded_v2_draft.source_config.linkedin.project_id`, the output `source_config.linkedin.project_id` MUST equal it. Do not invent, drop, or modify it. The same applies to `project_name` if present.
- The output `target_modules` SHOULD equal `seeded_v2_draft.target_modules` unless the recruiter explicitly mentioned other surfaces in `chapter_captures.where_to_look.anything_else`.

HALLUCINATION GUARD:
- Reformat / reorganize / tighten the recruiter's words into clean capability areas and depth definitions. Do NOT invent capability areas the recruiter didn't write about.
- Each `capability_areas[*].description` MUST share substantial vocabulary with `chapter_captures.good_looks.prose`. If you can't ground a description in the recruiter's prose, do not include that capability area.
- Better to ship 2 capability areas grounded in the recruiter's prose than 5 areas you partially invented.

HONESTY ABOUT GAPS:
- If the recruiter wrote a thin capture, the polished output is honest about gaps. Don't paper over with fabricated content.
- Empty depth_distinction fields (`""`) are FINE if the captures don't support a confident answer. Do NOT make up depth definitions to fill the schema.
- An empty `non_fit_patterns: []` is FINE if `chapter_captures.lookalikes.non_fit_prose` is empty.

BANNED TOKENS (engineer jargon — never let these appear in any output field):
- hypothesis, tracking, lane_key, planner, critic, artifact
- Any snake_case identifier (matches `[a-z]+(?:_[a-z]+)+`). Translate to readable form: write "forward-deployed engineering" not "forward_deployed_engineering"; write "ML platform" not "ml_platform".

Return JSON ONLY. No prose preamble, no closing remark, no markdown code fences."""


def build_brief_polish_user_prompt(
    *,
    chapter_captures: dict[str, Any],
    seeded_v2_draft: dict[str, Any],
    role_title: str | None = None,
) -> str:
    """User prompt: structured input the polish call grounds itself in.

    Pass-through of the recruiter's chapter captures plus the heuristic
    seed. The seed gives the LLM a structural starting point and the
    preservation contracts (role_title, source_config). The captures
    are the ground truth for the hallucination guard.
    """

    role = _as_dict(chapter_captures.get("role"))
    good_looks = _as_dict(chapter_captures.get("good_looks"))
    lookalikes = _as_dict(chapter_captures.get("lookalikes"))
    where_to_look = _as_dict(chapter_captures.get("where_to_look"))

    payload = {
        "chapter_captures": {
            "role": {
                "title": _as_str(role.get("title")) or _as_str(role_title),
                "framing": _as_str(role.get("framing")),
            },
            "good_looks": {
                "prose": _as_str(good_looks.get("prose")),
            },
            "lookalikes": {
                "exemplars_prose": _as_str(lookalikes.get("exemplars_prose")),
                "non_fit_prose": _as_str(lookalikes.get("non_fit_prose")),
            },
            "where_to_look": {
                "target_modules": _as_str_list(where_to_look.get("target_modules")),
                "linkedin_project_id": _as_str(
                    where_to_look.get("linkedin_project_id")
                ),
                "linkedin_project_name": _as_str(
                    where_to_look.get("linkedin_project_name")
                ),
                "anything_else": _as_str(where_to_look.get("anything_else")),
            },
        },
        "seeded_v2_draft": seeded_v2_draft,
    }

    return (
        "Reshape the recruiter's intake captures into a polished V2 brief draft.\n\n"
        "INPUT (structured — preserve identity fields exactly; ground capability "
        "areas in good_looks.prose):\n"
        f"{json.dumps(payload, indent=2)}\n\n"
        "Return JSON only matching the schema in the system prompt."
    )


# Re-export `_normalize_text` so tests of this module can use it without
# reaching into `briefing_polish` directly. Kept as a private alias.
__all__ = (
    "BANNED_BRIEFING_TOKENS",
    "BriefPolishBackend",
    "BriefPolishResult",
    "HALLUCINATION_OVERLAP_THRESHOLD",
    "HEURISTIC_CONFIDENCE_DENOMINATOR",
    "HeuristicBriefPolishBackend",
    "MIN_SUBSTANTIVE_CHARS",
    "POLISH_MAX_TOKENS",
    "SNAKE_CASE_IDENTIFIER_RE",
    "build_brief_polish_system_prompt",
    "build_brief_polish_user_prompt",
)
