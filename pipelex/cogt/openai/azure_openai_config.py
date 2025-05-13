# SPDX-FileCopyrightText: © 2025 Evotis S.A.S.
# SPDX-License-Identifier: Elastic-2.0
# "Pipelex" is a trademark of Evotis S.A.S.

from enum import StrEnum

from pydantic import Field

from pipelex import log
from pipelex.cogt.exceptions import CogtError
from pipelex.tools.config.models import ConfigModel
from pipelex.tools.environment import EnvVarNotFoundError, get_required_env
from pipelex.tools.secrets.secrets_errors import SecretNotFoundError
from pipelex.tools.secrets.secrets_provider_abstract import SecretsProviderAbstract


class AzureOpenAICredentialsError(CogtError):
    pass


class AzureOpenAIKeyMethod(StrEnum):
    SECRET_PROVIDER = "secret_provider"
    ENV = "env"


class AzureOpenAIConfig(ConfigModel):
    api_endpoint: str
    api_version: str
    api_key_method: AzureOpenAIKeyMethod = Field(strict=False)
    api_key_env_var_name: str
    api_key_secret_name: str

    def get_api_key(self, secrets_provider: SecretsProviderAbstract) -> str:
        match self.api_key_method:
            case AzureOpenAIKeyMethod.ENV:
                log.debug("Using Azure OpenAI API key from environment.")
                try:
                    key_from_env = get_required_env(self.api_key_env_var_name)
                    return key_from_env
                except EnvVarNotFoundError as exc:
                    raise AzureOpenAICredentialsError(f"Error getting Azure OpenAI API key from environment: {exc}") from exc
            case AzureOpenAIKeyMethod.SECRET_PROVIDER:
                log.verbose("Using Azure OpenAI API key from secrets provider.")
                # TODO: make it automatically select the right key for the right azure resource
                try:
                    key_from_secrets_provider = secrets_provider.get_secret(secret_id=self.api_key_secret_name)
                except SecretNotFoundError as exc:
                    raise AzureOpenAICredentialsError("Error getting Azure OpenAI API key from secrets provider.") from exc
                return key_from_secrets_provider
