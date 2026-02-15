import logging
import getpass
import json
from pathlib import Path
from scanner import scan_files
from manager import BackupManager
from utils import show_progress

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")


def main():
    print("=== Smart-Backup ===\n")
    print("1. Create backup")
    print("2. Restore version")
    choice = input("\nChoose an action (1/2): ").strip()

    # Общий ввод для обоих режимов
    dst_input = input("Enter the path for copying: ").strip()
    backup_base = Path(dst_input)
    manager = BackupManager(backup_base)

    if choice == "1":
        src_input = input("Enter the path to the source folder: ").strip()
        source_path = Path(src_input)
        if not source_path.exists():
            print("Error: The source folder was not found!")
            return

        project_name = (
            input(f"Specify the name of the directory [{source_path.name}]: ").strip()
            or source_path.name
        )

        last_versions = manager._find_target_versions(project_name)
        old_salt = None
        last_comp = True

        if last_versions:
            with open(last_versions[-1] / "manifest.json", "r", encoding="utf-8") as f:
                last_m = json.load(f)

            last_enc = last_m["info"].get("encryption") is not None

            old_salt = last_m["info"].get("salt")
            last_comp = last_m["info"].get("compression_enabled", True)
            last_enc = old_salt is not None
            print(
                f"\n[INFO] The previous version of the directory was found '{project_name}'."
            )

        comment = input("Comment on the version: ").strip()

        compress_yn = (
            input(
                f"Do you want to compress the data? (y/n) [{'y' if last_comp else 'n'}]: "
            ).lower()
            != "n"
        )

        pass_input = getpass.getpass(
            "Write the password (Enter — without password): "
        ).strip()
        password = pass_input if pass_input else None
        current_enc = password is not None

        if last_versions:
            if last_comp != compress_yn or last_enc != current_enc:
                print(
                    f"\n[!] ATTENTION: The parameters are different from the previous version!"
                )
                print(f"Was: Compression={last_comp}, Encryption={last_enc}")
                print(
                    f"Has become: Compression={compress_yn}, Encryption={current_enc}"
                )

                if input("\nContinue with the new parameters? (y/n): ").lower() != "y":
                    print("The operation was canceled by the user.")
                    return

            if last_enc and current_enc:
                print(
                    "[SUCCESS] The access parameters match. The files will use a common database."
                )
                if (
                    input(
                        "Generate a new security key (Salt)? Deduplication with older versions will be disabled. (y/n): "
                    ).lower()
                    == "y"
                ):
                    old_salt = None  # This will force the manager to create a new salt.
                    print(
                        "A new key will be used. Deduplication with older versions is disabled."
                    )

            elif not last_enc and current_enc:
                print("\n[!!!] CRITICAL WARNING [!!!]")
                print(
                    "You enable encryption, but previous versions of this project are OPEN in the repository."
                )
                print(
                    "An attacker will be able to read old copies of files without a password."
                )
                print(
                    "\nRecommendation: Create a new folder for this backup or delete the old storage."
                )
                if (
                    input(
                        "Do you understand the risk and want to continue? (y/n): "
                    ).lower()
                    != "y"
                ):
                    return

            elif last_enc and not current_enc:
                print(
                    "\n[!!!] WARNING: The new backup will be WITHOUT encryption, although it used to be."
                )
                if input("Are you sure? (y/n): ").lower() != "y":
                    return

        print("\n[1/2] Scanning and calculating hashes...")
        scan_result = scan_files(source_path, progress_callback=show_progress)

        print(f"\n[2/2] Creating a snapshot...")
        res = manager.create_backup(
            scan_result,
            source_path,
            project_name,
            comment,
            compress=compress_yn,
            password=password,
            forced_salt=old_salt,
        )
        print(f"\n Ready! New ones: {res.copied}, From the database: {res.skipped}")

    elif choice == "2":
        proj_query = (
            input("Directory name (Enter to search everywhere): ").strip() or None
        )
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

        with open(target_v / "manifest.json", "r", encoding="utf-8") as f:
            m_data = json.load(f)

        password = None
        if m_data["info"].get("salt"):
            password = getpass.getpass(
                "This backup is encrypted. Enter the password: "
            ).strip()

        target_path = Path(input("Where to restore it?: ").strip())

        print("\nRecovery mode:")
        print("1. Full (original files)")
        print("2. Technical (as in storage: compression/cipher")
        mode = input("Choose (1/2) [1]: ").strip() or "1"

        full_clean = mode == "1"

        manager.restore_version(
            target_v.parent.name,
            target_v.name,
            target_path,
            password=password,
            decrypt_data=full_clean,
            decompress_data=full_clean,
        )

        print(f"\nRecovery in {target_path} is complete!")


if __name__ == "__main__":
    main()
