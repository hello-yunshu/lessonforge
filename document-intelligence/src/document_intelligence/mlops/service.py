from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

from document_intelligence.exceptions import MLOpsGateError
from document_intelligence.mlops.active_learning import ActiveLearningSelector
from document_intelligence.mlops.models import (
    ActiveLearningBatch,
    AliasUpdateRecord,
    ApprovalRequest,
    CandidateEvaluationReport,
    CandidateRegistrationRequest,
    DatasetRole,
    DatasetSnapshot,
    DatasetSnapshotRequest,
    EvaluationRequest,
    ExperimentStatus,
    MLflowRunRecord,
    MLflowRunRequest,
    ModelAlias,
    ModelCandidate,
    PromoteRequest,
    ReleaseApproval,
    RollbackRecord,
    RollbackRequest,
    ShadowValidationReport,
    ShadowValidationRequest,
    stable_mlops_id,
)
from document_intelligence.mlops.store import MLOpsStore
from document_intelligence.rill.assist_store import RillAssistStore
from document_intelligence.rill.store import RillShadowStore


class MLOpsService:
    """Auditable Phase-7 lifecycle; never trains or deploys arbitrary code."""

    def __init__(
        self,
        store: MLOpsStore,
        shadow_store: RillShadowStore,
        assist_store: RillAssistStore,
        *,
        minimum_accuracy: float = 0.90,
        minimum_challenge_improvement: float = 0.0,
        maximum_latency_ms_p95: float = 30000.0,
        maximum_cost_usd_per_document: float = 10.0,
        maximum_family_regression: float = 0.02,
        minimum_shadow_samples: int = 100,
    ) -> None:
        self.store = store
        self.shadow_store = shadow_store
        self.assist_store = assist_store
        self.selector = ActiveLearningSelector()
        self.minimum_accuracy = minimum_accuracy
        self.minimum_challenge_improvement = minimum_challenge_improvement
        self.maximum_latency_ms_p95 = maximum_latency_ms_p95
        self.maximum_cost_usd_per_document = maximum_cost_usd_per_document
        self.maximum_family_regression = maximum_family_regression
        self.minimum_shadow_samples = minimum_shadow_samples

    def select_active_learning(
        self, *, max_items: int = 100, max_per_family: int = 20
    ) -> ActiveLearningBatch:
        approved_feedback_ids = {
            item.feedback_id
            for item in self.assist_store.list_attestations()
            if item.approved_for_qualification
        }
        feedback_by_eval = {
            item.evaluation_id: item.feedback_id
            for item in self.shadow_store.list_feedback()
        }
        excluded = {
            evaluation_id
            for evaluation_id, feedback_id in feedback_by_eval.items()
            if feedback_id in approved_feedback_ids
        }
        excluded.update(
            selection.evaluation_id
            for batch in self.store.list_active_learning()
            for selection in batch.selections
        )
        suspended_parsers = {
            item.parser_id for item in self.assist_store.active_parser_suspensions()
        }
        batch = self.selector.select(
            self.shadow_store.list_evaluations(),
            excluded_evaluation_ids=excluded,
            active_drift_parser_ids=suspended_parsers,
            max_items=max_items,
            max_per_family=max_per_family,
        )
        return self.store.commit_active_learning(batch)

    def create_snapshot(self, request: DatasetSnapshotRequest) -> DatasetSnapshot:
        if request.role in {DatasetRole.GOLD, DatasetRole.CHALLENGE}:
            if not request.expert_approved or request.approver_id_hash is None:
                raise MLOpsGateError(
                    "gold and challenge snapshots require expert approval"
                )
        if request.parent_snapshot_id is not None:
            parent = self.store.read_snapshot(request.parent_snapshot_id)
            if parent.dataset_name != request.dataset_name:
                raise MLOpsGateError("dataset parent must belong to the same dataset")
            if parent.role != request.role:
                raise MLOpsGateError("dataset parent must preserve the dataset role")
        snapshot_id = stable_mlops_id(
            "dataset",
            request.role.value,
            request.dataset_name,
            request.dvc_repo_revision,
            request.dvc_data_hash,
            request.manifest_sha256,
            request.schema_sha256,
        )
        return self.store.commit_snapshot(
            DatasetSnapshot(snapshot_id=snapshot_id, **request.model_dump(mode="python"))
        )

    def record_mlflow_run(self, request: MLflowRunRequest) -> MLflowRunRecord:
        snapshots = [self.store.read_snapshot(item) for item in request.dataset_snapshot_ids]
        if not any(item.role == DatasetRole.TRAIN for item in snapshots):
            raise MLOpsGateError("MLflow training record must bind a train snapshot")
        if any(item.role in {DatasetRole.GOLD, DatasetRole.CHALLENGE} for item in snapshots):
            raise MLOpsGateError("training runs cannot bind gold or challenge snapshots")
        record_id = stable_mlops_id(
            "mlflow",
            request.experiment_id,
            request.run_id,
            request.model_artifact_sha256,
            request.params_sha256,
        )
        return self.store.commit_mlflow_run(
            MLflowRunRecord(record_id=record_id, **request.model_dump(mode="python"))
        )

    def register_candidate(
        self, request: CandidateRegistrationRequest
    ) -> ModelCandidate:
        run = self.store.read_mlflow_run(request.mlflow_record_id)
        if run.status != ExperimentStatus.FINISHED:
            raise MLOpsGateError("candidate requires a finished MLflow run")
        if run.model_artifact_sha256 != request.model_artifact_sha256:
            raise MLOpsGateError("candidate artifact digest differs from MLflow lineage")
        if run.source_commit_sha != request.source_commit_sha:
            raise MLOpsGateError("candidate source commit differs from MLflow lineage")
        train = self.store.read_snapshot(request.train_snapshot_id)
        if train.role != DatasetRole.TRAIN:
            raise MLOpsGateError("candidate train snapshot has the wrong role")
        if train.snapshot_id not in run.dataset_snapshot_ids:
            raise MLOpsGateError("MLflow run does not bind candidate train snapshot")
        if request.validation_snapshot_id is not None:
            validation = self.store.read_snapshot(request.validation_snapshot_id)
            if validation.role != DatasetRole.VALIDATION:
                raise MLOpsGateError("candidate validation snapshot has the wrong role")
            if validation.snapshot_id not in run.dataset_snapshot_ids:
                raise MLOpsGateError("MLflow run does not bind validation snapshot")
        if request.baseline_candidate_id is not None:
            self.store.read_candidate(request.baseline_candidate_id)
        candidate_id = stable_mlops_id(
            "candidate",
            request.model_family,
            request.model_version,
            request.model_artifact_sha256,
            request.source_commit_sha,
        )
        candidate = self.store.commit_candidate(
            ModelCandidate(candidate_id=candidate_id, **request.model_dump(mode="python"))
        )
        with self.store.control_lock():
            aliases = self.store.aliases()
            previous = aliases.get(ModelAlias.CANDIDATE)
            update = self._alias_update(
                ModelAlias.CANDIDATE,
                candidate.candidate_id,
                previous_candidate_id=previous,
                operator_id_hash=hashlib.sha256(b"system:candidate-registration").hexdigest(),
                reason_code="CANDIDATE_REGISTERED",
            )
            self.store.commit_alias_update(update)
            aliases[ModelAlias.CANDIDATE] = candidate.candidate_id
            self.store.update_aliases(aliases)
        return candidate

    def evaluate(self, request: EvaluationRequest) -> CandidateEvaluationReport:
        candidate = self.store.read_candidate(request.candidate_id)
        if request.baseline_candidate_id != candidate.baseline_candidate_id:
            raise MLOpsGateError("evaluation baseline differs from candidate registration")
        gold = self.store.read_snapshot(request.gold_snapshot_id)
        challenge = self.store.read_snapshot(request.challenge_snapshot_id)
        if gold.role != DatasetRole.GOLD or not gold.expert_approved:
            raise MLOpsGateError("evaluation requires an approved gold snapshot")
        if challenge.role != DatasetRole.CHALLENGE or not challenge.expert_approved:
            raise MLOpsGateError("evaluation requires an approved challenge snapshot")
        if gold.dvc_data_hash == challenge.dvc_data_hash:
            raise MLOpsGateError("gold and challenge snapshots must be data-disjoint")
        run = self.store.read_mlflow_run(candidate.mlflow_record_id)
        training_hashes = {
            self.store.read_snapshot(item).dvc_data_hash
            for item in run.dataset_snapshot_ids
        }
        if gold.dvc_data_hash in training_hashes or challenge.dvc_data_hash in training_hashes:
            raise MLOpsGateError("protected evaluation data cannot appear in training lineage")
        if request.baseline_candidate_id is not None:
            self.store.read_candidate(request.baseline_candidate_id)
        blocking = self._evaluation_blocks(request)
        report_id = stable_mlops_id(
            "evaluation",
            request.candidate_id,
            request.gold_snapshot_id,
            request.challenge_snapshot_id,
            request.reproducibility_sha256,
            request.evaluation_config_sha256,
        )
        report = CandidateEvaluationReport(
            report_id=report_id,
            **request.model_dump(mode="python"),
            minimum_accuracy=self.minimum_accuracy,
            minimum_challenge_improvement=self.minimum_challenge_improvement,
            maximum_latency_ms_p95=self.maximum_latency_ms_p95,
            maximum_cost_usd_per_document=self.maximum_cost_usd_per_document,
            maximum_family_regression=self.maximum_family_regression,
            passed=not blocking,
            blocking_reasons=blocking,
        )
        return self.store.commit_evaluation(report)

    def record_shadow_validation(
        self, request: ShadowValidationRequest
    ) -> ShadowValidationReport:
        aliases = self.store.aliases()
        if aliases.get(ModelAlias.SHADOW) != request.candidate_id:
            raise MLOpsGateError("Shadow validation requires the active Shadow candidate")
        report = self.store.read_evaluation(request.evaluation_report_id)
        if not report.passed or report.candidate_id != request.candidate_id:
            raise MLOpsGateError("Shadow validation requires the candidate's passing evaluation")
        blocking: list[str] = []
        if request.sample_count < self.minimum_shadow_samples:
            blocking.append("SHADOW_SAMPLE_COUNT_BELOW_MINIMUM")
        if request.p0_errors:
            blocking.append("SHADOW_P0_ERRORS")
        if request.p1_errors:
            blocking.append("SHADOW_P1_ERRORS")
        if request.severe_error_rate > 0:
            blocking.append("SHADOW_SEVERE_ERRORS")
        if request.accuracy < self.minimum_accuracy:
            blocking.append("SHADOW_ACCURACY_BELOW_MINIMUM")
        if request.latency_ms_p95 > self.maximum_latency_ms_p95:
            blocking.append("SHADOW_LATENCY_OVER_BUDGET")
        if request.cost_usd_per_document > self.maximum_cost_usd_per_document:
            blocking.append("SHADOW_COST_OVER_BUDGET")
        if request.active_drift_alerts:
            blocking.append("SHADOW_ACTIVE_DRIFT")
        report_id = stable_mlops_id(
            "shadow-validation",
            request.candidate_id,
            request.evaluation_report_id,
            request.evidence_sha256,
        )
        return self.store.commit_shadow_validation(
            ShadowValidationReport(
                report_id=report_id,
                **request.model_dump(mode="python"),
                passed=not blocking,
                blocking_reasons=sorted(set(blocking)),
            )
        )

    def approve(self, request: ApprovalRequest) -> ReleaseApproval:
        report = self.store.read_evaluation(request.evaluation_report_id)
        if report.candidate_id != request.candidate_id or not report.passed:
            raise MLOpsGateError("only a passing candidate evaluation can be approved")
        if request.shadow_validation_report_id is not None:
            shadow = self.store.read_shadow_validation(request.shadow_validation_report_id)
            if not shadow.passed or shadow.candidate_id != request.candidate_id:
                raise MLOpsGateError("release approval requires a passing Shadow validation")
            if shadow.evaluation_report_id != request.evaluation_report_id:
                raise MLOpsGateError("Shadow validation and offline evaluation do not match")
        approval_id = stable_mlops_id(
            "approval",
            request.candidate_id,
            request.evaluation_report_id,
            request.shadow_validation_report_id or "none",
            request.approver_id_hash,
            request.approver_role,
        )
        return self.store.commit_approval(
            ReleaseApproval(approval_id=approval_id, **request.model_dump(mode="python"))
        )

    def promote_to_shadow(self, request: PromoteRequest) -> AliasUpdateRecord:
        if request.shadow_validation_report_id is not None:
            raise MLOpsGateError("Shadow promotion cannot use a pre-existing Shadow validation")
        return self._promote(ModelAlias.SHADOW, request)

    def promote_to_champion(self, request: PromoteRequest) -> AliasUpdateRecord:
        with self.store.control_lock():
            aliases = self.store.aliases()
            if aliases.get(ModelAlias.SHADOW) != request.candidate_id:
                raise MLOpsGateError("candidate must complete Shadow before Champion promotion")
            if request.shadow_validation_report_id is None:
                raise MLOpsGateError("Champion promotion requires a Shadow validation report")
            shadow = self.store.read_shadow_validation(
                request.shadow_validation_report_id
            )
            if not shadow.passed or shadow.candidate_id != request.candidate_id:
                raise MLOpsGateError("Champion promotion requires a passing Shadow validation")
            if shadow.evaluation_report_id != request.evaluation_report_id:
                raise MLOpsGateError("Shadow validation does not match the offline evaluation")
            previous_champion = aliases.get(ModelAlias.CHAMPION)
            update = self._validate_and_create_promotion(
                ModelAlias.CHAMPION,
                request,
                previous_candidate_id=previous_champion,
            )
            self.store.commit_alias_update(update)
            if previous_champion is not None:
                rollback_update = self._alias_update(
                    ModelAlias.ROLLBACK,
                    previous_champion,
                    previous_candidate_id=aliases.get(ModelAlias.ROLLBACK),
                    evaluation_report_id=request.evaluation_report_id,
                    approval_id=request.approval_id,
                    operator_id_hash=request.operator_id_hash,
                    reason_code="CHAMPION_PREDECESSOR",
                )
                self.store.commit_alias_update(rollback_update)
                aliases[ModelAlias.ROLLBACK] = previous_champion
            aliases[ModelAlias.CHAMPION] = request.candidate_id
            self.store.update_aliases(aliases)
            return update

    def rollback(self, request: RollbackRequest) -> RollbackRecord:
        with self.store.control_lock():
            aliases = self.store.aliases()
            current = aliases.get(ModelAlias.CHAMPION)
            target = aliases.get(ModelAlias.ROLLBACK)
            if current is None or target is None:
                raise MLOpsGateError("rollback requires champion and rollback aliases")
            update = self._alias_update(
                ModelAlias.CHAMPION,
                target,
                previous_candidate_id=current,
                operator_id_hash=request.operator_id_hash,
                reason_code=request.reason_code,
            )
            self.store.commit_alias_update(update)
            aliases[ModelAlias.CHAMPION] = target
            aliases[ModelAlias.ROLLBACK] = current
            self.store.update_aliases(aliases)
            rollback_id = stable_mlops_id(
                "rollback", current, target, update.update_id, request.operator_id_hash
            )
            return self.store.commit_rollback(
                RollbackRecord(
                    rollback_id=rollback_id,
                    from_candidate_id=current,
                    to_candidate_id=target,
                    operator_id_hash=request.operator_id_hash,
                    reason_code=request.reason_code,
                    alias_update_id=update.update_id,
                )
            )

    def lineage(self, candidate_id: str) -> dict[str, object]:
        candidate = self.store.read_candidate(candidate_id)
        run = self.store.read_mlflow_run(candidate.mlflow_record_id)
        snapshots = [
            self.store.read_snapshot(item).model_dump(mode="json")
            for item in run.dataset_snapshot_ids
        ]
        evaluations = [
            item.model_dump(mode="json")
            for item in self.store.list_evaluations()
            if item.candidate_id == candidate_id
        ]
        shadow_validations = [
            item.model_dump(mode="json")
            for item in self.store.list_shadow_validations()
            if item.candidate_id == candidate_id
        ]
        approvals = [
            item.model_dump(mode="json")
            for item in self.store.list_approvals()
            if item.candidate_id == candidate_id
        ]
        alias_updates = [
            item.model_dump(mode="json")
            for item in self.store.list_alias_updates()
            if item.candidate_id == candidate_id
            or item.previous_candidate_id == candidate_id
        ]
        return {
            "candidate": candidate.model_dump(mode="json"),
            "mlflowRun": run.model_dump(mode="json"),
            "datasetSnapshots": snapshots,
            "evaluations": evaluations,
            "shadowValidations": shadow_validations,
            "approvals": approvals,
            "aliasUpdates": alias_updates,
        }

    def inspect(self) -> dict[str, object]:
        aliases = {key.value: value for key, value in self.store.aliases().items()}
        return {
            "schemaVersion": "0.7",
            "boundedAuto": False,
            "activeLearningBatches": len(self.store.list_active_learning()),
            "datasetSnapshots": len(self.store.list_snapshots()),
            "mlflowRuns": len(self.store.list_mlflow_runs()),
            "candidates": len(self.store.list_candidates()),
            "evaluations": len(self.store.list_evaluations()),
            "shadowValidations": len(self.store.list_shadow_validations()),
            "approvals": len(self.store.list_approvals()),
            "aliases": aliases,
            "rollbacks": len(self.store.list_rollbacks()),
        }

    def _promote(self, alias: ModelAlias, request: PromoteRequest) -> AliasUpdateRecord:
        with self.store.control_lock():
            aliases = self.store.aliases()
            previous = aliases.get(alias)
            update = self._validate_and_create_promotion(
                alias, request, previous_candidate_id=previous
            )
            self.store.commit_alias_update(update)
            aliases[alias] = request.candidate_id
            self.store.update_aliases(aliases)
            return update

    def _validate_and_create_promotion(
        self,
        alias: ModelAlias,
        request: PromoteRequest,
        *,
        previous_candidate_id: str | None,
    ) -> AliasUpdateRecord:
        self.store.read_candidate(request.candidate_id)
        report = self.store.read_evaluation(request.evaluation_report_id)
        approval = self.store.read_approval(request.approval_id)
        if not report.passed or report.candidate_id != request.candidate_id:
            raise MLOpsGateError("promotion requires the candidate's passing evaluation")
        if (
            approval.candidate_id != request.candidate_id
            or approval.evaluation_report_id != report.report_id
            or approval.shadow_validation_report_id
            != request.shadow_validation_report_id
        ):
            raise MLOpsGateError("promotion approval does not match candidate evidence")
        return self._alias_update(
            alias,
            request.candidate_id,
            previous_candidate_id=previous_candidate_id,
            evaluation_report_id=report.report_id,
            approval_id=approval.approval_id,
            operator_id_hash=request.operator_id_hash,
            reason_code=request.reason_code,
        )

    @staticmethod
    def _alias_update(
        alias: ModelAlias,
        candidate_id: str,
        *,
        previous_candidate_id: str | None,
        operator_id_hash: str,
        reason_code: str,
        evaluation_report_id: str | None = None,
        approval_id: str | None = None,
    ) -> AliasUpdateRecord:
        update_id = stable_mlops_id(
            "alias-update",
            alias.value,
            candidate_id,
            previous_candidate_id or "none",
            evaluation_report_id or "none",
            approval_id or "none",
            operator_id_hash,
            reason_code,
        )
        return AliasUpdateRecord(
            update_id=update_id,
            alias=alias,
            candidate_id=candidate_id,
            previous_candidate_id=previous_candidate_id,
            evaluation_report_id=evaluation_report_id,
            approval_id=approval_id,
            operator_id_hash=operator_id_hash,
            reason_code=reason_code,
        )

    def _evaluation_blocks(self, request: EvaluationRequest) -> list[str]:
        blocks: list[str] = []
        gold = request.candidate_gold
        challenge = request.candidate_challenge
        for prefix, metrics in (("GOLD", gold), ("CHALLENGE", challenge)):
            if metrics.p0_errors:
                blocks.append(f"{prefix}_P0_ERRORS")
            if metrics.p1_errors:
                blocks.append(f"{prefix}_P1_ERRORS")
            if metrics.severe_error_rate > 0:
                blocks.append(f"{prefix}_SEVERE_ERRORS")
            if metrics.accuracy < self.minimum_accuracy:
                blocks.append(f"{prefix}_ACCURACY_BELOW_MINIMUM")
            if metrics.latency_ms_p95 > self.maximum_latency_ms_p95:
                blocks.append(f"{prefix}_LATENCY_OVER_BUDGET")
            if metrics.cost_usd_per_document > self.maximum_cost_usd_per_document:
                blocks.append(f"{prefix}_COST_OVER_BUDGET")
        if request.baseline_candidate_id is not None:
            if request.baseline_gold is None or request.baseline_challenge is None:
                raise MLOpsGateError(
                    "baseline candidate requires gold and challenge metrics"
                )
            for prefix, candidate, baseline in (
                ("GOLD", gold, request.baseline_gold),
                ("CHALLENGE", challenge, request.baseline_challenge),
            ):
                if candidate.accuracy < baseline.accuracy:
                    blocks.append(f"{prefix}_ACCURACY_REGRESSION")
                if candidate.p0_errors > baseline.p0_errors:
                    blocks.append(f"{prefix}_P0_REGRESSION")
                if candidate.p1_errors > baseline.p1_errors:
                    blocks.append(f"{prefix}_P1_REGRESSION")
                if candidate.severe_error_rate > baseline.severe_error_rate:
                    blocks.append(f"{prefix}_SEVERE_ERROR_REGRESSION")
                if candidate.standard_mismatch_rate > baseline.standard_mismatch_rate:
                    blocks.append(f"{prefix}_STANDARD_MISMATCH_REGRESSION")
                if candidate.key_value_accuracy < baseline.key_value_accuracy:
                    blocks.append(f"{prefix}_KEY_VALUE_REGRESSION")
                if candidate.relation_accuracy < baseline.relation_accuracy:
                    blocks.append(f"{prefix}_RELATION_REGRESSION")
                all_families = set(candidate.family_accuracy) | set(baseline.family_accuracy)
                if any(
                    candidate.family_accuracy.get(family, 0.0)
                    + self.maximum_family_regression
                    < baseline.family_accuracy.get(family, 0.0)
                    for family in all_families
                ):
                    blocks.append(f"{prefix}_DOCUMENT_FAMILY_REGRESSION")
            if (
                challenge.accuracy
                < request.baseline_challenge.accuracy
                + self.minimum_challenge_improvement
            ):
                blocks.append("CHALLENGE_IMPROVEMENT_NOT_MET")
        return sorted(set(blocks))
