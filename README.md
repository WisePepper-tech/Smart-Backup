🏗 Smart-Backup: Professional Data Snapshots
Smart-Backup is a lightweight yet powerful backup utility built on the principles of data immutability and cryptographic security. It combines efficient deduplication with the reliability of bank-grade encryption.

🛡 Security Features
AEAD Encryption: Uses the ChaCha20-Poly1305 algorithm — a modern standard providing both data confidentiality and authenticity.

Traffic Analysis Protection: Automatic padding to 256-bit block alignment, masking the exact file sizes from potential side-channel analysis.

Zero-Knowledge: Your passwords and keys never leave your local machine and are never stored in plaintext.

🚀 Key Features
Intelligent Deduplication: Utilizing Content-Addressable Storage (CAS), identical files across different projects are stored only once.

Cloud-Native: Full support for S3-compatible storage (MinIO, AWS, Google Cloud) out of the box.

Integrity Guard: Every restoration is verified against its original SHA-256 hash.

Flexible Recovery: Supports "Technical" recovery mode (restoring encrypted/compressed blobs) for secure migration between servers.

🛠 Technical Workflow
The data processing follows a strict pipeline:

Scanning: scanner.py generates SHA-256 hashes for all source files.

Compression: Zlib compression (automatically skipped for media and archives).

Obfuscation: Padding applied for block alignment and security.

Encryption: AEAD encryption using a unique salt.

Persistence: Objects are stored in a structured /objects/xx/hash hierarchy.

💻 Installation & Usage
Bash
# Clone the repository
git clone https://github.com/WisePepper-tech/Smart-Backup
cd smart-backup

# Install dependencies
pip install -r requirements.txt

# Launch the Control Panel
python main.py

🧪 Quality Assurance
The project includes an automated test suite verifying:

Salt Isolation: Ensuring different salts produce unique objects.

Deduplication: Validating storage efficiency for identical files.

Integrity: Full encryption/decryption cycle verification.

Access Validation: Pre-flight password checks before file operations.

⚖️ License & Disclaimer
Provided "as-is" under the MIT License. Always verify your backups before relying on them for critical data.