from __future__ import annotations

import json
import zipfile
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from document_intelligence.campaign import (
    CampaignActorRequest,
    CampaignCreateRequest,
    CampaignEvidenceKind,
    CampaignFinalizeRequest,
    CampaignState,
    CampaignStepKind,
    CampaignStepSpec,
    CampaignStore,
    EvidenceLinkRequest,
    QualificationCampaignService,
    StepCheckpointRequest,
    StepClaimRequest,
    StepHeartbeatRequest,
    StepTransitionRequest,
)
from document_intelligence.exceptions import (
    QualificationCampaignGateError,
    QualificationCampaignStoreCorruptError,
)
from tests.production.test_qualification import H, full_chain


def campaign_service(tmp_path: Path) -> tuple[QualificationCampaignService, dict[str, str]]:
    production, ids = full_chain(tmp_path)
    return (
        QualificationCampaignService(CampaignStore(tmp_path), production),
        ids,
    )


def create_started(
    tmp_path: Path,
) -> tuple[QualificationCampaignService, dict[str, str], str]:
    service, ids = campaign_service(tmp_path)
    request = service.default_request(
        campaign_name="phase11-real-qualification",
        source_commit_sha="a" * 40,
        environment_sha256=H,
        policy_sha256=service.production.policy.digest(),
        created_by_id_hash=H,
    ).model_copy(update={"external_data_authorized": True})
    manifest = service.create(request)
    service.start(manifest.campaign_id, CampaignActorRequest(actor_id_hash=H))
    return service, ids, manifest.campaign_id


def claim_link_complete(
    service: QualificationCampaignService,
    campaign_id: str,
    step_id: str,
    kind: CampaignEvidenceKind,
    evidence_id: str,
    *,
    now: datetime,
) -> None:
    claimed = service.claim(
        campaign_id,
        step_id,
        StepClaimRequest(worker_id_hash=H, lease_seconds=300),
        now=now,
    )
    step = next(item for item in claimed.steps if item.step_id == step_id)
    assert step.lease is not None
    lease_id = step.lease.lease_id
    service.checkpoint(
        campaign_id,
        step_id,
        StepCheckpointRequest(
            worker_id_hash=H,
            lease_id=lease_id,
            completed_units=1,
            total_units=1,
            cursor_sha256=H,
            metrics={"processed": 1.0},
        ),
        now=now,
    )
    service.link_evidence(
        campaign_id,
        step_id,
        EvidenceLinkRequest(
            worker_id_hash=H,
            lease_id=lease_id,
            evidence_kind=kind,
            evidence_id=evidence_id,
        ),
        now=now,
    )
    service.complete_step(
        campaign_id,
        step_id,
        StepTransitionRequest(worker_id_hash=H, lease_id=lease_id),
        now=now,
    )


def complete_chain(
    service: QualificationCampaignService, ids: dict[str, str], campaign_id: str
) -> None:
    now = datetime(2026, 8, 4, tzinfo=timezone.utc)
    for step, kind, key in (
        ("gold", CampaignEvidenceKind.DATASET, "gold"),
        ("challenge", CampaignEvidenceKind.DATASET, "challenge"),
        ("parser", CampaignEvidenceKind.PARSER, "parser"),
        ("scale", CampaignEvidenceKind.SCALE, "scale"),
        ("supply", CampaignEvidenceKind.SUPPLY_CHAIN, "supply"),
        ("license", CampaignEvidenceKind.LICENSE, "license"),
        ("pilot", CampaignEvidenceKind.PILOT, "pilot"),
    ):
        claim_link_complete(service, campaign_id, step, kind, ids[key], now=now)
        now += timedelta(seconds=1)


def test_complete_campaign_finalizes_without_automatic_release(tmp_path: Path) -> None:
    service, ids, campaign_id = create_started(tmp_path)
    complete_chain(service, ids, campaign_id)
    snapshot = service.finalize(
        campaign_id,
        CampaignFinalizeRequest(actor_id_hash=H, requested_by_id_hash=H),
    )
    assert snapshot.state == CampaignState.COMPLETED
    assert snapshot.production_qualified is True
    assert snapshot.production_report_id
    assert snapshot.automatic_release_authorized is False
    assert snapshot.bounded_auto is False
    assert service.inspect()["productionQualifiedCampaignCount"] == 1


