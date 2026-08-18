from __future__ import annotations

import hashlib
import importlib.metadata
import json
import math
import statistics
import sys
import time
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Any

try:
    import resource
except ImportError:  # pragma: no cover - Windows
    resource = None  # type: ignore[assignment]

from pypdf import PdfReader

from document_intelligence.exceptions import CorruptInputError, UnsupportedInputError
from document_intelligence.parser_sdk.utils import digest_mapping, normalize_bbox, stable_id
from document_intelligence.schema import (
    BaseType,
    BoundingBox,
    Confidence,
    Element,
    ElementContent,
    Evidence,
    EvidenceKind,
    Page,
    ParsedDocument,
    ParserHealth,
    ParserResult,
    ParseRequest,
    ParseRun,
    ParseWarning,
    PixelBoundingBox,
    ResourceUsage,
    RunStatus,
    SourceDescriptor,
)


# 标题候选的最大文本长度。真实教材/文档标题通常很短（如"例1""试一试""第二章"）。
# 排版异常页可能把整段正文误合并成超长文本行，若其字号又偏大就会被误判为 HEADING，
# 导致 OutlineNode.title 超出 2000 字符上限而崩溃。此常量用于过滤这类伪标题。
_MAX_HEADING_TEXT_LENGTH = 80


def _clamp_bbox(
    bbox: tuple[float, float, float, float], width: float, height: float
) -> tuple[float, float, float, float]:
    """把页面坐标 bbox 夹紧到 [0, width] x [0, height]，保证坐标非负且不越界。

    个别 PDF 页面的图像放置矩形会略微越出页面（例如 x0=-1.18），直接传入
    PixelBoundingBox 会触发 pydantic 非负校验失败并导致整页解析崩溃。
    """
    x1, y1, x2, y2 = bbox
    x1 = max(0.0, min(float(x1), width))
    y1 = max(0.0, min(float(y1), height))
    x2 = max(0.0, min(float(x2), width))
    y2 = max(0.0, min(float(y2), height))
    if x2 < x1:
        x1, x2 = x2, x1
    if y2 < y1:
        y1, y2 = y2, y1
    return (x1, y1, x2, y2)



