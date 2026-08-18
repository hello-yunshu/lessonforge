from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone

import pytest

from document_intelligence.exceptions import (
    RillAssistQualificationError,
    RillStoreCorruptError,
)
from document_intelligence.parser_sdk import ParserRegistry
from document_intelligence.parser_sdk.utils import stable_id
from document_intelligence.rill.assist import RillAssistService
from document_intelligence.rill.assist_models import (
    AssistActivationRequest,
    AssistAttestationRequest,
    AssistEvidenceOrigin,
    AssistQualificationReport,
    AssistReviewerRole,
    AssistRevocationRequest,
    Tier1AssistAction,
)
from document_intelligence.rill.assist_store import RillAssistStore
from document_intelligence.rill.client import ReferenceRillShadowClient
from document_intelligence.rill.models import (
    ACTION_TO_ARM,
    ParseSignals,
    PolicySuggestion,
    RillObserveEvent,
    RuntimeIdentity,
    ShadowAction,
    ShadowEvaluation,
    ShadowFeedbackRecord,
    ShadowSignals,
    stable_rill_id,
)
from document_intelligence.rill.service import RillShadowService
from document_intelligence.schema import (
    ParserHealth,
    ParserResult,
    ParseRun,
    ResourceUsage,
    RunStatus,
)
from document_intelligence.services.orchestrator import ParseOrchestrator
from document_intelligence.services.store import ArtifactStore
from tests.domain_runtime.helpers import build_parser_result
from tests.rill.helpers import build_reference_service


class RealTestRillClient(ReferenceRillShadowClient):
    def __init__(self, feature_schema_hash: str) -> None:
        super().__init__(feature_schema_hash)
        self._identity = RuntimeIdentity(
            name="rill-runtime-test",
            version="0.15.0-test",
            feature_schema_hash=feature_schema_hash,
            handler_api_version=1,
            capabilities=self._identity.capabilities,
        )

    def inspect(self):
        summary = super().inspect()
        summary["artifactDigests"] = {
            "runtimeSha256": "1" * 64,
            "modelSha256": "2" * 64,
            "handlerSha256": "3" * 64,
        }
        return summary

    def decide(self, event, *, static_suggestion, deterministic_seed):
        suggestion = super().decide(
            event,
            static_suggestion=static_suggestion,
            deterministic_seed=deterministic_seed,
        )
        return suggestion.model_copy(
            update={
                "source": "rill_runtime",
                "policy_version": "rill-runtime-test-policy",
            }
        )


class SecondaryFixtureParser:
    parser_id = "secondary-fixture"
    priority = 20
    capabilities = ["application/pdf", "normalized-gateway"]

    def supports(self, request) -> bool:
        return request.mime_type == "application/pdf"

    def health(self) -> ParserHealth:
        return ParserHealth(
            parser_id=self.parser_id,
            available=True,
            enabled=True,
            version="1",
            artifact_digest="a" * 64,
            capabilities=self.capabilities,
        )

    def parse(self, request) -> ParserResult:
        _, template = build_parser_result()
        run_id = stable_id(
            "run",
            request.sha256,
            request.context_digest(),
            self.parser_id,
            "1",
            "a" * 64,
        )
        evidence = [
            item.model_copy(update={"parse_run_id": run_id})
            for item in template.document.evidence
        ]
        source = template.document.source.model_copy(update={
            "filename": request.filename,
            "sha256": request.sha256,
            "mime_type": request.mime_type,
            "size_bytes": len(request.content),
        })
        document = template.document.model_copy(
            update={"parse_run_id": run_id, "source": source, "evidence": evidence},
            deep=True,
        )
        now = datetime.now(timezone.utc)
        run = ParseRun(
            parse_run_id=run_id,
            input_sha256=request.sha256,
            parser_id=self.parser_id,
            parser_version="1",
            parser_digest="a" * 64,
            config_digest="b" * 64,
            request_context_digest=request.context_digest(),
            status=RunStatus.SUCCEEDED,
            started_at=now,
            finished_at=now,
            semantic_output_digest=document.semantic_digest(),
            resource_usage=ResourceUsage(
                duration_ms=1,
                input_bytes=len(request.content),
                output_elements=len(document.elements),
            ),
        )
        return ParserResult(document=document, run=run)


