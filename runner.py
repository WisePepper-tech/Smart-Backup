from pathlib import Path
import logging
from typing import Callable, Optional

from scanner import scan_folder, count_files
from copier import copy_files
from models import ScanResult, CopyResult, ProgressEvent, DryRunResult
import os
from encryptor import encrypt_file


def run_backup(
    source: Path,
    destination: Path,
    dry_run: bool = False,
    on_progress: Optional[Callable[[ProgressEvent], None]] = None,
    logger=None,
) -> CopyResult | DryRunResult:
    logger = logger or logging.getLogger(__name__)

    key = None
    if not dry_run:
        key = os.getenv("BACKUP_ENCRYPTION_KEY")
        if not key:
            raise RuntimeError("BACKUP_ENCRYPTION_KEY is not set")
        key = key.encode()

    total_files = count_files(source)

    def wrapped_progress(processed: int):
        if not on_progress:
            return

        percent = int((processed / total_files) * 100) if total_files else 100

        on_progress(
            ProgressEvent(
                processed=processed,
                total=total_files,
                percent=percent,
            )
        )

    scan_result: ScanResult = scan_folder(source, on_progress=wrapped_progress)

    copy_stats = copy_files(
        files=scan_result.files,
        src_root=source,
        dst_root=destination,
        dry_run=dry_run,
        logger=logger,
    )

    if copy_stats.get("dry_run"):
        logger.info("[DRY-RUN] Encryption step skipped")
        logger.debug("[DRY-RUN] Listing files planned for encryption")
        
        for path in destination.rglob("*"):
            if path.is_file():
                logger.debug(
                    f"[DRY-RUN] Would encrypt file: " f"{path.relative_to(destination)}"
                )

        return DryRunResult(
            planned_copies=copy_stats["planned_copies"],
            planned_versions=copy_stats["planned_versions"],
            planned_skips=copy_stats["planned_skips"],
        )
    logger.info("Encrypting backup files")

    for path in destination.rglob("*"):
        if path.is_file():
            encrypt_file(path, key)

    return CopyResult(
        copied=copy_stats["copied"],
        skipped=copy_stats["skipped"],
        versions_created=copy_stats["versions_created"],
        total_files=total_files,
    )
