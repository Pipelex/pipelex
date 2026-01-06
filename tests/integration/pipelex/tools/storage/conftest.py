from pathlib import Path
from typing import Literal, cast

import pytest

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
