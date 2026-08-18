from __future__ import annotations

import hashlib
import re
from collections import defaultdict
from pathlib import Path
from typing import Iterable

from document_intelligence.domain_pack_sdk import LoadedDomainPack, ObjectRule, RelationRule
from document_intelligence.domain_runtime.models import (
    DomainAnnotation,
    DomainExecutionStatus,
    DomainMetrics,
    DomainRelationAnnotation,
    DomainResult,
    DomainValidationFinding,
)
from document_intelligence.parser_sdk.utils import stable_id
from document_intelligence.schema import Element, ParsedDocument, Relation
from document_intelligence.structure import StructureResult


class DomainRuntimeEngine:
    runtime_version = "1.0.0"

    def __init__(self) -> None:
        implementation = Path(__file__).read_bytes()
        models = Path(__file__).with_name("models.py").read_bytes()
        sdk = Path(__file__).parents[1] / "domain_pack_sdk" / "models.py"
        self.runtime_digest = hashlib.sha256(
            implementation
            + b"\0"
            + models
            + b"\0"
            + sdk.read_bytes()
            + b"\0"
            + self.runtime_version.encode()
        ).hexdigest()

    def apply(
        self,
        document: ParsedDocument,
        structure: StructureResult,
        pack: LoadedDomainPack,
    ) -> DomainResult:
        if document.document_id != structure.document_id:
            raise ValueError("domain runtime document and structure identities differ")
        if document.parse_run_id != structure.parse_run_id:
            raise ValueError("domain runtime parse and structure run identities differ")
        element_by_id = {item.element_id: item for item in document.elements}
        evidence_ids = {item.evidence_id for item in document.evidence} | {
            item.evidence_id for item in structure.evidence
        }
        reading_index = {
            element_id: index for index, element_id in enumerate(structure.content_reading_order)
        }
        annotations: list[DomainAnnotation] = []
        annotations_by_element: dict[str, list[DomainAnnotation]] = defaultdict(list)
        stopped: set[str] = set()
        for element_id in structure.content_reading_order:
            element = element_by_id[element_id]
            for rule in pack.rules.object_rules:
                if element_id in stopped:
                    break
                if not self._object_rule_matches(rule, element):
                    continue
                source_evidence = [item for item in element.evidence_ids if item in evidence_ids]
                if not source_evidence:
                    raise ValueError(
                        f"domain rule {rule.id} matched an element without valid evidence"
                    )
                annotation = DomainAnnotation(
                    annotation_id=stable_id(
                        "dann", pack.content_digest, structure.structure_id, rule.id, element_id
                    ),
                    element_id=element_id,
                    domain_type=rule.domain_type,
                    properties=rule.properties,
                    confidence=min(rule.confidence, element.confidence.overall),
                    evidence_ids=source_evidence,
                    rule_id=rule.id,
                )
                annotations.append(annotation)
                annotations_by_element[element_id].append(annotation)
                if rule.stop_on_match:
                    stopped.add(element_id)

        relations = self._relation_annotations(
            pack,
            structure,
            annotations_by_element,
            reading_index,
            evidence_ids,
        )
        findings = self._validate(pack, annotations, relations)
        metrics = DomainMetrics(
            source_elements=len(document.elements),
            source_relations=len(structure.relations),
            annotations=len(annotations),
            domain_relations=len(relations),
            validation_findings=len(findings),
            error_findings=sum(item.severity == "error" for item in findings),
            annotation_evidence_coverage=1.0 if annotations else 1.0,
            fallback_used=False,
        )
        result_id = stable_id(
            "domain",
            structure.structure_id,
            structure.semantic_digest(),
            pack.manifest.id,
            pack.manifest.version,
            pack.content_digest,
            self.runtime_digest,
        )
        return DomainResult(
            domain_result_id=result_id,
            runtime_version=self.runtime_version,
            runtime_digest=self.runtime_digest,
            structure_id=structure.structure_id,
            source_structure_digest=structure.semantic_digest(),
            document_id=document.document_id,
            parse_run_id=document.parse_run_id,
            pack_id=pack.manifest.id,
            pack_version=pack.manifest.version,
            pack_digest=pack.content_digest,
            status=DomainExecutionStatus.SUCCEEDED,
            annotations=annotations,
            relations=relations,
            findings=findings,
            metrics=metrics,
        )

    def fallback(
        self,
        document: ParsedDocument,
        structure: StructureResult,
        pack: LoadedDomainPack,
        *,
        code: str,
        message: str,
    ) -> DomainResult:
        result_id = stable_id(
            "domain",
            structure.structure_id,
            structure.semantic_digest(),
            pack.manifest.id,
            pack.manifest.version,
            pack.content_digest,
            self.runtime_digest,
            "fallback",
            code,
            message,
        )
        return DomainResult(
            domain_result_id=result_id,
            runtime_version=self.runtime_version,
            runtime_digest=self.runtime_digest,
            structure_id=structure.structure_id,
            source_structure_digest=structure.semantic_digest(),
            document_id=document.document_id,
            parse_run_id=document.parse_run_id,
            pack_id=pack.manifest.id,
            pack_version=pack.manifest.version,
            pack_digest=pack.content_digest,
            status=DomainExecutionStatus.FALLBACK_GENERIC,
            annotations=[],
            relations=[],
            findings=[],
            metrics=DomainMetrics(
                source_elements=len(document.elements),
                source_relations=len(structure.relations),
                annotations=0,
                domain_relations=0,
                validation_findings=0,
                error_findings=0,
                annotation_evidence_coverage=1.0,
                fallback_used=True,
            ),
            failure_code=code,
            failure_message=message[:4000],
        )

    @staticmethod
    def _object_rule_matches(rule: ObjectRule, element: Element) -> bool:
        if rule.base_types and element.base_type not in rule.base_types:
            return False
        if rule.subtypes and element.subtype not in rule.subtypes:
            return False
        text = (element.content.text or "").strip()
        if rule.require_text and not text:
            return False
        # OCR 常在汉字/字母间插入空格（含 em-space U+2003），
        # 统一移除空白后再做关键词匹配，避免"练 习 一"匹配不到"练习"。
        folded = re.sub(r"\s+", "", text.casefold())
        if rule.text_contains_any and not any(
            term.casefold() in folded for term in rule.text_contains_any
        ):
            return False
        if rule.text_starts_with_any and not any(
            folded.startswith(term.casefold()) for term in rule.text_starts_with_any
        ):
            return False
        return True

    def _relation_annotations(
        self,
        pack: LoadedDomainPack,
        structure: StructureResult,
        annotations_by_element: dict[str, list[DomainAnnotation]],
        reading_index: dict[str, int],
        evidence_ids: set[str],
    ) -> list[DomainRelationAnnotation]:
        output: list[DomainRelationAnnotation] = []
        structure_relations = list(structure.relations)
        for rule in pack.rules.relation_rules:
            candidates = self._candidate_pairs(
                rule, structure_relations, annotations_by_element, reading_index
            )
            for source_id, target_id, base_relation, relation_evidence in candidates:
                valid_evidence = [item for item in relation_evidence if item in evidence_ids]
                if not valid_evidence:
                    source_annotations = annotations_by_element[source_id]
                    target_annotations = annotations_by_element[target_id]
                    valid_evidence = list(
                        dict.fromkeys(
                            [
                                *source_annotations[0].evidence_ids,
                                *target_annotations[0].evidence_ids,
                            ]
                        )
                    )
                output.append(
                    DomainRelationAnnotation(
                        relation_id=stable_id(
                            "drel",
                            pack.content_digest,
                            structure.structure_id,
                            rule.id,
                            source_id,
                            target_id,
                        ),
                        source_id=source_id,
                        target_id=target_id,
                        domain_type=rule.domain_type,
                        base_relation_type=base_relation,
                        confidence=rule.confidence,
                        evidence_ids=valid_evidence,
                        rule_id=rule.id,
                    )
                )
        unique = {item.relation_id: item for item in output}
        return [unique[key] for key in sorted(unique)]

    @staticmethod
    def _candidate_pairs(
        rule: RelationRule,
        structure_relations: list[Relation],
        annotations_by_element: dict[str, list[DomainAnnotation]],
        reading_index: dict[str, int],
    ) -> Iterable[tuple[str, str, str, list[str]]]:
        source_ids = {
            element_id
            for element_id, annotations in annotations_by_element.items()
            if any(item.domain_type in rule.source_domain_types for item in annotations)
        }
        target_ids = {
            element_id
            for element_id, annotations in annotations_by_element.items()
            if any(item.domain_type in rule.target_domain_types for item in annotations)
        }
        yielded: set[tuple[str, str]] = set()
        for relation in structure_relations:
            if rule.base_relation_types and relation.type not in rule.base_relation_types:
                continue
            if relation.source_id in source_ids and relation.target_id in target_ids:
                yielded.add((relation.source_id, relation.target_id))
                yield (
                    relation.source_id,
                    relation.target_id,
                    relation.type,
                    relation.evidence_ids,
                )
        for source_id in sorted(source_ids, key=lambda item: reading_index.get(item, 10**9)):
            source_index = reading_index.get(source_id)
            if source_index is None:
                continue
            nearest = [
                target_id
                for target_id in target_ids
                if target_id != source_id
                and target_id in reading_index
                and 0 <= reading_index[target_id] - source_index <= rule.max_reading_distance
                and (source_id, target_id) not in yielded
            ]
            if nearest:
                target_id = min(nearest, key=lambda item: reading_index[item] - source_index)
                yield source_id, target_id, "associated_with", []

    @staticmethod
    def _validate(
        pack: LoadedDomainPack,
        annotations: list[DomainAnnotation],
        relations: list[DomainRelationAnnotation],
    ) -> list[DomainValidationFinding]:
        findings: list[DomainValidationFinding] = []
        counts: dict[str, int] = defaultdict(int)
        types_by_element: dict[str, set[str]] = defaultdict(set)
        for annotation in annotations:
            counts[annotation.domain_type] += 1
            types_by_element[annotation.element_id].add(annotation.domain_type)
        for constraint in pack.validators.required_types:
            count = sum(counts[item] for item in constraint.domain_types)
            if count < constraint.min_count:
                findings.append(
                    DomainValidationFinding(
                        code=constraint.code,
                        severity=constraint.severity,
                        message=constraint.message,
                    )
                )
        for constraint in pack.validators.relation_endpoints:
            for relation in relations:
                if relation.domain_type != constraint.relation_type:
                    continue
                source_types = types_by_element[relation.source_id]
                target_types = types_by_element[relation.target_id]
                if constraint.source_types and not source_types.intersection(
                    constraint.source_types
                ):
                    findings.append(
                        DomainValidationFinding(
                            code=constraint.code,
                            severity=constraint.severity,
                            message=constraint.message,
                            element_ids=[relation.source_id, relation.target_id],
                            relation_ids=[relation.relation_id],
                        )
                    )
                elif constraint.target_types and not target_types.intersection(
                    constraint.target_types
                ):
                    findings.append(
                        DomainValidationFinding(
                            code=constraint.code,
                            severity=constraint.severity,
                            message=constraint.message,
                            element_ids=[relation.source_id, relation.target_id],
                            relation_ids=[relation.relation_id],
                        )
                    )
        return findings
