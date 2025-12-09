from functools import partial

from pydantic import Field, ValidationError, model_validator
from rich.console import Console, Group
from rich.panel import Panel
from rich.text import Text

from pipelex.system.configuration.config_model import ConfigModel
from pipelex.system.telemetry.exceptions import TelemetryConfigValidationError
from pipelex.tools.misc.dict_utils import apply_to_strings_recursive
from pipelex.tools.misc.toml_utils import load_toml_from_path, load_toml_with_tomlkit, save_toml_to_path
from pipelex.tools.secrets.secrets_provider_abstract import SecretsProviderAbstract
from pipelex.tools.secrets.secrets_utils import (
    UnknownVarPrefixError,
    VarFallbackPatternError,
    VarNotFoundError,
    substitute_vars,
)
from pipelex.tools.typing.pydantic_utils import format_pydantic_validation_error
from pipelex.types import Self, StrEnum

TELEMETRY_CONFIG_FILE_NAME = "telemetry.toml"

# Deprecated Pipelex PostHog API key that used to be in user's telemetry.toml
# Pipelex's key is now hardcoded internally and the user's config should only have their own custom telemetry
_DEPRECATED_PIPELEX_POSTHOG_API_KEY = "phc_HPJnNKpIXh0SxNDYyTAyUtnq9KxNNZJWQszynsWVx4Y"
_PLACEHOLDER_POSTHOG_API_KEY = "phc_YOUR_POSTHOG_PROJECT_API_KEY"


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
    user_id: str | None = Field(default=None, description="Set if telemetry_mode is IDENTIFIED")
    ai_tracing_enabled: bool = Field(description="Enable OpenTelemetry tracing for AI operations")
    capture_content_enabled: bool = Field(description="Controls gen_ai.prompt/completion content capture for OTel")
    capture_content_max_length: int | None = Field(default=None, description="Max length for captured content (None = unlimited)")
    capture_pipe_codes_enabled: bool = Field(description="Controls whether pipe codes appear in span names/attributes")
    capture_output_class_name_enabled: bool = Field(description="Controls whether output class names appear in span names/attributes")
    langfuse_enabled: bool = Field(description="Enable Langfuse OTLP exporter")
    langfuse_base_url: str | None = Field(default=None, description="Override for self-hosted Langfuse (defaults to https://cloud.langfuse.com)")
    otlp_endpoint: str | None = Field(default=None, description="Optional OTLP endpoint for generic tracing")
    otlp_headers: dict[str, str] | None = Field(default=None, description="Optional headers for OTLP export")

    @model_validator(mode="after")
    def validate_user_id(self) -> Self:
        if self.telemetry_mode.is_identified and not self.user_id:
            msg = "user_id is required when telemetry_mode is IDENTIFIED"
            raise ValueError(msg)
        return self


def _build_deprecated_api_key_panel(config_path: str) -> Panel:
    """Build a Rich Panel explaining the deprecated API key migration.

    Args:
        config_path: Path to the config file.

    Returns:
        A Panel containing the migration explanation.
    """
    intro = Text(
        "Your telemetry.toml contained the old Pipelex PostHog API key.\n",
        style="white",
    )

    fixed_header = Text("\n✅ Auto-Fixed\n", style="bold green")
    fixed_text = Text(
        "  • The old API key has been replaced with a placeholder\n  • Your config file has been updated\n",
        style="white",
    )

    what_changed_header = Text("\n🔄 What Changed\n", style="bold cyan")
    what_changed = Text(
        "  • Pipelex telemetry is now configured internally (hardcoded in the library)\n"
        "  • Your telemetry.toml is now only for YOUR CUSTOM telemetry\n",
        style="white",
    )

    action_header = Text("\n⚡ Next Steps\n", style="bold cyan")
    action_text = Text(
        "If you want custom telemetry, update your telemetry.toml:\n"
        "  • Set your own PostHog project_api_key\n"
        "  • Or leave it as-is (custom telemetry will be disabled)\n",
        style="white",
    )

    config_file = Text("\n📁 Config file: ", style="dim")
    config_file.append(config_path, style="cyan")

    content = Group(intro, fixed_header, fixed_text, what_changed_header, what_changed, action_header, action_text, config_file)

    return Panel(
        content,
        title="[bold yellow]⚠️  Telemetry Configuration Migrated[/bold yellow]",
        border_style="yellow",
        padding=(1, 2),
    )


def _migrate_deprecated_pipelex_api_key(config_dict: dict[str, object], config_path: str) -> None:
    """Detect and fix deprecated Pipelex PostHog API key in user's telemetry config.

    Since Pipelex telemetry is now hardcoded internally, users should only configure
    their own custom telemetry. If we detect the old Pipelex API key, we replace it
    with a placeholder, save the file, and warn the user.

    Args:
        config_dict: The raw TOML config dictionary (modified in place).
        config_path: Path to the config file to update.
    """
    project_api_key = config_dict.get("project_api_key")
    if project_api_key == _DEPRECATED_PIPELEX_POSTHOG_API_KEY:
        # Update in-memory dict for the current run
        config_dict["project_api_key"] = _PLACEHOLDER_POSTHOG_API_KEY

        # Persist the fix to the file (using tomlkit to preserve comments)
        toml_doc = load_toml_with_tomlkit(config_path)
        toml_doc["project_api_key"] = _PLACEHOLDER_POSTHOG_API_KEY
        save_toml_to_path(toml_doc, config_path)

        # Display the migration notice
        console = Console(stderr=True)
        console.print()
        console.print(_build_deprecated_api_key_panel(config_path))
        console.print()


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

    # Detect and fix deprecated Pipelex PostHog API key in user's config
    _migrate_deprecated_pipelex_api_key(telemetry_config_toml_raw, path)

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
        msg = f"Invalid telemetry configuration: {validation_error_msg}"
        raise TelemetryConfigValidationError(msg) from exc
    return telemetry_config
