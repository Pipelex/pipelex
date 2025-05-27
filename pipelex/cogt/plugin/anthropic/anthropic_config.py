from enum import StrEnum

from pydantic import Field

from pipelex import log
from pipelex.cogt.exceptions import CogtError
from pipelex.tools.config.models import ConfigModel
from pipelex.tools.environment import EnvVarNotFoundError, get_required_env
from pipelex.tools.secrets.secrets_errors import SecretNotFoundError
from pipelex.tools.secrets.secrets_provider_abstract import SecretsProviderAbstract


class AnthropicCredentialsError(CogtError):
    pass


class AnthropicKeyMethod(StrEnum):
    SECRET_PROVIDER = "secret_provider"
    ENV = "env"


ANTHROPIC_API_KEY_VAR_NAME = "ANTHROPIC_API_KEY"


class AnthropicConfig(ConfigModel):
    api_key_method: AnthropicKeyMethod = Field(strict=False)

    def configure(self, secrets_provider: SecretsProviderAbstract) -> str:
        return self.get_api_key(secrets_provider=secrets_provider)

    def get_api_key(self, secrets_provider: SecretsProviderAbstract) -> str:
        match self.api_key_method:
            case AnthropicKeyMethod.ENV:
                log.verbose("Getting Anthropic API key from environment.")
                try:
                    key_from_env = get_required_env(ANTHROPIC_API_KEY_VAR_NAME)
                    return key_from_env
                except EnvVarNotFoundError as exc:
                    raise AnthropicCredentialsError(f"Error getting Anthropic API key from environment: {exc}") from exc
            case AnthropicKeyMethod.SECRET_PROVIDER:
                log.verbose("Getting Anthropic API key from secrets provider.")
                try:
                    key_from_service_provider = secrets_provider.get_secret(secret_id=ANTHROPIC_API_KEY_VAR_NAME)
                except SecretNotFoundError as exc:
                    raise AnthropicCredentialsError("Error getting Anthropic API key from secrets provider.") from exc
                return key_from_service_provider
