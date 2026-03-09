import logging
import getpass
import json
import shutil
import os
import tempfile
from dotenv import load_dotenv
from cloud_manager import CloudManager
from pathlib import Path
from scanner import scan_files
from manager import BackupManager
from utils import show_progress

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

logging.getLogger("botocore").setLevel(logging.WARNING)
logging.getLogger("boto3").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)

IS_DOCKER = os.getenv("DOCKER_MODE") == "true"
DOCKER_DATA_PATH = "/data"
MANIFEST_FILE = "manifest.json"
PRESS_ENTER = "\nPress Enter to continue..."


def get_safe_path(prompt):
    # Gets the path from the user and checks it for security
    user_input = input(prompt).strip()
    if not user_input:
        return None

    if IS_DOCKER:
        base = Path(DOCKER_DATA_PATH).resolve()
        # We remove the leading slashes and disks (type C:) so that Path does not consider the path to be absolute from the root
        safe_input = user_input.lstrip("/").lstrip("\\")
        # If the user entered the disk path (C:/...), we remove it as well
        if ":" in safe_input:
            safe_input = safe_input.split(":")[-1].lstrip("/").lstrip("\\")

        target = (base / safe_input).resolve()

        # Checking if the user is trying to leave /data (via ../..)
        if not str(target).startswith(str(base)):
            logging.warning(f"Attempt to escape sandbox: {user_input}")
            return base
        return target

    # If the startup is local (Windows/Linux)
    return Path(user_input).resolve()


def _setup_storage(is_cloud: bool):
    """Initialises cloud or local storage. Returns (cloud, backup_base) or None on failure."""
    load_dotenv()

    endpoint = os.getenv("S3_ENDPOINT", "http://minio:9000")

    if not os.getenv("DOCKER_MODE") and "minio" in endpoint:
        endpoint = endpoint.replace("minio", "localhost")

    if is_cloud:
        cloud = CloudManager(
            endpoint=endpoint,
            access_key=os.getenv("S3_ACCESS_KEY"),
            secret_key=os.getenv("S3_SECRET_KEY"),
            bucket_name=os.getenv("S3_BUCKET", "backup"),
        )

        backup_base = Path(tempfile.gettempdir()) / "smart_backup_cloud_temp"
        backup_base.mkdir(exist_ok=True)
        return cloud, backup_base

    cloud = None
    backup_base = get_safe_path("Enter path for storage [/data]: ") or Path(
        DOCKER_DATA_PATH
    )
    if not backup_base:
        print("Error: Storage path is required!")
        return None
    return cloud, backup_base


