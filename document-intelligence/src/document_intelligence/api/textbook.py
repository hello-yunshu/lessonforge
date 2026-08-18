"""
教材编排模块（独立板块，与核心 API 解耦）。

把「按章节解析 → 结构恢复 → 教育对象识别 → 人工标注 → 自学习迭代」编排成
对前端友好的高层端点。内部复用核心服务（orchestrator / structure / domain /
review / rill），并通过 app.state 注入，避免与 main.py 相互牵连，可单独更新。

端点：
- POST /v1/textbook/chapters/analyze   上传 PDF + page_range → 全面分析并落盘
- POST /v1/textbook/chapters/annotate  提交人工标注（正确/错误）→ 落盘 + 自学习回灌
- GET  /v1/textbook/chapters/list      列出已分析的章节
- GET  /v1/textbook/chapters/{id}      查询章节分析结果与迭代历史
"""
from __future__ import annotations

import json
import logging
import re
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Body, File, Form, HTTPException, Query, Request, Response, UploadFile
from fastapi import Path as PathParam
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, ConfigDict, Field

from document_intelligence.parser_sdk.utils import stable_id
from document_intelligence.review.models import (
    LabelUReviewSubmission,
    ReviewedObject,
    ReviewedRelation,
)
from document_intelligence.rill.models import (
    FeedbackSeverity,
    ShadowAction,
    ShadowFeedbackInput,
)
from document_intelligence.schema import SAFE_ID_PATTERN, validate_safe_id

def _section_titles_by_page(
    annotations: list[dict[str, Any]],
    elements_by_id: dict[str, object],
) -> dict[str, set[str]]:
    """汇总每页已识别的板块标题元素（试一试/想想做做/练习/动手做等，不含例题）。

    用于抑制例题数字误判：同一页若在候选数字之前已出现板块标题，
    则该数字极可能是栏目内容里的题号/算式，而非书本标志例题。
    """
    result: dict[str, set[str]] = {}
    for ann in annotations:
        if ann.get("domain_type") not in _BOARD_DOMAIN_TYPES:
            continue
        if ann.get("domain_type") == "example":
            continue
        element_id = ann.get("element_id")
        element = elements_by_id.get(element_id)
        if element is None:
            continue
        page_id = getattr(element, "page_id", "")
        result.setdefault(page_id, set()).add(element_id)
    return result


def _build_example_annotations(
    content_order: list[str],
    elements_by_id: dict[str, object],
    pages_by_id: dict[str, object],
    section_titles_by_page: dict[str, set[str]] | None = None,
) -> list[dict[str, Any]]:
    """为「书本标志 + 数字」检测出的例题生成可审核的标注条目。

    这些例题由几何特征识别（而非领域文本规则），因此补为领域标注，
    使前端注释列表与板块结构都能看到并支持人工订正。
    """
    annotations: list[dict[str, Any]] = []
    for element_id in _detect_example_titles(
        content_order, elements_by_id, section_titles_by_page
    ):
        element = elements_by_id.get(element_id)
        if element is None:
            continue
        number = _book_icon_number(_element_text(element)) or _element_text(element)
        page = pages_by_id.get(getattr(element, "page_id", ""))
        annotations.append(
            {
                "annotation_id": stable_id("dann", "book-icon-example", element_id),
                "confidence": 0.95,
                "content": number,
                "domain_type": "example",
                "element_id": element_id,
                "evidence_ids": list(getattr(element, "evidence_ids", []) or []),
                "page_index": getattr(page, "index", None) if page is not None else None,
                "properties": {"marker": "book-icon", "number": number},
                "review_status": "unreviewed",
                "rule_id": "education-example-book-icon",
            }
        )
    return annotations


def _annotation_view(
    a: dict[str, Any],
    elements_by_id: dict[str, object],
    pages_by_id: dict[str, object],
) -> dict[str, Any]:
    el = elements_by_id.get(a["element_id"])
    content: str | None = None
    page_index: int | None = None
    bbox: dict[str, float] | None = None
    if el is not None:
        content = _element_text(el)
        page = pages_by_id.get(getattr(el, "page_id", ""))
        if page is not None:
            page_index = page.index
        b = getattr(el, "bbox", None)
        if b is not None:
            x1 = getattr(b, "x1", None)
            y1 = getattr(b, "y1", None)
            x2 = getattr(b, "x2", None)
            y2 = getattr(b, "y2", None)
            if None not in (x1, y1, x2, y2):
                bbox = {"x1": x1, "y1": y1, "x2": x2, "y2": y2}
    return {**a, "content": content, "page_index": page_index, "bbox": bbox}


# 视觉语义锚点：语义对象 -> 板块类型。图标匹配命中这些语义时，转成对应的板块标题标注。
_SECTION_SEMANTIC_TO_DOMAIN_TYPE = {
    "example-book-icon": "example",
    "try": "try",
    "think-do": "think-do",
    "operation": "operation",
    "reflection": "thinking-question",
}


def _build_visual_semantic_annotations(
    document: object,
    visual_catalog_service: object,
    artifact_store: object,
    elements_by_id: dict[str, object],
    pages_by_id: dict[str, object],
) -> list[dict[str, Any]]:
    """「先识别图标/角色」：对解析出的每个图像元素调用视觉匹配器，产生例题/栏目/角色标注。

    图像元素通过 content.asset_ref（sha256:{digest}）从二进制工件库取回真实图像字节，
    交由 VisualCatalogService.catalog.match 做精确/感知匹配。命中的语义分为三类：
    - example-book-icon / try / think-do / operation / reflection → 板块标题锚点
    - character → 教材角色（学生/教师），供后续对话关系解析
    - 其余或未解析 → 不产生标注（fail-closed）
    """
    catalog = getattr(visual_catalog_service, "catalog", None)
    if catalog is None:
        return []
    annotations: list[dict[str, Any]] = []
    for element in getattr(document, "elements", []) or []:
        content = getattr(element, "content", None)
        asset_ref = getattr(content, "asset_ref", None)
        if not asset_ref or not str(asset_ref).startswith("sha256:"):
            continue
        try:
            asset_path = artifact_store.resolve_asset(str(asset_ref))
            image_bytes = asset_path.read_bytes()
        except Exception:
            continue
        try:
            result = catalog.match(image_bytes)
        except Exception:
            continue
        if result.status != "matched" or not result.semantic_id:
            continue
        domain_type = _semantic_to_domain_type(result.semantic_id)
        if domain_type is None:
            continue
        element_id = getattr(element, "element_id", "")
        page = pages_by_id.get(getattr(element, "page_id", ""))
        # 例题图标必须是页面左上角的板块标题锚点；位于页面其它位置的 example-book-icon
        # 是栏目内的书本形装饰/题目标记（如练习里的书本图标），不应被当作例题板块标题，
        # 否则会生成空标题的假例题板块（如第五单元 pg2 中下部图标）。
        if domain_type == "example":
            bbox = getattr(element, "bbox", None)
            if bbox is None:
                continue
            if getattr(bbox, "x1", 1.0) >= 0.25:
                continue
            if not (0.0 < getattr(bbox, "y1", 1.0) < 0.25):
                continue
        annotations.append(
            {
                "annotation_id": stable_id(
                    "dann", "visual-semantic", element_id, result.semantic_id
                ),
                "confidence": round(result.confidence, 6),
                "content": domain_type,
                "domain_type": domain_type,
                "element_id": element_id,
                "evidence_ids": list(getattr(element, "evidence_ids", []) or []),
                "page_index": getattr(page, "index", None) if page is not None else None,
                "properties": {
                    "marker": "visual-semantic",
                    "semantic_id": result.semantic_id,
                    "match_method": result.method,
                    "special_meaning": getattr(
                        catalog.profile(result.semantic_id), "special_meaning", ""
                    ),
                },
                "review_status": "unreviewed",
                "rule_id": "education-visual-semantic-anchor",
            }
        )
    return annotations


