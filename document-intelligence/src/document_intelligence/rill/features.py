from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

from document_intelligence.domain_runtime import DomainRuntimeService
from document_intelligence.matching import MatchResult
from document_intelligence.rill.models import (
    ACTION_ARMS,
    RILL_FEATURE_ORDER,
    DomainSignals,
    MatchSignals,
    ParseSignals,
    RillObserveEvent,
    ShadowSignals,
    StructureSignals,
    stable_rill_id,
)
from document_intelligence.schema import ParserResult
from document_intelligence.services.store import ArtifactStore
from document_intelligence.structure import StructureService


class ShadowFeatureBuilder:
    def __init__(
        self,
        artifact_store: ArtifactStore,
        structure_service: StructureService,
        domain_service: DomainRuntimeService,
        *,
        feature_schema_path: Path,
    ) -> None:
        self.artifact_store = artifact_store
        self.structure_service = structure_service
        self.domain_service = domain_service
        self.feature_schema_path = feature_schema_path
        self.feature_schema = self._load_feature_schema(feature_schema_path)
        self._validate_feature_schema(self.feature_schema)
        self.feature_schema_hash = hashlib.sha256(
            json.dumps(
                self.feature_schema,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()

    @staticmethod
    def _load_feature_schema(path: Path) -> dict[str, Any]:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("Rill feature schema must be a JSON object")
        return data

    @staticmethod
    def _validate_feature_schema(schema: dict[str, Any]) -> None:
        if schema.get("schemaVersion") != "1.0":
            raise ValueError("unsupported Rill feature schema version")
        if schema.get("valueType") != "float64":
            raise ValueError("Rill feature schema must declare float64 values")
        if schema.get("missingValuePolicy") != "explicit-zero-with-presence-flags":
            raise ValueError("unsupported Rill missing-value policy")
        if schema.get("featureOrder") != list(RILL_FEATURE_ORDER):
            raise ValueError("Rill feature schema order differs from the extractor")
        if schema.get("actionArms") != [action.value for action in ACTION_ARMS]:
            raise ValueError("Rill action arms differ from the host policy")
        if schema.get("shadowOnly") is not True:
            raise ValueError("Rill feature schema must remain Shadow-only")

    def build(
        self,
        parse_run_id: str,
        *,
        structure_id: str | None = None,
        domain_result_id: str | None = None,
        match_result: MatchResult | None = None,
    ) -> RillObserveEvent:
        parsed = self.artifact_store.read_result(parse_run_id)
        structure = self.structure_service.get(structure_id) if structure_id else None
        domain = self.domain_service.get(domain_result_id) if domain_result_id else None
        if structure is not None and structure.parse_run_id != parse_run_id:
            raise ValueError("structure does not belong to the supplied parse run")
        if domain is not None:
            if domain.parse_run_id != parse_run_id:
                raise ValueError("domain result does not belong to the supplied parse run")
            if structure is None or domain.structure_id != structure.structure_id:
                raise ValueError("domain result requires its matching structure result")

        confidences = [item.confidence.overall for item in parsed.document.elements]
        warning_counts = Counter(item.severity for item in parsed.run.warnings)
        usage = parsed.run.resource_usage
        parse_signals = ParseSignals(
            page_count=len(parsed.document.pages),
            element_count=len(parsed.document.elements),
            average_confidence=(sum(confidences) / len(confidences) if confidences else 0.0),
            minimum_confidence=(min(confidences) if confidences else 0.0),
            p0_warnings=warning_counts["P0"],
            p1_warnings=warning_counts["P1"],
            p2_warnings=warning_counts["P2"],
            empty_native_text=any(
                warning.code == "EMPTY_NATIVE_TEXT" for warning in parsed.run.warnings
            ),
            duration_ms=usage.duration_ms if usage else 0.0,
            estimated_cost_usd=usage.estimated_cost_usd if usage else 0.0,
        )
        matching_signals = None
        if match_result is not None:
            matching_signals = MatchSignals(
                decision=match_result.decision.value,
                top1_score=match_result.top1_score,
                margin=match_result.margin,
                candidate_count=len(match_result.candidates),
                safe_standard_reuse=match_result.safe_standard_ref is not None,
            )
        structure_signals = None
        if structure is not None:
            diagnostics = Counter(item.severity.value for item in structure.diagnostics)
            structure_signals = StructureSignals(
                reading_order_coverage=structure.metrics.reading_order_coverage,
                relation_evidence_coverage=structure.metrics.relation_evidence_coverage,
                consistency_score=structure.metrics.consistency_score,
                diagnostics_info=diagnostics["info"],
                diagnostics_warning=diagnostics["warning"],
                diagnostics_error=diagnostics["error"],
                cross_page_relations=structure.metrics.cross_page_relations,
            )
        domain_signals = None
        if domain is not None:
            domain_signals = DomainSignals(
                status=domain.status.value,
                annotations=domain.metrics.annotations,
                relations=domain.metrics.domain_relations,
                validation_findings=domain.metrics.validation_findings,
                error_findings=domain.metrics.error_findings,
                evidence_coverage=domain.metrics.annotation_evidence_coverage,
                fallback_used=domain.metrics.fallback_used,
            )
        identity = parsed.document.identity
        document_family = identity.family if identity is not None else None
        semantic_parts = [
            parsed.run.semantic_output_digest or parsed.document.semantic_digest(),
            structure.semantic_digest() if structure is not None else "none",
            domain.semantic_digest() if domain is not None else "none",
            (
                hashlib.sha256(
                    json.dumps(
                        match_result.model_dump(mode="json"),
                        sort_keys=True,
                        separators=(",", ":"),
                    ).encode("utf-8")
                ).hexdigest()
                if match_result is not None
                else "none"
            ),
            self.feature_schema_hash,
        ]
        event_id = stable_rill_id("observe", *semantic_parts)
        return RillObserveEvent(
            event_id=event_id,
            parse_run_id=parse_run_id,
            parser_id=parsed.run.parser_id,
            document_family=document_family,
            structure_id=structure_id,
            domain_result_id=domain_result_id,
            signals=ShadowSignals(
                parse=parse_signals,
                matching=matching_signals,
                structure=structure_signals,
                domain=domain_signals,
            ),
        )
