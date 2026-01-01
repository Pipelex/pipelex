import os
from pathlib import Path
from typing import Any

from pipelex.system.runtime import runtime_manager
from pipelex.tools.misc.toml_utils import load_toml_from_path_and_merge_with_overrides

CONFIG_DIR_NAME = ".pipelex"
CONFIG_NAME = "pipelex.toml"


class ConfigLoader:
    @property
    def pipelex_root_dir(self) -> str:
        """Get the root directory of the installed pipelex package.

        Uses __file__ to locate the package directory, which works in both
        development and installed modes.
        """
        return str(Path(__file__).resolve().parent.parent.parent)

    @property
    def pipelex_config_dir(self) -> str:
        return os.path.join(os.getcwd(), CONFIG_DIR_NAME)

    def load_config(self) -> dict[str, Any]:
        """Load and merge configurations from pipelex and local config files.

        The configuration is loaded and merged in the following order:
        1. Base pipelex config (pipelex.toml)
        2. Local project config (pipelex.toml) if not in pipelex package
        3. Override configs in sequence:
           - pipelex_local.toml (local execution)
           - pipelex_{environment}.toml
           - pipelex_{run_mode}.toml
           - pipelex_override.toml (final override)

        Returns:
            Dict[str, Any]: The merged configuration dictionary

        """
        list_of_configs: list[str] = []

        # Pipelex base config
        list_of_configs.append(os.path.join(self.pipelex_root_dir, CONFIG_NAME))

        # Current project overrides
        list_of_configs.append(os.path.join(self.pipelex_config_dir, CONFIG_NAME))

        # Override for local execution
        list_of_configs.append(os.path.join(self.pipelex_config_dir, "pipelex_local.toml"))

        # Override for environment
        list_of_configs.append(os.path.join(self.pipelex_config_dir, f"pipelex_{runtime_manager.environment}.toml"))

        # Override for run mode
        if runtime_manager.is_unit_testing:
            list_of_configs.append(os.path.join(os.getcwd(), "tests", f"pipelex_{runtime_manager.run_mode}.toml"))
        else:
            list_of_configs.append(os.path.join(self.pipelex_config_dir, f"pipelex_{runtime_manager.run_mode}.toml"))

        # Final override
        list_of_configs.append(os.path.join(self.pipelex_config_dir, "pipelex_override.toml"))

        return load_toml_from_path_and_merge_with_overrides(paths=list_of_configs)


config_manager = ConfigLoader()
