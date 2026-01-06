from typing import Generator

import pytest
from moto import mock_aws  # pyright: ignore[reportMissingImports,reportUnknownVariableType]

from pipelex.tools.storage.exceptions import StorageFileNotFoundError, StorageInvalidKeyError
from pipelex.tools.storage.s3_storage_provider import S3StorageProvider
from pipelex.tools.storage.storage_provider_abstract import PIPELEX_STORAGE_SCHEME

# Test constants
S3_TEST_BUCKET = "test-pipelex-bucket"
S3_TEST_REGION = "us-east-1"


class TestS3StorageProvider:
    """Unit tests for S3StorageProvider using moto to mock AWS S3."""

    @pytest.fixture
    def s3_mock_context(self) -> Generator[None, None, None]:
        """Create moto mock context with test bucket."""
        with mock_aws():  # pyright: ignore[reportUnknownMemberType]
            import boto3  # noqa: PLC0415

            s3_client = boto3.client("s3", region_name=S3_TEST_REGION)  # pyright: ignore[reportUnknownMemberType,reportUnknownVariableType]
            s3_client.create_bucket(Bucket=S3_TEST_BUCKET)  # pyright: ignore[reportUnknownMemberType]
            yield

    @pytest.fixture
    def s3_provider_no_signed_urls(self, s3_mock_context: None) -> S3StorageProvider:  # noqa: ARG002
        """Create an S3StorageProvider with signed URLs disabled."""
        return S3StorageProvider(
            bucket_name=S3_TEST_BUCKET,
            region=S3_TEST_REGION,
            signed_urls_lifespan=None,
        )

    @pytest.fixture
    def s3_provider_with_signed_urls(self, s3_mock_context: None) -> S3StorageProvider:  # noqa: ARG002
        """Create an S3StorageProvider with signed URLs enabled (1 hour lifespan)."""
        return S3StorageProvider(
            bucket_name=S3_TEST_BUCKET,
            region=S3_TEST_REGION,
            signed_urls_lifespan=3600,
        )

    def test_store_returns_uri_with_scheme(
        self,
        s3_provider_no_signed_urls: S3StorageProvider,
    ) -> None:
        """Test that store() returns a URI with the pipelex-storage:// scheme prefix."""
        test_data = b"Hello, World!"
        key = "test/file.bin"

        returned_uri = s3_provider_no_signed_urls.store(data=test_data, key=key)

        assert returned_uri == f"{PIPELEX_STORAGE_SCHEME}{key}"
        assert returned_uri.startswith(PIPELEX_STORAGE_SCHEME)

    def test_load_with_valid_uri_returns_data(
        self,
        s3_provider_no_signed_urls: S3StorageProvider,
    ) -> None:
        """Test roundtrip: store data with key, load with returned URI."""
        test_data = b"Test data \x00\x01\x02\xff"
        key = "roundtrip/test.bin"

        returned_uri = s3_provider_no_signed_urls.store(data=test_data, key=key)
        loaded_data = s3_provider_no_signed_urls.load(uri=returned_uri)

        assert loaded_data == test_data

    def test_load_with_nonexistent_key_raises_error(
        self,
        s3_provider_no_signed_urls: S3StorageProvider,
    ) -> None:
        """Test that loading a non-existent URI raises StorageFileNotFoundError."""
        nonexistent_uri = f"{PIPELEX_STORAGE_SCHEME}nonexistent/file.bin"

        with pytest.raises(StorageFileNotFoundError) as exc_info:
            s3_provider_no_signed_urls.load(uri=nonexistent_uri)

        assert "nonexistent/file.bin" in str(exc_info.value)

    def test_store_raises_if_key_has_scheme_prefix(
        self,
        s3_provider_no_signed_urls: S3StorageProvider,
    ) -> None:
        """Test that passing a key with pipelex-storage:// prefix raises an error."""
        invalid_key = f"{PIPELEX_STORAGE_SCHEME}already/prefixed.bin"

        with pytest.raises(StorageInvalidKeyError) as exc_info:
            s3_provider_no_signed_urls.store(data=b"test", key=invalid_key)

        assert "should not include scheme prefix" in str(exc_info.value).lower()

    def test_display_link_returns_public_url_when_signed_urls_disabled(
        self,
        s3_provider_no_signed_urls: S3StorageProvider,
    ) -> None:
        """Test that display_link() returns a public URL when signed URLs are disabled."""
        test_data = b"display test"
        key = "display/test.bin"

        returned_uri = s3_provider_no_signed_urls.store(data=test_data, key=key)
        display = s3_provider_no_signed_urls.display_link(uri=returned_uri)

        expected_url = f"https://{S3_TEST_BUCKET}.s3.{S3_TEST_REGION}.amazonaws.com/{key}"
        assert display == expected_url

    def test_display_link_returns_presigned_url_when_signed_urls_enabled(
        self,
        s3_provider_with_signed_urls: S3StorageProvider,
    ) -> None:
        """Test that display_link() returns a presigned URL when signed URLs are enabled."""
        test_data = b"presigned test"
        key = "presigned/test.bin"

        returned_uri = s3_provider_with_signed_urls.store(data=test_data, key=key)
        display = s3_provider_with_signed_urls.display_link(uri=returned_uri)

        # Presigned URLs contain the bucket name and various query parameters
        assert display is not None
        assert S3_TEST_BUCKET in display
        assert "X-Amz-Signature" in display or "Signature" in display

    def test_presigned_url_uses_regional_endpoint(
        self,
        s3_provider_with_signed_urls: S3StorageProvider,
    ) -> None:
        """Test that presigned URLs use the regional S3 endpoint.

        This is critical for signature validation - AWS validates signatures against
        the regional endpoint, so the URL must use s3.{region}.amazonaws.com format.
        Without this, presigned URLs will fail with SignatureDoesNotMatch errors.
        """
        test_data = b"regional endpoint test"
        key = "regional/test.bin"

        returned_uri = s3_provider_with_signed_urls.store(data=test_data, key=key)
        display = s3_provider_with_signed_urls.display_link(uri=returned_uri)

        assert display is not None
        # The URL must use the regional endpoint format: s3.{region}.amazonaws.com
        # NOT the global endpoint: s3.amazonaws.com (without region)
        regional_endpoint = f"s3.{S3_TEST_REGION}.amazonaws.com"
        assert regional_endpoint in display, (
            f"Presigned URL must use regional endpoint '{regional_endpoint}' to ensure signature validation works. Got: {display}"
        )

    def test_presigned_url_credential_matches_region(
        self,
        s3_provider_with_signed_urls: S3StorageProvider,
    ) -> None:
        """Test that the credential region in presigned URL matches the configured region.

        The X-Amz-Credential parameter must include the correct region for signature
        validation to succeed.
        """
        test_data = b"credential region test"
        key = "credential/test.bin"

        returned_uri = s3_provider_with_signed_urls.store(data=test_data, key=key)
        display = s3_provider_with_signed_urls.display_link(uri=returned_uri)

        assert display is not None
        # The credential should include the region
        assert f"%2F{S3_TEST_REGION}%2Fs3%2F" in display or f"/{S3_TEST_REGION}/s3/" in display, (
            f"Presigned URL credential must include region '{S3_TEST_REGION}'. Got: {display}"
        )

    def test_store_overwrites_existing_data(
        self,
        s3_provider_no_signed_urls: S3StorageProvider,
    ) -> None:
        """Test that storing with the same key overwrites the previous data."""
        key = "overwrite/test.bin"
        original_data = b"original"
        new_data = b"updated content"

        uri1 = s3_provider_no_signed_urls.store(data=original_data, key=key)
        uri2 = s3_provider_no_signed_urls.store(data=new_data, key=key)
        loaded_data = s3_provider_no_signed_urls.load(uri=uri2)

        assert uri1 == uri2
        assert loaded_data == new_data

    def test_store_empty_bytes(
        self,
        s3_provider_no_signed_urls: S3StorageProvider,
    ) -> None:
        """Test storing and loading empty bytes."""
        key = "empty.bin"

        returned_uri = s3_provider_no_signed_urls.store(data=b"", key=key)
        loaded_data = s3_provider_no_signed_urls.load(uri=returned_uri)

        assert loaded_data == b""

    def test_store_large_binary_data(
        self,
        s3_provider_no_signed_urls: S3StorageProvider,
    ) -> None:
        """Test storing and loading larger binary data."""
        test_data = bytes(range(256)) * 1000  # ~256KB of data
        key = "large_file.bin"

        returned_uri = s3_provider_no_signed_urls.store(data=test_data, key=key)
        loaded_data = s3_provider_no_signed_urls.load(uri=returned_uri)

        assert loaded_data == test_data

    def test_multiple_keys_isolated(
        self,
        s3_provider_no_signed_urls: S3StorageProvider,
    ) -> None:
        """Test that different keys store different data independently."""
        data1 = b"first"
        data2 = b"second"
        key1 = "file1.bin"
        key2 = "file2.bin"

        uri1 = s3_provider_no_signed_urls.store(data=data1, key=key1)
        uri2 = s3_provider_no_signed_urls.store(data=data2, key=key2)

        assert s3_provider_no_signed_urls.load(uri=uri1) == data1
        assert s3_provider_no_signed_urls.load(uri=uri2) == data2

    def test_store_with_content_type(
        self,
        s3_mock_context: None,  # noqa: ARG002
    ) -> None:
        """Test that content_type is properly set on S3 objects."""
        import boto3  # noqa: PLC0415

        provider = S3StorageProvider(
            bucket_name=S3_TEST_BUCKET,
            region=S3_TEST_REGION,
            signed_urls_lifespan=None,
        )

        test_data = b"\x89PNG\r\n\x1a\n"  # PNG header
        key = "images/test.png"
        content_type = "image/png"

        provider.store(data=test_data, key=key, content_type=content_type)

        # Verify content type was set using boto3 directly
        s3_client = boto3.client("s3", region_name=S3_TEST_REGION)  # pyright: ignore[reportUnknownMemberType,reportUnknownVariableType]
        response = s3_client.head_object(Bucket=S3_TEST_BUCKET, Key=key)  # pyright: ignore[reportUnknownMemberType,reportUnknownVariableType]
        assert response["ContentType"] == content_type

    def test_store_with_nested_path(
        self,
        s3_provider_no_signed_urls: S3StorageProvider,
    ) -> None:
        """Test storing data in a deeply nested path structure."""
        test_data = b"nested content"
        key = "level1/level2/level3/deep_file.bin"

        returned_uri = s3_provider_no_signed_urls.store(data=test_data, key=key)
        loaded_data = s3_provider_no_signed_urls.load(uri=returned_uri)

        assert loaded_data == test_data

    def test_presigned_url_uses_correct_region_for_non_us_east_1(
        self,
        s3_mock_context: None,  # noqa: ARG002
    ) -> None:
        """Test that presigned URLs use the correct regional endpoint for non-us-east-1 regions.

        This test specifically targets the bug where boto3 might use the global endpoint
        instead of the regional endpoint, causing SignatureDoesNotMatch errors in regions
        like eu-west-3.
        """
        import boto3  # noqa: PLC0415

        test_region = "eu-west-3"
        test_bucket = "test-eu-bucket"

        # Create bucket in a different region
        s3_client = boto3.client("s3", region_name=test_region)  # pyright: ignore[reportUnknownMemberType,reportUnknownVariableType]
        s3_client.create_bucket(  # pyright: ignore[reportUnknownMemberType]
            Bucket=test_bucket,
            CreateBucketConfiguration={"LocationConstraint": test_region},
        )

        provider = S3StorageProvider(
            bucket_name=test_bucket,
            region=test_region,
            signed_urls_lifespan=3600,
        )

        test_data = b"eu-west-3 test"
        key = "eu-test/file.bin"

        returned_uri = provider.store(data=test_data, key=key)
        display = provider.display_link(uri=returned_uri)

        assert display is not None
        # Must use regional endpoint for eu-west-3, not global s3.amazonaws.com
        assert f"s3.{test_region}.amazonaws.com" in display, (
            f"Presigned URL must use regional endpoint 's3.{test_region}.amazonaws.com'. "
            f"Using global endpoint causes SignatureDoesNotMatch errors. Got: {display}"
        )

    def test_client_uses_regional_endpoint_url(
        self,
        s3_mock_context: None,  # noqa: ARG002
    ) -> None:
        """Test that the S3 client is configured with the regional endpoint URL.

        This verifies the fix for SignatureDoesNotMatch errors caused by using
        the global S3 endpoint instead of the regional one.
        """
        test_region = "ap-southeast-1"
        provider = S3StorageProvider(
            bucket_name="test-bucket",
            region=test_region,
            signed_urls_lifespan=3600,
        )

        # Trigger client initialization
        client = provider._get_client()  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

        # Verify the client is using the regional endpoint
        endpoint_url = client.meta.endpoint_url  # pyright: ignore[reportUnknownMemberType,reportUnknownVariableType]
        expected_endpoint = f"https://s3.{test_region}.amazonaws.com"
        assert endpoint_url == expected_endpoint, (
            f"Client must use regional endpoint '{expected_endpoint}' to avoid SignatureDoesNotMatch errors. Got: {endpoint_url}"
        )
