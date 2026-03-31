"""Regression tests for shared.bias_controls save semantics."""

from shared.bias_controls import (
    AlertType,
    BiasMonitor,
    DecisionRecord,
    is_save_decision,
)


def _full_decision(decision: str, string_id: str = "s1", candidate_id: str = "c1") -> DecisionRecord:
    return DecisionRecord(
        candidate_id=candidate_id,
        string_id=string_id,
        stage="full",
        decision=decision,
        confidence=0.8,
        capability_area=None,
    )


def test_signal_save_counts_as_save():
    assert is_save_decision("SIGNAL_SAVE") is True


def test_signal_save_triggers_consecutive_save_alert():
    monitor = BiasMonitor(max_consecutive_saves=2)
    monitor.record_decision(_full_decision("SAVE", candidate_id="c1"))
    monitor.record_decision(_full_decision("SIGNAL_SAVE", candidate_id="c2"))

    alerts = monitor.check_alerts("s1")

    assert any(alert.alert_type == AlertType.CONSECUTIVE_SAVES for alert in alerts)


def test_signal_save_counts_in_save_rate_and_summary():
    monitor = BiasMonitor(save_rate_spike_window=3, save_rate_spike_threshold=2 / 3)
    monitor.record_decision(_full_decision("SAVE", candidate_id="c1"))
    monitor.record_decision(_full_decision("SIGNAL_SAVE", candidate_id="c2"))
    monitor.record_decision(_full_decision("REJECT", candidate_id="c3"))

    alerts = monitor.check_alerts("s1")
    summary = monitor.session_summary()

    assert any(alert.alert_type == AlertType.SAVE_RATE_SPIKE for alert in alerts)
    assert summary["saves"] == 2
    assert summary["per_string"]["s1"]["saves"] == 2
