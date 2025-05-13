# SPDX-FileCopyrightText: © 2025 Evotis S.A.S.
# SPDX-License-Identifier: Elastic-2.0
# "Pipelex" is a trademark of Evotis S.A.S.

from typing import Optional

from typing_extensions import override

from pipelex.tools.environment import EnvVarNotFoundError, get_optional_env, get_required_env
from pipelex.tools.secrets.secrets_errors import SecretNotFoundError
from pipelex.tools.secrets.secrets_provider_abstract import SecretsProviderAbstract


class EnvSecretsProvider(SecretsProviderAbstract):
    @override
    def get_required_secret(self, secret_id: str) -> str:
        try:
            return get_required_env(key=secret_id)
        except EnvVarNotFoundError as exc:
            raise SecretNotFoundError(f"Secret '{secret_id}' not found") from exc

    @override
    def get_optional_secret(self, secret_id: str) -> Optional[str]:
        return get_optional_env(key=secret_id)

    @override
    def get_required_secret_specific_version(self, secret_id: str, version_id: str) -> str:
        raise NotImplementedError("EnvSecretsProvider does not support specific versions")

    @override
    def get_optional_secret_specific_version(self, secret_id: str, version_id: str) -> Optional[str]:
        raise NotImplementedError("EnvSecretsProvider does not support specific versions")

    @override
    def set_secret_as_env_var(self, secret_id: str, version_id: str = "latest"):
        pass
