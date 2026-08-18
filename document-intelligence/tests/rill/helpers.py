from __future__ import annotations

from pathlib import Path

from document_intelligence.rill.service import RillShadowService
from document_intelligence.services import (
    build_domain_runtime_service,
    build_orchestrator,
    build_rill_shadow_service,
    build_structure_service,
)
from tests.domain_runtime.helpers import build_parser_result


def build_committed_run(settings) -> tuple[str, str]:
    orchestrator = build_orchestrator(settings)
    request, result = build_parser_result()
    orchestrator.store.commit_success(request, result)
    structures = build_structure_service(settings, artifact_store=orchestrator.store)
    structure = structures.recover_run(result.run.parse_run_id)
    orchestrator.registry.close()
    return result.run.parse_run_id, structure.structure_id


def build_reference_service(settings) -> tuple[RillShadowService, str, str]:
    settings = settings.model_copy(
        update={
            "rill_shadow_backend": "reference",
            "rill_reference_backend_allowed": True,
            "enable_rill_shadow_writes": True,
        }
    )
    parse_run_id, structure_id = build_committed_run(settings)
    service = build_rill_shadow_service(settings)
    return service, parse_run_id, structure_id
