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


class PerplexityCredentialsError(CogtError):
    pass


class PerplexityKeyMethod(StrEnum):
    SECRET_PROVIDER = "secret_provider"
    ENV = "env"


class PerplexityConfig(ConfigModel):
    api_endpoint: str
    api_key_method: PerplexityKeyMethod = Field(strict=False)
    api_key_env_var_name: str
    api_key_secret_name: str

    def get_api_key(self, secrets_provider: SecretsProviderAbstract) -> str:
        match self.api_key_method:
            case PerplexityKeyMethod.ENV:
                log.debug("Using Perplexity API key from environment.")
                try:
                    key_from_env = get_required_env(self.api_key_env_var_name)
                    return key_from_env
                except EnvVarNotFoundError as exc:
                    raise PerplexityCredentialsError(f"Error getting Azure OpenAI API key from environment: {exc}") from exc
            case PerplexityKeyMethod.SECRET_PROVIDER:
                log.verbose("Using Perplexity API key from secrets provider.")
                try:
                    key_from_secrets_provider = secrets_provider.get_secret(secret_id=self.api_key_secret_name)
                except SecretNotFoundError as exc:
                    raise PerplexityCredentialsError("Error getting Perplexity API key from secrets provider.") from exc
                return key_from_secrets_provider
