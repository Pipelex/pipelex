from pathlib import Path

import pytest

from pipelex.tools.storage.exceptions import StorageConfigError
from pipelex.tools.storage.in_memory_storage_provider import InMemoryStorageProvider
from pipelex.tools.storage.local_storage_provider import LocalStorageProvider
from pipelex.tools.storage.storage_config import (
    StorageInMemoryConfig,
    StorageLocalConfig,
    StorageMethod,
    StorageProviderConfig,
)
from pipelex.tools.storage.storage_provider_factory import make_storage_provider_from_config


class TestStorageProviderFactory:
    def test_local_method_returns_local_provider(self, tmp_path: Path):
        """A valid local config yields a LocalStorageProvider."""
        provider_config = StorageProviderConfig(
            method=StorageMethod.LOCAL,
            local=StorageLocalConfig(uri_format="assets/{hash}", local_storage_path=str(tmp_path / "store")),
        )
        provider = make_storage_provider_from_config(provider_config)
        assert isinstance(provider, LocalStorageProvider)

    def test_in_memory_method_returns_in_memory_provider(self):
        """A valid in-memory config yields an InMemoryStorageProvider."""
        provider_config = StorageProviderConfig(
            method=StorageMethod.IN_MEMORY,
            in_memory=StorageInMemoryConfig(uri_format="assets/{hash}"),
        )
        provider = make_storage_provider_from_config(provider_config)
        assert isinstance(provider, InMemoryStorageProvider)

    def test_local_config_is_validated_before_provider_construction(self, tmp_path: Path):
        """A local uri_format without a {hash} placeholder is rejected when the provider is built."""
        provider_config = StorageProviderConfig(
            method=StorageMethod.LOCAL,
            local=StorageLocalConfig(uri_format="assets/constant", local_storage_path=str(tmp_path / "store")),
        )
        with pytest.raises(StorageConfigError, match="uri_format must contain a"):
            make_storage_provider_from_config(provider_config)

    def test_in_memory_config_is_validated_before_provider_construction(self):
        """An in-memory uri_format without a {hash} placeholder is rejected when the provider is built."""
        provider_config = StorageProviderConfig(
            method=StorageMethod.IN_MEMORY,
            in_memory=StorageInMemoryConfig(uri_format="assets/constant"),
        )
        with pytest.raises(StorageConfigError, match="uri_format must contain a"):
            make_storage_provider_from_config(provider_config)