def test_external_data_authorization_is_required_to_start(tmp_path: Path) -> None:
    service, _ = campaign_service(tmp_path)
    request = service.default_request(
        campaign_name="unauthorized",
        source_commit_sha="a" * 40,
        environment_sha256=H,
        policy_sha256=service.production.policy.digest(),
        created_by_id_hash=H,
    )
    manifest = service.create(request)
    with pytest.raises(QualificationCampaignGateError):
        service.start(manifest.campaign_id, CampaignActorRequest(actor_id_hash=H))


def test_campaign_rejects_stale_policy_and_invalid_graph(tmp_path: Path) -> None:
    service, _ = campaign_service(tmp_path)
    request = service.default_request(
        campaign_name="stale-policy",
        source_commit_sha="a" * 40,
        environment_sha256=H,
        policy_sha256="b" * 64,
        created_by_id_hash=H,
    )
    with pytest.raises(QualificationCampaignGateError):
        service.create(request)
    with pytest.raises(ValueError):
        CampaignCreateRequest(
            campaign_name="cycle",
            source_commit_sha="a" * 40,
            environment_sha256=H,
            policy_sha256=service.production.policy.digest(),
            created_by_id_hash=H,
            steps=[
                CampaignStepSpec(
                    step_id="a",
                    kind=CampaignStepKind.GOLD_DATASET,
                    depends_on=["b"],
                ),
                CampaignStepSpec(
                    step_id="b",
                    kind=CampaignStepKind.QUALIFICATION_REPORT,
                    depends_on=["a"],
                ),
            ],
        )


def test_lease_expiry_allows_reclaim_and_old_worker_is_rejected(tmp_path: Path) -> None:
    service, _, campaign_id = create_started(tmp_path)
    now = datetime(2026, 8, 4, tzinfo=timezone.utc)
    first = service.claim(
        campaign_id,
        "gold",
        StepClaimRequest(worker_id_hash=H, lease_seconds=30),
        now=now,
    )
    lease = next(item for item in first.steps if item.step_id == "gold").lease
    assert lease is not None
    with pytest.raises(QualificationCampaignGateError):
        service.claim(
            campaign_id,
            "gold",
            StepClaimRequest(worker_id_hash="b" * 64, lease_seconds=30),
            now=now + timedelta(seconds=1),
        )
    second = service.claim(
        campaign_id,
        "gold",
        StepClaimRequest(worker_id_hash="b" * 64, lease_seconds=30),
        now=now + timedelta(seconds=31),
    )
    current = next(item for item in second.steps if item.step_id == "gold").lease
    assert current is not None and current.lease_id != lease.lease_id
    with pytest.raises(QualificationCampaignGateError):
        service.heartbeat(
            campaign_id,
            "gold",
            StepHeartbeatRequest(
                worker_id_hash=H,
                lease_id=lease.lease_id,
                lease_seconds=30,
            ),
            now=now + timedelta(seconds=32),
        )


def test_concurrent_claims_fail_closed(tmp_path: Path) -> None:
    service, _, campaign_id = create_started(tmp_path)
    now = datetime(2026, 8, 4, tzinfo=timezone.utc)

    def claim(worker: str) -> bool:
        try:
            service.claim(
                campaign_id,
                "gold",
                StepClaimRequest(worker_id_hash=worker, lease_seconds=300),
                now=now,
            )
            return True
        except (QualificationCampaignGateError, QualificationCampaignStoreCorruptError):
            return False

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(claim, [H, "b" * 64]))
    assert sum(results) == 1
    assert len(service.store.read_events(campaign_id)) == 2


