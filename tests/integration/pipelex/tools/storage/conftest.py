from pathlib import Path
from typing import Any, Literal, cast

import pytest
from pytest_mock import MockerFixture, MockType

from pipelex.cogt.content_generation.generated_content_factory import GeneratedContentFactory
from pipelex.config import get_config
from pipelex.tools.storage.gcp_storage_provider import GcpStorageProvider
from pipelex.tools.storage.in_memory_storage_provider import InMemoryStorageProvider
from pipelex.tools.storage.local_storage_provider import LocalStorageProvider
from pipelex.tools.storage.s3_storage_provider import S3StorageProvider
from pipelex.tools.storage.storage_provider_abstract import StorageProviderAbstract

StorageMethodLiteral = Literal["local", "in_memory", "s3", "gcp"]

# Constants for S3 mocking
S3_TEST_BUCKET = "test-pipelex-bucket"
S3_TEST_REGION = "us-east-1"

# Constants for GCP mocking
GCP_TEST_BUCKET = "test-gcp-pipelex-bucket"
GCP_TEST_PROJECT = "test-project"


@pytest.fixture(params=["local", "in_memory", "s3", "gcp"])
def storage_method(request: pytest.FixtureRequest) -> StorageMethodLiteral:
    """Parametrized fixture that yields each storage method."""
    return cast("StorageMethodLiteral", request.param)


@pytest.fixture
def s3_mock(mocker: MockerFixture) -> dict[str, Any]:
    """Mock aioboto3 for S3 tests.

    Creates a mock that simulates S3 behavior using an in-memory dict.
    """
    # Storage for mock data
    mock_data_storage: dict[str, bytes] = {}

    def create_mock_stream(key: str) -> MockType:
        """Create a mock async stream for response body."""
        stream: MockType = mocker.AsyncMock()
        stream.read = mocker.AsyncMock(side_effect=lambda: mock_data_storage.get(key, b""))
        stream.__aenter__ = mocker.AsyncMock(return_value=stream)
        stream.__aexit__ = mocker.AsyncMock(return_value=None)
        return stream

    # Create mock exceptions
    mock_exceptions = mocker.MagicMock()
    mock_exceptions.NoSuchKey = type("NoSuchKey", (Exception,), {})
    mock_exceptions.NoSuchBucket = type("NoSuchBucket", (Exception,), {})
    mock_exceptions.ClientError = type("ClientError", (Exception,), {})

    def mock_get_object(Bucket: str, Key: str) -> dict[str, Any]:  # noqa: ARG001, N803
        if Key not in mock_data_storage:
            msg = f"Key {Key} not found"
            raise mock_exceptions.NoSuchKey(msg)
        return {"Body": create_mock_stream(Key)}

    def mock_put_object(Bucket: str, Key: str, Body: bytes, **kwargs: Any) -> dict[str, Any]:  # noqa: ARG001, N803
        mock_data_storage[Key] = Body
        return {}

    def mock_generate_presigned_url(
        method: str,  # noqa: ARG001
        Params: dict[str, str],  # noqa: N803
        ExpiresIn: int,  # noqa: ARG001, N803
    ) -> str:
        key = Params.get("Key", "")
        return f"https://{S3_TEST_BUCKET}.s3.{S3_TEST_REGION}.amazonaws.com/{key}?X-Amz-Signature=mock"

    # Create mock client with sync functions wrapped in AsyncMock
    mock_client = mocker.AsyncMock()
    mock_client.get_object = mocker.AsyncMock(side_effect=mock_get_object)
    mock_client.put_object = mocker.AsyncMock(side_effect=mock_put_object)
    mock_client.generate_presigned_url = mocker.AsyncMock(side_effect=mock_generate_presigned_url)
    mock_client.exceptions = mock_exceptions

    # Create async context manager for client
    mock_client_context = mocker.AsyncMock()
    mock_client_context.__aenter__ = mocker.AsyncMock(return_value=mock_client)
    mock_client_context.__aexit__ = mocker.AsyncMock(return_value=None)

    # Create mock session
    mock_session = mocker.MagicMock()
    mock_session.client = mocker.MagicMock(return_value=mock_client_context)

    # Patch aioboto3.Session
    mocker.patch("aioboto3.Session", return_value=mock_session)

    return {
        "session": mock_session,
        "client": mock_client,
        "storage": mock_data_storage,
    }


