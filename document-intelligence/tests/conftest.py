from __future__ import annotations

from pathlib import Path

import pytest

from document_intelligence.config import Settings
from document_intelligence.services import IngestionPolicy

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures"


@pytest.fixture
def fixtures_dir() -> Path:
    return FIXTURES


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        workspace=tmp_path / "var",
        parser_config=ROOT / "configs" / "parsers.yaml",
        max_upload_bytes=10 * 1024 * 1024,
    )


@pytest.fixture
def ingestion_policy() -> IngestionPolicy:
    return IngestionPolicy(max_upload_bytes=10 * 1024 * 1024)
