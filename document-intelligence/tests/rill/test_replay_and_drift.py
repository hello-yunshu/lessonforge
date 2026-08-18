from __future__ import annotations

from document_intelligence.rill.drift import ShadowDriftMonitor


def test_drift_monitor_is_bounded_and_resettable(tmp_path) -> None:
    monitor = ShadowDriftMonitor(tmp_path, min_samples=5, threshold=0.2, delta=0)
    alert = None
    for value in [False, False, False, False, True, True, True]:
        state, candidate = monitor.update(error=value)
        alert = candidate or alert
    assert len(state.recent_errors) <= 100
    assert alert is not None
    restored = ShadowDriftMonitor(tmp_path, min_samples=5, threshold=0.2, delta=0).read()
    assert restored.sample_count == state.sample_count
    reset = monitor.reset()
    assert reset.sample_count == 0
    assert reset.state_generation > state.state_generation


def test_drift_alert_identity_binds_threshold_and_detects_tampering(tmp_path) -> None:
    from pathlib import Path

    import json
    import pytest

    from document_intelligence.exceptions import RillStoreCorruptError

    first = ShadowDriftMonitor(tmp_path, min_samples=2, threshold=0.1, delta=0)
    alert = None
    for value in [False, True, True]:
        _, candidate = first.update(error=value)
        alert = candidate or alert
    assert alert is not None

    other = ShadowDriftMonitor(tmp_path / "other", min_samples=2, threshold=0.2, delta=0)
    other_alert = None
    for value in [False, True, True]:
        _, candidate = other.update(error=value)
        other_alert = candidate or other_alert
    assert other_alert is not None
    assert other_alert.alert_id != alert.alert_id

    path = Path(tmp_path) / "rill-shadow" / "drift" / "alerts" / f"{alert.alert_id}.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["alert"]["threshold"] = 9.0
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(RillStoreCorruptError):
        first.list_alerts()
