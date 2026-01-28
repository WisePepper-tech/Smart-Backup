from pathlib import Path
import boto3
from botocore.exceptions import ClientError

from storage.base import BaseStorage


class S3Storage(BaseStorage):
    def __init__(
        self,
        bucket: str,
        endpoint_url: str | None = None,
        region: str = "us-east-1",
        access_key: str | None = None,
        secret_key: str | None = None,
    ):
        self.bucket = bucket

        self.client = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            region_name=region,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
        )

    def upload_file(self, local_path: Path, remote_path: str) -> None:
        try:
            self.client.upload_file(
                Filename=str(local_path),
                Bucket=self.bucket,
                Key=remote_path,
            )
        except ClientError as e:
            raise RuntimeError(f"S3 upload failed: {e}")

    def download_file(self, remote_path: str, local_path: Path) -> None:
        local_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            self.client.download_file(
                Bucket=self.bucket,
                Key=remote_path,
                Filename=str(local_path),
            )
        except ClientError as e:
            raise RuntimeError(f"S3 download failed: {e}")

    def list_files(self, prefix: str = "") -> list[str]:
        paginator = self.client.get_paginator("list_objects_v2")
        keys: list[str] = []

        for page in paginator.paginate(Bucket=self.bucket, Prefix=prefix):
            for obj in page.get("Contents", []):
                keys.append(obj["Key"])

        return keys
