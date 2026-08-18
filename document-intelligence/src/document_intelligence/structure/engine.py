from __future__ import annotations

import hashlib
import math
import re
import statistics
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Sequence

from pydantic import BaseModel, ConfigDict, Field

from document_intelligence.parser_sdk.utils import digest_mapping, stable_id
from document_intelligence.schema import (
    BaseType,
    BoundingBox,
    Element,
    Evidence,
    EvidenceKind,
    ParsedDocument,
    Relation,
)
from document_intelligence.structure.models import (
    ContentGroup,
    DiagnosticSeverity,
    GroupKind,
    OutlineNode,
    StructureDiagnostic,
    StructureMetrics,
    StructureResult,
)

_TERMINAL_PUNCTUATION = frozenset(".!?。！？;；:：")
_CONTINUATION_PUNCTUATION = frozenset(",，、-—–")
_CAPTION_PREFIX = re.compile(
    r"^(?:figure|fig\.?|table|formula|equation|图|表|公式|式)\s*[\d一二三四五六七八九十]*",
    re.IGNORECASE,
)
_DIGIT_ONLY = re.compile(r"^[\s\-–—]*\d+[\s\-–—]*$")

# OutlineNode.title 的硬上限（见 structure/models.py）。防御性截断，防止解析器误判出的
# 超长 HEADING 触发 Pydantic 校验失败（HTTP 500）。截断位置取整字符边界，避免产生孤立代理对。
_MAX_TITLE_LENGTH = 2000


def _title_from_element(element: Element) -> str:
    """从标题元素提取安全的 title：去空白 + 截断到 OutlineNode.title 上限。"""
    title = (element.content.text or "").strip()
    if len(title) > _MAX_TITLE_LENGTH:
        return title[:_MAX_TITLE_LENGTH]
    return title


class StructureConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    max_columns: int = Field(default=4, ge=1, le=8)
    spanning_width: float = Field(default=0.70, ge=0.40, le=1.0)
    column_gap: float = Field(default=0.18, ge=0.05, le=0.50)
    repeated_margin_ratio: float = Field(default=0.60, ge=0.40, le=1.0)
    top_margin: float = Field(default=0.12, ge=0.0, le=0.30)
    bottom_margin: float = Field(default=0.88, ge=0.70, le=1.0)
    text_group_gap: float = Field(default=0.035, ge=0.005, le=0.15)
    caption_threshold: float = Field(default=0.70, ge=0.50, le=1.0)
    cross_page_threshold: float = Field(default=0.70, ge=0.50, le=1.0)


