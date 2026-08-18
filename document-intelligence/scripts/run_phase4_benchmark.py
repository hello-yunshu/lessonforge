from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from document_intelligence.domain_runtime import DomainExecutionStatus
from document_intelligence.review import DomainReviewService, LabelUReviewSubmission
from tests.domain_runtime.test_engine_service import build_service

OUT = ROOT / "docs" / "phase-4" / "benchmark_results.json"


def main() -> None:
    cases: list[dict[str, object]] = []
    with tempfile.TemporaryDirectory(prefix="di-phase4-benchmark-") as temp_value:
        temp = Path(temp_value)
        service, structure, parsed = build_service(temp)
        source_digest = parsed.document.semantic_digest()
        structure_digest = structure.semantic_digest()

        first = service.apply(structure.structure_id, "education-content")
        second = service.apply(structure.structure_id, "education-content")
        cases.append(
            {
                "name": "deterministic-domain-result",
                "passed": first.domain_result_id == second.domain_result_id
                and first.semantic_digest() == second.semantic_digest(),
            }
        )
        expected_types = {
            "worked_example",
            "practice",
            "reflection_prompt",
            "learner_character",
            "speech",
        }
        actual_types = {item.domain_type for item in first.annotations}
        cases.append(
            {
                "name": "education-verification-pack-object-coverage",
                "passed": expected_types.issubset(actual_types),
                "actual": sorted(actual_types),
            }
        )
        actual_relations = {item.domain_type for item in first.relations}
        cases.append(
            {
                "name": "education-verification-pack-relations",
                "passed": {"speaks", "practice_for"}.issubset(actual_relations),
                "actual": sorted(actual_relations),
            }
        )
        loaded = service.get(first.domain_result_id)
        cases.append(
            {
                "name": "domain-result-integrity-roundtrip",
                "passed": loaded.semantic_digest() == first.semantic_digest(),
            }
        )
        cases.append(
            {
                "name": "generic-artifacts-remain-immutable",
                "passed": service.artifact_store.read_result(
                    parsed.run.parse_run_id
                ).document.semantic_digest()
                == source_digest
                and service.structure_service.get(
                    structure.structure_id
                ).semantic_digest()
                == structure_digest,
            }
        )

        original_apply = service.engine.apply

        def fail_apply(*args: object, **kwargs: object) -> object:
            del args, kwargs
            raise RuntimeError("private diagnostic detail")

        service.engine.apply = fail_apply  # type: ignore[method-assign]
        fallback = service.apply(structure.structure_id, "education-content")
        service.engine.apply = original_apply  # type: ignore[method-assign]
        cases.append(
            {
                "name": "domain-failure-safe-fallback",
                "passed": fallback.status == DomainExecutionStatus.FALLBACK_GENERIC
                and not fallback.annotations
                and not fallback.relations
                and "private diagnostic" not in (fallback.failure_message or ""),
            }
        )

        review = DomainReviewService(
            temp / "var",
            service.artifact_store,
            service.structure_service,
            service,
        )
        export_one = review.export_labelu(first.domain_result_id)
        export_two = review.export_labelu(first.domain_result_id)
        cases.append(
            {
                "name": "review-export-idempotent",
                "passed": export_one.model_dump(mode="json")
                == export_two.model_dump(mode="json"),
            }
        )
        submission = LabelUReviewSubmission(
            export_id=export_one.export_id,
            domain_result_id=first.domain_result_id,
            source_domain_digest=first.semantic_digest(),
            reviewer="phase4-benchmark",
            review_level="domain-expert",
            reason="deterministic verification submission",
        )
        record = review.submit_labelu(submission)
        cases.append(
            {
                "name": "review-submission-roundtrip",
                "passed": review.get_review(record.review_id).semantic_digest()
                == record.semantic_digest(),
            }
        )

    payload = {
        "phase": 4,
        "passed": all(bool(case["passed"]) for case in cases),
        "summary": {
            "cases": len(cases),
            "passed_cases": sum(bool(case["passed"]) for case in cases),
            "fallback_assertion_count": len(fallback.annotations) + len(fallback.relations),
            "annotation_evidence_coverage": first.metrics.annotation_evidence_coverage,
        },
        "cases": cases,
        "scope": (
            "Deterministic synthetic Domain Pack Runtime regression only; "
            "not a production-domain accuracy claim."
        ),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    if not payload["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
