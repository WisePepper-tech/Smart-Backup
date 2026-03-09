# 🏗 Smart-Backup: Professional Data Snapshots

Smart-Backup is a lightweight yet powerful backup utility built on the principles of data immutability and cryptographic security. It combines efficient deduplication with ChaCha20-Poly1305 encryption and full S3-compatible cloud sync.

---

## 🛡 Security Features

**AEAD Encryption:** ChaCha20-Poly1305 — a modern standard providing both data confidentiality and integrity verification.

**Traffic Analysis Protection:** Automatic padding to 256-byte block alignment, masking exact file sizes from side-channel analysis.

**Zero-Knowledge:** Passwords and keys never leave your local machine and are never stored in plaintext.

---

## 🚀 Key Features

**Intelligent Deduplication:** Content-Addressable Storage (CAS) — identical files across different projects are stored only once.

**Cloud-Native:** Full support for S3-compatible storage (MinIO, AWS S3, Yandex Object Storage, and any S3-compatible endpoint).

**Integrity Guard:** Every restoration is verified against its original SHA-256 hash.

**Flexible Recovery:** Supports standard and "technical" recovery modes — useful for secure migration between servers.

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
# Edit .env with your settings
make run
```

---

## 🚦 Two Ways to Run

Smart-Backup supports two launch modes with different path handling behaviour.

### Option A — `make run` (recommended, Docker)

```bash
make run
```

Makefile asks for a **Windows path** before starting the container:

```
Enter full Windows path: C:/MyFiles
```

This path is **mounted as `/data` inside the container**. The application then runs in an isolated Docker environment where all file access is restricted to `/data`.

```
C:/MyFiles  →  mounted as  →  /data  (inside container)
```

Inside the program, when asked for a source or restore path — just press **Enter** to use `/data`, or enter a subfolder like `/data/docs`.

**To back up one folder and restore to another**, mount a common parent:

```
Enter full Windows path: C:/
→ /data/MyFiles    (backup source)
→ /data/Restored   (restore target)
```

This way both paths are accessible inside the container without restarting.

> **Why this exists:** The `/data` boundary is a security sandbox. `get_safe_path()` in the code actively prevents path traversal attacks (e.g. `../../etc/passwd`) by validating that all paths stay within `/data`. Mounting only what you need limits the attack surface.

---

### Option B — `python main.py` (direct, no Docker)

```bash
python main.py
```

No mounting, no `/data` sandbox — the program runs directly on your machine. You can enter any local path at runtime:

```
Enter path to source: C:/MyFiles
Where to restore?:    C:/Restored
```

**Cloud (MinIO) with direct launch:** MinIO runs as a Docker container, but its API port `9000` is exposed to the host. The code automatically detects that `DOCKER_MODE` is not set and replaces the internal `minio` hostname with `localhost`:

```
S3_ENDPOINT=http://minio:9000  →  auto-replaced to  →  http://localhost:9000
```

So both `make run` and `python main.py` connect to the **same MinIO instance** and the same bucket — your data is in one place regardless of how you launched the app.

> **Note:** MinIO must be running before using cloud mode with direct launch. Start it with `docker-compose up minio -d` or use `make run` which handles this automatically.

---

## ⚙️ Configuration

Create a `.env` file in the root directory:

```env
# S3 Configuration (required for cloud mode)
S3_ENDPOINT=http://minio:9000
S3_ACCESS_KEY=your_secure_access_key
S3_SECRET_KEY=your_secure_secret_key
S3_BUCKET=smart-backups

