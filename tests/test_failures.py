from __future__ import annotations

from unittest.mock import patch

from shared.failures import (
    ApiBudgetExhaustedError,
    JUDGMENT_FAILURE,
    PARSE_FAILURE,
    RECOVERABLE_ERROR,
    TERMINAL_ERROR,
    classify_runtime_failure,
    is_api_budget_exhausted_error,
    judgment_failure_decision,
    parse_failure_decision,
)
from shared.llm_clients import _retry_with_backoff


class _StatusError(RuntimeError):
    def __init__(self, message: str, status_code: int):
        super().__init__(message)
        self.status_code = status_code


def test_classify_retryable_provider_status_code():
    classification = classify_runtime_failure(_StatusError("overloaded", 503), source="llm")
    assert classification.kind == RECOVERABLE_ERROR
    assert classification.domain == "provider"
    assert classification.reason == "http_503"
    assert classification.retryable is True


def test_classify_terminal_truncated_response():
    classification = classify_runtime_failure(
        RuntimeError("Opus response truncated: stop_reason=max_tokens"),
        source="llm",
    )
    assert classification.kind == TERMINAL_ERROR
    assert classification.domain == "provider"
    assert classification.reason == "truncated_response"
    assert classification.retryable is False


def test_classify_api_budget_exhausted_before_generic_http_400():
    exc = _StatusError(
        "Your credit balance is too low to access the Anthropic API. "
        "Please go to Plans & Billing to upgrade or purchase credits.",
        400,
    )

    classification = classify_runtime_failure(exc, source="llm")

    assert classification.kind == TERMINAL_ERROR
    assert classification.domain == "provider"
    assert classification.reason == "api_budget_exhausted"
    assert classification.retryable is False
    assert is_api_budget_exhausted_error(exc) is True
    assert is_api_budget_exhausted_error(ApiBudgetExhaustedError("credits exhausted")) is True


def test_classify_retryable_browser_disconnect():
    classification = classify_runtime_failure(
        RuntimeError("Target closed while reading browser page"),
        source="browser",
    )
    assert classification.kind == RECOVERABLE_ERROR
    assert classification.domain == "browser"
    assert classification.reason == "browser_disconnect"


def test_judgment_failure_decision_includes_shared_classification():
    decision = judgment_failure_decision(
        stage="full",
        candidate_name="Test Person",
        profile_url="/profile/test",
        error=_StatusError("provider overloaded", 503),
        source="judgment",
    )
    assert decision.decision == JUDGMENT_FAILURE
    assert decision.confidence == 0.0
    assert "recoverable_error/provider/http_503" in decision.rationale


def test_parse_failure_decision_includes_shared_classification():
    decision = parse_failure_decision(
        stage="facial",
        candidate_name="Test Person",
        profile_url="/profile/test",
        reason="invalid_decision",
        detail="decision='YOLO'",
    )
    assert decision.decision == PARSE_FAILURE
    assert decision.confidence == 0.0
    assert "terminal_error/parse/invalid_decision" in decision.rationale
    assert "decision='YOLO'" in decision.rationale


def test_retry_with_backoff_retries_recoverable_error():
    attempts = {"count": 0}

    def flaky_call():
        attempts["count"] += 1
        if attempts["count"] < 3:
            raise _StatusError("provider overloaded", 503)
        return "ok"

    with patch("shared.llm_clients.random.uniform", return_value=0.0), patch("shared.llm_clients.time.sleep") as sleep:
        result = _retry_with_backoff(flaky_call, label="test")

    assert result == "ok"
    assert attempts["count"] == 3
    assert sleep.call_count == 2


def test_retry_with_backoff_does_not_retry_terminal_error():
    attempts = {"count": 0}

    def truncated_call():
        attempts["count"] += 1
        raise RuntimeError("Opus response truncated: stop_reason=max_tokens")

    with patch("shared.llm_clients.random.uniform", return_value=0.0), patch("shared.llm_clients.time.sleep") as sleep:
        try:
            _retry_with_backoff(truncated_call, label="test")
        except RuntimeError as exc:
            assert "stop_reason=max_tokens" in str(exc)
        else:
            raise AssertionError("expected RuntimeError")

    assert attempts["count"] == 1
    assert sleep.call_count == 0
