import os
import shutil
from pathlib import Path
from typing import Any

from pipelex.system.runtime import runtime_manager
from pipelex.tools.misc.toml_utils import load_toml_from_path_and_merge_with_overrides

CONFIG_DIR_NAME = ".pipelex"
CONFIG_NAME = "pipelex.toml"

PROJECT_ROOT_MARKERS: frozenset[str] = frozenset({".git", "pyproject.toml", "setup.py", "setup.cfg", "package.json", ".hg"})

INFERENCE_DIR_NAME = "inference"
BACKENDS_FILE_NAME = "backends.toml"
BACKENDS_DIR_NAME = "backends"
ROUTING_PROFILES_FILE_NAME = "routing_profiles.toml"
MODEL_DECKS_DIR_NAME = "deck"


class ConfigLoader:
    @property
    def pipelex_root_dir(self) -> str:
        """Get the root directory of the installed pipelex package.

        Uses __file__ to locate the package directory, which works in both
        development and installed modes.
        """
        return str(Path(__file__).resolve().parent.parent.parent)

    @staticmethod
    def find_project_root(start_dir: Path) -> Path | None:
        """Walk up from start_dir looking for project root markers.

        Excludes the home directory, which may contain stray marker files
        (e.g. package.json) but is never a real project root.

        Returns the directory containing the marker, or None if not found.
        """
        current = start_dir.resolve()
        home_dir = Path.home().resolve()
        while True:
            if current == home_dir:
                return None
            for marker in PROJECT_ROOT_MARKERS:
                if (current / marker).exists():
                    return current
            parent = current.parent
            if parent == current:
                return None
            current = parent

    @property
    def global_config_dir(self) -> str:
        """Get the global config directory at ~/.pipelex."""
        return str(Path.home() / CONFIG_DIR_NAME)

    @property
    def project_root(self) -> str | None:
        """Get the detected project root directory, or None if no project root markers found."""
        project_root = self.find_project_root(Path.cwd())
        if project_root is None:
            return None
        return str(project_root)

    @property
    def project_config_dir(self) -> str | None:
        """Get the project config directory if it exists on disk.

        Returns the path to {project_root}/.pipelex if the project root was found
        and the .pipelex directory exists there, otherwise None.
        """
        project_root = self.find_project_root(Path.cwd())
        if project_root is None:
            return None
        project_config = project_root / CONFIG_DIR_NAME
        if project_config.is_dir():
            return str(project_config)
        return None

    @property
    def pipelex_config_dir(self) -> str:
        """Get the effective config directory (project if exists, else global).

        This preserves backwards compatibility for all current consumers.
        """
        project_dir = self.project_config_dir
        if project_dir is not None:
            return project_dir
        return self.global_config_dir

    def _resolve_inference_file(self, relative_path: str) -> str:
        """Resolve an inference file path, checking project dir first, then global.

        Args:
            relative_path: Path relative to the .pipelex directory (e.g. "inference/backends.toml").

        Returns:
            The resolved absolute path.
        """
        project_dir = self.project_config_dir
        if project_dir is not None:
            candidate = os.path.join(project_dir, relative_path)
            if os.path.exists(candidate):
                return candidate
        return os.path.join(self.global_config_dir, relative_path)

    @property
    def backends_file_path(self) -> str:
        """Resolve backends.toml from project dir or global dir."""
        return self._resolve_inference_file(os.path.join(INFERENCE_DIR_NAME, BACKENDS_FILE_NAME))

    @property
    def backends_dir_path(self) -> str:
        """Resolve backends/ directory from project dir or global dir."""
        return self._resolve_inference_file(os.path.join(INFERENCE_DIR_NAME, BACKENDS_DIR_NAME))

    @property
    def routing_profiles_file_path(self) -> str:
        """Resolve routing_profiles.toml from project dir or global dir."""
        return self._resolve_inference_file(os.path.join(INFERENCE_DIR_NAME, ROUTING_PROFILES_FILE_NAME))

    @property
    def model_decks_dir_path(self) -> str:
        """Resolve model decks directory from project dir or global dir."""
        return self._resolve_inference_file(os.path.join(INFERENCE_DIR_NAME, MODEL_DECKS_DIR_NAME))

    def ensure_global_config_exists(self) -> None:
        """Create the global ~/.pipelex/ directory with kit template files if it doesn't exist."""
        global_dir = Path(self.global_config_dir)
        if global_dir.is_dir():
            return

        from pipelex.kit.paths import GIT_IGNORED_CONFIG_FILES, get_kit_configs_dir  # noqa: PLC0415

        config_template_dir = str(get_kit_configs_dir())
        global_dir_str = str(global_dir)
        os.makedirs(global_dir_str, exist_ok=True)

        def copy_directory_structure(src_dir: str, dst_dir: str) -> None:
            """Recursively copy directory structure from kit templates."""
            for item in os.listdir(src_dir):
                if item in GIT_IGNORED_CONFIG_FILES or item == ".DS_Store":
                    continue
                src_item = os.path.join(src_dir, item)
                dst_item = os.path.join(dst_dir, item)
                if os.path.isdir(src_item):
                    os.makedirs(dst_item, exist_ok=True)
                    copy_directory_structure(src_item, dst_item)
                else:
                    shutil.copy2(src_item, dst_item)

        copy_directory_structure(src_dir=config_template_dir, dst_dir=global_dir_str)

    def load_config(self) -> dict[str, Any]:
        """Load and merge configurations from pipelex and local config files.

        The configuration is loaded and merged in the following order:
        1. Base pipelex config (pipelex/pipelex.toml — package defaults)
        2. Global config (~/.pipelex/pipelex.toml)
        3. Project config ({project_root}/.pipelex/pipelex.toml, if found)
        4. Override configs from effective config dir in sequence:
           - pipelex_local.toml (local execution)
           - pipelex_{environment}.toml
           - pipelex_{run_mode}.toml
           - pipelex_override.toml (final override)

        Returns:
            dict[str, Any]: The merged configuration dictionary
        """
        self.ensure_global_config_exists()

        list_of_configs: list[str] = []

        # 1. Pipelex package defaults
        list_of_configs.append(os.path.join(self.pipelex_root_dir, CONFIG_NAME))

        # 2. Global config
        list_of_configs.append(os.path.join(self.global_config_dir, CONFIG_NAME))

        # 3. Project config (if different from global)
        project_dir = self.project_config_dir
        if project_dir is not None and project_dir != self.global_config_dir:
            list_of_configs.append(os.path.join(project_dir, CONFIG_NAME))

        # Effective config dir for overrides
        effective_config_dir = self.pipelex_config_dir

        # 4. Override for local execution
        list_of_configs.append(os.path.join(effective_config_dir, "pipelex_local.toml"))

        # Override for environment
        list_of_configs.append(os.path.join(effective_config_dir, f"pipelex_{runtime_manager.environment}.toml"))

        # Override for run mode
        if runtime_manager.is_unit_testing:
            list_of_configs.append(os.path.join(os.getcwd(), "tests", f"pipelex_{runtime_manager.run_mode}.toml"))
        else:
            list_of_configs.append(os.path.join(effective_config_dir, f"pipelex_{runtime_manager.run_mode}.toml"))

        # Final override
        list_of_configs.append(os.path.join(effective_config_dir, "pipelex_override.toml"))

        return load_toml_from_path_and_merge_with_overrides(paths=list_of_configs)


config_manager = ConfigLoader()
