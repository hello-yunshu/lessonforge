from __future__ import annotations

import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "SHA256SUMS"
EXCLUDED_PARTS = {
    ".git",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "__pycache__",
    "dist",
    "htmlcov",
    "build",
}


def included(path: Path) -> bool:
    relative = path.relative_to(ROOT)
    if path == OUTPUT or path.name == ".coverage":
        return False
    if any(part in EXCLUDED_PARTS for part in relative.parts):
        return False
    if any(part.endswith(".egg-info") for part in relative.parts):
        return False
    runtime_namespaces = {
        "runs",
        "raw",
        "sources",
        "assets",
        "standard",
        "structures",
        "domain-packs",
        "domain-results",
        "domain-reviews",
        "rill-shadow",
        "rill-assist",
        "mlops",
        "production-qualification",
        "qualification-campaigns",
    }
    if len(relative.parts) >= 2 and relative.parts[0] == "var":
        if relative.parts[1] in runtime_namespaces and path.name != ".gitkeep":
            return False
    if path.suffix in {".pyc", ".pyo"}:
        return False
    return path.is_file()


def main() -> None:
    lines: list[str] = []
    for path in sorted(ROOT.rglob("*")):
        if not included(path):
            continue
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        lines.append(f"{digest}  {path.relative_to(ROOT).as_posix()}")
    OUTPUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {len(lines)} entries to {OUTPUT}")


if __name__ == "__main__":
    main()
