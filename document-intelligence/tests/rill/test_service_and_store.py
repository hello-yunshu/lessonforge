from __future__ import annotations

import json
from pathlib import Path

import pytest

from document_intelligence.exceptions import RillFeedbackError, RillStoreCorruptError
from document_intelligence.rill.models import (
    FeedbackSeverity,
    ShadowAction,
    ShadowFeedbackInput,
)
from document_intelligence.rill.store import RillShadowStore
from tests.rill.helpers import build_reference_service


def feedback(evaluation_id: str, action: ShadowAction) -> ShadowFeedbackInput:
    return ShadowFeedbackInput(
        evaluation_id=evaluation_id,
        actual_action=action,
        decision_correct=True,
        error_scope="route",
        error_type="none",
        severity=FeedbackSeverity.P2,
        human_edit_seconds=0,
        eligible_for_training=True,
        outcome_time_ms=1,
    )


def test_reference_shadow_lifecycle_never_executes_actions(settings) -> None:
    service, run_id, structure_id = build_reference_service(settings)
    try:
        evaluation = service.evaluate(run_id, structure_id=structure_id)
        generation = service.client.state_generation
        assert service.evaluate(run_id, structure_id=structure_id) == evaluation
        assert service.client.state_generation == generation
        assert evaluation.no_action_executed is True
        assert evaluation.shadow_only is True
        assert evaluation.rill_suggestion is not None
        record = service.feedback(
            feedback(evaluation.evaluation_id, evaluation.rill_suggestion.action)
        )
        assert record.runtime_feedback_accepted is True
        assert (
            service.feedback(
                feedback(evaluation.evaluation_id, evaluation.rill_suggestion.action)
            )
            == record
        )
        with pytest.raises(RillFeedbackError):
            service.feedback(feedback(evaluation.evaluation_id, ShadowAction.QUARANTINE))
        first = service.snapshot()
        second = service.snapshot()
        assert second.snapshot_id == first.snapshot_id
        reset = service.reset()
        assert reset.pre_reset_snapshot_id
        assert service.inspect()["noProductionActions"] is True
    finally:
        service.close()


def test_runtime_failure_is_isolated_from_base_artifacts(settings) -> None:
    service, run_id, structure_id = build_reference_service(settings)
    original_runs = sorted((settings.workspace / "runs").rglob("*"))
    service.client = None
    evaluation = service.evaluate(run_id, structure_id=structure_id)
    assert evaluation.status == "runtime_unavailable"
    assert sorted((settings.workspace / "runs").rglob("*")) == original_runs


def test_store_detects_tampering_and_identifier_collisions(settings) -> None:
    service, run_id, structure_id = build_reference_service(settings)
    evaluation = service.evaluate(run_id, structure_id=structure_id)
    path = (
        settings.workspace
        / "rill-shadow"
        / "evaluations"
        / evaluation.evaluation_id
        / "evaluation.json"
    )
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["runtimeErrorCode"] = "tampered"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(RillStoreCorruptError):
        RillShadowStore(settings.workspace).read_evaluation(evaluation.evaluation_id)


def test_same_event_can_be_reevaluated_after_runtime_context_changes(settings) -> None:
    service, run_id, structure_id = build_reference_service(settings)
    service.client = None
    service.backend_name = "disabled"
    unavailable = service.evaluate(run_id, structure_id=structure_id)
    assert unavailable.status == "runtime_unavailable"

    from document_intelligence.rill.client import ReferenceRillShadowClient

    service.client = ReferenceRillShadowClient(service.feature_builder.feature_schema_hash)
    service.backend_name = "reference"
    available = service.evaluate(run_id, structure_id=structure_id)
    assert available.status == "succeeded"
    assert available.evaluation_id != unavailable.evaluation_id

    suggestion = available.rill_suggestion
    assert suggestion is not None
    service.feedback(feedback(available.evaluation_id, suggestion.action))
    updated = service.evaluate(run_id, structure_id=structure_id)
    assert updated.evaluation_id != available.evaluation_id
    service.close()


def test_store_missing_record_is_not_reported_as_corruption(settings) -> None:
    store = RillShadowStore(settings.workspace)
    with pytest.raises(FileNotFoundError):
        store.read_evaluation("missing-evaluation")
    with pytest.raises(FileNotFoundError):
        store.read_snapshot("missing-snapshot")


def test_store_rechecks_namespace_symlink_on_each_access(settings, tmp_path) -> None:
    store = RillShadowStore(settings.workspace)
    namespace = settings.workspace / "rill-shadow" / "evaluations"
    namespace.rmdir()
    namespace.symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(RillStoreCorruptError):
        store.read_evaluation("missing-evaluation")


def test_reset_restores_local_drift_when_runtime_rejects(settings) -> None:
    service, _, _ = build_reference_service(settings)
    service.drift.update(error=True)
    before = service.drift.read()

    class RejectResetClient:
        def __init__(self, delegate):
            self.delegate = delegate

        def __getattr__(self, name):
            return getattr(self.delegate, name)

        def reset(self, *, expected_state_generation: int) -> int:
            raise RuntimeError("rejected")

    service.client = RejectResetClient(service.client)
    with pytest.raises(RuntimeError):
        service.reset()
    assert service.drift.read() == before
    service.close()
