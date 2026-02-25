import os
from functools import partial

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from pipelex.system.configuration.config_loader import config_manager
from pipelex.system.configuration.config_model import ConfigModel
from pipelex.system.telemetry.exceptions import TelemetryConfigValidationError
from pipelex.tools.misc.dict_utils import apply_to_strings_recursive
from pipelex.tools.misc.toml_utils import load_toml_from_path_and_merge_with_overrides
from pipelex.tools.secrets.secrets_provider_abstract import SecretsProviderAbstract
from pipelex.tools.secrets.secrets_utils import (
    UnknownVarPrefixError,
    substitute_vars,
)
from pipelex.tools.typing.pydantic_utils import empty_list_factory_of, format_pydantic_validation_error
from pipelex.types import Self, StrEnum

TELEMETRY_CONFIG_FILE_NAME = "telemetry.toml"
TELEMETRY_CONFIG_OVERRIDE_FILE_NAME = "telemetry_override.toml"


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
    endpoint: str = Field(default="https://us.i.posthog.com", description="PostHog endpoint URL")
    api_key: str | None = Field(default=None, description="PostHog project API key")
    geoip: bool = Field(default=True, description="Enable GeoIP lookup")
    debug: bool = Field(default=False, description="Enable PostHog debug mode")
    redact_properties: list[str] | None = Field(default_factory=list, description="Event properties to redact")
    tracing: PostHogTracingConfig = Field(default_factory=PostHogTracingConfig, description="AI span tracing to your PostHog")

    @model_validator(mode="after")
    def validate_user_id(self) -> Self:
        if self.mode.is_identified and not self.user_id:
            msg = "user_id is required when mode is 'identified'"
            raise ValueError(msg)
        return self


class PortkeyConfig(BaseModel):
    """Portkey SDK configuration for logging and tracing."""

    model_config = ConfigDict(extra="forbid")
    force_debug_enabled: bool = Field(default=False, description="Force-enable Portkey SDK debug mode regardless of backend setting")
    force_tracing_enabled: bool = Field(default=False, description="Force-enable Portkey SDK tracing regardless of backend setting")


class LangfuseConfig(BaseModel):
    """Langfuse integration configuration."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = Field(default=False, description="Enable Langfuse OTLP exporter")
    endpoint: str | None = Field(default=None, description="Override for self-hosted Langfuse (defaults to cloud)")
    public_key: str | None = Field(default=None, description="Langfuse public key")
    secret_key: str | None = Field(default=None, description="Langfuse secret key")


class OtlpExporterConfig(BaseModel):
    """Configuration for an additional OTLP exporter."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(description="Identifier for logging")
    endpoint: str = Field(description="OTLP endpoint URL")
    headers: dict[str, str] = Field(default_factory=dict, description="Headers for OTLP export")


class PipelexGatewayTelemetryConfig(BaseModel):
    """Pipelex Gateway telemetry configuration for internal maintainer use.

    NOTE TO CONTRIBUTORS: This config class exists to support personal overrides used by
    maintainers for improved observability while debugging and demoing Pipelex. It is NOT
    included in the base `.pipelex/telemetry.toml` installed via `pipelex init telemetry`.

    Maintainers can enable this by adding a `[pipelex_gateway]` section to their personal
    `telemetry_override.toml` file, which is loaded after and merged with the base config.

    IMPORTANT DISTINCTIONS:

    - **This config** (`pipelex_gateway`): Internal maintainer tooling, applied via personal overrides
    - **Custom telemetry** (`custom_posthog`, `langfuse`, `otlp`): User-controlled destinations
    - **Gateway telemetry** (automatic): When using Pipelex Gateway as inference backend,
      identified telemetry is automatically enabled (tied to Gateway API key, hashed for security)

    Using Pipelex Gateway is entirely optional—you can BYOK (Bring Your Own Keys) with direct
    provider backends (OpenAI, Anthropic, Azure, Bedrock, etc.) instead.

    See Also:
        - docs/home/5-setup/telemetry.md: Overview of telemetry streams
        - docs/home/7-configuration/config-practical/telemetry-config.md: Custom telemetry configuration
    """

    model_config = ConfigDict(extra="forbid")

    posthog: PostHogConfig = Field(description="Pipelex Gateway PostHog configuration")
    portkey: PortkeyConfig = Field(description="Pipelex Gateway Portkey SDK configuration")


