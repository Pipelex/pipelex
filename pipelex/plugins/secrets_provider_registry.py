from collections.abc import Callable

from pipelex.plugins.exceptions import UnknownSecretsMethodError
from pipelex.tools.secrets.secrets_config import SecretsProviderConfig
from pipelex.tools.secrets.secrets_provider_abstract import SecretsProviderAbstract

# A plugin's factory for one secrets backend: whole secrets config in, provider out. The whole
# config (not a pre-resolved sub-config) is passed so a factory can read whatever it needs — an
# SDK-backed provider (Vault, AWS Secrets Manager) reads its own settings — at the boot apply-point,
# never at registration. The built-in ``env`` factory ignores the config entirely.
SecretsProviderFactoryFn = Callable[[SecretsProviderConfig], SecretsProviderAbstract]


class SecretsProviderRegistry:
    """Read view over the secrets-provider factories contributed by discovered plugins.

    Keyed by the open secrets ``method`` token (a ``str``; the built-in ``SecretsPlugin`` registers
    ``"env"``, an external plugin registers e.g. ``"vault"``). Built once at boot from the registrar's
    accumulated ``secrets_providers`` and stored on the hub; core reads ``secrets_config.method`` and
    calls the looked-up factory to produce the one provider. Mirrors ``StorageProviderRegistry``.
    """

    def __init__(self, secrets_providers: dict[str, SecretsProviderFactoryFn]):
        self._secrets_providers: dict[str, SecretsProviderFactoryFn] = dict(secrets_providers)

    def get_required(self, *, method: str) -> SecretsProviderFactoryFn:
        factory = self._secrets_providers.get(method)
        if factory is None:
            raise UnknownSecretsMethodError(method=method, registered_methods=self.methods)
        return factory

    def has(self, *, method: str) -> bool:
        return method in self._secrets_providers

    @property
    def methods(self) -> list[str]:
        return list(self._secrets_providers)
