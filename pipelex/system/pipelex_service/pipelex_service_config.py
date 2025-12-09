"""Configuration model for Pipelex managed services."""

import os

from pydantic import Field, ValidationError

from pipelex.system.configuration.config_model import ConfigModel
from pipelex.tools.misc.toml_utils import load_toml_from_path
from pipelex.tools.typing.pydantic_utils import format_pydantic_validation_error

PIPELEX_SERVICE_CONFIG_FILE_NAME = "pipelex_service.toml"


class GatewayConfig(ConfigModel):
    """Configuration for Pipelex Gateway service."""

    terms_accepted: bool = Field(
        default=False,
        description="Whether the user has accepted Pipelex Gateway terms of service",
    )


class PipelexServiceConfig(ConfigModel):
    """Configuration for Pipelex managed services."""

    gateway: GatewayConfig = Field(default_factory=GatewayConfig)


# TODO: RC - move to exceptions.py
class PipelexServiceConfigValidationError(Exception):
    """Raised when pipelex_service.toml validation fails."""


def load_pipelex_service_config(config_dir: str) -> PipelexServiceConfig:
    """Load Pipelex service configuration from pipelex_service.toml.

    Args:
        config_dir: Path to the .pipelex configuration directory.

    Returns:
        PipelexServiceConfig instance.

    Raises:
        PipelexServiceConfigValidationError: If config validation fails.
        FileNotFoundError: If config file doesn't exist.
    """
    config_path = os.path.join(config_dir, PIPELEX_SERVICE_CONFIG_FILE_NAME)
    config_toml = load_toml_from_path(path=config_path)
    try:
        return PipelexServiceConfig.model_validate(config_toml)
    except ValidationError as exc:
        validation_error_msg = format_pydantic_validation_error(exc)
        msg = f"Invalid Pipelex service configuration: {validation_error_msg}"
        raise PipelexServiceConfigValidationError(msg) from exc


# TODO: RC - why not raise?
def load_pipelex_service_config_if_exists(config_dir: str) -> PipelexServiceConfig | None:
    """Load Pipelex service configuration if the file exists.

    Args:
        config_dir: Path to the .pipelex configuration directory.

    Returns:
        PipelexServiceConfig instance or None if file doesn't exist.
    """
    config_path = os.path.join(config_dir, PIPELEX_SERVICE_CONFIG_FILE_NAME)
    if not os.path.exists(config_path):
        return None
    return load_pipelex_service_config(config_dir=config_dir)
