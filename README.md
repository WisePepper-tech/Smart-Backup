# 🏗 Smart-Backup: Professional Data Snapshots
Smart-Backup is a lightweight yet powerful backup utility built on the principles of data immutability and cryptographic security. It combines efficient deduplication with the reliability of bank-grade encryption.

### 🛡 Security Features
AEAD Encryption: Uses the ChaCha20-Poly1305 algorithm — a modern standard providing both data confidentiality and authenticity.

Traffic Analysis Protection: Automatic padding to 256-bit block alignment, masking the exact file sizes from potential side-channel analysis.

Zero-Knowledge: Your passwords and keys never leave your local machine and are never stored in plaintext.

### 🚀 Key Features
Intelligent Deduplication: Utilizing Content-Addressable Storage (CAS), identical files across different projects are stored only once.

Cloud-Native: Full support for S3-compatible storage (MinIO, AWS, Google Cloud) out of the box.

Integrity Guard: Every restoration is verified against its original SHA-256 hash.

Flexible Recovery: Supports "Technical" recovery mode (restoring encrypted/compressed blobs) for secure migration between servers.

### 🛠 Technical Workflow
The data processing follows a strict pipeline:

Scanning: scanner.py generates SHA-256 hashes for all source files.

Compression: Zlib compression (automatically skipped for media and archives).

Obfuscation: Padding applied for block alignment and security.

Encryption: AEAD encryption using a unique salt.

Persistence: Objects are stored in a structured /objects/xx/hash hierarchy.

# 💻 Installation & Usage
Bash
Clone the repository
git clone https://github.com/WisePepper-tech/Smart-Backup

### 🚀 Usage Guide
This project is a high-security backup system with automatic S3 (MinIO) synchronization. It is designed with a Security-First approach, ensuring data integrity and environment isolation.

### 🛠 Prerequisites
Docker and Docker Compose.

An .env file in the root directory (refer to example.env).

Python (required only for the initial local dependency vendoring).

### ⚡ Quick Start
The easiest way to launch the system is using the provided Makefile. It automates the environment preparation, image building, and container orchestration: "make run"

How it works: The script checks for dependencies, builds the Docker image if the source code has changed, starts the MinIO infrastructure, and prompts you for the source data path (Windows or Linux).

### 🛡 Security & CI/CD Architecture
This project implements a Hardened DevSecOps Pipeline:

1) Supply Chain Protection: All base images are pinned using immutable SHA256 digests. Dependencies are strictly verified against pre-computed hashes in requirements.txt.

2) Environment Isolation:

- Vendoring: Dependencies are downloaded locally and injected into the image.

- Network Sandbox: The Docker build process runs with --network=none to prevent unauthorized external calls or data exfiltration during build time.

3) Principle of Least Privilege: The application runs under a non-privileged appuser (UID 10001). Access is restricted to /app and the mounted /data volume.

4) Artifact Provenance: Images in CI are signed via Cosign and include SLSA Attestations and SBOM (Software Bill of Materials) for full transparency.

### Command and Description
make run,"Standard launch: Prepare, build, and run interactively."
make build,Rebuild the Docker image (only if source files are modified).
make ci-build,Unbiased build: Rebuild from scratch with no cache and forced pull.
make down,Stop all containers and MinIO infrastructure.
make clean,"Full Reset: Remove images, MinIO volumes, and the wheels folder."
make logs,View MinIO logs for connection troubleshooting.

### ✅ Final Check of your Dockerfile
Your final Dockerfile is 100% correct.

The ARG PIP_FIND_LINKS is properly defined.

The HEALTHCHECK logic is robust enough for both local and cloud modes.

The chown commands before switching to USER appuser ensure no permission bottlenecks.

OR you can use "python main.py" for start program without Docker. Need MinIO if you want backup to cloud.

### ⚙️ Configuration
Create a `.env` file in the root directory. Below is a secure template:

```env

Storage Mode: 1 = Local Only, 2 = Cloud Sync (S3)
STORAGE_MODE=1

S3 Configuration (Required if STORAGE_MODE=2):
S3_ENDPOINT=http://minio:9000
S3_ACCESS_KEY=your_secure_access_key
S3_SECRET_KEY=your_secure_secret_key
S3_BUCKET_NAME=smart-backups
S3_REGION=us-east-1

Encryption (Ensure this key is backed up elsewhere!)
ChaCha20-Poly1305 AEAD via Python cryptography library

App Settings
LOG_LEVEL=INFO
DOCKER_MODE=true

```

# Install dependencies
pip install -r requirements.txt

### ⚙️ Configuration 
The project includes an automated test suite verifying:

Salt Isolation: Ensuring different salts produce unique objects.

Deduplication: Validating storage efficiency for identical files.

Integrity: Full encryption/decryption cycle verification.

Access Validation: Pre-flight password checks before file operations.

# ⚖️ License & Disclaimer
Provided "as-is" under the MIT License. Always verify your backups before relying on them for critical data.