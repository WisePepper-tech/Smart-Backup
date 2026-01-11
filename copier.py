import shutil
from pathlib import Path
from datetime import datetime


def copy_with_versions(files, source_root: Path, backup_root: Path):
    copied = 0
    skipped = 0
    versions_created = 0

    for src_path in files:
        relative_path = src_path.relative_to(source_root)
        dst_path = backup_root / relative_path

        dst_path.parent.mkdir(parents=True, exist_ok=True)

        if not dst_path.exists():
            shutil.copy2(src_path, dst_path)
            copied += 1
            continue

        # File exists → create version
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        versioned_name = f"{dst_path.stem}__{timestamp}{dst_path.suffix}"
        versioned_path = dst_path.with_name(versioned_name)

        shutil.copy2(src_path, versioned_path)
        versions_created += 1

    return {
        "copied": copied,
        "versions_created": versions_created,
        "skipped": skipped,
    }
