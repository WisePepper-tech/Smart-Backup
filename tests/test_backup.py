import io
import json
import shutil
import sys
import unittest
import os
from pathlib import Path
from unittest.mock import MagicMock, patch
from pydantic import ValidationError

os.environ.setdefault("API_KEY", "test-key-for-ci")
os.environ.setdefault("BACKUP_PATH", "/tmp/test-backups")
os.environ.setdefault("ALLOWED_SOURCE_PATH", "/data")

sys.path.append(str(Path(__file__).parent.parent))

from classes import ProgressEvent
from utils import show_progress
from hasher import get_file_hash
from scanner import scan_files, _should_skip, _process_file
from manager import BackupManager
from crypter import FileCrypter
from api import BackupRequest


# ---------------------------------------------------------------------------
# utils.py
# ---------------------------------------------------------------------------


class TestShowProgress(unittest.TestCase):
    def test_with_total(self):
        """Progress bar branch (total is set)."""
        event = ProgressEvent(processed=5, total=10, current_file="file.txt")
        buf = io.StringIO()
        with patch("sys.stdout", buf):
            show_progress(event)

    def test_without_total_scanning_branch(self):
        """Scanning branch (total is None) — line 7."""
        event = ProgressEvent(processed=3, total=None, current_file="file.txt")
        buf = io.StringIO()
        with patch("sys.stdout", buf):
            show_progress(event)
        self.assertIn("[SCANNING]", buf.getvalue())

    def test_completion_newline(self):
        """Newline written when processed >= total."""
        event = ProgressEvent(processed=10, total=10, current_file="done.txt")
        buf = io.StringIO()
        with patch("sys.stdout", buf):
            show_progress(event)
        self.assertIn("\n", buf.getvalue())


# ---------------------------------------------------------------------------
# hasher.py
# ---------------------------------------------------------------------------


class TestGetFileHash(unittest.TestCase):
    def setUp(self):
        self.base = Path(__file__).parent.parent / "test_sandbox_hasher"
        self.base.mkdir(exist_ok=True)

    def tearDown(self):
        shutil.rmtree(self.base, ignore_errors=True)

    def test_returns_hash_for_valid_file(self):
        f = self.base / "data.txt"
        f.write_bytes(b"hello")
        result = get_file_hash(f)
        self.assertIsNotNone(result)
        self.assertEqual(len(result), 64)

    def test_returns_none_on_oserror(self):
        """OSError branch — lines 11-12."""
        missing = self.base / "nonexistent.bin"
        result = get_file_hash(missing)
        self.assertIsNone(result)


# ---------------------------------------------------------------------------
# scanner.py
# ---------------------------------------------------------------------------


class TestScanner(unittest.TestCase):
    def setUp(self):
        self.base = Path(__file__).parent.parent / "test_sandbox_scanner"
        self.base.mkdir(exist_ok=True)
        (self.base / "note.txt").write_bytes(b"data")
        (self.base / "skip.tmp").write_bytes(b"temp")

    def tearDown(self):
        shutil.rmtree(self.base, ignore_errors=True)

    def test_should_skip_ignored_extension(self):
        self.assertTrue(_should_skip(Path("file.tmp")))
        self.assertTrue(_should_skip(Path("app.log")))
        self.assertFalse(_should_skip(Path("file.txt")))

    def test_scan_invalid_path_raises(self):
        """Lines 58-59 — invalid directory raises ValueError."""
        with self.assertRaises(ValueError):
            scan_files(Path("/nonexistent/path/xyz"))

    def test_scan_not_a_dir_raises(self):
        """Lines 58-59 — file path (not dir) raises ValueError."""
        f = self.base / "note.txt"
        with self.assertRaises(ValueError):
            scan_files(f)

    def test_process_file_oserror(self):
        """OSError branch in _process_file — lines 44-46."""
        files, file_data_map = [], {}
        result = _process_file(Path("/no/such/file.txt"), files, file_data_map, None)
        self.assertEqual(result, 0)
        self.assertEqual(files, [])

    def test_process_file_with_callback(self):
        """Progress callback branch — line 40."""
        f = self.base / "note.txt"
        files, file_data_map = [], {}
        callback = MagicMock()
        size = _process_file(f, files, file_data_map, callback)
        self.assertGreater(size, 0)
        callback.assert_called_once()

    def test_scan_calls_progress_callback(self):
        callback = MagicMock()
        result = scan_files(self.base, progress_callback=callback)
        self.assertGreater(result.total_files, 0)


# ---------------------------------------------------------------------------
# manager.py — missing lines
# ---------------------------------------------------------------------------


