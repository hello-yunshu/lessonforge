from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from typing import Any

from document_intelligence.exceptions import (
    ParserUnavailableError,
    RillAssistExecutionError,
    RillAssistQualificationError,
)
from document_intelligence.rill.assist_models import (
    AssistActivationRecord,
    AssistAttestationRequest,
    AssistActivationRequest,
    AssistEvidenceAttestation,
    AssistEvidenceOrigin,
    AssistExecutionRecord,
    AssistExecutionStatus,
    AssistQualificationReport,
    AssistQueueItem,
    AssistQueueKind,
    AssistParserSuspensionRecord,
    AssistParserSuspensionRequest,
    AssistParserResumeRecord,
    AssistParserResumeRequest,
    AssistRevocationRecord,
    AssistRevocationRequest,
    Tier1AssistAction,
    stable_assist_id,
)
from document_intelligence.rill.assist_store import RillAssistStore
from document_intelligence.rill.models import FeedbackSeverity, ShadowAction
from document_intelligence.rill.service import RillShadowService
from document_intelligence.schema import ParseRequest
from document_intelligence.services.orchestrator import ParseOrchestrator


class RillAssistService:
    """Qualification-gated, additive Tier-1 execution layer.

    Assist never replaces an existing parse/structure/domain/review result. Parser
    actions only create a new candidate run, while review and quarantine actions
    append immutable queue items. ``boundedAuto`` is intentionally absent from
    all execution paths and remains hard-disabled in the persisted models.
    """

    def __init__(
        self,
        shadow: RillShadowService,
        orchestrator: ParseOrchestrator,
        store: RillAssistStore,
        *,
        min_expert_feedback: int = 30,
        min_production_like_feedback: int = 30,
        min_accuracy: float = 0.90,
        min_action_feedback: int = 5,
        qualification_ttl_hours: int = 168,
        runtime_artifact_sha256: str | None = None,
        model_artifact_sha256: str | None = None,
        handler_artifact_sha256: str | None = None,
    ) -> None:
        self.shadow = shadow
        self.orchestrator = orchestrator
        self.store = store
        self.min_expert_feedback = min_expert_feedback
        self.min_production_like_feedback = min_production_like_feedback
        self.min_accuracy = min_accuracy
        self.min_action_feedback = min_action_feedback
        self.qualification_ttl_hours = qualification_ttl_hours
        self.runtime_artifact_sha256 = runtime_artifact_sha256
        self.model_artifact_sha256 = model_artifact_sha256
        self.handler_artifact_sha256 = handler_artifact_sha256
        self.orchestrator.parser_suspension_checker = self.is_parser_suspended

    def attest(self, value: AssistEvidenceAttestation) -> AssistEvidenceAttestation:
        # The immutable feedback must exist before an attestation can be accepted.
        self.shadow.store.read_feedback(value.feedback_id)
        return self.store.commit_attestation(value)

    def create_attestation(
        self, request: AssistAttestationRequest
    ) -> AssistEvidenceAttestation:
        attestation_id = stable_assist_id(
            "assist-attestation",
            request.feedback_id,
            request.reviewer_id_hash,
            request.evidence_origin.value,
            request.dataset_id or "none",
        )
        return self.attest(
            AssistEvidenceAttestation(
                attestation_id=attestation_id,
                feedback_id=request.feedback_id,
                reviewer_role=request.reviewer_role,
                evidence_origin=request.evidence_origin,
                reviewer_id_hash=request.reviewer_id_hash,
                dataset_id=request.dataset_id,
                approved_for_qualification=request.approved_for_qualification,
            )
        )

    def qualify(
        self,
        requested_actions: list[Tier1AssistAction],
    ) -> AssistQualificationReport:
        now = datetime.now(timezone.utc)
        if not requested_actions or len(requested_actions) != len(set(requested_actions)):
            raise ValueError("requested Assist actions must be non-empty and unique")

        feedback = {item.feedback_id: item for item in self.shadow.store.list_feedback()}
        evaluations = {
            item.evaluation_id: item for item in self.shadow.store.list_evaluations()
        }
        attestations = [
            item
            for item in self.store.list_attestations()
            if item.approved_for_qualification and item.feedback_id in feedback
        ]
        # One approved expert attestation per feedback. Conflicting duplicate
        # attestations are rejected instead of being double-counted.
        grouped: dict[str, list[AssistEvidenceAttestation]] = {}
        for item in attestations:
            grouped.setdefault(item.feedback_id, []).append(item)
        duplicate_feedback = sorted(key for key, values in grouped.items() if len(values) > 1)
        eligible_attestations = [values[0] for values in grouped.values() if len(values) == 1]

        rill_correct = 0
        static_correct = 0
        severe_accepts = 0
        missing_suggestion = 0
        eligible_feedback = []
        for attestation in eligible_attestations:
            record = feedback[attestation.feedback_id]
            evaluation = evaluations.get(record.evaluation_id)
            if (
                evaluation is None
                or evaluation.rill_suggestion is None
                or evaluation.rill_suggestion.source != "rill_runtime"
            ):
                missing_suggestion += 1
                continue
            eligible_feedback.append(record)
            rill_correct += int(evaluation.rill_suggestion.action == record.actual_action)
            static_correct += int(evaluation.static_suggestion.action == record.actual_action)
            if (
                evaluation.rill_suggestion.action == ShadowAction.ACCEPT
                and record.severity in {FeedbackSeverity.P0, FeedbackSeverity.P1}
            ):
                severe_accepts += 1

        eligible_count = len(eligible_feedback)
        rill_accuracy = rill_correct / eligible_count if eligible_count else None
        static_accuracy = static_correct / eligible_count if eligible_count else None
        expert_count = len(eligible_attestations)
        action_feedback_counts = {action: 0 for action in requested_actions}
        for record in eligible_feedback:
            evaluation = evaluations[record.evaluation_id]
            if evaluation.rill_suggestion is None:
                raise RillAssistQualificationError(
                    "qualified feedback references an evaluation without a Rill suggestion"
                )
            try:
                action = Tier1AssistAction(evaluation.rill_suggestion.action.value)
            except ValueError:
                continue
            if action in action_feedback_counts:
                action_feedback_counts[action] += 1

        production_like_count = sum(
            item.evidence_origin
            in {
                AssistEvidenceOrigin.PRODUCTION,
                AssistEvidenceOrigin.GOLD,
                AssistEvidenceOrigin.CHALLENGE,
            }
            for item in eligible_attestations
        )

        identity = self.shadow.client.identity if self.shadow.client is not None else None
        model_generation = self.shadow.client.model_generation if self.shadow.client else 0
        state_generation = self.shadow.client.state_generation if self.shadow.client else 0
        blocking: list[str] = []
        test_only = identity is None or "reference" in identity.name.lower()
        if identity is None:
            blocking.append("REAL_RUNTIME_REQUIRED")
            runtime_name = "unavailable"
            runtime_version = "0"
        else:
            runtime_name = identity.name
            runtime_version = identity.version
            if test_only:
                blocking.append("REFERENCE_RUNTIME_NOT_QUALIFIABLE")
            if identity.feature_schema_hash != self.shadow.feature_builder.feature_schema_hash:
                blocking.append("FEATURE_SCHEMA_MISMATCH")
        if self.runtime_artifact_sha256 is None:
            blocking.append("RUNTIME_ARTIFACT_DIGEST_REQUIRED")
        if self.model_artifact_sha256 is None:
            blocking.append("MODEL_ARTIFACT_DIGEST_REQUIRED")
        if self.handler_artifact_sha256 is None:
            blocking.append("HANDLER_ARTIFACT_DIGEST_REQUIRED")
        if identity is not None and not self._runtime_artifact_attestation_matches():
            blocking.append("RUNTIME_ARTIFACT_ATTESTATION_REQUIRED")
        if duplicate_feedback:
            blocking.append("DUPLICATE_EXPERT_ATTESTATIONS")
        if expert_count < self.min_expert_feedback:
            blocking.append("INSUFFICIENT_EXPERT_FEEDBACK")
        if production_like_count < self.min_production_like_feedback:
            blocking.append("INSUFFICIENT_PRODUCTION_LIKE_FEEDBACK")
        for action, count in action_feedback_counts.items():
            if count < self.min_action_feedback:
                blocking.append(f"INSUFFICIENT_ACTION_COVERAGE_{action.value}")
        if missing_suggestion:
            blocking.append("MISSING_RILL_SUGGESTIONS")
        if severe_accepts:
            blocking.append("RILL_ACCEPTED_P0_P1")
        if rill_accuracy is None or rill_accuracy < self.min_accuracy:
            blocking.append("RILL_ACCURACY_BELOW_THRESHOLD")
        if (
            rill_accuracy is not None
            and static_accuracy is not None
            and rill_accuracy < static_accuracy
        ):
            blocking.append("RILL_BELOW_STATIC_BASELINE")
        drift_state = self.shadow.drift.read()
        if drift_state.alert_count > 0:
            blocking.append("ACTIVE_DRIFT_BLOCKER")

        replay_payload = {
            "feedback": [item.semantic_dict() for item in eligible_feedback],
            "attestations": [item.semantic_dict() for item in eligible_attestations],
            "runtime": {
                "name": runtime_name,
                "version": runtime_version,
                "modelGeneration": model_generation,
                "stateGeneration": state_generation,
                "runtimeArtifactSha256": self.runtime_artifact_sha256,
                "modelArtifactSha256": self.model_artifact_sha256,
                "handlerArtifactSha256": self.handler_artifact_sha256,
            },
            "requestedActions": [item.value for item in requested_actions],
            "thresholds": {
                "minExpertFeedback": self.min_expert_feedback,
                "minProductionLikeFeedback": self.min_production_like_feedback,
                "minAccuracy": self.min_accuracy,
                "minActionFeedback": self.min_action_feedback,
            },
        }
        replay_digest = hashlib.sha256(
            json.dumps(
                replay_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            ).encode("utf-8")
        ).hexdigest()
        unique_blocking = list(dict.fromkeys(blocking))
        qualified = not unique_blocking and not test_only
        report_id = stable_assist_id(
            "assist-qualification",
            replay_digest,
            self.shadow.feature_builder.feature_schema_hash,
            runtime_name,
            runtime_version,
            str(model_generation),
            str(state_generation),
            now.isoformat(),
        )
        report = AssistQualificationReport(
            report_id=report_id,
            feature_schema_hash=self.shadow.feature_builder.feature_schema_hash,
            runtime_name=runtime_name,
            runtime_version=runtime_version,
            runtime_artifact_sha256=self.runtime_artifact_sha256,
            model_artifact_sha256=self.model_artifact_sha256,
            handler_artifact_sha256=self.handler_artifact_sha256,
            model_generation=model_generation,
            state_generation=state_generation,
            replay_digest=replay_digest,
            total_feedback_count=len(feedback),
            eligible_feedback_count=eligible_count,
            expert_feedback_count=expert_count,
            production_like_feedback_count=production_like_count,
            rill_accuracy=rill_accuracy,
            static_accuracy=static_accuracy,
            rill_accept_on_p0_p1=severe_accepts,
            active_drift_alerts=drift_state.alert_count,
            action_feedback_counts=action_feedback_counts,
            requested_actions=requested_actions,
            qualified_actions=requested_actions if qualified else [],
            qualified=qualified,
            blocking_reasons=unique_blocking,
            attestation_ids=sorted(item.attestation_id for item in eligible_attestations),
            test_only=test_only,
            created_at=now,
            expires_at=now + timedelta(hours=self.qualification_ttl_hours),
        )
        return self.store.commit_qualification(report)

    def activate(self, request: AssistActivationRequest) -> AssistActivationRecord:
        report = self.store.read_qualification(request.qualification_report_id)
        now = datetime.now(timezone.utc)
        if not report.qualified or report.test_only:
            raise RillAssistQualificationError("qualification report is not approved for Assist")
        if report.expires_at <= now or request.expires_at > report.expires_at:
            raise RillAssistQualificationError("qualification or requested activation has expired")
        if not set(request.allowed_actions).issubset(report.qualified_actions):
            raise RillAssistQualificationError("activation exceeds qualified action allowlist")
        identity = self._require_matching_runtime(report)
        activation_id = stable_assist_id(
            "assist-activation",
            report.report_id,
            report.semantic_digest(),
            request.approver_id_hash,
            ",".join(sorted(item.value for item in request.allowed_actions)),
            request.expires_at.isoformat(),
        )
        if not all((
            report.runtime_artifact_sha256,
            report.model_artifact_sha256,
            report.handler_artifact_sha256,
        )):
            raise RillAssistQualificationError(
                "qualified report does not bind fixed Runtime, model, and handler digests"
            )
        record = AssistActivationRecord(
            activation_id=activation_id,
            qualification_report_id=report.report_id,
            qualification_digest=report.semantic_digest(),
            approver_id_hash=request.approver_id_hash,
            allowed_actions=request.allowed_actions,
            max_executions_per_hour=request.max_executions_per_hour,
            runtime_name=identity.name,
            runtime_version=identity.version,
            runtime_artifact_sha256=report.runtime_artifact_sha256,
            model_artifact_sha256=report.model_artifact_sha256,
            handler_artifact_sha256=report.handler_artifact_sha256,
            model_generation=report.model_generation,
            minimum_state_generation=report.state_generation,
            feature_schema_hash=report.feature_schema_hash,
            expires_at=request.expires_at,
        )
        return self.store.commit_activation(record)

    def revoke(self, request: AssistRevocationRequest) -> AssistRevocationRecord:
        self.store.read_activation(request.activation_id)
        existing = self.store.revocation_for_activation(request.activation_id)
        revocation_id = stable_assist_id("assist-revocation", request.activation_id)
        candidate = AssistRevocationRecord(
            revocation_id=revocation_id,
            activation_id=request.activation_id,
            operator_id_hash=request.operator_id_hash,
            reason_code=request.reason_code,
        )
        if existing is not None:
            if existing.semantic_digest() != candidate.semantic_digest():
                raise RillAssistQualificationError("activation already has a different revocation")
            return existing
        return self.store.commit_revocation(candidate)

    def suspend_parser(
        self, request: AssistParserSuspensionRequest
    ) -> AssistParserSuspensionRecord:
        activation = self._validate_activation(
            request.activation_id, allow_active_drift=True
        )
        if Tier1AssistAction.QUARANTINE not in activation.allowed_actions:
            raise RillAssistQualificationError(
                "parser suspension requires an activation qualified for quarantine"
            )
        if request.parser_id == "native-pdf":
            raise RillAssistQualificationError(
                "the deterministic native PDF fallback cannot be suspended"
            )
        self.orchestrator.registry.get(request.parser_id)
        if request.expires_at > activation.expires_at:
            raise RillAssistQualificationError(
                "parser suspension cannot outlive the Assist activation"
            )
        alerts = {item.alert_id for item in self.shadow.drift.list_alerts()}
        if request.drift_alert_id not in alerts:
            raise RillAssistQualificationError(
                "parser suspension requires a verified drift alert"
            )
        if self.shadow.drift.read().alert_count <= 0:
            raise RillAssistQualificationError(
                "parser suspension requires an active drift blocker"
            )
        suspension_id = stable_assist_id(
            "assist-parser-suspension",
            activation.activation_id,
            request.parser_id,
            request.drift_alert_id,
            request.expires_at.isoformat(),
        )
        record = AssistParserSuspensionRecord(
            suspension_id=suspension_id,
            activation_id=activation.activation_id,
            parser_id=request.parser_id,
            drift_alert_id=request.drift_alert_id,
            operator_id_hash=request.operator_id_hash,
            reason_code=request.reason_code,
            expires_at=request.expires_at,
        )
        return self.store.commit_parser_suspension(record)

    def resume_parser(self, request: AssistParserResumeRequest) -> AssistParserResumeRecord:
        suspension = self.store.read_parser_suspension(request.suspension_id)
        self._validate_activation(suspension.activation_id, allow_active_drift=True)
        existing = self.store.resume_for_suspension(suspension.suspension_id)
        resume_id = stable_assist_id("assist-parser-resume", suspension.suspension_id)
        candidate = AssistParserResumeRecord(
            resume_id=resume_id,
            suspension_id=suspension.suspension_id,
            operator_id_hash=request.operator_id_hash,
            reason_code=request.reason_code,
        )
        if existing is not None:
            if existing.semantic_digest() != candidate.semantic_digest():
                raise RillAssistQualificationError(
                    "parser suspension already has a different resume record"
                )
            return existing
        return self.store.commit_parser_resume(candidate)

    def is_parser_suspended(self, parser_id: str) -> bool:
        return bool(self.store.active_parser_suspensions(parser_id))

    def execute(self, activation_id: str, evaluation_id: str) -> AssistExecutionRecord:
        activation = self._validate_activation(activation_id)
        evaluation = self.shadow.get(evaluation_id)
        if evaluation.rill_suggestion is None or evaluation.status != "succeeded":
            return self._blocked(
                activation,
                evaluation_id,
                evaluation.observe_event.parse_run_id,
                Tier1AssistAction.HUMAN_REVIEW,
                "RILL_SUGGESTION_UNAVAILABLE",
            )
        try:
            action = Tier1AssistAction(evaluation.rill_suggestion.action.value)
        except ValueError:
            return self._blocked(
                activation,
                evaluation_id,
                evaluation.observe_event.parse_run_id,
                Tier1AssistAction.HUMAN_REVIEW,
                "ACTION_NOT_TIER1",
            )
        execution_id = stable_assist_id(
            "assist-execution",
            activation.activation_id,
            evaluation.evaluation_id,
            action.value,
            evaluation.rill_suggestion.decision_id,
        )
        with self.store.activation_lock(activation.activation_id):
            # Activation, revocation, Runtime identity, drift, rate and idempotency
            # are rechecked under the same lock used to commit the execution.
            activation = self._validate_activation(activation_id)
            try:
                return self.store.read_execution(execution_id)
            except FileNotFoundError:
                pass
            source_run_id = evaluation.observe_event.parse_run_id
            if action not in activation.allowed_actions:
                return self._blocked(
                    activation,
                    evaluation_id,
                    source_run_id,
                    action,
                    "ACTION_NOT_ACTIVATED",
                    execution_id=execution_id,
                )
            try:
                self._check_live_safety(evaluation)
                self._check_rate_limit(activation)
            except RillAssistExecutionError as exc:
                code = (
                    "ASSIST_RATE_LIMIT_REACHED"
                    if "rate limit" in str(exc).lower()
                    else "ASSIST_LIVE_SAFETY_BLOCKED"
                )
                return self._blocked(
                    activation,
                    evaluation_id,
                    source_run_id,
                    action,
                    code,
                    execution_id=execution_id,
                )

            if action in {Tier1AssistAction.HUMAN_REVIEW, Tier1AssistAction.QUARANTINE}:
                queue = (
                    AssistQueueKind.HUMAN_REVIEW
                    if action == Tier1AssistAction.HUMAN_REVIEW
                    else AssistQueueKind.QUARANTINE
                )
                queue_item_id = stable_assist_id("assist-queue", execution_id, queue.value)
                priority = self._queue_priority(evaluation, queue)
                item = AssistQueueItem(
                    queue_item_id=queue_item_id,
                    execution_id=execution_id,
                    queue=queue,
                    priority=priority,
                    evaluation_id=evaluation_id,
                    parse_run_id=source_run_id,
                    reason_codes=list(evaluation.rill_suggestion.reason_codes),
                )
                self.store.commit_queue_item(item)
                record = AssistExecutionRecord(
                    execution_id=execution_id,
                    activation_id=activation.activation_id,
                    qualification_report_id=activation.qualification_report_id,
                    evaluation_id=evaluation_id,
                    action=action,
                    status=AssistExecutionStatus.SUCCEEDED,
                    source_run_id=source_run_id,
                    queue_item_id=queue_item_id,
                    reason_codes=["ADDITIVE_QUEUE_ITEM_CREATED"],
                )
                return self.store.commit_execution(record)

            try:
                result, parser_id = self._execute_parser_action(action, evaluation)
                record = AssistExecutionRecord(
                    execution_id=execution_id,
                    activation_id=activation.activation_id,
                    qualification_report_id=activation.qualification_report_id,
                    evaluation_id=evaluation_id,
                    action=action,
                    status=AssistExecutionStatus.SUCCEEDED,
                    source_run_id=source_run_id,
                    output_run_id=result.run.parse_run_id,
                    parser_id=parser_id,
                    reason_codes=["ADDITIVE_CANDIDATE_RUN_CREATED"],
                )
            except Exception:
                record = AssistExecutionRecord(
                    execution_id=execution_id,
                    activation_id=activation.activation_id,
                    qualification_report_id=activation.qualification_report_id,
                    evaluation_id=evaluation_id,
                    action=action,
                    status=AssistExecutionStatus.FAILED,
                    source_run_id=source_run_id,
                    reason_codes=["PARSER_ACTION_FAILED_SAFELY"],
                    error_code="ASSIST_PARSER_ACTION_FAILED",
                )
            return self.store.commit_execution(record)

    def inspect(self) -> dict[str, Any]:
        activations = self.store.list_activations()
        active = []
        now = datetime.now(timezone.utc)
        for item in activations:
            revoked = self.store.revocation_for_activation(item.activation_id) is not None
            if not revoked and item.expires_at > now:
                active.append(item.activation_id)
        return {
            "assistSchemaVersion": "0.6",
            "boundedAuto": False,
            "tier1Actions": [item.value for item in Tier1AssistAction],
            "activeActivations": active,
            "qualificationReports": len(self.store.list_qualifications()),
            "executions": len(self.store.list_executions()),
            "queueItems": len(self.store.list_queue_items()),
            "activeParserSuspensions": [
                item.parser_id for item in self.store.active_parser_suspensions()
            ],
        }

    def _require_matching_runtime(self, report: AssistQualificationReport):
        if self.shadow.client is None:
            raise RillAssistQualificationError("real Rill runtime is unavailable")
        identity = self.shadow.client.identity
        if "reference" in identity.name.lower():
            raise RillAssistQualificationError("reference runtime cannot activate Assist")
        if (
            identity.name != report.runtime_name
            or identity.version != report.runtime_version
            or identity.feature_schema_hash != report.feature_schema_hash
            or report.runtime_artifact_sha256 != self.runtime_artifact_sha256
            or report.model_artifact_sha256 != self.model_artifact_sha256
            or report.handler_artifact_sha256 != self.handler_artifact_sha256
            or self.shadow.client.model_generation != report.model_generation
            or self.shadow.client.state_generation < report.state_generation
        ):
            raise RillAssistQualificationError("Rill runtime identity or generation changed")
        if not self._runtime_artifact_attestation_matches():
            raise RillAssistQualificationError(
                "Rill runtime did not attest the configured Runtime, model, and handler digests"
            )
        return identity

    def _runtime_artifact_attestation_matches(self) -> bool:
        if self.shadow.client is None:
            return False
        try:
            summary = self.shadow.client.inspect()
        except Exception:
            return False
        digests = summary.get("artifactDigests")
        if not isinstance(digests, dict):
            return False
        return (
            digests.get("runtimeSha256") == self.runtime_artifact_sha256
            and digests.get("modelSha256") == self.model_artifact_sha256
            and digests.get("handlerSha256") == self.handler_artifact_sha256
        )

    def _validate_activation(
        self, activation_id: str, *, allow_active_drift: bool = False
    ) -> AssistActivationRecord:
        activation = self.store.read_activation(activation_id)
        now = datetime.now(timezone.utc)
        if activation.expires_at <= now:
            raise RillAssistQualificationError("Assist activation expired")
        if self.store.revocation_for_activation(activation.activation_id) is not None:
            raise RillAssistQualificationError("Assist activation was revoked")
        report = self.store.read_qualification(activation.qualification_report_id)
        if report.semantic_digest() != activation.qualification_digest:
            raise RillAssistQualificationError("qualification digest changed")
        identity = self._require_matching_runtime(report)
        if (
            identity.name != activation.runtime_name
            or identity.version != activation.runtime_version
            or identity.feature_schema_hash != activation.feature_schema_hash
            or self.shadow.client is None
            or activation.runtime_artifact_sha256 != self.runtime_artifact_sha256
            or activation.model_artifact_sha256 != self.model_artifact_sha256
            or activation.handler_artifact_sha256 != self.handler_artifact_sha256
            or self.shadow.client.model_generation != activation.model_generation
            or self.shadow.client.state_generation < activation.minimum_state_generation
        ):
            raise RillAssistQualificationError("active Runtime no longer matches activation")
        if not allow_active_drift and self.shadow.drift.read().alert_count > 0:
            raise RillAssistQualificationError("active drift blocker prevents Assist")
        return activation

    def _check_live_safety(self, evaluation) -> None:
        signals = evaluation.observe_event.signals
        action = evaluation.rill_suggestion.action
        severe = (
            signals.parse.p0_warnings > 0
            or signals.parse.p1_warnings > 0
            or (signals.structure is not None and signals.structure.diagnostics_error > 0)
            or (signals.domain is not None and signals.domain.error_findings > 0)
        )
        if severe and action not in {ShadowAction.HUMAN_REVIEW, ShadowAction.QUARANTINE}:
            raise RillAssistExecutionError(
                "critical signals require review or quarantine, not an automatic parser action"
            )
        metrics = self.shadow.replay.metrics()
        if metrics.rill_accept_on_p0_p1 > 0:
            raise RillAssistExecutionError("live replay contains severe false ACCEPT")
        if metrics.rill_accuracy is None or metrics.rill_accuracy < self.min_accuracy:
            raise RillAssistExecutionError("live Rill replay accuracy is below threshold")
        if (
            metrics.static_accuracy is not None
            and metrics.rill_accuracy < metrics.static_accuracy
        ):
            raise RillAssistExecutionError("live Rill replay fell below static baseline")

    def _check_rate_limit(self, activation: AssistActivationRecord) -> None:
        since = datetime.now(timezone.utc) - timedelta(hours=1)
        recent_count = len(
            self.store.executions_since(activation.activation_id, since)
        )
        if recent_count >= activation.max_executions_per_hour:
            raise RillAssistExecutionError("Assist activation rate limit reached")

    def _execute_parser_action(self, action: Tier1AssistAction, evaluation):
        source = self.orchestrator.store.read_result(evaluation.observe_event.parse_run_id)
        source_ref = source.document.source.source_ref
        if source_ref is None:
            raise FileNotFoundError("retained source is missing")
        content = self.orchestrator.store.read_source(source_ref)
        base = ParseRequest(
            filename=source.document.source.filename,
            mime_type=source.document.source.mime_type,
            content=content,
            domain_pack=source.run.domain_pack,
            options={
                "assist_parent_run_id": source.run.parse_run_id,
                "assist_action": action.value,
                "assist_additive_candidate": True,
            },
        )
        parser = self._select_parser(action, base, source.run.parser_id)
        request = base.model_copy(update={"parser_id": parser.parser_id})
        return self.orchestrator.parse(request), parser.parser_id

    def _select_parser(self, action: Tier1AssistAction, request: ParseRequest, original_id: str):
        candidates = []
        for parser in self.orchestrator.registry.candidates(request):
            health = parser.health()
            config = getattr(parser, "config", None)
            if not health.available or not health.enabled:
                continue
            if self.orchestrator.is_parser_suspended(parser.parser_id):
                continue
            if bool(getattr(config, "benchmark_only", False)):
                continue
            candidates.append(
                (
                    int(getattr(parser, "priority", 100)),
                    parser,
                    set(health.capabilities),
                )
            )
        candidates.sort(key=lambda item: (item[0], item[1].parser_id))
        if action == Tier1AssistAction.RETRY:
            if self.orchestrator.is_parser_suspended(original_id):
                raise ParserUnavailableError(
                    f"original parser is suspended: {original_id}"
                )
            return self.orchestrator.registry.get(original_id)
        if action == Tier1AssistAction.USE_SECONDARY_PARSER:
            for _, parser, _ in candidates:
                if parser.parser_id != original_id:
                    return parser
        elif action == Tier1AssistAction.REPROCESS_HIGH_RES:
            for _, parser, capabilities in candidates:
                if "high-resolution-reprocess" in capabilities:
                    return parser
        elif action == Tier1AssistAction.USE_SPECIALIST_PARSER:
            specialist = {
                "specialist",
                "specialist-parser",
                "formula-specialist",
                "table-specialist",
                "layout-specialist",
            }
            for _, parser, capabilities in candidates:
                if capabilities & specialist:
                    return parser
        raise ParserUnavailableError(f"no qualified parser is available for {action.value}")

    @staticmethod
    def _queue_priority(evaluation, queue: AssistQueueKind) -> int:
        if queue == AssistQueueKind.QUARANTINE:
            return 100
        parse = evaluation.observe_event.signals.parse
        priority = 50 + min(30, parse.p1_warnings * 10 + parse.p0_warnings * 20)
        if evaluation.observe_event.signals.domain is not None:
            priority += min(10, evaluation.observe_event.signals.domain.error_findings * 5)
        return min(99, priority)

    def _blocked(
        self,
        activation: AssistActivationRecord,
        evaluation_id: str,
        source_run_id: str,
        action: Tier1AssistAction,
        error_code: str,
        *,
        execution_id: str | None = None,
    ) -> AssistExecutionRecord:
        identifier = execution_id or stable_assist_id(
            "assist-execution", activation.activation_id, evaluation_id, action.value, error_code
        )
        record = AssistExecutionRecord(
            execution_id=identifier,
            activation_id=activation.activation_id,
            qualification_report_id=activation.qualification_report_id,
            evaluation_id=evaluation_id,
            action=action,
            status=AssistExecutionStatus.BLOCKED,
            source_run_id=source_run_id,
            reason_codes=["ASSIST_EXECUTION_BLOCKED"],
            error_code=error_code,
        )
        return self.store.commit_execution(record)
