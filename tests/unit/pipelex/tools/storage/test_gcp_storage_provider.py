from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
from pytest_mock import MockerFixture

from pipelex.tools.storage.exceptions import (
    StorageFileNotFoundError,
    StorageGcpCredentialsError,
    StorageInvalidKeyError,
)
from pipelex.tools.storage.gcp_storage_provider import GCS_SIGNED_URL_VERSION, GcpStorageProvider
from pipelex.tools.storage.storage_provider_abstract import PIPELEX_STORAGE_SCHEME


@pytest.mark.asyncio(loop_scope="class")
class TestGcpStorageProvider:
    """Unit tests for GcpStorageProvider using mocks for google.cloud.storage."""

    @pytest.fixture
    def gcp_bucket_name(self) -> str:
        """Return the test bucket name."""
        return "test-pipelex-bucket"

    @pytest.fixture
    def gcp_project_id(self) -> str:
        """Return the test GCP project ID."""
        return "test-project-id"

    @pytest.fixture
    def gcp_credentials_file(self, tmp_path: Path) -> str:
        """Create a mock credentials file and return its path."""
        credentials_path = tmp_path / "credentials.json"
        credentials_path.write_text('{"type": "service_account"}')
        return str(credentials_path)

    @pytest.fixture
    def mock_gcp_storage(self, mocker: MockerFixture) -> dict[str, Any]:
        """Mock the google.cloud.storage module.

        Returns a dict containing the mocked client, bucket, and blob objects
        for test assertions.
        """
        # Import the module first so it can be patched
        from google.cloud import storage  # type: ignore[import-untyped]  # ruff: ignore[import-outside-top-level]

        # Create mock objects
        mock_blob = mocker.MagicMock()
        mock_blob.exists.return_value = True
        mock_blob.download_as_bytes.return_value = b""
        mock_blob.upload_from_string = mocker.MagicMock()
        mock_blob.generate_signed_url.return_value = "https://storage.googleapis.com/signed-url"

        mock_bucket = mocker.MagicMock()
        mock_bucket.blob.return_value = mock_blob

        mock_client = mocker.MagicMock()
        mock_client.bucket.return_value = mock_bucket

        # Patch the Client.from_service_account_json method directly
        mock_from_service_account = mocker.patch.object(
            storage.Client,
            "from_service_account_json",
            return_value=mock_client,
        )

        return {
            "client": mock_client,
            "bucket": mock_bucket,
            "blob": mock_blob,
            "from_service_account_json": mock_from_service_account,
        }

    @pytest.fixture
    def gcp_provider_no_signed_urls(
        self,
        gcp_bucket_name: str,
        gcp_project_id: str,
        gcp_credentials_file: str,
        mock_gcp_storage: dict[str, Any],  # ruff: ignore[unused-method-argument]
    ) -> GcpStorageProvider:
        """Create a GcpStorageProvider with signed URLs disabled."""
        return GcpStorageProvider(
            bucket_name=gcp_bucket_name,
            project_id=gcp_project_id,
            credentials_file_path=gcp_credentials_file,
            signed_urls_lifespan=None,
        )

    @pytest.fixture
    def gcp_provider_with_signed_urls(
        self,
        gcp_bucket_name: str,
        gcp_project_id: str,
        gcp_credentials_file: str,
        mock_gcp_storage: dict[str, Any],  # ruff: ignore[unused-method-argument]
    ) -> GcpStorageProvider:
        """Create a GcpStorageProvider with signed URLs enabled (1 hour lifespan)."""
        return GcpStorageProvider(
            bucket_name=gcp_bucket_name,
            project_id=gcp_project_id,
            credentials_file_path=gcp_credentials_file,
            signed_urls_lifespan=3600,
        )

    async def test_store_returns_uri_with_scheme(
        self,
        gcp_provider_no_signed_urls: GcpStorageProvider,
    ) -> None:
        """Test that store() returns a URI with the pipelex-storage:// scheme prefix."""
        test_data = b"Hello, World!"
        key = "test/file.bin"

        returned_uri = await gcp_provider_no_signed_urls.store(data=test_data, key=key)

        assert returned_uri == f"{PIPELEX_STORAGE_SCHEME}{key}"
        assert returned_uri.startswith(PIPELEX_STORAGE_SCHEME)

    async def test_store_calls_upload_from_string(
        self,
        gcp_provider_no_signed_urls: GcpStorageProvider,
        mock_gcp_storage: dict[str, Any],
    ) -> None:
        """Test that store() correctly calls the GCS upload method."""
        test_data = b"Test data"
        key = "test/file.bin"
        content_type = "application/octet-stream"

        await gcp_provider_no_signed_urls.store(data=test_data, key=key, content_type=content_type)

        mock_gcp_storage["bucket"].blob.assert_called_once_with(key)
        mock_gcp_storage["blob"].upload_from_string.assert_called_once_with(
            test_data,
            content_type=content_type,
        )

    async def test_load_returns_data(
        self,
        gcp_provider_no_signed_urls: GcpStorageProvider,
        mock_gcp_storage: dict[str, Any],
    ) -> None:
        """Test that load() returns the data from GCS."""
        expected_data = b"Test data \x00\x01\x02\xff"
        mock_gcp_storage["blob"].download_as_bytes.return_value = expected_data

        uri = f"{PIPELEX_STORAGE_SCHEME}test/file.bin"
        loaded_data = await gcp_provider_no_signed_urls.load(uri=uri)

        assert loaded_data == expected_data

    async def test_load_with_nonexistent_key_raises_error(
        self,
        gcp_provider_no_signed_urls: GcpStorageProvider,
        mock_gcp_storage: dict[str, Any],
    ) -> None:
        """Test that loading a non-existent object raises StorageFileNotFoundError."""
        from google.api_core.exceptions import NotFound  # type: ignore[import-untyped]  # ruff: ignore[import-outside-top-level]

        mock_gcp_storage["blob"].download_as_bytes.side_effect = NotFound("Object not found")
        nonexistent_uri = f"{PIPELEX_STORAGE_SCHEME}nonexistent/file.bin"

        with pytest.raises(StorageFileNotFoundError) as exc_info:
            await gcp_provider_no_signed_urls.load(uri=nonexistent_uri)

        assert "nonexistent/file.bin" in str(exc_info.value)

    async def test_store_raises_if_key_has_scheme_prefix(
        self,
        gcp_provider_no_signed_urls: GcpStorageProvider,
    ) -> None:
        """Test that passing a key with pipelex-storage:// prefix raises an error."""
        invalid_key = f"{PIPELEX_STORAGE_SCHEME}already/prefixed.bin"

        with pytest.raises(StorageInvalidKeyError) as exc_info:
            await gcp_provider_no_signed_urls.store(data=b"test", key=invalid_key)

        assert "should not include scheme prefix" in str(exc_info.value).lower()

    async def test_public_url_returns_public_url_when_signed_urls_disabled(
        self,
        gcp_provider_no_signed_urls: GcpStorageProvider,
        gcp_bucket_name: str,
    ) -> None:
        """Test that public_url() returns a public URL when signed URLs are disabled."""
        key = "display/test.bin"
        uri = f"{PIPELEX_STORAGE_SCHEME}{key}"

        display = await gcp_provider_no_signed_urls.public_url(uri=uri)

        expected_url = f"https://storage.googleapis.com/{gcp_bucket_name}/{key}"
        assert display == expected_url

    async def test_public_url_returns_signed_url_when_signed_urls_enabled(
        self,
        gcp_provider_with_signed_urls: GcpStorageProvider,
        mock_gcp_storage: dict[str, Any],
    ) -> None:
        """Test that public_url() returns a signed URL when signed URLs are enabled."""
        key = "presigned/test.bin"
        uri = f"{PIPELEX_STORAGE_SCHEME}{key}"
        expected_signed_url = "https://storage.googleapis.com/signed-url?signature=xyz"
        mock_gcp_storage["blob"].generate_signed_url.return_value = expected_signed_url

        display = await gcp_provider_with_signed_urls.public_url(uri=uri)

        assert display == expected_signed_url
        mock_gcp_storage["blob"].generate_signed_url.assert_called_once_with(
            version=GCS_SIGNED_URL_VERSION,
            expiration=timedelta(seconds=3600),
            method="GET",
        )

    async def test_credentials_file_not_found_raises_error(
        self,
        gcp_bucket_name: str,
        gcp_project_id: str,
    ) -> None:
        """Test that a missing credentials file raises StorageGcpCredentialsError."""
        provider = GcpStorageProvider(
            bucket_name=gcp_bucket_name,
            project_id=gcp_project_id,
            credentials_file_path="/nonexistent/credentials.json",
            signed_urls_lifespan=None,
        )

        with pytest.raises(StorageGcpCredentialsError) as exc_info:
            await provider.store(data=b"test", key="test.bin")

        assert "credentials file not found" in str(exc_info.value).lower()

    async def test_store_with_nested_path(
        self,
        gcp_provider_no_signed_urls: GcpStorageProvider,
        mock_gcp_storage: dict[str, Any],
    ) -> None:
        """Test storing data in a deeply nested path structure."""
        test_data = b"nested content"
        key = "level1/level2/level3/deep_file.bin"

        returned_uri = await gcp_provider_no_signed_urls.store(data=test_data, key=key)

        assert returned_uri == f"{PIPELEX_STORAGE_SCHEME}{key}"
        mock_gcp_storage["bucket"].blob.assert_called_with(key)

    async def test_store_empty_bytes(
        self,
        gcp_provider_no_signed_urls: GcpStorageProvider,
        mock_gcp_storage: dict[str, Any],
    ) -> None:
        """Test storing empty bytes."""
        key = "empty.bin"

        returned_uri = await gcp_provider_no_signed_urls.store(data=b"", key=key)

        assert returned_uri == f"{PIPELEX_STORAGE_SCHEME}{key}"
        mock_gcp_storage["blob"].upload_from_string.assert_called_once_with(b"", content_type=None)

    async def test_multiple_operations_use_same_bucket(
        self,
        gcp_provider_no_signed_urls: GcpStorageProvider,
        mock_gcp_storage: dict[str, Any],
    ) -> None:
        """Test that multiple operations reuse the same bucket (lazy initialization)."""
        await gcp_provider_no_signed_urls.store(data=b"data1", key="file1.bin")
        await gcp_provider_no_signed_urls.store(data=b"data2", key="file2.bin")

        # Client should only be created once (lazy initialization)
        mock_gcp_storage["from_service_account_json"].assert_called_once()
