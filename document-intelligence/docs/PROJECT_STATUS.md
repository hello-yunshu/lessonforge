# Project Status

## Current baseline

- Project: `document-intelligence`
- Version: `1.0.3-rc.1`
- Completed: Phase 0—Phase 12
- Release class: restricted single-node self-hosted release candidate
- Core API authentication: required in production profile
- Resource isolation: tenant-scoped entitlements for core derived artifacts
- Native PDF base: `pypdf`
- Optional PDF pixel renderer: PyMuPDF, disabled by default in production
- Rill mode: Shadow plus qualification-gated Tier 1 Assist
- boundedAuto: hard disabled
- Production qualification: not obtained

## Phase 12 release-candidate hardening

- fail-closed production profile validation;
- tenant tokens, subject identity, rate/concurrency limits and deadlines;
- immutable access entitlements and access-audit records;
- liveness, readiness, bounded capability matrix, JSON logs and metrics;
- AGPL-3.0 project license;
- base PDF extraction moved away from PyMuPDF;
- digest-required container base configuration and loopback host binding;
- one current CI and package entry point through Phase 12;
- exact direct dependency versions, dependency inventory, SPDX SBOM and secret scan;
- normalized reproducible wheel build and deterministic complete source ZIP;
- bounded test batches, workspace backup/restore and optimized-mode verification.

## Frozen 1.x contracts

Phase 9's machine freeze remains intact. Phase 12 adds isolated and backward-compatible
security, observability and release tooling. Existing 1.x routes and payload contracts are
retained; production profile adds authentication before those routes are reachable.

## Release boundary

The RC may be evaluated as a single-node self-hosted deployment behind a trusted TLS reverse
proxy. Public SaaS, shared multi-process workspaces and automatic model/action release are not
supported. The distribution contains no production qualification records.

## Remaining blockers before a stable production release

- real multi-domain gold and challenge datasets;
- fixed and signed external parser runtime/model/image digests;
- 168-hour soak, scale, restart and recovery evidence;
- successful hosted CI evidence for Ruff, Mypy, pip-audit and container scanning;
- a digest-pinned container base selected and built by the distributor;
- optional renderer license attestation when PyMuPDF is enabled;
- real pilot evidence and independent release approval;
- higher branch coverage for error-heavy stores and API paths.
