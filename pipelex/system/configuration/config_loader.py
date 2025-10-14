import importlib
import os
from configparser import ConfigParser
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

    def load_inheritance_config(self, the_pipelex_config: dict[str, Any]):
        """Load the config by inheritance in a pyproject.toml file.
        This will be removed in the future.
        Requires to have a pyproject.toml file in the project root.
        """
        pyproject_path = os.path.join(os.getcwd(), "pyproject.toml")
        if not os.path.exists(pyproject_path):
            print(f"pyproject.toml not found in {os.getcwd()}")
            return

        def _find_package_path(package_name: str) -> str | None:
            """Find package path by importing it"""
            try:
                module = importlib.import_module(package_name)
                if hasattr(module, "__file__") and module.__file__:
                    return os.path.dirname(module.__file__)
            except ImportError:
                pass

            return None

        pyproject = load_toml_from_path(path=pyproject_path)
        if "tool" in pyproject and "pipelex" in pyproject["tool"] and "config_inheritance" in pyproject["tool"]["pipelex"]:
            for config_name in pyproject["tool"]["pipelex"]["config_inheritance"]:
                package_path = _find_package_path(config_name)
                if package_path:
                    config_path = os.path.join(package_path, "pipelex.toml")
                    if os.path.exists(config_path):
                        config = load_toml_from_path_if_exists(config_path)
                        if config:
                            deep_update(the_pipelex_config, config)

    def load_config(self, specific_config_path: str | None = None) -> dict[str, Any]:
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
        #################### 1. Load pipelex config ####################
        pipelex_config = self.get_pipelex_config()

        #################### 2. Load inheritance config for internal use ####################
        # TODO: Undocumented feature, soon to be removed.
        self.load_inheritance_config(pipelex_config)

        #################### 3. Load local (current project) config ####################
        if not self.is_in_pipelex_config:
            local_config = self.get_local_config()
            if local_config:
                deep_update(pipelex_config, local_config)

        #################### 4. Load overrides for the current project ####################
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

        #################### 5. Load specific config ####################
        if specific_config_path:
            config = load_toml_from_path_if_exists(specific_config_path)
            if config:
                deep_update(pipelex_config, config)
            else:
                msg = f"Failed to load specific config from {specific_config_path}"
                raise ConfigError(msg)

        return pipelex_config

    def get_project_name(self) -> str | None:
        """Get the project name from configuration files.

        Checks the following files in order:
        1. pipelex's pyproject.toml
        2. Local pyproject.toml
        3. setup.cfg
        4. setup.py

        Returns:
            str | None: The project name or None if not found

        """
        # First check pipelex's pyproject.toml
        pipelex_pyproject_path = os.path.join(os.path.dirname(os.getcwd()), "pyproject.toml")
        if pipelex_pyproject := load_toml_from_path_if_exists(path=pipelex_pyproject_path):
            if (project_name := pipelex_pyproject.get("project", {}).get("name")) and isinstance(project_name, str):
                return str(project_name)

        # Check local pyproject.toml
        local_pyproject_path = os.path.join(os.getcwd(), "pyproject.toml")
        if local_pyproject := load_toml_from_path_if_exists(local_pyproject_path):
            name_obj: object = local_pyproject.get("project", {}).get("name") or local_pyproject.get("tool", {}).get("poetry", {}).get("name")
            if isinstance(name_obj, str):
                return name_obj

        # Check setup.cfg
        setup_cfg_path = os.path.join(os.getcwd(), "setup.cfg")
        try:
            config = ConfigParser()
            config.read(setup_cfg_path)
            if (cfg_name := config.get("metadata", "name", fallback=None)) and config.has_section("metadata"):
                return cfg_name
        except FileNotFoundError as exc:
            print(f"setup.cfg not found at {setup_cfg_path}: {exc}")
        except (ValueError, OSError) as exc:
            print(f"Failed to parse setup.cfg at {setup_cfg_path}: {exc}")

        # Check setup.py as last resort
        setup_py_path = os.path.join(os.getcwd(), "setup.py")
        try:
            with open(setup_py_path) as f:
                content = f.read()
                # Simple string search for name parameter
                for line in content.splitlines():
                    if "name=" in line or "name =" in line:
                        # Extract value between quotes
                        for quote in ['"', "'"]:
                            start = line.find(quote)
                            if start != -1:
                                end = line.find(quote, start + 1)
                                if end != -1:
                                    return line[start + 1 : end]
        except FileNotFoundError as exc:
            print(f"setup.py not found at {setup_py_path}: {exc}")
        except (OSError, UnicodeDecodeError) as exc:
            print(f"Failed to read setup.py at {setup_py_path}: {exc}")

        print("Could not find project name in any of the configuration files")
        return None


config_manager = ConfigLoader()