class TestBackupManagerEdgeCases(unittest.TestCase):
    def setUp(self):
        self.base = Path(__file__).parent.parent / "test_sandbox_mgr"
        self.source = self.base / "source"
        self.storage = self.base / "storage"
        self.restore = self.base / "restore"
        for p in [self.source, self.storage, self.restore]:
            shutil.rmtree(p, ignore_errors=True)
            p.mkdir(parents=True)
        self.content = b"test content for manager edge cases"
        (self.source / "file.txt").write_bytes(self.content)

    def tearDown(self):
        shutil.rmtree(self.base, ignore_errors=True)

    def _backup(self, compress=True, password=None):
        manager = BackupManager(self.storage)
        scan_res = scan_files(self.source)
        manager.create_backup(
            scan_res, self.source, "Proj", compress=compress, password=password
        )
        return manager

    def test_after_obj_created_callback(self):
        """after_obj_created is called for each object and manifest — line 67."""
        manager = BackupManager(self.storage)
        scan_res = scan_files(self.source)
        calls = []
        manager.create_backup(
            scan_res,
            self.source,
            "Proj",
            after_obj_created=lambda p, d: calls.append(p),
        )
        self.assertGreater(len(calls), 0)

    def test_forced_salt_reused(self):
        """forced_salt parameter — lines 126, 129-132."""
        manager = BackupManager(self.storage)
        scan_res = scan_files(self.source)
        salt = FileCrypter("pass").salt.hex()
        manager.create_backup(
            scan_res, self.source, "Proj", password="pass", forced_salt=salt
        )
        versions = manager._find_target_versions("Proj")
        with open(versions[0] / "manifest.json") as f:
            m = json.load(f)
        self.assertEqual(m["info"]["salt"], salt)

    def test_restore_with_fetch_proxy(self):
        """fetch_proxy branch — lines 168-171."""
        manager = self._backup(compress=False)
        versions = manager._find_target_versions("Proj")
        ver = versions[0]

        def fetch_proxy(rel_path):
            return (self.storage / rel_path).read_bytes()

        manager.restore_version("Proj", ver.name, self.restore, fetch_proxy=fetch_proxy)
        restored = self.restore / f"Proj_{ver.name}" / "file.txt"
        self.assertTrue(restored.exists())

    def test_restore_hash_mismatch_alarm(self):
        """ALARM printed on hash mismatch — line 236."""
        manager = self._backup(compress=False)
        versions = manager._find_target_versions("Proj")
        ver = versions[0]

        obj_dir = self.storage / "objects"
        for obj in obj_dir.rglob("*"):
            if obj.is_file():
                obj.write_bytes(b"corrupted")
                break

        with patch("builtins.print") as mock_print:
            manager.restore_version("Proj", ver.name, self.restore)
        printed = " ".join(str(c) for c in mock_print.call_args_list)
        self.assertIn("ALARM", printed)

    def test_restore_exception_appended_to_error_list(self):
        """Exception during restore appended to error_list — lines 245-246."""
        manager = self._backup(compress=False)
        versions = manager._find_target_versions("Proj")
        ver = versions[0]

        original_open = open

        def broken_open(path, *a, **kw):
            p = Path(path)
            if p.parent.parent == self.storage / "objects":
                raise OSError("disk error")
            return original_open(path, *a, **kw)

        with patch("builtins.open", side_effect=broken_open):
            results = manager.restore_version("Proj", ver.name, self.restore)
        self.assertFalse(all(results.values()))

    def test_restore_wrong_password_returns_early(self):
        """PermissionError on wrong password — lines 253-254, 260-261."""
        manager = self._backup(compress=True, password="correct")
        versions = manager._find_target_versions("Proj")
        ver = versions[0]
        results = manager.restore_version(
            "Proj", ver.name, self.restore, password="wrong"
        )
        self.assertIsInstance(results, dict)

    def test_version_matches_not_a_dir(self):
        """_version_matches returns False for non-directory — line 278."""
        manager = BackupManager(self.storage)
        fake_file = self.storage / "notadir"
        fake_file.write_bytes(b"x")
        self.assertFalse(manager._version_matches(fake_file, None))

    def test_find_versions_nonexistent_base(self):
        """backup_base not exists returns [] — lines 286-290."""
        manager = BackupManager(Path("/nonexistent/path"))
        self.assertEqual(manager._find_target_versions(), [])

    def test_find_versions_with_date_hint_no_match(self):
        """date_hint filters out non-matching versions — lines 296-299."""
        manager = self._backup()
        versions = manager._find_target_versions("Proj", date_hint="9999-99-99")
        self.assertEqual(versions, [])

    def test_find_versions_all_projects(self):
        """No project_name — scans all projects — line 305."""
        manager = self._backup()
        versions = manager._find_target_versions()
        self.assertGreater(len(versions), 0)

    def test_find_versions_nonexistent_project(self):
        """Project dir not exists — lines 307, 309."""
        manager = BackupManager(self.storage)
        versions = manager._find_target_versions("NoSuchProject")
        self.assertEqual(versions, [])

    def test_verify_password_no_salt(self):
        """No salt → returns True immediately — line 316."""
        manager = self._backup(compress=False, password=None)
        versions = manager._find_target_versions("Proj")
        ver = versions[0]
        self.assertTrue(manager.verify_password("Proj", ver.name, "any"))

    def test_verify_password_empty_files(self):
        """Empty files dict → returns True — line 346."""
        manager = BackupManager(self.storage)
        ver_dir = self.storage / "Proj" / "2099-01-01_00-00-00"
        ver_dir.mkdir(parents=True)
        manifest = {
            "info": {"salt": "aabbccdd" * 4, "compression_enabled": False},
            "files": {},
        }
        with open(ver_dir / "manifest.json", "w") as f:
            json.dump(manifest, f)
        self.assertTrue(manager.verify_password("Proj", ver_dir.name, "any"))

    def test_verify_password_with_fetch_proxy(self):
        """fetch_proxy branch in verify_password — line 351."""
        manager = self._backup(compress=False, password="secret")
        versions = manager._find_target_versions("Proj")
        ver = versions[0]

        def fetch_proxy(rel_path):
            return (self.storage / rel_path).read_bytes()

        self.assertTrue(
            manager.verify_password("Proj", ver.name, "secret", fetch_proxy=fetch_proxy)
        )

    def test_verify_password_object_not_found(self):
        """Object file missing → returns False — lines 366, 369-372."""
        manager = self._backup(compress=False, password="secret")
        versions = manager._find_target_versions("Proj")
        ver = versions[0]
        shutil.rmtree(self.storage / "objects")
        result = manager.verify_password("Proj", ver.name, "secret")
        self.assertFalse(result)

    def test_remove_padding_short_data(self):
        """_remove_padding with data shorter than 4 bytes."""
        manager = BackupManager(self.storage)
        result = manager._remove_padding(b"\x00\x00")
        self.assertEqual(result, b"\x00\x00")

    def test_create_backup_file_read_error(self):
        """Exception during file read increments errors counter."""
        manager = BackupManager(self.storage)
        scan_res = scan_files(self.source)
        original_open = open

        def broken_open(path, *a, **kw):
            if str(path).endswith("file.txt") and len(a) > 0 and "rb" in a[0]:
                raise OSError("read error")
            return original_open(path, *a, **kw)

        with patch("builtins.open", side_effect=broken_open):
            result = manager.create_backup(scan_res, self.source, "ErrProj")
        self.assertGreater(result.errors, 0)


