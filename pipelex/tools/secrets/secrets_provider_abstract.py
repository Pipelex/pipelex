from abc import ABC, abstractmethod

LATEST_SECRET_VERSION_NAME = "latest"


class SecretsProviderAbstract(ABC):
    @abstractmethod
    def get_required_secret(self, secret_id: str) -> str: ...

    @abstractmethod
    def get_optional_secret(self, secret_id: str) -> str | None: ...

    @abstractmethod
    def get_required_secret_specific_version(self, secret_id: str, version_id: str) -> str: ...

    @abstractmethod
    def get_optional_secret_specific_version(self, secret_id: str, version_id: str) -> str | None: ...

    @abstractmethod
    def set_secret_as_env_var(self, secret_id: str, version_id: str = LATEST_SECRET_VERSION_NAME): ...

    def get_secret(self, secret_id: str) -> str:
        return self.get_required_secret(secret_id=secret_id)
