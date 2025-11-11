"""
Unit tests for StorageClient (MinIO/S3 interface).

Tests object storage operations with mocked MinIO client.
"""

import tempfile
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

import pytest
from minio.error import S3Error

from etl.common.storage import StorageClient


@pytest.mark.unit
@pytest.mark.etl
class TestStorageClient:
    """Test suite for StorageClient class"""
    
    @pytest.fixture
    def mock_minio_client(self) -> Mock:
        """Create a mock MinIO client"""
        client = Mock()
        client.bucket_exists.return_value = True
        client.make_bucket.return_value = None
        client.fput_object.return_value = None
        client.fget_object.return_value = None
        client.put_object.return_value = None
        client.list_objects.return_value = []
        client.stat_object.return_value = Mock()
        client.remove_object.return_value = None
        return client
    
    @pytest.fixture
    def storage_client(self, mock_minio_client) -> StorageClient:
        """Create storage client with mocked MinIO client"""
        with patch('etl.common.storage.Minio', return_value=mock_minio_client):
            client = StorageClient(
                endpoint="localhost:9000",
                access_key="test_access",
                secret_key="test_secret",
                secure=False
            )
            return client
    
    # =====================
    # INITIALIZATION TESTS
    # =====================
    
    @patch('etl.common.storage.Minio')
    def test_init_with_custom_values(self, mock_minio_class):
        """Test initialization with custom configuration"""
        mock_instance = Mock()
        mock_minio_class.return_value = mock_instance
        
        client = StorageClient(
            endpoint="custom.minio.com:9000",
            access_key="custom_key",
            secret_key="custom_secret",
            secure=True
        )
        
        assert client.endpoint == "custom.minio.com:9000"
        assert client.access_key == "custom_key"
        assert client.secret_key == "custom_secret"
        assert client.secure is True
        
        mock_minio_class.assert_called_once_with(
            "custom.minio.com:9000",
            access_key="custom_key",
            secret_key="custom_secret",
            secure=True
        )
    
    @patch('etl.common.storage.Minio')
    @patch.dict('os.environ', {
        'MINIO_ENDPOINT': 'env.minio.com:9000',
        'MINIO_ROOT_USER': 'env_user',
        'MINIO_ROOT_PASSWORD': 'env_password'
    })
    def test_init_from_environment(self, mock_minio_class):
        """Test initialization from environment variables"""
        mock_instance = Mock()
        mock_minio_class.return_value = mock_instance
        
        client = StorageClient()
        
        assert client.endpoint == "env.minio.com:9000"
        assert client.access_key == "env_user"
        assert client.secret_key == "env_password"
    
    def test_endpoint_strips_protocol(self):
        """Test that endpoint strips http:// and https:// prefixes"""
        with patch('etl.common.storage.Minio'):
            client1 = StorageClient(endpoint="http://minio.local:9000")
            client2 = StorageClient(endpoint="https://minio.local:9000")
            
            assert client1.endpoint == "minio.local:9000"
            assert client2.endpoint == "minio.local:9000"
    
    # =====================
    # BUCKET MANAGEMENT TESTS
    # =====================
    
    def test_ensure_bucket_exists(self, storage_client, mock_minio_client):
        """Test ensuring bucket exists when it already exists"""
        mock_minio_client.bucket_exists.return_value = True
        
        result = storage_client.ensure_bucket("test-bucket")
        
        assert result is True
        mock_minio_client.bucket_exists.assert_called_once_with("test-bucket")
        mock_minio_client.make_bucket.assert_not_called()
    
    def test_ensure_bucket_creates_if_not_exists(self, storage_client, mock_minio_client):
        """Test creating bucket if it doesn't exist"""
        mock_minio_client.bucket_exists.return_value = False
        
        result = storage_client.ensure_bucket("new-bucket")
        
        assert result is True
        mock_minio_client.bucket_exists.assert_called_once_with("new-bucket")
        mock_minio_client.make_bucket.assert_called_once_with("new-bucket")
    
    def test_ensure_bucket_handles_error(self, storage_client, mock_minio_client):
        """Test error handling when bucket operations fail"""
        mock_minio_client.bucket_exists.side_effect = S3Error(
            "BucketAccessError",
            "Forbidden",
            "resource",
            "request_id",
            "host_id",
            Mock()
        )
        
        result = storage_client.ensure_bucket("error-bucket")
        
        assert result is False
    
    # =====================
    # FILE UPLOAD TESTS
    # =====================
    
    def test_upload_file_success(self, storage_client, mock_minio_client):
        """Test successful file upload"""
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
            f.write("test content")
            file_path = Path(f.name)
        
        try:
            result = storage_client.upload_file(
                "test-bucket",
                "path/to/object.txt",
                file_path
            )
            
            assert result is True
            mock_minio_client.fput_object.assert_called_once()
            call_args = mock_minio_client.fput_object.call_args
            assert call_args[0][0] == "test-bucket"
            assert call_args[0][1] == "path/to/object.txt"
            assert call_args[0][2] == str(file_path)
        finally:
            file_path.unlink()
    
    def test_upload_file_with_content_type(self, storage_client, mock_minio_client):
        """Test file upload with custom content type"""
        with tempfile.NamedTemporaryFile(delete=False) as f:
            file_path = Path(f.name)
        
        try:
            result = storage_client.upload_file(
                "test-bucket",
                "data.json",
                file_path,
                content_type="application/json"
            )
            
            assert result is True
            call_kwargs = mock_minio_client.fput_object.call_args[1]
            assert call_kwargs["content_type"] == "application/json"
        finally:
            file_path.unlink()
    
    def test_upload_file_ensures_bucket(self, storage_client, mock_minio_client):
        """Test that upload ensures bucket exists"""
        with tempfile.NamedTemporaryFile(delete=False) as f:
            file_path = Path(f.name)
        
        try:
            mock_minio_client.bucket_exists.return_value = False
            
            result = storage_client.upload_file(
                "new-bucket",
                "object.txt",
                file_path
            )
            
            assert result is True
            mock_minio_client.make_bucket.assert_called_once_with("new-bucket")
        finally:
            file_path.unlink()
    
    def test_upload_file_handles_error(self, storage_client, mock_minio_client):
        """Test error handling during file upload"""
        with tempfile.NamedTemporaryFile(delete=False) as f:
            file_path = Path(f.name)
        
        try:
            mock_minio_client.fput_object.side_effect = S3Error(
                "UploadError",
                "Internal Error",
                "resource",
                "request_id",
                "host_id",
                Mock()
            )
            
            result = storage_client.upload_file(
                "test-bucket",
                "object.txt",
                file_path
            )
            
            assert result is False
        finally:
            file_path.unlink()
    
    # =====================
    # FILE DOWNLOAD TESTS
    # =====================
    
    def test_download_file_success(self, storage_client, mock_minio_client):
        """Test successful file download"""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "downloaded.txt"
            
            result = storage_client.download_file(
                "test-bucket",
                "path/to/object.txt",
                output_path
            )
            
            assert result is True
            mock_minio_client.fget_object.assert_called_once()
            call_args = mock_minio_client.fget_object.call_args
            assert call_args[0][0] == "test-bucket"
            assert call_args[0][1] == "path/to/object.txt"
            assert call_args[0][2] == str(output_path)
    
    def test_download_file_creates_parent_directory(self, storage_client, mock_minio_client):
        """Test that download creates parent directories"""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "nested" / "path" / "file.txt"
            
            result = storage_client.download_file(
                "test-bucket",
                "object.txt",
                output_path
            )
            
            assert result is True
            assert output_path.parent.exists()
    
    def test_download_file_handles_error(self, storage_client, mock_minio_client):
        """Test error handling during file download"""
        mock_minio_client.fget_object.side_effect = S3Error(
            "NoSuchKey",
            "Not Found",
            "resource",
            "request_id",
            "host_id",
            Mock()
        )
        
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "file.txt"
            
            result = storage_client.download_file(
                "test-bucket",
                "nonexistent.txt",
                output_path
            )
            
            assert result is False
    
    # =====================
    # BYTES UPLOAD TESTS
    # =====================
    
    def test_upload_bytes_success(self, storage_client, mock_minio_client):
        """Test successful bytes upload"""
        data = b"test binary data"
        
        result = storage_client.upload_bytes(
            "test-bucket",
            "path/to/data.bin",
            data
        )
        
        assert result is True
        mock_minio_client.put_object.assert_called_once()
        call_args = mock_minio_client.put_object.call_args
        assert call_args[0][0] == "test-bucket"
        assert call_args[0][1] == "path/to/data.bin"
        assert call_args[1]["length"] == len(data)
    
    def test_upload_bytes_with_content_type(self, storage_client, mock_minio_client):
        """Test bytes upload with custom content type"""
        data = b'{"key": "value"}'
        
        result = storage_client.upload_bytes(
            "test-bucket",
            "data.json",
            data,
            content_type="application/json"
        )
        
        assert result is True
        call_kwargs = mock_minio_client.put_object.call_args[1]
        assert call_kwargs["content_type"] == "application/json"
    
    def test_upload_bytes_handles_error(self, storage_client, mock_minio_client):
        """Test error handling during bytes upload"""
        mock_minio_client.put_object.side_effect = S3Error(
            "UploadError",
            "Internal Error",
            "resource",
            "request_id",
            "host_id",
            Mock()
        )
        
        result = storage_client.upload_bytes(
            "test-bucket",
            "data.bin",
            b"data"
        )
        
        assert result is False
    
    # =====================
    # LIST OBJECTS TESTS
    # =====================
    
    def test_list_objects_success(self, storage_client, mock_minio_client):
        """Test listing objects in bucket"""
        mock_obj1 = Mock()
        mock_obj1.object_name = "file1.txt"
        mock_obj2 = Mock()
        mock_obj2.object_name = "file2.txt"
        
        mock_minio_client.list_objects.return_value = [mock_obj1, mock_obj2]
        
        objects = storage_client.list_objects("test-bucket")
        
        assert objects == ["file1.txt", "file2.txt"]
        mock_minio_client.list_objects.assert_called_once_with(
            "test-bucket",
            prefix="",
            recursive=True
        )
    
    def test_list_objects_with_prefix(self, storage_client, mock_minio_client):
        """Test listing objects with prefix filter"""
        mock_obj = Mock()
        mock_obj.object_name = "data/file.txt"
        
        mock_minio_client.list_objects.return_value = [mock_obj]
        
        objects = storage_client.list_objects("test-bucket", prefix="data/")
        
        assert objects == ["data/file.txt"]
        call_kwargs = mock_minio_client.list_objects.call_args[1]
        assert call_kwargs["prefix"] == "data/"
    
    def test_list_objects_handles_error(self, storage_client, mock_minio_client):
        """Test error handling during list objects"""
        mock_minio_client.list_objects.side_effect = S3Error(
            "ListError",
            "Access Denied",
            "resource",
            "request_id",
            "host_id",
            Mock()
        )
        
        objects = storage_client.list_objects("test-bucket")
        
        assert objects == []
    
    # =====================
    # OBJECT EXISTS TESTS
    # =====================
    
    def test_object_exists_true(self, storage_client, mock_minio_client):
        """Test checking if object exists (returns True)"""
        mock_minio_client.stat_object.return_value = Mock()
        
        exists = storage_client.object_exists("test-bucket", "file.txt")
        
        assert exists is True
        mock_minio_client.stat_object.assert_called_once_with("test-bucket", "file.txt")
    
    def test_object_exists_false(self, storage_client, mock_minio_client):
        """Test checking if object exists (returns False)"""
        mock_minio_client.stat_object.side_effect = S3Error(
            "NoSuchKey",
            "Not Found",
            "resource",
            "request_id",
            "host_id",
            Mock()
        )
        
        exists = storage_client.object_exists("test-bucket", "nonexistent.txt")
        
        assert exists is False
    
    # =====================
    # DELETE OBJECT TESTS
    # =====================
    
    def test_delete_object_success(self, storage_client, mock_minio_client):
        """Test successful object deletion"""
        result = storage_client.delete_object("test-bucket", "file.txt")
        
        assert result is True
        mock_minio_client.remove_object.assert_called_once_with(
            "test-bucket",
            "file.txt"
        )
    
    def test_delete_object_handles_error(self, storage_client, mock_minio_client):
        """Test error handling during object deletion"""
        mock_minio_client.remove_object.side_effect = S3Error(
            "DeleteError",
            "Access Denied",
            "resource",
            "request_id",
            "host_id",
            Mock()
        )
        
        result = storage_client.delete_object("test-bucket", "file.txt")
        
        assert result is False
    
    # =====================
    # INTEGRATION TESTS
    # =====================
    
    def test_upload_and_check_exists(self, storage_client, mock_minio_client):
        """Test upload followed by exists check"""
        with tempfile.NamedTemporaryFile(delete=False) as f:
            file_path = Path(f.name)
        
        try:
            # Upload file
            upload_result = storage_client.upload_file(
                "test-bucket",
                "file.txt",
                file_path
            )
            
            # Check exists
            mock_minio_client.stat_object.return_value = Mock()
            exists = storage_client.object_exists("test-bucket", "file.txt")
            
            assert upload_result is True
            assert exists is True
        finally:
            file_path.unlink()
    
    def test_list_empty_bucket(self, storage_client, mock_minio_client):
        """Test listing objects in empty bucket"""
        mock_minio_client.list_objects.return_value = []
        
        objects = storage_client.list_objects("empty-bucket")
        
        assert objects == []

