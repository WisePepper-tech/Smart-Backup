from pathlib import Path
from classes import ScanResult, ProgressEvent
from typing import Optional, Callable
from hasher import get_file_hash
import logging

IGNORE_DIRS = {
    "__pycache__",
    ".git",
    ".idea",
    "node_modules",
    "Cache",
    "Temp",
}

IGNORE_EXTENSIONS = {".tmp", ".log", ".bak", ".swp"}

logger = logging.getLogger(__name__)


def scan_files(
    folder_path: Path,
    progress_callback: Optional[Callable[[ProgressEvent], None]] = None,
) -> ScanResult:

    files = []
    total_size = 0
    file_data_map = {}

    if not folder_path.exists() or not folder_path.is_dir():
        logger.error(f"The directory {folder_path} is not found or not is dir.")
        raise ValueError("Invalid directory path")

    for root, dirs, filenames in folder_path.walk():
        dirs[:] = [dir for dir in dirs if dir not in IGNORE_DIRS]
        for name in filenames:
            path = root / name

            if path.suffix.lower() in IGNORE_EXTENSIONS:
                continue

            try:
                file_stat = path.stat()
                file_hash = get_file_hash(path)
                if file_hash:
                    files.append(path)
                    total_size += file_stat.st_size
                    file_data_map[path] = file_hash

                if progress_callback:
                    progress_callback(
                        ProgressEvent(processed=len(files), current_file=path.name)
                    )

            except (PermissionError, OSError) as e:
                logger.warning(f"Skip file {path}: {e}")
                continue

    result = ScanResult(
        files=files,
        total_files=len(files),
        total_size=total_size,
        file_hashes=file_data_map,
    )

    print()
    logger.info(
        f"Scanning files is completed, total files: {len(files)} / volume: {total_size / (1024**2):.2f} Mb"
    )
    return result
