import os

from pydantic import Field

from pipelex.kit.paths import get_kit_configs_dir
from pipelex.system.configuration.config_loader import config_manager
from pipelex.system.configuration.config_model import ConfigModel
from pipelex.tools.misc.file_utils import path_exists
from pipelex.tools.misc.toml_utils import load_toml_with_tomlkit, save_toml_to_path

PIPELEX_SERVICE_CONFIG_FILE_NAME = "pipelex_service.toml"


class PipelexServiceAgreement(ConfigModel):
    terms_accepted: bool = Field(
        default=False,
        description="Whether the user has accepted Pipelex terms of service",
    )


def update_service_terms_acceptance(accepted: bool) -> None:
    """Update the service terms acceptance in pipelex_service.toml.

    Args:
        accepted: Whether the user accepted the terms.
    """
    service_config_path = os.path.join(config_manager.pipelex_config_dir, PIPELEX_SERVICE_CONFIG_FILE_NAME)

    if path_exists(service_config_path):
        toml_doc = load_toml_with_tomlkit(service_config_path)
    else:
        # Load from the kit template
        template_path = str(get_kit_configs_dir() / PIPELEX_SERVICE_CONFIG_FILE_NAME)
        toml_doc = load_toml_with_tomlkit(template_path)

    # Update terms_accepted
    toml_doc["agreement"]["terms_accepted"] = accepted  # type: ignore[index]

    save_toml_to_path(toml_doc, service_config_path)
