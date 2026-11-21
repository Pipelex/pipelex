"""The telemetry configuration models — what a `telemetry.toml` parses into.

Models only. `telemetry_loader.py` beside this reads the files and returns a `TelemetryConfig`,
and it is a module of its own because its failure path reaches the migration registry, which
imports every configuration model including these. See its docstring for the whole account.
"""

from enum import StrEnum
from typing import Any, Self, cast

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator, model_validator

from pipelex.system.configuration.config_model import ConfigModel
from pipelex.tools.typing.pydantic_utils import empty_list_factory_of

# The shortest `pipe_id_key` accepted: 32 characters, the length of 16 random bytes in hex, so the key cannot be
# guessed and a guessed pipe code cannot be confirmed against a `pipe_id`.
PIPE_ID_KEY_MIN_LENGTH = 32
# What a `${…}` placeholder the loader could not answer still holds after substitution.
PLACEHOLDER_MARKER = "${"
# The validation context key under which a reader that checks a file's shape, and not this process's secrets, validates
# the file as written: `pipelex doctor` reads the raw TOML with no variable substituted, so a `pipe_id_key` naming its
# secret through a placeholder is a well-formed file there, and only the loader's substituted value is held to the key's
# rules (`telemetry_file_shape_context`).
FILE_SHAPE_CHECK_CONTEXT_KEY = "is_file_shape_check"


def telemetry_file_shape_context() -> dict[str, bool]:
    """The validation context of a check of a telemetry file's shape, which accepts a placeholder as the `pipe_id_key`."""
    return {FILE_SHAPE_CHECK_CONTEXT_KEY: True}


TELEMETRY_CONFIG_FILE_NAME = "telemetry.toml"
TELEMETRY_CONFIG_OVERRIDE_FILE_NAME = "telemetry_override.toml"
# Kit template used when populating a project's `.pipelex/`. Every setting is commented
# out so the project file does not shadow `~/.pipelex/telemetry.toml` or
# `~/.pipelex/telemetry_override.toml` during layered config loading. Kit-internal:
# this filename never appears in `~/.pipelex/` or in a project's `.pipelex/` — it is
# always renamed to `telemetry.toml` on copy.
TELEMETRY_PROJECT_TEMPLATE_FILE_NAME = "telemetry.project.toml"


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


class PostHogEventsConfig(BaseModel):
    """Configuration for the runtime's event-style events to your PostHog.

    The event-style events are the ones `track_event` sends: `pipeline_execute`, `pipeline_complete`, `pipe_run`,
    `pipe_complete`, `pipe_dry_run` and the CLI's events. Switching them off leaves the AI spans and generations
    (`[custom_posthog.tracing]`) and the `$exception` events of the `posthog` error tracker untouched, which is what a
    host whose own events are the record of a run wants.
    """

    model_config = ConfigDict(extra="forbid")

    enabled: bool = Field(default=True, description="Send the runtime's event-style events to your PostHog")


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
    events: PostHogEventsConfig = Field(default_factory=PostHogEventsConfig, description="Event-style events to your PostHog")
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


