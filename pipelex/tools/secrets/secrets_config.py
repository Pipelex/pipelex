from pydantic import Field

from pipelex.system.configuration.config_model import ConfigModel


class SecretsProviderConfig(ConfigModel):
    """Provider-selection config for the secrets-provider seam.

    Mirrors ``StorageProviderConfig``'s open-token selection (S1): the built-in ``SecretsPlugin``
    registers the ``env`` method; an external ``pipelex-secrets-<backend>`` plugin registers its own
    (e.g. ``"vault"``). An unknown token is validated at registry lookup (``UnknownSecretsMethodError``
    at boot), not at parse — so a config naming an external method still loads, and only the registry
    decides what is installable. The built-in ``env`` method needs no per-method sub-config; a future
    external-provider config passthrough is a scoped follow-up (S4).
    """

    method: str = Field(strict=False)