class NativePdfParser:
    """Permissively licensed native-PDF text and image extractor.

    This parser intentionally does not render PDF pages. Pixel rendering remains an optional,
    separately qualified capability so the base distribution does not depend on PyMuPDF.
    """
    parser_id = "native-pdf"
    capabilities = ["application/pdf", "native-text", "images", "coordinates", "reading-order"]
    priority = 10

    def __init__(
        self,
        *,
        max_pages: int = 2000,
        max_page_elements: int = 20000,
        max_binary_artifact_bytes: int = 200 * 1024 * 1024,
    ) -> None:
        self.version = importlib.metadata.version("pypdf")
        implementation = Path(__file__).read_bytes()
        self.digest = hashlib.sha256(
            implementation + b"\0" + self.version.encode("utf-8")
        ).hexdigest()
        self.max_pages = max_pages
        self.max_page_elements = max_page_elements
        self.max_binary_artifact_bytes = max_binary_artifact_bytes
        self.config_digest = digest_mapping(
            {
                "text_visitor": True,
                "image_xobjects": True,
                "coordinate_estimation": "v1",
                "v": 3,
                "max_pages": max_pages,
                "max_page_elements": max_page_elements,
                "max_binary_artifact_bytes": max_binary_artifact_bytes,
            }
        )

    def health(self) -> ParserHealth:
        return ParserHealth(
            parser_id=self.parser_id,
            available=True,
            enabled=True,
            version=self.version,
            artifact_digest=self.digest,
            capabilities=self.capabilities,
        )

    def supports(self, request: ParseRequest) -> bool:
        return request.mime_type == "application/pdf"

    def parse(self, request: ParseRequest) -> ParserResult:
        if not self.supports(request):
            raise UnsupportedInputError("NativePdfParser only supports PDF input")
        started = datetime.now(timezone.utc)
        started_perf = time.perf_counter()
        request_context_digest = request.context_digest()
        run_id = stable_id(
            "run",
            request.sha256,
            request_context_digest,
            self.parser_id,
            self.version,
            self.digest,
            self.config_digest,
        )
        try:
            reader = PdfReader(BytesIO(request.content), strict=True)
        except Exception as exc:
            raise CorruptInputError("unable to open PDF") from exc
        if reader.is_encrypted:
            raise CorruptInputError("encrypted PDF requires a password and is not accepted")
        if not reader.pages:
            raise CorruptInputError("PDF contains no pages")
        if len(reader.pages) > self.max_pages:
            raise CorruptInputError(
                f"PDF page count exceeds limit: {len(reader.pages)} > {self.max_pages}"
            )

        pages: list[Page] = []
        elements: list[Element] = []
        evidence: list[Evidence] = []
        warnings: list[ParseWarning] = []
        raw_pages: list[dict[str, Any]] = []
        binary_artifacts: dict[str, bytes] = {}
        binary_artifact_bytes = 0

        # 图像定位（图标/角色）依赖 PyMuPDF；可选，失败时图像退回全页 bbox。
        fitz_doc = self._load_fitz_document(request.content)

        # 支持 page_range（绝对页码，含端点），仅解析指定页并重编号为 0..N-1，
        # 与 OCR 网关行为保持一致，避免每次都解析整册（扫描件会非常慢）。
        total_pages = len(reader.pages)
        selected: list[int] = list(range(total_pages))
        pr = request.options.get("page_range")
        if isinstance(pr, str) and "-" in pr:
            try:
                a, b = (int(x) for x in pr.split("-", 1))
                start = max(0, min(a, total_pages - 1))
                end = max(start, min(b, total_pages - 1))
                selected = list(range(start, end + 1))
            except Exception:
                selected = list(range(total_pages))

        for page_index, abs_page_index in enumerate(selected):
            pdf_page = reader.pages[abs_page_index]
            width = float(pdf_page.mediabox.width)
            height = float(pdf_page.mediabox.height)
            if width <= 0 or height <= 0:
                raise CorruptInputError(f"page {abs_page_index} has invalid dimensions")
            page_id = stable_id("page", request.sha256, abs_page_index)
            text_items = self._extract_text_items(pdf_page, width, height)
            try:
                fitz_page = fitz_doc[abs_page_index] if fitz_doc is not None else None
            except Exception:
                fitz_page = None
            images = self._extract_images(pdf_page, width, height, fitz_page)
            if len(text_items) + len(images) > self.max_page_elements:
                raise CorruptInputError(
                    f"page {page_index} element count exceeds limit: "
                    f"{len(text_items) + len(images)} > {self.max_page_elements}"
                )
            font_sizes = [item[2] for item in text_items if item[2] > 0]
            median_font = statistics.median(font_sizes) if font_sizes else 0.0
            page_element_ids: list[str] = []
            reading_order = 0
            raw_items: list[dict[str, Any]] = []

            for item_index, (text, raw_bbox, font_size) in enumerate(text_items):
                normalized = normalize_bbox(raw_bbox, width, height)
                bbox = BoundingBox(
                    x1=normalized[0], y1=normalized[1], x2=normalized[2], y2=normalized[3]
                )
                pixel_bbox = PixelBoundingBox(
                    x1=raw_bbox[0], y1=raw_bbox[1], x2=raw_bbox[2], y2=raw_bbox[3]
                )
                # 标题候选需同时满足：字号显著大于中位数，且文本足够短。
                # 某些排版异常页会把整段正文误合并成一条超长文本（可达数万字符），
                # 其字号又恰好偏大；若不限制长度，会被误判为 HEADING，
                # 进而因 OutlineNode.title 的 2000 字符上限触发 Pydantic 校验崩溃（HTTP 500）。
                is_heading = bool(
                    median_font
                    and font_size >= median_font * 1.25
                    and len(text) <= _MAX_HEADING_TEXT_LENGTH
                )
                base_type = BaseType.HEADING if is_heading else BaseType.TEXT
                subtype = "native_heading_candidate" if is_heading else "native_text_fragment"
                element_id = stable_id(
                    "el", request.sha256, page_index, item_index, base_type.value, text, raw_bbox
                )
                evidence_id = stable_id("ev", run_id, element_id)
                evidence.append(
                    Evidence(
                        evidence_id=evidence_id,
                        kind=EvidenceKind.NATIVE_EXTRACTION,
                        producer=self.parser_id,
                        producer_version=self.version,
                        model_digest=self.digest,
                        parse_run_id=run_id,
                        source_page_id=page_id,
                        bbox=bbox,
                        created_at=started,
                    )
                )
                elements.append(
                    Element(
                        element_id=element_id,
                        page_id=page_id,
                        base_type=base_type,
                        subtype=subtype,
                        bbox=bbox,
                        pixel_bbox=pixel_bbox,
                        content=ElementContent(text=text),
                        confidence=Confidence(overall=0.99, detection=0.99, recognition=0.99),
                        evidence_ids=[evidence_id],
                        reading_order=reading_order,
                    )
                )
                page_element_ids.append(element_id)
                reading_order += 1
                raw_items.append(
                    {"kind": "text", "text": text, "bbox": list(raw_bbox), "font_size": font_size}
                )

            for image_index, (name, image_bytes, extension, raw_bbox) in enumerate(images):
                digest = hashlib.sha256(image_bytes).hexdigest()
                if digest not in binary_artifacts:
                    binary_artifact_bytes += len(image_bytes)
                    if binary_artifact_bytes > self.max_binary_artifact_bytes:
                        raise CorruptInputError(
                            "embedded image artifacts exceed limit: "
                            f"{binary_artifact_bytes} > {self.max_binary_artifact_bytes} bytes"
                        )
                    binary_artifacts[digest] = image_bytes
                _bbox = raw_bbox  # (x0, y0, x1, y1) 页面坐标，y 向下
                normalized = normalize_bbox(_bbox, width, height)
                bbox = BoundingBox(
                    x1=normalized[0], y1=normalized[1], x2=normalized[2], y2=normalized[3]
                )
                pixel_bbox = PixelBoundingBox(
                    x1=_bbox[0], y1=_bbox[1], x2=_bbox[2], y2=_bbox[3]
                )
                element_id = stable_id(
                    "el", request.sha256, page_index, "image", image_index, name, digest
                )
                evidence_id = stable_id("ev", run_id, element_id)
                evidence.append(
                    Evidence(
                        evidence_id=evidence_id,
                        kind=EvidenceKind.NATIVE_EXTRACTION,
                        producer=self.parser_id,
                        producer_version=self.version,
                        model_digest=self.digest,
                        parse_run_id=run_id,
                        source_page_id=page_id,
                        bbox=bbox,
                        created_at=started,
                    )
                )
                elements.append(
                    Element(
                        element_id=element_id,
                        page_id=page_id,
                        base_type=BaseType.IMAGE,
                        subtype=extension or "embedded_image",
                        bbox=bbox,
                        pixel_bbox=pixel_bbox,
                        content=ElementContent(asset_ref=f"sha256:{digest}"),
                        confidence=Confidence(overall=0.95, detection=0.95),
                        evidence_ids=[evidence_id],
                        reading_order=reading_order,
                    )
                )
                page_element_ids.append(element_id)
                reading_order += 1
                raw_items.append(
                    {
                        "kind": "image",
                        "name": name,
                        "image_sha256": digest,
                        "image_bytes": len(image_bytes),
                    }
                )

            if not text_items:
                warnings.append(
                    ParseWarning(
                        code="EMPTY_NATIVE_TEXT",
                        message="No native text found; OCR-capable parser may be required.",
                        page_id=page_id,
                    )
                )
            pages.append(
                Page(
                    page_id=page_id,
                    index=page_index,
                    width=width,
                    height=height,
                    rotation=int(pdf_page.get("/Rotate", 0) or 0),
                    element_ids=page_element_ids,
                )
            )
            raw_pages.append(
                {
                    "page_index": page_index,
                    "width": width,
                    "height": height,
                    "items": raw_items,
                }
            )

        source = SourceDescriptor(
            filename=request.filename,
            sha256=request.sha256,
            mime_type="application/pdf",
            size_bytes=len(request.content),
        )
        document_id = stable_id("doc", request.sha256)
        document = ParsedDocument(
            document_id=document_id,
            source=source,
            pages=pages,
            elements=elements,
            evidence=evidence,
            domain_pack=request.domain_pack,
            parse_run_id=run_id,
        )
        duration_ms = (time.perf_counter() - started_perf) * 1000.0
        run = ParseRun(
            parse_run_id=run_id,
            input_sha256=request.sha256,
            parser_id=self.parser_id,
            parser_version=self.version,
            parser_digest=self.digest,
            config_digest=self.config_digest,
            request_context_digest=request_context_digest,
            domain_pack=request.domain_pack,
            status=RunStatus.SUCCEEDED,
            started_at=started,
            finished_at=datetime.now(timezone.utc),
            semantic_output_digest=document.semantic_digest(),
            resource_usage=ResourceUsage(
                duration_ms=duration_ms,
                max_rss_kb=self._max_rss_kb(),
                input_bytes=len(request.content),
                output_elements=len(elements),
            ),
            warnings=warnings,
        )
        return ParserResult(
            document=document,
            run=run,
            raw_output={"parser": self.parser_id, "pages": raw_pages},
            binary_artifacts=binary_artifacts,
        )

    @staticmethod
    def _estimate_text_width(value: str, size: float) -> float:
        """按字符类别估算文本串宽度（em 单位）。

        CJK/全角字符约 1em，ASCII 数字/字母约 0.55em，括号/空格约 0.3–0.5em。
        相比统一按 0.55em 估算，能显著降低同行碎片宽度误判，从而可靠区分
        「同一文本行内的连续碎片」与「同视觉行的不同栏」。
        """
        width = 0.0
        for char in value:
            code = ord(char)
            if char == " ":
                width += 0.30 * size
            elif char in "()（）：;；,，":
                width += 0.35 * size
            elif (
                0x2E80 <= code <= 0x9FFF
                or 0xFF00 <= code <= 0xFFEF
                or 0x3000 <= code <= 0x303F
            ):
                width += 1.0 * size
            else:
                width += 0.55 * size
        return max(width, size * 0.5)

    @staticmethod
    def _extract_text_items(
        page: Any, width: float, height: float
    ) -> list[tuple[str, tuple[float, float, float, float], float]]:
        """逐个文本矩阵提取碎片，并按视觉行合并为完整文本行。

        原生 PDF 的文本内容常被拆成过小的碎片（"我买"、"2"、"筒"……），导致句子不连贯。
        这里用文本矩阵 tm 计算真实字号（而非回退的 1.0），再把同一基线（视觉行）上的
        碎片按 x 顺序拼接成一行，行 bbox 取所有碎片并集，从而输出连贯、可定位的文本元素。

        同一基线可能同时包含多个栏（如例题的左右两栏算式），因此按水平间隔把基线组
        再细分为独立的文本行，避免跨栏拼接。
        """
        raw: list[tuple[float, float, float, float, float, float, float, str]] = []

        def visitor(
            text: str,
            _cm: list[float],
            tm: list[float],
            _font: Any,
            font_size: float,
        ) -> None:
            value = text.strip()
            if not value:
                return
            # 用文本矩阵计算真实字号（tm[0], tm[1] 为缩放），避免 pypdf 回传的 font_size 失真
            size = math.hypot(tm[0], tm[1]) or max(float(font_size or 0.0), 1.0)
            x = min(max(float(tm[4]), 0.0), width)
            baseline = min(max(float(tm[5]), 0.0), height)
            y1 = min(max(height - baseline - size, 0.0), height)
            estimated_width = min(width - x, NativePdfParser._estimate_text_width(value, size))
            x2 = min(width, x + max(estimated_width, 1.0))
            y2 = min(height, y1 + max(size * 1.25, 1.0))
            if x2 <= x or y2 <= y1:
                return
            raw.append((x, baseline, size, y1, x2, y2, len(value), value))

        try:
            page.extract_text(visitor_text=visitor)
        except Exception as exc:
            raise CorruptInputError("failed to extract native PDF text") from exc
        if not raw:
            return []

        # 第一步：按基线（视觉行）分组，同一行内 baseline 差异 <= 3pt。
        raw.sort(key=lambda item: (item[1], item[0]))
        baseline_groups: list[list[tuple[float, float, float, float, float, float, float, str]]] = []
        for item in raw:
            if baseline_groups and abs(item[1] - baseline_groups[-1][0][1]) <= 3.0:
                baseline_groups[-1].append(item)
            else:
                baseline_groups.append([item])

        # 第二步：同一基线组内按水平间隔细分为独立文本行（区分不同栏）。
        # 水平间隔 = 当前碎片起始 x - 当前行已合并碎片的右边界（最大 x2）。
        # 注意：必须用「当前行所有碎片中最大的 x2」而非「最后一个碎片的 x2」，
        # 否则窄碎片（如数字"3"）会覆盖行右边界，导致其后本应接续的碎片被误判为新栏。
        lines: list[list[tuple[float, float, float, float, float, float, float, str]]] = []
        for group in baseline_groups:
            group.sort(key=lambda item: item[0])
            current: list[tuple[float, float, float, float, float, float, float, str]] = []
            running_x2 = -1.0  # 当前行已合并碎片的最大右边界 x2
            running_size = 0.0
            for item in group:
                if current:
                    gap = item[0] - running_x2
                    threshold = 1.8 * running_size
                    if gap >= threshold:
                        lines.append(current)
                        current = []
                        running_x2 = -1.0
                        running_size = 0.0
                current.append(item)
                running_x2 = max(running_x2, item[4])
                running_size = max(running_size, item[2])
            if current:
                lines.append(current)

        items: list[tuple[str, tuple[float, float, float, float], float]] = []
        for line in lines:
            line.sort(key=lambda item: item[0])
            text = "".join(item[7] for item in line)
            # 原始碎片元组为 (x, baseline, size, y1, x2, y2, len, value)：
            # 索引 0=x, 3=y1, 4=x2, 5=y2。行 bbox 取所有碎片坐标的并集。
            x1 = min(item[0] for item in line)
            x2 = max(item[4] for item in line)
            y1 = min(item[3] for item in line)
            y2 = max(item[5] for item in line)
            size = max(item[2] for item in line)
            items.append((text, (x1, y1, x2, y2), size))

        items.sort(key=lambda item: (round(item[1][1], 3), round(item[1][0], 3), item[0]))
        return items

    @staticmethod
    def _extract_images(
        page: Any,
        width: float,
        height: float,
        fitz_page: Any | None = None,
    ) -> list[tuple[str, bytes, str, tuple[float, float, float, float]]]:
        """提取页面内嵌图像及其在页面上的真实位置。

        图像元素若无真实坐标（历史实现退化为全页 bbox），会：(1) 使图标/角色无法定位与识别；
        (2) 在结构排序时被排到页面最前，严重扰乱阅读顺序。

        这里优先用 PyMuPDF 的 get_image_rects 按 xref 定位每个图像的实际放置矩形；
        若 PyMuPDF 不可用（native 解析器默认不强制依赖），则退回全页 bbox。
        返回 (name, data, extension, raw_bbox)，其中 raw_bbox=(x0,y0,x1,y1) 为页面坐标（y 向下）。
        """
        images: list[tuple[str, bytes, str, tuple[float, float, float, float]]] = []
        try:
            for image in page.images:
                data = bytes(image.data)
                if not data:
                    continue
                name = str(getattr(image, "name", "embedded-image"))[:127]
                extension = name.rsplit(".", 1)[-1].lower() if "." in name else "embedded_image"
                raw_bbox = (0.0, 0.0, width, height)
                indirect = getattr(image, "indirect_reference", None)
                xref = getattr(indirect, "idnum", None)
                if fitz_page is not None and xref is not None:
                    try:
                        rects = fitz_page.get_image_rects(xref)
                    except Exception:
                        rects = []
                    if rects:
                        r = rects[0]
                        raw_bbox = (float(r.x0), float(r.y0), float(r.x1), float(r.y1))
                elif fitz_page is not None:
                    # 个别图像无 xref，尝试按名称从 fitz 图像列表匹配
                    try:
                        for img in fitz_page.get_images(full=True):
                            if str(img[7]) == name:
                                rects = fitz_page.get_image_rects(img[0])
                                if rects:
                                    r = rects[0]
                                    raw_bbox = (float(r.x0), float(r.y0), float(r.x1), float(r.y1))
                                break
                    except Exception:
                        pass
                # 边界防护：个别 PDF 图像放置矩形可能越出页面（负坐标或超界），
                # 会触发 PixelBoundingBox 非负校验失败导致整页解析崩溃。统一 clamp 到页面范围。
                raw_bbox = _clamp_bbox(raw_bbox, width, height)
                images.append((name, data, extension, raw_bbox))
        except Exception as exc:
            raise CorruptInputError("failed to extract embedded PDF images") from exc
        return images

    @staticmethod
    def _load_fitz_document(content: bytes) -> Any | None:
        """按需加载 PyMuPDF 用于图像定位（可选依赖，失败时返回 None 不影响解析）。"""
        try:
            import fitz  # type: ignore[import-not-found]

            return fitz.open(stream=content, filetype="pdf")
        except Exception:
            return None

    @staticmethod
    def _max_rss_kb() -> int | None:
        if resource is None:
            return None
        usage = resource.getrusage(resource.RUSAGE_SELF)
        if usage.ru_maxrss < 0:
            return None
        value = int(usage.ru_maxrss)
        return value // 1024 if sys.platform == "darwin" else value
