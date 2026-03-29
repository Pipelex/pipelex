from importlib.resources import files
from pathlib import Path

import pipelex.builder as builder_pkg  # package import — used for __file__ path
from pipelex import log
from pipelex.config import get_config
from pipelex.core.interpreter.helpers import MTHDS_EXTENSION, is_pipelex_file
from pipelex.tools.misc.file_utils import find_files_in_dir
from pipelex.types import Traversable


def get_pipelex_mthds_files_from_package() -> list[Path]:
    """Get all MTHDS files from the pipelex package using importlib.resources.

    This works reliably whether pipelex is installed as a wheel, from source,
    or as a relative path import.

    Returns:
        List of Path objects to MTHDS files in pipelex package
    """
    mthds_files: list[Path] = []
    pipelex_package = files("pipelex")

    def _find_mthds_in_traversable(traversable: Traversable, collected: list[Path]) -> None:
        """Recursively find .mthds files in a Traversable."""
        excluded_dirs = get_config().pipelex.scan_config.excluded_dirs
        try:
            if not traversable.is_dir():
                return

            for child in sorted(traversable.iterdir(), key=lambda entry: entry.name):
                if child.is_file() and is_pipelex_file(Path(child.name)):
                    mthds_path_str = str(child)
                    collected.append(Path(mthds_path_str))
                    log.verbose(f"Found pipelex package MTHDS file: {mthds_path_str}")
                elif child.is_dir():
                    # Skip excluded directories
                    if child.name not in excluded_dirs:
                        _find_mthds_in_traversable(child, collected)
        except (PermissionError, OSError) as exc:
            log.warning(f"Could not access {traversable}: {exc}")

    _find_mthds_in_traversable(pipelex_package, mthds_files)
    log.verbose(f"Found {len(mthds_files)} MTHDS files in pipelex package")
    return mthds_files


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


def get_pipelex_mthds_files_from_dirs(dirs: set[Path]) -> list[Path]:
    """Get all valid Pipelex MTHDS files from the given directories."""
    all_mthds_paths: list[Path] = []

    for dir_path in dirs:
        if not dir_path.exists():
            log.debug(f"Directory does not exist, skipping: {dir_path}")
            continue

        # Find all .mthds files in the directory, excluding problematic directories
        mthds_files = find_files_in_dir(
            dir_path=str(dir_path),
            pattern=f"*{MTHDS_EXTENSION}",
            excluded_dirs=list(get_config().pipelex.scan_config.excluded_dirs),
            force_include_dirs=[str(Path(builder_pkg.__file__).parent)],
        )

        # Filter to only include valid Pipelex files
        for mthds_file in mthds_files:
            if is_pipelex_file(mthds_file):
                all_mthds_paths.append(mthds_file)
            else:
                log.debug(f"Skipping non-Pipelex MTHDS file: {mthds_file}")
    return all_mthds_paths
