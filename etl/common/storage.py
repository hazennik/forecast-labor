"""
Storage Client
Interface to MinIO/S3 for data storage and retrieval
"""

import os
from pathlib import Path
from typing import Optional

import pandas as pd
from minio import Minio
from minio.error import S3Error
from loguru import logger


class StorageClient:
    """
    Client for MinIO/S3 object storage
    Handles uploads, downloads, and bucket management
    """

    def __init__(
        self,
        endpoint: Optional[str] = None,
        access_key: Optional[str] = None,
        secret_key: Optional[str] = None,
        secure: bool = False,
    ):
        """
        Initialize storage client

        Args:
            endpoint: MinIO endpoint (default: from env)
            access_key: Access key (default: from env)
            secret_key: Secret key (default: from env)
            secure: Use HTTPS (default: False for local)
        """
        # Get endpoint from parameter or environment, then strip protocol
        endpoint_raw = endpoint or os.getenv("MINIO_ENDPOINT", "minio:9000")
        self.endpoint = endpoint_raw.replace("http://", "").replace("https://", "")

        self.access_key = access_key or os.getenv("MINIO_ROOT_USER", "minioadmin")
        self.secret_key = secret_key or os.getenv("MINIO_ROOT_PASSWORD", "minioadmin123")
        self.secure = secure

        self.client = Minio(
            self.endpoint,
            access_key=self.access_key,
            secret_key=self.secret_key,
            secure=self.secure,
        )

        logger.info(f"Initialized storage client: {self.endpoint}")

    def ensure_bucket(self, bucket_name: str) -> bool:
        """
        Ensure bucket exists, create if not

        Args:
            bucket_name: Name of bucket

        Returns:
            bool: True if bucket exists or created
        """
        try:
            if not self.client.bucket_exists(bucket_name):
                self.client.make_bucket(bucket_name)
                logger.info(f"Created bucket: {bucket_name}")
            return True
        except S3Error as e:
            logger.error(f"Error ensuring bucket {bucket_name}: {e}")
            return False

    def upload_file(
        self,
        bucket_name: str,
        object_name: str,
        file_path: Path,
        content_type: str = "application/octet-stream",
    ) -> bool:
        """
        Upload file to storage

        Args:
            bucket_name: Bucket name
            object_name: Object key/path
            file_path: Local file path
            content_type: MIME type

        Returns:
            bool: True if successful
        """
        try:
            self.ensure_bucket(bucket_name)

            self.client.fput_object(
                bucket_name, object_name, str(file_path), content_type=content_type
            )

            logger.info(f"Uploaded {file_path} to {bucket_name}/{object_name}")
            return True

        except S3Error as e:
            logger.error(f"Error uploading {file_path}: {e}")
            return False

    def download_file(self, bucket_name: str, object_name: str, file_path: Path) -> bool:
        """
        Download file from storage

        Args:
            bucket_name: Bucket name
            object_name: Object key/path
            file_path: Local destination path

        Returns:
            bool: True if successful
        """
        try:
            file_path.parent.mkdir(parents=True, exist_ok=True)

            self.client.fget_object(bucket_name, object_name, str(file_path))

            logger.info(f"Downloaded {bucket_name}/{object_name} to {file_path}")
            return True

        except S3Error as e:
            logger.error(f"Error downloading {bucket_name}/{object_name}: {e}")
            return False

    def upload_bytes(
        self,
        bucket_name: str,
        object_name: str,
        data: bytes,
        content_type: str = "application/octet-stream",
    ) -> bool:
        """
        Upload bytes directly to storage

        Args:
            bucket_name: Bucket name
            object_name: Object key/path
            data: Bytes to upload
            content_type: MIME type

        Returns:
            bool: True if successful
        """
        try:
            from io import BytesIO

            self.ensure_bucket(bucket_name)

            self.client.put_object(
                bucket_name, object_name, BytesIO(data), length=len(data), content_type=content_type
            )

            logger.info(f"Uploaded {len(data)} bytes to {bucket_name}/{object_name}")
            return True

        except S3Error as e:
            logger.error(f"Error uploading bytes: {e}")
            return False

    def list_objects(self, bucket_name: str, prefix: str = "") -> list:
        """
        List objects in bucket

        Args:
            bucket_name: Bucket name
            prefix: Object prefix filter

        Returns:
            list: List of object names
        """
        try:
            objects = self.client.list_objects(bucket_name, prefix=prefix, recursive=True)
            return [obj.object_name for obj in objects]
        except S3Error as e:
            logger.error(f"Error listing objects in {bucket_name}: {e}")
            return []

    def object_exists(self, bucket_name: str, object_name: str) -> bool:
        """
        Check if object exists

        Args:
            bucket_name: Bucket name
            object_name: Object key/path

        Returns:
            bool: True if exists
        """
        try:
            self.client.stat_object(bucket_name, object_name)
            return True
        except S3Error:
            return False

    def delete_object(self, bucket_name: str, object_name: str) -> bool:
        """
        Delete object from storage

        Args:
            bucket_name: Bucket name
            object_name: Object key/path

        Returns:
            bool: True if successful
        """
        try:
            self.client.remove_object(bucket_name, object_name)
            logger.info(f"Deleted {bucket_name}/{object_name}")
            return True
        except S3Error as e:
            logger.error(f"Error deleting {bucket_name}/{object_name}: {e}")
            return False

    def read_parquet(self, object_path: str, bucket_name: str = "data") -> "pd.DataFrame":
        """
        Read parquet file from storage

        Args:
            object_path: Path to parquet file in storage
            bucket_name: Bucket name (default: data)

        Returns:
            pd.DataFrame: Loaded DataFrame
        """
        import pandas as pd
        import tempfile

        try:
            # Download to temporary file
            with tempfile.NamedTemporaryFile(suffix=".parquet", delete=False) as tmp:
                tmp_path = Path(tmp.name)

            if self.download_file(bucket_name, object_path, tmp_path):
                df = pd.read_parquet(tmp_path)
                tmp_path.unlink()  # Clean up temp file
                logger.info(f"Read parquet from {bucket_name}/{object_path}")
                return df
            else:
                raise Exception(f"Failed to download {bucket_name}/{object_path}")

        except Exception as e:
            logger.error(f"Error reading parquet from {bucket_name}/{object_path}: {e}")
            raise

    def write_parquet(
        self, df: "pd.DataFrame", object_path: str, bucket_name: str = "data"
    ) -> bool:
        """
        Write DataFrame as parquet to storage

        Args:
            df: DataFrame to write
            object_path: Path to store parquet file
            bucket_name: Bucket name (default: data)

        Returns:
            bool: True if successful
        """
        import tempfile

        try:
            # Write to temporary file
            with tempfile.NamedTemporaryFile(suffix=".parquet", delete=False) as tmp:
                tmp_path = Path(tmp.name)

            df.to_parquet(tmp_path, compression="snappy", index=False)

            success = self.upload_file(
                bucket_name, object_path, tmp_path, content_type="application/octet-stream"
            )

            tmp_path.unlink()  # Clean up temp file

            if success:
                logger.info(f"Wrote parquet to {bucket_name}/{object_path}")

            return success

        except Exception as e:
            logger.error(f"Error writing parquet to {bucket_name}/{object_path}: {e}")
            return False