# ---------------------------------------------------------------------------
# cloud_manager.py — full coverage via mocks
# ---------------------------------------------------------------------------


class TestCloudManager(unittest.TestCase):
    def _make_manager(self, mock_boto):
        from botocore.exceptions import ClientError
        from cloud_manager import CloudManager

        mock_s3 = MagicMock()
        mock_boto.return_value = mock_s3
        # head_bucket raises ClientError -> _ensure_bucket calls create_bucket (caught)
        mock_s3.head_bucket.side_effect = ClientError(
            {"Error": {"Code": "404", "Message": "Not Found"}}, "HeadBucket"
        )
        cm = CloudManager("http://localhost:9000", "key", "secret", "bucket")
        # Reset so further head_bucket/head_object calls behave as MagicMock defaults
        mock_s3.head_bucket.side_effect = None
        return cm, mock_s3

    @patch("cloud_manager.boto3.client")
    def test_ensure_bucket_creates_when_missing(self, mock_boto):
        cm, mock_s3 = self._make_manager(mock_boto)
        mock_s3.create_bucket.assert_called_once_with(Bucket="bucket")

    @patch("cloud_manager.boto3.client")
    def test_ensure_bucket_create_fails_gracefully(self, mock_boto):
        from botocore.exceptions import ClientError
        from cloud_manager import CloudManager

        mock_s3 = MagicMock()
        mock_boto.return_value = mock_s3
        mock_s3.head_bucket.side_effect = ClientError(
            {"Error": {"Code": "404", "Message": "Not Found"}}, "HeadBucket"
        )
        mock_s3.create_bucket.side_effect = ClientError(
            {"Error": {"Code": "500", "Message": "Error"}}, "CreateBucket"
        )
        with patch("builtins.print"):
            CloudManager("http://localhost:9000", "key", "secret", "bucket")

    @patch("cloud_manager.boto3.client")
    def test_ensure_bucket_already_exists(self, mock_boto):
        """head_bucket succeeds — no create called."""
        from cloud_manager import CloudManager

        mock_s3 = MagicMock()
        mock_boto.return_value = mock_s3
        mock_s3.head_bucket.return_value = {}
        CloudManager("http://localhost:9000", "key", "secret", "bucket")
        mock_s3.create_bucket.assert_not_called()

    @patch("cloud_manager.boto3.client")
    def test_list_manifests_with_project(self, mock_boto):
        cm, mock_s3 = self._make_manager(mock_boto)
        page = {
            "Contents": [
                {"Key": "backups/proj/2025/manifest.json"},
                {"Key": "backups/proj/2025/object"},
            ]
        }
        mock_s3.get_paginator.return_value.paginate.return_value = [page]
        result = cm.list_manifests("proj")
        self.assertEqual(result, ["backups/proj/2025/manifest.json"])

    @patch("cloud_manager.boto3.client")
    def test_list_manifests_without_project(self, mock_boto):
        cm, mock_s3 = self._make_manager(mock_boto)
        mock_s3.get_paginator.return_value.paginate.return_value = [{"Contents": []}]
        result = cm.list_manifests()
        self.assertEqual(result, [])

    @patch("cloud_manager.boto3.client")
    def test_list_manifests_no_contents_key(self, mock_boto):
        """Page without 'Contents' key — no crash."""
        cm, mock_s3 = self._make_manager(mock_boto)
        mock_s3.get_paginator.return_value.paginate.return_value = [{}]
        result = cm.list_manifests()
        self.assertEqual(result, [])

    @patch("cloud_manager.boto3.client")
    def test_get_last_manifest_success(self, mock_boto):
        cm, mock_s3 = self._make_manager(mock_boto)
        manifest_data = json.dumps({"info": {}, "files": {}}).encode()
        mock_s3.get_paginator.return_value.paginate.return_value = [
            {"Contents": [{"Key": "backups/proj/ver/manifest.json"}]}
        ]
        mock_s3.get_object.return_value = {"Body": io.BytesIO(manifest_data)}
        result = cm.get_last_manifest("proj")
        self.assertIsNotNone(result)

    @patch("cloud_manager.boto3.client")
    def test_get_last_manifest_no_manifests(self, mock_boto):
        cm, mock_s3 = self._make_manager(mock_boto)
        mock_s3.get_paginator.return_value.paginate.return_value = [{"Contents": []}]
        result = cm.get_last_manifest("proj")
        self.assertIsNone(result)

    @patch("cloud_manager.boto3.client")
    def test_get_last_manifest_download_error(self, mock_boto):
        from botocore.exceptions import ClientError

        cm, mock_s3 = self._make_manager(mock_boto)
        mock_s3.get_paginator.return_value.paginate.return_value = [
            {"Contents": [{"Key": "backups/proj/ver/manifest.json"}]}
        ]
        mock_s3.get_object.side_effect = ClientError(
            {"Error": {"Code": "500", "Message": "err"}}, "GetObject"
        )
        result = cm.get_last_manifest("proj")
        self.assertIsNone(result)

    @patch("cloud_manager.boto3.client")
    def test_upload_data_skips_existing(self, mock_boto):
        """head_object succeeds — object exists, upload skipped."""
        cm, mock_s3 = self._make_manager(mock_boto)
        mock_s3.head_object.return_value = {}
        cm.upload_data(Path("objects/aa/bb"), b"data")
        mock_s3.upload_fileobj.assert_not_called()

    @patch("cloud_manager.boto3.client")
    def test_upload_data_new_object(self, mock_boto):
        from botocore.exceptions import ClientError

        cm, mock_s3 = self._make_manager(mock_boto)
        mock_s3.head_object.side_effect = ClientError(
            {"Error": {"Code": "404", "Message": "Not Found"}}, "HeadObject"
        )
        with patch("builtins.print"):
            cm.upload_data(Path("objects/aa/bb"), b"data")
        mock_s3.upload_fileobj.assert_called_once()

    @patch("cloud_manager.boto3.client")
    def test_upload_data_json_content_type(self, mock_boto):
        from botocore.exceptions import ClientError

        cm, mock_s3 = self._make_manager(mock_boto)
        mock_s3.head_object.side_effect = ClientError(
            {"Error": {"Code": "404", "Message": "Not Found"}}, "HeadObject"
        )
        with patch("builtins.print"):
            cm.upload_data(Path("proj/ver/manifest.json"), b"{}")
        _, kwargs = mock_s3.upload_fileobj.call_args
        self.assertEqual(
            kwargs.get("ExtraArgs", {}).get("ContentType"), "application/json"
        )

    @patch("cloud_manager.boto3.client")
    def test_show_upload_progress(self, mock_boto):
        cm, _ = self._make_manager(mock_boto)
        buf = io.StringIO()
        with patch("sys.stdout", buf):
            cm._show_upload_progress(50, 100)
        self.assertIn("50", buf.getvalue())

    @patch("cloud_manager.boto3.client")
    def test_download_data(self, mock_boto):
        cm, mock_s3 = self._make_manager(mock_boto)
        mock_s3.get_object.return_value = {"Body": io.BytesIO(b"payload")}
        result = cm.download_data("backups/proj/ver/manifest.json")
        self.assertEqual(result, b"payload")

    @patch("cloud_manager.boto3.client")
    def test_download_objects(self, mock_boto):
        cm, mock_s3 = self._make_manager(mock_boto)
        mock_s3.get_object.return_value = {"Body": io.BytesIO(b"blob")}
        result = cm.download_objects(Path("objects/aa/bb"))
        self.assertEqual(result, b"blob")


