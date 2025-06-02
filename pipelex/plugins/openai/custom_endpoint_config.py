from typing import Optional, Tuple

from pydantic import Field

from pipelex import log
from pipelex.cogt.exceptions import CogtError
from pipelex.tools.config.models import ConfigModel
from pipelex.tools.environment import EnvVarNotFoundError, get_required_env
from pipelex.tools.secrets.secrets_errors import SecretNotFoundError
from pipelex.tools.secrets.secrets_provider_abstract import SecretsProviderAbstract
from pipelex.types import StrEnum


class CustomEndpointCredentialsError(CogtError):
    pass


class OpenAIKeyMethod(StrEnum):
    SECRET_PROVIDER = "secret_provider"
    ENV = "env"


CUSTOM_ENDPOINT_API_KEY_VAR_NAME = "CUSTOM_ENDPOINT_API_KEY"
CUSTOM_ENDPOINT_BASE_URL_VAR_NAME = "CUSTOM_ENDPOINT_BASE_URL"


class CustomEndpointConfig(ConfigModel):
    """Configuration for custom OpenAI-compatible endpoints (e.g., Ollama, LM Studio, etc.)"""

    api_key_method: OpenAIKeyMethod = Field(strict=False)

    def configure(self, secrets_provider: Optional[SecretsProviderAbstract] = None) -> Tuple[str, Optional[str]]:
        """Configure and return base URL and optional API key."""
        base_url = self._get_base_url(secrets_provider=secrets_provider)
        api_key = self._get_api_key(secrets_provider=secrets_provider)
        return base_url, api_key

    def _get_base_url(self, secrets_provider: Optional[SecretsProviderAbstract]) -> str:
        """Get base URL from environment or secrets provider."""
        match self.api_key_method:
            case OpenAIKeyMethod.ENV:
                log.debug("Getting Custom OpenAI base URL from environment.")
                try:
                    return get_required_env(CUSTOM_ENDPOINT_BASE_URL_VAR_NAME)
                except EnvVarNotFoundError as exc:
                    raise CustomEndpointCredentialsError(f"Error getting Custom OpenAI base URL from environment: {exc}") from exc
            case OpenAIKeyMethod.SECRET_PROVIDER:
                if not secrets_provider:
                    raise CustomEndpointCredentialsError("Secrets provider is required when using SECRET_PROVIDER method")
                log.verbose("Getting Custom OpenAI base URL from secrets provider.")
                try:
                    return secrets_provider.get_secret(secret_id=CUSTOM_ENDPOINT_BASE_URL_VAR_NAME)
                except SecretNotFoundError as exc:
                    raise CustomEndpointCredentialsError("Error getting Custom OpenAI base URL from secrets provider.") from exc

    def _get_api_key(self, secrets_provider: Optional[SecretsProviderAbstract] = None) -> Optional[str]:
        """Get API key if configured, otherwise return None for services that don't require authentication"""
        match self.api_key_method:
            case OpenAIKeyMethod.ENV:
                log.debug("Using Custom OpenAI API key from environment.")
                try:
                    return get_required_env(CUSTOM_ENDPOINT_API_KEY_VAR_NAME)
                except EnvVarNotFoundError:
                    log.debug("No Custom OpenAI API key found in environment - using None.")
                    return None
            case OpenAIKeyMethod.SECRET_PROVIDER:
                if not secrets_provider:
                    raise CustomEndpointCredentialsError("Secrets provider is required when using SECRET_PROVIDER method")
                log.verbose("Using Custom OpenAI API key from secrets provider.")
                try:
                    return secrets_provider.get_secret(secret_id=CUSTOM_ENDPOINT_API_KEY_VAR_NAME)
                except SecretNotFoundError:
                    log.debug("No Custom OpenAI API key found in secrets provider - using None.")
                    return None