def event(event_id: str, run_id: str) -> RillObserveEvent:
    return RillObserveEvent(
        event_id=event_id,
        parse_run_id=run_id,
        parser_id="fixture",
        signals=ShadowSignals(
            parse=ParseSignals(
                page_count=1,
                element_count=1,
                average_confidence=0.95,
                minimum_confidence=0.9,
                p0_warnings=0,
                p1_warnings=0,
                p2_warnings=0,
                empty_native_text=False,
                duration_ms=1,
                estimated_cost_usd=0,
            )
        ),
    )


def commit_labeled_decision(
    shadow: RillShadowService,
    *,
    index: int,
    run_id: str,
    action: ShadowAction,
) -> tuple[ShadowEvaluation, ShadowFeedbackRecord]:
    observed = event(f"assist-event-{index}", run_id)
    static = PolicySuggestion(
        decision_id=f"static-assist-{index}",
        action=action,
        selected_arm=ACTION_TO_ARM[action],
        policy_version="static-test",
        confidence=1,
        reason_codes=["TEST_STATIC"],
        source="static_policy",
    )
    suggestion = PolicySuggestion(
        decision_id=f"rill-assist-{index}",
        action=action,
        selected_arm=ACTION_TO_ARM[action],
        policy_version="real-test",
        confidence=1,
        reason_codes=["TEST_RILL"],
        source="rill_runtime",
        model_generation=shadow.client.model_generation if shadow.client else 0,
        state_generation=shadow.client.state_generation if shadow.client else 0,
    )
    evaluation = shadow.store.commit_evaluation(
        ShadowEvaluation(
            evaluation_id=f"assist-evaluation-{index}",
            feature_schema_hash=shadow.feature_builder.feature_schema_hash,
            observe_event=observed,
            static_suggestion=static,
            rill_suggestion=suggestion,
            runtime_identity=shadow.client.identity if shadow.client else None,
            backend_name="subprocess-test",
            input_model_generation=suggestion.model_generation,
            input_state_generation=suggestion.state_generation,
            status="succeeded",
        )
    )
    feedback = shadow.store.commit_feedback(
        ShadowFeedbackRecord(
            feedback_id=f"assist-feedback-{index}",
            evaluation_id=evaluation.evaluation_id,
            decision_id=suggestion.decision_id,
            selected_arm=suggestion.selected_arm,
            actual_action=action,
            decision_correct=True,
            error_scope="route",
            error_type="none",
            severity="P2",
            human_edit_seconds=0,
            eligible_for_training=True,
            reward=1,
            runtime_feedback_accepted=True,
        )
    )
    return evaluation, feedback


def build_assist(settings, *, action: ShadowAction, count: int = 2, with_run: bool = False):
    shadow, run_id, _ = build_reference_service(settings)
    shadow.client = RealTestRillClient(shadow.feature_builder.feature_schema_hash)
    shadow.backend_name = "subprocess-test"
    artifact_store = ArtifactStore(settings.workspace)
    if with_run:
        request, result = build_parser_result()
        artifact_store.commit_success(request, result)
        run_id = result.run.parse_run_id
    orchestrator = ParseOrchestrator(
        ParserRegistry([SecondaryFixtureParser()]),
        artifact_store,
    )
    assist = RillAssistService(
        shadow,
        orchestrator,
        RillAssistStore(settings.workspace),
        min_expert_feedback=count,
        min_production_like_feedback=count,
        min_accuracy=1,
        min_action_feedback=count,
        qualification_ttl_hours=24,
        runtime_artifact_sha256="1" * 64,
        model_artifact_sha256="2" * 64,
        handler_artifact_sha256="3" * 64,
    )
    pairs = [
        commit_labeled_decision(shadow, index=index, run_id=run_id, action=action)
        for index in range(count)
    ]
    reviewer = hashlib.sha256(b"expert").hexdigest()
    for _, feedback in pairs:
        assist.create_attestation(
            AssistAttestationRequest(
                feedback_id=feedback.feedback_id,
                reviewer_role=AssistReviewerRole.DOMAIN_EXPERT,
                evidence_origin=AssistEvidenceOrigin.GOLD,
                reviewer_id_hash=reviewer,
                dataset_id="gold-set-1",
                approved_for_qualification=True,
            )
        )
    return assist, pairs


