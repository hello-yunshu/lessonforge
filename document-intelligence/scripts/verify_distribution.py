from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "phase-12" / "distribution_verification.json"


def run(
    command: list[str], *, cwd: Path, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        command,
        cwd=cwd,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"command failed ({completed.returncode}): "
            f"{' '.join(command)}\n{completed.stdout}"
        )
    return completed


def main() -> None:
    checks: list[dict[str, object]] = []
    with tempfile.TemporaryDirectory(prefix="di-wheel-") as temp_value:
        temp = Path(temp_value)
        wheel_dir = temp / "wheel"
        target = temp / "site"
        wheel_dir.mkdir()
        target.mkdir()
        run(
            [
                sys.executable,
                "-m",
                "pip",
                "wheel",
                ".",
                "--no-deps",
                "--no-build-isolation",
                "--wheel-dir",
                str(wheel_dir),
            ],
            cwd=ROOT,
        )
        wheels = sorted(wheel_dir.glob("document_intelligence-*.whl"))
        checks.append({"name": "wheel-built", "passed": len(wheels) == 1})
        if len(wheels) != 1:
            raise RuntimeError(f"expected one wheel, found {wheels}")
        wheel = wheels[0]
        with zipfile.ZipFile(wheel) as archive:
            names = set(archive.namelist())
        checks.append(
            {
                "name": "package-default-parser-config-included",
                "passed": "document_intelligence/defaults/parsers.yaml" in names,
            }
        )
        checks.append(
            {
                "name": "rill-assist-policy-included",
                "passed": "document_intelligence/defaults/rill_assist_policy.yaml" in names,
            }
        )
        checks.append(
            {
                "name": "rill-shadow-schemas-included",
                "passed": all(
                    f"document_intelligence/defaults/{name}" in names
                    for name in ("rill_observe.schema.json", "rill_feature_schema.json")
                ),
            }
        )
        checks.append(
            {
                "name": "production-qualification-package-included",
                "passed": (
                    "document_intelligence/production/models.py" in names
                    and "document_intelligence/production/service.py" in names
                    and "document_intelligence/production/store.py" in names
                ),
            }
        )
        checks.append(
            {
                "name": "qualification-campaign-package-included",
                "passed": (
                    "document_intelligence/campaign/models.py" in names
                    and "document_intelligence/campaign/service.py" in names
                    and "document_intelligence/campaign/store.py" in names
                ),
            }
        )
        checks.append(
            {
                "name": "typed-marker-included",
                "passed": "document_intelligence/py.typed" in names,
            }
        )
        checks.append(
            {
                "name": "release-candidate-security-modules-included",
                "passed": all(
                    f"document_intelligence/{name}" in names
                    for name in ("security.py", "observability.py")
                ),
            }
        )
        checks.append(
            {
                "name": "license-and-notice-included",
                "passed": any(name.endswith(".dist-info/licenses/LICENSE") for name in names)
                and any(name.endswith(".dist-info/licenses/NOTICE") for name in names),
            }
        )
        checks.append(
            {
                "name": "frozen-contract-manifest-included",
                "passed": (
                    "document_intelligence/defaults/frozen_contracts_v1.json" in names
                ),
            }
        )
        checks.append(
            {
                "name": "default-domain-packs-included",
                "passed": all(
                    (
                        "document_intelligence/defaults/domain_packs/"
                        f"{pack_id}/manifest.yaml"
                    )
                    in names
                    for pack_id in (
                        "generic-document",
                        "education-content",
                        "examination-paper",
                        "academic-paper",
                        "legal-contract",
                        "technical-manual",
                    )
                ),
            }
        )
        run(
            [
                sys.executable,
                "-m",
                "pip",
                "install",
                "--no-deps",
                "--target",
                str(target),
                str(wheel),
            ],
            cwd=temp,
        )
        env = os.environ.copy()
        env.pop("PYTHONPATH", None)
        env["PYTHONPATH"] = str(target)
        smoke = run(
            [
                sys.executable,
                "-c",
                (
                    "from document_intelligence import __version__; "
                    "from document_intelligence.config import Settings; "
                    "from document_intelligence.freeze import FreezeService; "
                    "from document_intelligence.domain_runtime import "
                    "DomainRuntimeEngine; "
                    "from document_intelligence.services.bootstrap import "
                    "build_document_family_service, build_domain_pack_registry, build_registry, "
                    "build_structure_service, build_rill_shadow_service, "
                    "build_rill_assist_service, build_mlops_service, "
                    "build_production_qualification_service, "
                    "build_qualification_campaign_service; "
                    "s=Settings.from_env(); r=build_registry(s); "
                    "assert __version__ == '1.0.3rc1'; "
                    "assert FreezeService().verify().compatible is True; "
                    "ss=build_structure_service(s); "
                    "dr=build_domain_pack_registry(s); "
                    "assert s.parser_config.is_file(); "
                    "assert 'native-pdf' in r.ids(); "
                    "assert ss.engine.engine_version == '0.3.0'; "
                    "assert dr.engine_version == DomainRuntimeEngine.runtime_version; "
                    "assert len(dr.list_builtin_records()) == 6; "
                    "fs=build_document_family_service(s, domain_registry=dr); "
                    "assert fs.store.list_ids() == []; "
                    "rs=build_rill_shadow_service(s); "
                    "assert rs.inspect()['shadowOnly'] is True; "
                    "ra=build_rill_assist_service(s, shadow_service=rs); "
                    "assert ra.inspect()['boundedAuto'] is False; "
                    "ml=build_mlops_service(s, shadow_service=rs, assist_service=ra); "
                    "assert ml.inspect()['boundedAuto'] is False; "
                    "pq=build_production_qualification_service(s); "
                    "assert pq.inspect()['qualifiedReportCount'] == 0; "
                    "assert pq.inspect()['boundedAuto'] is False; "
                    "qc=build_qualification_campaign_service(s, production_service=pq); "
                    "assert qc.inspect()['campaignCount'] == 0; "
                    "assert qc.inspect()['boundedAuto'] is False; rs.close(); "
                    "print(s.parser_config)"
                ),
            ],
            cwd=temp,
            env=env,
        )
        checks.append(
            {
                "name": "wheel-import-from-arbitrary-cwd",
                "passed": "document_intelligence/defaults/parsers.yaml" in smoke.stdout,
            }
        )
        freeze_cli = run(
            [sys.executable, "-m", "document_intelligence.cli", "freeze-verify"],
            cwd=temp,
            env=env,
        )
        checks.append(
            {
                "name": "installed-freeze-cli-smoke",
                "passed": '"compatible": true' in freeze_cli.stdout.lower(),
            }
        )
        cli = run(
            [sys.executable, "-m", "document_intelligence.cli", "parsers"],
            cwd=temp,
            env=env,
        )
        checks.append(
            {
                "name": "installed-cli-module-smoke",
                "passed": "native-pdf" in cli.stdout,
            }
        )
    payload = {
        "phase": 12,
        "passed": all(bool(check["passed"]) for check in checks),
        "checks": checks,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    if not payload["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
