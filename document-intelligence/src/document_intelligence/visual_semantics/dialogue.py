from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import math
from typing import Iterable


@dataclass(frozen=True, slots=True)
class BBox:
    x1: float
    y1: float
    x2: float
    y2: float

    def __post_init__(self) -> None:
        if not (0 <= self.x1 < self.x2 <= 1 and 0 <= self.y1 < self.y2 <= 1):
            raise ValueError("bbox must be normalised and non-empty")

    @property
    def center(self) -> tuple[float, float]:
        return ((self.x1 + self.x2) / 2, (self.y1 + self.y2) / 2)

    @property
    def area(self) -> float:
        return (self.x2 - self.x1) * (self.y2 - self.y1)

    def distance_to_point(self, point: tuple[float, float]) -> float:
        x, y = point
        dx = max(self.x1 - x, 0.0, x - self.x2)
        dy = max(self.y1 - y, 0.0, y - self.y2)
        return math.hypot(dx, dy)

    def edge_distance(self, other: "BBox") -> float:
        dx = max(self.x1 - other.x2, other.x1 - self.x2, 0.0)
        dy = max(self.y1 - other.y2, other.y1 - self.y2, 0.0)
        return math.hypot(dx, dy)


@dataclass(frozen=True, slots=True)
class CharacterCandidate:
    element_id: str
    page_id: str
    bbox: BBox
    semantic_id: str
    role_name: str
    speaker_type: str
    visual_confidence: float
    evidence_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class BubbleCandidate:
    element_id: str
    page_id: str
    bbox: BBox
    text: str
    evidence_ids: tuple[str, ...]
    tail_point: tuple[float, float] | None = None


@dataclass(frozen=True, slots=True)
class DialogueRelation:
    relation_id: str
    source_id: str
    target_id: str
    type: str
    domain_type: str
    confidence: float
    evidence_ids: tuple[str, ...]
    evidence: dict[str, object]
    review_status: str = "unreviewed"


def classify_utterance_function(text: str, speaker_type: str) -> tuple[str, float, str]:
    clean = "".join(text.split())
    if not clean:
        return ("unknown", 0.0, "empty-text")
    question_mark = "？" in clean or "?" in clean
    question_words = ("为什么", "怎样", "怎么", "多少", "能不能", "是不是", "哪", "什么")
    discovery_words = ("我发现", "发现", "看出", "可以看出", "原来")
    conjecture_words = ("我猜", "可能", "也许", "我想")
    prompt_words = ("想一想", "试一试", "说一说", "你能", "你会", "怎样", "为什么", "看看")
    explain_words = ("因为", "所以", "也就是", "要注意", "可以这样", "先", "再")

    if speaker_type == "student":
        if question_mark or any(w in clean for w in question_words):
            return ("student_question", 0.92, "student-question-cue")
        if any(w in clean for w in discovery_words):
            return ("student_observation_or_discovery", 0.88, "student-discovery-cue")
        if any(w in clean for w in conjecture_words):
            return ("student_conjecture", 0.82, "student-conjecture-cue")
        return ("student_statement", 0.60, "role-only-fallback")

    if speaker_type == "teacher":
        if question_mark or any(w in clean for w in prompt_words):
            return ("teacher_prompt", 0.90, "teacher-prompt-cue")
        if any(w in clean for w in explain_words):
            return ("teacher_guidance_or_explanation", 0.76, "teacher-guidance-cue")
        return ("teacher_statement", 0.58, "role-only-fallback")

    return ("unknown", 0.25, "unknown-speaker-type")


