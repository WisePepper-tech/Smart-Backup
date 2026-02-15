import boto3
from pathlib import Path


class CloudManager:
    def __init__(self, endpoint, access_key, secret_key, bucket_name):
        self.s3 = boto3.client(
            "s3",
            endpoint_url=endpoint,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
        )
        self.bucket = bucket_name

    def download_object(self, obj_hash: str, local_path: Path):
        # Downloads a physical file from cloud objects/ to local objects/
        s3_key = f"objects/{obj_hash[:2]}/{obj_hash}"
        local_path.parent.mkdir(parents=True, exist_ok=True)
        self.s3.download_file(self.bucket, s3_key, str(local_path))
