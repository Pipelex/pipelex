from typing import ClassVar, Literal

from pydantic import Field, model_validator
from typing_extensions import override

from pipelex.system.configuration.config_model import ConfigModel
from pipelex.tools.storage.exceptions import StorageConfigError
from pipelex.types import Self, StrEnum
from pipelex.urls import URLs


class StorageMethod(StrEnum):
    LOCAL = "local"
    IN_MEMORY = "in_memory"
    S3 = "s3"
    GCP = "gcp"


class StorageMethodConfig(ConfigModel):
    """Base for per-method storage configs: shared uri_format rules and operator-facing error reporting.

    Subclasses declare `provider_label` and extend `_collect_error_msgs()` with their own checks.
    """

    provider_label: ClassVar[str]

    uri_format: str

    def _collect_error_msgs(self) -> list[str]:
        error_msgs: list[str] = []
        if self.uri_format == "":
            error_msgs.append("- set a value for uri_format")
        elif "{hash}" not in self.uri_format:
            error_msgs.append("- uri_format must contain a {hash} placeholder")
        return error_msgs

    def lazy_validate(self) -> None:
        error_msgs = self._collect_error_msgs()
        if not error_msgs:
            return
        msg = f"You have enabled storage on {self.provider_label} so you need a proper {self.provider_label} config.\n\n"
        msg += f"To fix your {self.provider_label} config:\n"
        msg += "\n".join(error_msgs)
        msg += f"\nThis can be done in the .pipelex/pipelex.toml file. More details can be found in the documentation: {URLs.documentation}"
        raise StorageConfigError(msg)


class StorageLocalConfig(StorageMethodConfig):
    provider_label: ClassVar[str] = "local"

    local_storage_path: str

    @override
    def _collect_error_msgs(self) -> list[str]:
        error_msgs = super()._collect_error_msgs()
        if self.local_storage_path == "":
            error_msgs.append("- set a value for local_storage_path")
        return error_msgs


class StorageInMemoryConfig(StorageMethodConfig):
    provider_label: ClassVar[str] = "in_memory"


class StorageBucketConfig(StorageMethodConfig):
    """Shared shape for bucket-based remote providers: bucket naming rules and signed-URL lifespan."""

    bucket_name: str
    signed_urls_lifespan_seconds: int | Literal["disabled"]

    @property
    def signed_urls_lifespan(self) -> int | None:
        """Return signed URL lifespan in seconds, or None if disabled."""
        if self.signed_urls_lifespan_seconds == "disabled":
            return None
        return self.signed_urls_lifespan_seconds

    @override
    def _collect_error_msgs(self) -> list[str]:
        error_msgs = super()._collect_error_msgs()
        if self.bucket_name == "":
            error_msgs.append("- set a value for bucket_name")
        elif "." in self.bucket_name:
            error_msgs.append("- bucket_name cannot contain a dot")
        elif "/" in self.bucket_name:
            error_msgs.append("- bucket_name cannot contain a slash")
        return error_msgs


class StorageS3Config(StorageBucketConfig):
    provider_label: ClassVar[str] = "S3"

    region: str

    @override
    def _collect_error_msgs(self) -> list[str]:
        error_msgs = super()._collect_error_msgs()
        if self.region == "":
            error_msgs.append("- set a value for region")
        return error_msgs


class StorageGcpConfig(StorageBucketConfig):
    provider_label: ClassVar[str] = "GCP"

    project_id: str

    @override
    def _collect_error_msgs(self) -> list[str]:
        error_msgs = super()._collect_error_msgs()
        if self.project_id == "":
            error_msgs.append("- set a value for project_id")
        return error_msgs


class StorageProviderConfig(ConfigModel):
    """Provider-selection config shared by asset storage and payload codec storage."""

    method: StorageMethod = Field(strict=False)
    local: StorageLocalConfig | None = None
    in_memory: StorageInMemoryConfig | None = None
    s3: StorageS3Config | None = None
    gcp: StorageGcpConfig | None = None

    @model_validator(mode="after")
    def validate_storage_provider_config(self) -> Self:
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
        match self.method:
            case StorageMethod.LOCAL:
                if not self.local:
                    msg = "local config is required to access storage_path"
                    raise StorageConfigError(msg)
                return self.local.local_storage_path
            case StorageMethod.IN_MEMORY | StorageMethod.S3 | StorageMethod.GCP:
                msg = f"storage_path is only available when method is local, but method is '{self.method}'"
                raise StorageConfigError(msg)

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


class StorageConfig(StorageProviderConfig):
    is_fetch_remote_content_enabled: bool
    is_upload_local_content_enabled: bool
