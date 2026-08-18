from __future__ import annotations

import hashlib
import importlib.metadata
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "phase-12" / "release_sbom.spdx.json"
RELEASE_EPOCH = int(os.getenv("SOURCE_DATE_EPOCH", "1785801600"))


def package_checksum(name: str) -> str:
    distribution = importlib.metadata.distribution(name)
    digest = hashlib.sha256()
    for item in sorted(distribution.files or [], key=str):
        path = distribution.locate_file(item)
        if path.is_file():
            digest.update(str(item).encode("utf-8"))
            try:
                digest.update(path.read_bytes())
            except OSError:
                pass
    return digest.hexdigest()


def project_checksum() -> str:
    digest = hashlib.sha256()
    sources = [ROOT / "pyproject.toml", ROOT / "LICENSE", ROOT / "NOTICE"]
    sources.extend(sorted((ROOT / "src" / "document_intelligence").rglob("*")))
    for path in sources:
        if path.is_file() and "__pycache__" not in path.parts:
            digest.update(path.relative_to(ROOT).as_posix().encode("utf-8"))
            digest.update(path.read_bytes())
    return digest.hexdigest()


def main() -> None:
    packages: list[dict[str, object]] = [
        {
            "SPDXID": "SPDXRef-Package-DocumentIntelligence",
            "name": "document-intelligence",
            "versionInfo": "1.0.3-rc.1",
            "downloadLocation": "NOASSERTION",
            "filesAnalyzed": False,
            "licenseConcluded": "Apache-2.0",
            "licenseDeclared": "Apache-2.0",
            "checksums": [
                {"algorithm": "SHA256", "checksumValue": project_checksum()}
            ],
        }
    ]
    names = [
        "fastapi",
        "httpx",
        "pillow",
        "pydantic",
        "pydantic-settings",
        "pypdf",
        "numpy",
        "opencv-python-headless",
        "python-multipart",
        "pyyaml",
        "packaging",
        "cryptography",
        "uvicorn",
    ]
    for index, name in enumerate(names, start=1):
        try:
            distribution = importlib.metadata.distribution(name)
        except importlib.metadata.PackageNotFoundError:
            continue
        metadata = distribution.metadata
        license_value = (
            metadata.get("License-Expression")
            or metadata.get("License")
            or "NOASSERTION"
        )
        packages.append(
            {
                "SPDXID": f"SPDXRef-Package-Dependency-{index}",
                "name": metadata.get("Name", name),
                "versionInfo": distribution.version,
                "downloadLocation": "NOASSERTION",
                "filesAnalyzed": False,
                "licenseConcluded": license_value.splitlines()[0],
                "licenseDeclared": license_value.splitlines()[0],
                "checksums": [
                    {"algorithm": "SHA256", "checksumValue": package_checksum(name)}
                ],
            }
        )
    package_material = json.dumps(packages, sort_keys=True, separators=(",", ":"))
    namespace_uuid = uuid.uuid5(uuid.NAMESPACE_URL, package_material)
    created = datetime.fromtimestamp(RELEASE_EPOCH, tz=timezone.utc)
    payload = {
        "spdxVersion": "SPDX-2.3",
        "dataLicense": "CC0-1.0",
        "SPDXID": "SPDXRef-DOCUMENT",
        "name": "document-intelligence-1.0.3-rc.1",
        "documentNamespace": f"urn:uuid:{namespace_uuid}",
        "creationInfo": {
            "created": created.isoformat().replace("+00:00", "Z"),
            "creators": ["Tool: document-intelligence-generate-sbom/1"],
        },
        "documentDescribes": ["SPDXRef-Package-DocumentIntelligence"],
        "packages": packages,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"packages": len(packages), "output": str(OUT)}, indent=2))


if __name__ == "__main__":
    main()
