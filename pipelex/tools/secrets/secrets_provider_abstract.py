# SPDX-FileCopyrightText: © 2025 Evotis S.A.S.
# SPDX-License-Identifier: Elastic-2.0
# "Pipelex" is a trademark of Evotis S.A.S.

from abc import ABC, abstractmethod
from typing import Optional

LATEST_SECRET_VERSION_NAME = "latest"


class SecretsProviderAbstract(ABC):
    @abstractmethod
    def get_required_secret(self, secret_id: str) -> str: ...

    @abstractmethod
    def get_optional_secret(self, secret_id: str) -> Optional[str]: ...

    @abstractmethod
    def get_required_secret_specific_version(self, secret_id: str, version_id: str) -> str: ...

    @abstractmethod
    def get_optional_secret_specific_version(self, secret_id: str, version_id: str) -> Optional[str]: ...

    @abstractmethod
    def set_secret_as_env_var(self, secret_id: str, version_id: str = LATEST_SECRET_VERSION_NAME): ...

    def get_secret(self, secret_id: str) -> str:
        return self.get_required_secret(secret_id=secret_id)
