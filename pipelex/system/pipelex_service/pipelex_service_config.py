import os
from typing import Any, cast

from pydantic import ValidationError

from pipelex.cogt.model_backends.backend import PipelexBackend
from pipelex.system.configuration.config_model import ConfigModel
from pipelex.system.configuration.configs import ConfigPaths
from pipelex.system.pipelex_service.exceptions import PipelexServiceConfigValidationError
from pipelex.system.pipelex_service.pipelex_service_agreement import (
    PIPELEX_SERVICE_CONFIG_FILE_NAME,
    PipelexServiceAgreement,
)
from pipelex.tools.misc.toml_utils import load_toml_from_path, load_toml_from_path_if_exists
from pipelex.tools.typing.pydantic_utils import format_pydantic_validation_error


class PipelexServiceConfig(ConfigModel):
    agreement: PipelexServiceAgreement


def load_pipelex_service_config_if_exists(config_dir: str) -> PipelexServiceConfig | None:
    """Load Pipelex service configuration if the file exists.

    Args:
        config_dir: Path to the .pipelex configuration directory.

    Returns:
        PipelexServiceConfig instance or None if file doesn't exist.
    """
    config_path = os.path.join(config_dir, PIPELEX_SERVICE_CONFIG_FILE_NAME)
    try:
        config_toml = load_toml_from_path(path=config_path)
        return PipelexServiceConfig.model_validate(config_toml)
    except FileNotFoundError:
        return None
    except ValidationError as exc:
        validation_error_msg = format_pydantic_validation_error(exc)
        msg = f"Invalid Pipelex service configuration: {validation_error_msg}"
        raise PipelexServiceConfigValidationError(msg) from exc


def is_pipelex_gateway_enabled() -> bool:
    """Check if pipelex_gateway is enabled in the backends configuration.

    This reads the backends.toml file directly without loading the full backend library.

    Returns:
        True if pipelex_gateway is enabled, False otherwise.
    """
    backends_toml = load_toml_from_path_if_exists(ConfigPaths.BACKENDS_FILE_PATH)
    if backends_toml is None:
        return False

    gateway_config = backends_toml.get(PipelexBackend.GATEWAY)
    if gateway_config is None or not isinstance(gateway_config, dict):
        return False

    gateway_config_dict = cast("dict[str, Any]", gateway_config)
    enabled_value = gateway_config_dict.get("enabled", True)
    return enabled_value is True
