"""Configuration files management for the init command."""

import shutil
from pathlib import Path

from pipelex.cli.exceptions import PipelexCLIError
from pipelex.kit.paths import GIT_IGNORED_CONFIG_FILES, get_kit_configs_dir
from pipelex.system.configuration.config_loader import config_manager
from pipelex.system.telemetry.telemetry_config import TELEMETRY_CONFIG_FILE_NAME

# Files to skip when copying configs to user's .pipelex directory.
# Includes git-ignored files plus telemetry.toml (created when user is prompted).
INIT_SKIP_FILES: frozenset[str] = GIT_IGNORED_CONFIG_FILES | {TELEMETRY_CONFIG_FILE_NAME, ".DS_Store"}

# Directories to skip when copying configs to user's .pipelex directory.
# The inference directory is managed by the inference init step independently.
INIT_SKIP_DIRS: frozenset[str] = frozenset({"inference"})


def init_config(reset: bool = False, dry_run: bool = False, target_dir: Path | None = None) -> int:
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

    try:
        copied_files: list[str] = []
        existing_files: list[str] = []

        def copy_directory_structure(src_dir: Path, dst_dir: Path, relative_path: Path | None = None, dry_run: bool = False) -> None:
            """Recursively copy directory structure, handling existing files."""
            for src_item in src_dir.iterdir():
                item = src_item.name
                dst_item = dst_dir / item
                relative_item = (relative_path / item) if relative_path is not None else Path(item)

                # Skip git-ignored files and telemetry.toml (created when user is prompted)
                if item in INIT_SKIP_FILES:
                    continue

                if src_item.is_dir():
                    if item in INIT_SKIP_DIRS:
                        continue
                    if not dry_run:
                        dst_item.mkdir(parents=True, exist_ok=True)
                    copy_directory_structure(src_item, dst_item, relative_item, dry_run)
                elif dst_item.exists() and not reset:
                    existing_files.append(relative_item.as_posix())
                else:
                    if not dry_run:
                        shutil.copy2(src_item, dst_item)
                    copied_files.append(relative_item.as_posix())

        copy_directory_structure(src_dir=config_template_dir, dst_dir=target_config_dir, dry_run=dry_run)

        if dry_run:
            return len(copied_files)

    except OSError as exc:
        msg = f"Failed to initialize configuration: {exc}"
        raise PipelexCLIError(msg) from exc

    return len(copied_files)
