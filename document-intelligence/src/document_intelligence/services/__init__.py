from __future__ import annotations

from typing import Any

from .ingestion import IngestionPolicy, detect_mime, ingest_bytes
from .orchestrator import ParseOrchestrator
from .store import ArtifactStore

_BOOTSTRAP_EXPORTS = {
    "build_document_family_service",
    "build_domain_pack_registry",
    "build_domain_review_service",
    "build_domain_runtime_service",
    "build_orchestrator",
    "build_rill_assist_service",
    "build_rill_shadow_service",
    "build_mlops_service",
    "build_production_qualification_service",
    "build_qualification_campaign_service",
    "build_registry",
    "build_structure_service",
    "build_visual_catalog_service",
}


def __getattr__(name: str) -> Any:
    if name in _BOOTSTRAP_EXPORTS:
        from . import bootstrap

        return getattr(bootstrap, name)
    raise AttributeError(name)


__all__ = [
    "ArtifactStore",
    "IngestionPolicy",
    "ParseOrchestrator",
    "build_document_family_service",
    "build_domain_pack_registry",
    "build_domain_review_service",
    "build_domain_runtime_service",
    "build_orchestrator",
    "build_rill_assist_service",
    "build_rill_shadow_service",
    "build_mlops_service",
    "build_production_qualification_service",
    "build_qualification_campaign_service",
    "build_registry",
    "build_structure_service",
    "build_visual_catalog_service",
    "detect_mime",
    "ingest_bytes",
]
