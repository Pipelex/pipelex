"""Utility functions for library management."""

import importlib
import inspect
import pkgutil
from importlib.abc import Traversable
from importlib.resources import files
from pathlib import Path
from typing import Any

from pipelex import log
from pipelex.core.interpreter import PipelexInterpreter
from pipelex.tools.func_registry import func_registry
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
                    excluded = {".venv", ".git", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", "node_modules", ".env", "results"}
                    if child.name not in excluded:
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

    # Directories to exclude from scanning to avoid loading invalid PLX files
    exclude_dirs = {".venv", ".git", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", "node_modules", ".env", "results"}

    # Filter out files in excluded directories
    filtered_files: list[Path] = []
    for file_path in all_files:
        # Check if any parent directory is in the exclude list
        should_exclude = any(part in exclude_dirs for part in file_path.parts)
        if not should_exclude:
            filtered_files.append(file_path)

    return filtered_files


def register_pipe_funcs_from_package(package_name: str, package: Any) -> int:
    """Register all @pipe_func decorated functions from a package.

    Args:
        package_name: Full name of the package (e.g. "pipelex.builder")
        package: The imported package object

    Returns:
        Number of functions registered
    """
    functions_registered = 0

    if not hasattr(package, "__path__"):
        log.warning(f"Package {package_name} has no __path__ attribute, cannot walk modules")
        return 0

    log.verbose(f"Walking package {package_name} at {package.__path__}")

    for _importer, modname, _ispkg in pkgutil.walk_packages(path=package.__path__, prefix=f"{package_name}.", onerror=lambda _: None):
        # Import the module
        module = importlib.import_module(modname)
        log.verbose(f"Imported {modname}")

        # Find @pipe_func decorated functions in this module
        for _name, obj in inspect.getmembers(module, inspect.isfunction):
            # Skip functions imported from other modules
            if obj.__module__ != modname:
                continue

            # Only process functions marked with @pipe_func
            if not func_registry.is_marked_pipe_func(obj):
                continue

            # Check for custom name from decorator
            custom_name = getattr(obj, "_pipe_func_name", None)
            func_name = custom_name if custom_name is not None else obj.__name__

            # Register the function
            func_registry.register_function(
                func=obj,
                name=func_name,
                should_raise_if_already_registered=False,
            )
            functions_registered += 1
            log.verbose(f"Registered @pipe_func: {func_name} from {modname}")

    return functions_registered
