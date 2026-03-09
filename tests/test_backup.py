import shutil
import unittest
import sys
from pathlib import Path

# Adding the root directory to the path so that the imports work
sys.path.append(str(Path(__file__).parent.parent))
from manager import BackupManager
from scanner import scan_files


class TestBackupSystem(unittest.TestCase):
    def setUp(self):
        # Creating a temporary sandbox for tests
        self.base_path = Path(__file__).parent.parent
        self.test_dir = self.base_path / "test_sandbox"
        self.source = self.test_dir / "source"
        self.storage = self.test_dir / "storage"
        self.restore = self.test_dir / "restore"

        for p in [self.source, self.storage, self.restore]:
            if p.exists():
                shutil.rmtree(p)
            p.mkdir(parents=True)

        # Creating a test file
        self.file_content = b"Secret data inside a file"
        self.test_file = self.source / "secret.txt"
        self.test_file.write_bytes(self.file_content)

    def test_full_cycle_encrypted(self):
        """Full cycle: Backup (compression + password) -> Validation -> Recovery"""
        manager = BackupManager(self.storage)
        password = "secure_pass_123"

        # 1. CREATING BACKUP
        scan_res = scan_files(self.source)
        manager.create_backup(
            scan_res, self.source, "ProjectX", compress=True, password=password
        )

        # We are looking for the created version
        versions = manager._find_target_versions("ProjectX")
        self.assertTrue(len(versions) > 0)
        ver_dir = versions[0]

        # 2. CHECKING THE PASSWORD VALIDATOR
        self.assertTrue(manager.verify_password("ProjectX", ver_dir.name, password))
        self.assertFalse(
            manager.verify_password("ProjectX", ver_dir.name, "wrong_password")
        )

        # 3. RESTORE
        manager.restore_version(
            "ProjectX",
            ver_dir.name,
            self.restore,
            password=password,
            decrypt_data=True,
            decompress_data=True,
        )

        # Data integrity check
        restored_file = self.restore / f"ProjectX_{ver_dir.name}" / "secret.txt"
        self.assertTrue(restored_file.exists())
        self.assertEqual(restored_file.read_bytes(), self.file_content)
        print("\n[✓] Encryption + Validation test passed!")

    def test_deduplication_logic(self):
        """Deduplication check: two identical files should create one object in the storage"""
        manager = BackupManager(self.storage)

        # Creating a second file with the same content
        (self.source / "duplicate.txt").write_bytes(self.file_content)

        scan_res = scan_files(self.source)
        manager.create_backup(
            scan_res, self.source, "DedupProject", compress=False, password=None
        )

        objects = list(self.storage.glob("objects/*/*"))
        # There should be only 1 object (because the hash of the content is the same)
        self.assertEqual(len(objects), 1)
        print(f"[✓] Deduplication test passed (Objects: {len(objects)})")

    def test_salt_change_isolation(self):
        """Checking that changing the salt creates different objects for the same file"""
        manager = BackupManager(self.storage)
        scan_res = scan_files(self.source)

        # Version 1
        manager.create_backup(scan_res, self.source, "SaltProject", password="123")
        # Version 2 (new salt generated since forced_salt=None)
        manager.create_backup(
            scan_res, self.source, "SaltProject", password="123", forced_salt=None
        )

        objects = list(self.storage.glob("objects/*/*"))
        # There must be 2 objects, since the salt is included in the final hash of the object
        self.assertEqual(len(objects), 2)
        print(f"[✓] Salt isolation test passed (Objects: {len(objects)})")

    def test_non_compressible_files_skipped(self):
        """Files with non-compressible extensions must not be compressed,
        but must still be backed up and restored correctly."""
        manager = BackupManager(self.storage)

        # NON_COMPRESSIBLE file alongside a regular text file
        jpg_content = b"\xff\xd8\xff" + b"fake_jpeg_data" * 100  # fake JPEG header
        txt_content = b"This is a plain text file that should be compressed"

        (self.source / "photo.jpg").write_bytes(jpg_content)
        (self.source / "notes.txt").write_bytes(txt_content)

        scan_res = scan_files(self.source)
        manager.create_backup(
            scan_res, self.source, "MixedProject", compress=True, password=None
        )

        versions = manager._find_target_versions("MixedProject")
        self.assertTrue(len(versions) > 0)
        ver_dir = versions[0]

        # Check manifest: jpg must have compressed=False, txt must have compressed=True
        import json

        manifest_path = self.storage / "MixedProject" / ver_dir.name / "manifest.json"
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)

        files = manifest["files"]
        jpg_entry = next((v for k, v in files.items() if k.endswith("photo.jpg")), None)
        txt_entry = next((v for k, v in files.items() if k.endswith("notes.txt")), None)

        self.assertIsNotNone(jpg_entry, "photo.jpg not found in manifest")
        self.assertIsNotNone(txt_entry, "notes.txt not found in manifest")
        self.assertFalse(jpg_entry["compressed"], "JPEG should NOT be compressed")
        self.assertTrue(txt_entry["compressed"], "TXT should be compressed")

        # Restore and verify both files are intact
        manager.restore_version(
            "MixedProject",
            ver_dir.name,
            self.restore,
            decrypt_data=True,
            decompress_data=True,
        )
        restore_base = self.restore / f"MixedProject_{ver_dir.name}"
        self.assertEqual((restore_base / "photo.jpg").read_bytes(), jpg_content)
        self.assertEqual((restore_base / "notes.txt").read_bytes(), txt_content)
        print("\n[✓] Non-compressible files test passed!")

    def test_directory_tree_backup_restore(self):
        """Backup and restore of a nested directory tree."""
        manager = BackupManager(self.storage)

        # Build a tree: source/subdir/deep/file.txt
        deep_dir = self.source / "subdir" / "deep"
        deep_dir.mkdir(parents=True)
        deep_content = b"Deep nested file content"
        (deep_dir / "deep_file.txt").write_bytes(deep_content)

        # Also a file at the second level
        mid_content = b"Mid-level file"
        (self.source / "subdir" / "mid.txt").write_bytes(mid_content)

        scan_res = scan_files(self.source)
        manager.create_backup(
            scan_res, self.source, "TreeProject", compress=False, password=None
        )

        versions = manager._find_target_versions("TreeProject")
        ver_dir = versions[0]

        manager.restore_version(
            "TreeProject",
            ver_dir.name,
            self.restore,
            decrypt_data=True,
            decompress_data=True,
        )

        restore_base = self.restore / f"TreeProject_{ver_dir.name}"
        self.assertEqual(
            (restore_base / "subdir" / "deep" / "deep_file.txt").read_bytes(),
            deep_content,
        )
        self.assertEqual(
            (restore_base / "subdir" / "mid.txt").read_bytes(),
            mid_content,
        )
        # Original root file must also be present
        self.assertEqual(
            (restore_base / "secret.txt").read_bytes(),
            self.file_content,
        )
        print("\n[✓] Directory tree backup/restore test passed!")

    def test_ignored_extensions_not_backed_up(self):
        """Files with ignored extensions (.tmp, .log, .bak, .swp) must not appear in the backup."""
        manager = BackupManager(self.storage)

        # Create ignored files alongside a normal file
        (self.source / "temp.tmp").write_bytes(b"temporary data")
        (self.source / "app.log").write_bytes(b"log output")
        (self.source / "old.bak").write_bytes(b"backup of backup")
        (self.source / "editor.swp").write_bytes(b"vim swap")

        scan_res = scan_files(self.source)
        manager.create_backup(
            scan_res, self.source, "IgnoreProject", compress=False, password=None
        )

        versions = manager._find_target_versions("IgnoreProject")
        ver_dir = versions[0]

        import json

        manifest_path = self.storage / "IgnoreProject" / ver_dir.name / "manifest.json"
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)

        backed_up = set(manifest["files"].keys())

        # Ignored extensions must not be in manifest
        for ignored in ["temp.tmp", "app.log", "old.bak", "editor.swp"]:
            self.assertFalse(
                any(ignored in k for k in backed_up),
                f"{ignored} should be excluded from backup",
            )

        # The normal file must be present
        self.assertTrue(
            any("secret.txt" in k for k in backed_up),
            "secret.txt should be included in backup",
        )
        print("\n[✓] Ignored extensions test passed!")

    def tearDown(self):
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir)


if __name__ == "__main__":
    unittest.main()
