import os
from configparser import ConfigParser
from typing import Any, Dict, Optional

import toml

from pipelex.tools.config.models import (
    CONFIG_BASE_OVERRIDES_AFTER_ENV,
    CONFIG_BASE_OVERRIDES_BEFORE_ENV,
)
from pipelex.tools.misc.json_utils import deep_update
from pipelex.tools.misc.toml_utils import failable_load_toml_from_path
from pipelex.tools.runtime_manager import runtime_manager

CONFIG_NAME = "pipelex.toml"


class ConfigException(Exception):
    pass


class ConfigManager:
    @property
    def is_in_pipelex_config(self) -> bool:
        return os.path.basename(self.local_root_dir) == "pipelex"

    @property
    def pipelex_root_dir(self) -> str:
        """Get the root directory of the installed pipelex package.

        Uses __file__ to locate the package directory, which works in both
        development and installed modes.
        """
        current_dir = os.path.dirname(os.path.abspath(__file__))
        return os.path.dirname(os.path.dirname(current_dir))

    @property
    def local_root_dir(self) -> str:
        """Get the root directory of the project using pipelex.
        This is the directory from where the command is being run."""
        return os.path.abspath(os.getcwd())

    def get_pipelex_config(self) -> Dict[str, Any]:
        """Get the pipelex configuration from pipelex.toml.

        Returns:
            Dict[str, Any]: The configuration dictionary from pipelex.toml
        """
        config_path = os.path.join(self.pipelex_root_dir, CONFIG_NAME)
        config = failable_load_toml_from_path(config_path)
        return config or {}

    def get_local_config(self) -> Dict[str, Any]:
        """Get the local pipelex configuration from pipelex.toml in the project root.

        Returns:
            Dict[str, Any]: The configuration dictionary from the local pipelex.toml
        """
        config_path = os.path.join(self.local_root_dir, CONFIG_NAME)
        config = failable_load_toml_from_path(config_path)
        return config or {}

    def load_inheritance_config(self, the_pipelex_config: Dict[str, Any]):
        """
        Load the config by inheritance in a pyproject.toml file.
        This will be removed in the future.
        Requires to have a pyproject.toml file in the project root.
        """
        pyproject_path = os.path.join(self.local_root_dir, "pyproject.toml")
        if not os.path.exists(pyproject_path):
            print(f"pyproject.toml not found in {self.local_root_dir}")
            return

        pyproject = toml.load(pyproject_path)
        if "tool" in pyproject and "pipelex" in pyproject["tool"] and "config_inheritance" in pyproject["tool"]["pipelex"]:
            for config_name in pyproject["tool"]["pipelex"]["config_inheritance"]:
                print(f"Loading config inheritance for {config_name}")
                # First check if it's a local dependency in poetry
                package_path: Optional[str] = None
                if "tool" in pyproject and "poetry" in pyproject["tool"] and "dependencies" in pyproject["tool"]["poetry"]:
                    dep_config: Dict[str, Any] = pyproject["tool"]["poetry"]["dependencies"].get(config_name, {})
                    if "path" in dep_config:
                        # It's a local path
                        local_path: str = str(dep_config["path"])
                        package_path = os.path.abspath(os.path.join(self.local_root_dir, local_path))

                if not package_path:
                    # Try to find in .venv
                    venv_path = os.path.join(self.local_root_dir, ".venv")
                    if os.path.exists(venv_path):
                        site_packages = os.path.join(venv_path, "lib", "python3.11", "site-packages", config_name)
                        if os.path.exists(site_packages):
                            package_path = site_packages

                if package_path:
                    config_path = os.path.join(package_path, "pipelex.toml")
                    print(f"Loading config inheritance for {config_name} from {config_path}")
                    if os.path.exists(config_path):
                        print(f"Found config inheritance for {config_name} from {config_path}")
                        config = failable_load_toml_from_path(config_path)
                        if config:
                            deep_update(the_pipelex_config, config)

    def load_config(self, specific_config_path: Optional[str] = None) -> Dict[str, Any]:
        """Load and merge configurations from pipelex and local config files.

        The configuration is loaded and merged in the following order:
        1. Base pipelex config (pipelex.toml)
        2. Local project config (pipelex.toml) if not in pipelex package
        3. Override configs in sequence:
           - pipelex_local.toml (before env)
           - pipelex_{environment}.toml
           - pipelex_{run_mode}.toml
           - pipelex_user.toml (after env)

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
        list_of_overrides = (
            CONFIG_BASE_OVERRIDES_BEFORE_ENV + [runtime_manager.environment] + [runtime_manager.run_mode] + CONFIG_BASE_OVERRIDES_AFTER_ENV
        )
        for override in list_of_overrides:
            if override:
                if override == runtime_manager.run_mode.UNIT_TEST:
                    override_path = os.path.join(self.local_root_dir, "tests", f"pipelex_{override}.toml")
                else:
                    override_path = os.path.join(self.local_root_dir, "pipelex" if self.is_in_pipelex_config else "", f"pipelex_{override}.toml")
                if override_dict := failable_load_toml_from_path(override_path):
                    deep_update(pipelex_config, override_dict)

        #################### 5. Load specific config ####################
        if specific_config_path:
            config = failable_load_toml_from_path(specific_config_path)
            if config:
                deep_update(pipelex_config, config)
            else:
                raise ConfigException(f"Failed to load specific config from {specific_config_path}")

        return pipelex_config

    def get_project_name(self) -> Optional[str]:
        """Get the project name from configuration files.

        Checks the following files in order:
        1. pipelex's pyproject.toml
        2. Local pyproject.toml
        3. setup.cfg
        4. setup.py

        Returns:
            Optional[str]: The project name or None if not found
        """
        # First check pipelex's pyproject.toml
        pipelex_pyproject_path = os.path.join(os.path.dirname(self.local_root_dir), "pyproject.toml")
        try:
            pyproject = toml.load(pipelex_pyproject_path)
            if project_name := pyproject.get("project", {}).get("name"):
                if isinstance(project_name, str):
                    return project_name
        except FileNotFoundError:
            pass
        except toml.TomlDecodeError as exc:
            print(f"Failed to parse pipelex pyproject.toml at {pipelex_pyproject_path}: {exc}")
        except (KeyError, TypeError, AttributeError) as exc:
            print(f"Invalid structure in pipelex pyproject.toml at {pipelex_pyproject_path}: {exc}")

        # Check local pyproject.toml
        pyproject_path = os.path.join(self.local_root_dir, "pyproject.toml")
        try:
            pyproject = toml.load(pyproject_path)
            if project_name := pyproject.get("project", {}).get("name") or pyproject.get("tool", {}).get("poetry", {}).get("name"):
                if isinstance(project_name, str):
                    return project_name
        except FileNotFoundError as exc:
            print(f"Local pyproject.toml not found at {pyproject_path}: {exc}")
        except toml.TomlDecodeError as exc:
            print(f"Failed to parse local pyproject.toml at {pyproject_path}: {exc}")
        except (KeyError, TypeError, AttributeError) as exc:
            print(f"Invalid structure in local pyproject.toml at {pyproject_path}: {exc}")

        # Check setup.cfg
        setup_cfg_path = os.path.join(self.local_root_dir, "setup.cfg")
        try:
            config = ConfigParser()
            config.read(setup_cfg_path)
            if config.has_section("metadata"):
                if cfg_name := config.get("metadata", "name", fallback=None):
                    return cfg_name
        except FileNotFoundError as exc:
            print(f"setup.cfg not found at {setup_cfg_path}: {exc}")
        except (ValueError, OSError) as exc:
            print(f"Failed to parse setup.cfg at {setup_cfg_path}: {exc}")

        # Check setup.py as last resort
        setup_py_path = os.path.join(self.local_root_dir, "setup.py")
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
        except (IOError, UnicodeDecodeError) as exc:
            print(f"Failed to read setup.py at {setup_py_path}: {exc}")

        print("Could not find project name in any of the configuration files")
        return None


config_manager = ConfigManager()
