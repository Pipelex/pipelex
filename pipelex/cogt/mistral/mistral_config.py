# SPDX-FileCopyrightText: © 2025 Evotis S.A.S.
# SPDX-License-Identifier: Elastic-2.0
# "Pipelex" is a trademark of Evotis S.A.S.

from pipelex.cogt.exceptions import CogtError
from pipelex.tools.config.models import ConfigModel
from pipelex.tools.secrets.secrets_errors import SecretNotFoundError
from pipelex.tools.secrets.secrets_provider_abstract import SecretsProviderAbstract


class MistralCredentialsError(CogtError):
    pass


class MistralConfig(ConfigModel):
    api_key_secret_name: str

    def api_key(self, secrets_provider: SecretsProviderAbstract) -> str:
        try:
            return secrets_provider.get_secret(secret_id=self.api_key_secret_name)
        except SecretNotFoundError as exc:
            raise MistralCredentialsError("Error getting Mistral API key from secrets provider.") from exc
