from pathlib import Path
from typing import Any, cast

from pydantic import Field, ValidationError

from pipelex.cogt.model_backends.backend import PipelexBackend
from pipelex.system.configuration.config_loader import config_manager
from pipelex.system.configuration.config_model import ConfigModel
from pipelex.system.configuration.config_surface import strip_reserved_meta
from pipelex.system.pipelex_service.exceptions import PipelexServiceConfigValidationError
from pipelex.system.pipelex_service.pipelex_service_agreement import (
    PIPELEX_SERVICE_CONFIG_FILE_NAME,
    PipelexServiceAgreement,
    PipelexServiceOnboarding,
)
from pipelex.tools.misc.toml_utils import load_toml_from_path, load_toml_from_path_if_exists
from pipelex.tools.typing.pydantic_utils import format_pydantic_validation_error


class PipelexServiceConfig(ConfigModel):
    # A default_factory, not a required field: this is the surface's defaults layer. Every
    # in-scope configuration surface must have one, because it is what makes an additive schema
    # change absorbable and therefore never a migration — see docs/migration-ledger.md.
    agreement: PipelexServiceAgreement = Field(default_factory=PipelexServiceAgreement)
    onboarding: PipelexServiceOnboarding = Field(default_factory=PipelexServiceOnboarding)


def load_pipelex_service_config_if_exists(config_dir: Path) -> PipelexServiceConfig | None:
    """Load Pipelex service configuration if the file exists.

    Args:
        config_dir: Path to the .pipelex configuration directory.

    Returns:
        PipelexServiceConfig instance or None if file doesn't exist.
    """
    config_path = config_dir / PIPELEX_SERVICE_CONFIG_FILE_NAME
    try:
        config_toml = load_toml_from_path(path=config_path)
        strip_reserved_meta(config_dict=config_toml)
        return PipelexServiceConfig.model_validate(config_toml)
    except FileNotFoundError:
        return None
    except ValidationError as exc:
        validation_error_msg = format_pydantic_validation_error(exc)
        msg = f"Invalid Pipelex service configuration: {validation_error_msg}"
        raise PipelexServiceConfigValidationError(msg) from exc


def is_pipelex_gateway_enabled(backends_file_path: Path | None = None) -> bool:
    """Check if pipelex_gateway is enabled in the backends configuration.

    This reads the backends.toml file directly without loading the full backend library.

    Args:
        backends_file_path: Explicit path to the ``backends.toml`` file to inspect. When
            ``None`` (default), uses the layered/project-preferred path from
            ``config_manager.backends_file_path``. Callers that act on a specific target
            directory (e.g. ``pipelex init`` / ``pipelex init --local``) should pass the
            target's ``backends.toml`` so they don't accidentally branch on a sibling config.

    Returns:
        True if pipelex_gateway is enabled, False otherwise.
    """
    resolved_path = backends_file_path if backends_file_path is not None else config_manager.backends_file_path
    backends_toml = load_toml_from_path_if_exists(resolved_path)
    if backends_toml is None:
        return False

    gateway_config = backends_toml.get(PipelexBackend.GATEWAY)
    if gateway_config is None or not isinstance(gateway_config, dict):
        return False

    gateway_config_dict = cast("dict[str, Any]", gateway_config)
    enabled_value = gateway_config_dict.get("enabled", True)
    return enabled_value is True
