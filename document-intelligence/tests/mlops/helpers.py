from __future__ import annotations

import hashlib

from document_intelligence.mlops import MLOpsService, MLOpsStore
from document_intelligence.mlops.models import (
    CandidateRegistrationRequest,
    DatasetRole,
    DatasetSnapshotRequest,
    EvaluationRequest,
    ExperimentStatus,
    MLflowRunRequest,
    MetricSet,
)
from document_intelligence.rill.assist_store import RillAssistStore
from document_intelligence.rill.store import RillShadowStore


def sha(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def metric(accuracy: float = 0.95, *, p0: int = 0, p1: int = 0) -> MetricSet:
    return MetricSet(
        accuracy=accuracy,
        p0_errors=p0,
        p1_errors=p1,
        severe_error_rate=0.0 if not (p0 or p1) else 0.01,
        standard_mismatch_rate=0.001,
        key_value_accuracy=accuracy,
        relation_accuracy=accuracy,
        latency_ms_p95=1000.0,
        cost_usd_per_document=0.01,
        family_accuracy={"generic": accuracy},
    )


def build_service(settings) -> MLOpsService:
    return MLOpsService(
        MLOpsStore(settings.workspace),
        RillShadowStore(settings.workspace),
        RillAssistStore(settings.workspace),
    )


def snapshot(service: MLOpsService, name: str, role: DatasetRole):
    protected = role in {DatasetRole.GOLD, DatasetRole.CHALLENGE}
    return service.create_snapshot(
        DatasetSnapshotRequest(
            role=role,
            dataset_name=name,
            dvc_repo_revision="a" * 40,
            dvc_data_hash=sha(name + role.value + "data"),
            manifest_sha256=sha(name + role.value + "manifest"),
            schema_sha256=sha("schema"),
            source_commit_sha="b" * 40,
            record_count=100,
            file_count=4,
            expert_approved=protected,
            approver_id_hash=sha("expert") if protected else None,
        )
    )


def candidate(service: MLOpsService, name: str, *, baseline: str | None = None):
    train = snapshot(service, name + "-train", DatasetRole.TRAIN)
    validation = snapshot(service, name + "-validation", DatasetRole.VALIDATION)
    artifact = sha(name + "-artifact")
    run = service.record_mlflow_run(
        MLflowRunRequest(
            experiment_id="experiment-1",
            run_id=name + "-run",
            tracking_uri_sha256=sha("tracking"),
            artifact_uri_sha256=sha(name + "-uri"),
            source_commit_sha="b" * 40,
            params_sha256=sha(name + "-params"),
            model_artifact_sha256=artifact,
            dataset_snapshot_ids=[train.snapshot_id, validation.snapshot_id],
            metrics={"train_loss": 0.1},
            status=ExperimentStatus.FINISHED,
        )
    )
    return service.register_candidate(
        CandidateRegistrationRequest(
            model_family="layout",
            model_version=name,
            model_artifact_sha256=artifact,
            source_commit_sha="b" * 40,
            mlflow_record_id=run.record_id,
            train_snapshot_id=train.snapshot_id,
            validation_snapshot_id=validation.snapshot_id,
            baseline_candidate_id=baseline,
        )
    )


def evaluation(
    service: MLOpsService,
    candidate_id: str,
    *,
    baseline_id: str | None = None,
    score: float = 0.95,
    baseline_score: float = 0.94,
):
    gold = snapshot(service, candidate_id + "-gold", DatasetRole.GOLD)
    challenge = snapshot(service, candidate_id + "-challenge", DatasetRole.CHALLENGE)
    return service.evaluate(
        EvaluationRequest(
            candidate_id=candidate_id,
            baseline_candidate_id=baseline_id,
            gold_snapshot_id=gold.snapshot_id,
            challenge_snapshot_id=challenge.snapshot_id,
            candidate_gold=metric(score),
            candidate_challenge=metric(score),
            baseline_gold=metric(baseline_score) if baseline_id else None,
            baseline_challenge=metric(baseline_score) if baseline_id else None,
            evaluator_version="eval-1",
            evaluation_config_sha256=sha("eval-config"),
            reproducibility_sha256=sha(candidate_id + "repro"),
        )
    )
