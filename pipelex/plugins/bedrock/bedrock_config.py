from pydantic import Field

from pipelex import log
from pipelex.cogt.exceptions import CogtError
from pipelex.tools.config.models import ConfigModel
from pipelex.tools.environment import EnvVarNotFoundError, get_required_env
from pipelex.tools.secrets.secrets_errors import SecretNotFoundError
from pipelex.tools.secrets.secrets_provider_abstract import SecretsProviderAbstract
from pipelex.types import StrEnum


class BedrockCredentialsError(CogtError):
    pass


class BedrockClientMethod(StrEnum):
    BOTO3 = "boto3"
    AIBOTO3 = "aioboto3"


AWS_REGION_VAR_NAME = "AWS_REGION"


class BedrockConfig(ConfigModel):
    client_method: BedrockClientMethod = Field(strict=False)

    def configure(self, secrets_provider: SecretsProviderAbstract) -> str:
        """Configure and return AWS region."""
        return self._get_region(secrets_provider=secrets_provider)

    def _get_region(self, secrets_provider: SecretsProviderAbstract) -> str:
        """Get AWS region from environment or secrets provider."""
        log.debug("Getting AWS region.")
        try:
            return get_required_env(AWS_REGION_VAR_NAME)
        except EnvVarNotFoundError:
            log.verbose("AWS region not found in environment, trying secrets provider.")
            try:
                return secrets_provider.get_secret(secret_id=AWS_REGION_VAR_NAME)
            except SecretNotFoundError as exc:
                raise BedrockCredentialsError("Error getting AWS region from secrets provider.") from exc
