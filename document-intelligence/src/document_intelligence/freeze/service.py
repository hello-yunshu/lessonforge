from __future__ import annotations

from pathlib import Path

from packaging.version import Version

from document_intelligence import __version__

from .models import (
    ContractDifference,
    FreezeManifest,
    FreezeVerification,
    canonical_digest,
)
from .registry import (
    FROZEN_API_OPERATIONS,
    FROZEN_MANIFEST_V1_DIGEST,
    build_manifest,
    default_manifest_path,
    discover_api_operations,
)


class FreezeService:
    def __init__(self, manifest_path: Path | None = None) -> None:
        self.manifest_path = manifest_path or default_manifest_path()

    def load_manifest(self) -> FreezeManifest:
        manifest = FreezeManifest.model_validate_json(
            self.manifest_path.read_text(encoding="utf-8")
        )
        if manifest.manifest_digest != FROZEN_MANIFEST_V1_DIGEST:
            raise ValueError("freeze manifest does not match the v1 trust anchor")
        return manifest

    def verify(self) -> FreezeVerification:
        expected = self.load_manifest()
        actual = build_manifest()
        expected_by_id = {item.contract_id: item for item in expected.contracts}
        actual_by_id = {item.contract_id: item for item in actual.contracts}
        differences: list[ContractDifference] = []
        for contract_id in sorted(set(expected_by_id) | set(actual_by_id)):
            expected_item = expected_by_id.get(contract_id)
            actual_item = actual_by_id.get(contract_id)
            if expected_item is None:
                differences.append(
                    ContractDifference(
                        contract_id=contract_id,
                        actual_digest=actual_item.digest if actual_item else None,
                        reason="unexpected contract",
                    )
                )
            elif actual_item is None:
                differences.append(
                    ContractDifference(
                        contract_id=contract_id,
                        expected_digest=expected_item.digest,
                        reason="missing contract",
                    )
                )
            elif expected_item.digest != actual_item.digest:
                differences.append(
                    ContractDifference(
                        contract_id=contract_id,
                        expected_digest=expected_item.digest,
                        actual_digest=actual_item.digest,
                        reason="contract digest changed",
                    )
                )
        missing_operations = sorted(
            set(FROZEN_API_OPERATIONS) - discover_api_operations()
        )
        if missing_operations:
            differences.append(
                ContractDifference(
                    contract_id="rest-api-v1",
                    expected_digest=expected_by_id["rest-api-v1"].digest,
                    actual_digest=canonical_digest(
                        [list(item) for item in sorted(discover_api_operations())]
                    ),
                    reason="frozen REST operations are missing from the API source",
                )
            )
        current_version = Version(__version__)
        if not (Version("1.0.0") <= current_version < Version("2.0.0")):
            differences.append(
                ContractDifference(
                    contract_id="version-semantics-v1",
                    expected_digest=expected.manifest_digest,
                    actual_digest=actual.manifest_digest,
                    reason="project version is outside the frozen 1.x compatibility range",
                )
            )
        if not differences and expected.manifest_digest != actual.manifest_digest:
            differences.append(
                ContractDifference(
                    contract_id="freeze-manifest-v1",
                    expected_digest=expected.manifest_digest,
                    actual_digest=actual.manifest_digest,
                    reason="freeze manifest metadata changed",
                )
            )
        exact = not differences
        return FreezeVerification(
            manifest_digest=expected.manifest_digest,
            project_version=__version__,
            compatible=exact,
            exact_match=exact,
            differences=differences,
        )
