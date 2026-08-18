from __future__ import annotations

from dataclasses import dataclass

import pytest

from document_intelligence.exceptions import ParserUnavailableError, RunStoreCorruptError
from document_intelligence.parser_sdk import ParserRegistry
from document_intelligence.parsers import NativePdfParser
from document_intelligence.schema import ParserHealth, ParseRequest
from document_intelligence.services import ArtifactStore, ParseOrchestrator


@dataclass
class FailingParser:
    parser_id: str = "failing"
    priority: int = 10

    def health(self) -> ParserHealth:
        return ParserHealth(
            parser_id=self.parser_id,
            available=True,
            enabled=True,
            version="1",
            artifact_digest="a" * 64,
        )

    def supports(self, request: ParseRequest) -> bool:
        return True

    def parse(self, request: ParseRequest):
        raise RuntimeError("synthetic failure")


def test_success_is_committed_atomically_and_readable(fixtures_dir, tmp_path) -> None:
    store = ArtifactStore(tmp_path / "var")
    orchestrator = ParseOrchestrator(ParserRegistry([NativePdfParser()]), store)
    path = fixtures_dir / "native_text.pdf"
    request = ParseRequest(
        filename=path.name,
        mime_type="application/pdf",
        content=path.read_bytes(),
        parser_id="native-pdf",
    )
    result = orchestrator.parse(request)
    loaded = store.read_result(result.run.parse_run_id)
    assert loaded.run.semantic_output_digest == result.run.semantic_output_digest
    assert loaded.document.evidence[0].raw_output_ref is not None
    assert store.standard_snapshot() == []


def test_failure_never_modifies_standard_results(tmp_path) -> None:
    store = ArtifactStore(tmp_path / "var")
    marker = store.standard_dir / "protected.json"
    marker.write_text('{"protected": true}\n', encoding="utf-8")
    snapshot = store.standard_snapshot()
    orchestrator = ParseOrchestrator(ParserRegistry([FailingParser()]), store)
    request = ParseRequest(
        filename="x.pdf", mime_type="application/pdf", content=b"%PDF-invalid", parser_id="failing"
    )
    with pytest.raises(RuntimeError, match="synthetic"):
        orchestrator.parse(request)
    assert store.standard_snapshot() == snapshot
    assert marker.read_text(encoding="utf-8") == '{"protected": true}\n'
    assert list(store.runs_dir.glob("*.failed.json"))


def test_auto_route_reports_no_parser_for_image_when_external_disabled(tmp_path) -> None:
    store = ArtifactStore(tmp_path / "var")
    orchestrator = ParseOrchestrator(ParserRegistry([NativePdfParser()]), store)
    request = ParseRequest(filename="x.png", mime_type="image/png", content=b"\x89PNG\r\n\x1a\n")
    with pytest.raises(ParserUnavailableError):
        orchestrator.parse(request)


@dataclass
class SuccessfulSecondary:
    result: object
    parser_id: str = "secondary"
    priority: int = 20

    def health(self) -> ParserHealth:
        return ParserHealth(
            parser_id=self.parser_id,
            available=True,
            enabled=True,
            version="1",
            artifact_digest="b" * 64,
        )

    def supports(self, request: ParseRequest) -> bool:
        return True

    def parse(self, request: ParseRequest):
        payload = self.result.model_dump(mode="python")
        new_run_id = f"run_secondary_{request.sha256[:16]}"
        payload["run"]["parse_run_id"] = new_run_id
        payload["document"]["parse_run_id"] = new_run_id
        payload["run"]["parser_id"] = self.parser_id
        payload["run"]["parser_version"] = "1"
        payload["run"]["parser_digest"] = "b" * 64
        payload["run"]["warnings"] = []
        for evidence in payload["document"]["evidence"]:
            evidence["parse_run_id"] = new_run_id
            evidence["producer"] = self.parser_id
            evidence["producer_version"] = "1"
            evidence["model_digest"] = "b" * 64
        from document_intelligence.schema import ParserResult, ParsedDocument

        document = ParsedDocument.model_validate(payload["document"])
        payload["run"]["semantic_output_digest"] = document.semantic_digest()
        payload["document"] = document
        return ParserResult.model_validate(payload)



def test_auto_route_uses_secondary_when_native_has_no_text(fixtures_dir, tmp_path) -> None:
    path = fixtures_dir / "scanned_image.pdf"
    request = ParseRequest(
        filename=path.name,
        mime_type="application/pdf",
        content=path.read_bytes(),
    )
    native_result = NativePdfParser().parse(request)
    secondary = SuccessfulSecondary(native_result)
    store = ArtifactStore(tmp_path / "var")
    registry = ParserRegistry([NativePdfParser(), secondary])
    orchestrator = ParseOrchestrator(registry, store)
    result = orchestrator.parse(request)
    assert result.run.parser_id == "secondary"
    assert not result.run.warnings
    assert len([p for p in store.runs_dir.iterdir() if p.is_dir()]) == 2


