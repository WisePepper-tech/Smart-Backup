from pathlib import Path
import os
import logging

from storage.s3 import S3Storage
from encryptor import decrypt_file


def run_restore(
    destination: Path,
    prefix: str = "",
    logger=None,
):
    logger = logger or logging.getLogger(__name__)

    key = os.getenv("BACKUP_ENCRYPTION_KEY")
    if not key:
        raise RuntimeError("BACKUP_ENCRYPTION_KEY is not set")
    key = key.encode()

    s3 = S3Storage(
        bucket=os.getenv("BACKUP_S3_BUCKET"),
        endpoint_url=os.getenv("BACKUP_S3_ENDPOINT"),
        access_key=os.getenv("AWS_ACCESS_KEY_ID"),
        secret_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
    )

    logger.info("Starting restore from S3")
    logger.info(f"Restoring to {destination}")
    files = s3.list_files(prefix)

    for remote_key in files:
        local_path = destination / remote_key

        logger.debug(f"Downloading {remote_key}")
        s3.download_file(remote_key, local_path)

        logger.debug(f"Decrypting {local_path}")
        decrypt_file(local_path, key)

    logger.info("Restore completed")
