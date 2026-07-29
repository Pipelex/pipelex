"""The built-in SecretsPlugin: registers the one ``env`` factory, which constructs an EnvSecretsProvider.

Secrets is a single-impl seam today — the ``env`` provider reads secrets from env vars and needs no
config, so its factory ignores the config it is handed. Registration is import-light (no SDK); an
out-of-tree ``pipelex-secrets-<backend>`` plugin would defer its SDK import into its own factory.
Mirrors ``test_storage_plugin`` (kept lean: one built-in method, no optional-dep matrix).
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING, cast

from pipelex.plugins.contract import PLUGIN_API_VERSION
from pipelex.plugins.registrar import PluginOrigin, PluginRegistrar
from pipelex.plugins.secrets_provider_registry import SecretsProviderRegistry
from pipelex.providers.secrets.secrets_plugin import SecretsPlugin
from pipelex.tools.secrets.env_secrets_provider import EnvSecretsProvider
from pipelex.tools.secrets.secrets_config import SecretsProviderConfig

if TYPE_CHECKING:
    from pipelex.system.configuration.configs import PipelexConfig


def _build_secrets_registry() -> SecretsProviderRegistry:
    registrar = PluginRegistrar(config=cast("PipelexConfig", SimpleNamespace(plugins=SimpleNamespace(disabled=[]))))
    SecretsPlugin().register(registrar)
    return SecretsProviderRegistry(registrar.secrets_providers)


class TestSecretsPlugin:
    def test_registers_the_env_factory(self) -> None:
        """SecretsPlugin is a named, API-versioned builtin registering exactly the built-in ``env`` method."""
        plugin = SecretsPlugin()
        assert plugin.name == "secrets"
        assert plugin.targets_api == PLUGIN_API_VERSION

        registrar = PluginRegistrar(config=cast("PipelexConfig", SimpleNamespace(plugins=SimpleNamespace(disabled=[]))))
        discovery = registrar.begin_plugin(name="secrets", origin=PluginOrigin.BUILTIN, targets_api=PLUGIN_API_VERSION)
        plugin.register(registrar)

        assert set(registrar.secrets_providers) == {"env"}
        assert "secrets provider env" in discovery.contributions

    def test_env_factory_constructs_an_env_secrets_provider(self) -> None:
        """Selecting ``env`` through the registry constructs an EnvSecretsProvider (the factory ignores its config)."""
        registry = _build_secrets_registry()
        provider = registry.get_required(method="env")(SecretsProviderConfig(method="env"))
        assert isinstance(provider, EnvSecretsProvider)
