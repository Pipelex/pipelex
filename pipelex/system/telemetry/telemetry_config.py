from functools import partial

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from pipelex.system.configuration.config_model import ConfigModel
from pipelex.system.telemetry.exceptions import TelemetryConfigValidationError
from pipelex.tools.misc.dict_utils import apply_to_strings_recursive
from pipelex.tools.misc.toml_utils import load_toml_from_path
from pipelex.tools.secrets.secrets_provider_abstract import SecretsProviderAbstract
from pipelex.tools.secrets.secrets_utils import (
    UnknownVarPrefixError,
    VarFallbackPatternError,
    VarNotFoundError,
    substitute_vars,
)
from pipelex.tools.typing.pydantic_utils import empty_list_factory_of, format_pydantic_validation_error
from pipelex.types import Self, StrEnum

TELEMETRY_CONFIG_FILE_NAME = "telemetry.toml"


class PostHogMode(StrEnum):
    """Mode for PostHog event tracking."""

    ANONYMOUS = "anonymous"
    OFF = "off"
    IDENTIFIED = "identified"

    @property
    def is_enabled(self) -> bool:
        match self:
            case PostHogMode.ANONYMOUS:
                return True
            case PostHogMode.OFF:
                return False
            case PostHogMode.IDENTIFIED:
                return True

    @property
    def is_identified(self) -> bool:
        match self:
            case PostHogMode.ANONYMOUS:
                return False
            case PostHogMode.OFF:
                return False
            case PostHogMode.IDENTIFIED:
                return True


class PostHogTracingCaptureConfig(BaseModel):
    """Privacy controls for what data to capture in PostHog spans."""

    model_config = ConfigDict(extra="forbid")

    content: bool = Field(default=False, description="Capture prompt/completion content")
    content_max_length: int | None = Field(default=None, description="Max length for captured content (None = unlimited)")
    pipe_codes: bool = Field(default=False, description="Include pipe codes in span names/attributes")
    output_class_names: bool = Field(default=False, description="Include output class names in span names/attributes")


class PostHogTracingConfig(BaseModel):
    """Configuration for AI span tracing to your PostHog."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = Field(default=False, description="Send AI spans to your PostHog")
    capture: PostHogTracingCaptureConfig = Field(
        default_factory=PostHogTracingCaptureConfig, description="Privacy controls for data sent to your PostHog"
    )


class PostHogConfig(BaseModel):
    """PostHog configuration for event tracking and span export."""

    model_config = ConfigDict(extra="forbid")

    mode: PostHogMode = Field(default=PostHogMode.OFF, strict=False, description="Event tracking mode")
    user_id: str | None = Field(default=None, description="Required when mode is 'identified'")
    host: str = Field(default="https://us.i.posthog.com", description="PostHog host URL")
    api_key: str = Field(description="PostHog project API key")
    geoip: bool = Field(default=True, description="Enable GeoIP lookup")
    debug: bool = Field(default=False, description="Enable PostHog debug mode")
    redact_properties: list[str] = Field(default_factory=list, description="Event properties to redact")
    tracing: PostHogTracingConfig = Field(default_factory=PostHogTracingConfig, description="AI span tracing to your PostHog")

    @model_validator(mode="after")
    def validate_user_id(self) -> Self:
        if self.mode.is_identified and not self.user_id:
            msg = "user_id is required when mode is 'identified'"
            raise ValueError(msg)
        return self


class LangfuseConfig(BaseModel):
    """Langfuse integration configuration."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = Field(default=False, description="Enable Langfuse OTLP exporter")
    base_url: str | None = Field(default=None, description="Override for self-hosted Langfuse (defaults to cloud)")


