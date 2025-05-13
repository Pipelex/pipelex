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


class OpenAICredentialsError(CogtError):
    pass


class OpenAIKeyMethod(StrEnum):
    SECRET_PROVIDER = "secret_provider"
    ENV = "env"


class OpenAIOpenAIConfig(ConfigModel):
    api_key_method: OpenAIKeyMethod = Field(strict=False)
    api_key_secret_name: str
    api_key_env_var_name: str

    def get_api_key(self, secrets_provider: SecretsProviderAbstract) -> str:
        match self.api_key_method:
            case OpenAIKeyMethod.ENV:
                log.debug("Using OpenAI API key from environment.")
                try:
                    key_from_env = get_required_env(self.api_key_env_var_name)
                    return key_from_env
                except EnvVarNotFoundError as exc:
                    raise OpenAICredentialsError(f"Error getting OpenAI API key from environment: {exc}") from exc
            case OpenAIKeyMethod.SECRET_PROVIDER:
                log.verbose("Using OpenAI API key from secrets provider.")
                try:
                    key_from_service_provider = secrets_provider.get_secret(secret_id=self.api_key_secret_name)
                except SecretNotFoundError as exc:
                    raise OpenAICredentialsError("Error getting OpenAI API key from secrets provider.") from exc
                return key_from_service_provider
