import json
import logging
import boto3
import os
import sys
from botocore.exceptions import ClientError
from botocore.config import Config
from pathlib import Path
from io import BytesIO

logger = logging.getLogger(__name__)


class CloudManager:
    def __init__(self, endpoint, access_key, secret_key, bucket_name):
        self.s3 = boto3.client(
            "s3",
            endpoint_url=endpoint,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            config=Config(
                connect_timeout=5,
                read_timeout=10,
                retries={"max_attempts": 1},
            ),
        )

        self.bucket = bucket_name
        self._ensure_bucket()

    def _ensure_bucket(self):
        try:
            self.s3.head_bucket(Bucket=self.bucket)
        except ClientError:
            try:
                self.s3.create_bucket(Bucket=self.bucket)
            except (ClientError, OSError) as e:
                print(f"[!] Connection error to MinIO: {e}")

    def get_last_manifest(self, project_name):
        """Downloads the most recent manifest to check the parameters"""
        manifests = self.list_manifests(project_name)
        if not manifests:
            return None

        last_key = manifests[-1]
        try:
            data = self.download_data(last_key)
            return json.loads(data), last_key
        except (ClientError, json.JSONDecodeError) as e:
            logger.warning(f"Failed to load manifest {last_key}: {e}")
            return None

    def upload_data(self, rel_path: str, data: bytes):
        s3_key = f"backups/{str(rel_path).replace(os.sep, '/')}"

        extra_args = (
            {"ContentType": "application/json"} if s3_key.endswith(".json") else {}
        )
        try:
            # Checking if there is already such an object
            self.s3.head_object(Bucket=self.bucket, Key=s3_key)
        except ClientError:
            data_size = len(data)
            file_obj = BytesIO(data)

            print(f"\n[CLOUD] Uploading {rel_path.name}...")

            self.s3.upload_fileobj(
                file_obj,
                self.bucket,
                s3_key,
                ExtraArgs=extra_args,
                Callback=lambda bytes_transferred: self._show_upload_progress(
                    bytes_transferred, data_size
                ),
            )
            print("\n   [OK] Uploaded.")

    def _show_upload_progress(self, transmitted, total):
        scale_width = 30
        percent = (transmitted / total) * 100
        filled = int(scale_width * transmitted / total)
        bar = "#" * filled + "-" * (scale_width - filled)
        msg = f"\r   Cloud |{bar}| {percent:.1f}% ({transmitted}/{total} bytes)"

        sys.stdout.write(msg)
        sys.stdout.flush()

    def download_data(self, s3_path: str) -> bytes:
        s3_path = s3_path.replace("\\", "/")
        response = self.s3.get_object(Bucket=self.bucket, Key=s3_path)
        return response["Body"].read()

    def download_objects(self, rel_path: Path) -> bytes:
        """Accepts a relative Path and downloads it from a folder backups/"""
        s3_key = f"backups/{str(rel_path).replace(os.sep, '/')}"
        return self.download_data(s3_key)

    def list_manifests(self, project_name=None):
        if project_name:
            clean_name = str(project_name).replace("\\", "/")
            prefix = f"backups/{clean_name}/"
        else:
            prefix = "backups/"

        paginator = self.s3.get_paginator("list_objects_v2")
        manifests = []
        for page in paginator.paginate(Bucket=self.bucket, Prefix=prefix):
            for obj in page.get("Contents", []):
                if obj["Key"].endswith("manifest.json"):
                    manifests.append(obj["Key"])
        return sorted(manifests)
