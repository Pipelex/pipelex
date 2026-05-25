import shutil
from pathlib import Path
from typing import Any

from pipelex.system.runtime import runtime_manager
from pipelex.tools.misc.json_utils import deep_update
from pipelex.tools.misc.toml_utils import load_toml_from_path_and_merge_with_overrides

CONFIG_DIR_NAME = ".pipelex"
CONFIG_NAME = "pipelex.toml"

PROJECT_ROOT_MARKERS: frozenset[str] = frozenset({CONFIG_DIR_NAME, ".git", "pyproject.toml", "setup.py", "setup.cfg", "package.json", ".hg"})

INFERENCE_DIR_NAME = "inference"
BACKENDS_FILE_NAME = "backends.toml"
BACKENDS_DIR_NAME = "backends"
ROUTING_PROFILES_FILE_NAME = "routing_profiles.toml"
MODEL_DECKS_DIR_NAME = "deck"


class ConfigLoader:
    @property
    def pipelex_root_dir(self) -> Path:
        """Get the root directory of the installed pipelex package.

        Uses __file__ to locate the package directory, which works in both
        development and installed modes.
        """
        return Path(__file__).resolve().parent.parent.parent

    @staticmethod
    def find_project_root(start_dir: Path) -> Path | None:
        """Walk up from start_dir looking for project root markers.

        Excludes the home directory, which may contain stray marker files
        (e.g. the global ~/.pipelex/ or a stray package.json) but is never a
        real project root.

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
    def global_config_dir(self) -> Path:
        """Get the global config directory at ~/.pipelex."""
        return Path.home() / CONFIG_DIR_NAME

    @property
    def project_root(self) -> Path | None:
        """Get the detected project root directory, or None if no project root markers found."""
        return self.find_project_root(Path.cwd())

    @property
    def project_config_dir(self) -> Path | None:
        """Get the project config directory if it exists on disk.

        Returns the path to {project_root}/.pipelex if the project root was found
        and the .pipelex directory exists there, otherwise None.
        """
        project_root = self.find_project_root(Path.cwd())
        if project_root is None:
            return None
        project_config = project_root / CONFIG_DIR_NAME
        if project_config.is_dir():
            return project_config
        return None

    @property
    def pipelex_config_dir(self) -> Path:
        """Get the effective config directory (project if exists, else global).

        This preserves backwards compatibility for all current consumers.
        """
        project_dir = self.project_config_dir
        if project_dir is not None:
            return project_dir
        return self.global_config_dir

    def resolve_config_file(self, relative_path: str, config_dir: Path | None = None) -> Path:
        """Resolve a config file path with layered resolution.

        When config_dir is provided (e.g. for --global override), the file is
        resolved directly under that directory.

        Otherwise, the project .pipelex/ directory is checked first; if the file
        exists there it wins, otherwise the global ~/.pipelex/ is used.
        This works on all platforms (macOS, Linux, Windows) because Path.home()
        returns the correct home directory everywhere.

        Args:
            relative_path: Path relative to the .pipelex directory (e.g. "telemetry.toml",
                "inference/backends.toml").
            config_dir: Explicit config directory override. When set, skips layered
                resolution and uses this directory directly.

        Returns:
            The resolved absolute path.
        """
        if config_dir is not None:
            return config_dir / relative_path
        project_dir = self.project_config_dir
        if project_dir is not None:
            candidate = project_dir / relative_path
            if candidate.exists():
                return candidate
        return self.global_config_dir / relative_path

    @property
    def backends_file_path(self) -> Path:
        """Resolve backends.toml from project dir or global dir."""
        return self.resolve_config_file(str(Path(INFERENCE_DIR_NAME) / BACKENDS_FILE_NAME))

    @property
    def backends_dir_path(self) -> Path:
        """Resolve backends/ directory from project dir or global dir."""
        return self.resolve_config_file(str(Path(INFERENCE_DIR_NAME) / BACKENDS_DIR_NAME))

    @property
    def routing_profiles_file_path(self) -> Path:
        """Resolve routing_profiles.toml from project dir or global dir."""
        return self.resolve_config_file(str(Path(INFERENCE_DIR_NAME) / ROUTING_PROFILES_FILE_NAME))

    @property
    def model_decks_dir_path(self) -> Path:
        """Resolve model decks directory from project dir or global dir."""
        return self.resolve_config_file(str(Path(INFERENCE_DIR_NAME) / MODEL_DECKS_DIR_NAME))

    def ensure_global_config_exists(self) -> None:
        """Create the global ~/.pipelex/ directory with kit template files if it doesn't exist."""
        global_dir = self.global_config_dir
        if global_dir.is_dir():
            return

        from pipelex.kit.paths import GIT_IGNORED_CONFIG_FILES, get_kit_configs_dir  # noqa: PLC0415

        config_template_dir = Path(str(get_kit_configs_dir()))
        global_dir.mkdir(parents=True, exist_ok=True)

        def copy_directory_structure(src_dir: Path, dst_dir: Path) -> None:
            """Recursively copy directory structure from kit templates."""
            for item in src_dir.iterdir():
                if item.name in GIT_IGNORED_CONFIG_FILES or item.name == ".DS_Store":
                    continue
                dst_item = dst_dir / item.name
                if item.is_dir():
                    dst_item.mkdir(parents=True, exist_ok=True)
                    copy_directory_structure(item, dst_item)
                else:
                    shutil.copy2(item, dst_item)

        copy_directory_structure(src_dir=config_template_dir, dst_dir=global_dir)

        # Stamp the deck manifest so the boot-time staleness check has a baseline.
        # Imported lazily to avoid a circular import — config_loader is loaded very early.
        from pipelex.cogt.models.deck_manifest import compute_kit_manifest, write_manifest  # noqa: PLC0415

        write_manifest(global_dir / "inference" / "deck", compute_kit_manifest())

    @classmethod
    def _override_files_for_dir(cls, config_dir: Path, include_run_mode: bool) -> list[Path]:
        """Build the override file sequence for a single config dir.

        Order matters: later files win on key collisions during deep-merge.

        Args:
            config_dir: The .pipelex directory to look in.
            include_run_mode: When False, omit the `pipelex_{run_mode}.toml` entry.
                Used under unit testing so the run_mode file is sourced only from
                `./tests/` and not from per-dir overrides.

        Returns:
            Ordered list of candidate file paths (missing files are ignored at load time).
        """
        files = [
            config_dir / "pipelex_local.toml",
            config_dir / f"pipelex_{runtime_manager.environment}.toml",
        ]
        if include_run_mode:
            files.append(config_dir / f"pipelex_{runtime_manager.run_mode}.toml")
        files.append(config_dir / "pipelex_override.toml")
        files.append(config_dir / "pipelex_temporary_override.toml")
        return files

    def load_config(self, extra_overrides: dict[str, Any] | None = None, config_dir: Path | None = None) -> dict[str, Any]:
        """Load and merge configurations from pipelex and local config files.

        When ``config_dir`` is provided, the load is scoped to a single directory
        (package defaults + ``config_dir`` base + ``config_dir`` overrides + ``extra_overrides``).
        This is what the doctor command uses for ``--global``: it wants the hub to reflect
        exactly the directory it is reporting on, with no project/global layering muddying
        the view.

        Otherwise the configuration is loaded and deep-merged in the following order
        (later wins per leaf key):

        1. Package defaults (pipelex/pipelex.toml)
        2. Global base (~/.pipelex/pipelex.toml)
        3. Global override sequence (from ~/.pipelex/):
           - pipelex_local.toml
           - pipelex_{environment}.toml
           - pipelex_{run_mode}.toml (omitted under unit testing — see below)
           - pipelex_override.toml
           - pipelex_temporary_override.toml
        4. Project base ({project_root}/.pipelex/pipelex.toml, if found and
           distinct from the global dir)
        5. Project override sequence (same five files as step 3, from the
           project's .pipelex/), if the project dir is distinct from global
        6. Programmatic `extra_overrides`, if any

        Unit-testing special case: when `runtime_manager.is_unit_testing` is
        true, the `pipelex_{run_mode}.toml` entry is sourced exclusively from
        `./tests/pipelex_{run_mode}.toml` and is layered at the highest run_mode
        precedence. Global and project run_mode files are not loaded, to keep
        test runs hermetic.

        Args:
            extra_overrides: Optional dict deep-merged on top as the final layer.
            config_dir: Optional explicit config dir. When given, project/global layering
                is bypassed and only this directory is read.

        Returns:
            dict[str, Any]: The merged configuration dictionary
        """
        is_unit_testing = runtime_manager.is_unit_testing

        list_of_configs: list[Path] = [self.pipelex_root_dir / CONFIG_NAME]

        if config_dir is not None:
            list_of_configs.append(config_dir / CONFIG_NAME)
            list_of_configs.extend(
                self._override_files_for_dir(config_dir, include_run_mode=not is_unit_testing),
            )
        else:
            self.ensure_global_config_exists()
            project_dir = self.project_config_dir

            list_of_configs.append(self.global_config_dir / CONFIG_NAME)
            list_of_configs.extend(
                self._override_files_for_dir(self.global_config_dir, include_run_mode=not is_unit_testing),
            )

            if project_dir is not None and project_dir != self.global_config_dir:
                list_of_configs.append(project_dir / CONFIG_NAME)
                list_of_configs.extend(
                    self._override_files_for_dir(project_dir, include_run_mode=not is_unit_testing),
                )

        if is_unit_testing:
            list_of_configs.append(Path.cwd() / "tests" / f"pipelex_{runtime_manager.run_mode}.toml")

        merged = load_toml_from_path_and_merge_with_overrides(paths=list_of_configs)
        if extra_overrides:
            deep_update(merged, extra_overrides)
        return merged


config_manager = ConfigLoader()
