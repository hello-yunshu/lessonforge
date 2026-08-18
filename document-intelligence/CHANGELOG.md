# Changelog

## 1.0.3-rc.1 — 2026-08-04

- Added production-profile startup validation, tenant authentication, access entitlements,
  rate/concurrency limits, request deadlines and immutable access audit records.
- Added liveness, readiness, capability status, structured JSON request logs and Prometheus
  text metrics.
- Replaced the base native PDF dependency with permissively licensed pypdf; PyMuPDF rendering
  is now an optional, separately qualified capability.
- Added Apache-2.0 project licensing, NOTICE, security policy and support matrix.
- Added deterministic release builder, dependency inventory, SBOM generation, secret scan,
  current-phase CI/release gates and hardened container defaults.
- Replaced production runtime asserts with explicit fail-closed validation.
- Added Phase 12 release-candidate audit and verification gates.

## 1.0.2 — 2026-08-04

- Added production qualification campaign orchestration and sealed evidence bundles.

## 1.0.1 — 2026-08-04

- Added production qualification evidence and policy gates.

## 1.0.0 — 2026-08-04

- Froze the 1.x core contracts.
