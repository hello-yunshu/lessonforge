from __future__ import annotations

import pytest

from document_intelligence.exceptions import CorruptInputError, UnsupportedInputError
from document_intelligence.services import IngestionPolicy, detect_mime, ingest_bytes


def test_detect_mime_uses_magic_bytes() -> None:
    assert detect_mime("wrong.txt", b"%PDF-1.7\n") == "application/pdf"
    assert detect_mime("x.bin", b"\x89PNG\r\n\x1a\nrest") == "image/png"


def test_ingestion_rejects_empty_and_oversize() -> None:
    policy = IngestionPolicy(max_upload_bytes=4)
    with pytest.raises(CorruptInputError):
        ingest_bytes("x.pdf", b"", policy=policy)
    with pytest.raises(CorruptInputError):
        ingest_bytes("x.pdf", b"%PDF-long", policy=policy)


def test_ingestion_rejects_unknown_type() -> None:
    policy = IngestionPolicy(max_upload_bytes=100)
    with pytest.raises(UnsupportedInputError):
        ingest_bytes("x.unknown", b"not-a-supported-document", policy=policy)


def test_ingestion_does_not_trust_file_extension() -> None:
    policy = IngestionPolicy(max_upload_bytes=100)
    with pytest.raises(UnsupportedInputError):
        ingest_bytes("renamed.pdf", b"not really a pdf", policy=policy)


def test_ingestion_rejects_unsafe_filename() -> None:
    policy = IngestionPolicy(max_upload_bytes=100)
    with pytest.raises(CorruptInputError):
        ingest_bytes("../x.pdf", b"%PDF-1.7\n", policy=policy)
