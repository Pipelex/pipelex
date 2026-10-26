import base64
import hashlib
from typing import Any

import pytest
from botocore.exceptions import BotoCoreError, ClientError, EndpointConnectionError, NoCredentialsError, ReadTimeoutError
from pytest_mock import MockerFixture

from pipelex.errors.problem import ProblemView
from pipelex.errors.registry.pipelex_codes import PipelexErrorCode
from pipelex.tools.storage.exceptions import StorageFileNotFoundError, StorageInvalidKeyError, StorageS3Error
from pipelex.tools.storage.s3_storage_provider import (
    CONDITIONAL_CONFLICT_RETRY_DELAYS_SECONDS,
    S3_MAX_POOL_CONNECTIONS,
    S3StorageProvider,
    checksum_sha256_header_value,
)
from pipelex.tools.storage.storage_provider_abstract import PIPELEX_STORAGE_SCHEME

# Test constants
S3_TEST_BUCKET = "test-pipelex-bucket"
S3_TEST_REGION = "us-east-1"


@pytest.mark.asyncio(loop_scope="class")
class TestS3StorageProvider:
    """Unit tests for S3StorageProvider using mocks for aiobotocore."""

    @pytest.fixture
    def mock_aiobotocore(self, mocker: MockerFixture) -> dict[str, Any]:
        """Mock the aiobotocore session and client.

        Returns a dict containing the mocked session, client, and response objects
        for test assertions.
        """
        # Create mock stream for response body
        mock_stream = mocker.AsyncMock()
        mock_stream.read = mocker.AsyncMock(return_value=b"")
        mock_stream.__aenter__ = mocker.AsyncMock(return_value=mock_stream)
        mock_stream.__aexit__ = mocker.AsyncMock(return_value=None)

        # Create mock client
        mock_client = mocker.AsyncMock()
        mock_client.get_object = mocker.AsyncMock(return_value={"Body": mock_stream})
        mock_client.put_object = mocker.AsyncMock(return_value={})
        mock_client.generate_presigned_url = mocker.AsyncMock(
            return_value=f"https://{S3_TEST_BUCKET}.s3.{S3_TEST_REGION}.amazonaws.com/test?signature=abc123"
        )

        # Create mock exceptions (modeled exceptions on the client)
        mock_exceptions = mocker.MagicMock()
        mock_exceptions.NoSuchKey = type("NoSuchKey", (Exception,), {})
        mock_exceptions.NoSuchBucket = type("NoSuchBucket", (Exception,), {})
        mock_client.exceptions = mock_exceptions

        # Create async context manager for client
        mock_client_context = mocker.AsyncMock()
        mock_client_context.__aenter__ = mocker.AsyncMock(return_value=mock_client)
        mock_client_context.__aexit__ = mocker.AsyncMock(return_value=None)

        # Create mock session
        mock_session = mocker.MagicMock()
        mock_session.create_client = mocker.MagicMock(return_value=mock_client_context)

        # Patch the session factory the provider imports lazily
        mock_get_session = mocker.patch("aiobotocore.session.get_session", return_value=mock_session)

        return {
            "get_session": mock_get_session,
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
        mock_aiobotocore: dict[str, Any],  # ruff: ignore[unused-method-argument]
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
        mock_aiobotocore: dict[str, Any],
    ) -> None:
        """store() writes with put_object and asks for the SHA-256, which botocore computes when the caller has no digest."""
        test_data = b"Test data"
        key = "test/file.bin"
        content_type = "application/octet-stream"

        await s3_provider_no_signed_urls.store(data=test_data, key=key, content_type=content_type)

        mock_aiobotocore["client"].put_object.assert_called_once_with(
            Bucket=S3_TEST_BUCKET,
            Key=key,
            Body=test_data,
            ContentType=content_type,
            ChecksumAlgorithm="SHA256",
        )

    async def test_store_sends_the_callers_digest_as_the_checksum(
        self,
        s3_provider_no_signed_urls: S3StorageProvider,
        mock_aiobotocore: dict[str, Any],
    ) -> None:
        """A caller that hashed the bytes already hands the digest over, and it goes as `x-amz-checksum-sha256`."""
        data = b"generated bytes"
        sha256 = hashlib.sha256(data).hexdigest()

        await s3_provider_no_signed_urls.store(
            data=data, key="scope/generated/abc/file.pdf", content_type="application/pdf", checksum_sha256_hex=sha256
        )

        mock_aiobotocore["client"].put_object.assert_called_once_with(
            Bucket=S3_TEST_BUCKET,
            Key="scope/generated/abc/file.pdf",
            Body=data,
            ContentType="application/pdf",
            ChecksumAlgorithm="SHA256",
            ChecksumSHA256=base64.b64encode(hashlib.sha256(data).digest()).decode("ascii"),
        )

    async def test_the_client_never_signs_the_payload(
        self,
        s3_provider_no_signed_urls: S3StorageProvider,
        mock_aiobotocore: dict[str, Any],
    ) -> None:
        """The signed checksum protects the body, so botocore is not asked to hash it again to sign it."""
        await s3_provider_no_signed_urls.store(data=b"bytes", key="scope/file.bin")

        client_config = mock_aiobotocore["session"].create_client.call_args.kwargs["config"]
        assert client_config.s3 == {"addressing_style": "virtual", "payload_signing_enabled": False}

    async def test_the_client_pool_is_sized_for_operations_running_at_once(
        self,
        s3_provider_no_signed_urls: S3StorageProvider,
        mock_aiobotocore: dict[str, Any],
    ) -> None:
        """Every operation on a loop shares one client, so its pool, not botocore's default of 10, bounds them."""
        await s3_provider_no_signed_urls.store(data=b"bytes", key="scope/file.bin")

        client_config = mock_aiobotocore["session"].create_client.call_args.kwargs["config"]
        assert client_config.max_pool_connections == S3_MAX_POOL_CONNECTIONS

    async def test_load_returns_data(
        self,
        mocker: MockerFixture,
        s3_provider_no_signed_urls: S3StorageProvider,
        mock_aiobotocore: dict[str, Any],
    ) -> None:
        """Test that load() returns the data from S3."""
        expected_data = b"Test data \x00\x01\x02\xff"
        mock_aiobotocore["stream"].read = mocker.AsyncMock(return_value=expected_data)

        uri = f"{PIPELEX_STORAGE_SCHEME}test/file.bin"
        loaded_data = await s3_provider_no_signed_urls.load(uri=uri)

        assert loaded_data == expected_data

    async def test_load_with_nonexistent_key_raises_error(
        self,
        mocker: MockerFixture,
        s3_provider_no_signed_urls: S3StorageProvider,
        mock_aiobotocore: dict[str, Any],
    ) -> None:
        """Test that loading a non-existent object raises StorageFileNotFoundError."""
        mock_aiobotocore["client"].get_object = mocker.AsyncMock(side_effect=mock_aiobotocore["exceptions"].NoSuchKey("Key not found"))
        nonexistent_uri = f"{PIPELEX_STORAGE_SCHEME}nonexistent/file.bin"

        with pytest.raises(StorageFileNotFoundError) as exc_info:
            await s3_provider_no_signed_urls.load(uri=nonexistent_uri)

        assert "nonexistent/file.bin" in str(exc_info.value)
        problem = exc_info.value.to_problem(view=ProblemView.CALLER)
        assert problem.code == PipelexErrorCode.STORAGE_NOT_FOUND
        assert problem.params is not None
        assert problem.params.as_wire() == {"scheme": "s3"}

    async def test_store_raises_if_key_has_scheme_prefix(
        self,
        s3_provider_no_signed_urls: S3StorageProvider,
        mock_aiobotocore: dict[str, Any],  # ruff: ignore[unused-method-argument]
    ) -> None:
        """Test that passing a key with pipelex-storage:// prefix raises an error."""
        invalid_key = f"{PIPELEX_STORAGE_SCHEME}already/prefixed.bin"

        with pytest.raises(StorageInvalidKeyError) as exc_info:
            await s3_provider_no_signed_urls.store(data=b"test", key=invalid_key)

        assert "should not include scheme prefix" in str(exc_info.value).lower()

    async def test_public_url_returns_public_url_when_signed_urls_disabled(
        self,
        s3_provider_no_signed_urls: S3StorageProvider,
        mock_aiobotocore: dict[str, Any],  # ruff: ignore[unused-method-argument]
    ) -> None:
        """Test that public_url() returns a public URL when signed URLs are disabled."""
        key = "display/test.bin"
        uri = f"{PIPELEX_STORAGE_SCHEME}{key}"

        display = await s3_provider_no_signed_urls.public_url(uri=uri)

        expected_url = f"https://{S3_TEST_BUCKET}.s3.{S3_TEST_REGION}.amazonaws.com/{key}"
        assert display == expected_url

    async def test_public_url_returns_presigned_url_when_signed_urls_enabled(
        self,
        mocker: MockerFixture,
        s3_provider_with_signed_urls: S3StorageProvider,
        mock_aiobotocore: dict[str, Any],
    ) -> None:
        """Test that public_url() returns a presigned URL when signed URLs are enabled."""
        key = "presigned/test.bin"
        uri = f"{PIPELEX_STORAGE_SCHEME}{key}"
        expected_presigned = "https://test-bucket.s3.amazonaws.com/presigned/test.bin?X-Amz-Signature=xyz"
        mock_aiobotocore["client"].generate_presigned_url = mocker.AsyncMock(return_value=expected_presigned)

        display = await s3_provider_with_signed_urls.public_url(uri=uri)

        assert display == expected_presigned
        mock_aiobotocore["client"].generate_presigned_url.assert_called_once_with(
            "get_object",
            Params={"Bucket": S3_TEST_BUCKET, "Key": key},
            ExpiresIn=3600,
        )

    async def test_store_with_nested_path(
        self,
        s3_provider_no_signed_urls: S3StorageProvider,
        mock_aiobotocore: dict[str, Any],
    ) -> None:
        """Test storing data in a deeply nested path structure."""
        test_data = b"nested content"
        key = "level1/level2/level3/deep_file.bin"

        returned_uri = await s3_provider_no_signed_urls.store(data=test_data, key=key)

        assert returned_uri == f"{PIPELEX_STORAGE_SCHEME}{key}"
        mock_aiobotocore["client"].put_object.assert_called_once()

    async def test_store_empty_bytes(
        self,
        s3_provider_no_signed_urls: S3StorageProvider,
        mock_aiobotocore: dict[str, Any],
    ) -> None:
        """Test storing empty bytes."""
        key = "empty.bin"

        returned_uri = await s3_provider_no_signed_urls.store(data=b"", key=key)

        assert returned_uri == f"{PIPELEX_STORAGE_SCHEME}{key}"
        mock_aiobotocore["client"].put_object.assert_called_once_with(
            Bucket=S3_TEST_BUCKET,
            Key=key,
            Body=b"",
            ChecksumAlgorithm="SHA256",
        )

    async def test_store_large_binary_data(
        self,
        s3_provider_no_signed_urls: S3StorageProvider,
        mock_aiobotocore: dict[str, Any],
    ) -> None:
        """Test storing larger binary data."""
        test_data = bytes(range(256)) * 1000  # ~256KB of data
        key = "large_file.bin"

        returned_uri = await s3_provider_no_signed_urls.store(data=test_data, key=key)

        assert returned_uri == f"{PIPELEX_STORAGE_SCHEME}{key}"
        mock_aiobotocore["client"].put_object.assert_called_once()

    async def test_store_bucket_not_found_raises_error(
        self,
        mocker: MockerFixture,
        s3_provider_no_signed_urls: S3StorageProvider,
        mock_aiobotocore: dict[str, Any],
    ) -> None:
        """Test that storing to a non-existent bucket raises StorageS3Error."""
        mock_aiobotocore["client"].put_object = mocker.AsyncMock(side_effect=mock_aiobotocore["exceptions"].NoSuchBucket("Bucket not found"))

        with pytest.raises(StorageS3Error) as exc_info:
            await s3_provider_no_signed_urls.store(data=b"test", key="test.bin")

        assert "Bucket not found" in str(exc_info.value)
        assert exc_info.value.resolve_error_code() == PipelexErrorCode.CONFIG_INVALID

    async def test_load_bucket_not_found_raises_error(
        self,
        mocker: MockerFixture,
        s3_provider_no_signed_urls: S3StorageProvider,
        mock_aiobotocore: dict[str, Any],
    ) -> None:
        """Test that loading from a non-existent bucket raises StorageS3Error."""
        mock_aiobotocore["client"].get_object = mocker.AsyncMock(side_effect=mock_aiobotocore["exceptions"].NoSuchBucket("Bucket not found"))
        uri = f"{PIPELEX_STORAGE_SCHEME}test.bin"

        with pytest.raises(StorageS3Error) as exc_info:
            await s3_provider_no_signed_urls.load(uri=uri)

        assert "Bucket not found" in str(exc_info.value)
        assert exc_info.value.resolve_error_code() == PipelexErrorCode.CONFIG_INVALID

    async def test_load_client_error_with_no_such_key_code_raises_file_not_found(
        self,
        mocker: MockerFixture,
        s3_provider_no_signed_urls: S3StorageProvider,
        mock_aiobotocore: dict[str, Any],
    ) -> None:
        """Test that ClientError with NoSuchKey code raises StorageFileNotFoundError."""
        error_response: Any = {"Error": {"Code": "NoSuchKey", "Message": "The specified key does not exist."}}
        mock_aiobotocore["client"].get_object = mocker.AsyncMock(side_effect=ClientError(error_response, "GetObject"))
        uri = f"{PIPELEX_STORAGE_SCHEME}missing/file.bin"

        with pytest.raises(StorageFileNotFoundError) as exc_info:
            await s3_provider_no_signed_urls.load(uri=uri)

        assert "missing/file.bin" in str(exc_info.value)

    async def test_load_client_error_with_access_denied_raises_s3_error(
        self,
        mocker: MockerFixture,
        s3_provider_no_signed_urls: S3StorageProvider,
        mock_aiobotocore: dict[str, Any],
    ) -> None:
        """Test that ClientError with AccessDenied code raises StorageS3Error."""
        error_response: Any = {"Error": {"Code": "AccessDenied", "Message": "Access Denied"}}
        mock_aiobotocore["client"].get_object = mocker.AsyncMock(side_effect=ClientError(error_response, "GetObject"))
        uri = f"{PIPELEX_STORAGE_SCHEME}forbidden/file.bin"

        with pytest.raises(StorageS3Error) as exc_info:
            await s3_provider_no_signed_urls.load(uri=uri)

        assert "AccessDenied" in str(exc_info.value)
        assert exc_info.value.resolve_error_code() == PipelexErrorCode.CONFIG_CREDENTIAL_REFUSED

    async def test_store_client_error_raises_s3_error(
        self,
        mocker: MockerFixture,
        s3_provider_no_signed_urls: S3StorageProvider,
        mock_aiobotocore: dict[str, Any],
    ) -> None:
        """Test that ClientError during store raises StorageS3Error."""
        error_response: Any = {"Error": {"Code": "InvalidAccessKeyId", "Message": "Invalid access key"}}
        mock_aiobotocore["client"].put_object = mocker.AsyncMock(side_effect=ClientError(error_response, "PutObject"))

        with pytest.raises(StorageS3Error) as exc_info:
            await s3_provider_no_signed_urls.store(data=b"test", key="test.bin")

        assert "InvalidAccessKeyId" in str(exc_info.value)
        assert exc_info.value.resolve_error_code() == PipelexErrorCode.CONFIG_CREDENTIAL_REFUSED

    async def test_load_no_credentials_error_raises_s3_error(
        self,
        mocker: MockerFixture,
        s3_provider_no_signed_urls: S3StorageProvider,
        mock_aiobotocore: dict[str, Any],
    ) -> None:
        """Test that NoCredentialsError (a BotoCoreError subclass) raises StorageS3Error."""
        mock_aiobotocore["client"].get_object = mocker.AsyncMock(side_effect=NoCredentialsError())
        uri = f"{PIPELEX_STORAGE_SCHEME}test.bin"

        with pytest.raises(StorageS3Error) as exc_info:
            await s3_provider_no_signed_urls.load(uri=uri)

        assert "NoCredentialsError" in str(exc_info.value)
        assert isinstance(exc_info.value.__cause__, BotoCoreError)
        assert exc_info.value.resolve_error_code() == PipelexErrorCode.CONFIG_CREDENTIAL_MISSING

    async def test_store_no_credentials_error_raises_s3_error(
        self,
        mocker: MockerFixture,
        s3_provider_no_signed_urls: S3StorageProvider,
        mock_aiobotocore: dict[str, Any],
    ) -> None:
        """Test that NoCredentialsError (a BotoCoreError subclass) during store raises StorageS3Error."""
        mock_aiobotocore["client"].put_object = mocker.AsyncMock(side_effect=NoCredentialsError())

        with pytest.raises(StorageS3Error) as exc_info:
            await s3_provider_no_signed_urls.store(data=b"test", key="test.bin")

        assert "NoCredentialsError" in str(exc_info.value)
        assert isinstance(exc_info.value.__cause__, BotoCoreError)
        assert exc_info.value.resolve_error_code() == PipelexErrorCode.CONFIG_CREDENTIAL_MISSING

    async def test_load_endpoint_connection_error_raises_s3_error(
        self,
        mocker: MockerFixture,
        s3_provider_no_signed_urls: S3StorageProvider,
        mock_aiobotocore: dict[str, Any],
    ) -> None:
        """Test that EndpointConnectionError (a BotoCoreError subclass) raises StorageS3Error."""
        mock_aiobotocore["client"].get_object = mocker.AsyncMock(side_effect=EndpointConnectionError(endpoint_url="https://s3.amazonaws.com"))
        uri = f"{PIPELEX_STORAGE_SCHEME}test.bin"

        with pytest.raises(StorageS3Error) as exc_info:
            await s3_provider_no_signed_urls.load(uri=uri)

        assert "EndpointConnectionError" in str(exc_info.value)
        assert isinstance(exc_info.value.__cause__, BotoCoreError)
        assert exc_info.value.resolve_error_code() == PipelexErrorCode.STORAGE_UNAVAILABLE

    async def test_load_read_timeout_error_raises_s3_error(
        self,
        mocker: MockerFixture,
        s3_provider_no_signed_urls: S3StorageProvider,
        mock_aiobotocore: dict[str, Any],
    ) -> None:
        """Test that ReadTimeoutError — the canonical transient-network BotoCoreError that used to escape — raises StorageS3Error."""
        mock_aiobotocore["client"].get_object = mocker.AsyncMock(side_effect=ReadTimeoutError(endpoint_url="https://s3.amazonaws.com"))
        uri = f"{PIPELEX_STORAGE_SCHEME}slow/file.bin"

        with pytest.raises(StorageS3Error) as exc_info:
            await s3_provider_no_signed_urls.load(uri=uri)

        assert "slow/file.bin" in str(exc_info.value)
        assert "ReadTimeoutError" in str(exc_info.value)
        assert isinstance(exc_info.value.__cause__, BotoCoreError)

    async def test_store_read_timeout_error_raises_s3_error(
        self,
        mocker: MockerFixture,
        s3_provider_no_signed_urls: S3StorageProvider,
        mock_aiobotocore: dict[str, Any],
    ) -> None:
        """Test that ReadTimeoutError during store (slow upload, transient blip) raises StorageS3Error."""
        mock_aiobotocore["client"].put_object = mocker.AsyncMock(side_effect=ReadTimeoutError(endpoint_url="https://s3.amazonaws.com"))

        with pytest.raises(StorageS3Error) as exc_info:
            await s3_provider_no_signed_urls.store(data=b"test", key="slow/upload.bin")

        assert "slow/upload.bin" in str(exc_info.value)
        assert "ReadTimeoutError" in str(exc_info.value)
        assert isinstance(exc_info.value.__cause__, BotoCoreError)

    async def test_public_url_falls_back_to_public_url_on_botocore_error(
        self,
        mocker: MockerFixture,
        s3_provider_with_signed_urls: S3StorageProvider,
        mock_aiobotocore: dict[str, Any],
    ) -> None:
        """Test that public_url() falls back to public URL on a transport BotoCoreError, not just ClientError."""
        key = "fallback/timeout.bin"
        uri = f"{PIPELEX_STORAGE_SCHEME}{key}"
        mock_aiobotocore["client"].generate_presigned_url = mocker.AsyncMock(side_effect=ReadTimeoutError(endpoint_url="https://s3.amazonaws.com"))

        display = await s3_provider_with_signed_urls.public_url(uri=uri)

        expected_public_url = f"https://{S3_TEST_BUCKET}.s3.{S3_TEST_REGION}.amazonaws.com/{key}"
        assert display == expected_public_url

    async def test_public_url_falls_back_to_public_url_on_client_error(
        self,
        mocker: MockerFixture,
        s3_provider_with_signed_urls: S3StorageProvider,
        mock_aiobotocore: dict[str, Any],
    ) -> None:
        """Test that public_url() falls back to public URL on botocore ClientError."""
        key = "fallback/test.bin"
        uri = f"{PIPELEX_STORAGE_SCHEME}{key}"
        error_response: Any = {"Error": {"Code": "SignatureDoesNotMatch", "Message": "Signature error"}}
        mock_aiobotocore["client"].generate_presigned_url = mocker.AsyncMock(side_effect=ClientError(error_response, "GeneratePresignedUrl"))

        display = await s3_provider_with_signed_urls.public_url(uri=uri)

        expected_public_url = f"https://{S3_TEST_BUCKET}.s3.{S3_TEST_REGION}.amazonaws.com/{key}"
        assert display == expected_public_url

    async def test_session_and_client_are_reused(self, mock_aiobotocore: dict[str, Any]) -> None:
        """The session and the loop's client are opened on the first operation, and every later one shares them."""
        provider = S3StorageProvider(
            bucket_name=S3_TEST_BUCKET,
            region=S3_TEST_REGION,
            signed_urls_lifespan=None,
        )

        # First call initializes the session
        await provider.store(data=b"data1", key="file1.bin")
        first_call_count: int = mock_aiobotocore["get_session"].call_count

        # Second call reuses the session
        await provider.store(data=b"data2", key="file2.bin")
        second_call_count: int = mock_aiobotocore["get_session"].call_count

        assert first_call_count == 1
        assert second_call_count == 1  # Session should only be created once
        assert mock_aiobotocore["session"].create_client.call_count == 1

    async def test_load_head_sends_a_ranged_get(
        self,
        mocker: MockerFixture,
        s3_provider_no_signed_urls: S3StorageProvider,
        mock_aiobotocore: dict[str, Any],
    ) -> None:
        """A head read asks S3 for the first bytes only, through an inclusive Range header."""
        mock_aiobotocore["stream"].read = mocker.AsyncMock(return_value=b"%PDF-1.7")

        head = await s3_provider_no_signed_urls.load_head(uri=f"{PIPELEX_STORAGE_SCHEME}test/file.pdf", nb_bytes=8192)

        assert head == b"%PDF-1.7"
        mock_aiobotocore["client"].get_object.assert_called_once_with(Bucket=S3_TEST_BUCKET, Key="test/file.pdf", Range="bytes=0-8191")

    async def test_load_head_of_an_empty_object_is_empty(
        self,
        mocker: MockerFixture,
        s3_provider_no_signed_urls: S3StorageProvider,
        mock_aiobotocore: dict[str, Any],
    ) -> None:
        """S3 answers a range over an empty object with InvalidRange, which is an empty head and not a failure."""
        invalid_range = ClientError({"Error": {"Code": "InvalidRange", "Message": "The requested range is not satisfiable"}}, "GetObject")
        mock_aiobotocore["client"].get_object = mocker.AsyncMock(side_effect=invalid_range)

        head = await s3_provider_no_signed_urls.load_head(uri=f"{PIPELEX_STORAGE_SCHEME}test/empty.bin", nb_bytes=8192)

        assert head == b""

    async def test_load_head_of_a_missing_object_raises_not_found(
        self,
        mocker: MockerFixture,
        s3_provider_no_signed_urls: S3StorageProvider,
        mock_aiobotocore: dict[str, Any],
    ) -> None:
        mock_aiobotocore["client"].get_object = mocker.AsyncMock(side_effect=mock_aiobotocore["exceptions"].NoSuchKey("Key not found"))

        with pytest.raises(StorageFileNotFoundError, match=r"missing/file\.pdf"):
            await s3_provider_no_signed_urls.load_head(uri=f"{PIPELEX_STORAGE_SCHEME}missing/file.pdf", nb_bytes=8192)

    async def test_load_head_maps_other_client_errors(
        self,
        mocker: MockerFixture,
        s3_provider_no_signed_urls: S3StorageProvider,
        mock_aiobotocore: dict[str, Any],
    ) -> None:
        access_denied = ClientError({"Error": {"Code": "AccessDenied", "Message": "Access Denied"}}, "GetObject")
        mock_aiobotocore["client"].get_object = mocker.AsyncMock(side_effect=access_denied)

        with pytest.raises(StorageS3Error, match="AccessDenied"):
            await s3_provider_no_signed_urls.load_head(uri=f"{PIPELEX_STORAGE_SCHEME}test/file.pdf", nb_bytes=8192)

    async def test_load_size_reads_the_content_length_of_a_head_request(
        self,
        mocker: MockerFixture,
        s3_provider_no_signed_urls: S3StorageProvider,
        mock_aiobotocore: dict[str, Any],
    ) -> None:
        """A size read asks S3 for the object's metadata alone, never its bytes."""
        mock_aiobotocore["client"].head_object = mocker.AsyncMock(return_value={"ContentLength": 4096})

        size = await s3_provider_no_signed_urls.load_size(uri=f"{PIPELEX_STORAGE_SCHEME}test/file.pdf")

        assert size == 4096
        mock_aiobotocore["client"].head_object.assert_called_once_with(Bucket=S3_TEST_BUCKET, Key="test/file.pdf")
        mock_aiobotocore["client"].get_object.assert_not_called()

    @pytest.mark.parametrize("error_code", ["404", "NoSuchKey", "NotFound"])
    async def test_load_size_of_a_missing_object_raises_not_found(
        self,
        mocker: MockerFixture,
        s3_provider_no_signed_urls: S3StorageProvider,
        mock_aiobotocore: dict[str, Any],
        error_code: str,
    ) -> None:
        """A HEAD answer has no body, so S3 names a missing object by its bare status code."""
        missing = ClientError({"Error": {"Code": error_code, "Message": "Not Found"}}, "HeadObject")
        mock_aiobotocore["client"].head_object = mocker.AsyncMock(side_effect=missing)

        with pytest.raises(StorageFileNotFoundError, match=r"missing/file\.pdf"):
            await s3_provider_no_signed_urls.load_size(uri=f"{PIPELEX_STORAGE_SCHEME}missing/file.pdf")

    async def test_load_size_maps_other_errors(
        self,
        mocker: MockerFixture,
        s3_provider_no_signed_urls: S3StorageProvider,
        mock_aiobotocore: dict[str, Any],
    ) -> None:
        access_denied = ClientError({"Error": {"Code": "403", "Message": "Forbidden"}}, "HeadObject")
        mock_aiobotocore["client"].head_object = mocker.AsyncMock(side_effect=access_denied)
        with pytest.raises(StorageS3Error, match="403"):
            await s3_provider_no_signed_urls.load_size(uri=f"{PIPELEX_STORAGE_SCHEME}test/file.pdf")

        mock_aiobotocore["client"].head_object = mocker.AsyncMock(side_effect=EndpointConnectionError(endpoint_url="https://s3.example.com"))
        with pytest.raises(StorageS3Error):
            await s3_provider_no_signed_urls.load_size(uri=f"{PIPELEX_STORAGE_SCHEME}test/file.pdf")

    async def test_store_if_absent_sends_the_condition_and_the_checksum(
        self,
        s3_provider_no_signed_urls: S3StorageProvider,
        mock_aiobotocore: dict[str, Any],
    ) -> None:
        """`If-None-Match: *` makes S3 refuse to replace an object, and the SHA-256 makes it refuse other bytes."""
        data = b"blob bytes"
        sha256 = hashlib.sha256(data).hexdigest()

        created = await s3_provider_no_signed_urls.store_if_absent(
            data=data, key="scope/blobs/one", content_type="application/octet-stream", checksum_sha256_hex=sha256
        )

        assert created is True
        mock_aiobotocore["client"].put_object.assert_called_once_with(
            Bucket=S3_TEST_BUCKET,
            Key="scope/blobs/one",
            Body=data,
            IfNoneMatch="*",
            ContentType="application/octet-stream",
            ChecksumAlgorithm="SHA256",
            ChecksumSHA256=base64.b64encode(hashlib.sha256(data).digest()).decode("ascii"),
        )

    async def test_store_if_absent_without_a_checksum_lets_botocore_compute_it(
        self,
        s3_provider_no_signed_urls: S3StorageProvider,
        mock_aiobotocore: dict[str, Any],
    ) -> None:
        assert await s3_provider_no_signed_urls.store_if_absent(data=b"bytes", key="scope/blobs/one") is True

        mock_aiobotocore["client"].put_object.assert_called_once_with(
            Bucket=S3_TEST_BUCKET, Key="scope/blobs/one", Body=b"bytes", IfNoneMatch="*", ChecksumAlgorithm="SHA256"
        )

    @pytest.mark.parametrize("error_code", ["412", "PreconditionFailed"])
    async def test_store_if_absent_over_a_held_object_is_no_error(
        self,
        mocker: MockerFixture,
        s3_provider_no_signed_urls: S3StorageProvider,
        mock_aiobotocore: dict[str, Any],
        error_code: str,
    ) -> None:
        held = ClientError({"Error": {"Code": error_code, "Message": "At least one of the pre-conditions you specified did not hold"}}, "PutObject")
        mock_aiobotocore["client"].put_object = mocker.AsyncMock(side_effect=held)

        assert await s3_provider_no_signed_urls.store_if_absent(data=b"bytes", key="scope/blobs/one") is False

    @pytest.mark.parametrize(
        ("final_answer", "expected_created"),
        [
            (ClientError({"Error": {"Code": "PreconditionFailed", "Message": "Precondition Failed"}}, "PutObject"), False),
            ({"ETag": '"created"'}, True),
        ],
    )
    async def test_store_if_absent_retries_a_conditional_conflict_until_s3_answers(
        self,
        mocker: MockerFixture,
        s3_provider_no_signed_urls: S3StorageProvider,
        mock_aiobotocore: dict[str, Any],
        final_answer: ClientError | dict[str, str],
        expected_created: bool,
    ) -> None:
        """A `409` is retried: a later `412` is the other write's object, held, and a later success is this call's own.

        The other operation may have failed or deleted the key, leaving it free, so the PUT is sent again rather than
        the key looked up.
        """
        mocked_sleep = mocker.patch("pipelex.tools.storage.s3_storage_provider.sleep", new_callable=mocker.AsyncMock)
        conflict = ClientError({"Error": {"Code": "ConditionalRequestConflict", "Message": "Conflict"}}, "PutObject")
        mock_aiobotocore["client"].put_object = mocker.AsyncMock(side_effect=[conflict, conflict, final_answer])
        mock_aiobotocore["client"].head_object = mocker.AsyncMock()

        created = await s3_provider_no_signed_urls.store_if_absent(
            data=b"bytes", key="scope/blobs/one", checksum_sha256_hex=hashlib.sha256(b"bytes").hexdigest()
        )

        assert created is expected_created
        assert mock_aiobotocore["client"].put_object.await_count == 3
        for put_call in mock_aiobotocore["client"].put_object.await_args_list:
            assert put_call.kwargs["IfNoneMatch"] == "*"
            assert put_call.kwargs["ChecksumSHA256"] == checksum_sha256_header_value(sha256_hex=hashlib.sha256(b"bytes").hexdigest())
        assert [sleep_call.args for sleep_call in mocked_sleep.await_args_list] == [
            (delay,) for delay in CONDITIONAL_CONFLICT_RETRY_DELAYS_SECONDS[:2]
        ]
        mock_aiobotocore["client"].head_object.assert_not_awaited()

    async def test_store_if_absent_whose_conflicts_outlast_the_retries_is_an_error(
        self,
        mocker: MockerFixture,
        s3_provider_no_signed_urls: S3StorageProvider,
        mock_aiobotocore: dict[str, Any],
    ) -> None:
        mocked_sleep = mocker.patch("pipelex.tools.storage.s3_storage_provider.sleep", new_callable=mocker.AsyncMock)
        conflict = ClientError({"Error": {"Code": "409", "Message": "Conflict"}}, "PutObject")
        mock_aiobotocore["client"].put_object = mocker.AsyncMock(side_effect=conflict)
        retry_delays = CONDITIONAL_CONFLICT_RETRY_DELAYS_SECONDS

        with pytest.raises(StorageS3Error, match="ConditionalRequestConflict") as exc_info:
            await s3_provider_no_signed_urls.store_if_absent(data=b"bytes", key="scope/blobs/one")

        assert exc_info.value.__cause__ is conflict
        assert mock_aiobotocore["client"].put_object.await_count == len(retry_delays) + 1
        assert [sleep_call.args for sleep_call in mocked_sleep.await_args_list] == [(delay,) for delay in retry_delays]
        assert sum(retry_delays) < 10

    async def test_store_if_absent_maps_other_errors(
        self,
        mocker: MockerFixture,
        s3_provider_no_signed_urls: S3StorageProvider,
        mock_aiobotocore: dict[str, Any],
    ) -> None:
        refused = ClientError({"Error": {"Code": "AccessDenied", "Message": "Access Denied"}}, "PutObject")
        mock_aiobotocore["client"].put_object = mocker.AsyncMock(side_effect=refused)
        with pytest.raises(StorageS3Error, match="AccessDenied"):
            await s3_provider_no_signed_urls.store_if_absent(data=b"bytes", key="scope/blobs/one")

        mock_aiobotocore["client"].put_object = mocker.AsyncMock(side_effect=NoCredentialsError())
        with pytest.raises(StorageS3Error, match="NoCredentialsError"):
            await s3_provider_no_signed_urls.store_if_absent(data=b"bytes", key="scope/blobs/one")

    async def test_checksum_header_value_is_the_raw_digest_in_base64(self) -> None:
        data = b"blob bytes"

        assert checksum_sha256_header_value(sha256_hex=hashlib.sha256(data).hexdigest()) == base64.b64encode(hashlib.sha256(data).digest()).decode(
            "ascii"
        )
