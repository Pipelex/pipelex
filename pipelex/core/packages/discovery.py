from pathlib import Path

from pipelex.core.packages.manifest import MthdsPackageManifest
from pipelex.core.packages.manifest_parser import parse_methods_toml

MANIFEST_FILENAME = "METHODS.toml"


def find_package_manifest(bundle_path: Path) -> MthdsPackageManifest | None:
    """Walk up from a bundle file's directory to find the nearest METHODS.toml.

    Stops at the first METHODS.toml found, or when a .git/ directory is
    encountered, or at the filesystem root.

    Args:
        bundle_path: Path to a .mthds bundle file

    Returns:
        The parsed MthdsPackageManifest, or None if no manifest is found

    Raises:
        ManifestParseError: If a METHODS.toml is found but has invalid TOML syntax
        ManifestValidationError: If a METHODS.toml is found but fails validation
    """
    current = bundle_path.parent.resolve()

    while True:
        manifest_path = current / MANIFEST_FILENAME
        if manifest_path.is_file():
            content = manifest_path.read_text(encoding="utf-8")
            return parse_methods_toml(content)

        # Stop at .git boundary
        git_dir = current / ".git"
        if git_dir.exists():
            return None

        # Stop at filesystem root
        parent = current.parent
        if parent == current:
            return None

        current = parent