class DialogueRelationResolver:
    """Geometry-first character -> speech-bubble relation resolver.

    It rejects ambiguous ownership instead of forcing a nearest-neighbour link.
    This preserves the project's rule that no deterministic relation is allowed
    without spatial evidence.
    """

    def __init__(
        self,
        *,
        max_edge_distance: float = 0.24,
        min_score: float = 0.62,
        ambiguity_margin: float = 0.10,
    ) -> None:
        self.max_edge_distance = max_edge_distance
        self.min_score = min_score
        self.ambiguity_margin = ambiguity_margin

    @staticmethod
    def _relation_id(character_id: str, bubble_id: str) -> str:
        digest = sha256(f"{character_id}|speaks|{bubble_id}".encode()).hexdigest()[:20]
        return f"rel_dialogue_{digest}"

    def _score(self, character: CharacterCandidate, bubble: BubbleCandidate) -> tuple[float, dict[str, object]]:
        if character.page_id != bubble.page_id:
            return (0.0, {"reason": "different-page"})
        edge = character.bbox.edge_distance(bubble.bbox)
        if edge > self.max_edge_distance:
            return (0.0, {"reason": "too-far", "edge_distance": edge})

        # A tail point, when supplied by a detector, is stronger than generic
        # proximity. Without it, geometry remains conservative.
        tail_distance = None
        if bubble.tail_point is not None:
            tail_distance = character.bbox.distance_to_point(bubble.tail_point)
            tail_component = max(0.0, 1.0 - tail_distance / max(0.001, self.max_edge_distance))
            proximity_component = max(0.0, 1.0 - edge / self.max_edge_distance)
            geometry = 0.72 * tail_component + 0.28 * proximity_component
        else:
            geometry = max(0.0, 1.0 - edge / self.max_edge_distance) * 0.82

        visual = min(max(character.visual_confidence, 0.0), 1.0)
        score = 0.82 * geometry + 0.18 * visual
        return (
            score,
            {
                "edge_distance": round(edge, 6),
                "tail_distance": round(tail_distance, 6) if tail_distance is not None else None,
                "geometry_score": round(geometry, 6),
                "visual_confidence": round(visual, 6),
            },
        )

    def resolve(
        self,
        characters: Iterable[CharacterCandidate],
        bubbles: Iterable[BubbleCandidate],
    ) -> tuple[list[DialogueRelation], list[dict[str, object]]]:
        chars = list(characters)
        relations: list[DialogueRelation] = []
        unresolved: list[dict[str, object]] = []
        for bubble in bubbles:
            scored: list[tuple[float, CharacterCandidate, dict[str, object]]] = []
            for char in chars:
                score, evidence = self._score(char, bubble)
                if score > 0:
                    scored.append((score, char, evidence))
            scored.sort(key=lambda row: (-row[0], row[1].element_id))
            if not scored or scored[0][0] < self.min_score:
                unresolved.append({
                    "bubble_id": bubble.element_id,
                    "reason": "no-safe-character-owner",
                    "best_score": round(scored[0][0], 6) if scored else 0.0,
                })
                continue
            if len(scored) > 1 and scored[0][0] - scored[1][0] < self.ambiguity_margin:
                unresolved.append({
                    "bubble_id": bubble.element_id,
                    "reason": "ambiguous-character-owner",
                    "candidates": [
                        [row[1].element_id, round(row[0], 6)] for row in scored[:3]
                    ],
                })
                continue
            score, char, geometry_evidence = scored[0]
            function, function_conf, function_reason = classify_utterance_function(
                bubble.text, char.speaker_type
            )
            evidence_ids = tuple(dict.fromkeys((*char.evidence_ids, *bubble.evidence_ids)))
            relation_evidence = {
                "speaker_role": char.role_name,
                "speaker_type": char.speaker_type,
                "geometry": geometry_evidence,
                "utterance_function": function,
                "utterance_function_confidence": function_conf,
                "utterance_function_reason": function_reason,
                "inference_status": "derived-not-textbook-fact",
            }
            relations.append(
                DialogueRelation(
                    relation_id=self._relation_id(char.element_id, bubble.element_id),
                    source_id=char.element_id,
                    target_id=bubble.element_id,
                    type="associated_with",
                    domain_type="speaks",
                    confidence=round(score, 6),
                    evidence_ids=evidence_ids,
                    evidence=relation_evidence,
                )
            )
        return relations, unresolved

    @staticmethod
    def relation_to_mapping(relation: DialogueRelation) -> dict[str, object]:
        return {
            "relation_id": relation.relation_id,
            "source_id": relation.source_id,
            "target_id": relation.target_id,
            "type": relation.type,
            "domain_type": relation.domain_type,
            "confidence": relation.confidence,
            "evidence_ids": list(relation.evidence_ids),
            "review_status": relation.review_status,
            "domain_evidence": relation.evidence,
        }
