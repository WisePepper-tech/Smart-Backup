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
        # The correct password
        self.assertTrue(manager.verify_password("ProjectX", ver_dir.name, password))
        # Incorrect password
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

        # Counting files in the objects folder
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
        # Version 2 (the salt is generated anew if forced_salt=None)
        manager.create_backup(
            scan_res, self.source, "SaltProject", password="123", forced_salt=None
        )

        objects = list(self.storage.glob("objects/*/*"))
        # There must be 2 objects, since the salt is included in the final hash of the object.
        self.assertEqual(len(objects), 2)
        print(f"[✓] Salt isolation test passed (Objects: {len(objects)})")

    def tearDown(self):
        # Cleaning up the garbage after the tests
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir)


if __name__ == "__main__":
    unittest.main()
