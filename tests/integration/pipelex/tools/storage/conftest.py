from pathlib import Path
from typing import Literal, cast

import pytest
from pytest_mock import MockerFixture

from pipelex.cogt.content_generation.generated_content_factory import GeneratedContentFactory
from pipelex.config import get_config
from pipelex.tools.storage.in_memory_storage_provider import InMemoryStorageProvider
from pipelex.tools.storage.local_storage_provider import LocalStorageProvider
from pipelex.tools.storage.storage_provider_abstract import StorageProviderAbstract

StorageMethodLiteral = Literal["local", "in_memory"]


@pytest.fixture(params=["local", "in_memory"])
def storage_method(request: pytest.FixtureRequest) -> StorageMethodLiteral:
    """Parametrized fixture that yields each storage method."""
    return cast("StorageMethodLiteral", request.param)


@pytest.fixture
def storage_provider(storage_method: StorageMethodLiteral, tmp_path: Path) -> StorageProviderAbstract:
    """Create a storage provider based on the storage method."""
    match storage_method:
        case "local":
            return LocalStorageProvider(root_path=tmp_path)
        case "in_memory":
            return InMemoryStorageProvider()


@pytest.fixture
def uri_format(storage_method: StorageMethodLiteral) -> str:
    """Get the URI format for the given storage method from the config."""
    storage_config = get_config().pipelex.storage_config
    match storage_method:
        case "local":
            assert storage_config.local is not None
            return storage_config.local.uri_format
        case "in_memory":
            assert storage_config.in_memory is not None
            return storage_config.in_memory.uri_format


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
        original_config.pipelex.storage_config,
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
        original_config.pipelex.storage_config,
        "is_fetch_remote_content_enabled",
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
