# Support and Compatibility Matrix

## Supported deployment

- Python 3.11
- Linux x86_64/arm64 single-node self-hosted deployment
- Local POSIX-compatible filesystem with atomic rename semantics
- One active API process per workspace
- TLS and external identity termination at a trusted reverse proxy

## Capability status

| Capability | Status in 1.0.3-rc.1 |
|---|---|
| Native PDF text/image extraction with pypdf | Stable engineering baseline |
| Generic structure recovery | Release candidate |
| Domain Pack runtime | Release candidate, declarative only |
| Standard visual matching | Preview; optional renderer required |
| PaddleOCR/OpenDoc | Disabled until fixed artifacts qualify |
| MinerU | Benchmark only |
| Rill Shadow | Preview and advisory only |
| Rill Assist | Qualification-gated Tier 1 only |
| boundedAuto | Unsupported and hard-disabled |
| Multi-node/shared-workspace operation | Unsupported |
| Public multi-tenant SaaS | Unsupported |

Production quality claims still require a real qualification report with `qualified=true`.
