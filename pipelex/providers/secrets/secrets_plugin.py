from pipelex.plugins.contract import PLUGIN_API_VERSION
from pipelex.plugins.registrar import PluginRegistrar
from pipelex.tools.secrets.env_secrets_provider import EnvSecretsProvider
from pipelex.tools.secrets.secrets_config import SecretsProviderConfig
from pipelex.tools.secrets.secrets_provider_abstract import SecretsProviderAbstract


def _make_env_secrets_provider(config: SecretsProviderConfig) -> SecretsProviderAbstract:  # noqa: ARG001 - env provider reads no config; uniform SecretsProviderFactoryFn signature
    return EnvSecretsProvider()


class SecretsPlugin:
    """Always-on built-in provider of the ``env`` secrets backend (reads secrets from env vars).

    Core-unconditional: secrets is required infra, so this plugin cannot be disabled into a boot
    with no secrets provider (see ``RUNTIME_CORE_UNCONDITIONAL_PLUGIN_NAMES``). It registers the one built-in
    ``env`` method; ``secrets_config.method`` selects which factory boot invokes. Importing this module
    is import-light — no SDK loads at register (the env provider needs none, and an external
    ``pipelex-secrets-<backend>`` plugin defers its SDK import to its own factory).
    """

    name = "secrets"
    targets_api = PLUGIN_API_VERSION

    def register(self, registrar: PluginRegistrar) -> None:
        registrar.add_secrets_provider(method="env", factory=_make_env_secrets_provider)
