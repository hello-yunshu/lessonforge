"""视觉语义目录服务（先识别图标/角色，再解析板块）。

把「教材图标 / 卡通角色」的 Reviewed 视觉模板目录持久化到 workspace，
并在首次启动时用包内默认模板 seed。用户在前端编辑/上传图标后，通过
add_reviewed_template 回写，保证后续解析能真正调用图像匹配器锚定例题与角色，
同时保留用户编辑后的样式更新。

对外暴露：
- load_or_seed：加载已存在目录，否则从默认模板 seed
- catalog：底层 VisualSemanticCatalog（fail-closed 匹配）
- bridge：EducationVisualSemanticBridge（把匹配结果转成领域标注）
- add_reviewed_template：用户编辑图标后增量更新并持久化
"""
from __future__ import annotations

import json
import shutil
from dataclasses import replace
from pathlib import Path
from typing import Any

from document_intelligence.visual_semantics import (
    EducationVisualSemanticBridge,
    VisualSemanticCatalog,
)
from document_intelligence.visual_semantics.dialogue import DialogueRelationResolver

_DEFAULT_CATALOG = (
    Path(__file__).resolve().parent.parent / "visual_semantics" / "data"
    / "visual-semantic-catalog.json"
)


class VisualCatalogService:
    """持久化到 workspace 的视觉语义目录服务。"""

    def __init__(
        self,
        workspace: Path,
        *,
        default_catalog: Path | None = None,
        max_dhash_distance: int = 24,
        ambiguity_margin: int = 5,
        min_information_score: float = 0.08,
    ) -> None:
        self.root = workspace / "visual-semantic"
        self.root.mkdir(parents=True, exist_ok=True)
        self.catalog_path = self.root / "catalog.json"
        self._default_catalog = default_catalog or _DEFAULT_CATALOG
        self._max_dhash_distance = max_dhash_distance
        self._ambiguity_margin = ambiguity_margin
        self._min_information_score = min_information_score
        self.catalog = self._load_or_seed()
        self.bridge = EducationVisualSemanticBridge(
            self.catalog,
            DialogueRelationResolver(),
        )

    # ---------- 加载 / seed ----------
    def _load_or_seed(self) -> VisualSemanticCatalog:
        if self.catalog_path.is_file():
            try:
                return VisualSemanticCatalog.load(self.catalog_path)
            except Exception:
                # 损坏时就近重建，避免服务不可用
                pass
        source = self._default_catalog
        if source.is_file():
            shutil.copyfile(source, self.catalog_path)
            return VisualSemanticCatalog.load(self.catalog_path)
        empty = {
            "schema_version": 1,
            "matching": {
                "max_dhash_distance": self._max_dhash_distance,
                "ambiguity_margin": self._ambiguity_margin,
                "min_information_score": self._min_information_score,
            },
            "profiles": [],
        }
        (self.catalog_path).write_text(
            json.dumps(empty, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        return VisualSemanticCatalog.load(self.catalog_path)

    # ---------- 查询 / 匹配 ----------
    def profiles(self) -> list[dict[str, Any]]:
        return [p.to_mapping() for p in self.catalog.profiles]

    def catalog_mapping(self) -> dict[str, Any]:
        """返回完整目录（匹配配置 + 全部 profile），供前端编辑/回显。

        这是「资源库作为解析依据」的读写契约：前端展示与修改的都是这份数据，
        解析时同样基于 self.catalog（持久化于 catalog.json）做图像匹配。
        """
        return {
            "schema_version": 1,
            "matching": {
                "max_dhash_distance": self.catalog.max_dhash_distance,
                "ambiguity_margin": self.catalog.ambiguity_margin,
                "min_information_score": self.catalog.min_information_score,
            },
            "profiles": [p.to_mapping() for p in self.catalog.profiles],
        }

    def update_profile(
        self, semantic_id: str, fields: dict[str, Any]
    ) -> dict[str, Any]:
        """更新某个语义对象的可编辑元数据并持久化。

        支持字段：category / role_name / speaker_type / special_meaning / review_status。
        更新后重建 in-memory catalog 与 bridge，使后续解析立即使用新语义。
        图像（模板哈希）请走 add_reviewed_template。
        """
        from document_intelligence.visual_semantics.catalog import SemanticProfile

        updated: list[SemanticProfile] = []
        found = False
        for profile in self.catalog.profiles:
            if profile.semantic_id != semantic_id:
                updated.append(profile)
                continue
            found = True
            kwargs: dict[str, Any] = {}
            if "category" in fields:
                kwargs["category"] = str(fields["category"])
            if "role_name" in fields:
                kwargs["role_name"] = (
                    str(fields["role_name"]) if fields["role_name"] else None
                )
            if "speaker_type" in fields:
                kwargs["speaker_type"] = (
                    str(fields["speaker_type"]) if fields["speaker_type"] else None
                )
            if "special_meaning" in fields:
                kwargs["special_meaning"] = str(fields["special_meaning"])
            if "review_status" in fields:
                kwargs["review_status"] = str(fields["review_status"])
            updated.append(replace(profile, **kwargs))
        if not found:
            raise KeyError(semantic_id)
        rebuilt = VisualSemanticCatalog(
            updated,
            max_dhash_distance=self.catalog.max_dhash_distance,
            ambiguity_margin=self.catalog.ambiguity_margin,
            min_information_score=self.catalog.min_information_score,
        )
        rebuilt.dump(self.catalog_path)
        self.catalog = rebuilt
        self.bridge = EducationVisualSemanticBridge(
            rebuilt, DialogueRelationResolver()
        )
        return rebuilt.profile(semantic_id).to_mapping()

    def reload_from_default(self) -> dict[str, Any]:
        """丢弃运行时目录改动，从包内默认模板重新 seed（误改后回滚/手动同步）。"""
        if self._default_catalog.is_file():
            shutil.copyfile(self._default_catalog, self.catalog_path)
        self.catalog = self._load_or_seed()
        self.bridge = EducationVisualSemanticBridge(
            self.catalog, DialogueRelationResolver()
        )
        return self.catalog_mapping()

    def match(self, image_bytes: bytes) -> dict[str, Any]:
        result = self.catalog.match(image_bytes)
        return {
            "status": result.status,
            "semantic_id": result.semantic_id,
            "confidence": result.confidence,
            "method": result.method,
            "evidence": result.evidence,
        }

    def identify_character(
        self, observation: Any, image_bytes: bytes
    ) -> dict[str, Any]:
        return self.bridge.identify_character(observation, image_bytes)

    # ---------- 用户编辑后的更新（保留样式） ----------
    def add_reviewed_template(self, semantic_id: str, image_bytes: bytes) -> dict[str, Any]:
        """用户上传/编辑某个语义对象的图像后，把该图加入 Reviewed 模板并持久化。"""
        updated = self.catalog.add_reviewed_template(semantic_id, image_bytes)
        updated.dump(self.catalog_path)
        self.catalog = updated
        self.bridge = EducationVisualSemanticBridge(
            updated, DialogueRelationResolver()
        )
        return updated.profile(semantic_id).to_mapping()

    def reload(self) -> None:
        self.catalog = self._load_or_seed()
        self.bridge = EducationVisualSemanticBridge(
            self.catalog, DialogueRelationResolver()
        )