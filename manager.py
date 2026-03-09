import json
import logging
import zlib
import hashlib
import os
from crypter import FileCrypter
from datetime import datetime
from pathlib import Path
from classes import ScanResult, ProgressEvent, CopyResult
from utils import show_progress
from hasher import get_file_hash
from typing import Callable, Optional

MANIFEST_FILE = "manifest.json"

logger = logging.getLogger(__name__)

NON_COMPRESSIBLE = {
    ".zip",
    ".7z",
    ".rar",
    ".gz",
    ".tar",  # Archives
    ".mp4",
    ".mkv",
    ".avi",
    ".mov",  # Movie
    ".mp3",
    ".wav",
    ".flac",  # Audio
    ".jpg",
    ".jpeg",
    ".png",  # Photo
    ".docx",
    ".xlsx",
    ".pptx",  # Docs MS Office
    ".pdf",
}


class BackupManager:
    def __init__(self, backup_base_path: Path):
        self.backup_base = backup_base_path
        self.objects_path = self.backup_base / "objects"

    def _get_object_path(
        self,
        file_hash: str,
        encrypted: bool = False,
        compressed: bool = False,
        salt: str = "",
    ) -> Path:
        meta = (
            f"{'enc' if encrypted else 'raw'}_{'zip' if compressed else 'nozip'}_{salt}"
        )
        store_hash = hashlib.sha256((file_hash + meta).encode()).hexdigest()
        return self.objects_path / store_hash[:2] / store_hash

    def _add_padding(self, data: bytes, block_size: int = 256) -> bytes:
        data_len = len(data).to_bytes(4, byteorder="big")
        pad_len = block_size - (len(data) + 4) % block_size
        padding = os.urandom(pad_len)
        return data_len + data + padding

    def _remove_padding(self, padded_data: bytes) -> bytes:
        if len(padded_data) < 4:
            return padded_data
        data_len = int.from_bytes(padded_data[:4], byteorder="big")
        return padded_data[4 : 4 + data_len]

    def _process_object(
        self, path, f_hash, compress, should_compress, crypter, after_obj_created
    ):
        """Processes a single file: compress, pad, encrypt, save. Returns (copied, skipped)."""
        current_salt = crypter.salt.hex() if crypter else ""
        obj_path = self._get_object_path(
            f_hash,
            encrypted=bool(crypter),
            compressed=compress,
            salt=current_salt,
        )
        if obj_path.exists():
            return 0, 1  # skipped

        obj_path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "rb") as f_in:
            data = f_in.read()
        if should_compress:
            data = zlib.compress(data, level=6)
        if should_compress or crypter:
            data = self._add_padding(data)
        if crypter:
            data = crypter.encrypt(data)
        with open(obj_path, "wb") as f_out:
            f_out.write(data)
        if after_obj_created:
            after_obj_created(obj_path.relative_to(self.backup_base), data)
        return 1, 0  # copied

    def _decode_object(
        self,
        data,
        crypter,
        salt_hex,
        file_specific_compression,
        decrypt_data,
        decompress_data,
    ):
        """Decrypt → unpad → decompress."""
        if decrypt_data and crypter:
            data = crypter.decrypt(data)  # raises on wrong password

        if (decrypt_data or not salt_hex) and decompress_data:
            if file_specific_compression or salt_hex:
                try:
                    data = self._remove_padding(data)
                except Exception:
                    pass

        if decompress_data and file_specific_compression:
            try:
                data = zlib.decompress(data)
            except Exception:
                logger.error("Decompression error")
        return data

    def create_backup(
        self,
        scan_result: ScanResult,
        source_path: Path,
        project_name: str,
        comment: str = "",
        compress: bool = True,
        password=None,
        forced_salt=None,
        after_obj_created: Optional[Callable[[Path, bytes], None]] = None,
    ) -> CopyResult:
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        snapshot_dir = self.backup_base / project_name / timestamp
        snapshot_dir.mkdir(parents=True, exist_ok=True)
        salt_bytes = bytes.fromhex(forced_salt) if forced_salt else None
        crypter = FileCrypter(password, salt=salt_bytes) if password else None

        copied_count, skipped_count, errors = 0, 0, 0
        manifest_files = {}

        for path, f_hash in scan_result.file_hashes.items():
            should_compress = compress and (path.suffix.lower() not in NON_COMPRESSIBLE)
            try:
                c, s = self._process_object(
                    path, f_hash, compress, should_compress, crypter, after_obj_created
                )
                copied_count += c
                skipped_count += s
            except Exception as e:
                logger.error(f"Failed to process {path}: {e}")
                errors += 1
                continue

            rel_path = path.relative_to(source_path)
            # Important: write flag "compressed" in the manifest for each file
            manifest_files[str(rel_path)] = {
                "hash": f_hash,
                "compressed": should_compress,
            }

            show_progress(
                ProgressEvent(
                    processed=copied_count + skipped_count,
                    total=scan_result.total_files,
                    current_file=path.name,
                )
            )

        manifest = {
            "info": {
                "timestamp": timestamp,
                "salt": crypter.salt.hex() if crypter else None,
                "encryption": "ChaCha20-Poly1305" if crypter else None,
                "comment": comment,
                "total_files": scan_result.total_files,
                "compression_enabled": compress,  # A common flag for the entire version
            },
            "files": manifest_files,
        }

        manifest_path = snapshot_dir / MANIFEST_FILE
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=4, ensure_ascii=False)

        if after_obj_created:
            manifest_data = json.dumps(manifest, indent=4, ensure_ascii=False).encode(
                "utf-8"
            )
            after_obj_created(
                manifest_path.relative_to(self.backup_base), manifest_data
            )

        print()
        return CopyResult(
            copied=copied_count,
            skipped=skipped_count,
            errors=errors,
            quantity_versions=0,
        )

    def restore_version(
        self,
        project_name: str,
        version_name: str,
        target_path: Path,
        password=None,
        decrypt_data=True,
        decompress_data=True,
        fetch_proxy: Optional[Callable[[Path], bytes]] = None,
    ):
        # 1. Path for safe restore
        safe_restore_path = target_path / f"{project_name}_{version_name}"
        safe_restore_path.mkdir(parents=True, exist_ok=True)

        manifest_path = self.backup_base / project_name / version_name / MANIFEST_FILE
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)

        salt_hex = manifest["info"].get("salt")
        crypter = (
            FileCrypter(password, bytes.fromhex(salt_hex))
            if salt_hex and password
            else None
        )

        total_files = manifest["info"]["total_files"]
        success_count = 0
        error_list = []
        results = {}
        print(f"\n[RESTORE] Restoring {total_files} files to: {safe_restore_path}")

        global_compression = manifest["info"].get("compression_enabled", False)

        for i, (rel_path_str, info) in enumerate(manifest["files"].items(), 1):
            file_hash = info["hash"]
            is_encrypted = bool(salt_hex)
            obj_path = self._get_object_path(
                file_hash,
                encrypted=is_encrypted,
                compressed=global_compression,
                salt=salt_hex or "",
            )

            file_specific_compression = info.get("compressed", False)

            dest_path = safe_restore_path / rel_path_str
            results[rel_path_str] = False

            try:
                dest_path.parent.mkdir(parents=True, exist_ok=True)

                # Read data from "objects"
                if fetch_proxy:
                    data = fetch_proxy(obj_path.relative_to(self.backup_base))
                else:
                    with open(obj_path, "rb") as f_in:
                        data = f_in.read()

                data = self._decode_object(
                    data,
                    crypter,
                    salt_hex,
                    file_specific_compression,
                    decrypt_data,
                    decompress_data,
                )

                # Write clean data
                final_path = (
                    dest_path
                    if (decrypt_data and decompress_data)
                    else dest_path.with_suffix(dest_path.suffix + ".raw")
                )
                with open(final_path, "wb") as f_out:
                    f_out.write(data)

                success_count += 1
                results[rel_path_str] = True

                # --- VERIFY ---
                if decrypt_data and decompress_data:
                    if get_file_hash(final_path) != info["hash"]:
                        print(f"ALARM: {rel_path_str} damaged!")

                show_progress(
                    ProgressEvent(
                        processed=i, total=total_files, current_file=rel_path_str
                    )
                )

            except PermissionError as e:
                print(f"\n[!!!] {e}")
                return results
            except Exception as e:
                error_list.append(f"{rel_path_str}: {e}")

        print(f"\n\n=== The results of the restoration ===")
        print(f"Successfully:   {success_count} / {total_files}")
        print()
        if error_list:
            print(f"Errors:    {len(error_list)}")
            print("Error details are saved in the log.")
            for err in error_list[:5]:
                logger.error(err)

        return results

    def _version_matches(self, v_dir: Path, date_hint: str | None) -> bool:
        if not v_dir.is_dir():
            return False
        if not (v_dir / MANIFEST_FILE).exists():
            return False
        if date_hint and date_hint not in v_dir.name:
            return False
        return True

    def _find_target_versions(
        self, project_name: str = None, date_hint: str = None
    ) -> list[Path]:
        if not self.backup_base.exists():
            return []

        search_dirs = (
            [self.backup_base / project_name]
            if project_name
            else [
                d
                for d in self.backup_base.iterdir()
                if d.is_dir() and d.name != "objects"
            ]
        )

        versions = [
            v_dir
            for p_dir in search_dirs
            if p_dir.exists()
            for v_dir in p_dir.iterdir()
            if self._version_matches(v_dir, date_hint)
        ]

        versions.sort(key=lambda x: x.name)
        return versions

    def verify_password(self, project_name, version_name, password, fetch_proxy=None):
        manifest_path = self.backup_base / project_name / version_name / MANIFEST_FILE
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)

        salt_hex = manifest["info"].get("salt")
        if not salt_hex:
            return True  # No salt - no encrypt

        # Try decrypt first file
        files = manifest.get("files", {})
        if not files:
            return True
        first_rel_path = next(iter(files))
        info = manifest["files"][first_rel_path]

        is_compressed_globally = manifest["info"].get("compression_enabled", False)

        obj_path = self._get_object_path(
            info["hash"],
            encrypted=True,
            compressed=is_compressed_globally,
            salt=salt_hex,
        )

        try:
            if fetch_proxy:
                data = fetch_proxy(obj_path.relative_to(self.backup_base))
            else:
                if not obj_path.exists():
                    logger.error(
                        "Verification failed: Object %s not found.", obj_path.name
                    )
                    return False
                with open(obj_path, "rb") as f:
                    data = f.read()

            test_crypter = FileCrypter(password, bytes.fromhex(salt_hex))
            test_crypter.decrypt(data)
            return True
        except Exception as e:
            # If this is an authentication error ChaCha20Poly1305, False is returned
            logger.debug(f"Decryption check failed: {e}")
            return False
