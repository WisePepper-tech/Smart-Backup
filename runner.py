from pathlib import Path
import logging
from typing import Callable, Optional

from scanner import scan_folder, count_files
from copier import copy_files
from models import ScanResult, CopyResult, ProgressEvent, DryRunResult
import os
from encryptor import encrypt_file
from storage.s3 import S3Storage


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
        logger.info("Backup scan started")
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
        logger.info("DRY-RUN enabled: filesystem will not be modified")

        for path in destination.rglob("*"):
            if path.is_file():
                logger.info(
                    "Planned copies: %d, versions: %d, skips: %d",
                    copy_stats["planned_copies"],
                    copy_stats["planned_versions"],
                    copy_stats["planned_skips"],
                )

        return DryRunResult(
            planned_copies=copy_stats["planned_copies"],
            planned_versions=copy_stats["planned_versions"],
            planned_skips=copy_stats["planned_skips"],
        )

    logger.info("Encrypting is started")

    for path in destination.rglob("*"):
        if not path.is_file():
            continue

        logger.debug("Encrypting file: %s", path)
        encrypt_file(path, key)

    logger.info("Encrypting is complete")

    s3 = S3Storage(
        bucket=os.getenv("BACKUP_S3_BUCKET"),
        endpoint_url=os.getenv("BACKUP_S3_ENDPOINT"),
        access_key=os.getenv("AWS_ACCESS_KEY_ID"),
        secret_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
    )

    if not s3.bucket:
        raise RuntimeError("BACKUP_S3_BUCKET is not set")

    logger.info("Uploading files to S3 bucket '%s'", s3.bucket)

    for file_path in destination.rglob("*"):
        if not file_path.is_file():
            continue

        remote_key = str(file_path.relative_to(destination))
        logger.debug("Uploading %s -> s3://%s/%s", file_path, s3.bucket, remote_key)
        s3.upload_file(file_path, remote_key)

    logger.info("Upload completed")

    return CopyResult(
        copied=copy_stats["copied"],
        skipped=copy_stats["skipped"],
        versions_created=copy_stats["versions_created"],
        total_files=total_files,
    )