class OtlpExporterConfig(BaseModel):
    """Configuration for an additional OTLP exporter."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(description="Identifier for logging")
    endpoint: str = Field(description="OTLP endpoint URL")
    headers: dict[str, str] = Field(default_factory=dict, description="Headers for OTLP export")


class TelemetryConfig(ConfigModel):
    """Main telemetry configuration with nested sections."""

    posthog: PostHogConfig = Field(description="PostHog configuration")
    langfuse: LangfuseConfig = Field(default_factory=LangfuseConfig, description="Langfuse configuration")
    otlp: list[OtlpExporterConfig] = Field(default_factory=empty_list_factory_of(OtlpExporterConfig), description="Additional OTLP exporters")


class TelemetryRedactionConfig(BaseModel):
    """Configuration for what telemetry data to redact at export time.

    This config is passed to span exporters so they can apply appropriate
    redaction rules before sending telemetry data to their destinations.
    """

    model_config = ConfigDict(frozen=True)

    redact_content: bool = False
    redact_pipe_codes: bool = False
    redact_output_class_names: bool = False
    content_max_length: int | None = None

    @classmethod
    def make_from_posthog_config(cls, posthog_config: PostHogConfig) -> Self:
        """Create from PostHogConfig (inverse of capture settings).

        Args:
            posthog_config: The user's PostHog configuration.

        Returns:
            A TelemetryRedactionConfig with redaction settings derived from the config.
        """
        return cls(
            redact_content=not posthog_config.tracing.capture.content,
            redact_pipe_codes=not posthog_config.tracing.capture.pipe_codes,
            redact_output_class_names=not posthog_config.tracing.capture.output_class_names,
            content_max_length=posthog_config.tracing.capture.content_max_length,
        )

    @classmethod
    def pipelex_config(cls) -> Self:
        """Create config for Pipelex telemetry (redact everything).

        Pipelex internal telemetry always redacts sensitive data like content,
        pipe codes, and output class names to protect user privacy.

        Returns:
            A TelemetryRedactionConfig with all redaction options enabled.
        """
        return cls(redact_content=True, redact_pipe_codes=True, redact_output_class_names=True)

    @classmethod
    def no_redaction(cls) -> Self:
        """Create config with no redaction (pass-through).

        Use this when you want to explicitly indicate no redaction should occur,
        rather than relying on default values.

        Returns:
            A TelemetryRedactionConfig with all redaction options disabled.
        """
        return cls()


def load_telemetry_config(path: str, secrets_provider: SecretsProviderAbstract) -> TelemetryConfig:
    """Load telemetry configuration from a TOML file with variable substitution.

    Supports variable placeholders in string values:
    - ${VAR_NAME} -> use secrets provider by default
    - ${env:ENV_VAR_NAME} -> force use environment variable
    - ${secret:SECRET_NAME} -> force use secrets provider
    - ${env:ENV_VAR|secret:SECRET} -> try env first, then secret as fallback

    Args:
        path: Path to the telemetry.toml configuration file.
        secrets_provider: Provider for resolving secret/env variable placeholders.

    Returns:
        Validated TelemetryConfig instance.

    Raises:
        TelemetryConfigValidationError: If configuration is invalid or variable substitution fails.
    """
    telemetry_config_toml_raw = load_toml_from_path(path=path)

    # Apply variable substitution to all string values
    substitute_vars_with_provider = partial(substitute_vars, secrets_provider=secrets_provider)
    try:
        telemetry_config_toml = apply_to_strings_recursive(telemetry_config_toml_raw, substitute_vars_with_provider)
    except (VarNotFoundError, UnknownVarPrefixError, VarFallbackPatternError) as exc:
        msg = f"Variable substitution failed in telemetry configuration '{path}': {exc}"
        raise TelemetryConfigValidationError(msg) from exc

    try:
        telemetry_config = TelemetryConfig.model_validate(telemetry_config_toml)
    except ValidationError as exc:
        validation_error_msg = format_pydantic_validation_error(exc)
        msg = f"Invalid telemetry configuration in '{path}':\n{validation_error_msg}"
        raise TelemetryConfigValidationError(msg) from exc
    return telemetry_config
