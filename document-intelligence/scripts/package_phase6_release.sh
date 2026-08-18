#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT_DIR="${OUT_DIR:-$ROOT/dist}"
NAME="document-intelligence_phase6_0.6.0"
mkdir -p "$OUT_DIR"
cd "$ROOT"
export PYTHONPATH="$ROOT/src${PYTHONPATH:+:$PYTHONPATH}"

python scripts/generate_fixtures.py
python scripts/run_phase1_benchmark.py
python scripts/run_phase2_benchmark.py
python scripts/run_phase3_benchmark.py
python scripts/run_phase4_benchmark.py
python scripts/run_phase5_benchmark.py
python scripts/run_phase6_benchmark.py
python scripts/generate_dependency_report.py
python scripts/export_schemas.py
python scripts/verify_phase1.py
python scripts/verify_phase2.py
python scripts/verify_phase3.py
python scripts/verify_phase4.py
python scripts/verify_phase5.py
python scripts/verify_phase6.py
python scripts/verify_distribution.py
python scripts/static_sanity.py
python -m compileall -q src tests scripts
python -m pytest --cov=document_intelligence --cov-branch --cov-report=term -q
python scripts/generate_source_manifest.py

rm -f "$OUT_DIR/$NAME.zip" "$OUT_DIR/$NAME.zip.sha256"
OUT_DIR="$OUT_DIR" python - <<'PY'
from pathlib import Path
import os
import zipfile

root = Path.cwd()
out = Path(os.environ["OUT_DIR"]) / "document-intelligence_phase6_0.6.0.zip"
excluded = {
    ".git", ".pytest_cache", ".mypy_cache", ".ruff_cache", "__pycache__",
    "dist", ".coverage", "htmlcov", "build",
}
runtime_namespaces = {
    "runs", "raw", "sources", "assets", "standard", "structures",
    "domain-packs", "domain-results", "domain-reviews", "rill-shadow", "rill-assist",
}
with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(root)
        if any(part in excluded for part in relative.parts):
            continue
        if path.suffix in {".pyc", ".pyo"}:
            continue
        if any(part.endswith(".egg-info") for part in relative.parts):
            continue
        if len(relative.parts) >= 2 and relative.parts[0] == "var":
            if relative.parts[1] in runtime_namespaces and path.name != ".gitkeep":
                continue
        archive.write(path, Path("document-intelligence") / relative)
print(out)
PY
sha256sum "$OUT_DIR/$NAME.zip" > "$OUT_DIR/$NAME.zip.sha256"
unzip -t "$OUT_DIR/$NAME.zip" >/dev/null

TEMP_DIR="$(mktemp -d -t di-phase6-release-XXXXXX)"
trap 'rm -rf "$TEMP_DIR"' EXIT
unzip -q "$OUT_DIR/$NAME.zip" -d "$TEMP_DIR"
EXTRACTED="$TEMP_DIR/document-intelligence"
(
    cd "$EXTRACTED"
    sha256sum -c SHA256SUMS >/dev/null
    export PYTHONPATH="$EXTRACTED/src"
    python -m compileall -q src tests scripts
    python -m pytest -q
    python scripts/verify_phase6.py >/dev/null
    python - <<'PY'
from document_intelligence import __version__
from document_intelligence.config import Settings
from document_intelligence.services import build_rill_assist_service
assert __version__ == "0.6.0"
service = build_rill_assist_service(Settings.from_env())
assert service.inspect()["boundedAuto"] is False
print(__version__)
PY
)
printf 'verified release: %s\n' "$OUT_DIR/$NAME.zip"
