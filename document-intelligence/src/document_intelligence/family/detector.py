from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path

from document_intelligence.domain_pack_sdk import DocumentFamilyProfile, FamilyCue, LoadedDomainPack
from document_intelligence.family.models import (
    FamilyCandidate,
    FamilyCueMatch,
    FamilyDecision,
    FamilyDetectionResult,
)
from document_intelligence.parser_sdk.utils import stable_id
from document_intelligence.schema import Element, ParsedDocument
from document_intelligence.structure import StructureResult

def family_profile_digest(profile: DocumentFamilyProfile) -> str:
    return hashlib.sha256(
        json.dumps(
            profile.model_dump(mode="json", exclude_none=False),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


class DocumentFamilyDetector:
    detector_version = "1.0.0"

    def __init__(self) -> None:
        implementation = Path(__file__).read_bytes()
        models = Path(__file__).with_name("models.py").read_bytes()
        sdk = Path(__file__).parents[1] / "domain_pack_sdk" / "models.py"
        self.detector_digest = hashlib.sha256(
            implementation
            + b"\0"
            + models
            + b"\0"
            + sdk.read_bytes()
            + b"\0"
            + self.detector_version.encode()
        ).hexdigest()

    def detect(
        self,
        document: ParsedDocument,
        structure: StructureResult,
        packs: list[LoadedDomainPack],
    ) -> FamilyDetectionResult:
        if document.document_id != structure.document_id:
            raise ValueError("family detector document and structure identities differ")
        if document.parse_run_id != structure.parse_run_id:
            raise ValueError("family detector parse and structure identities differ")
        element_by_id = {element.element_id: element for element in document.elements}
        ordered_elements = [
            element_by_id[element_id]
            for element_id in structure.content_reading_order
            if element_id in element_by_id
        ]
        candidates = [
            self._score_pack(document, ordered_elements, pack)
            for pack in packs
            if pack.family is not None
        ]
        candidates.sort(
            key=lambda item: (-int(item.eligible), -item.score, item.priority, item.family_id)
        )
        eligible = [item for item in candidates if item.eligible]
        decision = FamilyDecision.NO_MATCH
        selected_family_id = None
        selected_pack_id = None
        selected_pack_version = None
        observed_margin: float | None = None
        if eligible:
            top = eligible[0]
            runner_up = eligible[1] if len(eligible) > 1 else None
            observed_margin = top.score - runner_up.score if runner_up else 1.0
            profile = next(
                (
                    pack.family
                    for pack in packs
                    if pack.manifest.id == top.pack_id
                    and pack.manifest.version == top.pack_version
                    and pack.family is not None
                ),
                None,
            )
            if profile is None:
                raise RuntimeError(
                    "selected document-family candidate has no available profile"
                )
            if runner_up is not None and observed_margin < profile.min_margin:
                decision = FamilyDecision.AMBIGUOUS
            else:
                decision = FamilyDecision.CANDIDATE
                selected_family_id = top.family_id
                selected_pack_id = top.pack_id
                selected_pack_version = top.pack_version
        result_id = stable_id(
            "family",
            document.document_id,
            document.semantic_digest(),
            structure.structure_id,
            structure.semantic_digest(),
            self.detector_digest,
            *(f"{item.pack_id}@{item.pack_version}:{item.pack_digest}" for item in candidates),
        )
        return FamilyDetectionResult(
            detection_id=result_id,
            detector_version=self.detector_version,
            detector_digest=self.detector_digest,
            document_id=document.document_id,
            parse_run_id=document.parse_run_id,
            source_document_digest=document.semantic_digest(),
            structure_id=structure.structure_id,
            source_structure_digest=structure.semantic_digest(),
            decision=decision,
            selected_family_id=selected_family_id,
            selected_pack_id=selected_pack_id,
            selected_pack_version=selected_pack_version,
            candidates=candidates,
            min_margin_observed=observed_margin,
        )

    def _score_pack(
        self,
        document: ParsedDocument,
        elements: list[Element],
        pack: LoadedDomainPack,
    ) -> FamilyCandidate:
        profile = pack.family
        if profile is None:
            raise ValueError("family scoring requires a family profile")
        exclusions: list[str] = []
        if profile.family_id != pack.manifest.id:
            exclusions.append("FAMILY_ID_PACK_ID_MISMATCH")
        if profile.supported_mime_types and document.source.mime_type not in set(
            profile.supported_mime_types
        ):
            exclusions.append("MIME_TYPE_UNSUPPORTED")
        base_counts = Counter(element.base_type for element in elements)
        missing_base_types = {
            base_type: required - base_counts.get(base_type, 0)
            for base_type, required in profile.required_base_types.items()
            if base_counts.get(base_type, 0) < required
        }
        if missing_base_types:
            exclusions.append("REQUIRED_BASE_TYPES_MISSING")
        positive_matches = self._matches(profile.positive_cues, elements)
        negative_matches = self._matches(profile.negative_cues, elements)
        matched_positive_ids = {item.cue_id for item in positive_matches}
        missing_required = [
            cue.id
            for cue in profile.positive_cues
            if cue.required and cue.id not in matched_positive_ids
        ]
        if missing_required:
            exclusions.append("REQUIRED_CUES_MISSING")
        if len(positive_matches) < profile.min_positive_cues:
            exclusions.append("POSITIVE_CUE_COUNT_BELOW_MINIMUM")
        positive_score = sum(item.weight for item in positive_matches)
        negative_score = sum(item.weight for item in negative_matches)
        total_positive = sum(cue.weight for cue in profile.positive_cues)
        score = max(0.0, min(1.0, (positive_score - negative_score) / total_positive))
        if score < profile.min_score:
            exclusions.append("SCORE_BELOW_MINIMUM")
        profile_digest = family_profile_digest(profile)
        return FamilyCandidate(
            family_id=profile.family_id,
            pack_id=pack.manifest.id,
            pack_version=pack.manifest.version,
            pack_digest=pack.content_digest,
            profile_digest=profile_digest,
            priority=profile.priority,
            eligible=not exclusions,
            score=score,
            positive_score=positive_score,
            negative_score=negative_score,
            positive_matches=positive_matches,
            negative_matches=negative_matches,
            missing_required_cues=missing_required,
            missing_base_types=missing_base_types,
            exclusion_reasons=exclusions,
        )

    @classmethod
    def _matches(cls, cues: list[FamilyCue], elements: list[Element]) -> list[FamilyCueMatch]:
        output: list[FamilyCueMatch] = []
        for cue in cues:
            matched = [element for element in elements if cls._cue_matches(cue, element)]
            if not matched:
                continue
            output.append(
                FamilyCueMatch(
                    cue_id=cue.id,
                    weight=cue.weight,
                    element_ids=[element.element_id for element in matched],
                    evidence_ids=list(
                        dict.fromkeys(
                            evidence_id
                            for element in matched
                            for evidence_id in element.evidence_ids
                        )
                    ),
                )
            )
        return output

    @staticmethod
    def _cue_matches(cue: FamilyCue, element: Element) -> bool:
        if cue.base_types and element.base_type not in cue.base_types:
            return False
        if cue.subtypes and element.subtype not in cue.subtypes:
            return False
        text = (element.content.text or "").strip()
        if not text:
            return False
        folded = text.casefold()
        terms = [term.casefold() for term in cue.terms]
        if cue.match_mode == "contains":
            return any(term in folded for term in terms)
        if cue.match_mode == "starts_with":
            return any(folded.startswith(term) for term in terms)
        return folded in terms
