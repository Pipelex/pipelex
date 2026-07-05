from collections.abc import Callable

from pipelex.plugins.exceptions import UnknownStorageMethodError
from pipelex.tools.storage.storage_config import StorageProviderConfig
from pipelex.tools.storage.storage_provider_abstract import StorageProviderAbstract

# A plugin's factory for one storage backend: whole storage config in, provider out. The whole
# config (not a pre-resolved sub-config) is passed so a factory can read whatever it needs —
# including a hub secrets read (GCP) — at the boot apply-point, never at registration.
StorageProviderFactoryFn = Callable[[StorageProviderConfig], StorageProviderAbstract]


class StorageProviderRegistry:
    """Read view over the storage-provider factories contributed by discovered plugins.

    Keyed by the open storage ``method`` token (a ``str``; the built-ins keep the
    ``StorageMethod`` values, an external plugin registers e.g. ``"azure"``). Built once at
    boot from the registrar's accumulated ``storage_providers`` and stored on the hub; core
    reads ``storage_config.method`` and calls the looked-up factory to produce the one provider.
    """

    def __init__(self, storage_providers: dict[str, StorageProviderFactoryFn]):
        self._storage_providers: dict[str, StorageProviderFactoryFn] = dict(storage_providers)

    def get_optional(self, *, method: str) -> StorageProviderFactoryFn | None:
        return self._storage_providers.get(method)

    def get_required(self, *, method: str) -> StorageProviderFactoryFn:
        factory = self._storage_providers.get(method)
        if factory is None:
            raise UnknownStorageMethodError(method=method, registered_methods=self.methods)
        return factory

    def has(self, *, method: str) -> bool:
        return method in self._storage_providers

    @property
    def methods(self) -> list[str]:
        return list(self._storage_providers)