class TelemetryConfig(ConfigModel):
    """Main telemetry configuration with nested sections."""

    custom_posthog: PostHogConfig = Field(default_factory=PostHogConfig, description="PostHog configuration")
    custom_portkey: PortkeyConfig = Field(default_factory=PortkeyConfig, description="Custom Portkey SDK configuration")
    langfuse: LangfuseConfig = Field(default_factory=LangfuseConfig, description="Langfuse configuration")
    otlp: list[OtlpExporterConfig] = Field(default_factory=empty_list_factory_of(OtlpExporterConfig), description="Additional OTLP exporters")
    telemetry_allowed_modes: dict[str, bool] = Field(
        default_factory=dict,
        description="Which integration modes allow custom telemetry (e.g. cli=true, pytest=false)",
    )
    pipelex_gateway: PipelexGatewayTelemetryConfig | None = Field(default=None, description="Pipelex Gateway telemetry configuration")

    def is_custom_telemetry_allowed_for_mode(self, mode: str) -> bool:
        """Check if custom telemetry is allowed for the given integration mode.

        Args:
            mode: The integration mode string to check.

        Returns:
            True if custom telemetry is allowed for this mode, False otherwise.
        """
        return self.telemetry_allowed_modes.get(mode, False)

    @property
    def redact_properties(self) -> list[str]:
        """Get the list of properties to redact."""
        return self.custom_posthog.redact_properties or []


class TelemetryRedactionConfig(BaseModel):
    """Configuration for what telemetry data to redact at export time.

    This config is passed to span exporters so they can apply appropriate
    redaction rules before sending telemetry data to their destinations.
    """

    model_config = ConfigDict(frozen=True)

    redact_content: bool
    redact_pipe_codes: bool
    redact_output_class_names: bool
    content_max_length: int | None

    @classmethod
    def make_from_posthog_config(cls, posthog_config: PostHogConfig | None) -> Self:
        """Create from PostHogConfig (inverse of capture settings).

        Args:
            posthog_config: The user's PostHog configuration (or None if no configuration is provided).

        Returns:
            A TelemetryRedactionConfig with redaction settings derived from the config.
        """
        if posthog_config:
            return cls(
                redact_content=not posthog_config.tracing.capture.content,
                redact_pipe_codes=not posthog_config.tracing.capture.pipe_codes,
                redact_output_class_names=not posthog_config.tracing.capture.output_class_names,
                content_max_length=posthog_config.tracing.capture.content_max_length,
            )
        else:
            return cls(
                redact_content=True,
                redact_pipe_codes=True,
                redact_output_class_names=True,
                content_max_length=None,
            )


def load_telemetry_config(secrets_provider: SecretsProviderAbstract) -> TelemetryConfig:
    """Load telemetry configuration from a TOML file with variable substitution.

    Supports variable placeholders in string values:
    - ${VAR_NAME} -> use secrets provider by default
    - ${env:ENV_VAR_NAME} -> force use environment variable
    - ${secret:SECRET_NAME} -> force use secrets provider
    - ${env:ENV_VAR|secret:SECRET} -> try env first, then secret as fallback

    Args:
        secrets_provider: Provider for resolving secret/env variable placeholders.

    Returns:
        Validated TelemetryConfig instance.

    Raises:
        TelemetryConfigValidationError: If configuration is invalid or variable substitution fails.
    """
    telemetry_config_paths: list[str] = []
    telemetry_config_paths.append(os.path.join(config_manager.pipelex_config_dir, TELEMETRY_CONFIG_FILE_NAME))
    telemetry_config_paths.append(os.path.join(config_manager.pipelex_config_dir, TELEMETRY_CONFIG_OVERRIDE_FILE_NAME))
    telemetry_config_toml_raw = load_toml_from_path_and_merge_with_overrides(paths=telemetry_config_paths)

    # Apply variable substitution to all string values (keep placeholders for missing vars)
    substitute_vars_with_provider = partial(substitute_vars, secrets_provider=secrets_provider, raise_on_missing_var=False)
    try:
        telemetry_config_toml = apply_to_strings_recursive(telemetry_config_toml_raw, substitute_vars_with_provider)
    except UnknownVarPrefixError as exc:
        paths_str = "\n".join(telemetry_config_paths)
        msg = f"Variable substitution failed in telemetry configuration based on '{paths_str}': {exc}"
        raise TelemetryConfigValidationError(msg) from exc

    try:
        telemetry_config = TelemetryConfig.model_validate(telemetry_config_toml)
    except ValidationError as exc:
        validation_error_msg = format_pydantic_validation_error(exc)
        paths_str = "\n".join(telemetry_config_paths)
        msg = f"Invalid telemetry configuration in '{paths_str}':\n{validation_error_msg}"
        raise TelemetryConfigValidationError(msg) from exc
    return telemetry_config
