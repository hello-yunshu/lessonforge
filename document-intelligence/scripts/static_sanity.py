from __future__ import annotations

import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "phase-12" / "static_sanity.json"
PYTHON_ROOTS = (ROOT / "src", ROOT / "tests", ROOT / "scripts")
CORE_ROOT = ROOT / "src" / "document_intelligence"
FORBIDDEN_CORE_TERMS = (
    "textbook",
    "lesson",
    "worked_example",
    "教材",
    "课时",
    "例题",
)
DANGEROUS_CALLS = {"eval", "exec"}


def python_files() -> list[Path]:
    files: list[Path] = []
    for root in PYTHON_ROOTS:
        files.extend(path for path in root.rglob("*.py") if "__pycache__" not in path.parts)
    return sorted(files)


def main() -> None:
    violations: list[dict[str, object]] = []
    checked_files = python_files()
    for path in checked_files:
        relative = path.relative_to(ROOT).as_posix()
        text = path.read_text(encoding="utf-8")
        try:
            tree = ast.parse(text, filename=relative)
        except SyntaxError as exc:
            violations.append(
                {
                    "kind": "syntax-error",
                    "path": relative,
                    "line": exc.lineno,
                    "message": str(exc),
                }
            )
            continue
        for line_number, line in enumerate(text.splitlines(), start=1):
            if len(line) > 100:
                violations.append(
                    {
                        "kind": "line-too-long",
                        "path": relative,
                        "line": line_number,
                        "length": len(line),
                    }
                )
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and any(
                alias.name == "*" for alias in node.names
            ):
                violations.append(
                    {
                        "kind": "wildcard-import",
                        "path": relative,
                        "line": node.lineno,
                    }
                )
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                if node.func.id in DANGEROUS_CALLS:
                    violations.append(
                        {
                            "kind": "dangerous-call",
                            "path": relative,
                            "line": node.lineno,
                            "call": node.func.id,
                        }
                    )
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.name.startswith("_"):
                    continue
                missing: list[str] = []
                if node.returns is None:
                    missing.append("return")
                arguments = node.args.posonlyargs + node.args.args + node.args.kwonlyargs
                missing.extend(
                    argument.arg
                    for argument in arguments
                    if argument.arg not in {"self", "cls"} and argument.annotation is None
                )
                if node.args.vararg and node.args.vararg.annotation is None:
                    missing.append(f"*{node.args.vararg.arg}")
                if node.args.kwarg and node.args.kwarg.annotation is None:
                    missing.append(f"**{node.args.kwarg.arg}")
                if missing and path.is_relative_to(CORE_ROOT):
                    violations.append(
                        {
                            "kind": "public-annotation-missing",
                            "path": relative,
                            "line": node.lineno,
                            "function": node.name,
                            "missing": missing,
                        }
                    )
        if path.is_relative_to(CORE_ROOT):
            lowered = text.lower()
            for term in FORBIDDEN_CORE_TERMS:
                if term.lower() in lowered:
                    violations.append(
                        {
                            "kind": "domain-term-in-core",
                            "path": relative,
                            "term": term,
                        }
                    )
    payload = {
        "phase": 12,
        "passed": not violations,
        "checked_files": len(checked_files),
        "checks": [
            "python-ast-parse",
            "line-length-100",
            "no-wildcard-imports",
            "no-eval-or-exec",
            "public-core-annotations",
            "domain-neutral-core",
        ],
        "violations": violations,
        "note": (
            "This deterministic local gate complements, but does not replace, "
            "Ruff and Mypy in CI."
        ),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    if violations:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
