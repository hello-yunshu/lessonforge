from __future__ import annotations
from document_intelligence.exceptions import MLOpsGateError

import pytest

from document_intelligence.mlops.models import (
    ApprovalRequest,
    DatasetRole,
    ModelAlias,
    PromoteRequest,
    RollbackRequest,
    ShadowValidationRequest,
)
from tests.mlops.helpers import build_service, candidate, evaluation, metric, sha, snapshot


def approve(
    service, candidate_id: str, report_id: str, shadow_report_id: str | None = None
):
    return service.approve(
        ApprovalRequest(
            candidate_id=candidate_id,
            evaluation_report_id=report_id,
            shadow_validation_report_id=shadow_report_id,
            approver_id_hash=sha("release-manager" + candidate_id),
            approver_role="release_manager",
            reason_code="ALL_GATES_PASSED",
        )
    )


def promote_request(
    candidate_id: str,
    report_id: str,
    approval_id: str,
    shadow_report_id: str | None = None,
):
    return PromoteRequest(
        candidate_id=candidate_id,
        evaluation_report_id=report_id,
        shadow_validation_report_id=shadow_report_id,
        approval_id=approval_id,
        operator_id_hash=sha("operator"),
        reason_code="APPROVED_RELEASE",
    )


def shadow_validate(service, candidate_id: str, report_id: str):
    from datetime import datetime, timedelta, timezone

    started = datetime.now(timezone.utc) - timedelta(hours=1)
    return service.record_shadow_validation(
        ShadowValidationRequest(
            candidate_id=candidate_id,
            evaluation_report_id=report_id,
            evidence_sha256=sha("shadow-" + candidate_id),
            sample_count=100,
            accuracy=0.97,
            p0_errors=0,
            p1_errors=0,
            severe_error_rate=0.0,
            latency_ms_p95=1000,
            cost_usd_per_document=0.01,
            active_drift_alerts=0,
            started_at=started,
            ended_at=started + timedelta(minutes=30),
        )
    )


def test_candidate_shadow_champion_and_one_click_rollback(settings) -> None:
    service = build_service(settings)
    first = candidate(service, "1.0.0")
    first_report = evaluation(service, first.candidate_id)
    assert first_report.passed is True
    first_approval = approve(service, first.candidate_id, first_report.report_id)
    first_shadow_request = promote_request(
        first.candidate_id, first_report.report_id, first_approval.approval_id
    )
    service.promote_to_shadow(first_shadow_request)
    first_shadow = shadow_validate(service, first.candidate_id, first_report.report_id)
    first_champion_approval = approve(
        service, first.candidate_id, first_report.report_id, first_shadow.report_id
    )
    service.promote_to_champion(
        promote_request(
            first.candidate_id,
            first_report.report_id,
            first_champion_approval.approval_id,
            first_shadow.report_id,
        )
    )

    second = candidate(service, "1.1.0", baseline=first.candidate_id)
    second_report = evaluation(
        service,
        second.candidate_id,
        baseline_id=first.candidate_id,
        score=0.97,
        baseline_score=0.95,
    )
    second_approval = approve(service, second.candidate_id, second_report.report_id)
    second_shadow_request = promote_request(
        second.candidate_id, second_report.report_id, second_approval.approval_id
    )
    service.promote_to_shadow(second_shadow_request)
    second_shadow = shadow_validate(service, second.candidate_id, second_report.report_id)
    second_champion_approval = approve(
        service, second.candidate_id, second_report.report_id, second_shadow.report_id
    )
    service.promote_to_champion(
        promote_request(
            second.candidate_id,
            second_report.report_id,
            second_champion_approval.approval_id,
            second_shadow.report_id,
        )
    )
    aliases = service.store.aliases()
    assert aliases[ModelAlias.CHAMPION] == second.candidate_id
    assert aliases[ModelAlias.ROLLBACK] == first.candidate_id

    rollback = service.rollback(
        RollbackRequest(operator_id_hash=sha("rollback-operator"), reason_code="REGRESSION")
    )
    assert rollback.from_candidate_id == second.candidate_id
    assert service.store.aliases()[ModelAlias.CHAMPION] == first.candidate_id
    assert service.store.aliases()[ModelAlias.ROLLBACK] == second.candidate_id
    assert service.inspect()["boundedAuto"] is False


