# Incident Response Plan

This document defines response procedures for security events in the
Smart-Backup CI pipeline. It is written for a single-operator project
but follows the structure used in production environments.

---

## Severity Levels

| Level | Definition | Example |
|-------|-----------|---------|
| P1 — Critical | Active compromise; data or artifact integrity at risk | GitHub account hijacked; malicious image pushed to GHCR |
| P2 — High | Confirmed vulnerability or control bypass; no active exploitation | Known CVE in shipped image; leaked token detected in logs |
| P3 — Medium | Potential weakness identified; no confirmed exploitation | Dependency with unpatched CVE; unsigned commit merged |
| P4 — Low | Informational finding; no immediate action required | Bandit warning; unfixed Trivy finding |

---

## Scenario 1 — Cosign Verify Fails on Pushed Image

**Symptom:** The `Cosign verify` step in `attest_and_signing` exits non-zero.
This means the image in GHCR does not have a valid signature matching the
expected OIDC identity of this workflow.

**Immediate actions:**

1. Do not promote or deploy this image.
2. Check the GitHub Actions log for the exact error:
   - `MANIFEST_UNKNOWN` → image digest does not exist in registry (push failed silently)
   - `no matching signatures` → image was pushed but not signed, or signed by wrong identity
   - `invalid signature` → signature exists but does not verify against the transparency log
3. If the digest in the log differs from what was built, treat as **P1** (image tampering).
4. Delete the suspect image from GHCR:
   ```bash
   gh api \
     --method DELETE \
     /user/packages/container/smart-backup/versions/<version-id>
   ```
5. Re-run the pipeline from a clean commit to produce a new signed artifact.
6. Investigate why the signature failed before re-deploying.

**Revocation:** Sigstore keyless signatures cannot be revoked individually.
If the signing identity (GitHub OIDC) is compromised, file an incident with
GitHub and rotate all tokens. New signatures from the same compromised
workflow should not be trusted even if they verify successfully.

---

## Scenario 2 — Secret Detected in Logs (TruffleHog / Gitleaks Alert)

**Symptom:** TruffleHog or Gitleaks reports a credential in the repository
or CI logs.

**Immediate actions:**

1. Identify the secret type and scope from the scan output.
2. Rotate the secret immediately — do not wait to confirm exploitation:
   - `GITHUB_TOKEN`: auto-expires after workflow run; no manual rotation needed
     unless it was exfiltrated during the run.
   - `SONAR_TOKEN`: revoke in SonarCloud dashboard → generate new token →
     update in GitHub Secrets.
3. If the secret was committed to git history:
   ```bash
   git filter-repo --path <file> --invert-paths
   git push --force
   ```
   Note: `git filter-repo` rewrites history. All forks and clones must be
   re-cloned after this operation.
4. Check GitHub audit log for any API calls made using the exposed token
   during the window between exposure and rotation.
5. If the token had write permissions and API calls are found → escalate to **P1**.

---

## Scenario 3 — Unexpected Dependency Change Detected

**Symptom:** `dependency_guard` job emits a warning. A dependency in
`requirements.txt` changed without a corresponding PR review.

**Actions:**

1. Review the diff:
   ```bash
   git diff origin/main -- requirements.txt
   ```
2. Verify the new package version on PyPI:
   - Check the release date and changelog.
   - Check if the maintainer's account shows unusual activity.
   - Run `pip-audit` locally against the new version.
3. If the change was not intentional (no PR, no local commit) → treat as **P1**
   (possible repository compromise).
4. If intentional: proceed with normal PR review before merging.

---

## Scenario 4 — GitHub Account Compromise Suspected

**Symptom:** Unexpected login notification, unknown sessions in GitHub security
settings, PRs or commits not created by the account owner.

**Immediate actions:**

1. Terminate all active sessions in GitHub Settings → Sessions.
2. Change GitHub password immediately.
3. Review authorized OAuth apps and revoke unknown ones.
4. Review recent Actions runs for unexpected jobs or steps.
5. Rotate all tokens stored in GitHub Secrets:
   - `SONAR_TOKEN` → revoke and regenerate in SonarCloud.
6. Check GHCR for images pushed during the compromise window:
   - Verify signatures against known-good workflow runs.
   - Delete any images that cannot be verified.
7. If GPG key was stored on the compromised machine: revoke it on the keyserver
   and generate a new one. Update the trusted key in the repository.
8. Review branch protection rules and CODEOWNERS to ensure they were not modified.

---

## Routine Maintenance

| Task | Frequency | Notes |
|------|----------|-------|
| Review Trivy findings for newly-fixed CVEs | Weekly | Check `ignore-unfixed` items |
| Rotate `SONAR_TOKEN` | Quarterly | Precautionary rotation |
| Verify action SHA hashes are current | Monthly | Check for new upstream releases |
| Review GitHub audit log | Monthly | Look for unexpected API calls |
| Test GPG commit signing end-to-end | After key changes | Push signed commit, verify CI passes |
| Review Cosign transparency log entries | After each release | Confirm expected workflow identity |
