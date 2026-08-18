from __future__ import annotations

import base64
import hashlib
import json
import shutil
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import yaml
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from document_intelligence.domain_pack_sdk import DomainPackManifest
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
    ParserResult,
    ParseRequest,
    ParseRun,
    ResourceUsage,
    RunStatus,
    SourceDescriptor,
)

ROOT = Path(__file__).resolve().parents[2]


def archive_directory(source: Path) -> bytes:
    target = source.parent / f"{source.name}.zip"
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(source.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(source).as_posix())
    data = target.read_bytes()
    target.unlink()
    return data


def copy_pack(tmp_path: Path, pack_id: str = "education-content") -> Path:
    target = tmp_path / pack_id
    shutil.copytree(ROOT / "domain-packs" / pack_id, target)
    return target


def sign_pack(pack_root: Path, key_id: str = "test-key") -> tuple[bytes, str]:
    key = Ed25519PrivateKey.generate()
    public_key = base64.b64encode(key.public_key().public_bytes_raw()).decode("ascii")
    path = pack_root / "manifest.yaml"
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    raw["signing_key_id"] = key_id
    raw["signature"] = None
    unsigned = DomainPackManifest.model_construct(**raw)
    raw["signature"] = base64.b64encode(
        key.sign(unsigned.canonical_signing_payload())
    ).decode("ascii")
    path.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")
    return archive_directory(pack_root), public_key


def build_parser_result() -> tuple[ParseRequest, ParserResult]:
    content = b"domain-runtime-fixture"
    source_hash = hashlib.sha256(content).hexdigest()
    run_id = f"run_{source_hash[:20]}"
    page_id = "page_0"
    specs = [
        ("example", BaseType.HEADING, (0.1, 0.1, 0.8, 0.18), "例1 观察图形"),
        ("character", BaseType.CHARACTER, (0.1, 0.22, 0.2, 0.35), None),
        ("speech", BaseType.CALLOUT, (0.22, 0.22, 0.8, 0.35), "想一想，你发现了什么？"),
        ("practice", BaseType.TEXT, (0.1, 0.45, 0.8, 0.55), "练一练 第1题"),
    ]
    elements: list[Element] = []
    evidence: list[Evidence] = []
    for element_id, base_type, coords, text in specs:
        evidence_id = f"ev_{element_id}"
        bbox = BoundingBox(x1=coords[0], y1=coords[1], x2=coords[2], y2=coords[3])
        evidence.append(
            Evidence(
                evidence_id=evidence_id,
                kind=EvidenceKind.MODEL_PREDICTION,
                producer="fixture",
                producer_version="1",
                model_digest="0" * 64,
                parse_run_id=run_id,
                source_page_id=page_id,
                bbox=bbox,
            )
        )
        elements.append(
            Element(
                element_id=element_id,
                page_id=page_id,
                base_type=base_type,
                subtype=f"fixture_{base_type.value}",
                bbox=bbox,
                content=ElementContent(text=text),
                confidence=Confidence(overall=0.95),
                evidence_ids=[evidence_id],
            )
        )
    document = ParsedDocument(
        document_id=f"doc_{source_hash[:20]}",
        source=SourceDescriptor(
            filename="fixture.pdf",
            sha256=source_hash,
            mime_type="application/pdf",
            size_bytes=len(content),
        ),
        pages=[
            Page(
                page_id=page_id,
                index=0,
                width=1000,
                height=1000,
                element_ids=[item.element_id for item in elements],
            )
        ],
        elements=elements,
        evidence=evidence,
        parse_run_id=run_id,
    )
    now = datetime.now(timezone.utc)
    request = ParseRequest(
        filename="fixture.pdf",
        mime_type="application/pdf",
        content=content,
        parser_id="fixture",
    )
    run = ParseRun(
        parse_run_id=run_id,
        input_sha256=source_hash,
        parser_id="fixture",
        parser_version="1",
        parser_digest="1" * 64,
        config_digest="2" * 64,
        request_context_digest=request.context_digest(),
        status=RunStatus.SUCCEEDED,
        started_at=now,
        finished_at=now,
        semantic_output_digest=document.semantic_digest(),
        resource_usage=ResourceUsage(
            duration_ms=1,
            input_bytes=len(content),
            output_elements=len(elements),
        ),
    )
    return request, ParserResult(document=document, run=run)