def activate(assist: RillAssistService, action: Tier1AssistAction):
    report = assist.qualify([action])
    assert report.qualified is True
    activation = assist.activate(
        AssistActivationRequest(
            qualification_report_id=report.report_id,
            approver_id_hash=hashlib.sha256(b"approver").hexdigest(),
            allowed_actions=[action],
            max_executions_per_hour=10,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        )
    )
    return report, activation


def test_reference_runtime_and_missing_expert_data_never_qualify(settings) -> None:
    shadow, _, _ = build_reference_service(settings)
    assist = RillAssistService(
        shadow,
        ParseOrchestrator(ParserRegistry(), ArtifactStore(settings.workspace)),
        RillAssistStore(settings.workspace),
        min_expert_feedback=1,
        min_production_like_feedback=1,
        min_action_feedback=1,
    )
    report = assist.qualify([Tier1AssistAction.HUMAN_REVIEW])
    assert report.qualified is False
    assert report.test_only is True
    assert "REFERENCE_RUNTIME_NOT_QUALIFIABLE" in report.blocking_reasons



def test_runtime_must_attest_loaded_artifact_digests(settings) -> None:
    assist, _ = build_assist(settings, action=ShadowAction.HUMAN_REVIEW, count=1)
    assert assist.shadow.client is not None
    assist.shadow.client.inspect = lambda: {}  # type: ignore[method-assign]
    report = assist.qualify([Tier1AssistAction.HUMAN_REVIEW])
    assert report.qualified is False
    assert "RUNTIME_ARTIFACT_ATTESTATION_REQUIRED" in report.blocking_reasons

def test_synthetic_evidence_cannot_be_approved_for_qualification() -> None:
    with pytest.raises(ValueError):
        AssistAttestationRequest(
            feedback_id="feedback-one",
            reviewer_role=AssistReviewerRole.DOMAIN_EXPERT,
            evidence_origin=AssistEvidenceOrigin.SYNTHETIC,
            reviewer_id_hash="0" * 64,
            dataset_id="synthetic-set",
            approved_for_qualification=True,
        )


def test_qualified_human_review_execution_is_additive_idempotent_and_revocable(settings) -> None:
    assist, pairs = build_assist(settings, action=ShadowAction.HUMAN_REVIEW)
    _, activation = activate(assist, Tier1AssistAction.HUMAN_REVIEW)
    evaluation = pairs[0][0]
    first = assist.execute(activation.activation_id, evaluation.evaluation_id)
    second = assist.execute(activation.activation_id, evaluation.evaluation_id)
    assert first == second
    assert first.status == "succeeded"
    assert first.queue_item_id is not None
    assert first.replaced_existing_result is False
    assert first.bounded_auto is False
    assert len(assist.store.list_queue_items()) == 1

    assist.revoke(
        AssistRevocationRequest(
            activation_id=activation.activation_id,
            operator_id_hash=hashlib.sha256(b"operator").hexdigest(),
            reason_code="EMERGENCY_STOP",
        )
    )
    with pytest.raises(RillAssistQualificationError):
        assist.execute(activation.activation_id, pairs[1][0].evaluation_id)


def test_secondary_parser_execution_creates_candidate_without_replacing_source(settings) -> None:
    assist, pairs = build_assist(
        settings,
        action=ShadowAction.USE_SECONDARY_PARSER,
        count=1,
        with_run=True,
    )
    _, activation = activate(assist, Tier1AssistAction.USE_SECONDARY_PARSER)
    source_run = pairs[0][0].observe_event.parse_run_id
    execution = assist.execute(activation.activation_id, pairs[0][0].evaluation_id)
    assert execution.status == "succeeded"
    assert execution.output_run_id is not None
    assert execution.output_run_id != source_run
    assert execution.parser_id == "secondary-fixture"
    assert execution.replaced_existing_result is False
    assert assist.orchestrator.store.read_result(source_run).run.parse_run_id == source_run
    assert (
        assist.orchestrator.store.read_result(execution.output_run_id).run.parser_id
        == "secondary-fixture"
    )


