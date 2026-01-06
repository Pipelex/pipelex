from pydantic import Field, model_validator

from pipelex.base_exceptions import PipelexConfigError
from pipelex.system.configuration.config_model import ConfigModel
from pipelex.types import Self, StrEnum


class StorageMethod(StrEnum):
    LOCAL = "local"
    IN_MEMORY = "in_memory"


class StorageLocalConfig(ConfigModel):
    uri_format: str
    local_storage_path: str


class StorageInMemoryConfig(ConfigModel):
    uri_format: str


class StorageConfig(ConfigModel):
    is_fetch_remote_content_enabled: bool
    method: StorageMethod = Field(strict=False)
    local: StorageLocalConfig | None = None
    in_memory: StorageInMemoryConfig | None = None

    @model_validator(mode="after")
    def validate_storage_config(self) -> Self:
        match self.method:
            case StorageMethod.LOCAL:
                if not self.local:
                    msg = "local config is required when method is local"
                    raise PipelexConfigError(msg)
            case StorageMethod.IN_MEMORY:
                if not self.in_memory:
                    msg = "in_memory config is required when method is in_memory"
                    raise PipelexConfigError(msg)
        return self

    @property
    def storage_path(self) -> str:
        if not self.local:
            msg = "local config is required when method is local"
            raise PipelexConfigError(msg)
        return self.local.local_storage_path

    @property
    def uri_format(self) -> str:
        match self.method:
            case StorageMethod.LOCAL:
                if not self.local:
                    msg = "local config is required to access uri_format"
                    raise PipelexConfigError(msg)
                return self.local.uri_format
            case StorageMethod.IN_MEMORY:
                if not self.in_memory:
                    msg = "in_memory config is required to access uri_format"
                    raise PipelexConfigError(msg)
                return self.in_memory.uri_format
