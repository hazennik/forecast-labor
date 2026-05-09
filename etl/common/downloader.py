"""
Downloader Utility
Handles HTTP downloads, retries, and error handling for data sources
"""

import time
from pathlib import Path
from typing import Optional, Dict, Any

import requests
from loguru import logger


class DownloadError(Exception):
    """Raised when download fails after retries"""

    pass


class Downloader:
    """
    Robust downloader with retry logic and error handling
    """

    def __init__(
        self,
        max_retries: int = 3,
        retry_delay: int = 5,
        timeout: int = 30,
        user_agent: str = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    ):
        """
        Initialize downloader

        Args:
            max_retries: Maximum number of retry attempts
            retry_delay: Seconds to wait between retries
            timeout: Request timeout in seconds
            user_agent: User agent string (defaults to browser-like agent to avoid bot detection)
        """
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": user_agent})

    def download(
        self,
        url: str,
        output_path: Optional[Path] = None,
        headers: Optional[Dict[str, str]] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> bytes:
        """
        Download file from URL with retry logic

        Args:
            url: URL to download from
            output_path: Optional path to save file
            headers: Optional HTTP headers
            params: Optional query parameters

        Returns:
            bytes: Downloaded content

        Raises:
            DownloadError: If download fails after retries
        """
        if headers:
            self.session.headers.update(headers)

        for attempt in range(1, self.max_retries + 1):
            try:
                logger.info(f"Downloading: {url} (attempt {attempt}/{self.max_retries})")

                response = self.session.get(url, params=params, timeout=self.timeout, stream=True)
                response.raise_for_status()

                content = response.content

                logger.info(f"Downloaded {len(content)} bytes from {url}")

                # Save to file if path provided
                if output_path:
                    output_path.parent.mkdir(parents=True, exist_ok=True)
                    output_path.write_bytes(content)
                    logger.info(f"Saved to: {output_path}")

                return content

            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 404:
                    raise DownloadError(f"File not found: {url}") from e
                logger.warning(f"HTTP error {e.response.status_code}: {url}")

            except requests.exceptions.ConnectionError:
                logger.warning(f"Connection error: {url}")

            except requests.exceptions.Timeout:
                logger.warning(f"Timeout error: {url}")

            except Exception as e:
                logger.warning(f"Unexpected error: {e}")

            # Retry with delay
            if attempt < self.max_retries:
                logger.info(f"Retrying in {self.retry_delay} seconds...")
                time.sleep(self.retry_delay)

        raise DownloadError(f"Failed to download after {self.max_retries} attempts: {url}")

    def download_json(
        self,
        url: str,
        headers: Optional[Dict[str, str]] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Download and parse JSON response

        Args:
            url: URL to download from
            headers: Optional HTTP headers
            params: Optional query parameters

        Returns:
            dict: Parsed JSON response
        """
        if headers:
            self.session.headers.update(headers)

        for attempt in range(1, self.max_retries + 1):
            try:
                logger.info(f"Fetching JSON: {url} (attempt {attempt}/{self.max_retries})")

                response = self.session.get(url, params=params, timeout=self.timeout)
                response.raise_for_status()

                data = response.json()

                logger.info(f"Received JSON response from {url}")

                return data

            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 404:
                    raise DownloadError(f"Endpoint not found: {url}") from e
                logger.warning(f"HTTP error {e.response.status_code}: {url}")

            except requests.exceptions.JSONDecodeError as e:
                logger.error(f"Invalid JSON response from {url}")
                raise DownloadError(f"Invalid JSON: {url}") from e

            except Exception as e:
                logger.warning(f"Error fetching JSON: {e}")

            # Retry with delay
            if attempt < self.max_retries:
                logger.info(f"Retrying in {self.retry_delay} seconds...")
                time.sleep(self.retry_delay)

        raise DownloadError(f"Failed to fetch JSON after {self.max_retries} attempts: {url}")

    def close(self):
        """Close session"""
        self.session.close()

    def __enter__(self):
        """Context manager entry"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        self.close()
