from __future__ import annotations

import hashlib
import json
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from document_intelligence.config import Settings
from document_intelligence.rill.assist_models import (
    BOUNDED_AUTO_ENABLED,
    AssistActivationRequest,
    AssistParserResumeRequest,
    AssistParserSuspensionRequest,
    Tier1AssistAction,
)
from document_intelligence.rill.models import DriftAlert, DriftState, ShadowAction
from tests.rill.helpers import build_reference_service
from tests.rill.test_assist import activate, build_assist
from document_intelligence.rill.assist import RillAssistService
from document_intelligence.rill.assist_store import RillAssistStore
from document_intelligence.parser_sdk import ParserRegistry
from document_intelligence.services.orchestrator import ParseOrchestrator
from document_intelligence.services.store import ArtifactStore

OUT = ROOT / "docs" / "phase-6" / "benchmark_results.json"


def main() -> None:
    cases: list[dict[str, object]] = []
    with tempfile.TemporaryDirectory(prefix="di-phase6-benchmark-") as value:
        root = Path(value)

        reference_settings = Settings(
            workspace=root / "reference-var",
            parser_config=ROOT / "configs" / "parsers.yaml",
            rill_shadow_backend="reference",
            rill_reference_backend_allowed=True,
        )
        reference_shadow, _, _ = build_reference_service(reference_settings)
        reference = RillAssistService(
            reference_shadow,
            ParseOrchestrator(ParserRegistry(), ArtifactStore(reference_settings.workspace)),
            RillAssistStore(reference_settings.workspace),
            min_expert_feedback=1,
            min_production_like_feedback=1,
            min_action_feedback=1,
            runtime_artifact_sha256="1" * 64,
            model_artifact_sha256="2" * 64,
            handler_artifact_sha256="3" * 64,
        )
        reference_report = reference.qualify([Tier1AssistAction.HUMAN_REVIEW])
        cases.append(
            {
                "name": "reference-runtime-never-qualifies",
                "passed": not reference_report.qualified
                and "REFERENCE_RUNTIME_NOT_QUALIFIABLE"
                in reference_report.blocking_reasons,
            }
        )

        digest_settings = Settings(
            workspace=root / "digest-var",
            parser_config=ROOT / "configs" / "parsers.yaml",
        )
        missing_digest, _ = build_assist(
            digest_settings, action=ShadowAction.HUMAN_REVIEW, count=1
        )
        missing_digest.runtime_artifact_sha256 = None
        missing_digest_report = missing_digest.qualify(
            [Tier1AssistAction.HUMAN_REVIEW]
        )
        cases.append(
            {
                "name": "artifact-digests-are-mandatory",
                "passed": not missing_digest_report.qualified
                and "RUNTIME_ARTIFACT_DIGEST_REQUIRED"
                in missing_digest_report.blocking_reasons,
            }
        )

        review_settings = Settings(
            workspace=root / "review-var",
            parser_config=ROOT / "configs" / "parsers.yaml",
        )
        review, review_pairs = build_assist(
            review_settings, action=ShadowAction.HUMAN_REVIEW, count=2
        )
        review_report, review_activation = activate(
            review, Tier1AssistAction.HUMAN_REVIEW
        )
        first = review.execute(
            review_activation.activation_id, review_pairs[0][0].evaluation_id
        )
        repeated = review.execute(
            review_activation.activation_id, review_pairs[0][0].evaluation_id
        )
        cases.append(
            {
                "name": "qualified-additive-review-is-idempotent",
                "passed": review_report.qualified
                and first == repeated
                and first.queue_item_id is not None
                and not first.replaced_existing_result,
            }
        )

        rate_report = review.qualify([Tier1AssistAction.HUMAN_REVIEW])
        rate_activation = review.activate(
            AssistActivationRequest(
                qualification_report_id=rate_report.report_id,
                approver_id_hash=hashlib.sha256(b"rate-approver").hexdigest(),
                allowed_actions=[Tier1AssistAction.HUMAN_REVIEW],
                max_executions_per_hour=1,
                expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            )
        )
        rate_first = review.execute(
            rate_activation.activation_id, review_pairs[0][0].evaluation_id
        )
        rate_second = review.execute(
            rate_activation.activation_id, review_pairs[1][0].evaluation_id
        )
        cases.append(
            {
                "name": "rate-limit-block-is-audited",
                "passed": rate_first.status == "succeeded"
                and rate_second.status == "blocked"
                and rate_second.error_code == "ASSIST_RATE_LIMIT_REACHED",
            }
        )

        parser_settings = Settings(
            workspace=root / "parser-var",
            parser_config=ROOT / "configs" / "parsers.yaml",
        )
        parser_assist, parser_pairs = build_assist(
            parser_settings,
            action=ShadowAction.USE_SECONDARY_PARSER,
            count=1,
            with_run=True,
        )
        _, parser_activation = activate(
            parser_assist, Tier1AssistAction.USE_SECONDARY_PARSER
        )
        source_run = parser_pairs[0][0].observe_event.parse_run_id
        parser_execution = parser_assist.execute(
            parser_activation.activation_id, parser_pairs[0][0].evaluation_id
        )
        cases.append(
            {
                "name": "secondary-parser-produces-isolated-candidate",
                "passed": parser_execution.status == "succeeded"
                and parser_execution.output_run_id is not None
                and parser_execution.output_run_id != source_run
                and not parser_execution.replaced_existing_result,
            }
        )

        suspension_settings = Settings(
            workspace=root / "suspension-var",
            parser_config=ROOT / "configs" / "parsers.yaml",
        )
        suspension_assist, _ = build_assist(
            suspension_settings, action=ShadowAction.QUARANTINE, count=1
        )
        _, suspension_activation = activate(
            suspension_assist, Tier1AssistAction.QUARANTINE
        )
        alert = DriftAlert(
            alert_id="drift-alert-phase6-benchmark",
            sample_count=50,
            recent_error_rate=0.5,
            baseline_error_rate=0.1,
            page_hinkley_distance=10,
            threshold=5,
            reason_codes=["SHADOW_ERROR_RATE_DRIFT"],
        )
        suspension_assist.shadow.drift._commit_alert(alert)
        suspension_assist.shadow.drift.write(
            DriftState(alert_count=1, state_generation=1)
        )
        suspension = suspension_assist.suspend_parser(
            AssistParserSuspensionRequest(
                activation_id=suspension_activation.activation_id,
                parser_id="secondary-fixture",
                drift_alert_id=alert.alert_id,
                operator_id_hash=hashlib.sha256(b"suspend").hexdigest(),
                reason_code="DRIFT_CONFIRMED",
                expires_at=datetime.now(timezone.utc) + timedelta(minutes=30),
            )
        )
        was_suspended = suspension_assist.is_parser_suspended("secondary-fixture")
        suspension_assist.resume_parser(
            AssistParserResumeRequest(
                suspension_id=suspension.suspension_id,
                operator_id_hash=hashlib.sha256(b"resume").hexdigest(),
                reason_code="MANUAL_VALIDATION_COMPLETE",
            )
        )
        cases.append(
            {
                "name": "parser-circuit-breaker-is-drift-bound-and-reversible",
                "passed": was_suspended
                and not suspension_assist.is_parser_suspended("secondary-fixture"),
            }
        )

        cases.append(
            {
                "name": "bounded-auto-remains-hard-disabled",
                "passed": BOUNDED_AUTO_ENABLED is False
                and review.inspect()["boundedAuto"] is False,
            }
        )
        cases.append(
            {
                "name": "assist-does-not-replace-existing-results",
                "passed": all(
                    not item.replaced_existing_result
                    for item in [first, rate_first, rate_second, parser_execution]
                ),
            }
        )

    payload = {
        "phase": 6,
        "passed": all(bool(case["passed"]) for case in cases),
        "summary": {
            "cases": len(cases),
            "passed_cases": sum(bool(case["passed"]) for case in cases),
            "bounded_auto_enabled": False,
            "production_assist_activated": False,
        },
        "cases": cases,
        "scope": (
            "Deterministic qualification, additive Tier-1 execution, rate-limit and "
            "circuit-breaker regression only. Synthetic fixtures cannot qualify a real "
            "production deployment and no production Assist activation is claimed."
        ),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    if not payload["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
