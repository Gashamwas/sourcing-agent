"""Shared failure semantics for judgment and runtime retry decisions."""

from __future__ import annotations

from dataclasses import dataclass

from shared.contracts import FAILURE_DECISIONS as CONTRACT_FAILURE_DECISIONS
from shared.schemas import OpusDecision

PARSE_FAILURE = "PARSE_FAILURE"
JUDGMENT_FAILURE = "JUDGMENT_FAILURE"

RECOVERABLE_ERROR = "RECOVERABLE_ERROR"
TERMINAL_ERROR = "TERMINAL_ERROR"

FAILURE_DECISIONS = CONTRACT_FAILURE_DECISIONS
RETRYABLE_STATUS_CODES = frozenset({408, 409, 425, 429, 500, 502, 503, 504, 529})

_RECOVERABLE_PATTERNS: tuple[tuple[str, str, str], ...] = (
    ("rate_limit", "provider", "rate_limit"),
    ("rate limit", "provider", "rate_limit"),
    ("429", "provider", "http_429"),
    ("502", "provider", "http_502"),
    ("503", "provider", "http_503"),
    ("504", "provider", "http_504"),
    ("529", "provider", "http_529"),
    ("overloaded", "provider", "capacity"),
    ("capacity", "provider", "capacity"),
    ("timeout", "network", "timeout"),
    ("timed out", "network", "timeout"),
    ("connection reset", "network", "connection_reset"),
    ("connection closed", "network", "connection_closed"),
    ("connection aborted", "network", "connection_aborted"),
    ("target crashed", "browser", "browser_disconnect"),
    ("target closed", "browser", "browser_disconnect"),
    ("page closed", "browser", "browser_disconnect"),
    ("context closed", "browser", "browser_disconnect"),
    ("session closed", "browser", "browser_disconnect"),
    ("browser has been closed", "browser", "browser_disconnect"),
    ("cannot get world", "browser", "browser_disconnect"),
)

_TERMINAL_PATTERNS: tuple[tuple[str, str, str], ...] = (
    ("stop_reason=", "provider", "truncated_response"),
    ("invalid api key", "auth", "invalid_api_key"),
    ("authentication", "auth", "authentication_failed"),
    ("permission denied", "auth", "permission_denied"),
    ("forbidden", "auth", "forbidden"),
    ("unsupported", "request", "unsupported_request"),
)


@dataclass(frozen=True)
class FailureClassification:
    kind: str
    domain: str
    reason: str
    detail: str = ""
    status_code: int | None = None

    @property
    def retryable(self) -> bool:
        return self.kind == RECOVERABLE_ERROR


def is_failure_decision(decision: str) -> bool:
    """True if decision represents a non-terminal parse or judgment failure."""
    return decision in FAILURE_DECISIONS


def classify_runtime_failure(exc: Exception, source: str = "runtime") -> FailureClassification:
    """Classify an exception into shared retry semantics."""
    detail = _clip_detail(str(exc) or exc.__class__.__name__)
    status_code = _coerce_status_code(getattr(exc, "status_code", None))
    lowered = detail.lower()

    if status_code in RETRYABLE_STATUS_CODES:
        return FailureClassification(
            kind=RECOVERABLE_ERROR,
            domain="provider",
            reason=f"http_{status_code}",
            detail=detail,
            status_code=status_code,
        )

    if status_code in {400, 401, 403, 404, 422}:
        return FailureClassification(
            kind=TERMINAL_ERROR,
            domain="provider",
            reason=f"http_{status_code}",
            detail=detail,
            status_code=status_code,
        )

    for pattern, domain, reason in _TERMINAL_PATTERNS:
        if pattern in lowered:
            return FailureClassification(
                kind=TERMINAL_ERROR,
                domain=domain,
                reason=reason,
                detail=detail,
                status_code=status_code,
            )

    if isinstance(exc, (TimeoutError, ConnectionError)):
        return FailureClassification(
            kind=RECOVERABLE_ERROR,
            domain="network",
            reason="timeout" if isinstance(exc, TimeoutError) else "connection_error",
            detail=detail,
            status_code=status_code,
        )

    for pattern, domain, reason in _RECOVERABLE_PATTERNS:
        if pattern in lowered:
            return FailureClassification(
                kind=RECOVERABLE_ERROR,
                domain=domain,
                reason=reason,
                detail=detail,
                status_code=status_code,
            )

    return FailureClassification(
        kind=TERMINAL_ERROR,
        domain=source,
        reason="unclassified",
        detail=detail,
        status_code=status_code,
    )


def format_failure_rationale(
    decision: str,
    classification: FailureClassification | None = None,
    detail: str = "",
) -> str:
    """Build a stable rationale string for failure decisions."""
    clipped_detail = _clip_detail(detail)
    if not classification:
        return f"[{decision}: {clipped_detail}]"

    status_suffix = ""
    if classification.status_code is not None:
        status_suffix = f" status={classification.status_code}"

    meta = (
        f"{classification.kind.lower()}/"
        f"{classification.domain}/"
        f"{classification.reason}"
        f"{status_suffix}"
    )
    if clipped_detail:
        return f"[{decision}: {meta}] {clipped_detail}"
    return f"[{decision}: {meta}]"


def judgment_failure_decision(
    stage: str,
    candidate_name: str,
    profile_url: str,
    error: Exception,
    path: str = "none",
    source: str = "judgment",
) -> OpusDecision:
    """Build a standardized JUDGMENT_FAILURE decision."""
    classification = classify_runtime_failure(error, source=source)
    return OpusDecision(
        stage=stage,
        decision=JUDGMENT_FAILURE,
        path=path,
        confidence=0.0,
        rationale=format_failure_rationale(
            JUDGMENT_FAILURE,
            classification=classification,
            detail=str(error),
        ),
        candidate_name=candidate_name,
        profile_url=profile_url,
    )


def parse_failure_decision(
    stage: str,
    candidate_name: str,
    profile_url: str,
    detail: str,
    reason: str = "parse_error",
    path: str = "none",
) -> OpusDecision:
    """Build a standardized PARSE_FAILURE decision."""
    classification = FailureClassification(
        kind=TERMINAL_ERROR,
        domain="parse",
        reason=reason,
        detail=_clip_detail(detail),
    )
    return OpusDecision(
        stage=stage,
        decision=PARSE_FAILURE,
        path=path,
        confidence=0.0,
        rationale=format_failure_rationale(
            PARSE_FAILURE,
            classification=classification,
            detail=detail,
        ),
        candidate_name=candidate_name,
        profile_url=profile_url,
    )


def _coerce_status_code(value: object) -> int | None:
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None


def _clip_detail(detail: str, limit: int = 240) -> str:
    cleaned = (detail or "").strip()
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 3] + "..."