# App Settings
LOG_LEVEL=INFO
DOCKER_MODE=true
```

> `S3_REGION` is not used by MinIO but may be required by other S3-compatible endpoints.

---

## 📖 Usage Scenarios

### Scenario 1 — Simple local backup (no encryption, no compression)

Useful for fast snapshots of already-compressed data (images, archives, video).

```
[1] New Backup
Project name: my-photos
Compress? (y/n): n
Password (Enter for none): ⏎
```

Result: files are stored as-is in the CAS object store. Identical files across backups are deduplicated automatically.

---

### Scenario 2 — Encrypted + compressed backup

The standard secure workflow for source code, documents, or any text-heavy project.

```
[1] New Backup
Project name: work-docs
Compress? (y/n): y
Password: ••••••••
(The password is not displayed when you enter it)
```

Processing pipeline:
1. **Scan** — SHA-256 hash generated per file
2. **Compress** — Zlib (skipped automatically for `.jpg`, `.mp4`, `.zip`, etc.)
3. **Pad** — random padding added for block alignment
4. **Encrypt** — ChaCha20-Poly1305 with unique salt per backup session
5. **Store** — written to `objects/xx/hash`

> ⚠️ If you change compression or encryption settings on the next backup of the same project, Smart-Backup will warn you and show the previous parameters before proceeding.

---

### Scenario 3 — Changing backup parameters mid-project

You previously backed up `work-docs` with compression enabled. Now you want to disable it.

```
[1] New Backup
Project name: work-docs
Compress? (y/n): n   ← changed from previous

⚠ Warning: previous backup used compress=YES, encrypt=YES
   Current settings:  compress=NO,  encrypt=YES
   Continue? (y/n):
```

Both versions coexist. Each version stores its own parameters in `manifest.json`.

---

### Scenario 4 — Standard restore

Restores files to their original state in a safe subfolder.

```
[2] Restore
Project name: work-docs
Select version: 2025-03-09_00-24-17
Password: ••••••••
(The password is not displayed when you enter it)
```

Output path: `<restore_target>/work-docs_2025-03-09_00-24-17/`

All files are decrypted, decompressed, and verified against their original SHA-256 hash. A mismatch triggers an `ALARM` message.

---

### Scenario 5 — Technical restore (raw blobs)

Useful for server migration or forensic access — returns the encrypted/compressed blobs without processing.

```
[2] Restore
Project name: work-docs
Select version: 2025-03-09_00-24-17
Recovery mode: 2 (Technical)
```

Output: `report.docx.raw`, `notes.txt.raw`

The `.raw` extension signals the file has not been processed. The filename is the object hash — with no indication of content. Removing `.raw` manually restores the original extension and the file opens normally (if stored unencrypted).

---

### Scenario 6 — Cloud sync (S3 / MinIO)

Set storage mode to `2` when prompted. After each backup, objects and manifest are automatically uploaded to S3. Restore works transparently — objects are fetched from the bucket via `fetch_proxy` if not found locally.

```
Storage mode: 1. Local  2. Cloud (MinIO) [1]: 2

[1] New Backup
Project name: offsite-archive
→ Uploading objects/a3/a3f8c1... ✓
→ Uploading offsite-archive/2025-03-09/manifest.json ✓
```

---

## 🔧 Makefile Commands

| Command | Description |
|---|---|
| `make run` | Standard launch: prepare, build, and run interactively |
| `make build` | Rebuild the Docker image (only if source files changed) |
| `make local-build` | Full rebuild from scratch, no cache, forced pull |
| `make down` | Stop all containers and MinIO infrastructure |
| `make clean` | Full reset: remove images, MinIO volumes, and wheels folder |
| `make logs` | View MinIO logs for connection troubleshooting |

---

## 🛡 Security & CI/CD Architecture

**Supply Chain Protection:** All base images are pinned using immutable SHA256 digests. Dependencies are verified against pre-computed hashes in `requirements.txt`.

**Environment Isolation:**
- Vendoring: dependencies are downloaded locally and injected into the image
- Network Sandbox: Docker build runs with `--network=none` to prevent exfiltration

**Principle of Least Privilege:** Application runs as non-privileged `appuser` (UID 10001), restricted to `/app` and the mounted `/data` volume.

**Artifact Provenance:** Images are signed via Cosign and include SLSA Attestations and SBOM (Software Bill of Materials).

---

## ✅ Tests

```bash
python -m pytest
```

The test suite covers:

- Full encryption + decryption cycle with integrity verification
- Deduplication: identical files produce a single object
- Salt isolation: different salts produce different objects for the same file
- Directory tree backup and restore (nested paths)
- Non-compressible file handling (`.jpg`, `.mp4`, etc.)
- Ignored extensions (`.tmp`, `.log`, `.bak`, `.swp`) are excluded from backups
- Cloud manager: full mock coverage of S3 operations
- Main flow: all branches of backup, restore, and path handling

---

## ⚖️ License

MIT License. Provided "as-is". Always verify your backups before relying on them for critical data.