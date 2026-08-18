from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from document_intelligence.config import Settings
from document_intelligence.rill.client import ReferenceRillShadowClient
from document_intelligence.rill.models import FeedbackSeverity, ShadowAction, ShadowFeedbackInput
from document_intelligence.services import build_rill_shadow_service
from tests.rill.helpers import build_committed_run

OUT = ROOT / "docs" / "phase-5" / "benchmark_results.json"


def main() -> None:
    cases: list[dict[str, object]] = []
    with tempfile.TemporaryDirectory(prefix="di-phase5-benchmark-") as value:
        workspace = Path(value) / "var"
        settings = Settings(
            workspace=workspace,
            parser_config=ROOT / "configs" / "parsers.yaml",
            rill_shadow_backend="reference",
            rill_reference_backend_allowed=True,
            enable_rill_shadow_writes=True,
            rill_drift_min_samples=5,
            rill_drift_threshold=0.2,
            rill_drift_delta=0,
        )
        run_id, structure_id = build_committed_run(settings)
        service = build_rill_shadow_service(settings)
        first = service.evaluate(run_id, structure_id=structure_id)
        generation = service.client.state_generation if service.client else -1
        second = service.evaluate(run_id, structure_id=structure_id)
        cases.append({
            "name": "idempotent-observe-decide",
            "passed": first.evaluation_id == second.evaluation_id
            and (service.client.state_generation if service.client else -2) == generation,
        })
        cases.append({
            "name": "shadow-never-executes",
            "passed": first.shadow_only and first.no_action_executed,
        })
        suggestion = first.rill_suggestion or first.static_suggestion
        feedback = service.feedback(ShadowFeedbackInput(
            evaluation_id=first.evaluation_id,
            actual_action=suggestion.action,
            decision_correct=True,
            error_scope="route",
            error_type="none",
            severity=FeedbackSeverity.P2,
            human_edit_seconds=0,
            eligible_for_training=True,
            outcome_time_ms=1,
        ))
        cases.append({
            "name": "delayed-feedback-roundtrip",
            "passed": feedback.runtime_feedback_accepted and feedback.reward > 0,
        })
        snapshot_one = service.snapshot()
        snapshot_two = service.snapshot()
        cases.append({
            "name": "snapshot-idempotent-and-verifiable",
            "passed": snapshot_one.snapshot_id == snapshot_two.snapshot_id
            and service.store.read_snapshot(snapshot_one.snapshot_id)[0] == snapshot_one,
        })
        inspection = service.inspect()
        cases.append({
            "name": "inspect-explicitly-shadow-only",
            "passed": inspection["shadowOnly"] is True
            and inspection["noProductionActions"] is True,
        })
        service.close()

        disabled = settings.model_copy(update={
            "workspace": Path(value) / "disabled-var",
            "rill_shadow_backend": "disabled",
        })
        disabled_run_id, disabled_structure_id = build_committed_run(disabled)
        unavailable = build_rill_shadow_service(disabled)
        isolated = unavailable.evaluate(disabled_run_id, structure_id=disabled_structure_id)
        cases.append({
            "name": "runtime-failure-safe-isolation",
            "passed": isolated.status == "runtime_unavailable"
            and isolated.no_action_executed,
        })
        unavailable.close()

        reference = ReferenceRillShadowClient("a" * 64)
        cases.append({
            "name": "reference-backend-distinct-identity",
            "passed": reference.identity.name != "rill-runtime"
            and "reference" in reference.identity.name,
        })
        reference.close()

    payload = {
        "phase": 5,
        "passed": all(bool(case["passed"]) for case in cases),
        "summary": {
            "cases": len(cases),
            "passed_cases": sum(bool(case["passed"]) for case in cases),
            "production_actions_executed": 0,
        },
        "cases": cases,
        "scope": (
            "Deterministic Rill Shadow lifecycle and failure-isolation regression only; "
            "not a production routing-quality or real-runtime accuracy claim."
        ),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    if not payload["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
