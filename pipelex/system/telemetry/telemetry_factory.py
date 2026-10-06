from pipelex import log
from pipelex.system.environment import is_env_var_truthy
from pipelex.system.runtime import IntegrationMode
from pipelex.system.telemetry.otel_constants import OTelConstants
from pipelex.system.telemetry.telemetry_config import PostHogMode, TelemetryConfig
from pipelex.system.telemetry.telemetry_loader import load_telemetry_config
from pipelex.system.telemetry.telemetry_manager_abstract import (
    TelemetryManagerAbstract,
    TelemetryManagerNoOp,
)
from pipelex.tools.secrets.secrets_provider_abstract import SecretsProviderAbstract


class TelemetryFactory:
    @classmethod
    def make_telemetry_manager(
        cls,
        *,
        secrets_provider: SecretsProviderAbstract,
        integration_mode: IntegrationMode,
        telemetry_config: TelemetryConfig | None = None,
        injected_telemetry_manager: TelemetryManagerAbstract | None = None,
    ) -> TelemetryManagerAbstract:
        """The telemetry manager for this boot: the user's own opt-in telemetry, or a no-op.

        There is exactly one telemetry stream, and it is the user's: what ``telemetry.toml`` configures
        under ``[custom_posthog]``, ``[langfuse]`` and ``[[otlp]]``. Nothing here phones home to
        Pipelex.
        """
        # Always load telemetry config first to determine allowed modes
        if not telemetry_config:
            telemetry_config = load_telemetry_config(secrets_provider=secrets_provider)

        if not telemetry_config.is_custom_telemetry_allowed_for_mode(integration_mode):
            log.verbose(f"Telemetry is disabled because the integration mode '{integration_mode}' does not allow it")
            return TelemetryManagerNoOp()

        # Always respect DO_NOT_TRACK env var
        if is_env_var_truthy(OTelConstants.DO_NOT_TRACK_ENV_VAR_KEY):
            log.debug(f"Telemetry is disabled by env var '{OTelConstants.DO_NOT_TRACK_ENV_VAR_KEY}'")
            return TelemetryManagerNoOp()

        # Deferred import: avoid pulling heavy SDK at module-load time
        from pipelex.system.telemetry.telemetry_manager import TelemetryManager  # ruff: ignore[import-outside-top-level]

        chosen_telemetry_manager: TelemetryManagerAbstract
        match telemetry_config.custom_posthog.mode:
            case PostHogMode.OFF:
                chosen_telemetry_manager = TelemetryManagerNoOp()
                log.debug("Telemetry is disabled because posthog.mode is set to 'off'")
            case PostHogMode.ANONYMOUS | PostHogMode.IDENTIFIED:
                chosen_telemetry_manager = injected_telemetry_manager or TelemetryManager(telemetry_config=telemetry_config)
        return chosen_telemetry_manager
