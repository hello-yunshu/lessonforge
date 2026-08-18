from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import yaml

from document_intelligence.domain_pack_sdk import LoadedDomainPack, load_domain_pack
from document_intelligence.domain_regression.models import (
    CrossDomainRegressionReport,
    CrossDomainRegressionSuite,
    DomainRegressionCase,
    DomainRegressionCaseResult,
)
from document_intelligence.domain_runtime import DomainRuntimeEngine
from document_intelligence.family import DocumentFamilyDetector, FamilyDecision
from document_intelligence.schema import (
    Confidence,
    Element,
    ElementContent,
    Evidence,
    EvidenceKind,
    Page,
    ParsedDocument,
    SourceDescriptor,
)
from document_intelligence.structure import StructureRecoveryEngine


class CrossDomainRegressionRunner:
    def __init__(self, pack_roots: list[Path]) -> None:
        self.packs = [load_domain_pack(root) for root in pack_roots]
        self.pack_by_id = {pack.manifest.id: pack for pack in self.packs}
        if len(self.pack_by_id) != len(self.packs):
            raise ValueError("cross-domain regression pack IDs must be unique")
        self.structure_engine = StructureRecoveryEngine()
        self.domain_engine = DomainRuntimeEngine()
        self.family_detector = DocumentFamilyDetector()

    @staticmethod
    def load_suite(path: Path) -> CrossDomainRegressionSuite:
        return CrossDomainRegressionSuite.model_validate(
            yaml.safe_load(path.read_text(encoding="utf-8"))
        )

    def run(self, suite: CrossDomainRegressionSuite) -> CrossDomainRegressionReport:
        from document_intelligence.schema import ParsedDocument as CoreParsedDocument

        core_schema_digest = hashlib.sha256(
            json.dumps(
                CoreParsedDocument.model_json_schema(),
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        results = [self._run_case(case) for case in suite.cases]
        passed_cases = sum(item.passed for item in results)
        family_accuracy = (
            sum(item.detected_pack_id == item.expected_pack_id for item in results) / len(results)
            if results
            else 1.0
        )
        suite_digest = hashlib.sha256(
            json.dumps(
                suite.model_dump(mode="json"),
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        return CrossDomainRegressionReport(
            suite_digest=suite_digest,
            engine_digest=self.domain_engine.runtime_digest,
            detector_digest=self.family_detector.detector_digest,
            passed=passed_cases == len(results) and core_schema_digest == suite.core_schema_sha256,
            total_cases=len(results),
            passed_cases=passed_cases,
            family_accuracy=family_accuracy,
            core_schema_unchanged=core_schema_digest == suite.core_schema_sha256,
            cases=results,
        )

    def _run_case(self, case: DomainRegressionCase) -> DomainRegressionCaseResult:
        document = self._build_document(case)
        original_digest = document.semantic_digest()
        structure = self.structure_engine.recover(document)
        detection = self.family_detector.detect(document, structure, self.packs)
        expected_pack = self.pack_by_id.get(case.expected_pack_id)
        failures: list[str] = []
        if expected_pack is None:
            failures.append("EXPECTED_PACK_MISSING")
            return DomainRegressionCaseResult(
                case_id=case.case_id,
                passed=False,
                expected_pack_id=case.expected_pack_id,
                error_findings=0,
                family_score=0.0,
                source_unchanged=document.semantic_digest() == original_digest,
                evidence_complete=False,
                isolated_results=False,
                failure_codes=failures,
            )
        intended = self.domain_engine.apply(document, structure, expected_pack)
        annotation_types = sorted({item.domain_type for item in intended.annotations})
        missing = sorted(set(case.expected_annotation_types) - set(annotation_types))
        forbidden = sorted(set(case.forbidden_annotation_types) & set(annotation_types))
        if missing:
            failures.append("EXPECTED_ANNOTATION_TYPES_MISSING")
        if forbidden:
            failures.append("FORBIDDEN_ANNOTATION_TYPES_PRESENT")
        if intended.metrics.error_findings > case.maximum_error_findings:
            failures.append("ERROR_FINDING_LIMIT_EXCEEDED")
        if detection.decision != FamilyDecision.CANDIDATE:
            failures.append("FAMILY_NOT_DETERMINISTIC_CANDIDATE")
        if detection.selected_pack_id != case.expected_pack_id:
            failures.append("FAMILY_PACK_MISMATCH")
        if detection.selected_family_id != case.expected_family_id:
            failures.append("FAMILY_ID_MISMATCH")
        source_unchanged = document.semantic_digest() == original_digest
        if not source_unchanged:
            failures.append("CORE_DOCUMENT_MUTATED")
        evidence_complete = all(item.evidence_ids for item in intended.annotations) and all(
            item.evidence_ids for item in intended.relations
        )
        if not evidence_complete:
            failures.append("DOMAIN_EVIDENCE_INCOMPLETE")
        outputs = [self.domain_engine.apply(document, structure, pack) for pack in self.packs]
        output_ids = [item.domain_result_id for item in outputs]
        isolated_results = (
            len(output_ids) == len(set(output_ids))
            and all(
                set(annotation.domain_type for annotation in output.annotations).issubset(
                    set(pack.ontology.object_types)
                )
                for output, pack in zip(outputs, self.packs, strict=True)
            )
            and all(
                output.pack_id == pack.manifest.id
                for output, pack in zip(outputs, self.packs, strict=True)
            )
        )
        if not isolated_results:
            failures.append("DOMAIN_ISOLATION_FAILED")
        top = detection.candidates[0] if detection.candidates else None
        family_score = top.score if top and top.pack_id == case.expected_pack_id else 0.0
        return DomainRegressionCaseResult(
            case_id=case.case_id,
            passed=not failures,
            expected_pack_id=case.expected_pack_id,
            detected_pack_id=detection.selected_pack_id,
            detected_family_id=detection.selected_family_id,
            annotation_types=annotation_types,
            error_findings=intended.metrics.error_findings,
            family_score=family_score,
            source_unchanged=source_unchanged,
            evidence_complete=evidence_complete,
            isolated_results=isolated_results,
            failure_codes=failures,
        )

    @staticmethod
    def _build_document(case: DomainRegressionCase) -> ParsedDocument:
        material = json.dumps(
            case.model_dump(mode="json"),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        source_hash = hashlib.sha256(material).hexdigest()
        run_id = f"run_{source_hash[:20]}"
        page_id = "page_0"
        fixed_time = datetime(2026, 1, 1, tzinfo=timezone.utc)
        elements: list[Element] = []
        evidence: list[Evidence] = []
        for spec in case.elements:
            evidence_id = f"ev_{spec.element_id}"
            evidence.append(
                Evidence(
                    evidence_id=evidence_id,
                    kind=EvidenceKind.MODEL_PREDICTION,
                    producer="cross-domain-fixture",
                    producer_version="1.0.0",
                    model_digest="0" * 64,
                    parse_run_id=run_id,
                    source_page_id=page_id,
                    bbox=spec.bbox,
                    created_at=fixed_time,
                )
            )
            elements.append(
                Element(
                    element_id=spec.element_id,
                    page_id=page_id,
                    base_type=spec.base_type,
                    subtype=spec.subtype,
                    bbox=spec.bbox,
                    content=ElementContent(text=spec.text),
                    confidence=Confidence(overall=0.95),
                    evidence_ids=[evidence_id],
                )
            )
        return ParsedDocument(
            document_id=f"doc_{source_hash[:20]}",
            source=SourceDescriptor(
                filename=case.filename,
                sha256=source_hash,
                mime_type=case.mime_type,
                size_bytes=len(material),
            ),
            pages=[
                Page(
                    page_id=page_id,
                    index=0,
                    width=1000,
                    height=1000,
                    element_ids=[element.element_id for element in elements],
                )
            ],
            elements=elements,
            evidence=evidence,
            parse_run_id=run_id,
        )
