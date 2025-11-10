import os
from typing import Any

from pipelex.system.configuration.config_root import (
    CONFIG_BASE_OVERRIDES_AFTER_ENV,
    CONFIG_BASE_OVERRIDES_BEFORE_ENV,
)
from pipelex.system.runtime import runtime_manager
from pipelex.tools.misc.json_utils import deep_update
from pipelex.tools.misc.toml_utils import load_toml_from_path, load_toml_from_path_if_exists

CONFIG_DIR_NAME = ".pipelex"
CONFIG_NAME = "pipelex.toml"


class ConfigError(Exception):
    pass


class ConfigLoader:
    @property
    def is_in_pipelex_config(self) -> bool:
        return os.path.basename(os.getcwd()) == "pipelex"

    @property
    def pipelex_root_dir(self) -> str:
        """Get the root directory of the installed pipelex package.

        Uses __file__ to locate the package directory, which works in both
        development and installed modes.
        """
        current_dir = os.path.dirname(os.path.abspath(__file__))
        return os.path.dirname(os.path.dirname(current_dir))

    @property
    def pipelex_root_config_path(self) -> str:
        return os.path.join(self.pipelex_root_dir, CONFIG_NAME)

    @property
    def local_root_dir(self) -> str:
        """Get the root directory of the project using pipelex.
        This is the directory from where the command is being run.
        """
        return os.getcwd()

    @property
    def pipelex_config_dir(self) -> str:
        return os.path.join(os.getcwd(), CONFIG_DIR_NAME)

    @property
    def pipelex_specific_config_file_path(self) -> str:
        return os.path.join(self.pipelex_config_dir, CONFIG_NAME)

    def get_pipelex_config(self) -> dict[str, Any]:
        """Get the pipelex configuration from pipelex.toml.

        Returns:
            Dict[str, Any]: The configuration dictionary from pipelex.toml

        """
        config_path = self.pipelex_root_config_path
        return load_toml_from_path(config_path)

    def get_local_config(self) -> dict[str, Any]:
        """Get the local pipelex configuration from pipelex.toml in the project root.

        Returns:
            Dict[str, Any]: The configuration dictionary from the local pipelex.toml

        """
        config_path = os.path.join(self.pipelex_config_dir, CONFIG_NAME)
        return load_toml_from_path_if_exists(config_path) or {}

    def load_config(self) -> dict[str, Any]:
        """Load and merge configurations from pipelex and local config files.

        The configuration is loaded and merged in the following order:
        1. Base pipelex config (pipelex.toml)
        2. Local project config (pipelex.toml) if not in pipelex package
        3. Override configs in sequence:
           - pipelex_local.toml (before env)
           - pipelex_{environment}.toml
           - pipelex_{run_mode}.toml

        Returns:
            Dict[str, Any]: The merged configuration dictionary

        """
        #################### 1. Load pipelex base config ####################
        pipelex_config = self.get_pipelex_config()

        #################### 2. Load local (current project) config ####################
        if not self.is_in_pipelex_config:
            local_config = self.get_local_config()
            if local_config:
                deep_update(pipelex_config, local_config)

        #################### 3. Load overrides for the current project ####################
        list_of_overrides = [
            *CONFIG_BASE_OVERRIDES_BEFORE_ENV,
            runtime_manager.environment,
            runtime_manager.run_mode,
            *CONFIG_BASE_OVERRIDES_AFTER_ENV,
        ]
        for override in list_of_overrides:
            if override:
                if override == runtime_manager.run_mode.UNIT_TEST:
                    override_path = os.path.join(os.getcwd(), "tests", f"pipelex_{override}.toml")
                else:
                    override_path = os.path.join(os.getcwd(), "pipelex" if self.is_in_pipelex_config else "", f"pipelex_{override}.toml")
                if override_dict := load_toml_from_path_if_exists(override_path):
                    deep_update(pipelex_config, override_dict)

        return pipelex_config


config_manager = ConfigLoader()
