"""Configuration files management for the init command."""

import os
import shutil

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


def init_config(reset: bool = False, dry_run: bool = False, target_dir: str | None = None) -> int:
    """Initialize pipelex configuration in the .pipelex directory. Does not install telemetry, just the main config and inference backends.

    Args:
        reset: Whether to overwrite existing files.
        dry_run: Whether to only print the files that would be copied, without actually copying them.
        target_dir: Explicit target directory. If None, uses config_manager.pipelex_config_dir.

    Returns:
        The number of files copied.
    """
    config_template_dir = str(get_kit_configs_dir())
    target_config_dir = target_dir or str(config_manager.pipelex_config_dir)

    os.makedirs(target_config_dir, exist_ok=True)

    try:
        copied_files: list[str] = []
        existing_files: list[str] = []

        def copy_directory_structure(src_dir: str, dst_dir: str, relative_path: str = "", dry_run: bool = False) -> None:
            """Recursively copy directory structure, handling existing files."""
            for item in os.listdir(src_dir):
                src_item = os.path.join(src_dir, item)
                dst_item = os.path.join(dst_dir, item)
                relative_item = os.path.join(relative_path, item) if relative_path else item

                # Skip git-ignored files and telemetry.toml (created when user is prompted)
                if item in INIT_SKIP_FILES:
                    continue

                if os.path.isdir(src_item):
                    if item in INIT_SKIP_DIRS:
                        continue
                    if not dry_run:
                        os.makedirs(dst_item, exist_ok=True)
                    copy_directory_structure(src_item, dst_item, relative_item, dry_run)
                elif os.path.exists(dst_item) and not reset:
                    existing_files.append(relative_item)
                else:
                    if not dry_run:
                        shutil.copy2(src_item, dst_item)
                    copied_files.append(relative_item)

        copy_directory_structure(src_dir=config_template_dir, dst_dir=target_config_dir, dry_run=dry_run)

        if dry_run:
            return len(copied_files)

    except OSError as exc:
        msg = f"Failed to initialize configuration: {exc}"
        raise PipelexCLIError(msg) from exc

    return len(copied_files)
