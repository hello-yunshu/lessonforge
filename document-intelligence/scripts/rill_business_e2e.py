"""Qualify LessonForge's real Stable v2 consumer path on official Runtime 1.2.0."""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from document_intelligence.config import Settings
from document_intelligence.rill.adoption import load_adoption_lock
from document_intelligence.rill.distribution import RillAdoptionManager
from document_intelligence.rill.models import FeedbackSeverity, ShadowFeedbackInput
from document_intelligence.services import build_rill_shadow_service
from tests.rill.helpers import build_committed_run


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index", type=Path, required=True)
    parser.add_argument("--runtime", type=Path, required=True)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--handler", type=Path, required=True)
    parser.add_argument("--rill-pack", type=Path, required=True)
    parser.add_argument("--public-key", required=True)
    args = parser.parse_args()
    lock = load_adoption_lock()
    cases: list[dict[str, object]] = []
    with tempfile.TemporaryDirectory(prefix="lessonforge-rill-business-") as temporary:
        workspace = Path(temporary) / "var"
        manager = RillAdoptionManager(workspace)
        # The runtime is already downloaded and independently checked against
        # the upstream signed index by the Action. install_bundle still
        # verifies the bytes and records one atomic complete bundle.
        metadata = manager.install_bundle(
            args.index.read_bytes(),
            runtime_path=args.runtime,
            model_path=args.model,
            handler_path=args.handler,
            model_id="org.lessonforge.shadow.model",
            model_version="1.2.0",
            handler_id="org.lessonforge.shadow.handler",
            handler_version="1.2.0",
            model_key_id="lessonforge-ci-test-2026",
            model_public_key=args.public_key,
            handler_key_id="lessonforge-ci-test-2026",
            handler_public_key=args.public_key,
            rill_pack_command=(str(args.rill_pack),),
            feature_schema_hash="0" * 64,
            target=("linux", "x86_64", "gnu"),
        )
        cases.append({
            "name": "managed-bundle-qualified",
            "passed": metadata["qualification"] == "VERIFIED"
            and metadata["runtimeApi"] == 2
            and metadata["handlerApi"] == 1
            and metadata["capabilities"] == ["org.lessonforge.shadow.evaluate"],
        })

        settings = Settings(
            workspace=workspace,
            parser_config=ROOT / "configs" / "parsers.yaml",
            rill_shadow_backend="stable-v2",
            enable_rill_shadow_writes=True,
            rill_drift_min_samples=5,
            rill_drift_threshold=0.2,
            rill_drift_delta=0,
        )
        parse_run_id, structure_id = build_committed_run(settings)
        service = build_rill_shadow_service(settings)
        try:
            evaluation = service.evaluate(parse_run_id, structure_id=structure_id)
            suggestion = evaluation.rill_suggestion
            cases.append({
                "name": "real-rill-shadow-service-evaluate",
                "passed": evaluation.status.value == "succeeded"
                and suggestion is not None
                and suggestion.action.value == "HUMAN_REVIEW"
                and evaluation.runtime_identity is not None
                and evaluation.runtime_identity.name == "org.lessonforge.shadow.handler"
                and evaluation.runtime_identity.version == lock.supported,
            })
            if suggestion is None:
                raise SystemExit("LessonForge business handler returned no suggestion")
            feedback = service.feedback(
                ShadowFeedbackInput(
                    evaluation_id=evaluation.evaluation_id,
                    actual_action=suggestion.action,
                    decision_correct=True,
                    error_scope="route",
                    error_type="none",
                    severity=FeedbackSeverity.P2,
                    human_edit_seconds=0,
                    eligible_for_training=True,
                    outcome_time_ms=1,
                )
            )
            cases.append({
                "name": "host-owned-feedback",
                "passed": feedback.runtime_feedback_accepted is False
                and feedback.runtime_error_code == "RILL_HOST_OWNED_FEEDBACK",
            })
            snapshot = service.snapshot()
            snapshot_state = json.loads(service.store.read_snapshot(snapshot.snapshot_id)[1])
            reset = service.reset()
            cases.append({
                "name": "host-owned-snapshot-reset",
                "passed": reset.runtime_reset is False
                and reset.local_drift_reset is True
                and snapshot_state["hostOwned"] is True,
            })
        finally:
            service.close()

    result = {
        "status": "PASS" if all(bool(case["passed"]) for case in cases) else "FAIL",
        "rillRelease": lock.supported,
        "runtimeSource": f"{lock.upstream_repository}@{lock.tag}",
        "productionProtocol": lock.production_protocol,
        "cases": cases,
        "productionActionsExecuted": 0,
        "feedbackStateOwner": "LessonForge Host",
    }
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    if result["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