def _semantic_to_domain_type(semantic_id: str) -> str | None:
    """语义 id 后缀 -> 板块类型；角色语义返回 textbook-character。"""
    if semantic_id.startswith("sujiaoban.section."):
        suffix = semantic_id.rsplit(".", 1)[-1]
        return _SECTION_SEMANTIC_TO_DOMAIN_TYPE.get(suffix)
    if semantic_id.startswith("sujiaoban.character."):
        return "textbook-character"
    return None


router = APIRouter(prefix="/v1/textbook", tags=["textbook"])

logger = logging.getLogger("document_intelligence.api")

PACK_ID = "education-content"

# 板块类型：这些类型对应的元素是「板块标题」，用于板块切割的边界。
_BOARD_DOMAIN_TYPES = frozenset(
    {
        "example",
        "try",
        "think-do",
        "exercise",
        "operation",
        "thinking-question",
    }
)


class AnnotateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    chapter_id: str = Field(pattern=SAFE_ID_PATTERN)
    reviewer: str = Field(min_length=1, max_length=127)
    review_level: str = Field(default="domain-expert", pattern=r"^(reviewer|domain-expert)$")
    correct: list[str] = Field(default_factory=list)  # 判定正确的 annotation_id
    wrong: list[str] = Field(default_factory=list)  # 判定错误的 annotation_id
    # 用户可修正每个对象的板块类型（annotation_id -> 修正后 domain_type）
    labels: dict[str, str] = Field(default_factory=dict)
    # 用户为每个对象添加的解释说明（annotation_id -> 说明，供模型/引擎学习）
    notes: dict[str, str] = Field(default_factory=dict)
    reason: str = Field(default="", max_length=4000)
    human_edit_seconds: float = Field(default=0.0, ge=0.0, le=86400.0)


def _svc(request: Request, name: str) -> Any:
    service = getattr(request.app.state, name, None)
    if service is None:
        raise HTTPException(status_code=503, detail=f"service unavailable: {name}")
    return service


def _workspace(request: Request) -> Path:
    return Path(request.app.state.settings.workspace) / "textbook"


def _chapter_record(root: Path, chapter_id: str) -> dict[str, Any]:
    record_id = validate_safe_id(chapter_id, field_name="chapter_id")
    directory = root / "chapters" / record_id
    path = directory / "result.json"
    if not path.is_file():
        raise HTTPException(status_code=404, detail="chapter analysis not found")
    return json.loads(path.read_text(encoding="utf-8"))


def _commit_chapter(root: Path, chapter_id: str, payload: dict[str, Any]) -> None:
    record_id = validate_safe_id(chapter_id, field_name="chapter_id")
    directory = root / "chapters" / record_id
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "result.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _element_text(element: object) -> str:
    """提取元素的可见文本（优先原生文本，其次公式，其次表格）。"""
    content = getattr(element, "content", None)
    if content is None:
        return ""
    text = content.text or content.latex
    if text is None and content.table:
        text = " | ".join(", ".join(row) for row in content.table)
    return (text or "").strip()


# 价格单位：孤立出现的「元/角/分」视为价格缺失数字的填空位。
_PRICE_UNITS = frozenset({"元", "角", "分"})
# 归一化面积阈值：面积达标（或附近有价格标签）的图片视为「内容图片」（插图/照片），
# 否则视为填空框/装饰图。内容照片（校服~0.005+、笔记本~0.02）明显大于竖式填空框（≤0.005）。
_IMAGE_AREA_THRESHOLD = 0.005

# 对话框列保护（不可破坏原则）：
# - _GAP_CENTER_TOL：相邻行两条空隙被视为「同一竖直列边界」的中心最大偏差（归一化坐标）。
# - _COL_OVERLAP_RATIO：同一列堆叠内元素两两水平重叠所需的最低比例（按较小者宽度计）。
#   对话框各行文本共享对齐边、两两重叠；算式/表格碎片各行互不重叠，据此区分二者。
_GAP_CENTER_TOL = 0.06
_COL_OVERLAP_RATIO = 0.5


def _is_image_element(element: object) -> bool:
    """判断元素是否为图片区域（含 OCR 无文本的插图/填空框）。"""
    if getattr(element, "base_type", None) == "image":
        return True
    content = getattr(element, "content", None)
    asset_ref = getattr(content, "asset_ref", None) if content is not None else None
    return bool(asset_ref and str(asset_ref).startswith("sha256:"))


def _is_price_text(text: str) -> bool:
    """是否为价格标签：数字+元/角/分，或孤立单位。"""
    return bool(re.fullmatch(r"[0-9]+[元角分]", text)) or text in _PRICE_UNITS


def _price_label(text: str) -> str:
    """孤立价格单位渲染为填空框「（ ）元」；数字+单位原样保留。"""
    return f"（ ）{text}" if text in _PRICE_UNITS else text


# 「答：」句子里学生答案填空位（OCR 常把答案空位合并掉）。
# 规则：单位词前若紧邻非数字（且未已填）则补「（ ）」，且只插在「句尾单位」或
# 「量词+笔记本」处，避免误伤「笔记本」这类名词里的「本」。
# 例：「答：豆豆一共要付元。」→「答：豆豆一共要付（ ）元。」
#     「答：剩下的钱还可以买本笔记本。」→「答：剩下的钱还可以买（ ）本笔记本。」
_ANSWER_UNITS = "元角分个本张条只辆袋盒块朵棵架"
_answer_blank_re = re.compile(
    r"(?<![0-9）%s记])([%s])(?=[。]|[笔])" % (_ANSWER_UNITS, _ANSWER_UNITS)
)


def _insert_answer_blank(text: str) -> str:
    """在「答：」句子的答案填空位插入「（ ）」；非「答：」句子原样返回。"""
    if not text.startswith("答："):
        return text
    return _answer_blank_re.sub(lambda m: "（ ）" + m.group(1), text)


