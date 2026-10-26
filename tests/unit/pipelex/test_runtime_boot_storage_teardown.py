from typing_extensions import override

from pipelex.pipelex import Pipelex
from pipelex.system.runtime import IntegrationMode, runtime_manager
from pipelex.tools.storage.exceptions import StorageFileNotFoundError
from pipelex.tools.storage.storage_provider_abstract import StorageProviderAbstract, StoredData


def _test_integration_mode() -> IntegrationMode:
    """The boot mode the session conftest uses, so a re-boot here matches the one it replaces."""
    return IntegrationMode.CI if runtime_manager.is_ci_testing else IntegrationMode.PYTEST


class _TeardownCountingStorage(StorageProviderAbstract):
    """A storage holding nothing, counting its teardowns."""

    def __init__(self) -> None:
        self.teardown_count = 0

    @override
    async def _load_with_metadata(self, key: str) -> StoredData:
        msg = f"File not found: '{key}'"
        raise StorageFileNotFoundError(msg)

    @override
    async def _store(self, data: bytes, *, key: str, content_type: str | None, checksum_sha256_hex: str | None) -> None:
        pass

    @override
    async def public_url(self, uri: str) -> str | None:
        return None

    @override
    def teardown(self) -> None:
        self.teardown_count += 1


class TestRuntimeTeardownReleasesTheStorageProvider:
    def test_the_runtime_teardown_tears_down_the_storage_provider_it_booted_with(self) -> None:
        """A provider keeping a client open between operations, as the S3 one does, closes it when the runtime goes."""
        storage_provider = _TeardownCountingStorage()

        Pipelex.teardown_if_needed()
        try:
            Pipelex.make(integration_mode=_test_integration_mode(), needs_inference=False, storage_provider=storage_provider)
            assert storage_provider.teardown_count == 0

            Pipelex.teardown_if_needed()

            assert storage_provider.teardown_count == 1
        finally:
            Pipelex.teardown_if_needed()
            Pipelex.make(integration_mode=_test_integration_mode())
