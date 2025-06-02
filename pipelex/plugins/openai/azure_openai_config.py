from typing import Tuple

from pydantic import Field

from pipelex import log
from pipelex.cogt.exceptions import CogtError
from pipelex.tools.config.models import ConfigModel
from pipelex.tools.environment import EnvVarNotFoundError, get_required_env
from pipelex.tools.secrets.secrets_errors import SecretNotFoundError
from pipelex.tools.secrets.secrets_provider_abstract import SecretsProviderAbstract
from pipelex.types import StrEnum


class AzureOpenAICredentialsError(CogtError):
    pass


class AzureOpenAIKeyMethod(StrEnum):
    SECRET_PROVIDER = "secret_provider"
    ENV = "env"


AZURE_OPENAI_API_KEY_VAR_NAME = "AZURE_OPENAI_API_KEY"
AZURE_OPENAI_API_ENDPOINT_VAR_NAME = "AZURE_OPENAI_API_ENDPOINT"
AZURE_OPENAI_API_VERSION_VAR_NAME = "AZURE_OPENAI_API_VERSION"


class AzureOpenAIConfig(ConfigModel):
    api_key_method: AzureOpenAIKeyMethod = Field(strict=False)

    def configure(self, secrets_provider: SecretsProviderAbstract) -> Tuple[str, str, str]:
        """Configure and return endpoint, version, and API key."""
        api_endpoint = self._get_api_endpoint(secrets_provider=secrets_provider)
        api_version = self._get_api_version(secrets_provider=secrets_provider)
        api_key = self._get_api_key(secrets_provider=secrets_provider)
        return api_endpoint, api_version, api_key

    def _get_api_endpoint(self, secrets_provider: SecretsProviderAbstract) -> str:
        """Get API endpoint from environment or secrets provider."""
        match self.api_key_method:
            case AzureOpenAIKeyMethod.ENV:
                log.debug("Getting Azure OpenAI API endpoint from environment.")
                try:
                    return get_required_env(AZURE_OPENAI_API_ENDPOINT_VAR_NAME)
                except EnvVarNotFoundError as exc:
                    raise AzureOpenAICredentialsError(f"Error getting Azure OpenAI API endpoint from environment: {exc}") from exc
            case AzureOpenAIKeyMethod.SECRET_PROVIDER:
                log.verbose("Getting Azure OpenAI API endpoint from secrets provider.")
                try:
                    return secrets_provider.get_secret(secret_id=AZURE_OPENAI_API_ENDPOINT_VAR_NAME)
                except SecretNotFoundError as exc:
                    raise AzureOpenAICredentialsError("Error getting Azure OpenAI API endpoint from secrets provider.") from exc

    def _get_api_version(self, secrets_provider: SecretsProviderAbstract) -> str:
        """Get API version from environment or secrets provider."""
        match self.api_key_method:
            case AzureOpenAIKeyMethod.ENV:
                log.debug("Getting Azure OpenAI API version from environment.")
                try:
                    return get_required_env(AZURE_OPENAI_API_VERSION_VAR_NAME)
                except EnvVarNotFoundError as exc:
                    raise AzureOpenAICredentialsError(f"Error getting Azure OpenAI API version from environment: {exc}") from exc
            case AzureOpenAIKeyMethod.SECRET_PROVIDER:
                log.verbose("Getting Azure OpenAI API version from secrets provider.")
                try:
                    return secrets_provider.get_secret(secret_id=AZURE_OPENAI_API_VERSION_VAR_NAME)
                except SecretNotFoundError as exc:
                    raise AzureOpenAICredentialsError("Error getting Azure OpenAI API version from secrets provider.") from exc

    def _get_api_key(self, secrets_provider: SecretsProviderAbstract) -> str:
        """Get API key from environment or secrets provider."""
        match self.api_key_method:
            case AzureOpenAIKeyMethod.ENV:
                log.debug("Using Azure OpenAI API key from environment.")
                try:
                    key_from_env = get_required_env(AZURE_OPENAI_API_KEY_VAR_NAME)
                    return key_from_env
                except EnvVarNotFoundError as exc:
                    raise AzureOpenAICredentialsError(f"Error getting Azure OpenAI API key from environment: {exc}") from exc
            case AzureOpenAIKeyMethod.SECRET_PROVIDER:
                log.verbose("Using Azure OpenAI API key from secrets provider.")
                # TODO: make it automatically select the right key for the right azure resource
                try:
                    key_from_secrets_provider = secrets_provider.get_secret(secret_id=AZURE_OPENAI_API_KEY_VAR_NAME)
                except SecretNotFoundError as exc:
                    raise AzureOpenAICredentialsError("Error getting Azure OpenAI API key from secrets provider.") from exc
                return key_from_secrets_provider
