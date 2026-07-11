"""The storage-provider seam: the registrar collects per-method provider factories into a registry.

Pins the seam independent of the real built-in providers: a factory registered for a method is the
one the registry hands back; a miss raises ``UnknownStorageMethodError`` listing the registered
methods; a second registration for the same method fails loud naming both plugins; an empty registry
misses every method.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING, cast

import pytest

from pipelex.plugins.contract import PLUGIN_API_VERSION
from pipelex.plugins.exceptions import DuplicateStorageProviderError, UnknownStorageMethodError
from pipelex.plugins.registrar import PluginOrigin, PluginRegistrar
from pipelex.plugins.storage_provider_registry import StorageProviderRegistry
from pipelex.tools.storage.in_memory_storage_provider import InMemoryStorageProvider

if TYPE_CHECKING:
    from pipelex.system.configuration.configs import PipelexConfig
    from pipelex.tools.storage.storage_config import StorageProviderConfig
    from pipelex.tools.storage.storage_provider_abstract import StorageProviderAbstract


def _make_registrar() -> PluginRegistrar:
    return PluginRegistrar(config=cast("PipelexConfig", SimpleNamespace(plugins=SimpleNamespace(disabled=[]))))


def _fake_factory(_config: StorageProviderConfig) -> StorageProviderAbstract:
    """Stand-in factory: identity is all the registry tests assert (never actually invoked here)."""
    return InMemoryStorageProvider()


class TestStorageProviderRegistry:
    def test_registered_factory_is_retrievable_by_method(self) -> None:
        """A factory registered for a method is the exact callable the built registry returns for it."""
        registrar = _make_registrar()
        registrar.begin_plugin(name="alpha", origin=PluginOrigin.EXTERNAL, targets_api=PLUGIN_API_VERSION)
        registrar.add_storage_provider(method="azure", factory=_fake_factory)

        registry = StorageProviderRegistry(registrar.storage_providers)
        assert registry.get_required(method="azure") is _fake_factory
        assert registry.has(method="azure")
        assert registry.methods == ["azure"]

    def test_contribution_recorded_on_the_active_plugin(self) -> None:
        """Registering a provider records a ``storage provider <method>`` contribution on the plugin's discovery."""
        registrar = _make_registrar()
        discovery = registrar.begin_plugin(name="alpha", origin=PluginOrigin.EXTERNAL, targets_api=PLUGIN_API_VERSION)

        registrar.add_storage_provider(method="azure", factory=_fake_factory)

        assert "storage provider azure" in discovery.contributions

    def test_get_required_miss_raises_listing_registered_methods(self) -> None:
        """A miss names the requested method and lists the registered ones (the boot-time actionable error)."""
        registrar = _make_registrar()
        registrar.begin_plugin(name="alpha", origin=PluginOrigin.EXTERNAL, targets_api=PLUGIN_API_VERSION)
        registrar.add_storage_provider(method="local", factory=_fake_factory)
        registrar.add_storage_provider(method="s3", factory=_fake_factory)
        registry = StorageProviderRegistry(registrar.storage_providers)

        with pytest.raises(UnknownStorageMethodError) as exc_info:
            registry.get_required(method="azure")

        assert exc_info.value.method == "azure"
        assert set(exc_info.value.registered_methods) == {"local", "s3"}
        message = str(exc_info.value)
        assert "local" in message
        assert "s3" in message

    def test_empty_registry_misses_every_method(self) -> None:
        """A registry with no factories misses every method — soft via has, loud via get_required."""
        registry = StorageProviderRegistry({})

        assert not registry.has(method="local")
        assert registry.methods == []
        with pytest.raises(UnknownStorageMethodError):
            registry.get_required(method="local")

    def test_duplicate_method_fails_loud_naming_both_plugins(self) -> None:
        """Two plugins registering a provider for the same method is a fail-loud conflict naming both."""
        registrar = _make_registrar()
        registrar.begin_plugin(name="alpha", origin=PluginOrigin.EXTERNAL, targets_api=PLUGIN_API_VERSION)
        registrar.add_storage_provider(method="azure", factory=_fake_factory)
        registrar.begin_plugin(name="beta", origin=PluginOrigin.EXTERNAL, targets_api=PLUGIN_API_VERSION)

        with pytest.raises(DuplicateStorageProviderError) as exc_info:
            registrar.add_storage_provider(method="azure", factory=_fake_factory)

        assert exc_info.value.first_plugin == "alpha"
        assert exc_info.value.second_plugin == "beta"
        assert exc_info.value.method == "azure"