class StructureRecoveryEngine:
    engine_version = "0.3.0"

    def __init__(self, config: StructureConfig | None = None) -> None:
        self.config = config or StructureConfig()
        implementation = Path(__file__).read_bytes()
        model_implementation = Path(__file__).with_name("models.py").read_bytes()
        self.engine_digest = hashlib.sha256(
            implementation
            + b"\0"
            + model_implementation
            + b"\0"
            + self.engine_version.encode("utf-8")
        ).hexdigest()
        self.config_digest = digest_mapping(self.config.model_dump(mode="json"))

    def recover(self, document: ParsedDocument) -> StructureResult:
        generated_at = datetime.now(timezone.utc)
        element_by_id = {item.element_id: item for item in document.elements}
        page_by_id = {item.page_id: item for item in document.pages}
        elements_by_page: dict[str, list[Element]] = defaultdict(list)
        for element in document.elements:
            elements_by_page[element.page_id].append(element)

        excluded = self._detect_repeated_margins(document, elements_by_page)
        reading_order: list[str] = []
        content_order: list[str] = []
        for page in sorted(document.pages, key=lambda item: item.index):
            page_order = self._order_page(elements_by_page.get(page.page_id, []))
            reading_order.extend(item.element_id for item in page_order)
            content_order.extend(
                item.element_id for item in page_order if item.element_id not in excluded
            )

        if set(reading_order) != set(element_by_id):
            missing = sorted(set(element_by_id) - set(reading_order))
            foreign = sorted(set(reading_order) - set(element_by_id))
            raise ValueError(
                "structure reading order does not cover source elements: "
                f"missing={missing}, foreign={foreign}"
            )

        evidence: list[Evidence] = []
        groups: list[ContentGroup] = []
        relations: list[Relation] = []

        margin_groups, margin_evidence = self._margin_groups(
            document,
            excluded,
            element_by_id,
            generated_at,
        )
        groups.extend(margin_groups)
        evidence.extend(margin_evidence)

        text_groups, text_evidence = self._text_groups(
            document,
            content_order,
            element_by_id,
            generated_at,
        )
        groups.extend(text_groups)
        evidence.extend(text_evidence)

        caption_groups, caption_relations, caption_evidence = self._caption_associations(
            document,
            content_order,
            element_by_id,
            generated_at,
        )
        groups.extend(caption_groups)
        relations.extend(caption_relations)
        evidence.extend(caption_evidence)

        cross_relations, cross_evidence = self._cross_page_relations(
            document,
            content_order,
            element_by_id,
            page_by_id,
            generated_at,
        )
        relations.extend(cross_relations)
        evidence.extend(cross_evidence)

        outline, outline_evidence = self._build_outline(
            document,
            content_order,
            element_by_id,
            page_by_id,
            generated_at,
        )
        evidence.extend(outline_evidence)

        diagnostics = self._diagnostics(document, outline, relations)
        relation_evidence_coverage = self._relation_evidence_coverage(relations)
        coverage = len(reading_order) / len(document.elements) if document.elements else 1.0
        consistency_score = statistics.fmean(
            [coverage, relation_evidence_coverage, 1.0]
        )
        cross_page_count = sum(item.type == "continues_on" for item in relations)
        structure_id = stable_id(
            "structure",
            document.document_id,
            document.semantic_digest(),
            self.engine_digest,
            self.config_digest,
        )
        metrics = StructureMetrics(
            total_elements=len(document.elements),
            ordered_elements=len(reading_order),
            content_elements=len(content_order),
            excluded_margin_elements=len(excluded),
            heading_elements=sum(
                element_by_id[item].base_type == BaseType.HEADING
                for item in content_order
            ),
            outline_nodes=len(outline),
            groups=len(groups),
            relations=len(relations),
            cross_page_relations=cross_page_count,
            reading_order_coverage=coverage,
            relation_evidence_coverage=relation_evidence_coverage,
            consistency_score=consistency_score,
        )
        return StructureResult(
            structure_id=structure_id,
            engine_version=self.engine_version,
            engine_digest=self.engine_digest,
            config_digest=self.config_digest,
            document_id=document.document_id,
            parse_run_id=document.parse_run_id,
            source_semantic_digest=document.semantic_digest(),
            reading_order=reading_order,
            content_reading_order=content_order,
            excluded_margin_element_ids=sorted(excluded),
            outline=outline,
            groups=groups,
            relations=relations,
            evidence=evidence,
            diagnostics=diagnostics,
            metrics=metrics,
            generated_at=generated_at,
        )

    def _order_page(self, elements: Sequence[Element]) -> list[Element]:
        if len(elements) < 2:
            return list(elements)
        anchors = sorted(
            (
                item
                for item in elements
                if self._width(item) >= self.config.spanning_width
            ),
            key=self._geometric_key,
        )
        nonanchors = [item for item in elements if item not in anchors]
        result: list[Element] = []
        lower = 0.0
        for anchor in anchors:
            anchor_center = self._center_y(anchor)
            segment = [
                item
                for item in nonanchors
                if lower <= self._center_y(item) < anchor_center
            ]
            result.extend(self._order_segment(segment))
            result.append(anchor)
            lower = max(lower, anchor_center)
        tail = [item for item in nonanchors if self._center_y(item) >= lower]
        result.extend(self._order_segment(tail))
        if len(result) != len(elements) or len({item.element_id for item in result}) != len(result):
            return sorted(elements, key=self._geometric_key)
        return result

    def _order_segment(self, elements: Sequence[Element]) -> list[Element]:
        if len(elements) < 2:
            return list(elements)
        if len(elements) < 4:
            sparse = self._sparse_column_order(elements)
            return sparse or sorted(elements, key=self._geometric_key)
        centers = sorted(
            (self._center_x(item), item.element_id, item) for item in elements
        )
        split_points: list[int] = []
        gaps = [centers[index + 1][0] - centers[index][0] for index in range(len(centers) - 1)]
        ranked = sorted(range(len(gaps)), key=lambda index: gaps[index], reverse=True)
        for index in ranked:
            if gaps[index] < self.config.column_gap:
                break
            candidate = index + 1
            boundaries = sorted([*split_points, candidate])
            sizes = self._partition_sizes(len(centers), boundaries)
            if min(sizes) >= 2 and len(boundaries) + 1 <= self.config.max_columns:
                split_points.append(candidate)
        if not split_points:
            return sorted(elements, key=self._geometric_key)
        ordered: list[Element] = []
        starts = [0, *sorted(split_points)]
        ends = [*sorted(split_points), len(centers)]
        for start, end in zip(starts, ends, strict=True):
            column = [item for _, _, item in centers[start:end]]
            ordered.extend(sorted(column, key=self._geometric_key))
        return ordered

    def _sparse_column_order(
        self, elements: Sequence[Element]
    ) -> list[Element] | None:
        centers = sorted(
            (self._center_x(item), item.element_id, item) for item in elements
        )
        gaps = [
            centers[index + 1][0] - centers[index][0]
            for index in range(len(centers) - 1)
        ]
        if not gaps:
            return None
        split_index = max(range(len(gaps)), key=gaps.__getitem__)
        if gaps[split_index] < max(0.25, self.config.column_gap):
            return None
        left = [item for _, _, item in centers[: split_index + 1]]
        right = [item for _, _, item in centers[split_index + 1 :]]
        side_by_side = any(
            self._vertical_overlap_ratio(left_item, right_item) >= 0.30
            for left_item in left
            for right_item in right
        )
        if not side_by_side:
            return None
        return [
            *sorted(left, key=self._geometric_key),
            *sorted(right, key=self._geometric_key),
        ]

    @staticmethod
    def _partition_sizes(total: int, boundaries: Sequence[int]) -> list[int]:
        points = [0, *sorted(boundaries), total]
        return [points[index + 1] - points[index] for index in range(len(points) - 1)]

    def _detect_repeated_margins(
        self,
        document: ParsedDocument,
        elements_by_page: dict[str, list[Element]],
    ) -> set[str]:
        page_count = len(document.pages)
        occurrences: dict[tuple[str, str], set[str]] = defaultdict(set)
        members: dict[tuple[str, str], list[str]] = defaultdict(list)
        excluded: set[str] = set()
        for page in document.pages:
            for element in elements_by_page.get(page.page_id, []):
                text = (element.content.text or "").strip()
                region: str | None = None
                if element.base_type == BaseType.PAGE_NUMBER:
                    excluded.add(element.element_id)
                    region = "bottom"
                elif element.bbox.y1 <= self.config.top_margin:
                    region = "top"
                elif element.bbox.y2 >= self.config.bottom_margin:
                    region = "bottom"
                if region is None or not text:
                    continue
                if region == "bottom" and _DIGIT_ONLY.fullmatch(text):
                    excluded.add(element.element_id)
                normalized = self._normalize_margin_text(text)
                if not normalized:
                    continue
                key = (region, normalized)
                occurrences[key].add(page.page_id)
                members[key].append(element.element_id)
        if page_count < 2:
            return excluded
        required = max(2, math.ceil(page_count * self.config.repeated_margin_ratio))
        for key, pages in occurrences.items():
            if len(pages) >= required:
                excluded.update(members[key])
        return excluded

    def _margin_groups(
        self,
        document: ParsedDocument,
        excluded: set[str],
        element_by_id: dict[str, Element],
        generated_at: datetime,
    ) -> tuple[list[ContentGroup], list[Evidence]]:
        buckets: dict[tuple[str, str], list[Element]] = defaultdict(list)
        for element_id in sorted(excluded):
            element = element_by_id[element_id]
            text = (element.content.text or "").strip()
            region = "top" if element.bbox.y1 <= self.config.top_margin else "bottom"
            key = (region, self._normalize_margin_text(text) or element.element_id)
            buckets[key].append(element)
        groups: list[ContentGroup] = []
        evidence: list[Evidence] = []
        for key, items in sorted(buckets.items()):
            evidence_ids = [
                self._append_evidence(
                    evidence,
                    document,
                    item,
                    "repeated-margin",
                    generated_at,
                )
                for item in items
            ]
            group_id = stable_id(
                "group",
                document.document_id,
                GroupKind.REPEATED_MARGIN.value,
                key,
                [item.element_id for item in items],
            )
            groups.append(
                ContentGroup(
                    group_id=group_id,
                    kind=GroupKind.REPEATED_MARGIN,
                    element_ids=[item.element_id for item in items],
                    page_ids=sorted({item.page_id for item in items}),
                    confidence=0.98 if len(items) > 1 else 0.90,
                    evidence_ids=evidence_ids,
                )
            )
        return groups, evidence

    def _text_groups(
        self,
        document: ParsedDocument,
        content_order: Sequence[str],
        element_by_id: dict[str, Element],
        generated_at: datetime,
    ) -> tuple[list[ContentGroup], list[Evidence]]:
        groups: list[ContentGroup] = []
        evidence: list[Evidence] = []
        current: list[Element] = []

        def flush() -> None:
            if len(current) < 2:
                current.clear()
                return
            evidence_id = self._append_group_evidence(
                evidence,
                document,
                current,
                "text-cluster",
                generated_at,
            )
            group_id = stable_id(
                "group",
                document.document_id,
                GroupKind.TEXT_CLUSTER.value,
                [item.element_id for item in current],
            )
            groups.append(
                ContentGroup(
                    group_id=group_id,
                    kind=GroupKind.TEXT_CLUSTER,
                    element_ids=[item.element_id for item in current],
                    page_ids=[current[0].page_id],
                    confidence=0.82,
                    evidence_ids=[evidence_id],
                )
            )
            current.clear()

        for element_id in content_order:
            element = element_by_id[element_id]
            if element.base_type not in {
                BaseType.TEXT,
                BaseType.LIST,
                BaseType.CALLOUT,
                BaseType.FOOTNOTE,
            }:
                flush()
                continue
            if not current:
                current.append(element)
                continue
            previous = current[-1]
            gap = element.bbox.y1 - previous.bbox.y2
            aligned = abs(element.bbox.x1 - previous.bbox.x1) <= 0.12
            same_page = element.page_id == previous.page_id
            if same_page and aligned and -0.01 <= gap <= self.config.text_group_gap:
                current.append(element)
            else:
                flush()
                current.append(element)
        flush()
        return groups, evidence

    def _caption_associations(
        self,
        document: ParsedDocument,
        content_order: Sequence[str],
        element_by_id: dict[str, Element],
        generated_at: datetime,
    ) -> tuple[list[ContentGroup], list[Relation], list[Evidence]]:
        groups: list[ContentGroup] = []
        relations: list[Relation] = []
        evidence: list[Evidence] = []
        order_index = {element_id: index for index, element_id in enumerate(content_order)}
        visual_types = {BaseType.IMAGE, BaseType.FIGURE, BaseType.TABLE, BaseType.FORMULA}
        text_types = {BaseType.TEXT, BaseType.CALLOUT, BaseType.FOOTNOTE}
        text_elements = [
            item for item in element_by_id.values() if item.base_type in text_types
        ]
        used_captions: set[str] = set()
        for visual in element_by_id.values():
            if visual.base_type not in visual_types or visual.element_id not in order_index:
                continue
            candidates: list[tuple[float, Element]] = []
            for text in text_elements:
                if text.page_id != visual.page_id or text.element_id in used_captions:
                    continue
                score = self._caption_score(visual, text)
                if score >= self.config.caption_threshold:
                    candidates.append((score, text))
            if not candidates:
                continue
            score, caption = max(
                candidates,
                key=lambda item: (item[0], -abs(order_index.get(item[1].element_id, 0))),
            )
            used_captions.add(caption.element_id)
            caption_evidence = self._append_evidence(
                evidence,
                document,
                caption,
                "caption-text",
                generated_at,
            )
            visual_evidence = self._append_evidence(
                evidence,
                document,
                visual,
                "caption-target",
                generated_at,
            )
            relation_id = stable_id(
                "relation",
                document.document_id,
                "caption_of",
                caption.element_id,
                visual.element_id,
            )
            relations.append(
                Relation(
                    relation_id=relation_id,
                    source_id=caption.element_id,
                    target_id=visual.element_id,
                    type="caption_of",
                    confidence=score,
                    evidence_ids=[caption_evidence, visual_evidence],
                )
            )
            group_kind = (
                GroupKind.TABLE_WITH_CAPTION
                if visual.base_type == BaseType.TABLE
                else GroupKind.VISUAL_WITH_CAPTION
            )
            group_id = stable_id(
                "group",
                document.document_id,
                group_kind.value,
                caption.element_id,
                visual.element_id,
            )
            groups.append(
                ContentGroup(
                    group_id=group_id,
                    kind=group_kind,
                    element_ids=[visual.element_id, caption.element_id],
                    page_ids=[visual.page_id],
                    confidence=score,
                    evidence_ids=[caption_evidence, visual_evidence],
                )
            )
        return groups, relations, evidence

    def _cross_page_relations(
        self,
        document: ParsedDocument,
        content_order: Sequence[str],
        element_by_id: dict[str, Element],
        page_by_id: dict[str, object],
        generated_at: datetime,
    ) -> tuple[list[Relation], list[Evidence]]:
        del page_by_id
        order_index = {element_id: index for index, element_id in enumerate(content_order)}
        per_page: dict[str, list[Element]] = defaultdict(list)
        for element_id in content_order:
            per_page[element_by_id[element_id].page_id].append(element_by_id[element_id])
        relations: list[Relation] = []
        evidence: list[Evidence] = []
        ordered_pages = sorted(document.pages, key=lambda item: item.index)
        for left_page, right_page in zip(ordered_pages, ordered_pages[1:]):
            left = self._boundary_candidate(per_page.get(left_page.page_id, []), last=True)
            right = self._boundary_candidate(per_page.get(right_page.page_id, []), last=False)
            if left is None or right is None:
                continue
            score = self._continuation_score(left, right)
            if score < self.config.cross_page_threshold:
                continue
            if order_index[left.element_id] >= order_index[right.element_id]:
                continue
            left_evidence = self._append_evidence(
                evidence,
                document,
                left,
                "cross-page-source",
                generated_at,
            )
            right_evidence = self._append_evidence(
                evidence,
                document,
                right,
                "cross-page-target",
                generated_at,
            )
            relation_id = stable_id(
                "relation",
                document.document_id,
                "continues_on",
                left.element_id,
                right.element_id,
            )
            relations.append(
                Relation(
                    relation_id=relation_id,
                    source_id=left.element_id,
                    target_id=right.element_id,
                    type="continues_on",
                    confidence=score,
                    evidence_ids=[left_evidence, right_evidence],
                )
            )
        return relations, evidence

    def _build_outline(
        self,
        document: ParsedDocument,
        content_order: Sequence[str],
        element_by_id: dict[str, Element],
        page_by_id: dict[str, object],
        generated_at: datetime,
    ) -> tuple[list[OutlineNode], list[Evidence]]:
        del page_by_id
        headings = [
            element_by_id[element_id]
            for element_id in content_order
            if element_by_id[element_id].base_type == BaseType.HEADING
            and (element_by_id[element_id].content.text or "").strip()
        ]
        if not headings:
            return [], []
        levels = self._heading_levels(headings)
        content_positions = {element_id: index for index, element_id in enumerate(content_order)}
        evidence: list[Evidence] = []
        nodes: list[OutlineNode] = []
        stack: list[tuple[int, str]] = []
        for index, heading in enumerate(headings):
            level = levels[heading.element_id]
            while stack and stack[-1][0] >= level:
                stack.pop()
            parent_id = stack[-1][1] if stack else None
            start = content_positions[heading.element_id] + 1
            end = len(content_order)
            for later in headings[index + 1 :]:
                if levels[later.element_id] <= level:
                    end = content_positions[later.element_id]
                    break
            node_id = stable_id(
                "outline",
                document.document_id,
                heading.element_id,
                level,
            )
            evidence_id = self._append_evidence(
                evidence,
                document,
                heading,
                "heading-hierarchy",
                generated_at,
            )
            page_index = next(
                page.index for page in document.pages if page.page_id == heading.page_id
            )
            nodes.append(
                OutlineNode(
                    node_id=node_id,
                    heading_element_id=heading.element_id,
                    level=level,
                    parent_node_id=parent_id,
                    page_index=page_index,
                    title=_title_from_element(heading),
                    content_element_ids=list(content_order[start:end]),
                    confidence=max(0.65, min(0.95, heading.confidence.overall * 0.90)),
                    evidence_ids=[evidence_id],
                )
            )
            stack.append((level, node_id))
        return nodes, evidence

    def _heading_levels(self, headings: Sequence[Element]) -> dict[str, int]:
        heights = sorted((self._height(item), item.element_id) for item in headings)
        cluster_centers: list[float] = []
        assignments: dict[str, int] = {}
        for height, element_id in sorted(heights, reverse=True):
            assigned: int | None = None
            for index, center in enumerate(cluster_centers):
                tolerance = max(0.004, center * 0.20)
                if abs(height - center) <= tolerance:
                    assigned = index + 1
                    cluster_centers[index] = (center + height) / 2.0
                    break
            if assigned is None:
                cluster_centers.append(height)
                assigned = len(cluster_centers)
            assignments[element_id] = min(assigned, 6)
        previous = 1
        for heading in headings:
            level = assignments[heading.element_id]
            if level > previous + 1:
                level = previous + 1
                assignments[heading.element_id] = level
            previous = level
        return assignments

    def _diagnostics(
        self,
        document: ParsedDocument,
        outline: Sequence[OutlineNode],
        relations: Sequence[Relation],
    ) -> list[StructureDiagnostic]:
        diagnostics: list[StructureDiagnostic] = []
        if document.elements and not outline:
            diagnostics.append(
                StructureDiagnostic(
                    code="NO_HEADING_CANDIDATES",
                    severity=DiagnosticSeverity.INFO,
                    message="No generic heading candidates were present in the parsed document.",
                )
            )
        if len(document.pages) > 1 and not any(
            relation.type == "continues_on" for relation in relations
        ):
            diagnostics.append(
                StructureDiagnostic(
                    code="NO_CROSS_PAGE_CONTINUATION",
                    severity=DiagnosticSeverity.INFO,
                    message=(
                        "No cross-page continuation met the conservative evidence threshold."
                    ),
                )
            )
        return diagnostics

    def _caption_score(self, visual: Element, text: Element) -> float:
        text_value = (text.content.text or "").strip()
        if not text_value or len(text_value) > 300:
            return 0.0
        below_gap = text.bbox.y1 - visual.bbox.y2
        above_gap = visual.bbox.y1 - text.bbox.y2
        if 0.0 <= below_gap <= 0.08:
            distance = below_gap
            position_score = 1.0
        elif 0.0 <= above_gap <= 0.05:
            distance = above_gap
            position_score = 0.72
        else:
            return 0.0
        proximity = max(0.0, 1.0 - distance / 0.08)
        overlap = self._horizontal_overlap_ratio(visual, text)
        prefix = 1.0 if _CAPTION_PREFIX.match(text_value) else 0.0
        brevity = 1.0 if len(text_value) <= 160 else 0.55
        if prefix == 0.0:
            center_delta = abs(self._center_x(visual) - self._center_x(text))
            tight_gap = distance <= 0.035
            compact = self._width(text) <= self._width(visual) * 0.85
            if not (tight_gap and compact and center_delta <= 0.08 and brevity == 1.0):
                return 0.0
        score = (
            0.30 * proximity
            + 0.25 * overlap
            + 0.25 * prefix
            + 0.10 * position_score
            + 0.10 * brevity
        )
        return min(1.0, score)

    def _boundary_candidate(
        self,
        elements: Sequence[Element],
        *,
        last: bool,
    ) -> Element | None:
        allowed = {BaseType.TEXT, BaseType.LIST, BaseType.TABLE}
        candidates = [item for item in elements if item.base_type in allowed]
        if not candidates:
            return None
        return candidates[-1] if last else candidates[0]

    def _continuation_score(self, left: Element, right: Element) -> float:
        if left.base_type == BaseType.TABLE and right.base_type == BaseType.TABLE:
            if left.bbox.y2 >= 0.72 and right.bbox.y1 <= 0.28:
                return 0.86
            return 0.0
        if left.base_type not in {BaseType.TEXT, BaseType.LIST}:
            return 0.0
        if right.base_type not in {BaseType.TEXT, BaseType.LIST}:
            return 0.0
        left_text = (left.content.text or "").strip()
        right_text = (right.content.text or "").strip()
        if not left_text or not right_text:
            return 0.0
        if left.bbox.y2 < 0.72 or right.bbox.y1 > 0.28:
            return 0.0
        terminal = left_text[-1] in _TERMINAL_PUNCTUATION
        continuation_mark = left_text[-1] in _CONTINUATION_PUNCTUATION
        overlap = self._horizontal_overlap_ratio(left, right)
        alignment = max(0.0, 1.0 - abs(left.bbox.x1 - right.bbox.x1) / 0.25)
        lexical = 1.0 if not terminal else 0.0
        if continuation_mark:
            lexical = 1.0
        score = 0.35 * lexical + 0.30 * overlap + 0.20 * alignment + 0.15
        return min(1.0, score)

    def _append_evidence(
        self,
        evidence: list[Evidence],
        document: ParsedDocument,
        element: Element,
        role: str,
        generated_at: datetime,
    ) -> str:
        evidence_id = stable_id(
            "structure-evidence",
            document.document_id,
            role,
            element.element_id,
            self.engine_digest,
            self.config_digest,
        )
        evidence.append(
            Evidence(
                evidence_id=evidence_id,
                kind=EvidenceKind.RULE_INFERENCE,
                producer="structure-recovery",
                producer_version=self.engine_version,
                model_digest=self.engine_digest,
                parse_run_id=document.parse_run_id,
                source_page_id=element.page_id,
                bbox=element.bbox,
                created_at=generated_at,
            )
        )
        return evidence_id

    def _append_group_evidence(
        self,
        evidence: list[Evidence],
        document: ParsedDocument,
        elements: Sequence[Element],
        role: str,
        generated_at: datetime,
    ) -> str:
        page_id = elements[0].page_id
        if any(item.page_id != page_id for item in elements):
            raise ValueError("group evidence cannot span pages")
        bbox = self._union_bbox(item.bbox for item in elements)
        evidence_id = stable_id(
            "structure-evidence",
            document.document_id,
            role,
            [item.element_id for item in elements],
            self.engine_digest,
            self.config_digest,
        )
        evidence.append(
            Evidence(
                evidence_id=evidence_id,
                kind=EvidenceKind.RULE_INFERENCE,
                producer="structure-recovery",
                producer_version=self.engine_version,
                model_digest=self.engine_digest,
                parse_run_id=document.parse_run_id,
                source_page_id=page_id,
                bbox=bbox,
                created_at=generated_at,
            )
        )
        return evidence_id

    @staticmethod
    def _relation_evidence_coverage(relations: Sequence[Relation]) -> float:
        if not relations:
            return 1.0
        covered = sum(bool(item.evidence_ids) for item in relations)
        return covered / len(relations)

    @staticmethod
    def _normalize_margin_text(text: str) -> str:
        normalized = re.sub(r"\d+", "#", text.casefold())
        normalized = re.sub(r"\s+", " ", normalized).strip(" -–—|·")
        return normalized

    @staticmethod
    def _horizontal_overlap_ratio(left: Element, right: Element) -> float:
        overlap = max(0.0, min(left.bbox.x2, right.bbox.x2) - max(left.bbox.x1, right.bbox.x1))
        minimum = min(
            max(left.bbox.x2 - left.bbox.x1, 1e-9),
            max(right.bbox.x2 - right.bbox.x1, 1e-9),
        )
        return min(1.0, overlap / minimum)

    @staticmethod
    def _vertical_overlap_ratio(left: Element, right: Element) -> float:
        overlap = max(
            0.0,
            min(left.bbox.y2, right.bbox.y2)
            - max(left.bbox.y1, right.bbox.y1),
        )
        minimum = min(
            max(left.bbox.y2 - left.bbox.y1, 1e-9),
            max(right.bbox.y2 - right.bbox.y1, 1e-9),
        )
        return min(1.0, overlap / minimum)

    @staticmethod
    def _union_bbox(boxes: Iterable[BoundingBox]) -> BoundingBox:
        materialized = list(boxes)
        if not materialized:
            raise ValueError("cannot union an empty bbox collection")
        return BoundingBox(
            x1=min(item.x1 for item in materialized),
            y1=min(item.y1 for item in materialized),
            x2=max(item.x2 for item in materialized),
            y2=max(item.y2 for item in materialized),
        )

    @staticmethod
    def _geometric_key(element: Element) -> tuple[float, float, float, str]:
        return (element.bbox.y1, element.bbox.x1, element.bbox.y2, element.element_id)

    @staticmethod
    def _width(element: Element) -> float:
        return element.bbox.x2 - element.bbox.x1

    @staticmethod
    def _height(element: Element) -> float:
        return element.bbox.y2 - element.bbox.y1

    @staticmethod
    def _center_x(element: Element) -> float:
        return (element.bbox.x1 + element.bbox.x2) / 2.0

    @staticmethod
    def _center_y(element: Element) -> float:
        return (element.bbox.y1 + element.bbox.y2) / 2.0
