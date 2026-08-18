from __future__ import annotations

from pathlib import Path

from document_intelligence.domain_runtime import DomainPackRegistry


def test_builtin_catalog_and_install_are_complete(tmp_path: Path) -> None:
    registry = DomainPackRegistry(tmp_path / "var", engine_version="0.8.0")
    records = registry.list_builtin_records()
    assert {item.pack_id for item in records} == {
        "generic-document",
        "education-content",
        "examination-paper",
        "academic-paper",
        "legal-contract",
        "technical-manual",
    }
    family_records = [item for item in records if item.has_family_profile]
    assert len(family_records) == 5
    installed = registry.install_builtin("technical-manual")
    assert installed.pack_id == "technical-manual"
    assert installed.has_family_profile is True
    assert registry.activate(installed.pack_id, installed.version).active is True