def test_store_retains_source_and_assets(fixtures_dir, tmp_path) -> None:
    path = fixtures_dir / "mixed_layout.pdf"
    request = ParseRequest(
        filename=path.name,
        mime_type="application/pdf",
        content=path.read_bytes(),
        parser_id="native-pdf",
    )
    store = ArtifactStore(tmp_path / "var")
    result = ParseOrchestrator(ParserRegistry([NativePdfParser()]), store).parse(request)
    assert result.document.source.source_ref
    assert store.read_source(result.document.source.source_ref) == path.read_bytes()
    image_elements = [item for item in result.document.elements if item.content.asset_ref]
    assert image_elements
    assert store.resolve_asset(image_elements[0].content.asset_ref).is_file()


def test_store_rejects_unsafe_run_identifier(fixtures_dir, tmp_path) -> None:
    path = fixtures_dir / "native_text.pdf"
    request = ParseRequest(
        filename=path.name,
        mime_type="application/pdf",
        content=path.read_bytes(),
    )
    result = NativePdfParser().parse(request)
    payload = result.model_dump(mode="python")
    payload["run"]["parse_run_id"] = ".."
    payload["document"]["parse_run_id"] = ".."
    for evidence in payload["document"]["evidence"]:
        evidence["parse_run_id"] = ".."
    from pydantic import ValidationError
    from document_intelligence.schema import ParserResult

    with pytest.raises(ValidationError):
        ParserResult.model_validate(payload)


def test_orchestrator_rejects_parser_output_over_global_element_limit(
    fixtures_dir, tmp_path
) -> None:
    path = fixtures_dir / "native_text.pdf"
    request = ParseRequest(
        filename=path.name,
        mime_type="application/pdf",
        content=path.read_bytes(),
        parser_id="native-pdf",
    )
    orchestrator = ParseOrchestrator(
        ParserRegistry([NativePdfParser()]),
        ArtifactStore(tmp_path / "var"),
        max_document_elements=1,
    )
    with pytest.raises(ValueError, match="element count exceeds limit"):
        orchestrator.parse(request)


def test_store_detects_tampered_committed_run(fixtures_dir, tmp_path) -> None:
    path = fixtures_dir / "native_text.pdf"
    request = ParseRequest(
        filename=path.name,
        mime_type="application/pdf",
        content=path.read_bytes(),
        parser_id="native-pdf",
    )
    store = ArtifactStore(tmp_path / "var")
    result = ParseOrchestrator(ParserRegistry([NativePdfParser()]), store).parse(request)
    run_path = store.runs_dir / result.run.parse_run_id / "run.json"
    run_path.write_text(run_path.read_text(encoding="utf-8") + " ", encoding="utf-8")
    with pytest.raises(RunStoreCorruptError, match="digest mismatch"):
        store.read_result(result.run.parse_run_id)


def test_repeated_failures_are_recorded_as_distinct_attempts(tmp_path) -> None:
    store = ArtifactStore(tmp_path / "var")
    orchestrator = ParseOrchestrator(ParserRegistry([FailingParser()]), store)
    request = ParseRequest(
        filename="x.pdf",
        mime_type="application/pdf",
        content=b"%PDF-invalid",
        parser_id="failing",
    )
    for _ in range(2):
        with pytest.raises(RuntimeError, match="synthetic failure"):
            orchestrator.parse(request)
    assert len(list(store.runs_dir.glob("*.failed.json"))) == 2


def test_store_detects_tampered_retained_source(fixtures_dir, tmp_path) -> None:
    path = fixtures_dir / "native_text.pdf"
    request = ParseRequest(
        filename=path.name,
        mime_type="application/pdf",
        content=path.read_bytes(),
        parser_id="native-pdf",
    )
    store = ArtifactStore(tmp_path / "var")
    result = ParseOrchestrator(ParserRegistry([NativePdfParser()]), store).parse(request)
    source_path = store.workspace / result.document.source.source_ref
    source_path.write_bytes(source_path.read_bytes() + b"tamper")
    with pytest.raises(RunStoreCorruptError, match="retained source digest mismatch"):
        store.read_result(result.run.parse_run_id)


def test_store_treats_missing_committed_artifact_as_corruption(fixtures_dir, tmp_path) -> None:
    path = fixtures_dir / "native_text.pdf"
    request = ParseRequest(
        filename=path.name,
        mime_type="application/pdf",
        content=path.read_bytes(),
        parser_id="native-pdf",
    )
    store = ArtifactStore(tmp_path / "var")
    result = ParseOrchestrator(ParserRegistry([NativePdfParser()]), store).parse(request)
    manifest_path = store.runs_dir / result.run.parse_run_id / "manifest.json"
    manifest_path.unlink()
    with pytest.raises(RunStoreCorruptError, match="integrity verification"):
        store.read_result(result.run.parse_run_id)
