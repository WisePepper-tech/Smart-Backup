import logging
from pathlib import Path

# Create logs directory if it doesn't exist
BASE_DIR = Path(__file__).resolve().parent
LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)

LOG_FILE = LOG_DIR / "backup.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[logging.FileHandler(LOG_FILE, encoding="utf-8"), logging.StreamHandler()],
)

# Add ignored directories
IGNORE_DIRS = {
    "__pycache__",
    ".git",
    ".idea",
    "node_modules",
    "Cache",
    "Temp",
}

# User input path to folder, otherwise the program is not executed. That's mean restart program and repeat entering the folder path.
while True:
    folder_path = Path(input("Please enter the path of your folder: "))

    if folder_path.is_dir():
        logging.info(f"Selected folder: {folder_path}")
        break
    else:
        logging.warning("Invalid folder path entered")


# The following function scans the folder and calculates the number of files and their total weight according to the criteria.
def scan_folder(folder_path):
    files = []
    total_size = 0

    for path in folder_path.rglob("*"):
        if path.is_file():

            # Checking if the file is in the ignored folder
            if any(ignored in path.parts for ignored in IGNORE_DIRS):
                continue

            files.append(path)

            # Checking permission
            try:
                total_size += path.stat().st_size
            except PermissionError:
                continue

    return {"files": files, "total_size": total_size}


scan_result = scan_folder(folder_path)

logging.info(f"Total files: {len(scan_result['files'])}")
logging.info(f"Total size: {scan_result['total_size'] / 1024 / 1024:.2f} MB")
