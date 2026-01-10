from pathlib import Path

# Add ignored directories
IGNORE_DIRS = {
    "__pycache__",
    ".git",
    ".idea",
    "node_modules",
    "Cache",
    "Temp",
}


def scan_folder(folder_path: Path, on_progress=None):
    files = []
    total_size = 0
    processed = 0

    for path in folder_path.rglob("*"):
        if not path.is_file():
            continue

        # Ignore unwanted directories
        if any(ignored in path.parts for ignored in IGNORE_DIRS):
            continue

        try:
            stat = path.stat()
            total_size += stat.st_size
            files.append(path)
            processed += 1

            if on_progress:
                on_progress(processed)

        except (PermissionError, OSError):
            # Scanner does NOT log — just skips
            continue

    return {
        "files": files,
        "total_size": total_size,
        "processed": processed,
    }


def count_files(folder_path: Path) -> int:
    count = 0

    for path in folder_path.rglob("*"):
        if path.is_file():
            if any(ignored in path.parts for ignored in IGNORE_DIRS):
                continue
            count += 1

    return count
