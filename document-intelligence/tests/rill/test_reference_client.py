from __future__ import annotations

import pytest

from document_intelligence.exceptions import RillProtocolError
from document_intelligence.rill.client import ReferenceRillShadowClient, RuntimeSnapshot
from document_intelligence.rill.models import (
    ACTION_TO_ARM, ParseSignals, PolicySuggestion, RillObserveEvent,
    ShadowAction, ShadowSignals,
)


def event() -> RillObserveEvent:
    return RillObserveEvent(event_id="observe-reference", parse_run_id="run-reference",
                            parser_id="fixture", signals=ShadowSignals(parse=ParseSignals(
                                page_count=1, element_count=1, average_confidence=1,
                                minimum_confidence=1, p0_warnings=0, p1_warnings=0,
                                p2_warnings=0, duration_ms=0, estimated_cost_usd=0)))


def static() -> PolicySuggestion:
    return PolicySuggestion(decision_id="static-reference", action=ShadowAction.ACCEPT,
                            selected_arm=ACTION_TO_ARM[ShadowAction.ACCEPT],
                            policy_version="test", confidence=1,
                            reason_codes=["TEST"], source="static_policy")


def test_reference_snapshot_restore_and_validation() -> None:
    client = ReferenceRillShadowClient("a" * 64)
    item = event()
    client.observe(item)
    decision = client.decide(item, static_suggestion=static(), deterministic_seed=3)
    client.feedback(decision_id=decision.decision_id, selected_arm=decision.selected_arm,
                    reward=1, outcome_time_ms=1, generation=decision.state_generation)
    snapshot = client.snapshot()
    restored = ReferenceRillShadowClient("a" * 64)
    restored.restore(snapshot)
    assert restored.inspect() == client.inspect()
    with pytest.raises(RillProtocolError):
        restored.restore(RuntimeSnapshot(snapshot.state_schema_version, "0" * 64,
                                         snapshot.state, snapshot.model_generation,
                                         snapshot.state_generation))
    with pytest.raises(RillProtocolError):
        client.feedback(decision_id=decision.decision_id,
                        selected_arm=decision.selected_arm, reward=1,
                        outcome_time_ms=1, generation=decision.state_generation)
    with pytest.raises(RillProtocolError):
        client.reset(expected_state_generation=999)
