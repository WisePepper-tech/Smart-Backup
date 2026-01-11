import shutil
import logging
from pathlib import Path
from datetime import datetime


def copy_files(files, src_root: Path, dst_root: Path, dry_run: bool = False):
    copied = 0
    skipped = 0
    versions_created = 0

    for src_path in files:
        rel_path = src_path.relative_to(src_root)
        dst_path = dst_root / rel_path
        if not dry_run:
            dst_path.parent.mkdir(parents=True, exist_ok=True)

        if not dst_path.exists():
            if dry_run:
                logging.debug(f"[DRY-RUN] Would copy new file: {src_path}")
                skipped += 1
            else:
                shutil.copy2(src_path, dst_path)
                copied += 1
            continue

        src_stat = src_path.stat()
        dst_stat = dst_path.stat()

        if src_stat.st_size == dst_stat.st_size and int(src_stat.st_mtime) == int(
            dst_stat.st_mtime
        ):
            skipped += 1
            continue

        # VERSIONED BACKUP
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        versioned_name = dst_path.stem + f"_{timestamp}" + dst_path.suffix
        versioned_path = dst_path.with_name(versioned_name)

        if dry_run:
            logging.debug(f"[DRY-RUN] Would copy: {src_path} -> {dst_path}")
            skipped += 1
            continue

        shutil.move(dst_path, versioned_path)
        shutil.copy2(src_path, dst_path)
        versions_created += 1
        copied += 1

    return {
        "copied": copied,
        "versions_created": versions_created,
        "skipped": skipped,
    }
