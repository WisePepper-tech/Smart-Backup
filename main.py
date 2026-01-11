import logging
import time
from pathlib import Path
from scanner import scan_folder, count_files
from copier import copy_with_versions

# Progress in percent
PROGRESS_STEP_PERCENT = 5
last_logged_percent = 0

# Paths: Create logs directory if it doesn't exist
BASE_DIR = Path(__file__).resolve().parent
LOG_DIR = BASE_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)
LOG_FILE = LOG_DIR / "backup.log"

# Logging setting and Start timer
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[logging.FileHandler(LOG_FILE, encoding="utf-8"), logging.StreamHandler()],
)

start_time = time.perf_counter()
logging.info("Backup scan started")

# User input path to folder, otherwise the program is not executed. That's mean restart program and repeat entering the folder path.
while True:
    folder_path = Path(input("Please enter the path of your folder: "))

    if folder_path.is_dir():
        logging.info(f"Scan root folder: {folder_path}")
        break
    else:
        logging.warning("Invalid folder path entered")

# Ask for backup destination
while True:
    backup_root = Path(input("Please enter BACKUP destination folder: "))

    if backup_root.exists():
        logging.info(f"Backup destination: {backup_root}")
        break
    else:
        logging.warning("Invalid backup destination path")

# Calculate total quantity files
total_files = count_files(folder_path)
logging.info(f"Total files to process: {total_files}")


def progress_callback(processed):
    global last_logged_percent

    if total_files == 0:
        return

    percent = int((processed / total_files) * 100)

    if percent >= last_logged_percent + PROGRESS_STEP_PERCENT:
        last_logged_percent = percent
        logging.info(f"Progress: {percent}% ({processed}/{total_files})")


scan_result = scan_folder(folder_path, on_progress=progress_callback)

logging.info(f"Total files: {len(scan_result['files'])}")
logging.info(f"Total size: {scan_result['total_size'] / 1024 / 1024:.2f} MB")

copy_result = copy_with_versions(
    files=scan_result["files"],
    source_root=folder_path,
    backup_root=backup_root
)

logging.info(
    f"Copied: {copy_result['copied']}, "
    f"Versions created: {copy_result['versions_created']}"
)

# Finish
duration = time.perf_counter() - start_time
logging.info(f"Execution time: {duration:.2f} seconds")
logging.info("Backup scan finished successfully")
