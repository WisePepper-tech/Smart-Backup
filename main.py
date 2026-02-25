import logging
import getpass
import json
import shutil
import os
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

        load_dotenv()

        cloud = None
        if is_cloud:
            cloud = CloudManager(
                endpoint=os.getenv("S3_ENDPOINT"),
                access_key=os.getenv("S3_ACCESS_KEY"),
                secret_key=os.getenv("S3_SECRET_KEY"),
                bucket_name=os.getenv("S3_BUCKET", "backup"),
            )
            backup_base = Path("cloud_temp").resolve()
            backup_base.mkdir(exist_ok=True)
        else:
            cloud = None
            dst_input = input("Enter the path for storage: ").strip()
            backup_base = Path(dst_input).resolve()

        manager = BackupManager(backup_base)

        if choice == "1":
            src_input = input("Enter the path to the source folder: ").strip()
            source_path = Path(src_input)
            if not source_path.exists():
                print("Error: The source folder was not found!")
                return

            project_name = (
                input(
                    f"Specify the name of the directory [{source_path.name}]: "
                ).strip()
                or source_path.name
            )

            last_m = None

            if is_cloud:
                print(f"[INFO] Checking cloud for '{project_name}'...")
                cloud_res = cloud.get_last_manifest(project_name)
                if cloud_res:
                    last_m, _ = cloud_res
                    ts = last_m["info"]["timestamp"]
                    local_old_path = backup_base / project_name / ts
                    local_old_path.mkdir(parents=True, exist_ok=True)
                    with open(
                        local_old_path / "manifest.json", "w", encoding="utf-8"
                    ) as f:
                        json.dump(last_m, f, indent=4, ensure_ascii=False)
            else:
                last_versions = manager._find_target_versions(project_name)
                if last_versions:
                    with open(
                        last_versions[-1] / "manifest.json", "r", encoding="utf-8"
                    ) as f:
                        last_m = json.load(f)

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
                input(f"Compress non-archive files? (y/n) [{comp_default}]: ").lower()
                != "n"
            )
            pass_input = getpass.getpass("Password (Enter for none): ").strip()
            password = pass_input if pass_input else None
            current_enc = password is not None

            forced_salt = last_salt

            if last_m:
                if last_comp != compress_yn or last_enc != current_enc:
                    print(
                        f"\n[!] WARNING: Parameters changed! Was: Comp={last_comp}, Enc={last_enc}"
                    )
                    if input("Continue? (y/n): ").lower() != "y":
                        return
                    forced_salt = None

            if last_enc and current_enc:
                if input("Generate new security key (Salt)? (y/n): ").lower() == "y":
                    forced_salt = None

            print("\n[1/2] Scanning...")
            scan_result = scan_files(source_path, progress_callback=show_progress)

            print(f"\n[2/2] Creating snapshot...")

            def upload_hook(rel_path, data):
                cloud.upload_data(rel_path, data)

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

            if is_cloud and backup_base.name == "cloud_temp":
                shutil.rmtree(backup_base)

            print("\n" + "—" * 30)
            print(f" The snapshot was created successfully!")
            print(f"   • New objects:  {res.copied}")
            print(f"   • Used existing ones: {res.skipped}")
            print("—" * 30)

            input("\nPress Enter to continue...")
            continue

        elif choice == "2":
            if is_cloud:
                print("[INFO] Syncing manifests from cloud...")
                manifest_keys = cloud.list_manifests()
                for key in manifest_keys:
                    rel_s3_path = Path(key.replace("backups/", "", 1))
                    local_manifest_path = backup_base / rel_s3_path
                    local_manifest_path.parent.mkdir(parents=True, exist_ok=True)

                    # Download manifest
                    m_data = cloud.download_data(key)
                    with open(local_manifest_path, "wb") as f:
                        f.write(m_data)

            proj_query = (
                input("Directory name (Enter to search everywhere): ").strip() or None
            )
            date_query = (
                input(
                    "Part of the date/name of the version (Enter for latest): "
                ).strip()
                or None
            )

            found = manager._find_target_versions(proj_query, date_query)

            if not found:
                print("Versions not found.")
                return

            target_v = found[-1]
            print(f"\nVersion selected: {target_v.parent.name} / {target_v.name}")

            with open(target_v / "manifest.json", "r", encoding="utf-8") as f:
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
                    input("\nPress Enter to continue...")
                    continue

            target_path = Path(input("Where to restore?: ").strip())

            print("\nRecovery mode:")
            print("1. Full (original files)")
            print("2. Technical (as in storage: compression/cipher")
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
            print(f" Recovery results ")
            print(f"   • Path: {target_path}")
            print(f"   • Recovery results:: {success_count} / {total_count}")
            print("—" * 30)

            version_dir = target_path / f"{target_v.parent.name}_{target_v.name}"
            if version_dir.exists() and not any(version_dir.iterdir()):
                version_dir.rmdir()
                print(f"[INFO] Empty recovery directory removed.")

            input("\nPress Enter to continue...")
            continue


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[!] Program interrupted by user. Goodbye!")
