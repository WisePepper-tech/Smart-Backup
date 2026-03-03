# Architecture Decision Records (ADR)

This document records conscious trade-offs and design decisions made in the
pipeline. Each entry explains what was chosen, what was rejected, and why.

---

## ADR-001 — Network Isolation Scope

**Decision:** `--network=none` applied only to Docker build stage, not to
earlier CI stages.

**Context:** Several tools in the `checks` stage require outbound network
access: TruffleHog pulls its Docker image, SonarCloud sends scan results
to an external API, Gitleaks action fetches its binary. Disabling the network
on these stages would break the tools entirely.

**Alternatives considered:**
- Remove network-dependent tools → rejected; they provide meaningful signal.
- Run all tools in a pre-built, pinned offline container → out of scope for
  a personal project; adds significant maintenance overhead.

**Accepted trade-off:** Network access is open on `checks`, `tests`, and
`security` stages. Mitigation is scoping `GITHUB_TOKEN` to read-only on
those stages so that a compromised network call cannot write to packages
or secrets.

---

## ADR-002 — Digest Pinning vs. Mirror Registry

**Decision:** Third-party actions pinned to commit SHA. No internal mirror
registry used.

**Context:** Mirror registries (e.g., Artifactory) provide an additional
layer of control: they snapshot external actions at a known-good state and
prevent silent upstream changes. For an enterprise pipeline, this is standard.

**Alternatives considered:**
- Internal mirror registry → rejected; infrastructure cost and maintenance
  not justified for a personal project.
- Mutable tag references (`@v4`) → rejected; vulnerable to tag mutation attacks.

**Accepted trade-off:** SHA pinning protects against tag mutation but does
not protect against a supply-chain compromise that occurred before the SHA
was pinned. This is an accepted residual risk at this project scale.

---

## ADR-003 — Single CODEOWNER

**Decision:** One CODEOWNER (project author) controls all approvals, merges,
and branch protection.

**Context:** This is a personal project. Requiring 2+ reviewers is not
operationally feasible.

**Implication:** The GitHub account is the single root of trust. If the
account is compromised, all pipeline controls can be bypassed by an attacker
who also has the GPG key. `git verify-commit` provides partial protection
(requires GPG key), but is not a full mitigation.

**Enterprise equivalent:** Mandatory 2+ CODEOWNER approval, SSO with FIDO2
hardware key, external audit log.

---

## ADR-004 — Cosign Keyless Signing

**Decision:** Use Sigstore keyless signing (OIDC-based ephemeral keys) rather
than a long-lived private key.

**Context:** Managing a long-lived private key requires secure key storage
(HSM or encrypted secrets). Keyless signing delegates trust to the OIDC
identity of the GitHub Actions workflow — no key management required.

**Trade-off:** Keyless signing is only as trustworthy as the OIDC provider
(GitHub). If GitHub's OIDC infrastructure is compromised, signatures can be
forged. For a personal project, this risk is accepted. For a production
supply chain, consider a hardware-backed key.

---

## ADR-005 — SBOM Scope (requirements vs. environment)

**Decision:** SBOM generated from `requirements.txt` via `cyclonedx-py
requirements`, not from the live pip environment.

**Context:** `cyclonedx-py environment` captures everything installed in the
CI environment, including transitive dependencies and dev tools. This produces
a more complete picture of what is actually running but reflects the CI
environment state, not the declared project dependencies.

**Trade-off:** `requirements`-based SBOM is more reproducible and maps
directly to the project's declared dependencies. It may miss transitive
dependencies not listed in `requirements.txt`. Accepted for now; revisit
if the dependency tree becomes more complex.

---

## ADR-006 — Trivy `ignore-unfixed: true`

**Decision:** Trivy FS and image scans set `ignore-unfixed: true`.

**Context:** Many CVEs in base images or dependencies have no upstream fix
at time of scan. Failing CI on unfixable vulnerabilities creates permanent
build failures that cannot be resolved by the project owner.

**Trade-off:** Unfixed vulnerabilities are not surfaced in CI output. This
means the pipeline may ship images with known CVEs that have no available
patch. These are tracked and accepted as residual risk until upstream patches
are available.

**Mitigation:** Trivy is run on every build, so newly-fixed CVEs will appear
in subsequent scans automatically.

---

## ADR-007 — Bandit `exit_zero: true`

**Decision:** Bandit is configured with `exit_zero: true`, meaning it does
not fail CI even if issues are found.

**Context:** Bandit is run for informational purposes and to surface findings
in GitHub Security tab. Failing CI on every Bandit finding would produce too
many false positives for a project at this scale.

**Trade-off:** Bandit findings are visible but non-blocking. A developer must
manually review Security tab output. This is a conscious acceptance of lower
enforcement in exchange for signal without noise.

**Revisit condition:** If the codebase grows or findings start including
genuine high-severity issues, switch to `exit_zero: false` with a suppression
list for accepted false positives.

---

## ADR-008 — SBOM, SLSA, and Cosign for Personal Project

**Decision:** Full supply-chain attestation (SBOM, SLSA, Cosign) is included
despite the project being personal and low-risk.

**Rationale:** These controls are included explicitly to practice enterprise
patterns, not because the risk profile demands them. The project serves as a
portfolio demonstration and learning environment for DevSecOps practices.

**Acknowledged redundancy:** For a personal project with no external
consumers, artifact attestation provides no operational benefit. This is
a deliberate choice to build familiarity with the toolchain.

---

## ADR-009 — Vendoring vs Runtime Install

**Decision:** Dependencies vendored via `pip download --require-hashes` into
`wheels/` directory before Docker build.

**Context:** Docker build runs with `--network=none` to prevent exfiltration
during build stage. Runtime `pip install` requires network access and is
incompatible with this constraint.

**Alternatives considered:**
- Runtime pip install → rejected; requires network access during build.
- Pre-built base image with dependencies → rejected; adds maintenance overhead.

**Accepted trade-off:** `wheels/` must be regenerated when dependencies
change. CI handles this automatically via the Vendoring step before build.

---

## ADR-010 — conftest/OPA vs hadolint

**Decision:** Dockerfile policy enforced via conftest with custom Rego
policies rather than hadolint.

**Context:** Supply chain policy requires custom rules: mandatory digest
pinning, prohibition of curl/wget in RUN instructions.

**Alternatives considered:**
- hadolint → rejected; fixed ruleset without custom supply chain policy support.

**Accepted trade-off:** Fewer built-in Dockerfile best practice checks
compared to hadolint. Custom rules cover only explicitly declared policies.