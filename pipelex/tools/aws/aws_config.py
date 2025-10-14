from pydantic import Field

from pipelex import log
from pipelex.hub import get_secret
from pipelex.system.configuration.config_model import ConfigModel
from pipelex.system.environment import EnvVarNotFoundError, get_required_env
from pipelex.system.exceptions import CredentialsError
from pipelex.tools.secrets.secrets_errors import SecretNotFoundError
from pipelex.types import StrEnum


class AwsCredentialsError(CredentialsError):
    pass


class AwsKeyMethod(StrEnum):
    SECRET_PROVIDER = "secret_provider"
    ENV = "env"


AWS_ACCESS_KEY_ID_VAR_NAME = "AWS_ACCESS_KEY_ID"
AWS_SECRET_ACCESS_KEY_VAR_NAME = "AWS_SECRET_ACCESS_KEY"
AWS_REGION_VAR_NAME = "AWS_REGION"


class AwsConfig(ConfigModel):
    api_key_method: AwsKeyMethod = Field(strict=False)

    def get_aws_access_keys(self) -> tuple[str, str, str]:
        return self.get_aws_access_keys_with_method(api_key_method=self.api_key_method)

    def get_aws_access_keys_with_method(self, api_key_method: AwsKeyMethod) -> tuple[str, str, str]:
        match api_key_method:
            case AwsKeyMethod.ENV:
                log.debug("Getting AWS access keys from environment (key id and secret access key).")
                try:
                    aws_access_key_id = get_required_env(AWS_ACCESS_KEY_ID_VAR_NAME)
                    aws_secret_access_key = get_required_env(AWS_SECRET_ACCESS_KEY_VAR_NAME)
                    aws_region = get_required_env(AWS_REGION_VAR_NAME)
                except EnvVarNotFoundError as exc:
                    msg = f"Error getting AWS access keys from environment: {exc}"
                    raise AwsCredentialsError(msg) from exc
                log.debug("Getting AWS region from environment (priority override) or from aws_config.")

            case AwsKeyMethod.SECRET_PROVIDER:
                log.debug("Getting AWS secret access key from secrets provider (key id and secret access key).")
                try:
                    aws_access_key_id = get_secret(AWS_ACCESS_KEY_ID_VAR_NAME)
                    aws_secret_access_key = get_secret(AWS_SECRET_ACCESS_KEY_VAR_NAME)
                    aws_region = get_secret(AWS_REGION_VAR_NAME)
                except SecretNotFoundError as exc:
                    msg = "Error getting AWS access keys from secrets provider."
                    raise AwsCredentialsError(msg) from exc
                log.debug("Getting AWS region from environment (priority override) or from aws_config.")

        return aws_access_key_id, aws_secret_access_key, aws_region