@pytest.fixture
def gcp_mock(tmp_path: Path, mocker: MockerFixture) -> dict[str, Any]:
    """Mock GCP storage for tests.

    Creates a mock that simulates GCS behavior using an in-memory dict.
    """
    # Import the module first so it can be patched
    from google.cloud import storage  # type: ignore[import-untyped]  # noqa: PLC0415

    # Create mock credentials file
    credentials_path = tmp_path / "gcp_credentials.json"
    credentials_path.write_text('{"type": "service_account"}')

    # Storage for mock data
    mock_data_storage: dict[str, bytes] = {}

    # Create mock blob that behaves like a real blob
    def create_mock_blob(key: str) -> MockType:
        blob: MockType = mocker.MagicMock()
        blob.exists.side_effect = lambda: key in mock_data_storage
        blob.download_as_bytes.side_effect = lambda: mock_data_storage[key]
        blob.upload_from_string.side_effect = lambda data, content_type=None: mock_data_storage.__setitem__(key, data)  # noqa: ARG005  # pyright: ignore[reportUnknownLambdaType,reportUnknownArgumentType]
        blob.generate_signed_url.return_value = f"https://storage.googleapis.com/{GCP_TEST_BUCKET}/{key}?signed=true"
        return blob

    # Create mock bucket
    mock_bucket = mocker.MagicMock()
    mock_bucket.blob.side_effect = create_mock_blob

    # Create mock client
    mock_client = mocker.MagicMock()
    mock_client.bucket.return_value = mock_bucket

    # Patch the Client.from_service_account_json method directly
    mocker.patch.object(
        storage.Client,
        "from_service_account_json",
        return_value=mock_client,
    )

    return {
        "credentials_path": str(credentials_path),
        "storage": mock_data_storage,
    }


@pytest.fixture
def storage_provider(
    storage_method: StorageMethodLiteral,
    tmp_path: Path,
    request: pytest.FixtureRequest,
) -> StorageProviderAbstract:
    """Create a storage provider based on the storage method."""
    match storage_method:
        case "local":
            return LocalStorageProvider(root_path=tmp_path)
        case "in_memory":
            return InMemoryStorageProvider()
        case "s3":
            # Request the s3_mock fixture to set up aioboto3 mocks
            request.getfixturevalue("s3_mock")
            return S3StorageProvider(
                bucket_name=S3_TEST_BUCKET,
                region=S3_TEST_REGION,
                signed_urls_lifespan=None,
            )
        case "gcp":
            # Request the gcp_mock fixture to set up mocks
            gcp_mock_data = request.getfixturevalue("gcp_mock")
            return GcpStorageProvider(
                bucket_name=GCP_TEST_BUCKET,
                project_id=GCP_TEST_PROJECT,
                credentials_file_path=gcp_mock_data["credentials_path"],
                signed_urls_lifespan=None,
            )


@pytest.fixture
def uri_format(storage_method: StorageMethodLiteral) -> str:
    """Get the URI format for the given storage method from the config."""
    storage_config = get_config().runtime.storage
    match storage_method:
        case "local":
            assert storage_config.local is not None
            return storage_config.local.uri_format
        case "in_memory":
            assert storage_config.in_memory is not None
            return storage_config.in_memory.uri_format
        case "s3":
            assert storage_config.s3 is not None
            return storage_config.s3.uri_format
        case "gcp":
            assert storage_config.gcp is not None
            return storage_config.gcp.uri_format


@pytest.fixture
def generated_content_factory(storage_provider: StorageProviderAbstract) -> GeneratedContentFactory:
    """Create a GeneratedContentFactory with the parametrized storage provider.

    This fixture is useful for testing generated image flows with different storage methods.
    Future S3/GCP implementations should also work with this pattern.
    """
    return GeneratedContentFactory(storage_provider=storage_provider)


@pytest.fixture
def mock_fetch_remote_content_enabled(mocker: MockerFixture) -> None:
    """Mock the config to enable fetching remote content.

    When `is_fetch_remote_content_enabled` is True, remote HTTP URLs are fetched
    and stored locally instead of being passed through.
    """
    original_config = get_config()
    mocker.patch.object(
        original_config.runtime.storage,
        "is_fetch_remote_content_enabled",
        True,
    )


@pytest.fixture
def mock_fetch_remote_content_disabled(mocker: MockerFixture) -> None:
    """Mock the config to disable fetching remote content.

    When `is_fetch_remote_content_enabled` is False, remote HTTP URLs are passed
    through without being fetched and stored.
    """
    original_config = get_config()
    mocker.patch.object(
        original_config.runtime.storage,
        "is_fetch_remote_content_enabled",
        False,
    )


@pytest.fixture
def mock_upload_local_content_enabled(mocker: MockerFixture) -> None:
    """Mock the config to enable uploading local content.

    When `is_upload_local_content_enabled` is True, local file paths are read,
    uploaded to storage, and replaced with pipelex-storage:// URIs.
    """
    original_config = get_config()
    mocker.patch.object(
        original_config.runtime.storage,
        "is_upload_local_content_enabled",
        True,
    )


@pytest.fixture
def mock_upload_local_content_disabled(mocker: MockerFixture) -> None:
    """Mock the config to disable uploading local content.

    When `is_upload_local_content_enabled` is False, local file paths are passed
    through without being uploaded to storage.
    """
    original_config = get_config()
    mocker.patch.object(
        original_config.runtime.storage,
        "is_upload_local_content_enabled",
        False,
    )


@pytest.fixture
def storage_provider_patched(
    storage_provider: StorageProviderAbstract,
    mocker: MockerFixture,
) -> StorageProviderAbstract:
    """Patch get_storage_provider to return the parametrized storage provider.

    This is useful for tests that need to verify the full flow where internal
    code calls get_storage_provider() to obtain the storage provider.
    """
    mocker.patch("pipelex.pipeline.input_normalizer.get_storage_provider", return_value=storage_provider)
    mocker.patch("pipelex.cogt.image.prompt_image_utils.get_storage_provider", return_value=storage_provider)
    return storage_provider
