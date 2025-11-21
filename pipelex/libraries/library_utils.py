from pathlib import Path

from pipelex import log
from pipelex.config import get_config
from pipelex.core.interpreter import PipelexInterpreter
from pipelex.tools.misc.file_utils import find_files_in_dir


def find_plx_files_in_dir(dir_path: str, pattern: str, is_recursive: bool) -> list[Path]:
    """Find PLX files matching a pattern in a directory, excluding problematic directories.

    Args:
        dir_path: Directory path to search in
        pattern: File pattern to match (e.g. "*.plx")
        is_recursive: Whether to search recursively in subdirectories

    Returns:
        List of matching Path objects, filtered to exclude problematic directories
    """
    # Get all files using the base utility
    all_files = find_files_in_dir(dir_path, pattern, is_recursive)

    # Filter out files in excluded directories
    filtered_files: list[Path] = []
    excluded_dirs = get_config().pipelex.scan_config.excluded_dirs
    for file_path in all_files:
        # Check if any parent directory is in the exclude list
        should_exclude = any(part in excluded_dirs for part in file_path.parts)
        if not should_exclude:
            filtered_files.append(file_path)

    return filtered_files


def get_pipelex_plx_files_from_dirs(dirs: set[Path]) -> list[Path]:
    """Get all valid Pipelex PLX files from the given directories."""
    all_plx_paths: list[Path] = []

    for dir_path in dirs:
        if not dir_path.exists():
            log.debug(f"Directory does not exist, skipping: {dir_path}")
            continue

        # Find all .plx files in the directory, excluding problematic directories
        plx_files = find_plx_files_in_dir(
            dir_path=str(dir_path),
            pattern="*.plx",
            is_recursive=True,
        )

        # Filter to only include valid Pipelex files
        for plx_file in plx_files:
            if PipelexInterpreter.is_pipelex_file(plx_file):
                all_plx_paths.append(plx_file)
            else:
                log.debug(f"Skipping non-Pipelex PLX file: {plx_file}")

    return all_plx_paths
