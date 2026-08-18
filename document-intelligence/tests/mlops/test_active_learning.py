from __future__ import annotations

from document_intelligence.mlops.active_learning import ActiveLearningSelector
from document_intelligence.rill.models import (
    ACTION_TO_ARM,
    DomainSignals,
    MatchSignals,
    ParseSignals,
    PolicySuggestion,
    RillObserveEvent,
    ShadowAction,
    ShadowEvaluation,
    ShadowEvaluationStatus,
    ShadowSignals,
    RuntimeIdentity,
    StructureSignals,
)
from tests.mlops.helpers import sha


def evaluation(identifier: str, family: str, risky: bool) -> ShadowEvaluation:
    event = RillObserveEvent(
        event_id=f"event-{identifier}",
        parse_run_id=f"run-{identifier}",
        parser_id="paddle" if risky else "native-pdf",
        document_family=family,
        signals=ShadowSignals(
            parse=ParseSignals(
                page_count=1,
                element_count=10,
                average_confidence=0.5 if risky else 0.99,
                minimum_confidence=0.2 if risky else 0.98,
                p0_warnings=1 if risky else 0,
                p1_warnings=1 if risky else 0,
                p2_warnings=0,
                empty_native_text=risky,
                duration_ms=10,
                estimated_cost_usd=0,
            ),
            matching=MatchSignals(
                decision="ambiguous" if risky else "no_match",
                top1_score=0.5,
                margin=0.01 if risky else 0.5,
                candidate_count=2 if risky else 0,
                safe_standard_reuse=False,
            ),
            structure=StructureSignals(
                reading_order_coverage=1,
                relation_evidence_coverage=0.5 if risky else 1,
                consistency_score=0.8,
                diagnostics_info=0,
                diagnostics_warning=0,
                diagnostics_error=1 if risky else 0,
                cross_page_relations=0,
            ),
            domain=DomainSignals(
                status="fallback_generic" if risky else "succeeded",
                annotations=0,
                relations=0,
                validation_findings=1 if risky else 0,
                error_findings=1 if risky else 0,
                evidence_coverage=0.5 if risky else 1,
                fallback_used=risky,
            ),
        ),
    )
    static = PolicySuggestion(
        decision_id=f"static-{identifier}",
        action=ShadowAction.HUMAN_REVIEW if risky else ShadowAction.ACCEPT,
        selected_arm=ACTION_TO_ARM[
            ShadowAction.HUMAN_REVIEW if risky else ShadowAction.ACCEPT
        ],
        policy_version="static",
        confidence=1,
        reason_codes=["STATIC"],
        source="static_policy",
    )
    rill_action = ShadowAction.QUARANTINE if risky else ShadowAction.ACCEPT
    rill = PolicySuggestion(
        decision_id=f"rill-{identifier}",
        action=rill_action,
        selected_arm=ACTION_TO_ARM[rill_action],
        policy_version="rill",
        confidence=0.8,
        reason_codes=["RILL"],
        source="rill_runtime",
    )
    return ShadowEvaluation(
        evaluation_id=f"evaluation-{identifier}",
        feature_schema_hash=sha("features"),
        observe_event=event,
        static_suggestion=static,
        rill_suggestion=rill,
        runtime_identity=RuntimeIdentity(
            name="rill-runtime",
            version="1.1.0",
            feature_schema_hash=sha("features"),
            handler_api_version=1,
            capabilities=["observe", "decide", "feedback"],
        ),
        backend_name="subprocess",
        input_model_generation=1,
        input_state_generation=1,
        status=ShadowEvaluationStatus.SUCCEEDED,
    )


def test_active_learning_prioritizes_risk_and_caps_families() -> None:
    selector = ActiveLearningSelector()
    batch = selector.select(
        [
            evaluation("risk-a", "education", True),
            evaluation("risk-b", "education", True),
            evaluation("safe", "generic", False),
        ],
        active_drift_parser_ids={"paddle"},
        max_items=3,
        max_per_family=1,
    )
    assert len(batch.selections) == 1
    assert batch.selections[0].evaluation_id.startswith("evaluation-risk")
    assert "ACTIVE_DRIFT" in batch.selections[0].reason_codes
    assert "P0_WARNING" in batch.selections[0].reason_codes


def test_active_learning_identity_binds_exclusions_and_drift_context() -> None:
    selector = ActiveLearningSelector()
    item = evaluation("risk", "education", True)
    first = selector.select([item], max_items=1, max_per_family=1)
    excluded = selector.select(
        [item],
        excluded_evaluation_ids={item.evaluation_id},
        max_items=1,
        max_per_family=1,
    )
    drift = selector.select(
        [item],
        active_drift_parser_ids={"paddle"},
        max_items=1,
        max_per_family=1,
    )
    assert first.batch_id != excluded.batch_id
    assert first.batch_id != drift.batch_id
    assert excluded.selections == []


def test_service_does_not_requeue_existing_active_learning_items(settings) -> None:
    from document_intelligence.mlops import MLOpsService, MLOpsStore
    from document_intelligence.rill.assist_store import RillAssistStore
    from document_intelligence.rill.store import RillShadowStore

    shadow = RillShadowStore(settings.workspace)
    item = evaluation("queued", "education", True)
    shadow.commit_evaluation(item)
    service = MLOpsService(
        MLOpsStore(settings.workspace), shadow, RillAssistStore(settings.workspace)
    )
    first = service.select_active_learning(max_items=10, max_per_family=10)
    second = service.select_active_learning(max_items=10, max_per_family=10)
    assert len(first.selections) == 1
    assert second.selections == []
    assert first.batch_id != second.batch_id
