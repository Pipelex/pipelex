"""Utility functions for library management."""

from importlib.abc import Traversable
from importlib.resources import files
from pathlib import Path

from pipelex import log
from pipelex.config import get_config
from pipelex.core.interpreter import PipelexInterpreter
from pipelex.tools.misc.file_utils import find_files_in_dir


def get_pipelex_plx_files_from_package() -> list[Path]:
    """Get all PLX files from the pipelex package using importlib.resources.

    This works reliably whether pipelex is installed as a wheel, from source,
    or as a relative path import.

    Returns:
        List of Path objects to PLX files in pipelex package
    """
    plx_files: list[Path] = []
    pipelex_package = files("pipelex")

    def _find_plx_in_traversable(traversable: Traversable, collected: list[Path]) -> None:
        """Recursively find .plx files in a Traversable."""
        excluded_dirs = get_config().pipelex.scan_config.excluded_dirs
        try:
            if not traversable.is_dir():
                return

            for child in traversable.iterdir():
                if child.is_file() and child.name.endswith(".plx"):
                    # Convert to path string for validation
                    plx_path_str = str(child)
                    if PipelexInterpreter.is_pipelex_file(Path(plx_path_str)):
                        collected.append(Path(plx_path_str))
                        log.verbose(f"Found pipelex package PLX file: {plx_path_str}")
                elif child.is_dir():
                    # Skip excluded directories
                    if child.name not in excluded_dirs:
                        _find_plx_in_traversable(child, collected)
        except (PermissionError, OSError) as exc:
            log.warning(f"Could not access {traversable}: {exc}")

    _find_plx_in_traversable(pipelex_package, plx_files)
    log.verbose(f"Found {len(plx_files)} PLX files in pipelex package")
    return plx_files


def get_pipelex_package_dir_for_imports() -> Path | None:
    """Get the pipelex package directory as a Path for importing Python modules.

    Returns:
        Path to the pipelex package directory, or None if not accessible as filesystem
    """
    pipelex_package = files("pipelex")
    try:
        # Try to convert to Path (works for filesystem paths)
        pkg_path = Path(str(pipelex_package))
        if pkg_path.exists() and pkg_path.is_dir():
            return pkg_path
    except (TypeError, ValueError, OSError) as exc:
        log.warning(f"Could not convert importlib.resources Traversable to filesystem Path: {exc}")
    return None


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