def test_wrong_evidence_kind_and_context_are_rejected(tmp_path: Path) -> None:
    service, ids, campaign_id = create_started(tmp_path)
    now = datetime(2026, 8, 4, tzinfo=timezone.utc)
    claimed = service.claim(
        campaign_id,
        "gold",
        StepClaimRequest(worker_id_hash=H, lease_seconds=300),
        now=now,
    )
    lease = next(item for item in claimed.steps if item.step_id == "gold").lease
    assert lease
    with pytest.raises(QualificationCampaignGateError):
        service.link_evidence(
            campaign_id,
            "gold",
            EvidenceLinkRequest(
                worker_id_hash=H,
                lease_id=lease.lease_id,
                evidence_kind=CampaignEvidenceKind.PARSER,
                evidence_id=ids["parser"],
            ),
            now=now,
        )


def test_event_chain_tampering_is_detected(tmp_path: Path) -> None:
    service, _, campaign_id = create_started(tmp_path)
    event_path = next(
        (tmp_path / "qualification-campaigns" / "campaigns" / campaign_id / "events").glob(
            "*/event.json"
        )
    )
    payload = json.loads(event_path.read_text())
    payload["note"] = "tampered"
    event_path.write_text(json.dumps(payload))
    with pytest.raises(QualificationCampaignStoreCorruptError):
        service.snapshot(campaign_id)


def test_bundle_export_verify_and_restore_are_complete(tmp_path: Path) -> None:
    source = tmp_path / "source"
    service, ids, campaign_id = create_started(source)
    complete_chain(service, ids, campaign_id)
    final = service.finalize(
        campaign_id,
        CampaignFinalizeRequest(actor_id_hash=H, requested_by_id_hash=H),
    )
    bundle_path = tmp_path / "campaign.zip"
    exported = service.export_bundle(campaign_id, bundle_path)
    assert exported["bundle"]["contains_raw_documents"] is False
    assert service.verify_bundle(bundle_path)["verified"] is True

    target = tmp_path / "target"
    target_production, _ = full_chain(target)
    target_service = QualificationCampaignService(
        CampaignStore(target), target_production
    )
    restored = target_service.import_bundle(bundle_path)
    restored_again = target_service.import_bundle(bundle_path)
    assert restored.model_dump(mode="json") == final.model_dump(mode="json")
    assert restored_again.model_dump(mode="json") == restored.model_dump(mode="json")


def test_bundle_path_traversal_and_checksum_mismatch_are_rejected(tmp_path: Path) -> None:
    service, _, campaign_id = create_started(tmp_path / "workspace")
    good = tmp_path / "good.zip"
    service.export_bundle(campaign_id, good)
    bad = tmp_path / "bad.zip"
    with zipfile.ZipFile(good) as source, zipfile.ZipFile(bad, "w") as target:
        for info in source.infolist():
            target.writestr(info.filename, source.read(info))
        target.writestr("../escape.json", b"{}")
    with pytest.raises(QualificationCampaignStoreCorruptError):
        service.verify_bundle(bad)


def test_pause_fail_retry_and_cancel_transitions(tmp_path: Path) -> None:
    service, _, campaign_id = create_started(tmp_path)
    paused = service.pause(campaign_id, CampaignActorRequest(actor_id_hash=H))
    assert paused.state == CampaignState.PAUSED
    resumed = service.resume(campaign_id, CampaignActorRequest(actor_id_hash=H))
    assert resumed.state == CampaignState.RUNNING
    now = datetime(2026, 8, 4, tzinfo=timezone.utc)
    claimed = service.claim(
        campaign_id,
        "gold",
        StepClaimRequest(worker_id_hash=H, lease_seconds=300),
        now=now,
    )
    lease = next(item for item in claimed.steps if item.step_id == "gold").lease
    assert lease
    failed = service.fail_step(
        campaign_id,
        "gold",
        StepTransitionRequest(worker_id_hash=H, lease_id=lease.lease_id, note="fixture"),
        now=now,
    )
    assert next(item for item in failed.steps if item.step_id == "gold").state.value == "failed"
    retried = service.retry_step(
        campaign_id,
        "gold",
        CampaignActorRequest(actor_id_hash=H),
    )
    assert next(item for item in retried.steps if item.step_id == "gold").state.value == "pending"
    cancelled = service.cancel(campaign_id, CampaignActorRequest(actor_id_hash=H))
    assert cancelled.state == CampaignState.CANCELLED


