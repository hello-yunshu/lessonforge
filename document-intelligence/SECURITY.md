# Security Policy

## Supported versions

| Version | Security fixes |
|---|---|
| 1.0.3-rc.1 | Supported release candidate |
| 1.0.2 and earlier | Upgrade required |

## Reporting

Do not disclose suspected vulnerabilities in public issue trackers. Use the private security
contact or incident channel designated by the distributor of the deployment. Include the
affected version, reproduction steps, impact, and whether documents or credentials may have
been exposed. A public source repository and public security contact are not bundled in this
artifact, so operators must define this channel before exposing the service.

## Deployment boundary

The 1.0.3 release candidate is single-node self-hosted software. Production profile startup
fails unless tenant-scoped API authentication is configured. Run behind a trusted TLS reverse
proxy, keep the application port bound to loopback/private networks, rotate tokens, and protect
the workspace and backups with host-level encryption.

`boundedAuto` is not supported. Optional parsers, renderers, Rill artifacts and MLOps releases
must remain disabled until separately qualified.
