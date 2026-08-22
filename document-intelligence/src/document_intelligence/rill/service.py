from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from document_intelligence.exceptions import (
    RillFeedbackError,
    RillProtocolError,
    RillUnavailableError,
)
from document_intelligence.matching import MatchResult
from document_intelligence.rill.client import RillShadowClient, RuntimeSnapshot
from document_intelligence.rill.drift import ShadowDriftMonitor
from document_intelligence.rill.features import ShadowFeatureBuilder
from document_intelligence.rill.models import (
    ShadowEvaluation,
    ShadowEvaluationStatus,
    ShadowFeedbackInput,
    ShadowFeedbackRecord,
    ShadowResetRecord,
    ShadowSnapshotRecord,
    canonical_json_digest,
    stable_rill_id,
)
from document_intelligence.rill.policy import StaticShadowPolicy, calculate_reward
from document_intelligence.rill.replay import ShadowReplayService
from document_intelligence.rill.store import RillShadowStore


class RillShadowService:
    def __init__(
        self,
        feature_builder: ShadowFeatureBuilder,
        store: RillShadowStore,
        drift: ShadowDriftMonitor,
        *,
        client: RillShadowClient | None,
        backend_name: str,
    ) -> None:
        self.feature_builder = feature_builder
        self.store = store
        self.drift = drift
        self.client = client
        self.backend_name = backend_name
        self.static_policy = StaticShadowPolicy()
        self.replay = ShadowReplayService(store, drift)

    def evaluate(
        self,
        parse_run_id: str,
        *,
        structure_id: str | None = None,
        domain_result_id: str | None = None,
        match_result: MatchResult | None = None,
    ) -> ShadowEvaluation:
        event = self.feature_builder.build(
            parse_run_id,
            structure_id=structure_id,
            domain_result_id=domain_result_id,
            match_result=match_result,
        )
        input_model_generation = self.client.model_generation if self.client else 0
        input_state_generation = self.client.state_generation if self.client else 0
        existing = self.store.evaluation_for_context(
            event.event_id,
            backend_name=self.backend_name,
            model_generation=input_model_generation,
            state_generation=input_state_generation,
        )
        if existing is not None:
            return existing
        static_suggestion = self.static_policy.decide(event)
        rill_suggestion = None
        runtime_identity = None
        runtime_error_code = None
        runtime_error_message = None
        if self.client is None:
            status = ShadowEvaluationStatus.RUNTIME_UNAVAILABLE
            runtime_error_code = "RILL_BACKEND_DISABLED"
            runtime_error_message = "Rill Shadow backend is disabled or not configured"
        else:
            try:
                if not getattr(self.client, "host_owned_state", False):
                    self.client.observe(event)
                deterministic_seed = int(
                    hashlib.sha256(event.event_id.encode()).hexdigest()[:16], 16
                )
                rill_suggestion = self.client.decide(
                    event,
                    static_suggestion=static_suggestion,
                    deterministic_seed=deterministic_seed,
                )
                runtime_identity = self.client.identity
                status = ShadowEvaluationStatus.SUCCEEDED
            except RillUnavailableError:
                status = ShadowEvaluationStatus.RUNTIME_UNAVAILABLE
                runtime_error_code = "RILL_RUNTIME_UNAVAILABLE"
                runtime_error_message = "Rill runtime was unavailable; no production action changed"
            except RillProtocolError:
                status = ShadowEvaluationStatus.RUNTIME_ERROR
                runtime_error_code = "RILL_PROTOCOL_ERROR"
                runtime_error_message = "Rill runtime violated the validated Shadow contract"
            except Exception:
                status = ShadowEvaluationStatus.RUNTIME_ERROR
                runtime_error_code = "RILL_UNEXPECTED_ERROR"
                runtime_error_message = "Rill Shadow evaluation failed safely"
        evaluation_id = stable_rill_id(
            "shadow-evaluation",
            event.event_id,
            static_suggestion.decision_id,
            rill_suggestion.decision_id if rill_suggestion else runtime_error_code or "none",
            self.feature_builder.feature_schema_hash,
        )
        evaluation = ShadowEvaluation(
            evaluation_id=evaluation_id,
            feature_schema_hash=self.feature_builder.feature_schema_hash,
            observe_event=event,
            static_suggestion=static_suggestion,
            rill_suggestion=rill_suggestion,
            runtime_identity=runtime_identity,
            backend_name=self.backend_name,
            input_model_generation=input_model_generation,
            input_state_generation=input_state_generation,
            status=status,
            runtime_error_code=runtime_error_code,
            runtime_error_message=runtime_error_message,
        )
        return self.store.commit_evaluation(evaluation)

    def get(self, evaluation_id: str) -> ShadowEvaluation:
        return self.store.read_evaluation(evaluation_id)

    def feedback(self, payload: ShadowFeedbackInput) -> ShadowFeedbackRecord:
        existing = self.store.feedback_for_evaluation(payload.evaluation_id)
        evaluation = self.store.read_evaluation(payload.evaluation_id)
        suggestion = evaluation.rill_suggestion or evaluation.static_suggestion
        reward = calculate_reward(
            decision_correct=payload.decision_correct,
            severity=payload.severity,
            human_edit_seconds=payload.human_edit_seconds,
            suggested_action=suggestion.action,
            actual_action=payload.actual_action,
        )
        feedback_id = stable_rill_id("shadow-feedback", payload.evaluation_id)
        if existing is not None:
            candidate = existing.model_copy()
            if (
                candidate.actual_action != payload.actual_action
                or candidate.decision_correct != payload.decision_correct
                or candidate.error_scope != payload.error_scope
                or candidate.error_type != payload.error_type
                or candidate.severity != payload.severity
                or candidate.human_edit_seconds != payload.human_edit_seconds
                or candidate.eligible_for_training != payload.eligible_for_training
                or candidate.reward != reward
            ):
                raise RillFeedbackError("a different final feedback already exists")
            self._reconcile_drift()
            return existing

        runtime_accepted = False
        runtime_error_code: str | None = None
        if evaluation.rill_suggestion is None or self.client is None:
            runtime_error_code = "RILL_DECISION_UNAVAILABLE"
        elif getattr(self.client, "host_owned_state", False) and not getattr(
            self.client, "feedback_capability", None
        ):
            # Stable IPC v2 has no stateful feedback operation. The immutable
            # ledger below is the accepted feedback record; do not claim that
            # the external Runtime accepted or persisted it.
            runtime_error_code = "RILL_HOST_OWNED_FEEDBACK"
        else:
            try:
                self.client.feedback(
                    decision_id=evaluation.rill_suggestion.decision_id,
                    selected_arm=evaluation.rill_suggestion.selected_arm,
                    reward=reward,
                    outcome_time_ms=payload.outcome_time_ms,
                    generation=evaluation.rill_suggestion.state_generation,
                )
                runtime_accepted = True
            except RillUnavailableError:
                runtime_error_code = "RILL_RUNTIME_UNAVAILABLE"
            except RillProtocolError:
                runtime_error_code = "RILL_FEEDBACK_REJECTED"
            except Exception:
                runtime_error_code = "RILL_FEEDBACK_FAILED"

        record = ShadowFeedbackRecord(
            feedback_id=feedback_id,
            evaluation_id=evaluation.evaluation_id,
            decision_id=suggestion.decision_id,
            selected_arm=suggestion.selected_arm,
            actual_action=payload.actual_action,
            decision_correct=payload.decision_correct,
            error_scope=payload.error_scope,
            error_type=payload.error_type,
            severity=payload.severity,
            human_edit_seconds=payload.human_edit_seconds,
            eligible_for_training=payload.eligible_for_training,
            reward=reward,
            runtime_feedback_accepted=runtime_accepted,
            runtime_error_code=runtime_error_code,
        )
        committed = self.store.commit_feedback(record)
        self._reconcile_drift()
        return committed

    def inspect(self) -> dict[str, Any]:
        runtime: dict[str, Any]
        if self.client is None:
            runtime = {
                "available": False,
                "backend": self.backend_name,
                "errorCode": "RILL_BACKEND_DISABLED",
            }
        else:
            try:
                runtime = {
                    "available": True,
                    "backend": self.backend_name,
                    "identity": self.client.identity.model_dump(mode="json"),
                    "modelGeneration": self.client.model_generation,
                    "stateGeneration": self.client.state_generation,
                    "summary": self.client.inspect(),
                }
            except Exception:
                runtime = {
                    "available": False,
                    "backend": self.backend_name,
                    "errorCode": "RILL_INSPECT_FAILED",
                }
        return {
            "shadowOnly": True,
            "noProductionActions": True,
            "hostOwnedFeedback": True,
            "runtimeReset": False,
            "featureSchemaHash": self.feature_builder.feature_schema_hash,
            "runtime": runtime,
            "drift": self.drift.read().model_dump(mode="json"),
            "replay": self.replay.metrics().model_dump(mode="json"),
        }

    def snapshot(self) -> ShadowSnapshotRecord:
        if self.client is None:
            raise RillUnavailableError("Rill runtime is not configured")
        if getattr(self.client, "host_owned_state", False):
            # Stable IPC v2 executes a signed handler but has no stateful
            # observe/snapshot/reset operation. The business ledger and drift
            # state therefore remain a Host-owned, immutable snapshot.
            state = json.dumps(
                {
                    "schemaVersion": 1,
                    "hostOwned": True,
                    "evaluationDigests": [
                        item.semantic_digest() for item in self.store.list_evaluations()
                    ],
                    "feedbackDigests": [
                        item.semantic_digest() for item in self.store.list_feedback()
                    ],
                    "drift": self.drift.read().model_dump(mode="json"),
                },
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            snapshot = RuntimeSnapshot(
                state_schema_version=1,
                state_checksum=hashlib.sha256(state.encode("utf-8")).hexdigest(),
                state=state,
                model_generation=self.client.model_generation,
                state_generation=self.client.state_generation,
            )
        else:
            snapshot = self.client.snapshot()
        drift_state = self.drift.read().model_dump(mode="json")
        drift_checksum = canonical_json_digest(drift_state)
        snapshot_id = stable_rill_id(
            "shadow-snapshot",
            snapshot.state_checksum,
            drift_checksum,
            str(snapshot.model_generation),
            str(snapshot.state_generation),
        )
        state_ref = f"rill-shadow/snapshots/{snapshot_id}/state.txt"
        identity = self.client.identity
        record = ShadowSnapshotRecord(
            snapshot_id=snapshot_id,
            feature_schema_hash=self.feature_builder.feature_schema_hash,
            runtime_name=identity.name,
            runtime_version=identity.version,
            model_generation=snapshot.model_generation,
            state_generation=snapshot.state_generation,
            state_schema_version=snapshot.state_schema_version,
            state_checksum=snapshot.state_checksum,
            state_ref=state_ref,
            drift_state_checksum=drift_checksum,
        )
        return self.store.commit_snapshot(record, state=snapshot.state, drift_state=drift_state)

    def reset(self) -> ShadowResetRecord:
        if self.client is None:
            raise RillUnavailableError("Rill runtime is not configured")
        pre_reset = self.snapshot()
        expected = self.client.state_generation
        previous_drift = self.drift.read()
        drift = self.drift.reset()
        try:
            reset_generation = self.client.reset(expected_state_generation=expected)
        except Exception:
            # Keep host-side drift state aligned when the external Runtime did
            # not accept the reset. The immutable pre-reset snapshot remains
            # available for audit and operator recovery.
            self.drift.write(previous_drift)
            raise
        reset_id = stable_rill_id(
            "shadow-reset",
            pre_reset.snapshot_id,
            str(expected),
            str(reset_generation),
            str(drift.state_generation),
        )
        record = ShadowResetRecord(
            reset_id=reset_id,
            pre_reset_snapshot_id=pre_reset.snapshot_id,
            expected_state_generation=expected,
            reset_state_generation=reset_generation,
            runtime_reset=not getattr(self.client, "host_owned_state", False),
            local_drift_reset=True,
        )
        return self.store.commit_reset(record)

    def _reconcile_drift(self) -> None:
        resets = self.store.list_resets()
        latest_reset = max((item.created_at for item in resets), default=None)
        self.drift.reconcile(self.store.list_feedback(), reset_after=latest_reset)

    def close(self) -> None:
        if self.client is not None:
            self.client.close()
