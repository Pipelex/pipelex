from enum import StrEnum

from pydantic import Field

from pipelex import log
from pipelex.runtime_hub import get_secret
from pipelex.system.configuration.config_model import ConfigModel
from pipelex.system.environment import get_required_env
from pipelex.system.exceptions import EnvVarNotFoundError
from pipelex.tools.aws.exceptions import AwsCredentialsError
from pipelex.tools.secrets.exceptions import SecretNotFoundError


class AwsKeyMethod(StrEnum):
    SECRET_PROVIDER = "secret_provider"
    ENV = "env"


class BedrockAccessVariant(StrEnum):
    AWS_ACCESS = "aws_access"
    BEDROCK_TOKEN = "bedrock_token"


AWS_ACCESS_KEY_ID_VAR_NAME = "AWS_ACCESS_KEY_ID"
AWS_SECRET_ACCESS_KEY_VAR_NAME = "AWS_SECRET_ACCESS_KEY"
AWS_REGION_VAR_NAME = "AWS_REGION"

BEDROCK_TOKEN_VAR_NAME = "AWS_BEARER_TOKEN_BEDROCK"


class AwsConfig(ConfigModel):
    api_key_method: AwsKeyMethod = Field(strict=False)
    bedrock_access_variant: BedrockAccessVariant = Field(strict=False)

    def get_aws_access_keys(self) -> tuple[str, str, str]:
        return self.get_aws_access_keys_with_method(api_key_method=self.api_key_method)

    def get_aws_access_keys_with_method(self, *, api_key_method: AwsKeyMethod) -> tuple[str, str, str]:
        match api_key_method:
            case AwsKeyMethod.ENV:
                log.verbose("Getting AWS access keys from environment (key id and secret access key).")
                try:
                    aws_access_key_id = get_required_env(AWS_ACCESS_KEY_ID_VAR_NAME)
                    aws_secret_access_key = get_required_env(AWS_SECRET_ACCESS_KEY_VAR_NAME)
                    aws_region = get_required_env(AWS_REGION_VAR_NAME)
                except EnvVarNotFoundError as exc:
                    msg = f"Error getting AWS access keys from environment: {exc}"
                    raise AwsCredentialsError(msg) from exc
                log.verbose("Getting AWS region from environment (priority override) or from aws_config.")

            case AwsKeyMethod.SECRET_PROVIDER:
                log.verbose("Getting AWS secret access key from secrets provider (key id and secret access key).")
                try:
                    aws_access_key_id = get_secret(AWS_ACCESS_KEY_ID_VAR_NAME)
                    aws_secret_access_key = get_secret(AWS_SECRET_ACCESS_KEY_VAR_NAME)
                    aws_region = get_secret(AWS_REGION_VAR_NAME)
                except SecretNotFoundError as exc:
                    msg = "Error getting AWS access keys from secrets provider."
                    raise AwsCredentialsError(msg) from exc
                log.verbose("Getting AWS region from environment (priority override) or from aws_config.")

        return aws_access_key_id, aws_secret_access_key, aws_region

    def get_bedrock_token(self) -> str:
        match self.api_key_method:
            case AwsKeyMethod.ENV:
                try:
                    return get_required_env(BEDROCK_TOKEN_VAR_NAME)
                except EnvVarNotFoundError as exc:
                    msg = f"Error getting Bedrock token from environment: {exc}"
                    raise AwsCredentialsError(msg) from exc
            case AwsKeyMethod.SECRET_PROVIDER:
                try:
                    return get_secret(BEDROCK_TOKEN_VAR_NAME)
                except SecretNotFoundError as exc:
                    msg = "Error getting Bedrock token from secrets provider."
                    raise AwsCredentialsError(msg) from exc
