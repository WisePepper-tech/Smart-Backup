import logging
import time
from pathlib import Path
from scanner import scan_folder, count_files
from copier import copy_files
import argparse

# Argument parsing (CLI)
parser = argparse.ArgumentParser(
    description="Backup tool with versioning and dry-run support."
)
parser.add_argument(
    "--dry-run",
    action="store_true",
    help="Show what would be done without making changes",
)
args = parser.parse_args()

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

dry_run = args.dry_run
logging.warning(f"DEBUG: dry_run = {dry_run}")

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
files = scan_result["files"]

logging.info(f"Total files: {len(scan_result['files'])}")
logging.info(f"Total size: {scan_result['total_size'] / 1024 / 1024:.2f} MB")

# Ask for backup destination
backup_root = Path(input("Please enter BACKUP destination folder: "))
backup_root.mkdir(parents=True, exist_ok=True)
logging.info(f"Backup destination: {backup_root}")

if dry_run:
    logging.info("Running in dry-run mode: No files will be copied or moved.")

copy_result = copy_files(
    files=files,
    src_root=folder_path,
    dst_root=backup_root,
    dry_run=dry_run,
)

logging.info(f"Copied files: {copy_result['copied']}")
logging.info(f"Versioned files: {copy_result['versions_created']}")
logging.info(f"Skipped files: {copy_result['skipped']}")

# Finish
duration = time.perf_counter() - start_time
logging.info(f"Execution time: {duration:.2f} seconds")
logging.info("Backup scan finished successfully")
