import shutil
import unittest
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))
from manager import BackupManager
from scanner import scan_files


class TestBackupSystem(unittest.TestCase):
    def setUp(self):
        # Creating temporary folders for tests
        self.base_path = Path(__file__).parent.parent
        self.test_dir = self.base_path / "test_sandbox"
        self.source = self.test_dir / "source"
        self.storage = self.test_dir / "storage"
        self.restore = self.test_dir / "restore"

        for p in [self.source, self.storage, self.restore]:
            if p.exists():
                shutil.rmtree(p)
            p.mkdir(parents=True)

        # Creating test-file
        self.file_content = b"Secret data inside a file"
        (self.source / "secret.txt").write_bytes(self.file_content)

    def test_full_cycle(self):
        manager = BackupManager(self.storage)

        # 1. Creating a backup with compression and password
        scan_res = scan_files(self.source)
        manager.create_backup(
            scan_res, self.source, "ProjectX", compress=True, password="123"
        )

        # We find the created version
        ver_dir = manager._find_target_versions("ProjectX")[0]

        # 2. Restoring
        manager.restore_version(
            "ProjectX",
            ver_dir.name,
            self.restore,
            password="123",
            decrypt_data=True,
            decompress_data=True,
        )

        # Checking the result
        restored_file = self.restore / f"ProjectX_{ver_dir.name}" / "secret.txt"
        self.assertTrue(restored_file.exists())
        self.assertEqual(restored_file.read_bytes(), self.file_content)
        print("\n[✓] The Compression + Password test has been passed!")

    def test_salt_change_isolation(self):
        manager = BackupManager(self.storage)

        # We make two backups with different salts
        scan_res = scan_files(self.source)

        # Version 1
        manager.create_backup(scan_res, self.source, "ProjectX", password="123")

        # Version 2 (changing the salt by forcibly passing "None" to "forced_salt")
        manager.create_backup(
            scan_res, self.source, "ProjectX", password="123", forced_salt=None
        )

        # There should be 2 files in the objects folder
        objects = list(self.storage.glob("objects/*/*"))
        self.assertEqual(len(objects), 2)
        print(f"[✓] Salt isolation test passed (objects): {len(objects)})")

    def tearDown(self):
        # We remove the garbage after the test
        # shutil.rmtree(self.test_dir)
        pass


if __name__ == "__main__":
    unittest.main()
