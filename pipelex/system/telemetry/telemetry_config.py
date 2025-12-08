from pydantic import Field, ValidationError, model_validator

from pipelex.system.configuration.config_model import ConfigModel
from pipelex.system.telemetry.exceptions import TelemetryConfigValidationError
from pipelex.tools.misc.toml_utils import load_toml_from_path
from pipelex.tools.typing.pydantic_utils import format_pydantic_validation_error
from pipelex.types import Self, StrEnum

TELEMETRY_CONFIG_FILE_NAME = "telemetry.toml"


class TelemetryMode(StrEnum):
    ANONYMOUS = "anonymous"
    OFF = "off"
    IDENTIFIED = "identified"

    @property
    def is_enabled(self) -> bool:
        match self:
            case TelemetryMode.ANONYMOUS:
                return True
            case TelemetryMode.OFF:
                return False
            case TelemetryMode.IDENTIFIED:
                return True

    @property
    def is_identified(self) -> bool:
        match self:
            case TelemetryMode.ANONYMOUS:
                return False
            case TelemetryMode.OFF:
                return False
            case TelemetryMode.IDENTIFIED:
                return True


class TelemetryConfig(ConfigModel):
    telemetry_mode: TelemetryMode = Field(strict=False)
    host: str
    project_api_key: str
    respect_dnt: bool
    redact: list[str]
    geoip_enabled: bool
    dry_mode_enabled: bool
    verbose_enabled: bool
    user_id: str | None = None  # Set if telemetry_mode is IDENTIFIED
    ai_tracing_enabled: bool  # Enable OpenTelemetry tracing for AI operations
    capture_content_enabled: bool  # Controls gen_ai.prompt/completion content capture for OTel
    capture_content_max_length: int | None = None  # Max length for captured content (None = unlimited)
    capture_pipe_codes_enabled: bool  # Controls whether pipe codes appear in span names/attributes
    capture_output_class_name_enabled: bool  # Controls whether output class names appear in span names/attributes
    langfuse_enabled: bool = False  # Enable Langfuse OTLP exporter
    langfuse_base_url: str | None = None  # Override for self-hosted Langfuse (defaults to https://cloud.langfuse.com)
    otlp_endpoint: str | None = None  # Optional OTLP endpoint for generic tracing
    otlp_headers: dict[str, str] | None = None  # Optional headers for OTLP export

    @model_validator(mode="after")
    def validate_user_id(self) -> Self:
        if self.telemetry_mode.is_identified and not self.user_id:
            msg = "user_id is required when telemetry_mode is IDENTIFIED"
            raise ValueError(msg)
        return self


def load_telemetry_config(path: str) -> TelemetryConfig:
    telemetry_config_toml = load_toml_from_path(path=path)
    try:
        telemetry_config = TelemetryConfig.model_validate(telemetry_config_toml)
    except ValidationError as exc:
        validation_error_msg = format_pydantic_validation_error(exc)
        msg = f"Invalid telemetry configuration: {validation_error_msg}"
        raise TelemetryConfigValidationError(msg) from exc
    return telemetry_config
