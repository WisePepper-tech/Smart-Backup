## DISCLAIMER:

This tool is provided as-is. Always test backups before relying on them in production.

## 1. Project Description

Smart-Backup is a security-focused local backup utility with optional compression and AEAD encryption.

## 2. Key Features

- Versioned backup structure

- JSON metadata tracking

- Optional compression + padding

- Optional AEAD encryption (ChaCha20-Poly1305)

- Deterministic restore modes

- Integrity verification (SHA-256)

## 3. Architecture Overview

- Single storage directory

- Project-based versioning

- Timestamped snapshots

- Metadata-driven restore

## 4. Security Model

- No telemetry

- No remote communication

- Encryption keys never leave local machine

- Restore possible in raw or decrypted mode

## 5. Technical Workflow

The backup process follows a strict pipeline to ensure data integrity and confidentiality:

1. **Scanning**: `scanner.py` generates SHA-256 hashes for all source files.
2. **Compression**: Optional Zlib compression (skipped for media/archives).
3. **Padding**: Random noise added to reach 256-bit block alignment (Traffic Analysis protection).
4. **Encryption**: ChaCha20-Poly1305 AEAD encryption with a unique salt.
5. **Persistence**: Objects are stored in a Content-Addressable structure (`/objects/xx/hash`).