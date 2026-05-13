# Security Policy

## Supported versions

| Version | Supported          |
|---------|--------------------|
| 0.x     | yes (current)      |
| < 0.1   | no                 |

ObserVIBElity is pre-1.0; expect breaking changes between minor versions. Security patches will only target the latest 0.x release.

## Reporting a vulnerability

**Do NOT open a public GitHub issue for security reports.**

Instead, use GitHub's private vulnerability reporting:
1. Go to https://github.com/stephenwagner-grafana/observibelity/security/advisories/new
2. Fill in: affected version, reproduction, expected impact, suggested fix (if known)
3. Submit

You should receive an acknowledgment within 5 business days. For critical issues, we follow a coordinated disclosure timeline (typically 90 days unless actively exploited).

## Security model

### What's protected by default
- Credentials collected by the wizard are written to `.env` (chmod 600) and Kubernetes Secrets
- The state file `.observibelity-state` stores only SHA256 hashes of credentials, never the raw values
- Telemetry pushes to the user's own Grafana Cloud — no data is sent to maintainers

### What's NOT hardened in 0.x (target: 1.0+)
- Default RBAC is permissive for `install.sh` admin operations
- Pod-to-pod NetworkPolicies are not enforced by default
- Container images are not yet pinned by digest

### Threat model assumptions
- The cluster admin is trusted
- The cluster network is trusted (no untrusted tenants on the same cluster)
- `.env` and Kubernetes Secrets are protected by the cluster's RBAC and storage encryption

### Operating in production
If you're running this for more than a demo:
- Enable cluster-level Secret encryption (KMS-backed)
- Use [External Secrets Operator](docs/GITOPS.md) instead of plain Secrets
- Pin container images by digest, not tag
- Restrict ServiceAccount RBAC to least privilege
- Enable Pod Security Admission (`restricted` profile)
- Add NetworkPolicies between namespaces

See [docs/GITOPS.md](docs/GITOPS.md) for the production-leaning deploy path.

## Acknowledgments

Security researchers who responsibly disclose vulnerabilities will be credited in `CHANGELOG.md` and in release notes (unless they request anonymity).
