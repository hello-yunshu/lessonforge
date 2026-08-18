from __future__ import annotations
from document_intelligence.exceptions import MLOpsGateError

import json

import pytest

from document_intelligence.mlops.models import DatasetRole, DatasetSnapshotRequest
from document_intelligence.mlops.store import MLOpsStore, MLOpsStoreError
from tests.mlops.helpers import build_service, sha, snapshot


def test_gold_and_challenge_require_expert_approval(settings) -> None:
    service = build_service(settings)
    with pytest.raises(MLOpsGateError):
        service.create_snapshot(DatasetSnapshotRequest(
            role=DatasetRole.GOLD,
            dataset_name="gold",
            dvc_repo_revision="a" * 40,
            dvc_data_hash=sha("data"),
            manifest_sha256=sha("manifest"),
            schema_sha256=sha("schema"),
            source_commit_sha="b" * 40,
            record_count=1,
            file_count=1,
        ))


def test_store_detects_snapshot_tampering(settings) -> None:
    service = build_service(settings)
    record = snapshot(service, "train", DatasetRole.TRAIN)
    path = (
        settings.workspace
        / "mlops"
        / "dataset-snapshots"
        / record.snapshot_id
        / "snapshot.json"
    )
    payload = json.loads(path.read_text())
    payload["record_count"] = 999
    path.write_text(json.dumps(payload))
    with pytest.raises(MLOpsStoreError):
        MLOpsStore(settings.workspace).read_snapshot(record.snapshot_id)


def test_store_rechecks_namespace_symlink(settings, tmp_path) -> None:
    store = MLOpsStore(settings.workspace)
    namespace = settings.workspace / "mlops" / "dataset-snapshots"
    namespace.rmdir()
    namespace.symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(MLOpsStoreError):
        store.list_snapshots()


def test_alias_state_is_single_file_atomic_envelope(settings) -> None:
    from tests.mlops.helpers import candidate
    from document_intelligence.mlops.models import ModelAlias

    service = build_service(settings)
    item = candidate(service, "atomic")
    aliases = service.store.aliases()
    assert aliases[ModelAlias.CANDIDATE] == item.candidate_id
    control = settings.workspace / "mlops" / "control"
    assert (control / "aliases.json").is_file()
    assert not (control / "aliases.sha256").exists()


def test_alias_envelope_detects_tampering(settings) -> None:
    from tests.mlops.helpers import candidate

    service = build_service(settings)
    candidate(service, "tamper-alias")
    path = settings.workspace / "mlops" / "control" / "aliases.json"
    payload = json.loads(path.read_text())
    payload["aliases"]["candidate"] = "candidate-missing"
    path.write_text(json.dumps(payload))
    with pytest.raises(MLOpsStoreError, match="checksum"):
        service.store.aliases()


def test_dataset_parent_must_preserve_name_and_role(settings) -> None:
    service = build_service(settings)
    parent = snapshot(service, "series", DatasetRole.TRAIN)
    base = dict(
        dvc_repo_revision="c" * 40,
        dvc_data_hash=sha("next-data"),
        manifest_sha256=sha("next-manifest"),
        schema_sha256=sha("schema"),
        source_commit_sha="d" * 40,
        record_count=2,
        file_count=1,
        parent_snapshot_id=parent.snapshot_id,
    )
    with pytest.raises(MLOpsGateError, match="same dataset"):
        service.create_snapshot(
            DatasetSnapshotRequest(role=DatasetRole.TRAIN, dataset_name="other", **base)
        )
    with pytest.raises(MLOpsGateError, match="preserve"):
        service.create_snapshot(
            DatasetSnapshotRequest(
                role=DatasetRole.VALIDATION, dataset_name="series", **base
            )
        )


def test_evaluation_request_rejects_partial_baseline() -> None:
    from pydantic import ValidationError
    from document_intelligence.mlops.models import EvaluationRequest, MetricSet

    metrics = MetricSet(
        accuracy=0.95,
        p0_errors=0,
        p1_errors=0,
        severe_error_rate=0,
        standard_mismatch_rate=0,
        key_value_accuracy=0.96,
        relation_accuracy=0.94,
        latency_ms_p95=50,
        cost_usd_per_document=0.01,
    )
    with pytest.raises(ValidationError, match="requires gold and challenge"):
        EvaluationRequest(
            candidate_id="candidate-1",
            baseline_candidate_id="candidate-2",
            gold_snapshot_id="gold-1",
            challenge_snapshot_id="challenge-1",
            candidate_gold=metrics,
            candidate_challenge=metrics,
            evaluator_version="test-1",
            evaluation_config_sha256=sha("config"),
            reproducibility_sha256=sha("repro"),
        )


def test_shadow_request_rejects_naive_or_reversed_window() -> None:
    from datetime import datetime, timedelta, timezone
    from pydantic import ValidationError
    from document_intelligence.mlops.models import ShadowValidationRequest

    base = dict(
        candidate_id="candidate-1",
        evaluation_report_id="evaluation-1",
        evidence_sha256=sha("evidence"),
        sample_count=100,
        accuracy=0.95,
        p0_errors=0,
        p1_errors=0,
        severe_error_rate=0,
        latency_ms_p95=50,
        cost_usd_per_document=0.01,
        active_drift_alerts=0,
    )
    with pytest.raises(ValidationError, match="timezone-aware"):
        ShadowValidationRequest(
            **base,
            started_at=datetime(2026, 1, 1),
            ended_at=datetime(2026, 1, 2),
        )
    end = datetime(2026, 1, 2, tzinfo=timezone.utc)
    with pytest.raises(ValidationError, match="after start"):
        ShadowValidationRequest(
            **base,
            started_at=end,
            ended_at=end - timedelta(seconds=1),
        )


def test_mlflow_request_rejects_duplicate_snapshots_and_nonfinite_metrics() -> None:
    from pydantic import ValidationError
    from document_intelligence.mlops.models import ExperimentStatus, MLflowRunRequest

    base = dict(
        experiment_id="exp-1",
        run_id="run-1",
        tracking_uri_sha256=sha("tracking"),
        artifact_uri_sha256=sha("artifact-uri"),
        source_commit_sha="a" * 40,
        params_sha256=sha("params"),
        model_artifact_sha256=sha("model"),
        status=ExperimentStatus.FINISHED,
    )
    with pytest.raises(ValidationError, match="duplicate"):
        MLflowRunRequest(
            **base,
            dataset_snapshot_ids=["dataset-1", "dataset-1"],
            metrics={},
        )
    with pytest.raises(ValidationError, match="invalid MLflow metric"):
        MLflowRunRequest(
            **base,
            dataset_snapshot_ids=["dataset-1"],
            metrics={"loss": float("nan")},
        )
