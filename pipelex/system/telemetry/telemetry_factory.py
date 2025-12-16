from pipelex import log
from pipelex.system.environment import is_env_var_truthy
from pipelex.system.pipelex_service.exceptions import (
    GatewayApiKeyMissingError,
    GatewayDoNotTrackConflictError,
    GatewayTelemetryManagerInjectedError,
)
from pipelex.system.pipelex_service.pipelex_details import PipelexDetails
from pipelex.system.pipelex_service.remote_config import RemoteConfig
from pipelex.system.runtime import IntegrationMode
from pipelex.system.telemetry.otel_constants import OTelConstants
from pipelex.system.telemetry.telemetry_config import PostHogMode, TelemetryConfig, load_telemetry_config
from pipelex.system.telemetry.telemetry_manager import TelemetryManager
from pipelex.system.telemetry.telemetry_manager_abstract import (
    TelemetryManagerAbstract,
    TelemetryManagerNoOp,
)
from pipelex.tools.secrets.secrets_errors import SecretNotFoundError
from pipelex.tools.secrets.secrets_provider_abstract import SecretsProviderAbstract


class TelemetryFactory:
    @classmethod
    def make_telemetry_manager(
        cls,
        secrets_provider: SecretsProviderAbstract,
        integration_mode: IntegrationMode,
        remote_config: RemoteConfig | None,
        is_pipelex_telemetry_enabled: bool = False,
        telemetry_config: TelemetryConfig | None = None,
        injected_telemetry_manager: TelemetryManagerAbstract | None = None,
    ) -> TelemetryManagerAbstract:
        gateway_api_key: str | None = None
        if is_pipelex_telemetry_enabled:
            # Cannot inject custom TelemetryManager when gateway is enabled
            if injected_telemetry_manager is not None:
                raise GatewayTelemetryManagerInjectedError

            # Get gateway API key for telemetry distinct_id
            try:
                gateway_api_key = secrets_provider.get_required_secret(PipelexDetails.PIPELEX_GATEWAY_API_KEY_VAR)
            except SecretNotFoundError as exc:
                raise GatewayApiKeyMissingError from exc

        # Always load telemetry config first to determine allowed modes
        if not telemetry_config:
            telemetry_config = load_telemetry_config(secrets_provider=secrets_provider)

        allows_custom_telemetry = telemetry_config.is_custom_telemetry_allowed_for_mode(integration_mode)

        chosen_telemetry_manager: TelemetryManagerAbstract
        if allows_custom_telemetry or is_pipelex_telemetry_enabled:
            # Always respect DO_NOT_TRACK env var
            if is_env_var_truthy(OTelConstants.DO_NOT_TRACK_ENV_VAR_KEY):
                if is_pipelex_telemetry_enabled:
                    # Gateway requires telemetry but DNT is set - we respect DNT
                    raise GatewayDoNotTrackConflictError(dnt_env_var=OTelConstants.DO_NOT_TRACK_ENV_VAR_KEY)
                chosen_telemetry_manager = TelemetryManagerNoOp()
                log.debug(f"Telemetry is disabled by env var '{OTelConstants.DO_NOT_TRACK_ENV_VAR_KEY}'")
                return chosen_telemetry_manager

            match telemetry_config.custom_posthog.mode:
                case PostHogMode.OFF:
                    if is_pipelex_telemetry_enabled:
                        # Gateway requires telemetry - create manager with only Pipelex telemetry
                        chosen_telemetry_manager = TelemetryManager(
                            telemetry_config=telemetry_config,
                            remote_config=remote_config,
                            pipelex_telemetry_enabled=True,
                            gateway_api_key=gateway_api_key,
                        )
                        log.debug("Custom telemetry is off, but Pipelex Gateway telemetry is enabled")
                    else:
                        chosen_telemetry_manager = TelemetryManagerNoOp()
                        log.debug("Telemetry is disabled because posthog.mode is set to 'off'")
                case PostHogMode.ANONYMOUS | PostHogMode.IDENTIFIED:
                    chosen_telemetry_manager = injected_telemetry_manager or TelemetryManager(
                        telemetry_config=telemetry_config,
                        remote_config=remote_config,
                        pipelex_telemetry_enabled=is_pipelex_telemetry_enabled,
                        gateway_api_key=gateway_api_key,
                    )
        else:
            chosen_telemetry_manager = TelemetryManagerNoOp()
            log.verbose(f"Telemetry is disabled because the integration mode '{integration_mode}' does not allow it")

        return chosen_telemetry_manager