def _layout_text(
    element_ids: list[str],
    elements_by_id: dict[str, object],
) -> str:
    """按几何位置把内容元素重排为可读文本，实现「图片 → 连贯文字」。

    翻译规则：
    - 图片识别：base_type=image 且面积≥阈值（或附近有价格标签）→ 内容图片，渲染为
      「〔图片：价格〕」，把紧邻的价格标签并入图片描述；否则视为填空框/装饰图，渲染为「（ ）」。
    - 价格归属：图片水平范围内、垂直位于图片内或紧贴图片下方的「数字+元/角/分」或孤立
      「元/角/分」并入所属图片；未被图片吸收的孤立价格单位渲染为「（ ）元」。
    - 学生填空：小面积填空框/空文本元素渲染为「（ ）」；「答：」句子里单位词前若紧邻
      非数字则补「（ ）」，如「答：豆豆一共要付元。」→「答：豆豆一共要付（ ）元。」。
    - 不可破坏原则：对话框内的文字是完整语义单元，必须保持完整顺序，不得因从左到右阅读序
      将不同对话框内容交错拼接。检测稳定竖直列边界后，对多列并行区域优先列优先输出。
    - 默认布局：按归一化 bbox 的 y 中心分行、行内按 x 中心排序，空格/换行分隔。
    """
    flow: list[tuple[float, float, float, str]] = []  # 随行排列的元素：(cy, x1, x2, text)
    blocks: list[tuple[float, float, float, str]] = []  # 内容图片描述块：(cy, x1, x2, text)
    deco: list[tuple[float, float, float, str]] = []  # 装饰性小图（气泡图标）占位：(cy, x1, x2, "（ ）"）
    flow_heights: list[float] = []

    images: list[tuple[str, object, float, float]] = []  # (element_id, bbox, cx, cy)
    prices: list[tuple[str, object, float, float, str]] = []  # (element_id, bbox, cx, cy, text)

    for element_id in element_ids:
        element = elements_by_id.get(element_id)
        if element is None or element.bbox is None:
            continue
        bbox = element.bbox
        cx = (bbox.x1 + bbox.x2) / 2.0
        cy = (bbox.y1 + bbox.y2) / 2.0
        text = _insert_answer_blank(_element_text(element))
        if _is_image_element(element):
            images.append((element_id, bbox, cx, cy))
        elif text and _is_price_text(text):
            prices.append((element_id, bbox, cx, cy, text))
        else:
            flow.append((cy, bbox.x1, bbox.x2, text or "（ ）"))
            height = bbox.y2 - bbox.y1
            if height > 0:
                flow_heights.append(height)

    # 内容图片：面积达标，或附近有价格标签
    content_images: set[str] = set()
    for element_id, bbox, _, _ in images:
        area = (bbox.x2 - bbox.x1) * (bbox.y2 - bbox.y1)
        if area >= _IMAGE_AREA_THRESHOLD:
            content_images.add(element_id)

    # 把价格标签归给最近的图片（几何邻近）
    price_by_image: dict[str, list[tuple[float, str]]] = {}
    used_prices: set[str] = set()
    for peid, pbbox, pcx, pcy, ptext in prices:
        best: str | None = None
        best_dist = float("inf")
        for ieid, ibbox, icx, icy in images:
            if ieid not in content_images:
                continue
            margin = (ibbox.x2 - ibbox.x1) * 0.5
            if not (ibbox.x1 - margin <= pcx <= ibbox.x2 + margin):
                continue
            if not (ibbox.y1 - margin <= pcy <= ibbox.y2 + margin):
                continue
            dist = (pcx - icx) ** 2 + (pcy - icy) ** 2
            if dist < best_dist:
                best_dist = dist
                best = ieid
        if best is not None:
            price_by_image.setdefault(best, []).append((pcx, ptext))
            used_prices.add(peid)

    # 生成图片描述块 / 填空框占位
    for ieid, bbox, cx, cy in images:
        if ieid in content_images:
            items = sorted(price_by_image.get(ieid, []), key=lambda it: it[0])
            desc = "、".join(_price_label(t) for _, t in items) if items else ""
            blocks.append((cy, bbox.x1, bbox.x2, f"〔图片：{desc}〕" if desc else "〔图片〕"))
        else:
            # 装饰性小图（气泡图标等）不参与行分组与行容差统计：其高度约为文字行高的数倍，
            # cy 常落在相邻两行文字之间，若混入 flow 会作为「链环」把两行文字粘成一行，
            # 把对话框内容搅碎。改为行分组完成后按 cy 就近挂到最近文本行。
            deco.append((cy, bbox.x1, bbox.x2, "（ ）"))

    # 未被图片吸收的孤立价格单位
    for peid, pbbox, pcx, pcy, ptext in prices:
        if peid not in used_prices:
            flow.append((pcy, pbbox.x1, pbbox.x2, _price_label(ptext)))
            height = pbbox.y2 - pbbox.y1
            if height > 0:
                flow_heights.append(height)

    elems = flow + blocks
    if not elems:
        return ""

    # 行容差：取流式元素中位高度的一半（内容图片块单独成行，不参与中位统计），过低则回退固定值
    flow_heights.sort()
    median_height = flow_heights[len(flow_heights) // 2] if flow_heights else 0.02
    tolerance = max(median_height * 0.5, 0.008)

    elems.sort(key=lambda item: item[0])
    rows: list[list[tuple[float, float, float, str]]] = [[elems[0]]]
    for item in elems[1:]:
        if item[0] - rows[-1][-1][0] <= tolerance:
            rows[-1].append(item)
        else:
            rows.append([item])

    # 装饰性小图（气泡图标）按 cy 就近挂到最近文本行，行内位置由后续 x 排序决定。
    if deco:
        row_cy = [sum(it[0] for it in row) / len(row) for row in rows]
        for d in deco:
            best = min(range(len(rows)), key=lambda r: abs(d[0] - row_cy[r]))
            rows[best].append(d)
            row_cy[best] = sum(it[0] for it in rows[best]) / len(rows[best])

    for row in rows:
        row.sort(key=lambda item: (item[1] + item[2]) / 2.0)  # 行内按 x 中心排序

    # ---- 对话框列保护（不可破坏原则）----
    # 教材里并排的对话框各自包含完整的一句话，若按「y 分行 + 行内按 x 排序」输出，
    # 会把左右对话框的文字交错拼接，把语义搞破碎（如把「数学课本封面的宽比18厘米多一些。」
    # 与「多出的部分不足1厘米。」交错成一行）。因此：
    #   1. 检测相邻两行是否共享一条「稳定的竖直列边界」（同一条空隙在上下两行同时出现）；
    #   2. 校验边界两侧元素各自构成水平对齐的「列堆叠」（两两重叠，区别于行内算式碎片）；
    #   3. 命中后把该行段改为列优先输出：先整列自上而下、再下一列，保持对话框句子完整。
    # 普通单列行（正文、算式、数轴）不满足稳定列边界，仍按默认从左到右分行输出，不受影响。
    def _row_gaps(
        row: list[tuple[float, float, float, str]],
    ) -> list[tuple[float, float, float]]:
        """返回行内相邻元素之间的空隙：(中心, 左元素右缘, 右元素左缘)，按中心升序。"""
        gaps: list[tuple[float, float, float]] = []
        for a, b in zip(row, row[1:]):
            left_x2, right_x1 = a[2], b[1]
            if right_x1 > left_x2:
                gaps.append(((left_x2 + right_x1) / 2.0, left_x2, right_x1))
        return gaps

    def _side_coherent(items: list[tuple[float, float, float, str]]) -> bool:
        """列堆叠判定：同一列的多个行元素须构成「水平重叠的连通簇」。

        对话框各行文本共享对齐边、彼此重叠，构成一个大连通簇；紧贴对话框外侧的装饰性
        气泡图标（小图，渲染为「（ ）」）与文本列水平不重叠，是孤立离群点，应被容忍而不
        破坏列保护。算式/表格碎片各行水平位置各异、互相孤立（最大连通分量=1），仍被拒绝。
        判定标准：连通簇至少含 2 个元素，且覆盖该侧半数以上元素，才是真正的列堆叠。
        """
        if len(items) < 2:
            return True
        n = len(items)
        parent = list(range(n))

        def _find(x: int) -> int:
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        for i in range(n):
            for j in range(i + 1, n):
                overlap = min(items[i][2], items[j][2]) - max(items[i][1], items[j][1])
                if overlap <= 0:
                    continue
                small = min(items[i][2] - items[i][1], items[j][2] - items[j][1])
                if small <= 0 or overlap / small < _COL_OVERLAP_RATIO:
                    continue
                ri, rj = _find(i), _find(j)
                if ri != rj:
                    parent[rj] = ri
        sizes: dict[int, int] = {}
        for i in range(n):
            root = _find(i)
            sizes[root] = sizes.get(root, 0) + 1
        largest = max(sizes.values())
        return largest >= 2 and largest * 2 >= n

    protected: list[bool] = [False] * len(rows)
    boundary_of_row: list[float | None] = [None] * len(rows)
    for i in range(len(rows) - 1):
        gaps_i = _row_gaps(rows[i])
        gaps_j = _row_gaps(rows[i + 1])
        if not gaps_i or not gaps_j:
            continue
        matched = False
        for c1, l1, r1 in gaps_i:
            if matched:
                break
            for c2, l2, r2 in gaps_j:
                if abs(c1 - c2) > _GAP_CENTER_TOL:
                    continue
                if min(r1, r2) <= max(l1, l2):
                    continue  # 两条空隙在水平方向无交集，非同一列边界
                boundary = (c1 + c2) / 2.0
                left_items = [
                    it
                    for row in (rows[i], rows[i + 1])
                    for it in row
                    if it[2] < boundary
                ]
                right_items = [
                    it
                    for row in (rows[i], rows[i + 1])
                    for it in row
                    if it[1] > boundary
                ]
                if not left_items or not right_items:
                    continue
                if not _side_coherent(left_items) or not _side_coherent(right_items):
                    continue
                matched = True
                protected[i] = True
                protected[i + 1] = True
                boundary_of_row[i] = boundary
                boundary_of_row[i + 1] = boundary
                break

    # 扩展受保护段：吸收「列延续行」，避免把一句话拆散。
    # 并排对话框的某一侧可能比另一侧多一行（如左对话框 3 行、右对话框 2 行），
    # 末尾单列收尾行只有一个元素、行内无空隙，无法匹配稳定列边界而未被保护，
    # 若不吸收会被排到另一侧之后、把句子搞破碎。判定：整行元素全部落在边界某一侧
    # （无跨界元素、左右两侧不同时出现），即为该列的延续，纳入保护段一并列优先输出。
    def _row_fits_column(row: list[tuple[float, float, float, str]], b: float) -> bool:
        lefts = [it for it in row if it[2] <= b]
        rights = [it for it in row if it[1] >= b]
        if lefts and rights:
            return False  # 左右两侧都有元素，非单列延续
        return bool(lefts) or bool(rights)

    i = 0
    while i < len(rows):
        if not protected[i]:
            i += 1
            continue
        start = i
        bounds: list[float] = []
        while i < len(rows) and protected[i]:
            if boundary_of_row[i] is not None:
                bounds.append(boundary_of_row[i])
            i += 1
        end = i - 1
        if not bounds:
            continue
        b = sum(bounds) / len(bounds)
        r = end + 1
        while r < len(rows) and not protected[r]:
            if _row_fits_column(rows[r], b):
                protected[r] = True
                boundary_of_row[r] = b
                end = r
                r += 1
            else:
                break
        r = start - 1
        while r >= 0 and not protected[r]:
            if _row_fits_column(rows[r], b):
                protected[r] = True
                boundary_of_row[r] = b
                start = r
                r -= 1
            else:
                break
        i = end + 1

    lines: list[str] = []

    def _emit_segment(start: int, end: int) -> None:
        """列优先输出受保护的连续行段：先整列自上而下，再下一列。"""
        boundaries = [
            boundary_of_row[r]
            for r in range(start, end + 1)
            if boundary_of_row[r] is not None
        ]
        if not boundaries:
            for r in range(start, end + 1):
                lines.append(" ".join(it[3] for it in rows[r]))
            return
        boundary = sum(boundaries) / len(boundaries)
        left_elems: list[str] = []
        right_elems: list[str] = []
        for r in range(start, end + 1):
            for it in rows[r]:
                if it[2] < boundary:
                    left_elems.append(it[3])
                elif it[1] > boundary:
                    right_elems.append(it[3])
                else:
                    # 跨界元素（如跨列图片块）随左列输出，避免丢失
                    left_elems.append(it[3])
        if left_elems:
            lines.append(" ".join(left_elems))
        if right_elems:
            lines.append(" ".join(right_elems))

    seg_start: int | None = None
    for r in range(len(rows)):
        if protected[r]:
            if seg_start is None:
                seg_start = r
            continue
        if seg_start is not None:
            _emit_segment(seg_start, r - 1)
            seg_start = None
        lines.append(" ".join(it[3] for it in rows[r]))
    if seg_start is not None:
        _emit_segment(seg_start, len(rows) - 1)
    return "\n".join(lines)


# 书本标志（例题）的几何判定：归一化 bbox 落在页面左上角区域，且文本以数字开头。
# 苏教版教材中，例题在板块左上角有一个书本图标，图标内标注数字（1、2、3……）。
_BOOK_ICON_BBOX_X1_MAX = 0.16
_BOOK_ICON_BBOX_Y1_MIN = 0.03
# 不同页面书本图标位置略有浮动（实测例题行顶可达 y≈0.144），放宽上界避免漏检。
_BOOK_ICON_BBOX_Y1_MAX = 0.18
_BOOK_ICON_NUMBER_MAX_DIGITS = 3
# 例题数字后正文至少含有的汉字数。真实例题的正文是一整句话（如 "1东林村在村里3条主干道路…"），
# 而钟表标签（"9时"、"12时30分"）虽以数字开头且位于左上角，但其后汉字很少，据此排除误检。
_BOOK_ICON_MIN_BODY_CJK = 4
# 例题编号上限。单元内例题编号通常很小（本教材实测 ≤ 10）；
# 左上角出现的较大纯数字（如 "162"、"54"、"60"）实为算式数据/题号而非例题图标，据此排除误判。
_BOOK_ICON_MAX_NUMBER = 20

# 例题数字：以 1-3 位数字开头，其后（可含空白）跟汉字或文本结束。
# 允许「数字与正文被解析器合并」的情形（如 "1东林村…"、"2王叔叔…"），
# 同时排除以数字开头的算式/编号/数轴（数字后跟运算符或空白数字，如 "50×3"、"0 1 2 3"）。
_BOOK_ICON_NUMBER_RE = re.compile(
    r"^\s*(\d{1," + str(_BOOK_ICON_NUMBER_MAX_DIGITS) + r"})(?=\s*[\u4e00-\u9fff]|\s*$)"
)


def _book_icon_number(text: str) -> str | None:
    """从文本开头提取「书本标志数字」。返回数字串；非例题数字开头返回 None。

    支持两种情形：
    1. 纯数字（如 "1"、"2"）；
    2. 数字与正文被解析器合并成一条文本（如 "1东林村……"）——仍能提取开头的数字。

    为排除钟表标签（如 "9时"、"12时30分"）等短标签误判，要求数字之后的正文
    至少含 _BOOK_ICON_MIN_BODY_CJK 个汉字。
    """
    m = _BOOK_ICON_NUMBER_RE.match(text)
    if not m:
        return None
    number = m.group(1)
    rest = text[m.end():]
    if int(number) > _BOOK_ICON_MAX_NUMBER:
        return None  # 编号过大（如 162、54、60）实为算式数据，排除
    if not rest:
        return number  # 纯数字（书本图标单独成行）
    cjk_count = sum(1 for ch in rest if "\u4e00" <= ch <= "\u9fff")
    if cjk_count < _BOOK_ICON_MIN_BODY_CJK:
        return None
    return number


def _is_book_icon_number(element: object) -> bool:
    """判断元素是否为「书本标志里面的数字」（例题标记）。

    判据：文本以 1-3 位数字开头（可为合并长文本）+ 位于页面左上角
    （归一化 bbox x1<0.16、0.03<y1<0.18）。
    是否作为例题标题还需结合「该页阅读序中第一个满足几何判定的元素」进一步确认。
    """
    bbox = getattr(element, "bbox", None)
    if bbox is None:
        return False
    x1 = getattr(bbox, "x1", None)
    y1 = getattr(bbox, "y1", None)
    if x1 is None or y1 is None:
        return False
    if x1 >= _BOOK_ICON_BBOX_X1_MAX:
        return False
    if not (_BOOK_ICON_BBOX_Y1_MIN < y1 < _BOOK_ICON_BBOX_Y1_MAX):
        return False
    return _book_icon_number(_element_text(element)) is not None


def _detect_example_titles(
    content_order: list[str],
    elements_by_id: dict[str, object],
    section_titles_by_page: dict[str, set[str]] | None = None,
) -> list[str]:
    """检测「书本标志 + 数字 → 例题」板块标题元素。

    规则：书本图标里的数字是页面左上角区域「第一个满足书本标志几何判定」的文本元素。
    不要求是整页第一个文本元素——其前面可能还有章节标题（如"口算和估算"）；
    章节标题不以数字开头，不会被误判。

    抑制规则：若候选数字元素所在页已出现「板块标题」（试一试/想想做做/练习/动手做等，
    即 section_titles_by_page[page_id]），则该数字很可能是栏目内容里的题号/算式数字
    （如练习三里的 "5."），而非书本标志例题，应被抑制。

    判定采用「几何优先、阅读序兜底」：
    - 几何：板块标题的归一化 y1 小于候选数字的 y1（即标题在数字上方）→ 抑制。
      真实例题总是其所在页最靠上的板块级标记，其上方不可能再出现其它板块标题。
      该判据不依赖列优先的阅读序（阅读序会把右列标题排在左列数字之后，造成漏抑）。
    - 兜底：板块标题在阅读序中位于候选数字之前 → 抑制。
    """
    order_pos = {element_id: i for i, element_id in enumerate(content_order)}
    first_by_page: dict[str, str] = {}

    def _y1(eid: str) -> float | None:
        el = elements_by_id.get(eid)
        if el is None:
            return None
        bbox = getattr(el, "bbox", None)
        if bbox is None:
            return None
        return getattr(bbox, "y1", None)

    for element_id in content_order:
        element = elements_by_id.get(element_id)
        if element is None:
            continue
        page_id = getattr(element, "page_id", "")
        if page_id in first_by_page:
            continue
        if not _is_book_icon_number(element):
            continue
        if section_titles_by_page is not None:
            page_sections = section_titles_by_page.get(page_id) or set()
            if page_sections:
                cand_y1 = _y1(element_id)
                pos = order_pos.get(element_id, 0)
                suppressed = False
                for sec_id in page_sections:
                    if suppressed:
                        break
                    # 几何：标题在数字上方（y 更小）
                    sec_y1 = _y1(sec_id)
                    if cand_y1 is not None and sec_y1 is not None and sec_y1 < cand_y1:
                        suppressed = True
                        break
                    # 阅读序兜底：标题先于数字出现
                    if order_pos.get(sec_id, 1 << 30) < pos:
                        suppressed = True
                        break
                if suppressed:
                    continue
        first_by_page[page_id] = element_id
    return list(first_by_page.values())


def _build_boards(
    structure: object,
    annotations: list[dict[str, Any]],
    elements_by_id: dict[str, object],
    pages_by_id: dict[str, object],
) -> list[dict[str, Any]]:
    """板块切割：把「板块标题」与其后内容归并为完整板块，边界精确到下一个板块标题。

    规则：
    - 板块标题来自两类来源：
      1. 领域标注元素（试一试/想想做做/例N/练习/动手做/思考题）；
      2. 「书本标志 + 数字」几何检测出的例题标题（见 _detect_example_titles）。
    - 板块标题元素本身 + 其后直到下一个板块标题之前的所有内容元素，属于该板块。
    - 若某内容元素同时被多个板块标注（如 think-do 误含上方 try 内容），按阅读序最近的板块标题归属。
    """
    content_order = list(getattr(structure, "content_reading_order", []) or [])
    if not content_order:
        return []

    # 板块标题：element_id -> domain_type，按阅读顺序
    title_by_element: dict[str, str] = {}
    for ann in annotations:
        if ann.get("domain_type") in _BOARD_DOMAIN_TYPES:
            title_by_element[ann["element_id"]] = ann["domain_type"]
    # 书本标志 + 数字 → 例题（未被领域标注覆盖的优先级更高，避免误判为其它板块）
    section_titles_by_page = _section_titles_by_page(annotations, elements_by_id)
    for element_id in _detect_example_titles(
        content_order, elements_by_id, section_titles_by_page
    ):
        title_by_element[element_id] = "example"
    if not title_by_element:
        return []

    boards: list[dict[str, Any]] = []

    def _text_of(element_id: str) -> str:
        element = elements_by_id.get(element_id)
        return _element_text(element) if element is not None else ""

    def _page_index(element_id: str) -> int | None:
        element = elements_by_id.get(element_id)
        if element is None:
            return None
        page = pages_by_id.get(getattr(element, "page_id", ""))
        return getattr(page, "index", None) if page is not None else None

    # 记录每次标注的标题（含识别到的旧板块归属），用于在切割时把内容分给正确的板块
    for element_id in content_order:
        if element_id not in title_by_element:
            continue
        board_type = title_by_element[element_id]
        title = _text_of(element_id)
        if board_type == "example":
            # 书本标志例题：标题取「例N」，而非被合并进的长正文
            number = _book_icon_number(title)
            if number:
                title = f"例{number}"
        boards.append(
            {
                "title_element_id": element_id,
                "board_type": board_type,
                "title": title,
                "page_index": _page_index(element_id),
                "element_ids": [element_id],
                "content": "",
            }
        )
    if not boards:
        return []

    # 在阅读序中定位每个板块标题的索引
    order_index = {element_id: i for i, element_id in enumerate(content_order)}
    board_indexes = [
        (order_index[board["title_element_id"]], board) for board in boards
    ]
    board_indexes.sort(key=lambda item: item[0])

    # 当下一个板块标题的索引，作为当前板块的结束边界（不含）
    next_index = [
        board_indexes[i + 1][0] if i + 1 < len(board_indexes) else len(content_order)
        for i in range(len(board_indexes))
    ]

    for i, (start_index, board) in enumerate(board_indexes):
        end_index = next_index[i]
        content_ids = list(content_order[start_index + 1 : end_index])
        board["element_ids"] = [board["title_element_id"], *content_ids]
        # 按几何位置重排内容（分行 + 行内按 x 排序 + 空格/换行分隔 + □ 占位），
        # 代替原先按阅读序裸拼接，避免左右列交错、公式粘连、孤立运算符等问题。
        board["content"] = _layout_text(content_ids, elements_by_id)
    return [board for _, board in board_indexes]


@router.post("/chapters/analyze")
async def analyze_chapter(
    request: Request,
    file: Annotated[UploadFile, File()],
    page_range: Annotated[str | None, Form()] = None,
    chapter_name: Annotated[str | None, Form()] = None,
    parser_id: Annotated[str, Form()] = "auto",
) -> dict[str, Any]:
    """上传教材 PDF，按 page_range 解析章节，串联 parse → structure → domain。"""
    orchestrator = _svc(request, "orchestrator")
    structure_service = _svc(request, "structure_service")
    domain_service = _svc(request, "domain_service")
    review_service = _svc(request, "review_service")
    settings = request.app.state.settings

    content = await file.read(settings.max_upload_bytes + 1)
    from document_intelligence.services import IngestionPolicy, ingest_bytes

    policy = IngestionPolicy(max_upload_bytes=settings.max_upload_bytes)
    options: dict[str, object] = {}
    if page_range:
        options["page_range"] = page_range
    parse_request = ingest_bytes(
        file.filename or "textbook.pdf",
        content,
        policy=policy,
        parser_id=parser_id,
        options=options,
    )
    _t_parse = time.perf_counter()
    result = await run_in_threadpool(orchestrator.parse, parse_request)
    logger.info("textbook analyze parse took %.1fs elements=%d", time.perf_counter() - _t_parse, len(result.document.elements))
    parse_run_id = result.run.parse_run_id
    document_id = result.document.document_id

    _t = time.perf_counter()
    structure = await run_in_threadpool(structure_service.recover_run, parse_run_id)
    logger.info("textbook analyze structure took %.1fs", time.perf_counter() - _t)
    structure_id = structure.structure_id

    _t = time.perf_counter()
    domain_result = await run_in_threadpool(
        domain_service.apply, structure_id, PACK_ID, None, fallback_on_error=True
    )
    logger.info("textbook analyze domain took %.1fs", time.perf_counter() - _t)
    _t = time.perf_counter()
    export = await run_in_threadpool(review_service.export_labelu, domain_result.domain_result_id)
    logger.info("textbook analyze export took %.1fs", time.perf_counter() - _t)

    root = _workspace(request)
    root.mkdir(parents=True, exist_ok=True)
    chapter_id = stable_id(
        "chapter",
        document_id,
        page_range or "full",
        chapter_name or "untitled",
        parse_run_id,
    )

    # 为每个识别对象附加对应的教材原文（供人工审核判断对错）
    elements_by_id = {e.element_id: e for e in result.document.elements}
    pages_by_id = {p.page_id: p for p in result.document.pages}

    # 补充「书本标志 + 数字 → 例题」的几何检测标注，使例题在注释列表与板块结构中可见
    base_annotations = [a.model_dump(mode="json") for a in domain_result.annotations]
    # 汇总每页已识别的板块标题，抑制练习/想想做做等栏目页上的例题数字误判
    section_titles_by_page = _section_titles_by_page(base_annotations, elements_by_id)
    all_annotations = base_annotations + _build_example_annotations(
        list(getattr(structure, "content_reading_order", []) or []),
        elements_by_id,
        pages_by_id,
        section_titles_by_page,
    )

    # 「先识别图标/角色」：调用视觉匹配器锚定例题/栏目图标与教材角色
    visual_catalog_service = getattr(request.app.state, "visual_catalog_service", None)
    if visual_catalog_service is not None:
        all_annotations += _build_visual_semantic_annotations(
            result.document,
            visual_catalog_service,
            orchestrator.store,
            elements_by_id,
            pages_by_id,
        )

    # 板块切割：把「板块标题 + 其后内容」归并为完整板块，边界到下一个板块标题
    boards = _build_boards(
        structure,
        all_annotations,
        elements_by_id,
        pages_by_id,
    )

    record = {
        "chapter_id": chapter_id,
        "chapter_name": chapter_name or "未命名章节",
        "page_range": page_range,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "parse_run_id": parse_run_id,
        "document_id": document_id,
        "source_ref": result.document.source.source_ref,
        "structure_id": structure_id,
        "domain_result_id": domain_result.domain_result_id,
        "export_id": export.export_id,
        "source_domain_digest": domain_result.semantic_digest(),
        "annotations": [
            _annotation_view(a, elements_by_id, pages_by_id) for a in all_annotations
        ],
        "boards": boards,
        "relations": [r.model_dump(mode="json") for r in domain_result.relations],
        "metrics": {
            "annotations": domain_result.metrics.annotations,
            "domain_relations": domain_result.metrics.domain_relations,
            "validation_findings": domain_result.metrics.validation_findings,
            "error_findings": domain_result.metrics.error_findings,
            "fallback_used": domain_result.metrics.fallback_used,
        },
        "iterations": [],
    }
    _commit_chapter(root, chapter_id, record)
    return {"success": True, "chapter": record}


def _page_range_start(page_range: str | None) -> int:
    """从 page_range（如 "8-11"，0 起含端点）解析出起始物理页。"""
    if not page_range or "-" not in page_range:
        return 0
    try:
        return int(page_range.split("-", 1)[0])
    except ValueError:
        return 0


@router.get("/chapters/{chapter_id}/pages/{page_index}/image")
async def chapter_page_image(
    request: Request,
    chapter_id: Annotated[str, PathParam(pattern=SAFE_ID_PATTERN)],
    page_index: Annotated[int, PathParam(ge=0)],
) -> Response:
    """渲染章节内页序 page_index 对应的原页图片（供人工对照判断识别对象对错）。

    物理页 = page_range 起始页 + page_index。渲染结果按物理页缓存到章节目录，
    避免重复打开大体积扫描版 PDF。
    """
    root = _workspace(request)
    record = _chapter_record(root, chapter_id)
    source_ref = record.get("source_ref")
    if not source_ref:
        raise HTTPException(status_code=404, detail="该章节未保留源 PDF，请重新解析")
    source_path = Path(request.app.state.settings.workspace) / source_ref
    if not source_path.is_file():
        raise HTTPException(status_code=404, detail="源 PDF 文件缺失")

    physical_page = _page_range_start(record.get("page_range")) + page_index
    cache_dir = root / "chapters" / chapter_id / "pages"
    cache_file = cache_dir / f"{physical_page:04d}.png"
    if not cache_file.is_file():
        try:
            import fitz  # PyMuPDF
        except ImportError as exc:  # pragma: no cover
            raise HTTPException(status_code=503, detail="PyMuPDF 未安装，无法渲染页面") from exc
        try:
            doc = fitz.open(source_path)
            try:
                if physical_page < 0 or physical_page >= doc.page_count:
                    raise HTTPException(status_code=404, detail="页面超出范围")
                page = doc[physical_page]
                pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
                cache_dir.mkdir(parents=True, exist_ok=True)
                pix.save(str(cache_file))
            finally:
                doc.close()
        except HTTPException:
            raise
        except Exception as exc:  # pragma: no cover
            logger.exception("render page %d failed", physical_page)
            raise HTTPException(status_code=500, detail=f"渲染页面失败: {exc}") from exc
    return Response(
        content=cache_file.read_bytes(),
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=86400"},
    )


@router.post("/chapters/annotate")
async def annotate_chapter(
    request: Request,
    payload: Annotated[AnnotateRequest, Body()],
) -> dict[str, Any]:
    """提交章节标注（正确/错误），落盘并触发 rill 自学习回灌。"""
    review_service = _svc(request, "review_service")
    rill_service = _svc(request, "rill_service")
    root = _workspace(request)

    record = _chapter_record(root, payload.chapter_id)
    domain_result_id = record["domain_result_id"]
    source_domain_digest = record["source_domain_digest"]
    export_id = record["export_id"]

    # 构造 LabelU 评审提交：正确项保留其 domain_type 标签，错误项剔除（不写入标签）
    annotations = {a["annotation_id"]: a for a in record["annotations"]}
    correct_ids = set(payload.correct)
    wrong_ids = set(payload.wrong)
    if correct_ids & wrong_ids:
        raise HTTPException(
            status_code=422, detail="an annotation cannot be both correct and wrong"
        )
    objects: list[ReviewedObject] = []
    for annotation in record["annotations"]:
        annotation_id = annotation["annotation_id"]
        if annotation_id in wrong_ids:
            continue  # 人工判定错误 → 不保留该对象（作为反例）
        if annotation_id in correct_ids or not (correct_ids or wrong_ids):
            # 优先采用用户修正的板块类型，否则沿用引擎识别结果
            corrected = payload.labels.get(annotation_id, annotation["domain_type"])
            objects.append(
                ReviewedObject(
                    element_id=annotation["element_id"],
                    labels=[corrected],
                )
            )

    submission = LabelUReviewSubmission(
        adapter="labelu-json-v1",
        export_id=export_id,
        domain_result_id=domain_result_id,
        source_domain_digest=source_domain_digest,
        reviewer=payload.reviewer,
        review_level=payload.review_level,  # type: ignore[arg-type]
        reason=payload.reason or "textbook chapter annotation",
        objects=objects,
        relations=[
            ReviewedRelation(
                source_id=r["source_id"],
                target_id=r["target_id"],
                label=r["domain_type"],
            )
            for r in record["relations"]
        ],
    )
    review_record = await run_in_threadpool(review_service.submit_labelu, submission)

    # 自学习回灌：对章节执行 rill shadow 评估，并把人工标注作为反馈写入
    iteration = {
        "iteration": len(record["iterations"]) + 1,
        "reviewed_at": datetime.now(timezone.utc).isoformat(),
        "reviewer": payload.reviewer,
        "correct_count": len(objects),
        "wrong_count": len(wrong_ids),
        # 用户修正的板块类型（annotation_id -> domain_type）
        "labels": payload.labels,
        # 用户解释说明（annotation_id -> 说明），供模型/引擎学习迭代
        "notes": payload.notes,
        "feedback": None,
    }
    try:
        evaluation = await run_in_threadpool(
            rill_service.evaluate,
            record["parse_run_id"],
            structure_id=record["structure_id"],
            domain_result_id=domain_result_id,
        )
        feedback = ShadowFeedbackInput(
            evaluation_id=evaluation.evaluation_id,
            actual_action=ShadowAction.HUMAN_REVIEW,
            decision_correct=(len(wrong_ids) == 0),
            error_scope="textbook.chapter.annotation",
            error_type="wrong" if wrong_ids else "ok",
            severity=FeedbackSeverity.P0 if wrong_ids else FeedbackSeverity.P2,
            human_edit_seconds=payload.human_edit_seconds,
            eligible_for_training=True,
            outcome_time_ms=0,
        )
        iteration["feedback"] = (
            await run_in_threadpool(rill_service.feedback, feedback)
        ).model_dump(mode="json")
    except Exception as exc:  # 自学习失败不应阻断标注提交
        iteration["feedback_error"] = str(exc)

    record["iterations"].append(iteration)
    _commit_chapter(root, payload.chapter_id, record)
    return {
        "success": True,
        "review": review_record.model_dump(mode="json"),
        "chapter": record,
    }


@router.delete("/chapters/{chapter_id}")
async def delete_chapter(
    request: Request,
    chapter_id: Annotated[str, PathParam(pattern=SAFE_ID_PATTERN)],
) -> dict[str, Any]:
    """删除章节分析记录（含解析结果、标注历史和自学习数据）。"""
    root = _workspace(request)
    record_id = validate_safe_id(chapter_id, field_name="chapter_id")
    chapter_dir = root / "chapters" / record_id
    if not chapter_dir.is_dir() or not (chapter_dir / "result.json").is_file():
        raise HTTPException(status_code=404, detail="章节记录不存在")
    try:
        shutil.rmtree(chapter_dir)
    except Exception as exc:  # pragma: no cover
        logger.exception("delete chapter %s failed", record_id)
        raise HTTPException(status_code=500, detail=f"删除章节失败: {exc}") from exc
    return {"success": True, "chapter_id": chapter_id, "deleted": True}


@router.get("/chapters/list")
async def list_chapters(request: Request) -> dict[str, Any]:
    root = _workspace(request)
    chapters_dir = root / "chapters"
    results: list[dict[str, Any]] = []
    if chapters_dir.is_dir():
        for item in sorted(chapters_dir.iterdir(), reverse=True):
            if not item.is_dir():
                continue
            path = item / "result.json"
            if not path.is_file():
                continue
            try:
                record = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            results.append(
                {
                    "chapter_id": record.get("chapter_id"),
                    "chapter_name": record.get("chapter_name"),
                    "page_range": record.get("page_range"),
                    "created_at": record.get("created_at"),
                    "metrics": record.get("metrics"),
                    "iteration_count": len(record.get("iterations", [])),
                }
            )
    return {"chapters": results}


@router.get("/chapters/{chapter_id}")
async def get_chapter(
    request: Request, chapter_id: Annotated[str, PathParam(pattern=SAFE_ID_PATTERN)]
) -> dict[str, Any]:
    record = _chapter_record(_workspace(request), chapter_id)
    # 旧数据可能未存 bbox（序列化后才引入）；读取时按 parse_run 重新补齐，供前端页面标注视图定位
    _enrich_annotation_bbox(request, record)
    # 用人工修正文字覆盖板块 content，使「板块结构」直接展示已提交的标准文字
    root = _workspace(request)
    samples = record.get(_BOARD_LEARNING_KEY, {})
    boards = record.get("boards", [])
    for idx_str, entry in samples.items():
        if not isinstance(entry, dict):
            continue
        text = entry.get("corrected_text", "")
        if not text:
            continue
        try:
            idx = int(idx_str)
        except (ValueError, TypeError):
            continue
        if 0 <= idx < len(boards):
            board = boards[idx]
            if "engine_content" not in board:
                board["engine_content"] = board.get("content", "")
            board["content"] = text
    return {"chapter": record}


def _enrich_annotation_bbox(request: Request, record: dict[str, Any]) -> None:
    """按 parse_run redis 重建 element/page 索引，为存储的标注补齐 bbox（及缺失的 content/page_index）。

    仅当记录里已有 element_id 且对应 parse run 仍可读时生效；不可读时静默跳过，不阻塞详情展示。
    """
    parse_run_id = record.get("parse_run_id")
    annotations = record.get("annotations") or []
    if not parse_run_id or not annotations:
        return
    try:
        result = _svc(request, "orchestrator").store.read_result(parse_run_id)
    except Exception:  # run 被清理/损坏时降级为已有数据
        return
    elements_by_id = {e.element_id: e for e in result.document.elements}
    pages_by_id = {p.page_id: p for p in result.document.pages}
    for a in annotations:
        if not isinstance(a, dict) or not a.get("element_id"):
            continue
        view = _annotation_view(a, elements_by_id, pages_by_id)
        if a.get("bbox") is None:
            a["bbox"] = view.get("bbox")
        if a.get("content") is None:
            a["content"] = view.get("content")
        if a.get("page_index") is None:
            a["page_index"] = view.get("page_index")


# ============================================================================
# 板块文字标注：用户提交标准文字 → 样本库，及板块裁剪图
# ============================================================================

# 学习样本保留的字段名前缀，用于区分「AI 生成的」与「人工标注的」
_BOARD_LEARNING_KEY = "board_learning_samples"


def _board_drafts_file(root: Path, chapter_id: str) -> Path:
    """AI 自迭代生成的板块文字草稿文件（未人工确认前只写入草稿库）。"""
    return root / "board-drafts" / f"{chapter_id}.json"


def _load_board_drafts(root: Path, chapter_id: str) -> dict[str, Any]:
    """读取 AI 生成的板块文字草稿：board_index(str) -> 草稿条目。"""
    path = _board_drafts_file(root, chapter_id)
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_board_drafts(root: Path, chapter_id: str, drafts: dict[str, Any]) -> None:
    path = _board_drafts_file(root, chapter_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(drafts, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


@router.post("/chapters/{chapter_id}/board-texts")
async def update_board_texts(
    request: Request,
    chapter_id: str,
    texts: Annotated[dict[str, str], Body()],
) -> dict[str, Any]:
    """提交用户修正的板块标准文字（board_index -> 标准文字）。

    保存到章节记录中的 board_learning_samples 字段，同时保留原始自动生成文本，
    作为后续自学习样本库。并触发 rill 自学习回灌：对章节执行 shadow 评估，
    将「板块文字是否被人工修正」作为反馈写入 rill，供模型学习板块文字生成质量。
    """
    root = _workspace(request)
    record = _chapter_record(root, chapter_id)
    boards = record.get("boards", [])
    samples = record.setdefault(_BOARD_LEARNING_KEY, {})
    sample_dir = root / "board-samples"
    sample_file = sample_dir / f"{chapter_id}.json"
    persisted: dict[str, Any] = {}
    if sample_file.is_file():
        try:
            persisted = json.loads(sample_file.read_text(encoding="utf-8"))
        except Exception:
            persisted = {}
    # AI 草稿：用户提交后即视为「已学」，从草稿库中移除
    drafts = _load_board_drafts(root, chapter_id)
    submitted_idx: list[str] = []
    corrected_count = 0  # 被人工修正（与引擎原文不同）的板块数
    for idx_str, user_text in texts.items():
        try:
            idx = int(idx_str)
        except (ValueError, TypeError):
            continue
        if idx < 0 or idx >= len(boards):
            continue
        board = boards[idx]
        original_text = board.get("content", "")
        entry = {
            "chapter_id": chapter_id,
            "board_index": idx,
            "board_type": board["board_type"],
            "title": board.get("title", ""),
            "page_index": board.get("page_index"),
            "element_ids": board.get("element_ids", []),
            "original_text": original_text,
            "corrected_text": user_text,
            "corrected_at": datetime.now(timezone.utc).isoformat(),
        }
        samples[idx_str] = entry
        persisted[idx_str] = entry
        submitted_idx.append(idx_str)
        if user_text.strip() != original_text.strip():
            corrected_count += 1
    # 覆盖板块 content 为修正文字（保留 engine_content 原文），使页面结构同步显示修正结果
    for idx_str in submitted_idx:
        idx = int(idx_str)
        if 0 <= idx < len(boards):
            board = boards[idx]
            if "engine_content" not in board:
                board["engine_content"] = board.get("content", "")
            board["content"] = samples[idx_str]["corrected_text"]

    # rill 自学习回灌：板块文字人工标注同样作为反馈写入 rill
    rill_iteration: dict[str, Any] = {
        "iteration": len(record.get("iterations", [])) + 1,
        "source": "board_text",
        "reviewed_at": datetime.now(timezone.utc).isoformat(),
        "correct_count": len(submitted_idx) - corrected_count,
        "wrong_count": corrected_count,
        "submitted_count": len(submitted_idx),
        "feedback": None,
    }
    rill_service = _svc(request, "rill_service")
    try:
        evaluation = await run_in_threadpool(
            rill_service.evaluate,
            record.get("parse_run_id") or "",
            structure_id=record.get("structure_id"),
            domain_result_id=record.get("domain_result_id"),
        )
        feedback = ShadowFeedbackInput(
            evaluation_id=evaluation.evaluation_id,
            actual_action=ShadowAction.HUMAN_REVIEW,
            decision_correct=(corrected_count == 0),
            error_scope="textbook.board_text",
            error_type="corrected" if corrected_count else "ok",
            severity=FeedbackSeverity.P0 if corrected_count else FeedbackSeverity.P2,
            human_edit_seconds=0.0,
            eligible_for_training=True,
            outcome_time_ms=0,
        )
        rill_iteration["feedback"] = (
            await run_in_threadpool(rill_service.feedback, feedback)
        ).model_dump(mode="json")
    except Exception as exc:  # 自学习失败不应阻断标注提交
        rill_iteration["feedback_error"] = str(exc)

    record.setdefault("iterations", []).append(rill_iteration)
    _commit_chapter(root, chapter_id, record)
    sample_dir.mkdir(parents=True, exist_ok=True)
    sample_file.write_text(
        json.dumps(persisted, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    if drafts:
        changed = False
        for idx_str in submitted_idx:
            if idx_str in drafts:
                del drafts[idx_str]
                changed = True
        if changed:
            _save_board_drafts(root, chapter_id, drafts)
    return {
        "success": True,
        "saved_count": len(samples),
        "rill": {
            "evaluated": rill_iteration.get("feedback") is not None,
            "iteration": rill_iteration,
        },
    }


@router.get("/chapters/{chapter_id}/boards")
async def get_board_texts(
    request: Request,
    chapter_id: str,
) -> dict[str, Any]:
    """返回板块列表及已保存的标准文字（供前端标注界面）、以及学习样本状态。

    每个板块附带涉及页面列表 pages（page_index），供前端逐页展示裁剪图。
    """
    record = _chapter_record(_workspace(request), chapter_id)
    _enrich_annotation_bbox(request, record)
    samples = record.get(_BOARD_LEARNING_KEY, {})
    drafts = _load_board_drafts(_workspace(request), chapter_id)

    # 为每个板块补充涉及页面列表（跨页板块可多页）
    boards = record.get("boards", [])
    parse_run_id = record.get("parse_run_id")
    if parse_run_id and boards:
        try:
            result = _svc(request, "orchestrator").store.read_result(parse_run_id)
            elements_by_id = {e.element_id: e for e in result.document.elements}
            pages_by_id = {p.page_id: p for p in result.document.pages}
            for board in boards:
                page_indexes: list[int] = []
                for eid in board.get("element_ids", []):
                    el = elements_by_id.get(eid)
                    if el is None:
                        continue
                    pg = pages_by_id.get(getattr(el, "page_id", ""))
                    if pg is None:
                        continue
                    pi = getattr(pg, "index", None)
                    if isinstance(pi, int) and pi not in page_indexes:
                        page_indexes.append(pi)
                page_indexes.sort()
                board["pages"] = page_indexes
        except Exception:
            pass

    # 用修正文字覆盖板块 content（保留 engine_content 原文），供页面结构与标注视图统一展示
    corrected_texts = {k: v.get("corrected_text", "") for k, v in samples.items()}
    for idx_str, text in corrected_texts.items():
        if not text:
            continue
        try:
            idx = int(idx_str)
        except (ValueError, TypeError):
            continue
        if 0 <= idx < len(boards):
            board = boards[idx]
            if "engine_content" not in board:
                board["engine_content"] = board.get("content", "")
            board["content"] = text

    # AI 草稿：仅提供给「尚无人工修正」的板块（人工已提交的板块不重复给出草稿）
    board_drafts: dict[str, str] = {}
    for idx_str, entry in drafts.items():
        if idx_str in corrected_texts and corrected_texts[idx_str]:
            continue
        draft_text = entry.get("draft_text", "")
        if draft_text:
            board_drafts[idx_str] = draft_text

    return {
        "boards": boards,
        "board_texts": corrected_texts,
        "board_drafts": board_drafts,
        "learning_samples": samples,
    }


@router.get("/chapters/{chapter_id}/boards/{board_index}/crop")
async def chapter_board_crop_image(
    request: Request,
    chapter_id: str,
    board_index: int,
    page_index: Annotated[int | None, Query()] = None,
    padding: Annotated[float, Query()] = 0.02,
) -> Response:
    """返回板块在指定页上的裁剪区域图片。

    计算该板块在该页的元素外接矩形，从页面渲染图中裁剪出该区域返回。
    padding 为归一化扩充边距（默认 0.02），避免文字紧贴边缘。
    """
    root = _workspace(request)
    record = _chapter_record(root, chapter_id)
    boards = record.get("boards", [])
    if board_index < 0 or board_index >= len(boards):
        raise HTTPException(status_code=404, detail="board_index out of range")
    board = boards[board_index]

    parse_run_id = record.get("parse_run_id")
    if not parse_run_id:
        raise HTTPException(status_code=503, detail="parse_run_id missing")
    try:
        result = _svc(request, "orchestrator").store.read_result(parse_run_id)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"cannot read parse run: {exc}") from exc

    elements_by_id = {e.element_id: e for e in result.document.elements}
    pages_by_id = {p.page_id: p for p in result.document.pages}

    # 收集该板块在该页的元素 bbox
    page_bboxes: dict[str, list[tuple[float, float, float, float]]] = {}
    for eid in board.get("element_ids", []):
        el = elements_by_id.get(eid)
        if el is None:
            continue
        bb = getattr(el, "bbox", None)
        if bb is None:
            continue
        pid = getattr(el, "page_id", "")
        page_bboxes.setdefault(pid, []).append((bb.x1, bb.y1, bb.x2, bb.y2))

    if not page_bboxes:
        raise HTTPException(status_code=404, detail="no element bbox found for this board")

    # 如果指定了 page_index，只返回该页的裁剪
    if page_index is not None:
        target_pid = None
        for pid, pg in pages_by_id.items():
            if getattr(pg, "index", None) == page_index:
                target_pid = pid
                break
        if target_pid is None or target_pid not in page_bboxes:
            raise HTTPException(status_code=404, detail=f"page_index {page_index} not in this board")
        page_bboxes = {target_pid: page_bboxes[target_pid]}

    # 选择第一页（对于多页板，默认返回第一页）
    page_ids = sorted(page_bboxes.keys(), key=lambda pid: getattr(pages_by_id.get(pid), "index", 0) or 0)
    target_pid = page_ids[0]
    bb_list = page_bboxes[target_pid]

    x1 = max(0.0, min(b[0] for b in bb_list) - padding)
    y1 = max(0.0, min(b[1] for b in bb_list) - padding)
    x2 = min(1.0, max(b[2] for b in bb_list) + padding)
    y2 = min(1.0, max(b[3] for b in bb_list) + padding)

    pg = pages_by_id.get(target_pid)
    page_w = getattr(pg, "width", 541.417) if pg is not None else 541.417
    page_h = getattr(pg, "height", 754.016) if pg is not None else 754.016

    px1 = int(x1 * page_w * 2)
    py1 = int(y1 * page_h * 2)
    px2 = int(x2 * page_w * 2)
    py2 = int(y2 * page_h * 2)

    source_ref = record.get("source_ref")
    if not source_ref:
        raise HTTPException(status_code=404, detail="source PDF missing")
    source_path = Path(request.app.state.settings.workspace) / source_ref
    if not source_path.is_file():
        raise HTTPException(status_code=404, detail="PDF file not found")

    physical_page = _page_range_start(record.get("page_range")) + getattr(pg, "index", 0)
    cache_dir = root / "chapters" / chapter_id / "pages"
    cache_file = cache_dir / f"{physical_page:04d}.png"

    if not cache_file.is_file():
        try:
            import fitz
        except ImportError as exc:
            raise HTTPException(status_code=503, detail="PyMuPDF not installed") from exc
        try:
            doc = fitz.open(source_path)
            if physical_page < 0 or physical_page >= doc.page_count:
                raise HTTPException(status_code=404, detail="page out of range")
            p = doc[physical_page]
            pix = p.get_pixmap(matrix=fitz.Matrix(2, 2))
            cache_dir.mkdir(parents=True, exist_ok=True)
            pix.save(str(cache_file))
            doc.close()
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"render page failed: {exc}") from exc

    try:
        from PIL import Image
        img = Image.open(cache_file)
        cropped = img.crop((px1, py1, px2, py2))
        buf = __import__("io").BytesIO()
        cropped.save(buf, format="PNG")
        return Response(
            content=buf.getvalue(),
            media_type="image/png",
            headers={"Cache-Control": "public, max-age=86400"},
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"crop failed: {exc}") from exc