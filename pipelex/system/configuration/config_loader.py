import shutil
from pathlib import Path
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from pipelex.system.configuration.config_surface import (
    PIPELEX_CONFIG_SURFACE_ID,
    replay_surface_files_in_memory,
    stale_configuration_warning,
    strip_reserved_meta,
)
from pipelex.system.exceptions import ConfigValidationError
from pipelex.system.runtime import runtime_manager
from pipelex.tools.misc.json_utils import deep_update
from pipelex.tools.misc.toml_utils import load_toml_from_path_and_merge_with_overrides

_PluginConfigT = TypeVar("_PluginConfigT", bound=BaseModel)
_ConfigT = TypeVar("_ConfigT", bound=BaseModel)

# What a configuration model raises when it refuses a document, and there are two of them.
# `ConfigRoot` gives itself a custom `__init__` that translates pydantic's error into ours, and
# pydantic v2 routes `model_validate` through a custom `__init__` — so the main configuration
# arrives as `ConfigValidationError` while a plain model surface arrives as pydantic's own.
# Catching one of the pair would silently switch boot tolerance off for whichever model it missed.
CONFIG_REFUSED = (ValidationError, ConfigValidationError)


def pydantic_error_behind(*, config_error: Exception) -> ValidationError | None:
    """The pydantic error a refused configuration actually carries, whichever half of `CONFIG_REFUSED` arrived.

    The companion of the tuple above, and it exists for the same reason: a caller that wants the
    field-level analysis has to reach through `ConfigValidationError` to the `__cause__` the
    translation kept, and doing that by hand at each site is how one of them comes to catch only
    pydantic's and quietly stop reporting anything for the main configuration.

    `None` when the refusal carries no pydantic error at all — a `ConfigValidationError` raised for
    a reason of its own — in which case its own message is the whole account.
    """
    if isinstance(config_error, ValidationError):
        return config_error
    cause = config_error.__cause__
    return cause if isinstance(cause, ValidationError) else None


CONFIG_DIR_NAME = ".pipelex"
CONFIG_NAME = "pipelex.toml"

PROJECT_ROOT_MARKERS: frozenset[str] = frozenset({CONFIG_DIR_NAME, ".git", "pyproject.toml", "setup.py", "setup.cfg", "package.json", ".hg"})

INFERENCE_DIR_NAME = "inference"
BACKENDS_FILE_NAME = "backends.toml"
BACKENDS_OVERRIDE_FILE_NAME = "backends_override.toml"
BACKENDS_DIR_NAME = "backends"
ROUTING_PROFILES_FILE_NAME = "routing_profiles.toml"
ROUTING_PROFILES_OVERRIDE_FILE_NAME = "routing_profiles_override.toml"
MODEL_DECKS_DIR_NAME = "deck"


