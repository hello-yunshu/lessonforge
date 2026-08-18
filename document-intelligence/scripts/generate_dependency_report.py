from __future__ import annotations

import hashlib
import importlib.metadata
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT_JSON = ROOT / "docs" / "phase-12" / "dependency_inventory.json"
OUT_MD = ROOT / "docs" / "phase-12" / "DEPENDENCY_LOCK.md"
CORE_DISTRIBUTIONS = [
    "fastapi",
    "httpx",
    "Pillow",
    "pydantic",
    "pydantic-settings",
    "pypdf",
    "numpy",
    "opencv-python-headless",
    "packaging",
    "cryptography",
    "python-multipart",
    "PyYAML",
    "uvicorn",
]
QUALITY_DISTRIBUTIONS = [
    "pytest",
    "coverage",
    "ruff",
    "mypy",
    "cyclonedx-bom",
    "pip-audit",
]
OPTIONAL_DISTRIBUTIONS = [
    "PyMuPDF",
    "paddleocr",
    "paddlepaddle",
    "openocr-python",
    "mineru",
    "dvc",
    "mlflow",
]


def distribution_tree_digest(name: str) -> tuple[str, str]:
    distribution = importlib.metadata.distribution(name)
    digest = hashlib.sha256()
    for item in sorted(distribution.files or [], key=str):
        path = distribution.locate_file(item)
        if not path.is_file():
            continue
        digest.update(str(item).encode("utf-8"))
        try:
            digest.update(path.read_bytes())
        except OSError:
            continue
    return distribution.version, digest.hexdigest()


def distribution_record(name: str) -> dict[str, object]:
    try:
        version, digest = distribution_tree_digest(name)
    except importlib.metadata.PackageNotFoundError:
        return {"name": name, "installed": False}
    metadata = importlib.metadata.metadata(name)
    license_value = metadata.get("License-Expression") or metadata.get("License")
    if license_value:
        license_value = license_value.splitlines()[0]
    return {
        "name": name,
        "installed": True,
        "version": version,
        "tree_sha256": digest,
        "license": license_value,
    }


def binary_digest(name: str) -> dict[str, str] | None:
    value = shutil.which(name)
    if not value:
        return None
    path = Path(value)
    return {
        "path": str(path),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def main() -> None:
    core = [distribution_record(name) for name in CORE_DISTRIBUTIONS]
    quality = [distribution_record(name) for name in QUALITY_DISTRIBUTIONS]
    optional = [distribution_record(name) for name in OPTIONAL_DISTRIBUTIONS]
    pymupdf = next(item for item in optional if item["name"] == "PyMuPDF")
    payload = {
        "phase": 12,
        "release": "1.0.3-rc.1",
        "core_python": core,
        "quality_tools": quality,
        "optional_components": optional,
        "system_binaries": {"tesseract": binary_digest("tesseract")},
        "license_gate": {
            "core_native_pdf": "cleared-pypdf-bsd-3-clause",
            "optional_pymupdf": (
                "installed-but-disabled-pending-attestation"
                if pymupdf.get("installed")
                else "not-installed"
            ),
            "production_default_renderer": "disabled",
        },
        "limitations": [
            "Installed-tree digests are environment evidence, not wheel hashes.",
            "CI must run pip-audit and preserve its report before release.",
            "External parser services require image and model SHA-256 evidence.",
        ],
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    lines = [
        "# Phase 12 / 1.0.3-rc.1 依赖与许可证登记",
        "",
        "核心原生PDF文本提取已改为 `pypdf`。PyMuPDF只作为可选像素渲染器，",
        "生产配置默认关闭，只有显式完成许可证证明后才能启用。",
        "",
        "## 核心依赖",
        "",
        "| 名称 | 已安装 | 版本 | 许可证 | 安装树SHA-256 |",
        "|---|---|---|---|---|",
    ]
    for item in core:
        lines.append(
            f"| {item['name']} | {item['installed']} | "
            f"{item.get('version', '-')} | {item.get('license') or '-'} | "
            f"{item.get('tree_sha256', '-')} |"
        )
    lines.extend(
        [
            "",
            "## 正式质量工具状态",
            "",
            "未安装的工具不会被描述为本地通过；正式CI必须执行Ruff、Mypy、",
            "pip-audit、测试超时门禁和SBOM生成。",
            "",
            "| 名称 | 当前环境已安装 | 版本 |",
            "|---|---|---|",
        ]
    )
    for item in quality:
        lines.append(
            f"| {item['name']} | {item['installed']} | {item.get('version', '-')} |"
        )
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
