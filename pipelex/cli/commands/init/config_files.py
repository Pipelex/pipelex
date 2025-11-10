"""Configuration files management for the init command."""

import os
import shutil

import typer

from pipelex.exceptions import PipelexCLIError
from pipelex.kit.paths import get_kit_configs_dir
from pipelex.system.configuration.config_loader import config_manager
from pipelex.system.telemetry.telemetry_config import TELEMETRY_CONFIG_FILE_NAME


def init_config(reset: bool = False, dry_run: bool = False) -> int:
    """Initialize pipelex configuration in the .pipelex directory. Does not install telemetry, just the main config dans inference backends.

    Args:
        reset: Whether to overwrite existing files.
        dry_run: Whether to only print the files that would be copied, without actually copying them.

    Returns:
        The number of files copied.
    """
    config_template_dir = str(get_kit_configs_dir())
    target_config_dir = config_manager.pipelex_config_dir

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

                # Skip telemetry.toml - it will be created when user is prompted
                if item == TELEMETRY_CONFIG_FILE_NAME:
                    continue

                if os.path.isdir(src_item):
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

        # Report results
        if copied_files:
            typer.echo(f"✅ Copied {len(copied_files)} files to {target_config_dir}:")
            for file in sorted(copied_files):
                typer.echo(f"   • {file}")

        if existing_files:
            typer.echo(f"ℹ️  Skipped {len(existing_files)} existing files (use --reset to overwrite):")
            for file in sorted(existing_files):
                typer.echo(f"   • {file}")

        if not copied_files and not existing_files:
            typer.echo(f"✅ Configuration directory {target_config_dir} is already up to date")

    except Exception as exc:
        msg = f"Failed to initialize configuration: {exc}"
        raise PipelexCLIError(msg) from exc

    return len(copied_files)