def test_assist_store_detects_payload_tampering_and_namespace_symlink(settings, tmp_path) -> None:
    assist, _ = build_assist(settings, action=ShadowAction.HUMAN_REVIEW)
    report = assist.qualify([Tier1AssistAction.HUMAN_REVIEW])
    path = (
        settings.workspace
        / "rill-assist"
        / "qualifications"
        / report.report_id
        / "qualification.json"
    )
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["qualified"] = False
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(RillStoreCorruptError):
        assist.store.read_qualification(report.report_id)

    other = RillAssistStore(tmp_path / "other")
    namespace = other.qualifications_dir
    namespace.rmdir()
    namespace.symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(RillStoreCorruptError):
        other.list_qualifications()


def test_qualification_expiry_is_semantic() -> None:
    now = datetime.now(timezone.utc)
    base = dict(
        report_id="assist-report-one",
        feature_schema_hash="0" * 64,
        runtime_name="rill-runtime",
        runtime_version="1",
        runtime_artifact_sha256="2" * 64,
        model_artifact_sha256="3" * 64,
        handler_artifact_sha256="4" * 64,
        model_generation=1,
        state_generation=1,
        replay_digest="1" * 64,
        total_feedback_count=1,
        eligible_feedback_count=1,
        expert_feedback_count=1,
        production_like_feedback_count=1,
        rill_accuracy=1,
        static_accuracy=1,
        rill_accept_on_p0_p1=0,
        active_drift_alerts=0,
        action_feedback_counts={Tier1AssistAction.HUMAN_REVIEW: 1},
        requested_actions=[Tier1AssistAction.HUMAN_REVIEW],
        qualified_actions=[Tier1AssistAction.HUMAN_REVIEW],
        qualified=True,
        created_at=now,
    )
    first = AssistQualificationReport(**base, expires_at=now + timedelta(hours=1))
    second = AssistQualificationReport(**base, expires_at=now + timedelta(hours=2))
    assert first.semantic_digest() != second.semantic_digest()


def test_assist_rate_limit_is_atomic_and_blocked_attempt_is_audited(settings) -> None:
    from concurrent.futures import ThreadPoolExecutor

    assist, pairs = build_assist(settings, action=ShadowAction.HUMAN_REVIEW, count=2)
    report = assist.qualify([Tier1AssistAction.HUMAN_REVIEW])
    activation = assist.activate(
        AssistActivationRequest(
            qualification_report_id=report.report_id,
            approver_id_hash=hashlib.sha256(b"rate-approver").hexdigest(),
            allowed_actions=[Tier1AssistAction.HUMAN_REVIEW],
            max_executions_per_hour=1,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        )
    )
    with ThreadPoolExecutor(max_workers=2) as pool:
        records = list(
            pool.map(
                lambda pair: assist.execute(activation.activation_id, pair[0].evaluation_id),
                pairs,
            )
        )
    assert sorted(item.status.value for item in records) == ["blocked", "succeeded"]
    assert any(item.error_code == "ASSIST_RATE_LIMIT_REACHED" for item in records)
    assert len(assist.store.list_executions()) == 2
    assert len(assist.store.list_queue_items()) == 1


def test_parser_suspension_is_drift_bound_reversible_and_filters_routing(settings) -> None:
    from document_intelligence.rill.assist_models import (
        AssistParserResumeRequest,
        AssistParserSuspensionRequest,
    )
    from document_intelligence.rill.models import DriftAlert, DriftState
    from document_intelligence.exceptions import ParserUnavailableError

    assist, _ = build_assist(settings, action=ShadowAction.QUARANTINE, count=1)
    _, activation = activate(assist, Tier1AssistAction.QUARANTINE)
    alert = DriftAlert(
        alert_id="drift-alert-assist-test",
        sample_count=50,
        recent_error_rate=0.5,
        baseline_error_rate=0.1,
        page_hinkley_distance=10,
        threshold=5,
        reason_codes=["SHADOW_ERROR_RATE_DRIFT"],
    )
    assist.shadow.drift._commit_alert(alert)
    assist.shadow.drift.write(DriftState(alert_count=1, state_generation=1))
    suspension_request = AssistParserSuspensionRequest(
        activation_id=activation.activation_id,
        parser_id="secondary-fixture",
        drift_alert_id=alert.alert_id,
        operator_id_hash=hashlib.sha256(b"suspend-operator").hexdigest(),
        reason_code="DRIFT_CONFIRMED",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=30),
    )
    suspension = assist.suspend_parser(suspension_request)
    assert assist.suspend_parser(suspension_request) == suspension
    assert assist.is_parser_suspended("secondary-fixture") is True
    request, _ = build_parser_result()
    explicit = request.model_copy(update={"parser_id": "secondary-fixture"})
    with pytest.raises(ParserUnavailableError):
        assist.orchestrator.parse(explicit)

    resume_request = AssistParserResumeRequest(
        suspension_id=suspension.suspension_id,
        operator_id_hash=hashlib.sha256(b"resume-operator").hexdigest(),
        reason_code="MANUAL_VALIDATION_COMPLETE",
    )
    resume = assist.resume_parser(resume_request)
    assert assist.resume_parser(resume_request) == resume
    assert resume.suspension_id == suspension.suspension_id
    assert assist.is_parser_suspended("secondary-fixture") is False