class TelemetryConfig(ConfigModel):
    """Main telemetry configuration with nested sections."""

    # A refused value is never quoted in the error's text: `pipe_id_key` is a secret, and a key refused as too short
    # would otherwise reach a traceback, and the logs of a server whose boot it stopped, as the error's `input_value`.
    model_config = ConfigDict(hide_input_in_errors=True)

    custom_posthog: PostHogConfig = Field(default_factory=PostHogConfig, description="PostHog configuration")
    custom_portkey: PortkeyConfig = Field(default_factory=PortkeyConfig, description="Custom Portkey SDK configuration")
    langfuse: LangfuseConfig = Field(default_factory=LangfuseConfig, description="Langfuse configuration")
    otlp: list[OtlpExporterConfig] = Field(default_factory=empty_list_factory_of(OtlpExporterConfig), description="Additional OTLP exporters")
    join_host_trace: bool = Field(
        default=False,
        description="Pipelex's spans join the host process's OpenTelemetry trace: a run continues the host's current span, follows its "
        "sampling decision, and its pipe and LLM spans are made current while they run. Refused at boot unless a span destination "
        "of this file receives Pipelex's spans. `PIPELEX_JOIN_HOST_TRACE` and `Pipelex.make(join_host_trace=...)` override it.",
    )
    pipe_id_key: str | None = Field(
        default=None,
        description="The secret key of the stable pipe identifier: with it, every pipe span and every inference span carries "
        "`pipelex.pipe.id`, a keyed digest of the method's identity and the pipe code that stays the same for one pipe across "
        "runs and cannot be turned back into the code; without it, no span carries one. At least "
        f"{PIPE_ID_KEY_MIN_LENGTH} characters. Changing it starts a new series of identifiers.",
    )
    telemetry_allowed_modes: dict[str, bool] = Field(
        default_factory=lambda: {
            "ci": False,
            "cli": True,
            "docker": True,
            "fastapi": True,
            "mcp": True,
            "n8n": True,
            "pytest": False,
            "python": False,
        },
        description="Which integration modes allow custom telemetry (e.g. cli=true, pytest=false). "
        "Defaults live here so a project-level telemetry.toml that omits the section "
        "doesn't silently disable custom telemetry for everyone.",
    )

    @field_validator("pipe_id_key")
    @classmethod
    def _validate_pipe_id_key(cls, value: str | None, info: ValidationInfo) -> str | None:
        """Refuse a key that is no key: a placeholder no variable answered, or one too short to resist guessing.

        The loader keeps a `${…}` placeholder whose variable is missing rather than failing, so without this a deployment
        whose secret did not arrive would digest every pipe code under the placeholder's literal text, a key anyone can
        read in the file. Refusing it makes a missing key a boot failure for a file that states one. A check of the
        file's shape (`telemetry_file_shape_context`) substitutes nothing, so it takes a placeholder as written.
        """
        if value is None:
            return None
        if PLACEHOLDER_MARKER in value:
            validation_context = cast("dict[str, Any] | None", info.context)
            if validation_context is not None and validation_context.get(FILE_SHAPE_CHECK_CONTEXT_KEY) is True:
                return value
            msg = "pipe_id_key holds a placeholder that no variable answered: the secret it names did not reach this process"
            raise ValueError(msg)
        if len(value) < PIPE_ID_KEY_MIN_LENGTH:
            msg = f"pipe_id_key is too short: it must be at least {PIPE_ID_KEY_MIN_LENGTH} characters, such as `openssl rand -hex 32` prints"
            raise ValueError(msg)
        return value

    def is_custom_telemetry_allowed_for_mode(self, mode: str) -> bool:
        """Check if custom telemetry is allowed for the given integration mode.

        Args:
            mode: The integration mode string to check.

        Returns:
            True if custom telemetry is allowed for this mode, False otherwise.
        """
        return self.telemetry_allowed_modes.get(mode, False)

    def operator_span_destinations(self) -> list[str]:
        """The destinations of this file that receive Pipelex's spans, by name, or nothing.

        They all hang off the one tracer, which exists whenever any of them is configured, each independently of the
        others: the operator's PostHog stream when it is on (`anonymous` or `identified`) with its AI span tracing
        enabled, each `[[otlp]]` exporter, and Langfuse when it is enabled.
        """
        destinations: list[str] = []
        if self.custom_posthog.mode.is_enabled and self.custom_posthog.tracing.enabled:
            destinations.append("custom_posthog")
        destinations.extend(f"otlp:{exporter_config.name}" for exporter_config in self.otlp)
        if self.langfuse.enabled:
            destinations.append("langfuse")
        return destinations

    @property
    def is_custom_telemetry_configured(self) -> bool:
        """Whether this file turns on any of the operator's own telemetry: the PostHog stream, or a destination of Pipelex's spans.

        The telemetry manager is made only then; with neither, telemetry is a no-op.
        """
        return self.custom_posthog.mode.is_enabled or bool(self.operator_span_destinations())

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
