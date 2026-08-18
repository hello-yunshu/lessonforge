#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT_DIR="${OUT_DIR:-$ROOT/dist}"
NAME="document-intelligence_phase1_0.1.0"
mkdir -p "$OUT_DIR"
cd "$ROOT"
export PYTHONPATH="$ROOT/src${PYTHONPATH:+:$PYTHONPATH}"
python scripts/generate_fixtures.py
python scripts/run_phase1_benchmark.py
python scripts/generate_dependency_report.py
python scripts/export_schemas.py
python scripts/verify_phase1.py
python -m compileall -q src tests scripts
pytest --cov=document_intelligence --cov-report=term-missing -q
python scripts/generate_source_manifest.py
rm -f "$OUT_DIR/$NAME.zip"
OUT_DIR="$OUT_DIR" python - <<'PY'
from pathlib import Path
import os
import zipfile
root = Path.cwd()
out = Path(os.environ['OUT_DIR']) / 'document-intelligence_phase1_0.1.0.zip'
excluded = {'.git', '.pytest_cache', '.mypy_cache', '.ruff_cache', '__pycache__', 'dist', '.coverage', 'htmlcov'}
with zipfile.ZipFile(out, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
    for path in sorted(root.rglob('*')):
        if not path.is_file():
            continue
        relative = path.relative_to(root)
        if any(part in excluded for part in relative.parts):
            continue
        if path.suffix in {'.pyc', '.pyo'} or relative.parts[:2] in {('var', 'runs'), ('var', 'raw')}:
            continue
        archive.write(path, Path('document-intelligence') / relative)
print(out)
PY
sha256sum "$OUT_DIR/$NAME.zip" > "$OUT_DIR/$NAME.zip.sha256"
