from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping, Any

from .catalog import VisualSemanticCatalog
from .dialogue import (
    BBox,
    BubbleCandidate,
    CharacterCandidate,
    DialogueRelationResolver,
)


def _get(value: Any, name: str, default: Any = None) -> Any:
    if isinstance(value, Mapping):
        return value.get(name, default)
    return getattr(value, name, default)


def _bbox(value: Any) -> BBox:
    raw = _get(value, "bbox")
    if raw is None:
        raise ValueError("visual/text candidate lacks bbox")
    return BBox(
        float(_get(raw, "x1")),
        float(_get(raw, "y1")),
        float(_get(raw, "x2")),
        float(_get(raw, "y2")),
    )


@dataclass(slots=True)
class EducationVisualSemanticBridge:
    """Phase-13-compatible adapter for education-domain semantics.

    The bridge deliberately accepts mappings or objects by attribute so it can
    sit after VisualAssetObservation/Entry without changing the frozen core
    schema. It returns domain annotations/relations only.
    """

    catalog: VisualSemanticCatalog
    resolver: DialogueRelationResolver

    def identify_character(
        self,
        observation: Any,
        image_bytes: bytes,
    ) -> dict[str, object]:
        match = self.catalog.match(image_bytes)
        base = {
            "source_element_id": str(_get(observation, "source_element_id", _get(observation, "element_id", ""))),
            "source_page_id": str(_get(observation, "source_page_id", _get(observation, "page_id", ""))),
            "bbox": {
                "x1": _bbox(observation).x1,
                "y1": _bbox(observation).y1,
                "x2": _bbox(observation).x2,
                "y2": _bbox(observation).y2,
            },
            "match_status": match.status,
            "match_method": match.method,
            "confidence": match.confidence,
            "evidence": match.evidence,
        }
        if match.status != "matched" or match.semantic_id is None:
            return {**base, "domain_type": "unresolved-compact-visual"}
        profile = self.catalog.profile(match.semantic_id)
        if profile.category != "character":
            return {
                **base,
                "domain_type": profile.category,
                "semantic_id": profile.semantic_id,
                "special_meaning": profile.special_meaning,
            }
        return {
            **base,
            "domain_type": "textbook-character",
            "semantic_id": profile.semantic_id,
            "role_name": profile.role_name,
            "speaker_type": profile.speaker_type,
            "special_meaning": profile.special_meaning,
            "inference_status": "reviewed-visual-semantic-evidence",
        }

    def build_dialogue_relations(
        self,
        character_annotations: Iterable[Mapping[str, object]],
        bubbles: Iterable[Any],
    ) -> dict[str, object]:
        chars: list[CharacterCandidate] = []
        for ann in character_annotations:
            if ann.get("domain_type") != "textbook-character":
                continue
            bbox_raw = ann["bbox"]
            chars.append(
                CharacterCandidate(
                    element_id=str(ann["source_element_id"]),
                    page_id=str(ann["source_page_id"]),
                    bbox=BBox(
                        float(bbox_raw["x1"]), float(bbox_raw["y1"]),
                        float(bbox_raw["x2"]), float(bbox_raw["y2"]),
                    ),
                    semantic_id=str(ann["semantic_id"]),
                    role_name=str(ann["role_name"]),
                    speaker_type=str(ann["speaker_type"]),
                    visual_confidence=float(ann["confidence"]),
                    evidence_ids=tuple(str(x) for x in ann.get("evidence_ids", [])) or (
                        f"ev_visual_{ann['source_element_id']}",
                    ),
                )
            )
        bubble_candidates: list[BubbleCandidate] = []
        for bubble in bubbles:
            tail = _get(bubble, "tail_point", None)
            bubble_candidates.append(
                BubbleCandidate(
                    element_id=str(_get(bubble, "element_id")),
                    page_id=str(_get(bubble, "page_id")),
                    bbox=_bbox(bubble),
                    text=str(_get(bubble, "text", "")),
                    evidence_ids=tuple(str(x) for x in _get(bubble, "evidence_ids", ())) or (
                        f"ev_bubble_{_get(bubble, 'element_id')}",
                    ),
                    tail_point=(float(tail[0]), float(tail[1])) if tail else None,
                )
            )
        relations, unresolved = self.resolver.resolve(chars, bubble_candidates)
        return {
            "relations": [self.resolver.relation_to_mapping(r) for r in relations],
            "unresolved_bubbles": unresolved,
        }
