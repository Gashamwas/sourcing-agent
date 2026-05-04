"""Project-quality sub-index for OSS Maintainers Slice 5.

Per OSS Maintainers Module Spec §11, when a recruiter does NOT name
explicit ``target_projects``, Cloris still needs a way to distinguish
"maintainer of a critical project" from "maintainer of a stars-but-
no-substance project." This module produces a per-project quality
score from GitHub-derivable signals only (no registry adapters —
those land in Phase 3 follow-ups per spec §16).

Signals (each weighted into a composite score in [0, 1]):

1. **Downstream dependents** — count from
   :mod:`github.network_dependents` HTML scrape, log-scaled.
2. **Release cadence regularity** — derived from ``/releases``;
   regular cadence scores higher than burst.
3. **Contributor diversity** — distinct contributor count from
   ``/contributors``, log-scaled.
4. **Age × sustained activity** — repo age in years × (recent commit
   activity normalized).
5. **OpenSSF Criticality Score snapshot** — local lookup from a
   weekly-refreshed CSV (per spec §9). Authoritative when present;
   absence does not penalize.

Per spec §12: ``target_projects`` overrides the sub-index. Named
projects skip prestige scoring. The sub-index exists for the
unnamed-project path: once a maintainership signal lands on a
candidate without a recruiter-named project, this score helps the
evaluator decide whether the project itself is load-bearing.

Failure-mode posture: every signal is fail-soft per spec §12. A
network failure on dependents returns ``None`` for that signal; the
composite score weights what's available and reports
``signals["unavailable"]`` listing the dropped ones.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from github import maintainer_signal_cache as mcache
from github import network_dependents
from github.client import GitHubClient
from github.ossf_criticality import lookup_criticality_score

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public types
# ---------------------------------------------------------------------------


@dataclass
class ProjectQualityScore:
    """Composite quality assessment for an ``owner/repo``.

    ``score`` is a normalized composite in ``[0, 1]``. ``signals``
    carries the per-signal contributions for debugging and per-
    signal-contribution analysis at the calibration layer.
    ``criticality_band`` is a recruiter-readable band derived from
    ``score``: ``niche`` (< 0.33), ``established`` (0.33 - 0.66),
    ``critical`` (>= 0.66).
    """

    owner: str
    repo: str
    score: float
    criticality_band: str
    signals: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "owner": self.owner,
            "repo": self.repo,
            "score": self.score,
            "criticality_band": self.criticality_band,
            "signals": dict(self.signals),
        }


# ---------------------------------------------------------------------------
# Signal weights — first-pass; tunable post-trial.
# ---------------------------------------------------------------------------


SIGNAL_WEIGHTS: dict[str, float] = {
    "ossf_criticality": 1.5,            # authoritative when present
    "downstream_dependents": 1.2,
    "contributor_diversity": 0.8,
    "release_cadence": 0.6,
    "age_x_activity": 0.4,
}


BAND_THRESHOLDS: dict[str, float] = {
    "critical": 0.66,
    "established": 0.33,
    # Below `established` is `niche`.
}


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


async def score_project(
    owner: str,
    repo: str,
    client: GitHubClient,
) -> ProjectQualityScore:
    """Score a project's quality from GitHub-derivable signals.

    All signals are fail-soft: a fetch failure drops that signal
    from the composite (recorded in ``signals["unavailable"]``)
    rather than aborting the score.
    """

    signals: dict[str, Any] = {}
    unavailable: list[str] = []

    # 1. OSSF Criticality (authoritative, cheap snapshot lookup).
    criticality = lookup_criticality_score(owner, repo)
    if criticality is None:
        unavailable.append("ossf_criticality")
        signals["ossf_criticality"] = 0.0
    else:
        signals["ossf_criticality_raw"] = criticality
        signals["ossf_criticality"] = criticality

    # 2. Downstream dependents (HTML scrape; cached 30d).
    dep_count = await network_dependents.fetch_dependents_count(
        owner, repo, throttle_seconds=0.0
    )
    if dep_count is None:
        unavailable.append("downstream_dependents")
        signals["downstream_dependents"] = 0.0
    else:
        signals["downstream_dependents_raw"] = dep_count
        # log10 scale: 1 dependent → ~0; 10 → 0.2; 100 → 0.4; 1k →
        # 0.6; 10k → 0.8; 100k+ → ~1.0.
        signals["downstream_dependents"] = _log_scale(dep_count, max_log=5.0)

    # 3. Contributor diversity (existing /contributors endpoint;
    # cached as part of broader github enrichment, but we issue a
    # fresh call here to avoid coupling to enrichment ordering).
    contributor_count = await _safe_contributor_count(client, owner, repo)
    if contributor_count is None:
        unavailable.append("contributor_diversity")
        signals["contributor_diversity"] = 0.0
    else:
        signals["contributor_diversity_raw"] = contributor_count
        # log10 scale: 1 contributor → 0; 10 → 0.33; 100 → 0.67;
        # 1k+ → ~1.0.
        signals["contributor_diversity"] = _log_scale(contributor_count, max_log=3.0)

    # 4. Release cadence regularity (derived from /releases via the
    # maintainer-signal cache or a fresh call).
    cadence_score, cadence_raw = await _release_cadence(client, owner, repo)
    if cadence_score is None:
        unavailable.append("release_cadence")
        signals["release_cadence"] = 0.0
    else:
        signals["release_cadence"] = cadence_score
        signals["release_cadence_raw"] = cadence_raw

    # 5. Age × sustained activity (repo age × recent activity).
    age_activity = await _age_x_activity(client, owner, repo)
    if age_activity is None:
        unavailable.append("age_x_activity")
        signals["age_x_activity"] = 0.0
    else:
        signals["age_x_activity"] = age_activity

    # Aggregate. Weights sum nominally, but unavailable signals
    # contribute zero — the score is the available-signal-weighted-
    # average normalized by the SUM of available weights. That way
    # a project with only OSSF + dependents data scores fairly
    # without being penalized by missing release info.
    total_weight = 0.0
    weighted_sum = 0.0
    for name, weight in SIGNAL_WEIGHTS.items():
        if name in unavailable:
            continue
        total_weight += weight
        weighted_sum += weight * float(signals.get(name, 0.0))

    if total_weight > 0:
        score = round(min(weighted_sum / total_weight, 1.0), 3)
    else:
        # All signals unavailable — return zero. Recruiter sees a
        # niche band; the orchestrator can decide whether to retry.
        score = 0.0

    if unavailable:
        signals["unavailable"] = unavailable

    return ProjectQualityScore(
        owner=owner,
        repo=repo,
        score=score,
        criticality_band=_band_for(score),
        signals=signals,
    )


# ---------------------------------------------------------------------------
# Signal helpers
# ---------------------------------------------------------------------------


async def _safe_contributor_count(
    client: GitHubClient, owner: str, repo: str
) -> Optional[int]:
    try:
        contributors = await client.get_repo_contributors(f"{owner}/{repo}")
    except Exception as exc:  # noqa: BLE001 — fail-soft per spec §12
        logger.warning("contributors fetch failed for %s/%s: %s", owner, repo, exc)
        return None
    return len(contributors) if isinstance(contributors, list) else None


async def _release_cadence(
    client: GitHubClient,
    owner: str,
    repo: str,
) -> tuple[Optional[float], dict[str, Any]]:
    """Return ``(cadence_score, raw_metadata)``.

    Cadence score in ``[0, 1]``: regular releases (low gap variance)
    score higher than burst-then-silence. Raw metadata records the
    release count, mean gap days, and gap stddev so the calibration
    layer can audit per-signal contribution.
    """

    cached = mcache.get(owner, repo, "releases")
    releases: Optional[list[dict]]
    if cached is not None and isinstance(cached.data, list):
        releases = cached.data
    else:
        try:
            releases = await client.list_repo_releases(f"{owner}/{repo}")
        except Exception as exc:  # noqa: BLE001 — fail-soft per spec §12
            logger.warning("releases fetch failed for %s/%s: %s", owner, repo, exc)
            return None, {}
        if releases is not None:
            mcache.put(owner, repo, "releases", releases)
    if not isinstance(releases, list):
        return None, {}

    timestamps: list[datetime] = []
    for release in releases:
        published = release.get("published_at")
        if not isinstance(published, str):
            continue
        try:
            ts = datetime.fromisoformat(published.replace("Z", "+00:00"))
        except ValueError:
            continue
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        timestamps.append(ts)

    if len(timestamps) < 2:
        # Not enough releases to derive cadence; treat as low.
        return 0.0, {"release_count": len(timestamps)}

    timestamps.sort()
    gaps_days = [
        (timestamps[i] - timestamps[i - 1]).days
        for i in range(1, len(timestamps))
    ]
    gaps_days = [g for g in gaps_days if g >= 0]
    if not gaps_days:
        return 0.0, {"release_count": len(timestamps)}
    mean_gap = sum(gaps_days) / len(gaps_days)
    variance = sum((g - mean_gap) ** 2 for g in gaps_days) / len(gaps_days)
    stddev = math.sqrt(variance)
    # Regularity: low coefficient-of-variation maps to high score.
    cv = stddev / mean_gap if mean_gap > 0 else 0.0
    # Score: 1.0 at cv=0; 0.0 at cv >= 1.5.
    score = max(0.0, 1.0 - min(cv / 1.5, 1.0))
    raw = {
        "release_count": len(timestamps),
        "mean_gap_days": round(mean_gap, 1),
        "gap_stddev_days": round(stddev, 1),
    }
    return round(score, 3), raw


async def _age_x_activity(
    client: GitHubClient,
    owner: str,
    repo: str,
) -> Optional[float]:
    """Composite of repo age (years) and recent commit activity.

    Returns ``[0, 1]``. The product saturates: a 10-year-old repo
    with sustained activity scores high; a 6-month-old repo with
    intense activity scores moderate; a 10-year-old repo with no
    recent activity scores low.
    """

    try:
        repo_data = await client.get_repo(f"{owner}/{repo}")
    except Exception as exc:  # noqa: BLE001 — fail-soft per spec §12
        logger.warning("get_repo failed for %s/%s: %s", owner, repo, exc)
        return None
    if not isinstance(repo_data, dict):
        return None

    created_at = repo_data.get("created_at")
    pushed_at = repo_data.get("pushed_at")
    if not isinstance(created_at, str) or not isinstance(pushed_at, str):
        return None
    try:
        created = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        pushed = datetime.fromisoformat(pushed_at.replace("Z", "+00:00"))
    except ValueError:
        return None
    if created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    if pushed.tzinfo is None:
        pushed = pushed.replace(tzinfo=timezone.utc)

    now = datetime.now(timezone.utc)
    age_years = (now - created).days / 365.0
    days_since_push = (now - pushed).days

    # Age score saturates at 10 years.
    age_score = min(age_years / 10.0, 1.0)
    # Activity score: 1.0 if pushed within 30 days; 0.0 if > 365.
    if days_since_push <= 30:
        activity_score = 1.0
    elif days_since_push >= 365:
        activity_score = 0.0
    else:
        activity_score = 1.0 - (days_since_push - 30) / 335.0

    return round(age_score * activity_score, 3)


def _log_scale(value: int, *, max_log: float) -> float:
    """log10-scaled normalization to [0, 1].

    ``max_log`` is the log10 value where the scale saturates at 1.0.
    E.g. ``max_log=3`` means count=1000 → score 1.0; count=10 → 0.33.
    """

    if value <= 0:
        return 0.0
    log_val = math.log10(value)
    return round(min(log_val / max_log, 1.0), 3)


def _band_for(score: float) -> str:
    if score >= BAND_THRESHOLDS["critical"]:
        return "critical"
    if score >= BAND_THRESHOLDS["established"]:
        return "established"
    return "niche"