def test_champion_cannot_skip_shadow(settings) -> None:
    service = build_service(settings)
    item = candidate(service, "1.0.0")
    report = evaluation(service, item.candidate_id)
    approval = approve(service, item.candidate_id, report.report_id)
    with pytest.raises(MLOpsGateError, match="complete Shadow"):
        service.promote_to_champion(
            promote_request(item.candidate_id, report.report_id, approval.approval_id)
        )


def test_regressing_candidate_fails_and_cannot_be_approved(settings) -> None:
    service = build_service(settings)
    baseline = candidate(service, "1.0.0")
    item = candidate(service, "0.9.0", baseline=baseline.candidate_id)
    report = evaluation(
        service,
        item.candidate_id,
        baseline_id=baseline.candidate_id,
        score=0.90,
        baseline_score=0.95,
    )
    assert report.passed is False
    assert "GOLD_ACCURACY_REGRESSION" in report.blocking_reasons
    with pytest.raises(MLOpsGateError, match="passing"):
        approve(service, item.candidate_id, report.report_id)


def test_champion_requires_passing_shadow_validation_and_second_approval(settings) -> None:
    service = build_service(settings)
    item = candidate(service, "2.0.0")
    report = evaluation(service, item.candidate_id)
    offline_approval = approve(service, item.candidate_id, report.report_id)
    service.promote_to_shadow(
        promote_request(item.candidate_id, report.report_id, offline_approval.approval_id)
    )
    with pytest.raises(MLOpsGateError, match="Shadow validation"):
        service.promote_to_champion(
            promote_request(item.candidate_id, report.report_id, offline_approval.approval_id)
        )
    shadow = shadow_validate(service, item.candidate_id, report.report_id)
    with pytest.raises(MLOpsGateError, match="candidate evidence"):
        service.promote_to_champion(
            promote_request(
                item.candidate_id,
                report.report_id,
                offline_approval.approval_id,
                shadow.report_id,
            )
        )


def test_shadow_validation_blocks_small_or_severe_observation(settings) -> None:
    from datetime import datetime, timedelta, timezone

    service = build_service(settings)
    item = candidate(service, "3.0.0")
    report = evaluation(service, item.candidate_id)
    offline = approve(service, item.candidate_id, report.report_id)
    service.promote_to_shadow(
        promote_request(item.candidate_id, report.report_id, offline.approval_id)
    )
    started = datetime.now(timezone.utc) - timedelta(hours=1)
    shadow = service.record_shadow_validation(
        ShadowValidationRequest(
            candidate_id=item.candidate_id,
            evaluation_report_id=report.report_id,
            evidence_sha256=sha("bad-shadow"),
            sample_count=1,
            accuracy=0.99,
            p0_errors=0,
            p1_errors=1,
            severe_error_rate=0.01,
            latency_ms_p95=10,
            cost_usd_per_document=0,
            active_drift_alerts=0,
            started_at=started,
            ended_at=started + timedelta(minutes=10),
        )
    )
    assert shadow.passed is False
    assert "SHADOW_SAMPLE_COUNT_BELOW_MINIMUM" in shadow.blocking_reasons
    assert "SHADOW_P1_ERRORS" in shadow.blocking_reasons
    with pytest.raises(MLOpsGateError, match="passing Shadow"):
        approve(service, item.candidate_id, report.report_id, shadow.report_id)


def test_mlflow_training_lineage_rejects_protected_sets(settings) -> None:
    from document_intelligence.mlops.models import ExperimentStatus, MLflowRunRequest

    service = build_service(settings)
    train = snapshot(service, "safe-train", DatasetRole.TRAIN)
    gold = snapshot(service, "leaked-gold", DatasetRole.GOLD)
    with pytest.raises(MLOpsGateError, match="cannot bind gold"):
        service.record_mlflow_run(
            MLflowRunRequest(
                experiment_id="leak-test",
                run_id="run-leak",
                tracking_uri_sha256=sha("tracking"),
                artifact_uri_sha256=sha("artifact-uri"),
                source_commit_sha="b" * 40,
                params_sha256=sha("params"),
                model_artifact_sha256=sha("model"),
                dataset_snapshot_ids=[train.snapshot_id, gold.snapshot_id],
                metrics={},
                status=ExperimentStatus.FINISHED,
            )
        )


