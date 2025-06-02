from pydantic import Field

from pipelex import log
from pipelex.cogt.exceptions import CogtError
from pipelex.tools.config.models import ConfigModel
from pipelex.tools.environment import EnvVarNotFoundError, get_required_env
from pipelex.tools.secrets.secrets_errors import SecretNotFoundError
from pipelex.tools.secrets.secrets_provider_abstract import SecretsProviderAbstract
from pipelex.types import StrEnum


class OpenAICredentialsError(CogtError):
    pass


class OpenAIKeyMethod(StrEnum):
    SECRET_PROVIDER = "secret_provider"
    ENV = "env"


OPENAI_API_KEY_VAR_NAME = "OPENAI_API_KEY"


class OpenAIConfig(ConfigModel):
    image_output_compression: int = Field(ge=1, le=100)
    api_key_method: OpenAIKeyMethod = Field(strict=False)

    def get_api_key(self, secrets_provider: SecretsProviderAbstract) -> str:
        match self.api_key_method:
            case OpenAIKeyMethod.ENV:
                log.debug("Using OpenAI API key from environment.")
                try:
                    key_from_env = get_required_env(OPENAI_API_KEY_VAR_NAME)
                    return key_from_env
                except EnvVarNotFoundError as exc:
                    raise OpenAICredentialsError(f"Error getting OpenAI API key from environment: {exc}") from exc
            case OpenAIKeyMethod.SECRET_PROVIDER:
                log.verbose("Using OpenAI API key from secrets provider.")
                try:
                    key_from_service_provider = secrets_provider.get_secret(secret_id=OPENAI_API_KEY_VAR_NAME)
                except SecretNotFoundError as exc:
                    raise OpenAICredentialsError("Error getting OpenAI API key from secrets provider.") from exc
                return key_from_service_provider
