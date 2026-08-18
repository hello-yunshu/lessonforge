from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from document_intelligence.exceptions import QualificationCampaignGateError
from document_intelligence.production import (
    DatasetQualificationEvidence,
    LicenseQualificationEvidence,
    ParserQualificationEvidence,
    PilotQualificationEvidence,
    ProductionQualificationReport,
    ProductionQualificationRequest,
    ProductionQualificationService,
    QualificationDatasetRole,
    ScaleQualificationEvidence,
    SupplyChainQualificationEvidence,
)

from .models import (
    STEP_EVIDENCE_KIND,
    CampaignAction,
    CampaignActorRequest,
    CampaignCreateRequest,
    CampaignEvent,
    CampaignEvidenceKind,
    CampaignFinalizeRequest,
    CampaignManifest,
    CampaignSnapshot,
    CampaignState,
    CampaignStepKind,
    CampaignStepSnapshot,
    CampaignStepState,
    EvidenceLink,
    EvidenceLinkRequest,
    StepCheckpointRequest,
    StepClaimRequest,
    StepHeartbeatRequest,
    StepLease,
    StepTransitionRequest,
    stable_campaign_id,
)
from .store import CampaignStore


class QualificationCampaignService:
    def __init__(
        self,
        store: CampaignStore,
        production: ProductionQualificationService,
        *,
        maximum_lease_seconds: int = 86400,
    ) -> None:
        self.store = store
        self.production = production
        self.maximum_lease_seconds = maximum_lease_seconds

    @staticmethod
    def default_request(
        *,
        campaign_name: str,
        source_commit_sha: str,
        environment_sha256: str,
        policy_sha256: str,
        created_by_id_hash: str,
    ) -> CampaignCreateRequest:
        from .models import CampaignStepSpec

        steps = [
            CampaignStepSpec(step_id="gold", kind=CampaignStepKind.GOLD_DATASET),
            CampaignStepSpec(step_id="challenge", kind=CampaignStepKind.CHALLENGE_DATASET),
            CampaignStepSpec(
                step_id="parser",
                kind=CampaignStepKind.PARSER_QUALIFICATION,
                depends_on=["gold", "challenge"],
            ),
            CampaignStepSpec(step_id="scale", kind=CampaignStepKind.SCALE_SOAK),
            CampaignStepSpec(step_id="supply", kind=CampaignStepKind.SUPPLY_CHAIN),
            CampaignStepSpec(step_id="license", kind=CampaignStepKind.LICENSE_REVIEW),
            CampaignStepSpec(step_id="pilot", kind=CampaignStepKind.PILOT),
            CampaignStepSpec(
                step_id="qualification",
                kind=CampaignStepKind.QUALIFICATION_REPORT,
                depends_on=["parser", "scale", "supply", "license", "pilot"],
            ),
        ]
        return CampaignCreateRequest(
            campaign_name=campaign_name,
            source_commit_sha=source_commit_sha,
            environment_sha256=environment_sha256,
            policy_sha256=policy_sha256,
            created_by_id_hash=created_by_id_hash,
            steps=steps,
            external_data_authorized=False,
        )

    def create(self, request: CampaignCreateRequest) -> CampaignManifest:
        if request.policy_sha256 != self.production.policy.digest():
            raise QualificationCampaignGateError(
                "campaign policy digest does not match current policy"
            )
        campaign_id = stable_campaign_id("campaign", request.semantic_digest())
        return self.store.commit_manifest(
            CampaignManifest(campaign_id=campaign_id, **request.model_dump(mode="python"))
        )

    def start(self, campaign_id: str, request: CampaignActorRequest) -> CampaignSnapshot:
        snapshot = self.snapshot(campaign_id)
        manifest = self.store.read_manifest(campaign_id)
        if not manifest.external_data_authorized:
            raise QualificationCampaignGateError("campaign external data authorization is missing")
        if snapshot.state != CampaignState.PLANNED:
            raise QualificationCampaignGateError("only a planned campaign can start")
        self._append(campaign_id, CampaignAction.START, request.actor_id_hash, note=request.note)
        return self.snapshot(campaign_id)

    def pause(self, campaign_id: str, request: CampaignActorRequest) -> CampaignSnapshot:
        if self.snapshot(campaign_id).state != CampaignState.RUNNING:
            raise QualificationCampaignGateError("only a running campaign can pause")
        self._append(campaign_id, CampaignAction.PAUSE, request.actor_id_hash, note=request.note)
        return self.snapshot(campaign_id)

    def resume(self, campaign_id: str, request: CampaignActorRequest) -> CampaignSnapshot:
        if self.snapshot(campaign_id).state != CampaignState.PAUSED:
            raise QualificationCampaignGateError("only a paused campaign can resume")
        self._append(campaign_id, CampaignAction.RESUME, request.actor_id_hash, note=request.note)
        return self.snapshot(campaign_id)

    def cancel(self, campaign_id: str, request: CampaignActorRequest) -> CampaignSnapshot:
        if self.snapshot(campaign_id).state in {CampaignState.COMPLETED, CampaignState.CANCELLED}:
            raise QualificationCampaignGateError("terminal campaign cannot be cancelled")
        self._append(campaign_id, CampaignAction.CANCEL, request.actor_id_hash, note=request.note)
        return self.snapshot(campaign_id)

    def claim(
        self,
        campaign_id: str,
        step_id: str,
        request: StepClaimRequest,
        *,
        now: datetime | None = None,
    ) -> CampaignSnapshot:
        moment = now or datetime.now(timezone.utc)
        snapshot = self.snapshot(campaign_id, now=moment)
        if snapshot.state != CampaignState.RUNNING:
            raise QualificationCampaignGateError("campaign is not running")
        step = self._step(snapshot, step_id)
        if step.kind == CampaignStepKind.QUALIFICATION_REPORT:
            raise QualificationCampaignGateError(
                "qualification report step is controlled by finalize"
            )
        if step.state not in {CampaignStepState.PENDING, CampaignStepState.LEASED}:
            raise QualificationCampaignGateError("step cannot be claimed")
        if step.lease and step.lease.expires_at >= moment:
            raise QualificationCampaignGateError("step already has an active lease")
        if any(
            self._step(snapshot, item).state != CampaignStepState.COMPLETED
            for item in step.depends_on
        ):
            raise QualificationCampaignGateError("step dependencies are incomplete")
        seconds = min(request.lease_seconds, self.maximum_lease_seconds)
        lease_id = stable_campaign_id(
            "lease", campaign_id, step_id, request.worker_id_hash, moment.isoformat()
        )
        self._append(
            campaign_id,
            CampaignAction.CLAIM_STEP,
            request.worker_id_hash,
            step_id=step_id,
            worker_id_hash=request.worker_id_hash,
            lease_id=lease_id,
            lease_expires_at=moment + timedelta(seconds=seconds),
            created_at=moment,
        )
        return self.snapshot(campaign_id, now=moment)

    def heartbeat(
        self,
        campaign_id: str,
        step_id: str,
        request: StepHeartbeatRequest,
        *,
        now: datetime | None = None,
    ) -> CampaignSnapshot:
        moment = now or datetime.now(timezone.utc)
        snapshot = self.snapshot(campaign_id, now=moment)
        step = self._active_lease(
            snapshot, step_id, request.worker_id_hash, request.lease_id, moment
        )
        seconds = min(request.lease_seconds, self.maximum_lease_seconds)
        self._append(
            campaign_id,
            CampaignAction.HEARTBEAT,
            request.worker_id_hash,
            step_id=step.step_id,
            worker_id_hash=request.worker_id_hash,
            lease_id=request.lease_id,
            lease_expires_at=moment + timedelta(seconds=seconds),
            created_at=moment,
        )
        return self.snapshot(campaign_id, now=moment)

    def checkpoint(
        self,
        campaign_id: str,
        step_id: str,
        request: StepCheckpointRequest,
        *,
        now: datetime | None = None,
    ) -> CampaignSnapshot:
        moment = now or datetime.now(timezone.utc)
        snapshot = self.snapshot(campaign_id, now=moment)
        self._active_lease(snapshot, step_id, request.worker_id_hash, request.lease_id, moment)
        self._append(
            campaign_id,
            CampaignAction.CHECKPOINT,
            request.worker_id_hash,
            step_id=step_id,
            worker_id_hash=request.worker_id_hash,
            lease_id=request.lease_id,
            checkpoint=request,
            created_at=moment,
        )
        return self.snapshot(campaign_id, now=moment)

    def link_evidence(
        self,
        campaign_id: str,
        step_id: str,
        request: EvidenceLinkRequest,
        *,
        now: datetime | None = None,
    ) -> CampaignSnapshot:
        moment = now or datetime.now(timezone.utc)
        snapshot = self.snapshot(campaign_id, now=moment)
        step = self._active_lease(
            snapshot, step_id, request.worker_id_hash, request.lease_id, moment
        )
        expected = STEP_EVIDENCE_KIND[step.kind]
        if any(item.evidence_id == request.evidence_id for item in step.evidence):
            raise QualificationCampaignGateError("evidence is already linked to this step")
        if expected != request.evidence_kind:
            raise QualificationCampaignGateError("evidence kind does not match campaign step")
        evidence = self._read_evidence(request.evidence_kind, request.evidence_id)
        manifest = self.store.read_manifest(campaign_id)
        if request.evidence_kind == CampaignEvidenceKind.SCALE:
            if (
                evidence.source_commit_sha != manifest.source_commit_sha
                or evidence.environment_sha256 != manifest.environment_sha256
            ):
                raise QualificationCampaignGateError(
                    "scale evidence does not match campaign source or environment"
                )
        if request.evidence_kind == CampaignEvidenceKind.SUPPLY_CHAIN:
            if evidence.source_commit_sha != manifest.source_commit_sha:
                raise QualificationCampaignGateError(
                    "supply-chain evidence does not match campaign source"
                )
        if request.evidence_kind == CampaignEvidenceKind.REPORT:
            if evidence.policy_sha256 != manifest.policy_sha256:
                raise QualificationCampaignGateError(
                    "qualification report does not match campaign policy"
                )
        if (
            step.kind == CampaignStepKind.GOLD_DATASET
            and evidence.role != QualificationDatasetRole.GOLD
        ):
            raise QualificationCampaignGateError("gold step requires gold dataset evidence")
        if (
            step.kind == CampaignStepKind.CHALLENGE_DATASET
            and evidence.role != QualificationDatasetRole.CHALLENGE
        ):
            raise QualificationCampaignGateError(
                "challenge step requires challenge dataset evidence"
            )
        self._append(
            campaign_id,
            CampaignAction.LINK_EVIDENCE,
            request.worker_id_hash,
            step_id=step_id,
            worker_id_hash=request.worker_id_hash,
            lease_id=request.lease_id,
            evidence_kind=request.evidence_kind,
            evidence_id=request.evidence_id,
            evidence_semantic_sha256=evidence.semantic_digest(),
            created_at=moment,
        )
        return self.snapshot(campaign_id, now=moment)

    def complete_step(
        self,
        campaign_id: str,
        step_id: str,
        request: StepTransitionRequest,
        *,
        now: datetime | None = None,
    ) -> CampaignSnapshot:
        moment = now or datetime.now(timezone.utc)
        snapshot = self.snapshot(campaign_id, now=moment)
        step = self._active_lease(
            snapshot, step_id, request.worker_id_hash, request.lease_id, moment
        )
        spec = next(
            item
            for item in self.store.read_manifest(campaign_id).steps
            if item.step_id == step_id
        )
        if len(step.evidence) < spec.minimum_evidence_count:
            raise QualificationCampaignGateError("step lacks required evidence")
        self._append(
            campaign_id,
            CampaignAction.COMPLETE_STEP,
            request.worker_id_hash,
            step_id=step_id,
            worker_id_hash=request.worker_id_hash,
            lease_id=request.lease_id,
            note=request.note,
            created_at=moment,
        )
        return self.snapshot(campaign_id, now=moment)

    def fail_step(
        self,
        campaign_id: str,
        step_id: str,
        request: StepTransitionRequest,
        *,
        now: datetime | None = None,
    ) -> CampaignSnapshot:
        moment = now or datetime.now(timezone.utc)
        snapshot = self.snapshot(campaign_id, now=moment)
        self._active_lease(snapshot, step_id, request.worker_id_hash, request.lease_id, moment)
        self._append(
            campaign_id,
            CampaignAction.FAIL_STEP,
            request.worker_id_hash,
            step_id=step_id,
            worker_id_hash=request.worker_id_hash,
            lease_id=request.lease_id,
            note=request.note or "step failed",
            created_at=moment,
        )
        return self.snapshot(campaign_id, now=moment)

    def retry_step(
        self, campaign_id: str, step_id: str, request: CampaignActorRequest
    ) -> CampaignSnapshot:
        step = self._step(self.snapshot(campaign_id), step_id)
        if step.state != CampaignStepState.FAILED:
            raise QualificationCampaignGateError("only a failed step can be retried")
        self._append(
            campaign_id,
            CampaignAction.RETRY_STEP,
            request.actor_id_hash,
            step_id=step_id,
            note=request.note,
        )
        return self.snapshot(campaign_id)

    def finalize(self, campaign_id: str, request: CampaignFinalizeRequest) -> CampaignSnapshot:
        snapshot = self.snapshot(campaign_id)
        manifest = self.store.read_manifest(campaign_id)
        if manifest.policy_sha256 != self.production.policy.digest():
            raise QualificationCampaignGateError("campaign policy is stale")
        if snapshot.state != CampaignState.RUNNING:
            raise QualificationCampaignGateError("campaign must be running to finalize")
        report_step = next(
            step
            for step in snapshot.steps
            if step.kind == CampaignStepKind.QUALIFICATION_REPORT
        )
        if any(
            self._step(snapshot, dep).state != CampaignStepState.COMPLETED
            for dep in report_step.depends_on
        ):
            raise QualificationCampaignGateError("qualification dependencies are incomplete")
        links = [link for step in snapshot.steps for link in step.evidence]
        datasets = [
            item.evidence_id
            for item in links
            if item.evidence_kind == CampaignEvidenceKind.DATASET
        ]
        parsers = [
            item.evidence_id
            for item in links
            if item.evidence_kind == CampaignEvidenceKind.PARSER
        ]
        licenses = [
            item.evidence_id
            for item in links
            if item.evidence_kind == CampaignEvidenceKind.LICENSE
        ]
        single = {
            kind: [item.evidence_id for item in links if item.evidence_kind == kind]
            for kind in (
                CampaignEvidenceKind.SCALE,
                CampaignEvidenceKind.SUPPLY_CHAIN,
                CampaignEvidenceKind.PILOT,
            )
        }
        if (
            len(single[CampaignEvidenceKind.SCALE]) != 1
            or len(single[CampaignEvidenceKind.SUPPLY_CHAIN]) != 1
            or len(single[CampaignEvidenceKind.PILOT]) != 1
        ):
            raise QualificationCampaignGateError(
                "campaign requires one scale, supply-chain, and pilot evidence"
            )
        report = self.production.qualify(
            ProductionQualificationRequest(
                dataset_evidence_ids=datasets,
                parser_evidence_ids=parsers,
                scale_evidence_id=single[CampaignEvidenceKind.SCALE][0],
                supply_chain_evidence_id=single[CampaignEvidenceKind.SUPPLY_CHAIN][0],
                license_evidence_ids=licenses,
                pilot_evidence_id=single[CampaignEvidenceKind.PILOT][0],
                requested_by_id_hash=request.requested_by_id_hash,
            )
        )
        self._append(
            campaign_id,
            CampaignAction.FINALIZE,
            request.actor_id_hash,
            step_id=report_step.step_id,
            evidence_kind=CampaignEvidenceKind.REPORT,
            evidence_id=report.report_id,
            evidence_semantic_sha256=report.semantic_digest(),
            note="production qualification evaluated; no automatic release",
        )
        return self.snapshot(campaign_id)

    def snapshot(self, campaign_id: str, *, now: datetime | None = None) -> CampaignSnapshot:
        manifest = self.store.read_manifest(campaign_id)
        events = self.store.read_events(campaign_id)
        moment = now or datetime.now(timezone.utc)
        state = CampaignState.PLANNED
        steps = {
            spec.step_id: CampaignStepSnapshot(
                step_id=spec.step_id,
                kind=spec.kind,
                state=CampaignStepState.PENDING,
                depends_on=spec.depends_on,
            )
            for spec in manifest.steps
        }
        report_id: str | None = None
        qualified = False
        for event in events:
            if event.action == CampaignAction.START:
                state = CampaignState.RUNNING
            elif event.action == CampaignAction.PAUSE:
                state = CampaignState.PAUSED
            elif event.action == CampaignAction.RESUME:
                state = CampaignState.RUNNING
            elif event.action == CampaignAction.CANCEL:
                state = CampaignState.CANCELLED
            elif event.step_id:
                try:
                    step = steps[event.step_id]
                except KeyError as exc:
                    raise QualificationCampaignGateError(
                        "campaign event references an unknown step"
                    ) from exc
                if event.action in {CampaignAction.CLAIM_STEP, CampaignAction.HEARTBEAT}:
                    step.state = CampaignStepState.LEASED
                    step.lease = StepLease(
                        lease_id=event.lease_id,
                        worker_id_hash=event.worker_id_hash,
                        expires_at=event.lease_expires_at,
                    )
                elif event.action == CampaignAction.LINK_EVIDENCE:
                    value = self._read_evidence(event.evidence_kind, event.evidence_id)
                    if value.semantic_digest() != event.evidence_semantic_sha256:
                        raise QualificationCampaignGateError(
                            "linked evidence changed after campaign event"
                        )
                    link = EvidenceLink(
                        step_id=event.step_id,
                        evidence_kind=event.evidence_kind,
                        evidence_id=event.evidence_id,
                        evidence_semantic_sha256=event.evidence_semantic_sha256,
                        passed=bool(value.passed if hasattr(value, "passed") else value.qualified),
                    )
                    if all(item.evidence_id != link.evidence_id for item in step.evidence):
                        step.evidence.append(link)
                elif event.action == CampaignAction.CHECKPOINT:
                    step.checkpoint = event.checkpoint
                elif event.action == CampaignAction.COMPLETE_STEP:
                    step.state = CampaignStepState.COMPLETED
                    step.lease = None
                elif event.action == CampaignAction.FAIL_STEP:
                    step.state = CampaignStepState.FAILED
                    step.lease = None
                    step.failure_note = event.note
                elif event.action == CampaignAction.RETRY_STEP:
                    step.state = CampaignStepState.PENDING
                    step.lease = None
                    step.failure_note = None
                elif event.action == CampaignAction.FINALIZE:
                    report_id = event.evidence_id
                    report = self.production.store.read_report(report_id)
                    if report.semantic_digest() != event.evidence_semantic_sha256:
                        raise QualificationCampaignGateError("qualification report changed")
                    qualified = (
                        report.qualified
                        and report.policy_sha256 == self.production.policy.digest()
                    )
                    step.evidence = [
                        EvidenceLink(
                            step_id=event.step_id,
                            evidence_kind=CampaignEvidenceKind.REPORT,
                            evidence_id=report.report_id,
                            evidence_semantic_sha256=report.semantic_digest(),
                            passed=report.qualified,
                        )
                    ]
                    step.state = CampaignStepState.COMPLETED
                    state = CampaignState.COMPLETED
        if state in {CampaignState.RUNNING, CampaignState.PAUSED}:
            for step in steps.values():
                if (
                    step.state == CampaignStepState.LEASED
                    and step.lease
                    and step.lease.expires_at < moment
                ):
                    step.state = CampaignStepState.PENDING
                    step.lease = None
        return CampaignSnapshot(
            campaign_id=campaign_id,
            manifest_sha256=manifest.semantic_digest(),
            state=state,
            steps=list(steps.values()),
            event_count=len(events),
            last_event_sha256=events[-1].chain_digest() if events else None,
            production_report_id=report_id,
            production_qualified=qualified,
        )

    def inspect(self) -> dict[str, Any]:
        snapshots = [self.snapshot(item) for item in self.store.list_campaign_ids()]
        counts = {
            state.value: sum(item.state == state for item in snapshots)
            for state in CampaignState
        }
        return {
            "campaignCount": len(snapshots),
            "stateCounts": counts,
            "productionQualifiedCampaignCount": sum(
                item.production_qualified for item in snapshots
            ),
            "automaticReleaseAuthorized": False,
            "boundedAuto": False,
        }

    def export_bundle(self, campaign_id: str, output: Path) -> dict[str, Any]:
        snapshot = self.snapshot(campaign_id)
        evidence_files: dict[str, bytes] = {}
        for step in snapshot.steps:
            for link in step.evidence:
                value = self._read_evidence(link.evidence_kind, link.evidence_id)
                name = f"evidence/{link.evidence_kind.value}/{link.evidence_id}.json"
                evidence_files[name] = (value.model_dump_json(exclude_none=False) + "\n").encode()
        bundle = self.store.export_bundle(campaign_id, evidence_files=evidence_files, output=output)
        return {"bundle": bundle.model_dump(mode="json"), "path": str(output)}

    def verify_bundle(self, path: Path) -> dict[str, Any]:
        bundle, payload = self.store.verify_bundle(path)
        return {
            "bundle": bundle.model_dump(mode="json"),
            "fileCount": len(payload),
            "verified": True,
            "automaticReleaseAuthorized": False,
            "boundedAuto": False,
        }

    def import_bundle(self, path: Path) -> CampaignSnapshot:
        bundle, payload = self.store.verify_bundle(path)
        model_map: dict[str, tuple[type[Any], Any]] = {
            CampaignEvidenceKind.DATASET.value: (
                DatasetQualificationEvidence, self.production.store.commit_dataset
            ),
            CampaignEvidenceKind.PARSER.value: (
                ParserQualificationEvidence, self.production.store.commit_parser
            ),
            CampaignEvidenceKind.SCALE.value: (
                ScaleQualificationEvidence, self.production.store.commit_scale
            ),
            CampaignEvidenceKind.SUPPLY_CHAIN.value: (
                SupplyChainQualificationEvidence, self.production.store.commit_supply_chain
            ),
            CampaignEvidenceKind.LICENSE.value: (
                LicenseQualificationEvidence, self.production.store.commit_license
            ),
            CampaignEvidenceKind.PILOT.value: (
                PilotQualificationEvidence, self.production.store.commit_pilot
            ),
            CampaignEvidenceKind.REPORT.value: (
                ProductionQualificationReport, self.production.store.commit_report
            ),
        }
        for name, raw in sorted(payload.items()):
            parts = name.split("/")
            if len(parts) != 3 or parts[0] != "evidence":
                continue
            try:
                model, commit = model_map[parts[1]]
            except KeyError as exc:
                raise QualificationCampaignGateError("bundle evidence kind is unsupported") from exc
            value = model.model_validate_json(raw)
            if f"{getattr(value, 'evidence_id', getattr(value, 'report_id', ''))}.json" != parts[2]:
                raise QualificationCampaignGateError("bundle evidence path identity mismatch")
            commit(value)
        manifest = CampaignManifest.model_validate_json(payload["campaign/manifest.json"])
        self.store.commit_manifest(manifest)
        events = [
            CampaignEvent.model_validate(item)
            for item in json.loads(payload["campaign/events.json"])
        ]
        existing = self.store.read_events(manifest.campaign_id)
        for event in events:
            if event.sequence <= len(existing):
                current = existing[event.sequence - 1]
                if current.model_dump(mode="json") != event.model_dump(mode="json"):
                    raise QualificationCampaignGateError(
                        "restored campaign conflicts with existing event history"
                    )
                continue
            self.store.append_event(manifest.campaign_id, event)
        snapshot = self.snapshot(bundle.campaign_id)
        if snapshot.last_event_sha256 != bundle.event_chain_sha256:
            raise QualificationCampaignGateError("restored campaign chain does not match bundle")
        return snapshot

    def _append(
        self,
        campaign_id: str,
        action: CampaignAction,
        actor_id_hash: str,
        **kwargs: Any,
    ) -> CampaignEvent:
        events = self.store.read_events(campaign_id)
        sequence = len(events) + 1
        previous = events[-1].chain_digest() if events else None
        created_at = kwargs.pop("created_at", datetime.now(timezone.utc))
        payload_digest = json.dumps(kwargs, default=str, sort_keys=True, separators=(",", ":"))
        event_id = stable_campaign_id(
            "event", campaign_id, str(sequence), action.value, actor_id_hash, payload_digest
        )
        return self.store.append_event(
            campaign_id,
            CampaignEvent(
                event_id=event_id,
                campaign_id=campaign_id,
                sequence=sequence,
                previous_event_sha256=previous,
                action=action,
                actor_id_hash=actor_id_hash,
                created_at=created_at,
                **kwargs,
            ),
        )

    def _active_lease(
        self,
        snapshot: CampaignSnapshot,
        step_id: str,
        worker_id_hash: str,
        lease_id: str,
        moment: datetime,
    ) -> CampaignStepSnapshot:
        if snapshot.state != CampaignState.RUNNING:
            raise QualificationCampaignGateError("campaign is not running")
        step = self._step(snapshot, step_id)
        if (
            step.state != CampaignStepState.LEASED
            or step.lease is None
            or step.lease.worker_id_hash != worker_id_hash
            or step.lease.lease_id != lease_id
            or step.lease.expires_at < moment
        ):
            raise QualificationCampaignGateError("step lease is missing, expired, or mismatched")
        return step

    @staticmethod
    def _step(snapshot: CampaignSnapshot, step_id: str) -> CampaignStepSnapshot:
        try:
            return next(item for item in snapshot.steps if item.step_id == step_id)
        except StopIteration as exc:
            raise QualificationCampaignGateError("campaign step does not exist") from exc

    def _read_evidence(self, kind: CampaignEvidenceKind | None, evidence_id: str | None) -> Any:
        if kind is None or evidence_id is None:
            raise QualificationCampaignGateError("evidence identity is incomplete")
        mapping = {
            CampaignEvidenceKind.DATASET: self.production.store.read_dataset,
            CampaignEvidenceKind.PARSER: self.production.store.read_parser,
            CampaignEvidenceKind.SCALE: self.production.store.read_scale,
            CampaignEvidenceKind.SUPPLY_CHAIN: self.production.store.read_supply_chain,
            CampaignEvidenceKind.LICENSE: self.production.store.read_license,
            CampaignEvidenceKind.PILOT: self.production.store.read_pilot,
            CampaignEvidenceKind.REPORT: self.production.store.read_report,
        }
        try:
            return mapping[kind](evidence_id)
        except FileNotFoundError as exc:
            raise QualificationCampaignGateError(
                "linked production evidence does not exist"
            ) from exc
