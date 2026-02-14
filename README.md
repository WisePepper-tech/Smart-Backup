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