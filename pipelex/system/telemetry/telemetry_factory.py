from pipelex import log
from pipelex.system.environment import get_optional_env, is_env_var_truthy
from pipelex.system.runtime import IntegrationMode
from pipelex.system.telemetry.exceptions import TelemetryConfigValidationError
from pipelex.system.telemetry.otel_constants import OTelConstants
from pipelex.system.telemetry.telemetry_config import TELEMETRY_CONFIG_FILE_NAME, PostHogMode, TelemetryConfig
from pipelex.system.telemetry.telemetry_loader import TELEMETRY_SURFACE, load_telemetry_config
from pipelex.system.telemetry.telemetry_manager_abstract import (
    TelemetryManagerAbstract,
    TelemetryManagerNoOp,
)
from pipelex.tools.secrets.secrets_provider_abstract import SecretsProviderAbstract

# The values `PIPELEX_JOIN_HOST_TRACE` may hold, compared case-insensitively; an empty variable counts as unset.
_JOIN_HOST_TRACE_ENV_VALUES: dict[str, bool] = {"true": True, "1": True, "false": False, "0": False}

JOIN_HOST_TRACE_SETTING = "join_host_trace"


class TelemetryFactory:
    @classmethod
    def make_telemetry_manager(
        cls,
        *,
        secrets_provider: SecretsProviderAbstract,
        integration_mode: IntegrationMode,
        telemetry_config: TelemetryConfig | None = None,
        injected_telemetry_manager: TelemetryManagerAbstract | None = None,
        join_host_trace: bool | None = None,
    ) -> TelemetryManagerAbstract:
        """The telemetry manager for this boot: the user's own opt-in telemetry, or a no-op.

        There is exactly one telemetry stream, and it is the user's: what ``telemetry.toml`` configures
        under ``[custom_posthog]``, ``[langfuse]`` and ``[[otlp]]``. Nothing here phones home to
        Pipelex.

        ``join_host_trace`` is the in-code form of the switch that lets Pipelex's spans join the host's
        trace; ``None`` leaves it to ``PIPELEX_JOIN_HOST_TRACE``, then to ``telemetry.toml``. With the switch
        on, the boot is refused unless a destination of the file receives Pipelex's spans, since the host's
        own spans made children of a Pipelex span would otherwise reach the host's backend with a parent
        nobody has. With telemetry off as a whole, by its integration mode or ``DO_NOT_TRACK``, Pipelex
        starts no span, so there is nothing to orphan and the switch is inert.

        An injected manager states the switch for itself, through its own ``join_host_trace``, which is what
        the runtime reads: the environment and the file are not consulted for it, its destinations are its own
        to check, and an in-code ``join_host_trace`` that disagrees with it is refused.

        Raises:
            TelemetryConfigValidationError: The switch is on with no span destination, ``PIPELEX_JOIN_HOST_TRACE``
                is unreadable, or an in-code ``join_host_trace`` contradicts the injected manager's.
        """
        # Always load telemetry config first to determine allowed modes
        if not telemetry_config:
            telemetry_config = load_telemetry_config(secrets_provider=secrets_provider)

        is_join_host_trace: bool
        if injected_telemetry_manager is not None:
            is_join_host_trace = injected_telemetry_manager.join_host_trace
            if join_host_trace is not None and join_host_trace != is_join_host_trace:
                msg = (
                    f"join_host_trace={join_host_trace} was passed to the boot, but the injected telemetry manager states "
                    f"join_host_trace={is_join_host_trace}, which is what the runtime reads: make them agree, or pass neither"
                )
                raise TelemetryConfigValidationError(msg, surface=TELEMETRY_SURFACE, file=None, setting=JOIN_HOST_TRACE_SETTING)
        else:
            is_join_host_trace = cls.resolve_join_host_trace(telemetry_config=telemetry_config, join_host_trace=join_host_trace)

        if not telemetry_config.is_custom_telemetry_allowed_for_mode(integration_mode):
            log.debug(f"Telemetry is disabled because the integration mode '{integration_mode}' does not allow it")
            if is_join_host_trace:
                log.debug("The join_host_trace switch is inert, since telemetry is off and Pipelex starts no span")
            return TelemetryManagerNoOp()

        # Always respect DO_NOT_TRACK env var
        if is_env_var_truthy(OTelConstants.DO_NOT_TRACK_ENV_VAR_KEY):
            log.debug(f"Telemetry is disabled by env var '{OTelConstants.DO_NOT_TRACK_ENV_VAR_KEY}'")
            if is_join_host_trace:
                log.debug("The join_host_trace switch is inert, since telemetry is off and Pipelex starts no span")
            return TelemetryManagerNoOp()

        # An injected manager's destinations are its own, so the file's are checked only for the manager made here.
        if is_join_host_trace and injected_telemetry_manager is None:
            cls.check_join_host_trace_destination(telemetry_config=telemetry_config)

        # Deferred import: avoid pulling heavy SDK at module-load time
        from pipelex.system.telemetry.telemetry_manager import TelemetryManager  # ruff: ignore[import-outside-top-level]

        chosen_telemetry_manager: TelemetryManagerAbstract
        match telemetry_config.custom_posthog.mode:
            case PostHogMode.OFF:
                chosen_telemetry_manager = TelemetryManagerNoOp()
                log.debug("Telemetry is disabled because posthog.mode is set to 'off'")
            case PostHogMode.ANONYMOUS | PostHogMode.IDENTIFIED:
                chosen_telemetry_manager = injected_telemetry_manager or TelemetryManager(
                    telemetry_config=telemetry_config,
                    join_host_trace=is_join_host_trace,
                )
        return chosen_telemetry_manager

    @classmethod
    def resolve_join_host_trace(cls, *, telemetry_config: TelemetryConfig, join_host_trace: bool | None) -> bool:
        """Whether Pipelex's spans join the host's trace: the in-code value, else ``PIPELEX_JOIN_HOST_TRACE``, else the file.

        An empty or whitespace-only variable counts as unset.

        Raises:
            TelemetryConfigValidationError: The environment variable holds something other than ``true``, ``false``,
                ``1`` or ``0``.
        """
        if join_host_trace is not None:
            return join_host_trace
        env_value = (get_optional_env(OTelConstants.JOIN_HOST_TRACE_ENV_VAR_KEY) or "").strip()
        if env_value:
            parsed = _JOIN_HOST_TRACE_ENV_VALUES.get(env_value.lower())
            if parsed is None:
                msg = (
                    f"The environment variable '{OTelConstants.JOIN_HOST_TRACE_ENV_VAR_KEY}' must be 'true', 'false', '1' or '0' "
                    "to state whether Pipelex's spans join the host's trace"
                )
                # No file is at fault: the variable is the setting to correct.
                raise TelemetryConfigValidationError(msg, surface=TELEMETRY_SURFACE, file=None, setting=OTelConstants.JOIN_HOST_TRACE_ENV_VAR_KEY)
            return parsed
        return telemetry_config.join_host_trace

    @classmethod
    def check_join_host_trace_destination(cls, *, telemetry_config: TelemetryConfig) -> None:
        """Refuse the switch when no destination the operator owns receives Pipelex's spans.

        Raises:
            TelemetryConfigValidationError: No destination of the telemetry configuration receives Pipelex's spans.
        """
        if telemetry_config.operator_span_destinations():
            return
        msg = (
            "join_host_trace is on, but no destination of yours receives Pipelex's spans, so the host's spans made their "
            "children would reach your backend with a parent nobody has. Turn on [custom_posthog] (mode 'anonymous' or "
            "'identified') with [custom_posthog.tracing] enabled, which also feeds any [[otlp]] exporter and [langfuse], "
            "or turn join_host_trace off."
        )
        raise TelemetryConfigValidationError(msg, surface=TELEMETRY_SURFACE, file=TELEMETRY_CONFIG_FILE_NAME, setting=JOIN_HOST_TRACE_SETTING)