def test_dependency_incomplete_and_report_claim_are_blocked(tmp_path: Path) -> None:
    service, _, campaign_id = create_started(tmp_path)
    now = datetime(2026, 8, 4, tzinfo=timezone.utc)
    with pytest.raises(QualificationCampaignGateError):
        service.claim(
            campaign_id,
            "parser",
            StepClaimRequest(worker_id_hash=H),
            now=now,
        )
    with pytest.raises(QualificationCampaignGateError):
        service.claim(
            campaign_id,
            "qualification",
            StepClaimRequest(worker_id_hash=H),
            now=now,
        )


def test_step_cannot_complete_without_evidence_or_duplicate_link(tmp_path: Path) -> None:
    service, ids, campaign_id = create_started(tmp_path)
    now = datetime(2026, 8, 4, tzinfo=timezone.utc)
    claimed = service.claim(
        campaign_id,
        "gold",
        StepClaimRequest(worker_id_hash=H),
        now=now,
    )
    lease = next(item for item in claimed.steps if item.step_id == "gold").lease
    assert lease
    transition = StepTransitionRequest(worker_id_hash=H, lease_id=lease.lease_id)
    with pytest.raises(QualificationCampaignGateError):
        service.complete_step(campaign_id, "gold", transition, now=now)
    link = EvidenceLinkRequest(
        worker_id_hash=H,
        lease_id=lease.lease_id,
        evidence_kind=CampaignEvidenceKind.DATASET,
        evidence_id=ids["gold"],
    )
    service.link_evidence(campaign_id, "gold", link, now=now)
    with pytest.raises(QualificationCampaignGateError):
        service.link_evidence(campaign_id, "gold", link, now=now)


def test_scale_evidence_must_match_campaign_context(tmp_path: Path) -> None:
    service, ids, campaign_id = create_started(tmp_path)
    now = datetime(2026, 8, 4, tzinfo=timezone.utc)
    claimed = service.claim(
        campaign_id,
        "scale",
        StepClaimRequest(worker_id_hash=H),
        now=now,
    )
    lease = next(item for item in claimed.steps if item.step_id == "scale").lease
    assert lease
    original = service.production.store.read_scale(ids["scale"])
    mismatched = original.model_copy(
        update={
            "evidence_id": "scale-" + "1" * 32,
            "environment_sha256": "b" * 64,
        }
    )
    service.production.store.commit_scale(mismatched)
    with pytest.raises(QualificationCampaignGateError):
        service.link_evidence(
            campaign_id,
            "scale",
            EvidenceLinkRequest(
                worker_id_hash=H,
                lease_id=lease.lease_id,
                evidence_kind=CampaignEvidenceKind.SCALE,
                evidence_id=mismatched.evidence_id,
            ),
            now=now,
        )


def test_stale_policy_report_is_restored_for_audit_but_not_currently_qualified(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source-stale"
    service, ids, campaign_id = create_started(source)
    complete_chain(service, ids, campaign_id)
    service.finalize(
        campaign_id,
        CampaignFinalizeRequest(actor_id_hash=H, requested_by_id_hash=H),
    )
    bundle = tmp_path / "stale.zip"
    service.export_bundle(campaign_id, bundle)
    from document_intelligence.production import ProductionQualificationPolicy

    target = tmp_path / "target-stale"
    production, _ = full_chain(target)
    production.policy = ProductionQualificationPolicy(
        **{**production.policy.__dict__, "minimum_pilot_days": 3}
    )
    restored = QualificationCampaignService(CampaignStore(target), production).import_bundle(
        bundle
    )
    assert restored.state == CampaignState.COMPLETED
    assert restored.production_qualified is False
