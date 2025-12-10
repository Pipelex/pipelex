import copy
import warnings
from typing import Any, cast

from pipelex.cogt.model_backends.model_spec_factory import BackendModelSpecs
from pipelex.system.pipelex_service.exceptions import GatewayConfigMergeError, GatewayOverrideWarning
from pipelex.tools.log.log import log

# Keys that can be overridden locally
ALLOWED_OVERRIDE_KEYS = frozenset({"sdk", "structure_method"})


class GatewayConfigMerger:
    """Merges remote gateway configuration with local overrides.

    Only allows overriding specific keys (sdk, structure_method).
    Logs warnings when overrides are applied or when disallowed keys are found.
    """

    @classmethod
    def merge(
        cls,
        gateway_model_specs: BackendModelSpecs,
        local_overrides: BackendModelSpecs,
    ) -> dict[str, Any]:
        """Merge remote config with local overrides.

        Args:
            gateway_model_specs: Model specs from Pipelex Gateway.
            local_overrides: Local overrides from local pipelex_gateway.toml.

        Returns:
            Merged configuration with allowed overrides applied.
        """
        result: dict[str, Any] = copy.deepcopy(gateway_model_specs)

        # Warn if defaults section is present (not allowed for local overrides)
        if "defaults" in local_overrides:
            log.warning("[GatewayConfigMerger] Local 'defaults' section ignored. Overrides are only allowed per-model, not via defaults.")

        # Handle per-model overrides only
        for model_name, local_model_config in local_overrides.items():
            if model_name == "defaults":
                continue  # Skip defaults section (already warned above)

            if not isinstance(local_model_config, dict):
                msg = f"Local override for model '{model_name}' must be a dictionary, got {type(local_model_config).__name__}"
                raise GatewayConfigMergeError(msg)

            if model_name not in result:
                log.warning(f"[GatewayConfigMerger] Local override for model '{model_name}' ignored: model not found in remote configuration")
                continue

            remote_model = result[model_name]
            if not isinstance(remote_model, dict):
                msg = f"Remote config for model '{model_name}' must be a dictionary, got {type(remote_model).__name__}"
                raise GatewayConfigMergeError(msg)

            cls._apply_overrides_to_model(
                model_name=model_name,
                gateway_model_specs=cast("dict[str, Any]", remote_model),
                local_model_config=cast("dict[str, Any]", local_model_config),
            )

        return result

    @classmethod
    def _apply_overrides_to_model(
        cls,
        model_name: str,
        gateway_model_specs: BackendModelSpecs,
        local_model_config: BackendModelSpecs,
    ) -> None:
        """Apply local overrides to a single model configuration.

        Args:
            model_name: Name of the model being configured.
            gateway_model_specs: Remote model configuration to apply overrides to.
            local_model_config: Local overrides for the model.
        """
        applied_overrides: list[str] = []
        ignored_keys: list[str] = []

        for key, value in local_model_config.items():
            if key in ALLOWED_OVERRIDE_KEYS:
                old_value = gateway_model_specs.get(key)
                if old_value != value:
                    gateway_model_specs[key] = value
                    applied_overrides.append(f"{key}: {old_value!r} -> {value!r}")
            else:
                ignored_keys.append(key)

        if applied_overrides:
            override_details = ", ".join(applied_overrides)
            warning_msg = f"[GatewayConfigMerger] Local overrides applied for '{model_name}': {override_details}. This may affect behavior."
            log.warning(warning_msg)
            warnings.warn(warning_msg, GatewayOverrideWarning, stacklevel=3)

        if ignored_keys:
            log.warning(
                f"[GatewayConfigMerger] Ignored non-overridable keys for '{model_name}': "
                f"{ignored_keys}. Only {list(ALLOWED_OVERRIDE_KEYS)} can be overridden."
            )