def test_candidate_rejects_failed_or_inconsistent_mlflow_lineage(settings) -> None:
    from document_intelligence.mlops.models import (
        CandidateRegistrationRequest,
        ExperimentStatus,
        MLflowRunRequest,
    )

    service = build_service(settings)
    train = snapshot(service, "lineage-train", DatasetRole.TRAIN)
    failed = service.record_mlflow_run(
        MLflowRunRequest(
            experiment_id="lineage",
            run_id="failed-run",
            tracking_uri_sha256=sha("track"),
            artifact_uri_sha256=sha("uri"),
            source_commit_sha="b" * 40,
            params_sha256=sha("params"),
            model_artifact_sha256=sha("artifact"),
            dataset_snapshot_ids=[train.snapshot_id],
            metrics={},
            status=ExperimentStatus.FAILED,
        )
    )
    request = CandidateRegistrationRequest(
        model_family="layout",
        model_version="failed",
        model_artifact_sha256=sha("artifact"),
        source_commit_sha="b" * 40,
        mlflow_record_id=failed.record_id,
        train_snapshot_id=train.snapshot_id,
    )
    with pytest.raises(MLOpsGateError, match="finished"):
        service.register_candidate(request)


def test_evaluation_rejects_protected_set_overlap(settings) -> None:
    from document_intelligence.mlops.models import DatasetSnapshotRequest, EvaluationRequest

    service = build_service(settings)
    item = candidate(service, "overlap")
    shared_hash = sha("same-protected-data")
    protected = dict(
        dvc_repo_revision="e" * 40,
        dvc_data_hash=shared_hash,
        schema_sha256=sha("schema"),
        source_commit_sha="f" * 40,
        record_count=10,
        file_count=1,
        expert_approved=True,
        approver_id_hash=sha("expert"),
    )
    gold = service.create_snapshot(
        DatasetSnapshotRequest(
            role=DatasetRole.GOLD,
            dataset_name="overlap-gold",
            manifest_sha256=sha("gold-manifest"),
            **protected,
        )
    )
    challenge = service.create_snapshot(
        DatasetSnapshotRequest(
            role=DatasetRole.CHALLENGE,
            dataset_name="overlap-challenge",
            manifest_sha256=sha("challenge-manifest"),
            **protected,
        )
    )
    with pytest.raises(MLOpsGateError, match="data-disjoint"):
        service.evaluate(
            EvaluationRequest(
                candidate_id=item.candidate_id,
                gold_snapshot_id=gold.snapshot_id,
                challenge_snapshot_id=challenge.snapshot_id,
                candidate_gold=metric(),
                candidate_challenge=metric(),
                evaluator_version="eval",
                evaluation_config_sha256=sha("config"),
                reproducibility_sha256=sha("repro"),
            )
        )


def test_shadow_validation_blocks_drift_latency_cost_and_accuracy(settings) -> None:
    from datetime import datetime, timedelta, timezone

    service = build_service(settings)
    item = candidate(service, "bad-shadow-all")
    report = evaluation(service, item.candidate_id)
    offline = approve(service, item.candidate_id, report.report_id)
    service.promote_to_shadow(
        promote_request(item.candidate_id, report.report_id, offline.approval_id)
    )
    start = datetime.now(timezone.utc) - timedelta(hours=1)
    result = service.record_shadow_validation(
        ShadowValidationRequest(
            candidate_id=item.candidate_id,
            evaluation_report_id=report.report_id,
            evidence_sha256=sha("bad-all"),
            sample_count=100,
            accuracy=0.5,
            p0_errors=1,
            p1_errors=1,
            severe_error_rate=0.1,
            latency_ms_p95=999999,
            cost_usd_per_document=999,
            active_drift_alerts=1,
            started_at=start,
            ended_at=start + timedelta(minutes=30),
        )
    )
    assert set(result.blocking_reasons) >= {
        "SHADOW_P0_ERRORS",
        "SHADOW_P1_ERRORS",
        "SHADOW_SEVERE_ERRORS",
        "SHADOW_ACCURACY_BELOW_MINIMUM",
        "SHADOW_LATENCY_OVER_BUDGET",
        "SHADOW_COST_OVER_BUDGET",
        "SHADOW_ACTIVE_DRIFT",
    }
