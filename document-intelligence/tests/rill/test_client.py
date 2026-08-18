from __future__ import annotations

import sys
from pathlib import Path

from document_intelligence.rill.client import SubprocessRillClient
from document_intelligence.rill.models import (
    ACTION_TO_ARM,
    ParseSignals,
    PolicySuggestion,
    RillObserveEvent,
    ShadowAction,
    ShadowSignals,
)


def event() -> RillObserveEvent:
    return RillObserveEvent(
        event_id="observe-test",
        parse_run_id="run-test",
        parser_id="fixture",
        signals=ShadowSignals(parse=ParseSignals(
            page_count=1, element_count=1, average_confidence=0.9,
            minimum_confidence=0.9, p0_warnings=0, p1_warnings=0,
            p2_warnings=0, duration_ms=1, estimated_cost_usd=0,
        )),
    )


def test_subprocess_client_matches_real_ipc_v3_and_duplicate_feedback_is_idempotent() -> None:
    schema_hash = "a" * 64
    script = Path(__file__).with_name("fake_runtime.py")
    client = SubprocessRillClient(
        [sys.executable, str(script), schema_hash],
        feature_schema_hash=schema_hash,
        request_timeout_seconds=2,
        startup_timeout_seconds=2,
    )
    try:
        assert client.health()
        item = event()
        static = PolicySuggestion(
            decision_id="static-1", action=ShadowAction.HUMAN_REVIEW,
            selected_arm=ACTION_TO_ARM[ShadowAction.HUMAN_REVIEW],
            policy_version="static", confidence=1,
            reason_codes=["TEST"], source="static_policy",
        )
        client.observe(item)
        suggestion = client.decide(item, static_suggestion=static, deterministic_seed=1)
        assert suggestion.action == ShadowAction.HUMAN_REVIEW
        client.feedback(
            decision_id=suggestion.decision_id,
            selected_arm=suggestion.selected_arm,
            reward=1,
            outcome_time_ms=1,
            generation=suggestion.state_generation,
        )
        # Runtime returns duplicateFeedback; host treats this as an idempotent success.
        client.feedback(
            decision_id=suggestion.decision_id,
            selected_arm=suggestion.selected_arm,
            reward=1,
            outcome_time_ms=1,
            generation=suggestion.state_generation,
        )
        snapshot = client.snapshot()
        assert snapshot.state_checksum
        assert client.inspect()["shadowOnly"] is True
    finally:
        client.close()


def test_subprocess_client_verifies_runtime_binary_digest() -> None:
    import hashlib
    import pytest
    from document_intelligence.exceptions import RillUnavailableError

    schema_hash = "b" * 64
    script = Path(__file__).with_name("fake_runtime.py")
    executable = Path(sys.executable).resolve()
    digest = hashlib.sha256(executable.read_bytes()).hexdigest()
    client = SubprocessRillClient(
        [sys.executable, str(script), schema_hash],
        feature_schema_hash=schema_hash,
        expected_runtime_sha256=digest,
        request_timeout_seconds=2,
        startup_timeout_seconds=2,
    )
    client.close()
    with pytest.raises(RillUnavailableError):
        SubprocessRillClient(
            [sys.executable, str(script), schema_hash],
            feature_schema_hash=schema_hash,
            expected_runtime_sha256="0" * 64,
            request_timeout_seconds=2,
            startup_timeout_seconds=2,
        )
