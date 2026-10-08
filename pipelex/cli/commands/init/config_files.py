"""Configuration files management for the init command."""

from pathlib import Path

from pipelex.cli.exceptions import PipelexCLIError
from pipelex.kit.paths import GIT_IGNORED_CONFIG_FILES, get_kit_configs_dir
from pipelex.kit.template_copy import copy_kit_templates
from pipelex.migration.gitignore import ensure_config_dir_gitignore
from pipelex.system.configuration.config_loader import config_manager
from pipelex.system.telemetry.telemetry_config import TELEMETRY_CONFIG_FILE_NAME

# Files to skip when copying configs to user's .pipelex directory.
# Includes git-ignored files plus telemetry.toml (created when user is prompted).
INIT_SKIP_FILES: frozenset[str] = GIT_IGNORED_CONFIG_FILES | {TELEMETRY_CONFIG_FILE_NAME, ".DS_Store"}

# Directories to skip when copying configs to user's .pipelex directory.
# The inference directory is managed by the inference init step independently.
INIT_SKIP_DIRS: frozenset[str] = frozenset({"inference"})


def init_config(*, reset: bool = False, dry_run: bool = False, target_dir: Path | None = None) -> int:
    """Initialize pipelex configuration in the .pipelex directory. Does not install telemetry, just the main config and inference backends.

    Args:
        reset: Whether to overwrite existing files.
        dry_run: Whether to only print the files that would be copied, without actually copying them.
        target_dir: Explicit target directory. If None, uses config_manager.pipelex_config_dir.

    Returns:
        The number of files copied.
    """
    config_template_dir = Path(str(get_kit_configs_dir()))
    target_config_dir = target_dir or config_manager.pipelex_config_dir

    target_config_dir.mkdir(parents=True, exist_ok=True)

    if not dry_run:
        # Before anything is copied in, so the directory is never briefly a source of untracked
        # noise. `pipelex migrate` ensures the same rule for a directory that predates it.
        ensure_config_dir_gitignore(directory=target_config_dir)

    try:
        # The same walk the first boot fills the home configuration directory with, so the two agree on
        # which files a directory receives.
        copied_files = copy_kit_templates(
            template_dir=config_template_dir,
            target_dir=target_config_dir,
            skip_names=INIT_SKIP_FILES | INIT_SKIP_DIRS,
            overwrite=reset,
            dry_run=dry_run,
        )
    except OSError as exc:
        msg = f"Failed to initialize configuration: {exc}"
        raise PipelexCLIError(msg) from exc

    return len(copied_files)