def _load_last_manifest(
    manager: BackupManager, cloud, backup_base: Path, project_name: str, is_cloud: bool
):
    """Loads the last manifest for the project, returns manifest dict or None."""
    if is_cloud:
        print(f"[INFO] Checking cloud for '{project_name}'...")
        cloud_res = cloud.get_last_manifest(project_name)
        if cloud_res:
            last_m, _ = cloud_res
            ts = last_m["info"]["timestamp"]
            local_old_path = backup_base / project_name / ts
            local_old_path.mkdir(parents=True, exist_ok=True)
            with open(local_old_path / MANIFEST_FILE, "w", encoding="utf-8") as f:
                json.dump(last_m, f, indent=4, ensure_ascii=False)
            return last_m
        return None

    last_versions = manager._find_target_versions(project_name)
    if last_versions:
        with open(last_versions[-1] / MANIFEST_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return None


def _check_param_changes(
    last_m, last_comp, last_enc, compress_yn, current_enc, last_salt
):
    """Returns forced_salt or raises SystemExit if user aborts."""
    forced_salt = last_salt
    if last_m and (last_comp != compress_yn or last_enc != current_enc):
        print(
            f"\n[!] WARNING: Parameters changed! Was: Comp={last_comp}, Enc={last_enc}"
        )
        if input("Continue? (y/n): ").lower() != "y":
            return None, True  # (forced_salt, aborted)
        forced_salt = None
    if last_enc and current_enc:
        if input("Generate new security key (Salt)? (y/n): ").lower() == "y":
            forced_salt = None
    return forced_salt, False


def handle_backup(manager, cloud, backup_base, is_cloud) -> None:
    source_path = get_safe_path("Enter path to source [/data]: ") or Path(
        DOCKER_DATA_PATH
    )
    if not source_path or not source_path.exists():
        print(f"Error: The source folder '{source_path}' was not found!")
        return

    project_name = (
        input(f"Specify the name of the directory [{source_path.name}]: ").strip()
        or source_path.name
    )

    last_m = _load_last_manifest(manager, cloud, backup_base, project_name, is_cloud)

    last_salt = None
    last_comp = True
    last_enc = False

    if last_m:
        last_salt = last_m["info"].get("salt")
        last_comp = last_m["info"].get("compression_enabled", False)
        last_enc = last_salt is not None
        print(f"\n[INFO] Found previous version of '{project_name}'.")

    comment = input("Comment: ").strip()
    comp_default = "y" if last_comp else "n"
    compress_yn = (
        input(f"Compress non-archive files? (y/n) [{comp_default}]: ").lower() != "n"
    )
    pass_input = getpass.getpass("Password (Enter for none): ").strip()
    password = pass_input if pass_input else None
    current_enc = password is not None

    forced_salt, aborted = _check_param_changes(
        last_m, last_comp, last_enc, compress_yn, current_enc, last_salt
    )
    if aborted:
        return

    print("\n[1/2] Scanning...")
    scan_result = scan_files(source_path, progress_callback=show_progress)

    print("\n[2/2] Creating snapshot...")

    def upload_hook(rel_path, data, _cloud=cloud):
        _cloud.upload_data(rel_path, data)

    res = manager.create_backup(
        scan_result,
        source_path,
        project_name,
        comment,
        compress=compress_yn,
        password=password,
        forced_salt=forced_salt,
        after_obj_created=upload_hook if is_cloud else None,
    )

    if is_cloud and backup_base.name == "smart_backup_cloud_temp":
        shutil.rmtree(backup_base)

    print("\n" + "—" * 30)
    print(" The snapshot was created successfully!")
    print(f"   • New objects:  {res.copied}")
    print(f"   • Used existing ones: {res.skipped}")
    print("—" * 30)

    input(PRESS_ENTER)


def handle_restore(manager, cloud, backup_base, is_cloud) -> None:
    if is_cloud:
        print("[INFO] Syncing manifests from cloud...")
        manifest_keys = cloud.list_manifests()
        for key in manifest_keys:
            rel_s3_path = Path(key.replace("backups/", "", 1))
            local_manifest_path = backup_base / rel_s3_path
            local_manifest_path.parent.mkdir(parents=True, exist_ok=True)
            m_data = cloud.download_data(key)
            with open(local_manifest_path, "wb") as f:
                f.write(m_data)

    proj_query = input("Directory name (Enter to search everywhere): ").strip() or None
    date_query = (
        input("Part of the date/name of the version (Enter for latest): ").strip()
        or None
    )

    found = manager._find_target_versions(proj_query, date_query)
    if not found:
        print("Versions not found.")
        return

    target_v = found[-1]
    print(f"\nVersion selected: {target_v.parent.name} / {target_v.name}")

    with open(target_v / MANIFEST_FILE, "r", encoding="utf-8") as f:
        m_data = json.load(f)

    password = None
    if m_data["info"].get("salt"):
        password = getpass.getpass(
            "This backup is encrypted. Enter the password: "
        ).strip()
        print("[INFO] Verifying access...")

        if not manager.verify_password(
            target_v.parent.name,
            target_v.name,
            password,
            fetch_proxy=cloud.download_objects if is_cloud else None,
        ):
            print("\n[!!!] Access Denied: Invalid password.")
            input(PRESS_ENTER)

    target_path = get_safe_path("Where to restore?: ")

    print("\nRecovery mode:")
    print("1. Full (original files)")
    print("2. Technical (as in storage: compression/cipher)")
    mode = input("Choose (1/2) [1]: ").strip() or "1"
    full_clean = mode == "1"

    results = manager.restore_version(
        target_v.parent.name,
        target_v.name,
        target_path,
        password=password,
        decrypt_data=full_clean,
        decompress_data=full_clean,
        fetch_proxy=cloud.download_objects if is_cloud else None,
    )

    success_count = sum(1 for status in results.values() if status is True)
    total_count = len(m_data.get("files", []))

    print("\n" + "—" * 30)
    print(" Recovery results ")
    print(f"   • Path: {target_path}")
    print(f"   • Restored: {success_count} / {total_count}")
    print("—" * 30)

    version_dir = target_path / f"{target_v.parent.name}_{target_v.name}"
    if version_dir.exists() and not any(version_dir.iterdir()):
        version_dir.rmdir()
        print("[INFO] Empty recovery directory removed.")

    input(PRESS_ENTER)


def main():
    while True:
        print("\n" + "-" * 40)
        print("   SMART-BACKUP CONTROL PANEL")
        print("-" * 40)
        print("1. Create backup")
        print("2. Restore version")
        print("0. Exit")

        choice = input("\nChoose an action (0/1/2): ").strip()

        if choice == "0":
            print("Goodbye!")
            break

        if choice not in ["1", "2"]:
            print("Invalid choice, try again.\n")
            continue

        storage_mode = input("Storage mode: 1. Local 2. Cloud (MinIO) [1]: ") or "1"
        is_cloud = storage_mode == "2"

        result = _setup_storage(is_cloud)
        if result is None:
            continue
        cloud, backup_base = result

        manager = BackupManager(backup_base)

        if choice == "1":
            handle_backup(manager, cloud, backup_base, is_cloud)
        elif choice == "2":
            handle_restore(manager, cloud, backup_base, is_cloud)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[!] Program interrupted by user. Goodbye!")
