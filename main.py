import logging
import time
from pathlib import Path
import argparse
from runner import run_backup, DryRunResult

# Argument parsing (CLI)
parser = argparse.ArgumentParser()
parser.add_argument("--dry-run", action="store_true")
args = parser.parse_args()

# logging setup
logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")
logger = logging.getLogger("backup")

start_time = time.perf_counter()

# Paths: Create logs directory if it doesn't exist
BASE_DIR = Path(__file__).resolve().parent
LOG_DIR = BASE_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)
LOG_FILE = LOG_DIR / "backup.log"

dry_run = args.dry_run
logger.warning(f"DEBUG: dry_run = {dry_run}")

start_time = time.perf_counter()
logger.info("Backup scan started")

# User input path to folder, otherwise the program is not executed. That's mean restart program and repeat entering the folder path.
while True:
    folder_path = Path(input("Please enter the path of your folder: "))
    if folder_path.is_dir():
        break


def progress_callback(processed):
    if processed % 10 == 0:
        logger.info(f"Scanned: {processed}")


def progress_callback(event):
    if event.percent % 10 == 0:
        logger.info(f"Progress: {event.percent}% " f"({event.processed}/{event.total})")


# Ask for backup destination
backup_root = Path(input("Please enter BACKUP destination folder: "))
backup_root.mkdir(parents=True, exist_ok=True)
logger.info(f"Backup destination: {backup_root}")

if dry_run:
    logger.info("DRY-RUN enabled: filesystem will not be modified")


result = run_backup(
    source=folder_path,
    destination=backup_root,
    dry_run=dry_run,
    on_progress=progress_callback,
    logger=logging.getLogger("backup"),
)

if isinstance(result, DryRunResult):
    logger.info("DRY-RUN execution plan:")
    logger.info(f"Planned copies: {result.planned_copies}")
    logger.info(f"Planned versions: {result.planned_versions}")
    logger.info(f"Planned skips: {result.planned_skips}")
else:
    logger.info(f"Copied: {result.copied}")
    logger.info(f"Skipped: {result.skipped}")
    logger.info(f"Versioned: {result.versions_created}")

logger.info(f"Execution time: {time.perf_counter() - start_time:.2f}s")
