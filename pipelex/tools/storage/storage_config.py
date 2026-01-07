from typing import Literal

from pydantic import Field, model_validator

from pipelex.system.configuration.config_model import ConfigModel
from pipelex.tools.storage.exceptions import StorageConfigError
from pipelex.types import Self, StrEnum
from pipelex.urls import URLs


class StorageMethod(StrEnum):
    LOCAL = "local"
    IN_MEMORY = "in_memory"
    S3 = "s3"
    GCP = "gcp"


class StorageLocalConfig(ConfigModel):
    uri_format: str
    local_storage_path: str


class StorageInMemoryConfig(ConfigModel):
    uri_format: str


class StorageS3Config(ConfigModel):
    uri_format: str
    bucket_name: str
    region: str
    signed_urls_lifespan_seconds: int | Literal["disabled"]

    @property
    def signed_urls_lifespan(self) -> int | None:
        """Return signed URL lifespan in seconds, or None if disabled."""
        if self.signed_urls_lifespan_seconds == "disabled":
            return None
        return self.signed_urls_lifespan_seconds

    def lazy_validate(self):
        error_msgs: list[str] = []

        if self.uri_format == "":
            error_msgs.append("- set a value for uri_format")
        elif "{hash}" not in self.uri_format:
            error_msgs.append("- uri_format must contain a {hash} placeholder")

        if self.bucket_name == "":
            error_msgs.append("- set a value for bucket_name")
        elif "." in self.bucket_name:
            error_msgs.append("- bucket_name cannot contain a dot")
        elif "/" in self.bucket_name:
            error_msgs.append("- bucket_name cannot contain a slash")

        if self.region == "":
            error_msgs.append("- set a value for region")

        if error_msgs:
            msg = "You have enabled storage on S3 so you need a proper S3 config.\n\nTo fix you S3 config:\n"
            msg += "\n".join(error_msgs)
            msg += f"\nThis can be done in the .pipelex/pipelex.toml file. More details can be found in the documentation: {URLs.documentation}"
            raise StorageConfigError(msg)


class StorageGcpConfig(ConfigModel):
    uri_format: str
    bucket_name: str
    project_id: str
    signed_urls_lifespan_seconds: int | Literal["disabled"]

    @property
    def signed_urls_lifespan(self) -> int | None:
        """Return signed URL lifespan in seconds, or None if disabled."""
        if self.signed_urls_lifespan_seconds == "disabled":
            return None
        return self.signed_urls_lifespan_seconds

    def lazy_validate(self):
        error_msgs: list[str] = []

        if self.uri_format == "":
            error_msgs.append("set a value for uri_format")
        elif "hash" not in self.uri_format:
            error_msgs.append("uri_format must contain a {hash} placeholder")

        if self.bucket_name == "":
            error_msgs.append("set a value for bucket_name")
        elif "." in self.bucket_name:
            error_msgs.append("bucket_name cannot contain a dot")
        elif "/" in self.bucket_name:
            error_msgs.append("bucket_name cannot contain a slash")

        if self.project_id == "":
            error_msgs.append("set a value for project_id")

        if error_msgs:
            msg = "You have enabled storage on GCP so you need a proper GCP config:\n"
            msg += "\n".join(error_msgs)
            raise StorageConfigError(msg)


class StorageConfig(ConfigModel):
    is_fetch_remote_content_enabled: bool
    method: StorageMethod = Field(strict=False)
    local: StorageLocalConfig | None = None
    in_memory: StorageInMemoryConfig | None = None
    s3: StorageS3Config | None = None
    gcp: StorageGcpConfig | None = None

    @model_validator(mode="after")
    def validate_storage_config(self) -> Self:
        match self.method:
            case StorageMethod.LOCAL:
                if not self.local:
                    msg = "local config is required when method is local"
                    raise StorageConfigError(msg)
            case StorageMethod.IN_MEMORY:
                if not self.in_memory:
                    msg = "in_memory config is required when method is in_memory"
                    raise StorageConfigError(msg)
            case StorageMethod.S3:
                if not self.s3:
                    msg = "s3 config is required when method is s3"
                    raise StorageConfigError(msg)
            case StorageMethod.GCP:
                if not self.gcp:
                    msg = "gcp config is required when method is gcp"
                    raise StorageConfigError(msg)
        return self

    @property
    def storage_path(self) -> str:
        if not self.local:
            msg = "local config is required when method is local"
            raise StorageConfigError(msg)
        return self.local.local_storage_path

    @property
    def uri_format(self) -> str:
        match self.method:
            case StorageMethod.LOCAL:
                if not self.local:
                    msg = "local config is required to access uri_format"
                    raise StorageConfigError(msg)
                return self.local.uri_format
            case StorageMethod.IN_MEMORY:
                if not self.in_memory:
                    msg = "in_memory config is required to access uri_format"
                    raise StorageConfigError(msg)
                return self.in_memory.uri_format
            case StorageMethod.S3:
                if not self.s3:
                    msg = "s3 config is required to access uri_format"
                    raise StorageConfigError(msg)
                return self.s3.uri_format
            case StorageMethod.GCP:
                if not self.gcp:
                    msg = "gcp config is required to access uri_format"
                    raise StorageConfigError(msg)
                return self.gcp.uri_format