# ---------------------------------------------------------------------------
# main.py — full coverage via mocks
# ---------------------------------------------------------------------------


class TestMain(unittest.TestCase):
    def setUp(self):
        self.base = Path(__file__).parent.parent / "test_sandbox_main"
        self.source = self.base / "source"
        self.storage = self.base / "storage"
        self.restore = self.base / "restore"
        for p in [self.source, self.storage, self.restore]:
            shutil.rmtree(p, ignore_errors=True)
            p.mkdir(parents=True)
        (self.source / "data.txt").write_bytes(b"main test data")

    def tearDown(self):
        shutil.rmtree(self.base, ignore_errors=True)

    # --- get_safe_path ---
    def test_get_safe_path_empty_returns_none(self):
        import main

        with patch("builtins.input", return_value=""):
            result = main.get_safe_path("prompt: ")
        self.assertIsNone(result)

    def test_get_safe_path_local(self):
        import main

        with patch("builtins.input", return_value=str(self.source)):
            with patch.object(main, "IS_DOCKER", False):
                result = main.get_safe_path("prompt: ")
        self.assertEqual(result, self.source.resolve())

    def test_get_safe_path_docker_normal(self):
        import main

        with patch.object(main, "IS_DOCKER", True):
            with patch.object(main, "DOCKER_DATA_PATH", str(self.base)):
                with patch("builtins.input", return_value="source"):
                    result = main.get_safe_path("prompt: ")
        self.assertIsNotNone(result)

    def test_get_safe_path_docker_escape_attempt(self):
        import main

        with patch.object(main, "IS_DOCKER", True):
            with patch.object(main, "DOCKER_DATA_PATH", str(self.base)):
                with patch("builtins.input", return_value="../../etc/passwd"):
                    result = main.get_safe_path("prompt: ")
        self.assertTrue(str(result).startswith(str(self.base)))

    def test_get_safe_path_docker_windows_path(self):
        import main

        with patch.object(main, "IS_DOCKER", True):
            with patch.object(main, "DOCKER_DATA_PATH", str(self.base)):
                with patch("builtins.input", return_value="C:\\Users\\test"):
                    result = main.get_safe_path("prompt: ")
        self.assertIsNotNone(result)

    # --- _setup_storage ---
    def test_setup_storage_local(self):
        import main

        with patch("main.get_safe_path", return_value=self.storage):
            with patch("main.load_dotenv"):
                result = main._setup_storage(is_cloud=False)
        self.assertIsNotNone(result)
        cloud, backup_base = result
        self.assertIsNone(cloud)

    def test_setup_storage_cloud(self):
        import main

        with patch("main.load_dotenv"):
            with patch("main.CloudManager"):
                with patch("main.Path.mkdir"):
                    with patch(
                        "main.os.getenv",
                        side_effect=lambda k, *d: (
                            "true"
                            if k == "DOCKER_MODE"
                            else (
                                "http://minio:9000"
                                if k == "S3_ENDPOINT"
                                else (d[0] if d else "val")
                            )
                        ),
                    ):
                        result = main._setup_storage(is_cloud=True)
        self.assertIsNotNone(result)

    def test_setup_storage_minio_replaced_without_docker_mode(self):
        import main

        with patch("main.load_dotenv"):
            with patch("main.Path.mkdir"):
                with patch(
                    "main.os.getenv",
                    side_effect=lambda k, *d: (
                        None
                        if k == "DOCKER_MODE"
                        else (
                            "http://minio:9000"
                            if k == "S3_ENDPOINT"
                            else (d[0] if d else "val")
                        )
                    ),
                ):
                    with patch("main.CloudManager") as mock_cm:
                        main._setup_storage(is_cloud=True)
        call_kwargs = mock_cm.call_args
        endpoint_used = call_kwargs.kwargs.get("endpoint") or call_kwargs.args[0]
        self.assertIn("localhost", endpoint_used)
        self.assertNotIn("minio", endpoint_used)

    def test_setup_storage_path_fallback(self):
        """get_safe_path returns None → fallback to DOCKER_DATA_PATH."""
        import main

        with patch("main.get_safe_path", return_value=None):
            with patch("main.load_dotenv"):
                result = main._setup_storage(is_cloud=False)
        self.assertIsNotNone(result)

    # --- _load_last_manifest ---
    def test_load_last_manifest_local_no_versions(self):
        import main

        manager = BackupManager(self.storage)
        result = main._load_last_manifest(
            manager, None, self.storage, "NoProject", is_cloud=False
        )
        self.assertIsNone(result)

    def test_load_last_manifest_local_with_version(self):
        import main

        manager = BackupManager(self.storage)
        scan_res = scan_files(self.source)
        manager.create_backup(scan_res, self.source, "Proj")
        result = main._load_last_manifest(
            manager, None, self.storage, "Proj", is_cloud=False
        )
        self.assertIsNotNone(result)

    def test_load_last_manifest_cloud_found(self):
        import main

        manager = BackupManager(self.storage)
        fake_manifest = {
            "info": {
                "timestamp": "2025-01-01_00-00-00",
                "salt": None,
                "compression_enabled": True,
            },
            "files": {},
        }
        cloud = MagicMock()
        cloud.get_last_manifest.return_value = (fake_manifest, "key")
        result = main._load_last_manifest(
            manager, cloud, self.storage, "Proj", is_cloud=True
        )
        self.assertEqual(result, fake_manifest)

    def test_load_last_manifest_cloud_not_found(self):
        import main

        manager = BackupManager(self.storage)
        cloud = MagicMock()
        cloud.get_last_manifest.return_value = None
        result = main._load_last_manifest(
            manager, cloud, self.storage, "Proj", is_cloud=True
        )
        self.assertIsNone(result)

    # --- handle_backup ---
    def test_handle_backup_source_not_found(self):
        import main

        manager = BackupManager(self.storage)
        with patch("main.get_safe_path", return_value=Path("/nonexistent/xyz")):
            with patch("builtins.print"):
                main.handle_backup(manager, None, self.storage, is_cloud=False)

    def test_handle_backup_no_password_no_compress(self):
        import main

        manager = BackupManager(self.storage)
        # input() calls in handle_backup (after get_safe_path is mocked):
        # 1. project_name (default = source_path.name)
        # 2. comment
        # 3. compress? y/n
        # 4. PRESS_ENTER at end
        inputs = iter(["", "", "n", ""])
        with patch("main.get_safe_path", return_value=self.source):
            with patch("builtins.input", side_effect=inputs):
                with patch("main.getpass.getpass", return_value=""):
                    with patch("builtins.print"):
                        result = main.handle_backup(
                            manager, None, self.storage, is_cloud=False
                        )

    def test_handle_backup_with_password(self):
        import main

        manager = BackupManager(self.storage)
        inputs = iter(["MyProject", "comment", "y", ""])
        with patch("main.get_safe_path", return_value=self.source):
            with patch("builtins.input", side_effect=inputs):
                with patch("main.getpass.getpass", return_value="secret"):
                    with patch("builtins.print"):
                        result = main.handle_backup(
                            manager, None, self.storage, is_cloud=False
                        )

    def test_handle_backup_params_changed_abort(self):
        """User aborts when parameters change."""
        import main

        manager = BackupManager(self.storage)
        scan_res = scan_files(self.source)
        manager.create_backup(scan_res, self.source, "Proj", compress=True)

        inputs = iter(["Proj", "", "n", "n", ""])
        with patch("main.get_safe_path", return_value=self.source):
            with patch("builtins.input", side_effect=inputs):
                with patch("main.getpass.getpass", return_value=""):
                    with patch("builtins.print"):
                        result = main.handle_backup(
                            manager, None, self.storage, is_cloud=False
                        )

    def test_handle_backup_params_changed_continue(self):
        """User continues when parameters change."""
        import main

        manager = BackupManager(self.storage)
        scan_res = scan_files(self.source)
        manager.create_backup(scan_res, self.source, "Proj", compress=True)

        inputs = iter(["Proj", "", "n", "y", ""])
        with patch("main.get_safe_path", return_value=self.source):
            with patch("builtins.input", side_effect=inputs):
                with patch("main.getpass.getpass", return_value=""):
                    with patch("builtins.print"):
                        result = main.handle_backup(
                            manager, None, self.storage, is_cloud=False
                        )

    def test_handle_backup_new_salt_prompt(self):
        """With existing encrypted backup, prompt for new salt."""
        import main

        manager = BackupManager(self.storage)
        scan_res = scan_files(self.source)
        manager.create_backup(
            scan_res, self.source, "EncProj", compress=True, password="old"
        )

        inputs = iter(["EncProj", "", "y", "y", ""])
        with patch("main.get_safe_path", return_value=self.source):
            with patch("builtins.input", side_effect=inputs):
                with patch("main.getpass.getpass", return_value="old"):
                    with patch("builtins.print"):
                        result = main.handle_backup(
                            manager, None, self.storage, is_cloud=False
                        )

    def test_handle_backup_cloud(self):
        import main

        cloud_temp = self.base / "cloud_temp"
        cloud_temp.mkdir(exist_ok=True)
        manager = BackupManager(cloud_temp)
        cloud = MagicMock()
        cloud.get_last_manifest.return_value = None
        inputs = iter(["CloudProj", "", "y", ""])
        with patch("main.get_safe_path", return_value=self.source):
            with patch("builtins.input", side_effect=inputs):
                with patch("main.getpass.getpass", return_value=""):
                    with patch("main.shutil.rmtree"):
                        with patch("builtins.print"):
                            result = main.handle_backup(
                                manager, cloud, cloud_temp, is_cloud=True
                            )

    # --- handle_restore ---
    def test_handle_restore_no_versions(self):
        import main

        manager = BackupManager(self.storage)
        inputs = iter(["", ""])
        with patch("builtins.input", side_effect=inputs):
            with patch("builtins.print"):
                result = main.handle_restore(
                    manager, None, self.storage, is_cloud=False
                )

    def test_handle_restore_unencrypted(self):
        import main

        manager = BackupManager(self.storage)
        scan_res = scan_files(self.source)
        manager.create_backup(scan_res, self.source, "Proj", compress=False)

        inputs = iter(["Proj", "", "1", ""])
        with patch("builtins.input", side_effect=inputs):
            with patch("main.get_safe_path", return_value=self.restore):
                with patch("builtins.print"):
                    result = main.handle_restore(
                        manager, None, self.storage, is_cloud=False
                    )

    def test_handle_restore_encrypted_wrong_password(self):
        import main

        manager = BackupManager(self.storage)
        scan_res = scan_files(self.source)
        manager.create_backup(
            scan_res, self.source, "EncProj", compress=False, password="correct"
        )

        inputs = iter(["EncProj", "", "1", ""])
        with patch("builtins.input", side_effect=inputs):
            with patch("main.getpass.getpass", return_value="wrong"):
                with patch("main.get_safe_path", return_value=self.restore):
                    with patch("builtins.print"):
                        result = main.handle_restore(
                            manager, None, self.storage, is_cloud=False
                        )

    def test_handle_restore_technical_mode(self):
        import main

        manager = BackupManager(self.storage)
        scan_res = scan_files(self.source)
        manager.create_backup(scan_res, self.source, "Proj", compress=False)

        inputs = iter(["Proj", "", "2", ""])
        with patch("builtins.input", side_effect=inputs):
            with patch("main.get_safe_path", return_value=self.restore):
                with patch("builtins.print"):
                    result = main.handle_restore(
                        manager, None, self.storage, is_cloud=False
                    )

    def test_handle_restore_cloud_sync(self):
        import main

        manager = BackupManager(self.storage)
        scan_res = scan_files(self.source)
        manager.create_backup(scan_res, self.source, "Proj", compress=False)

        ver = manager._find_target_versions("Proj")[0]
        manifest_key = f"backups/Proj/{ver.name}/manifest.json"
        manifest_data = (
            self.storage / "Proj" / ver.name / "manifest.json"
        ).read_bytes()

        cloud = MagicMock()
        cloud.list_manifests.return_value = [manifest_key]
        cloud.download_data.return_value = manifest_data
        cloud.download_objects.side_effect = lambda rel_path: (
            self.storage / rel_path
        ).read_bytes()

        inputs = iter(["Proj", "", "1", ""])
        with patch("builtins.input", side_effect=inputs):
            with patch("main.get_safe_path", return_value=self.restore):
                with patch("builtins.print"):
                    main.handle_restore(manager, cloud, self.storage, is_cloud=True)

    def test_handle_restore_encrypted_correct_password(self):
        """Correct password — verify_password passes, restore proceeds."""
        import main

        manager = BackupManager(self.storage)
        scan_res = scan_files(self.source)
        manager.create_backup(
            scan_res, self.source, "EncProj2", compress=False, password="correct"
        )
        inputs = iter(["EncProj2", "", "1", ""])
        with patch("builtins.input", side_effect=inputs):
            with patch("main.getpass.getpass", return_value="correct"):
                with patch("main.get_safe_path", return_value=self.restore):
                    with patch("builtins.print"):
                        result = main.handle_restore(
                            manager, None, self.storage, is_cloud=False
                        )

    def test_handle_restore_empty_dir_cleaned(self):
        """Empty restore dir is removed — rmdir branch in handle_restore."""
        import main

        manager = BackupManager(self.storage)
        scan_res = scan_files(self.source)
        manager.create_backup(scan_res, self.source, "CleanProj", compress=False)
        ver = manager._find_target_versions("CleanProj")[0]
        # Pre-create empty restore target dir so rmdir branch triggers
        restore2 = self.base / "restore2"
        restore2.mkdir(parents=True, exist_ok=True)
        empty = restore2 / f"CleanProj_{ver.name}"
        empty.mkdir(parents=True, exist_ok=True)
        inputs = iter(["CleanProj", ver.name, "1", ""])
        with patch("builtins.input", side_effect=inputs):
            with patch("main.get_safe_path", return_value=restore2):
                with patch("builtins.print"):
                    main.handle_restore(manager, None, self.storage, is_cloud=False)

    # --- main() loop ---
    def test_main_exit(self):
        import main

        with patch("builtins.input", side_effect=["0"]):
            with patch("builtins.print"):
                main.main()

    def test_main_invalid_choice(self):
        import main

        with patch("builtins.input", side_effect=["9", "0"]):
            with patch("builtins.print"):
                main.main()

    def test_main_setup_storage_returns_none(self):
        """_setup_storage returns None → continue."""
        import main

        side_effects = ["1", "1", "0"]
        with patch("builtins.input", side_effect=side_effects):
            with patch("main._setup_storage", return_value=None):
                with patch("builtins.print"):
                    main.main()

    def test_main_calls_handle_backup(self):
        import main

        side_effects = ["1", "1", "0"]
        manager_mock = MagicMock()
        with patch("builtins.input", side_effect=side_effects):
            with patch("main._setup_storage", return_value=(None, self.storage)):
                with patch("main.BackupManager", return_value=manager_mock):
                    with patch("main.handle_backup", return_value=True):
                        with patch("builtins.print"):
                            main.main()

    def test_main_calls_handle_restore(self):
        import main

        side_effects = ["2", "1", "0"]
        manager_mock = MagicMock()
        with patch("builtins.input", side_effect=side_effects):
            with patch("main._setup_storage", return_value=(None, self.storage)):
                with patch("main.BackupManager", return_value=manager_mock):
                    with patch("main.handle_restore", return_value=True):
                        with patch("builtins.print"):
                            main.main()


