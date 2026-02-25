"""Discovery and lookup of installed methods from the filesystem.

Scans ~/.mthds/methods/ (global) and .mthds/methods/ (project-local) for
installed method packages.
"""

from pathlib import Path

from mthds.package.discovery import MANIFEST_FILENAME
from mthds.package.manifest.parser import parse_methods_toml
from mthds.package.manifest.schema import MethodsManifest
from pydantic import BaseModel

GLOBAL_METHODS_DIR = Path.home() / ".mthds" / "methods"
PROJECT_METHODS_DIR = Path(".mthds") / "methods"


class MethodNotFoundError(Exception):
    """Raised when no installed method matches the given name."""

    def __init__(self, message: str = "") -> None:
        self.message = message
        super().__init__(message)


class DuplicateMethodNameError(Exception):
    """Raised when two installed methods share the same name."""

    def __init__(self, message: str = "") -> None:
        self.message = message
        super().__init__(message)


class InstalledMethod(BaseModel):
    """An installed method discovered from the filesystem."""

    name: str
    path: Path
    manifest: MethodsManifest
    mthds_files: list[Path]


def discover_installed_methods(
    include_global: bool = True,
    include_project: bool = True,
) -> list[InstalledMethod]:
    """Scan ~/.mthds/methods/ and ./.mthds/methods/ for installed methods.

    For each subdirectory with a METHODS.toml:
    - Parse the manifest and get ``name`` from it
    - The directory name must match manifest.name
    - Collect all .mthds files recursively

    Args:
        include_global: Whether to scan the global methods directory
        include_project: Whether to scan the project-local methods directory

    Returns:
        A list of discovered installed methods
    """
    methods: list[InstalledMethod] = []
    seen_dirs: set[Path] = set()
    dirs_to_scan: list[Path] = []

    if include_project:
        project_dir = PROJECT_METHODS_DIR.resolve()
        if project_dir.is_dir():
            dirs_to_scan.append(project_dir)
            seen_dirs.add(project_dir)

    if include_global:
        global_dir = GLOBAL_METHODS_DIR.resolve()
        if global_dir.is_dir() and global_dir not in seen_dirs:
            dirs_to_scan.append(global_dir)

    for methods_dir in dirs_to_scan:
        for subdir in sorted(methods_dir.iterdir()):
            if not subdir.is_dir():
                continue
            manifest_path = subdir / MANIFEST_FILENAME
            if not manifest_path.is_file():
                continue

            content = manifest_path.read_text(encoding="utf-8")
            manifest = parse_methods_toml(content)

            name = manifest.name if manifest.name is not None else subdir.name

            mthds_files = sorted(subdir.rglob("*.mthds"))

            methods.append(
                InstalledMethod(
                    name=name,
                    path=subdir,
                    manifest=manifest,
                    mthds_files=mthds_files,
                )
            )

    return methods


def find_method_by_name(
    method_name: str,
    methods: list[InstalledMethod] | None = None,
) -> InstalledMethod:
    """Find a method by name.

    Args:
        method_name: The method name to search for
        methods: Pre-discovered methods list; if None, runs discovery

    Returns:
        The matching InstalledMethod

    Raises:
        MethodNotFoundError: If no method matches the given name
        DuplicateMethodNameError: If multiple methods share the same name
    """
    if methods is None:
        methods = discover_installed_methods()

    matches = [method for method in methods if method.name == method_name]

    if len(matches) == 0:
        msg = f"No installed method named '{method_name}' found."
        raise MethodNotFoundError(msg)
    if len(matches) > 1:
        locations = ", ".join(str(method.path) for method in matches)
        msg = f"Multiple methods named '{method_name}' found: {locations}"
        raise DuplicateMethodNameError(msg)

    return matches[0]