class ConfigLoader:
    def __init__(self) -> None:
        self._stale_warning: str | None = None

    def take_stale_configuration_warning(self) -> str | None:
        """The warning a tolerated boot owes the user, once — or ``None`` when the load was clean.

        The loader parks it rather than logging it because the main configuration is what
        *configures logging*: at the moment the retry succeeds there is no logger yet, and the
        dispatch raises on any attempt. The boot emits it right after ``log.configure``.
        """
        warning, self._stale_warning = self._stale_warning, None
        return warning

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
    def existing_config_dirs(self) -> list[Path]:
        """The user's configuration directories that exist on this machine, in tier order.

        The global directory comes first and the project one second, which is the order the load
        merges them in. A project directory that *is* the global one — a project rooted at the home
        directory — is listed once rather than twice.

        This is the loader's own answer to "where does this machine keep its configuration", and it
        is deliberately the only answer there is: `pipelex migrate`'s walk is exactly this set (see
        `pipelex.migration.run.config_directories_to_migrate`, which reads it), and the stale-boot
        warning decides whether it may name that command by asking whether the stale file is under
        one of these. Two derivations of "the configuration directories" would let a boot promise a
        remedy the command then declines.
        """
        directories: list[Path] = []
        global_dir = self.global_config_dir
        if global_dir.is_dir():
            directories.append(global_dir)
        project_dir = self.project_config_dir
        if project_dir is not None and project_dir.resolve() not in {directory.resolve() for directory in directories}:
            directories.append(project_dir)
        return directories

    @property
    def pipelex_config_dir(self) -> Path:
        """Get the effective config directory (project if exists, else global).

        This preserves backwards compatibility for all current consumers.
        """
        project_dir = self.project_config_dir
        if project_dir is not None:
            return project_dir
        return self.global_config_dir

    def resolve_config_file(self, relative_path: str, *, config_dir: Path | None = None) -> Path:
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
        """The base ``backends.toml``, from the project dir or else the global dir.

        The base is the file that must exist and the one ``pipelex init`` writes. A reader wants
        ``backends_file_paths`` instead: the same base followed by the personal override files.
        """
        return self.resolve_config_file(f"{INFERENCE_DIR_NAME}/{BACKENDS_FILE_NAME}")

    @property
    def backends_dir_path(self) -> Path:
        """Resolve backends/ directory from project dir or global dir."""
        return self.resolve_config_file(f"{INFERENCE_DIR_NAME}/{BACKENDS_DIR_NAME}")

    @property
    def routing_profiles_file_path(self) -> Path:
        """The base ``routing_profiles.toml``, from the project dir or else the global dir.

        The base is the file that must exist and the one ``pipelex init`` writes. A reader wants
        ``routing_profiles_file_paths`` instead: the same base followed by the personal override files.
        """
        return self.resolve_config_file(f"{INFERENCE_DIR_NAME}/{ROUTING_PROFILES_FILE_NAME}")

    def backends_file_paths(self, *, config_dir: Path | None = None) -> list[Path]:
        """The ``backends.toml`` merge sequence: the resolved base, then the override at each tier.

        See ``_inference_file_paths`` for the order and why it is what it is.
        """
        return self._inference_file_paths(
            resolved_base=self.backends_file_path,
            file_name=BACKENDS_FILE_NAME,
            override_file_name=BACKENDS_OVERRIDE_FILE_NAME,
            config_dir=config_dir,
        )

    def routing_profiles_file_paths(self, *, config_dir: Path | None = None) -> list[Path]:
        """The ``routing_profiles.toml`` merge sequence: the resolved base, then the override at each tier.

        See ``_inference_file_paths`` for the order and why it is what it is.
        """
        return self._inference_file_paths(
            resolved_base=self.routing_profiles_file_path,
            file_name=ROUTING_PROFILES_FILE_NAME,
            override_file_name=ROUTING_PROFILES_OVERRIDE_FILE_NAME,
            config_dir=config_dir,
        )

    def _inference_file_paths(self, *, resolved_base: Path, file_name: str, override_file_name: str, config_dir: Path | None) -> list[Path]:
        """The paths a reader of one inference document merges, base first.

        The first path is the base and must exist; the rest are the personal override files, each
        carrying only the keys it sets, merged in order so the last wins per leaf key
        (``load_toml_from_base_and_overrides`` is the loader that honours this contract).

        Without ``config_dir`` the sequence is::

            [resolved base, ~/.pipelex/inference/<override>, <project>/.pipelex/inference/<override>]

        The base keeps today's winner-takes-all resolution — a project's file if it has one, else
        the global one — and the overrides layer over whichever was picked, global then project.
        That order is deliberately not ``pipelex.toml``'s, where a project base beats a global
        override: a global inference override exists so that one machine-wide choice ("run on this
        backend") reaches every project on the machine, and every project carries a tracked
        ``backends.toml`` of its own, so a project base that beat it would defeat the file's purpose.
        A project override still wins over the global one, for the one project that needs to differ.

        With ``config_dir`` (the doctor's ``--global``, an init targeting one directory) the
        sequence is pinned to that directory and its own override, mirroring ``load_config``.

        ``resolved_base`` is the public ``backends_file_path`` / ``routing_profiles_file_path``
        property, read rather than recomputed here on purpose: that property is a seam a test
        fixture may patch to boot on a document of its own, and a sequence that resolved the base
        itself would read past the patch and boot every such test on the real file. A fixture that
        must also keep the personal override tiers out patches this repository's sequence methods
        instead. A property patched with a ``str`` is what the ``Path(...)`` below is for.
        """
        relative_base = f"{INFERENCE_DIR_NAME}/{file_name}"
        relative_override = f"{INFERENCE_DIR_NAME}/{override_file_name}"
        if config_dir is not None:
            return [config_dir / relative_base, config_dir / relative_override]
        paths = [Path(resolved_base), self.global_config_dir / relative_override]
        project_dir = self.project_config_dir
        if project_dir is not None and project_dir != self.global_config_dir:
            paths.append(project_dir / relative_override)
        return paths

    @property
    def model_decks_dir_path(self) -> Path:
        """Resolve model decks directory from project dir or global dir."""
        return self.resolve_config_file(f"{INFERENCE_DIR_NAME}/{MODEL_DECKS_DIR_NAME}")

    def ensure_global_config_exists(self) -> None:
        """Create the global ~/.pipelex/ directory with kit template files if it doesn't exist."""
        global_dir = self.global_config_dir
        if global_dir.is_dir():
            return

        from pipelex.kit.paths import GIT_IGNORED_CONFIG_FILES, get_kit_configs_dir  # ruff: ignore[import-outside-top-level]

        config_template_dir = Path(str(get_kit_configs_dir()))
        global_dir.mkdir(parents=True, exist_ok=True)

        def copy_directory_structure(*, src_dir: Path, dst_dir: Path) -> None:
            """Recursively copy directory structure from kit templates."""
            for item in src_dir.iterdir():
                if item.name in GIT_IGNORED_CONFIG_FILES or item.name == ".DS_Store":
                    continue
                dst_item = dst_dir / item.name
                if item.is_dir():
                    dst_item.mkdir(parents=True, exist_ok=True)
                    copy_directory_structure(src_dir=item, dst_dir=dst_item)
                else:
                    shutil.copy2(item, dst_item)

        copy_directory_structure(src_dir=config_template_dir, dst_dir=global_dir)

        # Stamp the deck manifest so the boot-time staleness check has a baseline.
        # Imported lazily to avoid a circular import — config_loader is loaded very early.
        from pipelex.cogt.models.deck_manifest import compute_kit_manifest, write_manifest  # ruff: ignore[import-outside-top-level]

        write_manifest(compute_kit_manifest(), deck_dir=global_dir / "inference" / "deck")

    @classmethod
    def _override_files_for_dir(cls, config_dir: Path, *, include_run_mode: bool) -> list[Path]:
        """Build the override file sequence for a single config dir.

        Order matters: later files win on key collisions during deep-merge.

        This is the widest of the three override families a ``.pipelex/`` directory carries. The
        other two are narrower on purpose: a plugin config takes ``{name}_{environment}.toml`` and
        ``{name}_override.toml`` (``_plugin_override_files_for_dir``), and the two inference
        documents take a single ``*_override.toml`` each (``_inference_file_paths``).

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

    @classmethod
    def _plugin_override_files_for_dir(cls, config_dir: Path, *, name: str) -> list[Path]:
        """Build the plugin-config override sequence for one ``.pipelex`` dir.

        Order matters: later files win on key collisions during deep-merge. Mirrors
        ``_override_files_for_dir`` but keyed on a plugin's config ``name`` rather
        than ``"pipelex"``, and intentionally narrower — a plugin config carries no
        local / run_mode / temporary tiers (it is env-selected and deployment-baked,
        not developer-scratch-layered).

        Returns:
            Ordered list of candidate file paths (missing files are ignored at load time).
        """
        return [
            config_dir / f"{name}_{runtime_manager.environment}.toml",
            config_dir / f"{name}_override.toml",
        ]

    def load_plugin_config(
        self,
        *,
        name: str,
        package_dir: Path,
        schema: type[_PluginConfigT],
        extra_overrides: dict[str, Any] | None = None,
    ) -> _PluginConfigT:
        """Load, deep-merge and validate a plugin's config with env layering.

        Mirrors ``load_config``'s env-keyed layering for an arbitrary plugin whose
        config base name is ``name`` (e.g. ``"temporal"``). Every discovered plugin
        self-loads its config through this one helper so they all inherit identical
        env semantics: one image bakes every env file and ``PIPELEX_ENV``
        (``runtime_manager.environment``) selects which ``{name}_{env}.toml`` wins
        at runtime.

        Layers, deep-merged in order (later wins per leaf key):

        1. Packaged default: ``{package_dir}/{name}.toml`` — the plugin's bundled
           default, shipped inside its own distribution.
        2. Global override sequence from ``~/.pipelex/``:
           ``{name}_{environment}.toml`` then ``{name}_override.toml``.
        3. Project override sequence from ``{project_root}/.pipelex/`` (same two
           files), when a project dir is found and distinct from the global dir.
        4. Programmatic ``extra_overrides``, if any.

        Missing files at any tier are skipped, so the packaged default alone is a
        valid, fully-resolved config. Unlike ``load_config`` this never creates the
        global config dir or copies kit templates — a plugin config is purely
        additive layering over its own packaged default.

        Args:
            name: The plugin config base name, used for both the packaged default
                filename (``{name}.toml``) and the ``.pipelex`` override filenames.
            package_dir: Directory holding the plugin's packaged ``{name}.toml``
                (typically ``Path(__file__).parent`` in the plugin).
            schema: The pydantic model the merged config is validated into.
            extra_overrides: Optional dict deep-merged on top as the final layer.

        Returns:
            The merged config validated into ``schema``.
        """
        list_of_configs: list[Path] = [package_dir / f"{name}.toml"]
        list_of_configs.extend(self._plugin_override_files_for_dir(self.global_config_dir, name=name))
        project_dir = self.project_config_dir
        if project_dir is not None and project_dir != self.global_config_dir:
            list_of_configs.extend(self._plugin_override_files_for_dir(project_dir, name=name))

        merged = load_toml_from_path_and_merge_with_overrides(paths=list_of_configs)
        if extra_overrides:
            deep_update(merged, updates=extra_overrides)
        return schema.model_validate(merged)

    def load_config(self, *, extra_overrides: dict[str, Any] | None = None, config_dir: Path | None = None) -> dict[str, Any]:
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
                is bypassed and the load becomes package defaults + this directory (the
                package layer always applies — it is what the TOML overrides *are*
                overrides of), plus the unit-testing layer below when it applies.

        Returns:
            dict[str, Any]: The merged configuration dictionary
        """
        if config_dir is None:
            self.ensure_global_config_exists()
        merged = load_toml_from_path_and_merge_with_overrides(paths=self.config_file_paths(config_dir=config_dir))
        strip_reserved_meta(config_dict=merged)
        if extra_overrides:
            deep_update(merged, updates=extra_overrides)
        return merged

    def config_file_paths(self, *, config_dir: Path | None = None) -> list[Path]:
        """The ordered layers ``load_config`` merges, later files winning on a collision.

        Split out of ``load_config`` because boot tolerance has to replay the ledger over exactly
        the files that were merged, in exactly that order — a second list assembled beside this one
        would answer for a different machine the first time the layering changed. Pure: unlike
        ``load_config`` it never creates the global directory, so asking which files *would* be
        read does not bring one of them into existence.

        Missing files stay in the list and are skipped by whoever reads them.
        """
        is_unit_testing = runtime_manager.is_unit_testing

        list_of_configs: list[Path] = [self.pipelex_root_dir / CONFIG_NAME]

        if config_dir is not None:
            list_of_configs.append(config_dir / CONFIG_NAME)
            list_of_configs.extend(
                self._override_files_for_dir(config_dir, include_run_mode=not is_unit_testing),
            )
        else:
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

        return list_of_configs

    def load_config_validated(
        self,
        *,
        config_cls: type[_ConfigT],
        extra_overrides: dict[str, Any] | None = None,
        config_dir: Path | None = None,
    ) -> _ConfigT:
        """``load_config``, validated — and tolerant of a configuration the ledger can explain.

        This is the boot's entry point, and the tolerance is the whole reason it exists. A file
        left behind by a schema change should not stop the world: when validation fails, the
        surface's ledger is replayed over the same files **in memory**, the result is validated
        again, and a boot that succeeds says so in a warning naming the files and the
        ``pipelex migrate`` remedy — parked on the loader (``take_stale_configuration_warning``)
        for the boot to emit once logging exists. Nothing is written — only the explicit command
        writes.

        A configuration the ledger cannot explain raises exactly what it raised before: the retry
        is the only new behaviour, and it either recovers or gets out of the way.
        """
        config_dict = self.load_config(extra_overrides=extra_overrides, config_dir=config_dir)
        try:
            return config_cls.model_validate(config_dict)
        except CONFIG_REFUSED:
            recovered = self._config_the_ledger_can_explain(config_cls=config_cls, extra_overrides=extra_overrides, config_dir=config_dir)
            if recovered is None:
                raise
            return recovered

    def _config_the_ledger_can_explain(
        self,
        *,
        config_cls: type[_ConfigT],
        extra_overrides: dict[str, Any] | None,
        config_dir: Path | None,
    ) -> _ConfigT | None:
        """The same configuration with the ledger replayed over the user's files, or ``None``.

        ``None`` covers both ways this can decline — the ledger had nothing to say about these
        files, or it did and the result still does not validate. Neither is this method's to
        report: the caller re-raises the error the configuration actually produced, which is a
        truer account than "migration did not help" would be.

        The programmatic overrides are re-applied on top, because they are a layer of the load
        rather than a property of the files, and the replay only ever sees the files.
        """
        replayed = replay_surface_files_in_memory(surface_id=PIPELEX_CONFIG_SURFACE_ID, paths=self.config_file_paths(config_dir=config_dir))
        if replayed is None:
            return None
        config_dict = replayed.config_dict
        if extra_overrides:
            deep_update(config_dict, updates=extra_overrides)
        try:
            config = config_cls.model_validate(config_dict)
        except CONFIG_REFUSED:
            return None
        self._stale_warning = stale_configuration_warning(plans=replayed.plans, walked_dirs=self.existing_config_dirs)
        return config


config_manager = ConfigLoader()
