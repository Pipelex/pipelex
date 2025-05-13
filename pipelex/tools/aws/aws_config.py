# SPDX-FileCopyrightText: © 2025 Evotis S.A.S.
# SPDX-License-Identifier: Elastic-2.0
# "Pipelex" is a trademark of Evotis S.A.S.

from enum import StrEnum
from typing import Tuple

from pydantic import Field

from pipelex import log
from pipelex.hub import get_secret
from pipelex.tools.config.models import ConfigModel
from pipelex.tools.environment import EnvVarNotFoundError, get_optional_env, get_required_env
from pipelex.tools.exceptions import ToolException
from pipelex.tools.secrets.secrets_errors import SecretNotFoundError


class AwsCredentialsError(ToolException):
    pass


class AwsKeyMethod(StrEnum):
    SECRET_PROVIDER = "secret_provider"
    ENV = "env"


class AwsConfig(ConfigModel):
    api_key_method: AwsKeyMethod = Field(strict=False)
    aws_region: str

    aws_access_key_id_env_var_name: str
    aws_secret_access_key_env_var_name: str
    aws_region_env_var_name: str

    aws_access_key_id_secret_name: str
    aws_secret_access_key_secret_name: str

    def get_aws_access_keys(self) -> Tuple[str, str, str]:
        return self.get_aws_access_keys_with_method(api_key_method=self.api_key_method)

    def get_aws_access_keys_with_method(self, api_key_method: AwsKeyMethod) -> Tuple[str, str, str]:
        aws_access_key_id: str
        aws_secret_access_key: str
        aws_region: str
        match api_key_method:
            case AwsKeyMethod.ENV:
                log.debug("Getting AWS access keys from environment (key id and secret access key).")
                try:
                    aws_access_key_id = get_required_env(self.aws_access_key_id_env_var_name)
                    aws_secret_access_key = get_required_env(self.aws_secret_access_key_env_var_name)
                except EnvVarNotFoundError as exc:
                    raise AwsCredentialsError(f"Error getting AWS access keys from environment: {exc}") from exc
                log.debug("Getting AWS region from environment (priority override) or from aws_config.")
                aws_region = get_optional_env(self.aws_region_env_var_name) or self.aws_region
            case AwsKeyMethod.SECRET_PROVIDER:
                log.debug("Getting AWS secret access key from secrets provider (key id and secret access key).")
                try:
                    aws_access_key_id = get_secret(self.aws_access_key_id_secret_name)
                    aws_secret_access_key = get_secret(self.aws_secret_access_key_secret_name)
                except SecretNotFoundError as exc:
                    raise AwsCredentialsError("Error getting AWS access keys from secrets provider.") from exc
                log.debug("Getting AWS region from environment (priority override) or from aws_config.")
                aws_region = get_optional_env(self.aws_region_env_var_name) or self.aws_region

        return aws_access_key_id, aws_secret_access_key, aws_region
