# Secure CI Pipeline — Overview

## Purpose

This document describes the architecture and security rationale of the CI pipeline
for the Smart-Backup project. The pipeline is designed to enforce supply-chain
integrity, detect vulnerabilities early, and minimize the blast radius of a
compromise at any single point.

---

## Pipeline Structure

```
push / pull_request
        │
        ├─── checks ──────────────────────────────────────────────┐
        │    Runner assertion, checkout, commit verification,      │
        │    dependency integrity, license check, secret scanning, │
        │    SonarCloud SAST                                       │
        │                                                          │
        ├─── tests ───────────────────────────────────────────────┤
        │    pytest with deterministic seed                        │
        │                                                          │ needs: [checks, tests]
        ├─── security ────────────────────────────────────────────┤
        │    Bandit, Semgrep, pip-audit, Trivy FS                 │
        │                                                          │ needs: security
        ├─── dependency_guard (PR only) ──────────────────────────┤
        │    Detect changes in requirements.txt / pyproject        │
        │                                                          │ needs: [security, dependency_guard]
        └─── build (main only) ───────────────────────────────────┤
             Dockerfile policy check, image build, Trivy image    │
                                                                   │ needs: build
             attest_and_signing (main only) ──────────────────────┘
             SBOM, SLSA provenance, Cosign sign + verify
```

The DAG structure ensures that later stages never run if earlier ones fail.
This reduces wasted compute and prevents a compromised artifact from progressing
through the pipeline.

---

## Jobs

### `checks`

| Step | Purpose |
|------|---------|
| Assert runner OS | Fail fast if runner is not Linux |
| Checkout (`@sha`) | Pin action to immutable commit hash |
| Verify commit (GPG) | Ensure commits are signed; unsigned commits fail CI |
| Verify requirements hashes | `pip install --require-hashes` rejects tampered packages |
| License Check | Block GPL/AGPL dependencies (license compliance) |
| Setup Python (`@sha`) | Pinned action; deterministic Python version |
| Detect secrets (TruffleHog) | Scan filesystem for leaked credentials |
| Gitleaks | Secondary secret scanner; complements TruffleHog |
| SonarCloud Scan | SAST; restricted to push/non-fork PRs to avoid secret leakage |

**Permissions:** `contents: read`, `pull-requests: read`

---

### `tests`

| Step | Purpose |
|------|---------|
| pytest | Functional correctness; `PYTHONHASHSEED=0` for determinism |

**Permissions:** `contents: read`, `pull-requests: read`

---

### `security`

Runs only after `checks` and `tests` pass.

| Step | Purpose |
|------|---------|
| Bandit | Python SAST; high severity/confidence only |
| Semgrep | Multi-ruleset SAST: security-audit, secrets, OWASP Top 10, Python |
| pip-audit `--strict` | Dependency CVE audit; fails on any known vulnerability |
| Trivy FS | Filesystem scan; `ignore-unfixed: true` avoids noise from unpatched upstream issues |

**Permissions:** `contents: read`, `pull-requests: read`

---

### `dependency_guard`

Runs on `pull_request` only. Detects changes to `requirements.txt` or `pyproject.toml`
and emits a warning that triggers mandatory CODEOWNER review via branch protection rules.

---

### `build`

Runs on `main` branch only.

| Step | Purpose |
|------|---------|
| conftest (OPA) | Validate Dockerfile against policy before building |
| Docker build | `--network=none --pull --no-cache` for isolation and freshness |
| Trivy image | Scan built image by digest; fail on CRITICAL/HIGH |
| Push to GHCR | Push only after all scans pass; tagged by commit SHA |

`--network=none` during build prevents exfiltration of secrets or data
during the build stage. This is the primary network isolation control
since network access cannot be disabled in earlier stages (SonarCloud,
TruffleHog require outbound connections).

Vendoring: Dependencies are downloaded via pip download --require-hashes into wheels/ directory before Docker build. This enables --network=none during build while ensuring all packages are available.

**Permissions:** `contents: read`, `pull-requests: read`, `packages: write`

---

### `attest_and_signing`

Runs on `main` branch only, after `build`.

| Step | Purpose |
|------|---------|
| Get digest | Retrieve immutable image digest from registry |
| Generate SBOM | CycloneDX SBOM from declared dependencies |
| Attach SBOM | Attach SBOM to image via Cosign |
| SLSA provenance | Build provenance attestation via `actions/attest-build-provenance` |
| Cosign sign (keyless) | Sign image with OIDC-based ephemeral key |
| Cosign verify | Confirm signature is valid before pipeline completes |

**Permissions:** `contents: read`, `pull-requests: read`, `id-token: write`, `packages: write`

---

## Global Settings

```yaml
permissions: {}          # deny-all at workflow level; each job grants only what it needs
concurrency:             # cancel redundant runs on the same ref
  group: ci-${{ github.ref }}
  cancel-in-progress: true
defaults:
  run:
    shell: bash --noprofile --norc -Eeuo pipefail {0}
```

`-Eeuo pipefail` ensures that any unhandled error, unset variable, or failed
pipe immediately terminates the step with a non-zero exit code. This prevents
silent failures that could allow a compromised step to continue.

---

## Action Pinning Policy

All third-party actions are pinned to a full commit SHA, not a mutable tag.

**Example:**
```yaml
uses: actions/checkout@de0fac2e4500dabe0009e67214ff5f5447ce83dd  # v4.6.2
```

This prevents tag mutation attacks where an attacker modifies the code behind
a version tag without changing the tag itself.
