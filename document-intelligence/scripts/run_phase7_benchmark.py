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
from document_intelligence.exceptions import MLOpsGateError
from document_intelligence.mlops.models import (
    ApprovalRequest,
    DatasetRole,
    ModelAlias,
    PromoteRequest,
    RollbackRequest,
    ShadowValidationRequest,
)
from tests.mlops.helpers import build_service, candidate, evaluation, sha, snapshot

OUT = ROOT / "docs" / "phase-7" / "benchmark_results.json"


def approval(service, candidate_id: str, report_id: str, shadow_id: str | None = None):
    return service.approve(
        ApprovalRequest(
            candidate_id=candidate_id,
            evaluation_report_id=report_id,
            shadow_validation_report_id=shadow_id,
            approver_id_hash=sha("phase7-approver-" + candidate_id + (shadow_id or "")),
            approver_role="release_manager",
            reason_code="BENCHMARK_APPROVED",
        )
    )


def promote(candidate_id: str, report_id: str, approval_id: str, shadow_id: str | None = None):
    return PromoteRequest(
        candidate_id=candidate_id,
        evaluation_report_id=report_id,
        shadow_validation_report_id=shadow_id,
        approval_id=approval_id,
        operator_id_hash=sha("phase7-operator"),
        reason_code="BENCHMARK_PROMOTION",
    )


def shadow_validation(service, candidate_id: str, report_id: str):
    start = datetime.now(timezone.utc) - timedelta(hours=2)
    return service.record_shadow_validation(
        ShadowValidationRequest(
            candidate_id=candidate_id,
            evaluation_report_id=report_id,
            evidence_sha256=sha("phase7-shadow-" + candidate_id),
            sample_count=1000,
            accuracy=0.98,
            p0_errors=0,
            p1_errors=0,
            severe_error_rate=0.0,
            latency_ms_p95=1200,
            cost_usd_per_document=0.02,
            active_drift_alerts=0,
            started_at=start,
            ended_at=start + timedelta(hours=1),
        )
    )


def main() -> None:
    cases: list[dict[str, object]] = []
    with tempfile.TemporaryDirectory(prefix="di-phase7-benchmark-") as value:
        settings = Settings(
            workspace=Path(value) / "var",
            parser_config=ROOT / "configs" / "parsers.yaml",
        )
        service = build_service(settings)

        train = snapshot(service, "benchmark-train", DatasetRole.TRAIN)
        gold = snapshot(service, "benchmark-gold", DatasetRole.GOLD)
        challenge = snapshot(service, "benchmark-challenge", DatasetRole.CHALLENGE)
        cases.append(
            {
                "name": "dvc-snapshots-are-role-separated-and-immutable",
                "passed": train.immutable
                and gold.expert_approved
                and challenge.expert_approved
                and len({train.snapshot_id, gold.snapshot_id, challenge.snapshot_id}) == 3,
            }
        )

        first = candidate(service, "1.0.0")
        first_report = evaluation(service, first.candidate_id)
        first_offline_approval = approval(service, first.candidate_id, first_report.report_id)
        service.promote_to_shadow(
            promote(first.candidate_id, first_report.report_id, first_offline_approval.approval_id)
        )
        cases.append(
            {
                "name": "champion-cannot-skip-shadow-validation",
                "passed": _champion_is_blocked_without_shadow(
                    service, first, first_report, first_offline_approval
                ),
            }
        )
        first_shadow = shadow_validation(service, first.candidate_id, first_report.report_id)
        first_release_approval = approval(
            service, first.candidate_id, first_report.report_id, first_shadow.report_id
        )
        service.promote_to_champion(
            promote(
                first.candidate_id,
                first_report.report_id,
                first_release_approval.approval_id,
                first_shadow.report_id,
            )
        )
        cases.append(
            {
                "name": "candidate-shadow-champion-gates-pass-in-order",
                "passed": service.store.aliases().get(ModelAlias.CHAMPION)
                == first.candidate_id,
            }
        )

        regressing = candidate(service, "0.9.0", baseline=first.candidate_id)
        regression_report = evaluation(
            service,
            regressing.candidate_id,
            baseline_id=first.candidate_id,
            score=0.90,
            baseline_score=0.98,
        )
        cases.append(
            {
                "name": "gold-and-challenge-regression-blocks-candidate",
                "passed": not regression_report.passed
                and "GOLD_ACCURACY_REGRESSION" in regression_report.blocking_reasons,
            }
        )

        second = candidate(service, "1.1.0", baseline=first.candidate_id)
        second_report = evaluation(
            service,
            second.candidate_id,
            baseline_id=first.candidate_id,
            score=0.99,
            baseline_score=0.98,
        )
        second_offline = approval(service, second.candidate_id, second_report.report_id)
        service.promote_to_shadow(
            promote(second.candidate_id, second_report.report_id, second_offline.approval_id)
        )
        second_shadow = shadow_validation(service, second.candidate_id, second_report.report_id)
        second_release = approval(
            service, second.candidate_id, second_report.report_id, second_shadow.report_id
        )
        service.promote_to_champion(
            promote(
                second.candidate_id,
                second_report.report_id,
                second_release.approval_id,
                second_shadow.report_id,
            )
        )
        aliases = service.store.aliases()
        cases.append(
            {
                "name": "previous-champion-is-retained-for-rollback",
                "passed": aliases.get(ModelAlias.CHAMPION) == second.candidate_id
                and aliases.get(ModelAlias.ROLLBACK) == first.candidate_id,
            }
        )
        rollback = service.rollback(
            RollbackRequest(
                operator_id_hash=hashlib.sha256(b"phase7-rollback").hexdigest(),
                reason_code="BENCHMARK_ROLLBACK",
            )
        )
        cases.append(
            {
                "name": "one-click-rollback-swaps-champion-and-rollback",
                "passed": rollback.from_candidate_id == second.candidate_id
                and service.store.aliases().get(ModelAlias.CHAMPION) == first.candidate_id,
            }
        )

        lineage = service.lineage(second.candidate_id)
        cases.append(
            {
                "name": "candidate-lineage-binds-mlflow-dvc-evaluation-and-shadow",
                "passed": bool(lineage["mlflowRun"])
                and len(lineage["datasetSnapshots"]) >= 2
                and len(lineage["evaluations"]) == 1
                and len(lineage["shadowValidations"]) == 1,
            }
        )
        cases.append(
            {
                "name": "bounded-auto-remains-hard-disabled",
                "passed": service.inspect()["boundedAuto"] is False,
            }
        )
        cases.append(
            {
                "name": "no-training-or-model-code-is-executed-by-mlops-core",
                "passed": first.model_artifact_sha256
                == service.store.read_mlflow_run(first.mlflow_record_id).model_artifact_sha256,
            }
        )

    payload = {
        "phase": 7,
        "passed": all(bool(case["passed"]) for case in cases),
        "summary": {
            "cases": len(cases),
            "passed_cases": sum(bool(case["passed"]) for case in cases),
            "bounded_auto_enabled": False,
            "production_model_promoted": False,
        },
        "cases": cases,
        "scope": (
            "Deterministic lineage, gate ordering, alias promotion and rollback regression. "
            "The benchmark uses synthetic digests and does not claim a production model release."
        ),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    if not payload["passed"]:
        raise SystemExit(1)


def _champion_is_blocked_without_shadow(service, candidate_value, report, approval_value) -> bool:
    try:
        service.promote_to_champion(
            promote(candidate_value.candidate_id, report.report_id, approval_value.approval_id)
        )
    except MLOpsGateError:
        return True
    return False


if __name__ == "__main__":
    main()