# ---------------------------------------------------------------------------
# Original integration tests
# ---------------------------------------------------------------------------


class TestBackupSystem(unittest.TestCase):
    def setUp(self):
        self.base_path = Path(__file__).parent.parent
        self.test_dir = self.base_path / "test_sandbox"
        self.source = self.test_dir / "source"
        self.storage = self.test_dir / "storage"
        self.restore = self.test_dir / "restore"
        for p in [self.source, self.storage, self.restore]:
            if p.exists():
                shutil.rmtree(p)
            p.mkdir(parents=True)
        self.file_content = b"Secret data inside a file"
        self.test_file = self.source / "secret.txt"
        self.test_file.write_bytes(self.file_content)

    def test_full_cycle_encrypted(self):
        manager = BackupManager(self.storage)
        password = "secure_pass_123"
        scan_res = scan_files(self.source)
        manager.create_backup(
            scan_res, self.source, "ProjectX", compress=True, password=password
        )
        versions = manager._find_target_versions("ProjectX")
        self.assertTrue(len(versions) > 0)
        ver_dir = versions[0]
        self.assertTrue(manager.verify_password("ProjectX", ver_dir.name, password))
        self.assertFalse(
            manager.verify_password("ProjectX", ver_dir.name, "wrong_password")
        )
        manager.restore_version(
            "ProjectX",
            ver_dir.name,
            self.restore,
            password=password,
            decrypt_data=True,
            decompress_data=True,
        )
        restored_file = self.restore / f"ProjectX_{ver_dir.name}" / "secret.txt"
        self.assertTrue(restored_file.exists())
        self.assertEqual(restored_file.read_bytes(), self.file_content)
        print("\n[✓] Encryption + Validation test passed!")

    def test_deduplication_logic(self):
        manager = BackupManager(self.storage)
        (self.source / "duplicate.txt").write_bytes(self.file_content)
        scan_res = scan_files(self.source)
        manager.create_backup(
            scan_res, self.source, "DedupProject", compress=False, password=None
        )
        objects = list(self.storage.glob("objects/*/*"))
        self.assertEqual(len(objects), 1)
        print(f"[✓] Deduplication test passed (Objects: {len(objects)})")

    def test_salt_change_isolation(self):
        manager = BackupManager(self.storage)
        scan_res = scan_files(self.source)
        manager.create_backup(scan_res, self.source, "SaltProject", password="123")
        manager.create_backup(
            scan_res, self.source, "SaltProject", password="123", forced_salt=None
        )
        objects = list(self.storage.glob("objects/*/*"))
        self.assertEqual(len(objects), 2)
        print(f"[✓] Salt isolation test passed (Objects: {len(objects)})")

    def test_non_compressible_files_skipped(self):
        manager = BackupManager(self.storage)
        jpg_content = b"\xff\xd8\xff" + b"fake_jpeg_data" * 100
        txt_content = b"This is a plain text file that should be compressed"
        (self.source / "photo.jpg").write_bytes(jpg_content)
        (self.source / "notes.txt").write_bytes(txt_content)
        scan_res = scan_files(self.source)
        manager.create_backup(
            scan_res, self.source, "MixedProject", compress=True, password=None
        )
        versions = manager._find_target_versions("MixedProject")
        ver_dir = versions[0]
        manifest_path = self.storage / "MixedProject" / ver_dir.name / "manifest.json"
        with open(manifest_path) as f:
            manifest = json.load(f)
        files = manifest["files"]
        jpg_entry = next((v for k, v in files.items() if k.endswith("photo.jpg")), None)
        txt_entry = next((v for k, v in files.items() if k.endswith("notes.txt")), None)
        self.assertFalse(jpg_entry["compressed"])
        self.assertTrue(txt_entry["compressed"])
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
        manager = BackupManager(self.storage)
        deep_dir = self.source / "subdir" / "deep"
        deep_dir.mkdir(parents=True)
        deep_content = b"Deep nested file content"
        (deep_dir / "deep_file.txt").write_bytes(deep_content)
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
            (restore_base / "subdir" / "mid.txt").read_bytes(), mid_content
        )
        self.assertEqual((restore_base / "secret.txt").read_bytes(), self.file_content)
        print("\n[✓] Directory tree backup/restore test passed!")

    def test_ignored_extensions_not_backed_up(self):
        manager = BackupManager(self.storage)
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
        manifest_path = self.storage / "IgnoreProject" / ver_dir.name / "manifest.json"
        with open(manifest_path) as f:
            manifest = json.load(f)
        backed_up = set(manifest["files"].keys())
        for ignored in ["temp.tmp", "app.log", "old.bak", "editor.swp"]:
            self.assertFalse(any(ignored in k for k in backed_up))
        self.assertTrue(any("secret.txt" in k for k in backed_up))
        print("\n[✓] Ignored extensions test passed!")

    def tearDown(self):
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir)


# ---------------------------------------------------------------------------
# Tests for API (api.py)
# ---------------------------------------------------------------------------


class TestApiValidators(unittest.TestCase):
    def test_project_name_valid(self):

        # Pydantic v2 — validating via model_validate
        req = BackupRequest.model_validate(
            {
                "source_path": "/data/test",
                "project_name": "my-project",
            }
        )
        self.assertEqual(req.project_name, "my-project")

    def test_project_name_invalid(self):
        with self.assertRaises(ValidationError):
            BackupRequest.model_validate(
                {
                    "source_path": "/data/test",
                    "project_name": "../../etc",
                }
            )

    def test_source_path_outside_allowed(self):
        with self.assertRaises(ValidationError):
            BackupRequest.model_validate(
                {
                    "source_path": "/etc/passwd",
                    "project_name": "proj",
                }
            )

    def test_comment_too_long(self):
        with self.assertRaises(ValidationError):
            BackupRequest.model_validate(
                {
                    "source_path": "/data/test",
                    "project_name": "proj",
                    "comment": "x" * 501,
                }
            )


if __name__ == "__main__":
    unittest.main()
