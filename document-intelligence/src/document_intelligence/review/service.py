from __future__ import annotations

import errno
import hashlib
import json
import os
import tempfile
from collections import defaultdict
from pathlib import Path
from typing import Any

from document_intelligence.domain_runtime import DomainRuntimeService
from document_intelligence.exceptions import DomainReviewError
from document_intelligence.parser_sdk.utils import stable_id
from document_intelligence.schema import validate_safe_id
from document_intelligence.review.models import (
    LabelUObject,
    LabelURelation,
    LabelUReviewExport,
    LabelUReviewSubmission,
    LabelUTask,
    ReviewRecord,
)
from document_intelligence.services.store import ArtifactStore
from document_intelligence.structure import StructureService


class DomainReviewService:
    def __init__(
        self,
        workspace: Path,
        artifact_store: ArtifactStore,
        structure_service: StructureService,
        domain_service: DomainRuntimeService,
    ) -> None:
        self.root = workspace / "domain-reviews"
        if self.root.is_symlink():
            raise ValueError("domain review namespace cannot be a symlink")
        self.root.mkdir(parents=True, exist_ok=True)
        self.artifact_store = artifact_store
        self.structure_service = structure_service
        self.domain_service = domain_service

    def export_labelu(self, domain_result_id: str) -> LabelUReviewExport:
        result = self.domain_service.get(domain_result_id)
        pack = self.domain_service.registry.load(
            result.pack_id, result.pack_version, enforce_compatibility=False
        )
        if "review-export" not in pack.manifest.permissions:
            raise DomainReviewError("domain pack does not permit review export")
        export_id = stable_id(
            "reviewexport", result.domain_result_id, result.semantic_digest(), pack.content_digest
        )
        try:
            existing = LabelUReviewExport.model_validate(self._read_record("exports", export_id))
        except FileNotFoundError:
            existing = None
        if existing is not None:
            if (
                existing.domain_result_id != result.domain_result_id
                or existing.source_domain_digest != result.semantic_digest()
            ):
                raise DomainReviewError("stored review export identity is inconsistent")
            return existing

        parsed = self.artifact_store.read_result(result.parse_run_id)
        element_by_id = {item.element_id: item for item in parsed.document.elements}
        annotations_by_page: dict[str, list[LabelUObject]] = defaultdict(list)
        annotation_id_by_element: dict[str, str] = {}
        for annotation in result.annotations:
            element = element_by_id[annotation.element_id]
            annotation_id_by_element[annotation.element_id] = annotation.annotation_id
            annotations_by_page[element.page_id].append(
                LabelUObject(
                    id=annotation.annotation_id,
                    element_id=annotation.element_id,
                    label=annotation.domain_type,
                    bbox=element.bbox,
                    text=element.content.text,
                    confidence=annotation.confidence,
                    evidence_ids=annotation.evidence_ids,
                )
            )
        relations_by_page: dict[str, list[LabelURelation]] = defaultdict(list)
        cross_page_relations: list[LabelURelation] = []
        for relation in result.relations:
            source = element_by_id[relation.source_id]
            target = element_by_id[relation.target_id]
            exported_relation = LabelURelation(
                id=relation.relation_id,
                source_id=annotation_id_by_element[relation.source_id],
                target_id=annotation_id_by_element[relation.target_id],
                label=relation.domain_type,
                confidence=relation.confidence,
                evidence_ids=relation.evidence_ids,
            )
            if source.page_id != target.page_id:
                cross_page_relations.append(exported_relation)
            else:
                relations_by_page[source.page_id].append(exported_relation)
        tasks = [
            LabelUTask(
                task_id=stable_id("reviewtask", result.domain_result_id, page.page_id),
                page_id=page.page_id,
                image_ref=page.image_ref,
                objects=sorted(annotations_by_page[page.page_id], key=lambda item: item.id),
                relations=sorted(relations_by_page[page.page_id], key=lambda item: item.id),
            )
            for page in parsed.document.pages
        ]
        export = LabelUReviewExport(
            export_id=export_id,
            domain_result_id=result.domain_result_id,
            source_domain_digest=result.semantic_digest(),
            pack_id=result.pack_id,
            pack_version=result.pack_version,
            object_labels=pack.review.object_labels,
            relation_labels=pack.review.relation_labels,
            tasks=tasks,
            cross_page_relations=sorted(cross_page_relations, key=lambda item: item.id),
        )
        self._commit_record("exports", export_id, export.model_dump(mode="json"))
        return export

    def submit_labelu(self, submission: LabelUReviewSubmission) -> ReviewRecord:
        result = self.domain_service.get(submission.domain_result_id)
        if result.semantic_digest() != submission.source_domain_digest:
            raise DomainReviewError("review submission is stale relative to the domain result")
        try:
            export = LabelUReviewExport.model_validate(
                self._read_record("exports", submission.export_id)
            )
        except FileNotFoundError as exc:
            raise DomainReviewError("review export does not exist") from exc
        if export.domain_result_id != submission.domain_result_id:
            raise DomainReviewError("review submission references a different export result")
        if export.source_domain_digest != submission.source_domain_digest:
            raise DomainReviewError("review submission digest differs from its review export")
        pack = self.domain_service.registry.load(
            result.pack_id, result.pack_version, enforce_compatibility=False
        )
        allowed_objects = set(pack.review.object_labels)
        allowed_relations = set(pack.review.relation_labels)
        source_elements = {
            item.element_id
            for item in self.artifact_store.read_result(result.parse_run_id).document.elements
        }
        for item in submission.objects:
            if item.element_id not in source_elements:
                raise DomainReviewError("review references an unknown source element")
            if not set(item.labels).issubset(allowed_objects):
                raise DomainReviewError("review uses object labels not declared by the domain pack")
        for item in submission.relations:
            if item.source_id not in source_elements or item.target_id not in source_elements:
                raise DomainReviewError("review relation references unknown source elements")
            if item.label not in allowed_relations:
                raise DomainReviewError(
                    "review uses relation labels not declared by the domain pack"
                )
        review_id = stable_id(
            "review",
            submission.export_id,
            submission.domain_result_id,
            submission.source_domain_digest,
            submission.reviewer,
            submission.review_level,
            submission.reason,
            submission.submitted_at.isoformat(),
        )
        record = ReviewRecord(
            review_id=review_id,
            export_id=submission.export_id,
            domain_result_id=submission.domain_result_id,
            source_domain_digest=submission.source_domain_digest,
            reviewer=submission.reviewer,
            review_level=submission.review_level,
            reason=submission.reason,
            objects=submission.objects,
            relations=submission.relations,
            submitted_at=submission.submitted_at,
        )
        self._commit_record("submissions", review_id, record.model_dump(mode="json"))
        return record

    def get_review(self, review_id: str) -> ReviewRecord:
        record = ReviewRecord.model_validate(self._read_record("submissions", review_id))
        result = self.domain_service.get(record.domain_result_id)
        if result.semantic_digest() != record.source_domain_digest:
            raise DomainReviewError("stored review is stale relative to its domain result")
        export = LabelUReviewExport.model_validate(
            self._read_record("exports", record.export_id)
        )
        if export.source_domain_digest != record.source_domain_digest:
            raise DomainReviewError("stored review differs from its source export")
        return record

    def _commit_record(self, namespace: str, record_id: str, payload: object) -> None:
        record_id = validate_safe_id(record_id, field_name="review_record_id")
        if namespace not in {"exports", "submissions"}:
            raise DomainReviewError("unsupported review record namespace")
        namespace_root = self.root / namespace
        namespace_root.mkdir(parents=True, exist_ok=True)
        directory = namespace_root / record_id
        if directory.exists():
            existing = self._read_record(namespace, record_id)
            if existing != payload:
                raise DomainReviewError("review record identifier contains different content")
            return
        staged = Path(tempfile.mkdtemp(prefix=f".{record_id}.", dir=namespace_root))
        try:
            result_path = staged / "result.json"
            self._atomic_json(result_path, payload)
            self._atomic_json(
                staged / "manifest.json",
                {
                    "version": 1,
                    "record_id": record_id,
                    "result_sha256": hashlib.sha256(result_path.read_bytes()).hexdigest(),
                },
            )
            try:
                os.rename(staged, directory)
            except OSError as exc:
                if exc.errno not in {errno.EEXIST, errno.ENOTEMPTY} and not directory.exists():
                    raise
                self._remove_tree(staged)
                existing = self._read_record(namespace, record_id)
                if existing != payload:
                    raise DomainReviewError(
                        "concurrent review record commit produced different content"
                    ) from exc
        except Exception:
            self._remove_tree(staged)
            raise

    def _read_record(self, namespace: str, record_id: str) -> dict[str, Any]:
        record_id = validate_safe_id(record_id, field_name="review_record_id")
        if namespace not in {"exports", "submissions"}:
            raise DomainReviewError("unsupported review record namespace")
        namespace_root = self.root / namespace
        if namespace_root.is_symlink():
            raise DomainReviewError("review record namespace is unsafe")
        directory = namespace_root / record_id
        if directory.is_symlink() or not directory.is_dir():
            raise FileNotFoundError(record_id)
        result_path = directory / "result.json"
        manifest_path = directory / "manifest.json"
        if (
            result_path.is_symlink()
            or manifest_path.is_symlink()
            or not result_path.is_file()
            or not manifest_path.is_file()
        ):
            raise DomainReviewError("review record artifacts are missing or unsafe")
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            if manifest.get("version") != 1 or manifest.get("record_id") != record_id:
                raise ValueError("review record manifest is invalid")
            actual_digest = hashlib.sha256(result_path.read_bytes()).hexdigest()
            if manifest.get("result_sha256") != actual_digest:
                raise ValueError("review record digest verification failed")
            payload = json.loads(result_path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("review record payload must be an object")
            return payload
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            raise DomainReviewError(f"review record failed integrity verification: {exc}") from exc

    @staticmethod
    def _atomic_json(path: Path, payload: object) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        encoded = (
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        ).encode()
        fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(encoded)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_name, path)
        except Exception:
            Path(temp_name).unlink(missing_ok=True)
            raise

    @classmethod
    def _remove_tree(cls, path: Path) -> None:
        if not path.exists():
            return
        if path.is_file() or path.is_symlink():
            path.unlink(missing_ok=True)
            return
        for child in path.iterdir():
            cls._remove_tree(child)
        path.rmdir()
