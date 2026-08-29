"""Discovery and lookup of installed methods from the filesystem.

Scans ~/.mthds/methods/ (global) and .mthds/methods/ (project-local) for
installed method packages.
"""

from pathlib import Path

from mthds.package.discovery import MANIFEST_FILENAME
from mthds.package.manifest.parser import parse_methods_toml
from mthds.package.manifest.schema import MethodsManifest
from pydantic import BaseModel

from pipelex.methods.fetching import MethodProvenance

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
    """An installed method discovered from the filesystem.

    ``provenance`` is set only for methods fetched by reference: the address, the tag when
    one was named, and the commit SHA of what was actually cloned.
    """

    name: str
    path: Path
    manifest: MethodsManifest
    mthds_files: list[Path]
    provenance: MethodProvenance | None = None


def discover_installed_methods(
    *,
    include_global: bool = True,
    include_project: bool = True,
    extra_search_dirs: list[Path] | None = None,
) -> list[InstalledMethod]:
    """Scan ~/.mthds/methods/ and ./.mthds/methods/ for installed methods.

    For each subdirectory with a METHODS.toml:
    - Parse the manifest and get ``name`` from it (falls back to directory name)
    - Collect all .mthds files recursively

    Args:
        include_global: Whether to scan the global methods directory
        include_project: Whether to scan the project-local methods directory
        extra_search_dirs: Additional .mthds/methods/ directories to scan

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

    if extra_search_dirs:
        for extra_dir in extra_search_dirs:
            resolved = extra_dir.resolve()
            if resolved.is_dir() and resolved not in seen_dirs:
                dirs_to_scan.append(resolved)
                seen_dirs.add(resolved)

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


def discover_method_at(method_dir: Path, *, seen_dirs: set[Path]) -> InstalledMethod | None:
    """Try to discover a single method at *method_dir*.

    Returns an ``InstalledMethod`` if the directory contains a ``METHODS.toml``,
    or ``None`` otherwise. Updates *seen_dirs* in place.
    """
    resolved = method_dir.resolve()
    if resolved in seen_dirs or not resolved.is_dir():
        return None
    seen_dirs.add(resolved)

    manifest_path = resolved / MANIFEST_FILENAME
    if not manifest_path.is_file():
        return None

    content = manifest_path.read_text(encoding="utf-8")
    manifest = parse_methods_toml(content)

    name = manifest.name if manifest.name is not None else resolved.name

    mthds_files = sorted(resolved.rglob("*.mthds"))

    return InstalledMethod(
        name=name,
        path=resolved,
        manifest=manifest,
        mthds_files=mthds_files,
    )


def discover_methods_from_library_dirs(
    library_dirs: list[str],
) -> list[InstalledMethod]:
    """Discover methods from explicit library directories.

    For each directory in ``library_dirs``:

    - If the directory itself contains a ``METHODS.toml``, it is recognised as a
      method (the ``-L`` flag points directly to the method directory).
    - Otherwise, the directory is searched recursively for ``METHODS.toml`` files,
      so ``-L .`` finds methods at any depth below the current directory.

    Args:
        library_dirs: Paths to directories that may contain methods

    Returns:
        A list of discovered installed methods, deduplicated by resolved path
    """
    methods: list[InstalledMethod] = []
    seen_dirs: set[Path] = set()

    for dir_str in library_dirs:
        lib_dir = Path(dir_str).resolve()
        if not lib_dir.is_dir():
            continue

        # First, check if the directory itself is a method
        method = discover_method_at(lib_dir, seen_dirs=seen_dirs)
        if method is not None:
            methods.append(method)
            continue

        # Otherwise, recursively find all METHODS.toml files below this directory
        for manifest_path in sorted(lib_dir.rglob(MANIFEST_FILENAME)):
            method_dir = manifest_path.parent
            sub_method = discover_method_at(method_dir, seen_dirs=seen_dirs)
            if sub_method is not None:
                methods.append(sub_method)

    return methods


def find_method_by_full_address(
    full_address: str,
    *,
    methods: list[InstalledMethod] | None = None,
    extra_search_dirs: list[Path] | None = None,
) -> InstalledMethod | None:
    """Find an installed method by its full address (manifest address + "/" + name).

    The full address is computed as ``manifest.address + "/" + name`` for each
    discovered installed method. For example, a package with
    ``address = "github.com/Pipelex/methods"`` and ``name = "documents"`` has
    the full address ``"github.com/Pipelex/methods/documents"``.

    Args:
        full_address: The full package address to search for
        methods: Pre-discovered methods list; if None, runs discovery
        extra_search_dirs: Additional .mthds/methods/ directories to scan

    Returns:
        The matching InstalledMethod, or None if no match is found
    """
    if methods is None:
        methods = discover_installed_methods(extra_search_dirs=extra_search_dirs)

    for method in methods:
        candidate_address = f"{method.manifest.address}/{method.name}"
        if candidate_address == full_address:
            return method

    return None


def find_method_by_name(
    method_name: str,
    *,
    methods: list[InstalledMethod] | None = None,
    library_dirs: list[str] | None = None,
) -> InstalledMethod:
    """Find a method by name.

    Args:
        method_name: The method name to search for
        methods: Pre-discovered methods list; if None, runs discovery
        library_dirs: Additional directories to check for methods

    Returns:
        The matching InstalledMethod

    Raises:
        MethodNotFoundError: If no method matches the given name
        DuplicateMethodNameError: If multiple methods share the same name
    """
    if methods is None:
        methods = discover_installed_methods()

    # Merge in methods discovered from library dirs, deduplicating by resolved path
    all_methods = list(methods)
    if library_dirs:
        seen_paths = {method.path.resolve() for method in all_methods}
        for lib_method in discover_methods_from_library_dirs(library_dirs):
            if lib_method.path.resolve() not in seen_paths:
                all_methods.append(lib_method)
                seen_paths.add(lib_method.path.resolve())

    matches = [method for method in all_methods if method.name == method_name]

    if len(matches) == 0:
        msg = f"No installed method named '{method_name}' found."
        raise MethodNotFoundError(msg)
    if len(matches) > 1:
        locations = ", ".join(str(method.path) for method in matches)
        msg = f"Multiple methods named '{method_name}' found: {locations}"
        raise DuplicateMethodNameError(msg)

    return matches[0]