def test_qualification_rejects_empty_actions_and_duplicate_attestations(settings) -> None:
    assist, pairs = build_assist(settings, action=ShadowAction.HUMAN_REVIEW, count=1)
    with pytest.raises(ValueError):
        assist.qualify([])
    feedback = pairs[0][1]
    assist.create_attestation(
        AssistAttestationRequest(
            feedback_id=feedback.feedback_id,
            reviewer_role=AssistReviewerRole.DOMAIN_EXPERT,
            evidence_origin=AssistEvidenceOrigin.CHALLENGE,
            reviewer_id_hash=hashlib.sha256(b"second-expert").hexdigest(),
            dataset_id="challenge-set-2",
            approved_for_qualification=True,
        )
    )
    report = assist.qualify([Tier1AssistAction.HUMAN_REVIEW])
    assert report.qualified is False
    assert "DUPLICATE_EXPERT_ATTESTATIONS" in report.blocking_reasons


def test_activation_rejects_digest_change_and_action_expansion(settings) -> None:
    assist, _ = build_assist(settings, action=ShadowAction.HUMAN_REVIEW, count=1)
    report = assist.qualify([Tier1AssistAction.HUMAN_REVIEW])
    with pytest.raises(RillAssistQualificationError):
        assist.activate(
            AssistActivationRequest(
                qualification_report_id=report.report_id,
                approver_id_hash="1" * 64,
                allowed_actions=[Tier1AssistAction.QUARANTINE],
                max_executions_per_hour=1,
                expires_at=datetime.now(timezone.utc) + timedelta(minutes=30),
            )
        )
    assist.runtime_artifact_sha256 = "9" * 64
    with pytest.raises(RillAssistQualificationError):
        assist.activate(
            AssistActivationRequest(
                qualification_report_id=report.report_id,
                approver_id_hash="1" * 64,
                allowed_actions=[Tier1AssistAction.HUMAN_REVIEW],
                max_executions_per_hour=1,
                expires_at=datetime.now(timezone.utc) + timedelta(minutes=30),
            )
        )


def test_action_outside_activation_is_blocked_and_audited(settings) -> None:
    assist, pairs = build_assist(settings, action=ShadowAction.HUMAN_REVIEW, count=1)
    quarantine_eval, quarantine_feedback = commit_labeled_decision(
        assist.shadow,
        index=99,
        run_id=pairs[0][0].observe_event.parse_run_id,
        action=ShadowAction.QUARANTINE,
    )
    assist.create_attestation(
        AssistAttestationRequest(
            feedback_id=quarantine_feedback.feedback_id,
            reviewer_role=AssistReviewerRole.DOMAIN_EXPERT,
            evidence_origin=AssistEvidenceOrigin.GOLD,
            reviewer_id_hash=hashlib.sha256(b"expert-2").hexdigest(),
            dataset_id="gold-set-2",
            approved_for_qualification=True,
        )
    )
    report = assist.qualify(
        [Tier1AssistAction.HUMAN_REVIEW, Tier1AssistAction.QUARANTINE]
    )
    activation = assist.activate(
        AssistActivationRequest(
            qualification_report_id=report.report_id,
            approver_id_hash="2" * 64,
            allowed_actions=[Tier1AssistAction.HUMAN_REVIEW],
            max_executions_per_hour=10,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=30),
        )
    )
    blocked = assist.execute(activation.activation_id, quarantine_eval.evaluation_id)
    assert blocked.status == "blocked"
    assert blocked.error_code == "ACTION_NOT_ACTIVATED"


