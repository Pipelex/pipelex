from typing import Tuple

from pydantic import Field

from pipelex import log
from pipelex.cogt.exceptions import CogtError
from pipelex.tools.config.models import ConfigModel
from pipelex.tools.environment import EnvVarNotFoundError, get_required_env
from pipelex.tools.secrets.secrets_errors import SecretNotFoundError
from pipelex.tools.secrets.secrets_provider_abstract import SecretsProviderAbstract
from pipelex.types import StrEnum


class XaiCredentialsError(CogtError):
    pass


class XaiKeyMethod(StrEnum):
    SECRET_PROVIDER = "secret_provider"
    ENV = "env"


XAI_API_KEY_VAR_NAME = "XAI_API_KEY"
XAI_API_ENDPOINT_VAR_NAME = "XAI_API_ENDPOINT"


class XaiConfig(ConfigModel):
    api_key_method: XaiKeyMethod = Field(strict=False)

    def configure(self, secrets_provider: SecretsProviderAbstract) -> Tuple[str, str]:
        """Configure and return endpoint and API key."""
        api_endpoint = self._get_api_endpoint(secrets_provider=secrets_provider)
        api_key = self._get_api_key(secrets_provider=secrets_provider)
        return api_endpoint, api_key

    def _get_api_endpoint(self, secrets_provider: SecretsProviderAbstract) -> str:
        """Get API endpoint from environment or secrets provider."""
        match self.api_key_method:
            case XaiKeyMethod.ENV:
                log.debug("Getting Xai API endpoint from environment.")
                try:
                    return get_required_env(XAI_API_ENDPOINT_VAR_NAME)
                except EnvVarNotFoundError as exc:
                    raise XaiCredentialsError(f"Error getting Xai API endpoint from environment: {exc}") from exc
            case XaiKeyMethod.SECRET_PROVIDER:
                log.verbose("Getting Xai API endpoint from secrets provider.")
                try:
                    return secrets_provider.get_secret(secret_id=XAI_API_ENDPOINT_VAR_NAME)
                except SecretNotFoundError as exc:
                    raise XaiCredentialsError("Error getting Xai API endpoint from secrets provider.") from exc

    def _get_api_key(self, secrets_provider: SecretsProviderAbstract) -> str:
        """Get API key from environment or secrets provider."""
        match self.api_key_method:
            case XaiKeyMethod.ENV:
                log.debug("Using Xai API key from environment.")
                try:
                    key_from_env = get_required_env(XAI_API_KEY_VAR_NAME)
                    return key_from_env
                except EnvVarNotFoundError as exc:
                    raise XaiCredentialsError(f"Error getting Xai API key from environment: {exc}") from exc
            case XaiKeyMethod.SECRET_PROVIDER:
                log.verbose("Using Xai API key from secrets provider.")
                try:
                    key_from_secrets_provider = secrets_provider.get_secret(secret_id=XAI_API_KEY_VAR_NAME)
                except SecretNotFoundError as exc:
                    raise XaiCredentialsError("Error getting Xai API key from secrets provider.") from exc
                return key_from_secrets_provider
