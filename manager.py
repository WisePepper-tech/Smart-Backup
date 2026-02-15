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

    def create_backup(
        self,
        scan_result: ScanResult,
        source_path: Path,
        project_name: str,
        comment: str = "",
        compress: bool = True,
        password=None,
        forced_salt=None,
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
            current_salt = crypter.salt.hex() if crypter else ""
            obj_path = self._get_object_path(
                f_hash,
                encrypted=bool(password),
                compressed=should_compress,
                salt=current_salt,
            )

            if not obj_path.exists():
                try:
                    obj_path.parent.mkdir(parents=True, exist_ok=True)

                    # Read original
                    with open(path, "rb") as f_in:
                        data = f_in.read()

                    # Compress if "on"
                    if should_compress:
                        data = zlib.compress(data, level=6)

                    if should_compress or crypter:
                        data = self._add_padding(data)

                    if crypter:
                        data = crypter.encrypt(data)

                    # Save result
                    with open(obj_path, "wb") as f_out:
                        f_out.write(data)

                    copied_count += 1
                except Exception as e:
                    logger.error(f"Failed to process {path}: {e}")
                    errors += 1
                    continue
            else:
                skipped_count += 1

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

        with open(snapshot_dir / "manifest.json", "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=4, ensure_ascii=False)

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
    ):
        # 1. Path for safe restore
        safe_restore_path = target_path / f"{project_name}_{version_name}"
        safe_restore_path.mkdir(parents=True, exist_ok=True)

        manifest_path = self.backup_base / project_name / version_name / "manifest.json"
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
        print(f"\n[RESTORE] Restoring {total_files} files to: {safe_restore_path}")

        for i, (rel_path_str, info) in enumerate(manifest["files"].items(), 1):
            file_hash = info["hash"]
            is_compressed = info.get("compressed", False)
            is_encrypted = bool(salt_hex)
            obj_path = self._get_object_path(
                file_hash,
                encrypted=is_encrypted,
                compressed=is_compressed,
                salt=salt_hex or "",
            )
            dest_path = safe_restore_path / rel_path_str

            try:
                dest_path.parent.mkdir(parents=True, exist_ok=True)

                # Read data from "objects"
                with open(obj_path, "rb") as f_in:
                    data = f_in.read()

                if decrypt_data and crypter:
                    try:
                        data = crypter.decrypt(data)
                    except Exception:
                        raise PermissionError(f"Invalid password for {rel_path_str}")

                if (decrypt_data or not salt_hex) and decompress_data:
                    if info.get("compressed") or salt_hex:
                        try:
                            data = self._remove_padding(data)
                        except:
                            pass

                # AUTO—DECOMPRESSION: if there is a compression flag in the manifest, decompress
                if decompress_data and info.get("compressed"):
                    try:
                        data = zlib.decompress(data)
                    except:
                        logger.error(f"Decompression error {rel_path_str}")

                # Write clean data
                final_path = (
                    dest_path
                    if (decrypt_data and decompress_data)
                    else dest_path.with_suffix(dest_path.suffix + ".raw")
                )
                with open(final_path, "wb") as f_out:
                    f_out.write(data)

                success_count += 1

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
                return
            except Exception as e:
                error_list.append(f"{rel_path_str}: {e}")

        print(f"\n\n=== The results of the restoration ===")
        print(f"Successfully:   {success_count} / {total_files}")
        if error_list:
            print(f"Errors:    {len(error_list)}")
            print("Error details are saved in the log.")
            for err in error_list[:5]:
                logger.error(err)

    def _find_target_versions(
        self, project_name: str = None, date_hint: str = None
    ) -> list[Path]:
        versions = []
        # If path is not exist, we will refund empty list
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

        for p_dir in search_dirs:
            if not p_dir.exists():
                continue
            for v_dir in p_dir.iterdir():
                if v_dir.is_dir() and (v_dir / "manifest.json").exists():
                    if date_hint and date_hint not in v_dir.name:
                        continue
                    versions.append(v_dir)

        versions.sort(key=lambda x: x.name)
        return versions
