from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from botocore.exceptions import BotoCoreError, ClientError, EndpointConnectionError, NoCredentialsError, ReadTimeoutError
from pytest_mock import MockerFixture

from pipelex.tools.storage.exceptions import StorageFileNotFoundError, StorageInvalidKeyError, StorageS3Error
from pipelex.tools.storage.s3_storage_provider import S3StorageProvider
from pipelex.tools.storage.storage_provider_abstract import PIPELEX_STORAGE_SCHEME

# Test constants
S3_TEST_BUCKET = "test-pipelex-bucket"
S3_TEST_REGION = "us-east-1"


@pytest.mark.asyncio(loop_scope="class")
class TestS3StorageProvider:
    """Unit tests for S3StorageProvider using mocks for aioboto3."""

    @pytest.fixture
    def mock_aioboto3(self, mocker: MockerFixture) -> dict[str, Any]:
        """Mock aioboto3 session and client.

        Returns a dict containing the mocked session, client, and response objects
        for test assertions.
        """
        # Create mock stream for response body
        mock_stream = AsyncMock()
        mock_stream.read = AsyncMock(return_value=b"")
        mock_stream.__aenter__ = AsyncMock(return_value=mock_stream)
        mock_stream.__aexit__ = AsyncMock(return_value=None)

        # Create mock client
        mock_client = AsyncMock()
        mock_client.get_object = AsyncMock(return_value={"Body": mock_stream})
        mock_client.put_object = AsyncMock(return_value={})
        mock_client.generate_presigned_url = AsyncMock(
            return_value=f"https://{S3_TEST_BUCKET}.s3.{S3_TEST_REGION}.amazonaws.com/test?signature=abc123"
        )

        # Create mock exceptions (modeled exceptions on the client)
        mock_exceptions = MagicMock()
        mock_exceptions.NoSuchKey = type("NoSuchKey", (Exception,), {})
        mock_exceptions.NoSuchBucket = type("NoSuchBucket", (Exception,), {})
        mock_client.exceptions = mock_exceptions

        # Create async context manager for client
        mock_client_context = AsyncMock()
        mock_client_context.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_context.__aexit__ = AsyncMock(return_value=None)

        # Create mock session
        mock_session = MagicMock()
        mock_session.client = MagicMock(return_value=mock_client_context)

        # Patch aioboto3.Session
        mocker.patch("aioboto3.Session", return_value=mock_session)

        return {
            "session": mock_session,
            "client": mock_client,
            "client_context": mock_client_context,
            "stream": mock_stream,
            "exceptions": mock_exceptions,
        }

    @pytest.fixture
    def s3_provider_no_signed_urls(self) -> S3StorageProvider:
        """Create an S3StorageProvider with signed URLs disabled."""
        return S3StorageProvider(
            bucket_name=S3_TEST_BUCKET,
            region=S3_TEST_REGION,
            signed_urls_lifespan=None,
        )

    @pytest.fixture
    def s3_provider_with_signed_urls(self) -> S3StorageProvider:
        """Create an S3StorageProvider with signed URLs enabled (1 hour lifespan)."""
        return S3StorageProvider(
            bucket_name=S3_TEST_BUCKET,
            region=S3_TEST_REGION,
            signed_urls_lifespan=3600,
        )

    async def test_store_returns_uri_with_scheme(
        self,
        s3_provider_no_signed_urls: S3StorageProvider,
        mock_aioboto3: dict[str, Any],  # noqa: ARG002
    ) -> None:
        """Test that store() returns a URI with the pipelex-storage:// scheme prefix."""
        test_data = b"Hello, World!"
        key = "test/file.bin"

        returned_uri = await s3_provider_no_signed_urls.store(data=test_data, key=key)

        assert returned_uri == f"{PIPELEX_STORAGE_SCHEME}{key}"
        assert returned_uri.startswith(PIPELEX_STORAGE_SCHEME)

    async def test_store_calls_put_object(
        self,
        s3_provider_no_signed_urls: S3StorageProvider,
        mock_aioboto3: dict[str, Any],
    ) -> None:
        """Test that store() correctly calls the S3 put_object method."""
        test_data = b"Test data"
        key = "test/file.bin"
        content_type = "application/octet-stream"

        await s3_provider_no_signed_urls.store(data=test_data, key=key, content_type=content_type)

        mock_aioboto3["client"].put_object.assert_called_once_with(
            Bucket=S3_TEST_BUCKET,
            Key=key,
            Body=test_data,
            ContentType=content_type,
        )

    async def test_load_returns_data(
        self,
        s3_provider_no_signed_urls: S3StorageProvider,
        mock_aioboto3: dict[str, Any],
    ) -> None:
        """Test that load() returns the data from S3."""
        expected_data = b"Test data \x00\x01\x02\xff"
        mock_aioboto3["stream"].read = AsyncMock(return_value=expected_data)

        uri = f"{PIPELEX_STORAGE_SCHEME}test/file.bin"
        loaded_data = await s3_provider_no_signed_urls.load(uri=uri)

        assert loaded_data == expected_data

    async def test_load_with_nonexistent_key_raises_error(
        self,
        s3_provider_no_signed_urls: S3StorageProvider,
        mock_aioboto3: dict[str, Any],
    ) -> None:
        """Test that loading a non-existent object raises StorageFileNotFoundError."""
        mock_aioboto3["client"].get_object = AsyncMock(side_effect=mock_aioboto3["exceptions"].NoSuchKey("Key not found"))
        nonexistent_uri = f"{PIPELEX_STORAGE_SCHEME}nonexistent/file.bin"

        with pytest.raises(StorageFileNotFoundError) as exc_info:
            await s3_provider_no_signed_urls.load(uri=nonexistent_uri)

        assert "nonexistent/file.bin" in str(exc_info.value)

    async def test_store_raises_if_key_has_scheme_prefix(
        self,
        s3_provider_no_signed_urls: S3StorageProvider,
        mock_aioboto3: dict[str, Any],  # noqa: ARG002
    ) -> None:
        """Test that passing a key with pipelex-storage:// prefix raises an error."""
        invalid_key = f"{PIPELEX_STORAGE_SCHEME}already/prefixed.bin"

        with pytest.raises(StorageInvalidKeyError) as exc_info:
            await s3_provider_no_signed_urls.store(data=b"test", key=invalid_key)

        assert "should not include scheme prefix" in str(exc_info.value).lower()

    async def test_public_url_returns_public_url_when_signed_urls_disabled(
        self,
        s3_provider_no_signed_urls: S3StorageProvider,
        mock_aioboto3: dict[str, Any],  # noqa: ARG002
    ) -> None:
        """Test that public_url() returns a public URL when signed URLs are disabled."""
        key = "display/test.bin"
        uri = f"{PIPELEX_STORAGE_SCHEME}{key}"

        display = await s3_provider_no_signed_urls.public_url(uri=uri)

        expected_url = f"https://{S3_TEST_BUCKET}.s3.{S3_TEST_REGION}.amazonaws.com/{key}"
        assert display == expected_url

    async def test_public_url_returns_presigned_url_when_signed_urls_enabled(
        self,
        s3_provider_with_signed_urls: S3StorageProvider,
        mock_aioboto3: dict[str, Any],
    ) -> None:
        """Test that public_url() returns a presigned URL when signed URLs are enabled."""
        key = "presigned/test.bin"
        uri = f"{PIPELEX_STORAGE_SCHEME}{key}"
        expected_presigned = "https://test-bucket.s3.amazonaws.com/presigned/test.bin?X-Amz-Signature=xyz"
        mock_aioboto3["client"].generate_presigned_url = AsyncMock(return_value=expected_presigned)

        display = await s3_provider_with_signed_urls.public_url(uri=uri)

        assert display == expected_presigned
        mock_aioboto3["client"].generate_presigned_url.assert_called_once_with(
            "get_object",
            Params={"Bucket": S3_TEST_BUCKET, "Key": key},
            ExpiresIn=3600,
        )

    async def test_public_url_handles_sync_presigned_url(
        self,
        s3_provider_with_signed_urls: S3StorageProvider,
        mock_aioboto3: dict[str, Any],
    ) -> None:
        """Test that public_url() handles sync presigned URL generation (non-awaitable)."""
        key = "sync-presign/test.bin"
        uri = f"{PIPELEX_STORAGE_SCHEME}{key}"
        expected_presigned = "https://test-bucket.s3.amazonaws.com/sync-presign/test.bin?X-Amz-Signature=sync"
        # Return a plain string (non-awaitable) to simulate sync behavior in some aioboto3 versions
        mock_aioboto3["client"].generate_presigned_url = MagicMock(return_value=expected_presigned)

        display = await s3_provider_with_signed_urls.public_url(uri=uri)

        assert display == expected_presigned

    async def test_store_with_nested_path(
        self,
        s3_provider_no_signed_urls: S3StorageProvider,
        mock_aioboto3: dict[str, Any],
    ) -> None:
        """Test storing data in a deeply nested path structure."""
        test_data = b"nested content"
        key = "level1/level2/level3/deep_file.bin"

        returned_uri = await s3_provider_no_signed_urls.store(data=test_data, key=key)

        assert returned_uri == f"{PIPELEX_STORAGE_SCHEME}{key}"
        mock_aioboto3["client"].put_object.assert_called_once()

    async def test_store_empty_bytes(
        self,
        s3_provider_no_signed_urls: S3StorageProvider,
        mock_aioboto3: dict[str, Any],
    ) -> None:
        """Test storing empty bytes."""
        key = "empty.bin"

        returned_uri = await s3_provider_no_signed_urls.store(data=b"", key=key)

        assert returned_uri == f"{PIPELEX_STORAGE_SCHEME}{key}"
        mock_aioboto3["client"].put_object.assert_called_once_with(
            Bucket=S3_TEST_BUCKET,
            Key=key,
            Body=b"",
        )

    async def test_store_large_binary_data(
        self,
        s3_provider_no_signed_urls: S3StorageProvider,
        mock_aioboto3: dict[str, Any],
    ) -> None:
        """Test storing larger binary data."""
        test_data = bytes(range(256)) * 1000  # ~256KB of data
        key = "large_file.bin"

        returned_uri = await s3_provider_no_signed_urls.store(data=test_data, key=key)

        assert returned_uri == f"{PIPELEX_STORAGE_SCHEME}{key}"
        mock_aioboto3["client"].put_object.assert_called_once()

    async def test_store_bucket_not_found_raises_error(
        self,
        s3_provider_no_signed_urls: S3StorageProvider,
        mock_aioboto3: dict[str, Any],
    ) -> None:
        """Test that storing to a non-existent bucket raises StorageS3Error."""
        mock_aioboto3["client"].put_object = AsyncMock(side_effect=mock_aioboto3["exceptions"].NoSuchBucket("Bucket not found"))

        with pytest.raises(StorageS3Error) as exc_info:
            await s3_provider_no_signed_urls.store(data=b"test", key="test.bin")

        assert "Bucket not found" in str(exc_info.value)

    async def test_load_bucket_not_found_raises_error(
        self,
        s3_provider_no_signed_urls: S3StorageProvider,
        mock_aioboto3: dict[str, Any],
    ) -> None:
        """Test that loading from a non-existent bucket raises StorageS3Error."""
        mock_aioboto3["client"].get_object = AsyncMock(side_effect=mock_aioboto3["exceptions"].NoSuchBucket("Bucket not found"))
        uri = f"{PIPELEX_STORAGE_SCHEME}test.bin"

        with pytest.raises(StorageS3Error) as exc_info:
            await s3_provider_no_signed_urls.load(uri=uri)

        assert "Bucket not found" in str(exc_info.value)

    async def test_load_client_error_with_no_such_key_code_raises_file_not_found(
        self,
        s3_provider_no_signed_urls: S3StorageProvider,
        mock_aioboto3: dict[str, Any],
    ) -> None:
        """Test that ClientError with NoSuchKey code raises StorageFileNotFoundError."""
        error_response: Any = {"Error": {"Code": "NoSuchKey", "Message": "The specified key does not exist."}}
        mock_aioboto3["client"].get_object = AsyncMock(side_effect=ClientError(error_response, "GetObject"))
        uri = f"{PIPELEX_STORAGE_SCHEME}missing/file.bin"

        with pytest.raises(StorageFileNotFoundError) as exc_info:
            await s3_provider_no_signed_urls.load(uri=uri)

        assert "missing/file.bin" in str(exc_info.value)

    async def test_load_client_error_with_access_denied_raises_s3_error(
        self,
        s3_provider_no_signed_urls: S3StorageProvider,
        mock_aioboto3: dict[str, Any],
    ) -> None:
        """Test that ClientError with AccessDenied code raises StorageS3Error."""
        error_response: Any = {"Error": {"Code": "AccessDenied", "Message": "Access Denied"}}
        mock_aioboto3["client"].get_object = AsyncMock(side_effect=ClientError(error_response, "GetObject"))
        uri = f"{PIPELEX_STORAGE_SCHEME}forbidden/file.bin"

        with pytest.raises(StorageS3Error) as exc_info:
            await s3_provider_no_signed_urls.load(uri=uri)

        assert "AccessDenied" in str(exc_info.value)

    async def test_store_client_error_raises_s3_error(
        self,
        s3_provider_no_signed_urls: S3StorageProvider,
        mock_aioboto3: dict[str, Any],
    ) -> None:
        """Test that ClientError during store raises StorageS3Error."""
        error_response: Any = {"Error": {"Code": "InvalidAccessKeyId", "Message": "Invalid access key"}}
        mock_aioboto3["client"].put_object = AsyncMock(side_effect=ClientError(error_response, "PutObject"))

        with pytest.raises(StorageS3Error) as exc_info:
            await s3_provider_no_signed_urls.store(data=b"test", key="test.bin")

        assert "InvalidAccessKeyId" in str(exc_info.value)

    async def test_load_no_credentials_error_raises_s3_error(
        self,
        s3_provider_no_signed_urls: S3StorageProvider,
        mock_aioboto3: dict[str, Any],
    ) -> None:
        """Test that NoCredentialsError (a BotoCoreError subclass) raises StorageS3Error."""
        mock_aioboto3["client"].get_object = AsyncMock(side_effect=NoCredentialsError())
        uri = f"{PIPELEX_STORAGE_SCHEME}test.bin"

        with pytest.raises(StorageS3Error) as exc_info:
            await s3_provider_no_signed_urls.load(uri=uri)

        assert "NoCredentialsError" in str(exc_info.value)
        assert isinstance(exc_info.value.__cause__, BotoCoreError)

    async def test_store_no_credentials_error_raises_s3_error(
        self,
        s3_provider_no_signed_urls: S3StorageProvider,
        mock_aioboto3: dict[str, Any],
    ) -> None:
        """Test that NoCredentialsError (a BotoCoreError subclass) during store raises StorageS3Error."""
        mock_aioboto3["client"].put_object = AsyncMock(side_effect=NoCredentialsError())

        with pytest.raises(StorageS3Error) as exc_info:
            await s3_provider_no_signed_urls.store(data=b"test", key="test.bin")

        assert "NoCredentialsError" in str(exc_info.value)
        assert isinstance(exc_info.value.__cause__, BotoCoreError)

    async def test_load_endpoint_connection_error_raises_s3_error(
        self,
        s3_provider_no_signed_urls: S3StorageProvider,
        mock_aioboto3: dict[str, Any],
    ) -> None:
        """Test that EndpointConnectionError (a BotoCoreError subclass) raises StorageS3Error."""
        mock_aioboto3["client"].get_object = AsyncMock(side_effect=EndpointConnectionError(endpoint_url="https://s3.amazonaws.com"))
        uri = f"{PIPELEX_STORAGE_SCHEME}test.bin"

        with pytest.raises(StorageS3Error) as exc_info:
            await s3_provider_no_signed_urls.load(uri=uri)

        assert "EndpointConnectionError" in str(exc_info.value)
        assert isinstance(exc_info.value.__cause__, BotoCoreError)

    async def test_load_read_timeout_error_raises_s3_error(
        self,
        s3_provider_no_signed_urls: S3StorageProvider,
        mock_aioboto3: dict[str, Any],
    ) -> None:
        """Test that ReadTimeoutError — the canonical transient-network BotoCoreError that used to escape — raises StorageS3Error."""
        mock_aioboto3["client"].get_object = AsyncMock(side_effect=ReadTimeoutError(endpoint_url="https://s3.amazonaws.com"))
        uri = f"{PIPELEX_STORAGE_SCHEME}slow/file.bin"

        with pytest.raises(StorageS3Error) as exc_info:
            await s3_provider_no_signed_urls.load(uri=uri)

        assert "slow/file.bin" in str(exc_info.value)
        assert "ReadTimeoutError" in str(exc_info.value)
        assert isinstance(exc_info.value.__cause__, BotoCoreError)

    async def test_store_read_timeout_error_raises_s3_error(
        self,
        s3_provider_no_signed_urls: S3StorageProvider,
        mock_aioboto3: dict[str, Any],
    ) -> None:
        """Test that ReadTimeoutError during store (slow upload, transient blip) raises StorageS3Error."""
        mock_aioboto3["client"].put_object = AsyncMock(side_effect=ReadTimeoutError(endpoint_url="https://s3.amazonaws.com"))

        with pytest.raises(StorageS3Error) as exc_info:
            await s3_provider_no_signed_urls.store(data=b"test", key="slow/upload.bin")

        assert "slow/upload.bin" in str(exc_info.value)
        assert "ReadTimeoutError" in str(exc_info.value)
        assert isinstance(exc_info.value.__cause__, BotoCoreError)

    async def test_public_url_falls_back_to_public_url_on_botocore_error(
        self,
        s3_provider_with_signed_urls: S3StorageProvider,
        mock_aioboto3: dict[str, Any],
    ) -> None:
        """Test that public_url() falls back to public URL on a transport BotoCoreError, not just ClientError."""
        key = "fallback/timeout.bin"
        uri = f"{PIPELEX_STORAGE_SCHEME}{key}"
        mock_aioboto3["client"].generate_presigned_url = MagicMock(side_effect=ReadTimeoutError(endpoint_url="https://s3.amazonaws.com"))

        display = await s3_provider_with_signed_urls.public_url(uri=uri)

        expected_public_url = f"https://{S3_TEST_BUCKET}.s3.{S3_TEST_REGION}.amazonaws.com/{key}"
        assert display == expected_public_url

    async def test_public_url_falls_back_to_public_url_on_client_error(
        self,
        s3_provider_with_signed_urls: S3StorageProvider,
        mock_aioboto3: dict[str, Any],
    ) -> None:
        """Test that public_url() falls back to public URL on botocore ClientError."""
        key = "fallback/test.bin"
        uri = f"{PIPELEX_STORAGE_SCHEME}{key}"
        error_response: Any = {"Error": {"Code": "SignatureDoesNotMatch", "Message": "Signature error"}}
        mock_aioboto3["client"].generate_presigned_url = MagicMock(side_effect=ClientError(error_response, "GeneratePresignedUrl"))

        display = await s3_provider_with_signed_urls.public_url(uri=uri)

        expected_public_url = f"https://{S3_TEST_BUCKET}.s3.{S3_TEST_REGION}.amazonaws.com/{key}"
        assert display == expected_public_url

    @pytest.mark.usefixtures("mock_aioboto3")
    async def test_session_is_reused(self) -> None:
        """Test that the session is lazily initialized and reused."""
        import aioboto3  # noqa: PLC0415

        provider = S3StorageProvider(
            bucket_name=S3_TEST_BUCKET,
            region=S3_TEST_REGION,
            signed_urls_lifespan=None,
        )

        # First call initializes the session
        await provider.store(data=b"data1", key="file1.bin")
        first_call_count: int = aioboto3.Session.call_count  # type: ignore[attr-defined] # pyright: ignore[reportUnknownMemberType,reportAttributeAccessIssue,reportUnknownVariableType]

        # Second call reuses the session
        await provider.store(data=b"data2", key="file2.bin")
        second_call_count: int = aioboto3.Session.call_count  # type: ignore[attr-defined] # pyright: ignore[reportUnknownMemberType,reportAttributeAccessIssue,reportUnknownVariableType]

        assert first_call_count == 1
        assert second_call_count == 1  # Session should only be created once
