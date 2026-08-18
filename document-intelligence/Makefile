.PHONY: install test test-budget test-cov lint typecheck verify run fixtures report package sbom

install:
	python -m pip install -r requirements/development.txt
	python -m pip install --no-deps -e .

test:
	pytest -q

test-budget:
	python scripts/run_test_budget.py

test-cov:
	pytest --cov=document_intelligence --cov-branch --cov-report=term-missing -q

lint:
	ruff check src tests scripts
	ruff format --check src tests scripts

typecheck:
	mypy src/document_intelligence

verify: lint typecheck test-budget test-cov
	PYTHONPATH=src python scripts/verify_all.py
	python scripts/secret_scan.py

run:
	uvicorn document_intelligence.api.main:app --host 127.0.0.1 --port 8080

fixtures:
	python scripts/generate_fixtures.py

report:
	PYTHONPATH=src python scripts/verify_all.py
	PYTHONPATH=src python scripts/generate_dependency_report.py
	python scripts/generate_sbom.py

sbom:
	python scripts/generate_sbom.py

package:
	python scripts/build_release_candidate.py
