from __future__ import annotations

import hashlib
from enum import StrEnum
from pathlib import Path
from typing import Any

import yaml
from packaging.version import Version

from document_intelligence.domain_pack_sdk.models import DomainPackManifest
from document_intelligence.schema import validate_safe_id


class DomainPackTemplateKind(StrEnum):
    BASIC = "basic"
    CLASSIFICATION = "classification"
    RELATION_HEAVY = "relation-heavy"


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_yaml(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(payload, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )


def create_domain_pack_scaffold(
    target_parent: Path,
    *,
    pack_id: str,
    version: str = "0.1.0",
    template: DomainPackTemplateKind = DomainPackTemplateKind.CLASSIFICATION,
    include_family_profile: bool = True,
) -> Path:
    validate_safe_id(pack_id, field_name="pack_id")
    if not pack_id[0].islower() or any(
        character not in "abcdefghijklmnopqrstuvwxyz0123456789-" for character in pack_id
    ):
        raise ValueError("pack_id must use lowercase ASCII letters, digits and hyphens")
    parsed_version = Version(version)
    if parsed_version.local is not None or parsed_version.epoch != 0:
        raise ValueError("domain pack scaffold version cannot use local or epoch identifiers")
    parent = target_parent.resolve()
    if parent.is_symlink():
        raise ValueError("domain pack scaffold parent cannot be a symlink")
    parent.mkdir(parents=True, exist_ok=True)
    target = parent / pack_id
    if target.exists():
        raise FileExistsError(f"domain pack scaffold already exists: {target}")
    target.mkdir()

    object_types: dict[str, Any] = {
        "domain_section": {
            "base_types": ["heading"],
            "description": "Replace with a domain-specific section type.",
        },
        "domain_content": {
            "base_types": ["text", "list", "callout"],
            "description": "Replace with a domain-specific content type.",
        },
    }
    relation_types: dict[str, Any] = {}
    relation_rules: list[dict[str, Any]] = []
    if template == DomainPackTemplateKind.RELATION_HEAVY:
        relation_types["domain_association"] = {
            "base_type": "associated_with",
            "source_types": ["domain_section"],
            "target_types": ["domain_content"],
            "description": "Replace with a domain-specific relation.",
        }
        relation_rules.append(
            {
                "id": f"{pack_id}-association",
                "domain_type": "domain_association",
                "source_domain_types": ["domain_section"],
                "target_domain_types": ["domain_content"],
                "base_relation_types": ["associated_with", "precedes"],
                "max_reading_distance": 4,
                "confidence": 0.75,
            }
        )

    _write_yaml(
        target / "ontology.yaml",
        {"version": 1, "object_types": object_types, "relation_types": relation_types},
    )
    _write_yaml(
        target / "labels.yaml",
        {
            "version": 1,
            "labels": {
                "domain_section": {"en": "Domain section"},
                "domain_content": {"en": "Domain content"},
            },
        },
    )
    object_rules: list[dict[str, Any]] = [
        {
            "id": f"{pack_id}-section",
            "domain_type": "domain_section",
            "base_types": ["heading"],
            "confidence": 0.80,
            "stop_on_match": True,
        }
    ]
    if template != DomainPackTemplateKind.BASIC:
        object_rules.append(
            {
                "id": f"{pack_id}-content",
                "domain_type": "domain_content",
                "base_types": ["text", "list", "callout"],
                "require_text": True,
                "confidence": 0.75,
                "stop_on_match": True,
            }
        )
    _write_yaml(
        target / "rules" / "main.yaml",
        {"version": 1, "object_rules": object_rules, "relation_rules": relation_rules},
    )
    _write_yaml(
        target / "validators" / "main.yaml",
        {
            "version": 1,
            "required_types": [
                {
                    "code": f"{pack_id.upper().replace('-', '_')}_NO_DOMAIN_CONTENT",
                    "domain_types": ["domain_section", "domain_content"],
                    "min_count": 1,
                    "severity": "warning",
                    "message": (
                        "No domain content was identified; retain the generic result "
                        "and review the pack rules."
                    ),
                }
            ],
            "relation_endpoints": [],
        },
    )
    _write_yaml(
        target / "review" / "labelu.yaml",
        {
            "version": 1,
            "adapter": "labelu-json-v1",
            "object_labels": ["domain_section", "domain_content"],
            "relation_labels": list(relation_types),
        },
    )
    entrypoints = {
        "rules": "rules/main.yaml",
        "validators": "validators/main.yaml",
        "review": "review/labelu.yaml",
    }
    capabilities = [
        "object-classification",
        "validation",
        "review-export",
    ]
    permissions = list(capabilities)
    if relation_types:
        capabilities.append("relation-recovery")
        permissions.append("relation-recovery")
    if include_family_profile:
        _write_yaml(
            target / "family.yaml",
            {
                "version": 1,
                "family_id": pack_id,
                "aliases": [],
                "supported_mime_types": ["application/pdf", "image/png", "image/jpeg"],
                "priority": 100,
                "min_score": 0.60,
                "min_margin": 0.10,
                "min_positive_cues": 1,
                "required_base_types": {},
                "positive_cues": [
                    {
                        "id": f"{pack_id}-family-cue",
                        "terms": ["REPLACE_WITH_DOMAIN_CUE"],
                        "weight": 1.0,
                        "match_mode": "contains",
                        "base_types": ["heading", "text"],
                        "required": True,
                    }
                ],
                "negative_cues": [],
            },
        )
        entrypoints["family"] = "family.yaml"
        capabilities.append("family-detection-metadata")
        permissions.append("family-detection-metadata")

    files = {
        path.relative_to(target).as_posix(): _sha256_file(path)
        for path in sorted(target.rglob("*"))
        if path.is_file()
    }
    manifest = DomainPackManifest(
        id=pack_id,
        version=str(parsed_version),
        core_schema=">=1.1,<2.0",
        engine=">=0.8,<1.0",
        supported_languages=[],
        capabilities=capabilities,
        permissions=permissions,
        entrypoints=entrypoints,
        file_digests=files,
    )
    _write_yaml(target / "manifest.yaml", manifest.model_dump(mode="json"))
    return target
