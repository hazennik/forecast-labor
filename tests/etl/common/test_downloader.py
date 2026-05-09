"""
Unit tests for Downloader utility.

Tests HTTP download functionality, retry logic, and error handling.
"""

import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
import requests

from etl.common.downloader import Downloader, DownloadError


@pytest.mark.unit
@pytest.mark.etl
class TestDownloader:
    """Test suite for Downloader class"""

    @pytest.fixture
    def downloader(self) -> Downloader:
        """Create downloader instance for testing"""
        return Downloader(max_retries=3, retry_delay=1, timeout=30)

    @pytest.fixture
    def mock_response(self) -> Mock:
        """Create a mock successful HTTP response"""
        response = Mock()
        response.status_code = 200
        response.content = b"test data content"
        response.json.return_value = {"status": "success", "data": [1, 2, 3]}
        response.raise_for_status.return_value = None
        return response

    # =====================
    # INITIALIZATION TESTS
    # =====================

    def test_init_default_values(self):
        """Test downloader initialization with default values"""
        downloader = Downloader()

        assert downloader.max_retries == 3
        assert downloader.retry_delay == 5
        assert downloader.timeout == 30
        assert "Mozilla/5.0" in downloader.session.headers["User-Agent"]

    def test_init_custom_values(self):
        """Test downloader initialization with custom values"""
        downloader = Downloader(
            max_retries=5, retry_delay=10, timeout=60, user_agent="custom-agent/2.0"
        )

        assert downloader.max_retries == 5
        assert downloader.retry_delay == 10
        assert downloader.timeout == 60
        assert downloader.session.headers["User-Agent"] == "custom-agent/2.0"

    # =====================
    # DOWNLOAD METHOD TESTS
    # =====================

    @patch("requests.Session.get")
    def test_download_success(self, mock_get, downloader, mock_response):
        """Test successful download"""
        mock_get.return_value = mock_response

        content = downloader.download("https://example.com/data.json")

        assert content == b"test data content"
        mock_get.assert_called_once()

    @patch("requests.Session.get")
    def test_download_with_params(self, mock_get, downloader, mock_response):
        """Test download with query parameters"""
        mock_get.return_value = mock_response

        params = {"key": "value", "page": 1}
        content = downloader.download("https://example.com/api", params=params)

        assert content == b"test data content"
        mock_get.assert_called_once()
        call_kwargs = mock_get.call_args[1]
        assert call_kwargs["params"] == params

    @patch("requests.Session.get")
    def test_download_with_headers(self, mock_get, downloader, mock_response):
        """Test download with custom headers"""
        mock_get.return_value = mock_response

        headers = {"Authorization": "Bearer token123"}
        content = downloader.download("https://example.com/api", headers=headers)

        assert content == b"test data content"
        assert "Authorization" in downloader.session.headers

    @patch("requests.Session.get")
    def test_download_save_to_file(self, mock_get, downloader, mock_response):
        """Test download with saving to file"""
        mock_get.return_value = mock_response

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "output.dat"
            content = downloader.download("https://example.com/data", output_path=output_path)

            assert content == b"test data content"
            assert output_path.exists()
            assert output_path.read_bytes() == b"test data content"

    # =====================
    # ERROR HANDLING TESTS
    # =====================

    @patch("requests.Session.get")
    def test_download_404_error(self, mock_get, downloader):
        """Test handling of 404 errors (should not retry)"""
        response = Mock()
        response.status_code = 404
        response.raise_for_status.side_effect = requests.exceptions.HTTPError(response=response)
        mock_get.return_value = response

        with pytest.raises(DownloadError) as exc_info:
            downloader.download("https://example.com/notfound")

        assert "File not found" in str(exc_info.value)
        # Should only try once for 404 (no retries)
        mock_get.assert_called_once()

    @patch("requests.Session.get")
    @patch("time.sleep")  # Mock sleep to speed up test
    def test_download_retry_on_500_error(self, mock_sleep, mock_get, downloader, mock_response):
        """Test retry logic on 500 server errors"""
        # Fail twice, then succeed
        error_response = Mock()
        error_response.status_code = 500
        error_response.raise_for_status.side_effect = requests.exceptions.HTTPError(
            response=error_response
        )

        mock_get.side_effect = [error_response, error_response, mock_response]

        content = downloader.download("https://example.com/data")

        assert content == b"test data content"
        assert mock_get.call_count == 3
        assert mock_sleep.call_count == 2  # Slept between retries

    @patch("requests.Session.get")
    @patch("time.sleep")
    def test_download_max_retries_exceeded(self, mock_sleep, mock_get, downloader):
        """Test failure after max retries exceeded"""
        error_response = Mock()
        error_response.status_code = 500
        error_response.raise_for_status.side_effect = requests.exceptions.HTTPError(
            response=error_response
        )
        mock_get.return_value = error_response

        with pytest.raises(DownloadError) as exc_info:
            downloader.download("https://example.com/data")

        assert "Failed to download after" in str(exc_info.value)
        assert mock_get.call_count == 3  # max_retries = 3

    @patch("requests.Session.get")
    @patch("time.sleep")
    def test_download_retry_on_connection_error(
        self, mock_sleep, mock_get, downloader, mock_response
    ):
        """Test retry logic on connection errors"""
        mock_get.side_effect = [
            requests.exceptions.ConnectionError("Connection failed"),
            mock_response,
        ]

        content = downloader.download("https://example.com/data")

        assert content == b"test data content"
        assert mock_get.call_count == 2

    @patch("requests.Session.get")
    @patch("time.sleep")
    def test_download_retry_on_timeout(self, mock_sleep, mock_get, downloader, mock_response):
        """Test retry logic on timeout errors"""
        mock_get.side_effect = [requests.exceptions.Timeout("Request timed out"), mock_response]

        content = downloader.download("https://example.com/data")

        assert content == b"test data content"
        assert mock_get.call_count == 2

    # =====================
    # DOWNLOAD_JSON TESTS
    # =====================

    @patch("requests.Session.get")
    def test_download_json_success(self, mock_get, downloader, mock_response):
        """Test successful JSON download"""
        mock_get.return_value = mock_response

        data = downloader.download_json("https://example.com/api/data")

        assert data == {"status": "success", "data": [1, 2, 3]}
        mock_get.assert_called_once()

    @patch("requests.Session.get")
    def test_download_json_with_params(self, mock_get, downloader, mock_response):
        """Test JSON download with query parameters"""
        mock_get.return_value = mock_response

        params = {"format": "json", "limit": 100}
        data = downloader.download_json("https://example.com/api", params=params)

        assert data == {"status": "success", "data": [1, 2, 3]}
        call_kwargs = mock_get.call_args[1]
        assert call_kwargs["params"] == params

    @patch("requests.Session.get")
    def test_download_json_invalid_response(self, mock_get, downloader):
        """Test handling of invalid JSON response"""
        response = Mock()
        response.status_code = 200
        response.raise_for_status.return_value = None
        response.json.side_effect = requests.exceptions.JSONDecodeError("Invalid JSON", "", 0)
        mock_get.return_value = response

        with pytest.raises(DownloadError) as exc_info:
            downloader.download_json("https://example.com/api")

        assert "Invalid JSON" in str(exc_info.value)

    @patch("requests.Session.get")
    def test_download_json_404_error(self, mock_get, downloader):
        """Test JSON download with 404 error"""
        response = Mock()
        response.status_code = 404
        response.raise_for_status.side_effect = requests.exceptions.HTTPError(response=response)
        mock_get.return_value = response

        with pytest.raises(DownloadError) as exc_info:
            downloader.download_json("https://example.com/api")

        assert "Endpoint not found" in str(exc_info.value)

    @patch("requests.Session.get")
    @patch("time.sleep")
    def test_download_json_retry_on_error(self, mock_sleep, mock_get, downloader, mock_response):
        """Test JSON download retry logic"""
        error_response = Mock()
        error_response.status_code = 503
        error_response.raise_for_status.side_effect = requests.exceptions.HTTPError(
            response=error_response
        )

        mock_get.side_effect = [error_response, mock_response]

        data = downloader.download_json("https://example.com/api")

        assert data == {"status": "success", "data": [1, 2, 3]}
        assert mock_get.call_count == 2

    # =====================
    # CONTEXT MANAGER TESTS
    # =====================

    def test_context_manager_usage(self, mock_response):
        """Test downloader as context manager"""
        with patch("requests.Session.get", return_value=mock_response):
            with Downloader() as downloader:
                content = downloader.download("https://example.com/data")
                assert content == b"test data content"

    def test_close_method(self, downloader):
        """Test session cleanup on close"""
        session_mock = Mock()
        downloader.session = session_mock

        downloader.close()

        session_mock.close.assert_called_once()

    # =====================
    # EDGE CASE TESTS
    # =====================

    @patch("requests.Session.get")
    def test_download_empty_response(self, mock_get, downloader):
        """Test handling of empty response"""
        response = Mock()
        response.status_code = 200
        response.content = b""
        response.raise_for_status.return_value = None
        mock_get.return_value = response

        content = downloader.download("https://example.com/empty")

        assert content == b""

    @patch("requests.Session.get")
    def test_download_large_response(self, mock_get, downloader):
        """Test handling of large response (streaming)"""
        large_content = b"x" * (10 * 1024 * 1024)  # 10 MB
        response = Mock()
        response.status_code = 200
        response.content = large_content
        response.raise_for_status.return_value = None
        mock_get.return_value = response

        content = downloader.download("https://example.com/large")

        assert len(content) == 10 * 1024 * 1024

    def test_downloader_reusable(self, downloader, mock_response):
        """Test that downloader can be reused for multiple downloads"""
        with patch("requests.Session.get", return_value=mock_response):
            content1 = downloader.download("https://example.com/data1")
            content2 = downloader.download("https://example.com/data2")

            assert content1 == b"test data content"
            assert content2 == b"test data content"
