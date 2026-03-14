# 🏗 Smart-Backup: Professional Data Snapshots

Smart-Backup is a lightweight yet powerful backup utility built on the principles of data immutability and cryptographic security. It combines efficient deduplication with ChaCha20-Poly1305 encryption and full S3-compatible cloud sync.

---

## 🛡 Security Features

**AEAD Encryption:** ChaCha20-Poly1305 — a modern standard providing both data confidentiality and integrity verification.

**Argon2id Key Derivation:** Passwords are stretched using Argon2id (OWASP-recommended, 64 MB memory, 3 iterations) — resistant to GPU and side-channel attacks. KDF parameters are stored in each backup manifest, ensuring future-proof decryption even if defaults change.

**Traffic Analysis Protection:** Automatic padding to 256-byte block alignment, masking exact file sizes from side-channel analysis.

**Zero-Knowledge:** Passwords and keys never leave your local machine and are never stored in plaintext.

---

## 🚀 Key Features

**Intelligent Deduplication:** Content-Addressable Storage (CAS) — identical files across different projects are stored only once.

**Cloud-Native:** Full support for S3-compatible storage (MinIO, AWS S3, Yandex Object Storage, and any S3-compatible endpoint).

**Integrity Guard:** Every restoration is verified against its original SHA-256 hash.

**Flexible Recovery:** Supports standard and "technical" recovery modes — useful for secure migration between servers.

**REST API:** Optional FastAPI service exposing backup and listing endpoints, secured with API key authentication and per-IP rate limiting.

---

## 🛠 Prerequisites

- Docker and Docker Compose
- An `.env` file in the root directory (see `example.env`)
- Python 3.13+ (required only for running without Docker)

> **Windows:** Install Make first: `winget install GnuWin32.Make`

---

## ⚡ Quick Start

```bash
git clone https://github.com/WisePepper-tech/Smart-Backup
cd Smart-Backup
cp example.env .env
# Edit .env with your credentials and API_KEY
make run
```

---

## 🚦 Three Ways to Run

### Option A — `make run` (recommended, Docker)

```bash
make run
```

Makefile asks for a **Windows path** before starting the container:

```
Enter full Windows path: C:/MyFiles
```

This path is **mounted as `/data` inside the container**. All file access is restricted to `/data`.

```
C:/MyFiles  →  mounted as  →  /data  (inside container)
```

Inside the program, press **Enter** to use `/data`, or enter a subfolder like `/data/docs`.

**To back up one folder and restore to another**, mount a common parent:

```
Enter full Windows path: C:/
→ /data/MyFiles    (backup source)
→ /data/Restored   (restore target)
```

> **Why this exists:** The `/data` boundary is a security sandbox. `get_safe_path()` actively prevents path traversal attacks by validating that all paths stay within `/data`.

---

### Option B — `python main.py` (direct, no Docker)

```bash
python main.py
```

No mounting, no `/data` sandbox — the program runs directly on your machine:

```
Enter path to source: C:/MyFiles
Where to restore?:    C:/Restored
```

**Cloud (MinIO) with direct launch:** The code automatically replaces the internal `minio` hostname with `localhost`:

```
S3_ENDPOINT=http://minio:9000  →  auto-replaced to  →  http://localhost:9000
```

> **Note:** Start MinIO first with `docker-compose up minio -d` or use `make run`.

---

### Option C — REST API (FastAPI)

```bash
docker-compose up minio api -d
```

The API runs on port `8000`. All endpoints require the `X-API-Key` header matching `API_KEY` from `.env`.

**Endpoints:**

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Health check (no auth required) |
| `GET` | `/backups?project=name` | List backup versions |
| `POST` | `/backup` | Create a new backup |

**Example — create backup:**

```bash
curl -X POST http://localhost:8000/backup \
  -H "X-API-Key: your_api_key" \
  -H "Content-Type: application/json" \
  -d '{"source_path": "/data/docs", "project_name": "my-docs", "compress": true}'
```

**Example — list backups:**

```bash
curl http://localhost:8000/backups \
  -H "X-API-Key: your_api_key"
```

**Path security:** `source_path` must be inside `ALLOWED_SOURCE_PATH` (default: `/data`). `project_name` is validated against `[a-zA-Z0-9_-]{1,64}`. Invalid paths return HTTP 422.

**Rate limits:** `GET /backups` — 30 req/min, `POST /backup` — 10 req/min per IP.

---

## ⚙️ Configuration

```env
# S3 Configuration (required for cloud mode)
S3_ENDPOINT=http://minio:9000
S3_ACCESS_KEY=your_secure_access_key
S3_SECRET_KEY=your_secure_secret_key
S3_BUCKET=smart-backups

# API (required when running the API service)
API_KEY=your_generated_api_key
ALLOWED_SOURCE_PATH=/data

# App Settings
BACKUP_PATH=/data
DOCKER_MODE=true
```

**Generate a secure API key:**

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

---

## 📖 Usage Scenarios

### Scenario 1 — Simple local backup (no encryption, no compression)

