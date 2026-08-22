from __future__ import annotations

import sys
from pathlib import Path

import pytest

from document_intelligence.exceptions import RillProtocolError, RillUnavailableError
from document_intelligence.rill.models import (
    ACTION_TO_ARM,
    ParseSignals,
    PolicySuggestion,
    RillObserveEvent,
    ShadowAction,
    ShadowSignals,
)
from document_intelligence.rill.stable_client import StableV2RillClient


def event() -> RillObserveEvent:
    return RillObserveEvent(
        event_id="stable-v2-event",
        parse_run_id="stable-v2-run",
        parser_id="fixture",
        signals=ShadowSignals(
            parse=ParseSignals(
                page_count=1,
                element_count=1,
                average_confidence=0.9,
                minimum_confidence=0.9,
                p0_warnings=0,
                p1_warnings=0,
                p2_warnings=0,
                duration_ms=1,
                estimated_cost_usd=0,
            )
        ),
    )


def static() -> PolicySuggestion:
    return PolicySuggestion(
        decision_id="stable-v2-static",
        action=ShadowAction.ACCEPT,
        selected_arm=ACTION_TO_ARM[ShadowAction.ACCEPT],
        policy_version="static",
        confidence=1,
        reason_codes=["TEST"],
        source="static_policy",
    )


def command(*args: str) -> list[str]:
    return [sys.executable, str(Path(__file__).with_name("fake_runtime_v2.py")), *args]


def test_stable_v2_handshake_health_invoke_and_host_feedback() -> None:
    client = StableV2RillClient(command(), feature_schema_hash="a" * 64)
    try:
        assert client.protocol_api_version == 2
        assert client.model_pack_id == "lessonforge.test"
        assert client.health() is True
        suggestion = client.decide(event(), static_suggestion=static(), deterministic_seed=7)
        assert suggestion.action == ShadowAction.HUMAN_REVIEW
        assert suggestion.selected_arm == 7
        with pytest.raises(RillProtocolError):
            client.feedback(
                decision_id=suggestion.decision_id,
                selected_arm=suggestion.selected_arm,
                reward=1,
                outcome_time_ms=2,
                generation=suggestion.state_generation,
            )
        assert client.inspect()["hostOwnedState"] is True
    finally:
        client.close()


def test_stable_v2_requires_exact_capability_and_fail_closes_malformed_output() -> None:
    with pytest.raises(RillProtocolError):
        StableV2RillClient(
            command("rillml.linearRegression.predict"),
            feature_schema_hash="a" * 64,
        )
    with pytest.raises(RillProtocolError):
        StableV2RillClient(
            command("org.lessonforge.shadow.evaluate,org.lessonforge.shadow.update", "malformed"),
            feature_schema_hash="a" * 64,
        )


def test_stable_v2_can_consume_a_business_neutral_official_capability() -> None:
    client = StableV2RillClient(
        command("rillml.linearRegression.predict"),
        feature_schema_hash="a" * 64,
        evaluate_capability="rillml.linearRegression.predict",
        feedback_capability=None,
    )
    try:
        output = client.invoke("rillml.linearRegression.predict", {"features": [1.0, 2.0]})
        assert output == {"features": [1.0, 2.0]}
    finally:
        client.close()


def test_stable_v2_health_failure_is_unavailable() -> None:
    with pytest.raises(RillUnavailableError):
        StableV2RillClient(
            command("org.lessonforge.shadow.evaluate,org.lessonforge.shadow.update", "unhealthy"),
            feature_schema_hash="a" * 64,
        )
