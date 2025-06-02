from pydantic import Field

from pipelex import log
from pipelex.cogt.exceptions import CogtError
from pipelex.tools.config.models import ConfigModel
from pipelex.tools.environment import EnvVarNotFoundError, get_required_env
from pipelex.tools.secrets.secrets_errors import SecretNotFoundError
from pipelex.tools.secrets.secrets_provider_abstract import SecretsProviderAbstract
from pipelex.types import StrEnum


class MistralCredentialsError(CogtError):
    pass


class MistralKeyMethod(StrEnum):
    SECRET_PROVIDER = "secret_provider"
    ENV = "env"


class MistralConfig(ConfigModel):
    api_key_method: MistralKeyMethod = Field(strict=False)

    def api_key(self, secrets_provider: SecretsProviderAbstract) -> str:
        match self.api_key_method:
            case MistralKeyMethod.ENV:
                log.debug("Using Mistral API key from environment.")
                try:
                    key_from_env = get_required_env("MISTRAL_API_KEY")
                    return key_from_env
                except EnvVarNotFoundError as exc:
                    raise MistralCredentialsError(f"Error getting Mistral API key from environment: {exc}") from exc
            case MistralKeyMethod.SECRET_PROVIDER:
                log.verbose("Using Mistral API key from secrets provider.")
                try:
                    key_from_secrets_provider = secrets_provider.get_secret(secret_id="MISTRAL_API_KEY")
                    return key_from_secrets_provider
                except SecretNotFoundError as exc:
                    raise MistralCredentialsError("Error getting Mistral API key from secrets provider.") from exc