def test_live_replay_regression_blocks_execution_with_record(settings) -> None:
    assist, pairs = build_assist(settings, action=ShadowAction.HUMAN_REVIEW, count=1)
    _, activation = activate(assist, Tier1AssistAction.HUMAN_REVIEW)
    bad_evaluation, _ = commit_labeled_decision(
        assist.shadow,
        index=100,
        run_id=pairs[0][0].observe_event.parse_run_id,
        action=ShadowAction.HUMAN_REVIEW,
    )
    assist.shadow.store.commit_feedback(
        ShadowFeedbackRecord(
            feedback_id="assist-feedback-bad-live",
            evaluation_id=bad_evaluation.evaluation_id,
            decision_id=bad_evaluation.rill_suggestion.decision_id,
            selected_arm=bad_evaluation.rill_suggestion.selected_arm,
            actual_action=ShadowAction.QUARANTINE,
            decision_correct=False,
            error_scope="route",
            error_type="wrong-route",
            severity="P2",
            human_edit_seconds=10,
            eligible_for_training=True,
            reward=-1,
            runtime_feedback_accepted=True,
        )
    )
    record = assist.execute(activation.activation_id, pairs[0][0].evaluation_id)
    assert record.status == "blocked"
    assert record.error_code == "ASSIST_LIVE_SAFETY_BLOCKED"


def test_high_resolution_and_specialist_parser_routes(settings) -> None:
    class CapabilityParser(SecondaryFixtureParser):
        pass

    for action, parser_id, capabilities in (
        (
            ShadowAction.REPROCESS_HIGH_RES,
            "highres-fixture",
            ["application/pdf", "high-resolution-reprocess"],
        ),
        (
            ShadowAction.USE_SPECIALIST_PARSER,
            "specialist-fixture",
            ["application/pdf", "formula-specialist"],
        ),
    ):
        scoped = settings.model_copy(
            update={"workspace": settings.workspace.parent / f"var-{parser_id}"}
        )
        assist, pairs = build_assist(scoped, action=action, count=1, with_run=True)
        parser = CapabilityParser()
        parser.parser_id = parser_id
        parser.capabilities = capabilities
        assist.orchestrator.registry.register(parser)
        _, activation = activate(assist, Tier1AssistAction(action.value))
        result = assist.execute(activation.activation_id, pairs[0][0].evaluation_id)
        assert result.status == "succeeded"
        assert result.parser_id == parser_id


def test_retry_failure_isolated_and_parser_suspension_guards(settings) -> None:
    from document_intelligence.rill.assist_models import AssistParserSuspensionRequest
    from document_intelligence.rill.models import DriftAlert, DriftState

    assist, pairs = build_assist(
        settings, action=ShadowAction.RETRY, count=1, with_run=True
    )
    _, activation = activate(assist, Tier1AssistAction.RETRY)
    failed = assist.execute(activation.activation_id, pairs[0][0].evaluation_id)
    assert failed.status == "failed"
    assert failed.error_code == "ASSIST_PARSER_ACTION_FAILED"

    quarantine_settings = settings.model_copy(
        update={"workspace": settings.workspace.parent / "var-suspension-guards"}
    )
    guard, _ = build_assist(
        quarantine_settings, action=ShadowAction.QUARANTINE, count=1
    )
    _, guard_activation = activate(guard, Tier1AssistAction.QUARANTINE)
    alert = DriftAlert(
        alert_id="drift-alert-guard",
        sample_count=30,
        recent_error_rate=0.4,
        baseline_error_rate=0.1,
        page_hinkley_distance=8,
        threshold=5,
        reason_codes=["SHADOW_ERROR_RATE_DRIFT"],
    )
    guard.shadow.drift._commit_alert(alert)
    guard.shadow.drift.write(DriftState(alert_count=1, state_generation=1))
    base = dict(
        activation_id=guard_activation.activation_id,
        drift_alert_id=alert.alert_id,
        operator_id_hash="3" * 64,
        reason_code="TEST_GUARD",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
    )
    with pytest.raises(RillAssistQualificationError):
        guard.suspend_parser(AssistParserSuspensionRequest(parser_id="native-pdf", **base))
    with pytest.raises(RillAssistQualificationError):
        guard.suspend_parser(
            AssistParserSuspensionRequest(
                parser_id="secondary-fixture",
                **{**base, "drift_alert_id": "missing-drift-alert"},
            )
        )
