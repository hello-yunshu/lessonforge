from __future__ import annotations

from pathlib import Path

from document_intelligence.domain_pack_sdk import load_domain_pack

ROOT = Path(__file__).resolve().parents[2]


def test_generic_domain_pack_loads_without_core_pollution() -> None:
    pack = load_domain_pack(ROOT / "domain-packs" / "generic-document")
    assert pack.manifest.id == "generic-document"
    assert pack.manifest.core_schema == ">=1.1,<2.0"
    assert "section" in pack.ontology.object_types
