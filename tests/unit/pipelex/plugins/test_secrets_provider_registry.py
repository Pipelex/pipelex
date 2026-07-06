"""The secrets-provider seam: the registrar collects per-method provider factories into a registry.

Pins the seam independent of the real built-in ``env`` provider: a factory registered for a method is
the one the registry hands back; a miss raises ``UnknownSecretsMethodError`` listing the registered
methods; a second registration for the same method fails loud naming both plugins; an empty registry
misses every method. Mirrors ``test_storage_provider_registry``.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING, cast

import pytest

from pipelex.plugins.contract import PLUGIN_API_VERSION
from pipelex.plugins.exceptions import DuplicateSecretsProviderError, UnknownSecretsMethodError
from pipelex.plugins.registrar import PluginOrigin, PluginRegistrar
from pipelex.plugins.secrets_provider_registry import SecretsProviderRegistry
from pipelex.tools.secrets.env_secrets_provider import EnvSecretsProvider

if TYPE_CHECKING:
    from pipelex.system.configuration.configs import PipelexConfig
    from pipelex.tools.secrets.secrets_config import SecretsProviderConfig
    from pipelex.tools.secrets.secrets_provider_abstract import SecretsProviderAbstract


def _make_registrar() -> PluginRegistrar:
    return PluginRegistrar(config=cast("PipelexConfig", SimpleNamespace(plugins=SimpleNamespace(disabled=[]))))


def _fake_factory(_config: SecretsProviderConfig) -> SecretsProviderAbstract:
    """Stand-in factory: identity is all the registry tests assert (never actually invoked here)."""
    return EnvSecretsProvider()


class TestSecretsProviderRegistry:
    def test_registered_factory_is_retrievable_by_method(self) -> None:
        """A factory registered for a method is the exact callable the built registry returns for it."""
        registrar = _make_registrar()
        registrar.begin_plugin(name="alpha", origin=PluginOrigin.EXTERNAL, targets_api=PLUGIN_API_VERSION)
        registrar.add_secrets_provider(method="vault", factory=_fake_factory)

        registry = SecretsProviderRegistry(registrar.secrets_providers)
        assert registry.get_optional(method="vault") is _fake_factory
        assert registry.get_required(method="vault") is _fake_factory
        assert registry.has(method="vault")
        assert registry.methods == ["vault"]

    def test_contribution_recorded_on_the_active_plugin(self) -> None:
        """Registering a provider records a ``secrets provider <method>`` contribution on the plugin's discovery."""
        registrar = _make_registrar()
        discovery = registrar.begin_plugin(name="alpha", origin=PluginOrigin.EXTERNAL, targets_api=PLUGIN_API_VERSION)

        registrar.add_secrets_provider(method="vault", factory=_fake_factory)

        assert "secrets provider vault" in discovery.contributions

    def test_get_required_miss_raises_listing_registered_methods(self) -> None:
        """A miss names the requested method and lists the registered ones (the boot-time actionable error)."""
        registrar = _make_registrar()
        registrar.begin_plugin(name="alpha", origin=PluginOrigin.EXTERNAL, targets_api=PLUGIN_API_VERSION)
        registrar.add_secrets_provider(method="env", factory=_fake_factory)
        registrar.add_secrets_provider(method="vault", factory=_fake_factory)
        registry = SecretsProviderRegistry(registrar.secrets_providers)

        with pytest.raises(UnknownSecretsMethodError) as exc_info:
            registry.get_required(method="aws")

        assert exc_info.value.method == "aws"
        assert set(exc_info.value.registered_methods) == {"env", "vault"}
        message = str(exc_info.value)
        assert "env" in message
        assert "vault" in message

    def test_empty_registry_misses_every_method(self) -> None:
        """A registry with no factories misses every method — soft via get_optional/has, loud via get_required."""
        registry = SecretsProviderRegistry({})

        assert registry.get_optional(method="env") is None
        assert not registry.has(method="env")
        assert registry.methods == []
        with pytest.raises(UnknownSecretsMethodError):
            registry.get_required(method="env")

    def test_duplicate_method_fails_loud_naming_both_plugins(self) -> None:
        """Two plugins registering a provider for the same method is a fail-loud conflict naming both."""
        registrar = _make_registrar()
        registrar.begin_plugin(name="alpha", origin=PluginOrigin.EXTERNAL, targets_api=PLUGIN_API_VERSION)
        registrar.add_secrets_provider(method="vault", factory=_fake_factory)
        registrar.begin_plugin(name="beta", origin=PluginOrigin.EXTERNAL, targets_api=PLUGIN_API_VERSION)

        with pytest.raises(DuplicateSecretsProviderError) as exc_info:
            registrar.add_secrets_provider(method="vault", factory=_fake_factory)

        assert exc_info.value.first_plugin == "alpha"
        assert exc_info.value.second_plugin == "beta"
        assert exc_info.value.method == "vault"
