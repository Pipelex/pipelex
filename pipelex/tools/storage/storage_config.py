from string import Formatter
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

    # The exact keyword arguments GeneratedContentFactory._build_storage_key supplies to uri_format.format();
    # any other placeholder would raise KeyError/IndexError at content-store time, so reject it at config time.
    URI_FORMAT_SUPPORTED_FIELDS: ClassVar[frozenset[str]] = frozenset({"primary_id", "secondary_id", "hash", "extension"})

    provider_label: ClassVar[str]

    uri_format: str

    def _collect_uri_format_error_msgs(self) -> list[str]:
        if self.uri_format == "":
            return ["- set a value for uri_format"]
        try:
            # Parse instead of substring-checking: the escaped literal "{{hash}}" renders as the constant
            # "{hash}" (same URI for every object), and a format spec like "{hash:.0}" truncates the digest
            # to a constant/colliding key. Only a plain {hash} replacement field guarantees unique keys.
            parsed_fields = [
                (field_name, format_spec, conversion)
                for _, field_name, format_spec, conversion in Formatter().parse(self.uri_format)
                if field_name is not None
            ]
        except ValueError as exc:
            return [f"- uri_format is not a valid format string ({exc})"]
        error_msgs: list[str] = []
        unsupported_names: set[str] = set()
        nonplain_names: set[str] = set()
        hash_field_found = False
        plain_hash_found = False
        for field_name, format_spec, conversion in parsed_fields:
            base_name = field_name.split(".")[0].split("[")[0]
            if base_name not in self.URI_FORMAT_SUPPORTED_FIELDS:
                unsupported_names.add(field_name)
                continue
            if base_name == "hash":
                hash_field_found = True
                if field_name == "hash" and not format_spec and not conversion:
                    plain_hash_found = True
            elif field_name != base_name or format_spec or conversion:
                # Every supported field is a str path component, so a format spec, conversion, or
                # attribute/index access renders a constant, colliding, or oversized key ({primary_id:.0}
                # truncates to "" → every object shares one URI; {primary_id:1000000000} would allocate a
                # ~1GB string at render time) — the same silent-overwrite/OOM hazard we reject on {hash}.
                nonplain_names.add(field_name)
        supported_list = ", ".join("{" + name + "}" for name in sorted(self.URI_FORMAT_SUPPORTED_FIELDS))
        for unsupported_name in sorted(unsupported_names):
            error_msgs.append(f"- uri_format placeholder '{{{unsupported_name}}}' is not supported (supported: {supported_list})")
        for nonplain_name in sorted(nonplain_names):
            error_msgs.append(f"- uri_format placeholder '{{{nonplain_name}}}' must be plain: no format spec, conversion, or attribute/index access")
        if not hash_field_found:
            error_msgs.append("- uri_format must contain a {hash} placeholder")
        elif not plain_hash_found:
            error_msgs.append("- the {hash} placeholder must be plain: no format spec, conversion, or attribute/index access")
        if not error_msgs:
            # Defensive backstop: only plain {supported} placeholders reach here, so format() with the real
            # keyword set is cheap and cannot allocate — it just proves nothing slipped past the parse checks.
            try:
                self.uri_format.format(**dict.fromkeys(self.URI_FORMAT_SUPPORTED_FIELDS, "test"))
            except (KeyError, IndexError, ValueError, TypeError, AttributeError) as exc:
                # The full set str.format raises — the backstop must never let a raw formatting error escape
                error_msgs.append(f"- uri_format failed a test rendering ({exc})")
        return error_msgs

    def _collect_error_msgs(self) -> list[str]:
        return self._collect_uri_format_error_msgs()

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
        if isinstance(self.signed_urls_lifespan_seconds, int) and self.signed_urls_lifespan_seconds <= 0:
            error_msgs.append("- signed_urls_lifespan_seconds must be a positive number of seconds, or 'disabled'")
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