```
[1] New Backup
Project name: my-photos
Compress? (y/n): n
Password (Enter for none): ⏎
```

Files are stored as-is in the CAS object store. Identical files deduplicated automatically.

---

### Scenario 2 — Encrypted + compressed backup

```
[1] New Backup
Project name: work-docs
Compress? (y/n): y
Password: ••••••••
```

Processing pipeline:
1. **Scan** — SHA-256 hash per file
2. **Compress** — Zlib (skipped for `.jpg`, `.mp4`, `.zip`, etc.)
3. **Pad** — random padding to 256-byte block alignment
4. **Encrypt** — ChaCha20-Poly1305 with Argon2id-derived key and unique salt
5. **Store** — written to `objects/xx/hash`

KDF parameters (`time_cost`, `memory_cost`, `parallelism`) are recorded in `manifest.json` alongside the salt — ensuring correct decryption regardless of future parameter changes.

> ⚠️ If you change compression or encryption settings on the next backup of the same project, Smart-Backup will warn you before proceeding.

---

### Scenario 3 — Changing backup parameters mid-project

```
[1] New Backup
Project name: work-docs
Compress? (y/n): n   ← changed from previous

⚠ Warning: previous backup used compress=YES, encrypt=YES
   Current settings:  compress=NO,  encrypt=YES
   Continue? (y/n):
```

Both versions coexist. Each stores its own parameters in `manifest.json`.

---

### Scenario 4 — Standard restore

```
[2] Restore
Project name: work-docs
Select version: 2025-03-09_00-24-17
Password: ••••••••
```

Files are decrypted, decompressed, and verified against their original SHA-256 hash. A mismatch triggers an `ALARM` message.

Output: `<restore_target>/work-docs_2025-03-09_00-24-17/`

---

### Scenario 5 — Technical restore (raw blobs)

```
[2] Restore
Project name: work-docs
Recovery mode: 2 (Technical)
```

Returns encrypted/compressed blobs without processing. Output files get a `.raw` extension.

---

### Scenario 6 — Cloud sync (S3 / MinIO)

```
Storage mode: 1. Local  2. Cloud (MinIO) [1]: 2

[1] New Backup
Project name: offsite-archive
→ Uploading objects/a3/a3f8c1... ✓
→ Uploading offsite-archive/2025-03-09/manifest.json ✓
```

---

### Scenario 7 — Portable restore (different machine)

After `git pull` on a new machine with the same `.env`:

```
Storage mode: 2 (Cloud)
[2] Restore
Password: ••••••••  ← same password as during backup
```

Argon2id re-derives the identical key from password + salt (read from manifest). All data decrypts correctly.

---

## 🔧 Makefile Commands

|       Command      |                         Description                         |
|--------------------|-------------------------------------------------------------|
| `make run`         | Standard launch: prepare, build, and run interactively      |
| `make build`       | Rebuild the Docker image (only if source files changed)     |
| `make api`         | Start MinIO + API service in background                     |
| `make local-build` | Full rebuild from scratch, no cache, forced pull            |
| `make down`        | Stop all containers                                         |
| `make clean`       | Full reset: remove images, MinIO volumes, and wheels folder |
| `make logs`        | View MinIO logs for connection troubleshooting              |

---

## 🛡 Security & CI/CD Architecture

**Supply Chain Protection:** Base images pinned via immutable SHA256 digests. Dependencies verified against pre-computed hashes (`requirements.txt`, `requirements-dev.txt`, `requirements-sbom.txt`).

**Hermetic Build:** Docker image built with `--network=none` — dependencies vendored before build, no network access during compilation.

**Principle of Least Privilege:** Application runs as non-privileged `appuser` (UID 10001), restricted to `/app` and the mounted `/data` volume.

**CI Pipeline (GitHub Actions):**
- `tests` — pytest with coverage report
- `checks` — GPG commit verification, license scan, TruffleHog, Gitleaks, CodeQL, SonarQube
- `security` — pip-audit (CVE check for all requirement files), Bandit, Semgrep, Trivy FS
- `dependency_guard` — blocks PRs that modify requirements without explicit review
- `build` — hermetic Docker build, Trivy image scan, push to GHCR
- `attest_and_signing` — SBOM generation (CycloneDX), SLSA provenance, Cosign keyless signing and verification

**Artifact Provenance:** Images signed via Cosign with SLSA attestations and SBOM attached to the registry manifest.

---

## ✅ Tests

```bash
python -m pytest
```

Coverage includes: encryption/decryption cycle, deduplication, salt isolation, directory tree backup/restore, non-compressible file handling, ignored extensions, cloud manager (full S3 mock), API validators (path whitelist, project name regex, comment length), and all branches of the main CLI flow.

---

> **Storage tip:** For consistent access across all launch methods (CLI, Docker, API),
> always use cloud mode (Storage mode: 2). Local mode creates isolated storage
> per launch method and is recommended for testing only.

## ⚖️ License

MIT License. Provided "as-is". Always verify your backups before relying on them for critical data.
