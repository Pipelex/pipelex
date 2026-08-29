"""Locate a package inside a fetched clone by manifest identity.

Package location is by manifest identity, not directory path: the clone is scanned for
`METHODS.toml` files, and the requested package is the one whose manifest `address` equals
the requested address (a repo-root package) or whose `address + "/" + name` equals it (a
package in a library repo). No match, or more than one, is a loud error listing the
packages the clone does contain.

Address comparison is case-insensitive: GitHub owner and repository names are
case-insensitive, and manifests in the wild mix their casing.
"""

from pathlib import Path

from mthds.package.discovery import MANIFEST_FILENAME
from mthds.package.exceptions import ManifestError
from mthds.package.manifest.parser import parse_methods_toml
from mthds.package.manifest.schema import MethodsManifest
from pydantic import BaseModel, ConfigDict, Field

from pipelex.methods.exceptions import MethodPackageAmbiguityError, MethodPackageNotFoundError, MethodPackageTooLargeError
from pipelex.methods.fetch_limits import MAX_MANIFEST_FILE_BYTES, MAX_SCANNED_MANIFESTS
from pipelex.tools.typing.pydantic_utils import empty_list_factory_of

_SKIPPED_DIR_NAMES = {".git"}


class PackageCandidate(BaseModel):
    """One package found inside a clone: its directory and parsed manifest."""

    model_config = ConfigDict(frozen=True)

    package_dir: Path
    manifest: MethodsManifest

    @property
    def full_address(self) -> str:
        """The package's full address: `address + "/" + name` when named, else `address`."""
        if self.manifest.name:
            return f"{self.manifest.address}/{self.manifest.name}"
        return self.manifest.address


class PackageScan(BaseModel):
    """The result of scanning a clone for `METHODS.toml` manifests."""

    model_config = ConfigDict(frozen=True)

    candidates: list[PackageCandidate] = Field(default_factory=empty_list_factory_of(PackageCandidate))
    invalid_manifests: list[str] = Field(default_factory=list)


def scan_packages_in_clone(*, clone_root: Path) -> PackageScan:
    """Scan a clone for packages, tolerating unparseable manifests.

    The scan is bounded — the repository is fetched content: at most
    ``MAX_SCANNED_MANIFESTS`` manifests are considered, and a manifest larger than
    ``MAX_MANIFEST_FILE_BYTES`` is skipped (and reported) rather than read.

    Args:
        clone_root: The root directory of the fetched clone.

    Returns:
        The scan result: valid candidates and a note for each manifest that failed to parse.

    Raises:
        MethodPackageTooLargeError: If the repository contains more manifests than the scan ceiling.
    """
    candidates: list[PackageCandidate] = []
    invalid_manifests: list[str] = []
    manifest_count = 0
    for manifest_path in sorted(clone_root.rglob(MANIFEST_FILENAME)):
        relative_parts = manifest_path.relative_to(clone_root).parts
        if any(part in _SKIPPED_DIR_NAMES for part in relative_parts):
            continue
        manifest_count += 1
        if manifest_count > MAX_SCANNED_MANIFESTS:
            msg = f"The fetched repository contains more than {MAX_SCANNED_MANIFESTS} {MANIFEST_FILENAME} manifests; refusing to scan further."
            raise MethodPackageTooLargeError(msg)
        if manifest_path.stat().st_size > MAX_MANIFEST_FILE_BYTES:
            invalid_manifests.append(f"{'/'.join(relative_parts)}: exceeds the manifest size ceiling of {MAX_MANIFEST_FILE_BYTES} bytes, skipped")
            continue
        try:
            manifest = parse_methods_toml(manifest_path.read_text(encoding="utf-8"))
        except ManifestError as exc:
            invalid_manifests.append(f"{'/'.join(relative_parts)}: {exc.message}")
            continue
        candidates.append(PackageCandidate(package_dir=manifest_path.parent, manifest=manifest))
    return PackageScan(candidates=candidates, invalid_manifests=invalid_manifests)


def _matches(*, candidate: PackageCandidate, requested: str, clone_root: Path) -> bool:
    folded = requested.casefold()
    if candidate.manifest.name and candidate.full_address.casefold() == folded:
        # Library-repo identity: address + "/" + name, wherever the package sits in the tree.
        return True
    # Address-only identity belongs to a repo-root package: a nested package's identity is
    # address + "/" + name, so a bare repository address must not silently select it.
    return candidate.manifest.address.casefold() == folded and candidate.package_dir.resolve() == clone_root.resolve()


def locate_package_in_clone(*, clone_root: Path, requested_address: str) -> PackageCandidate:
    """Locate the requested package inside a clone by manifest identity.

    Args:
        clone_root: The root directory of the fetched clone.
        requested_address: The full requested address, e.g. `github.com/Pipelex/methods/documents`.

    Returns:
        The single matching package candidate.

    Raises:
        MethodPackageNotFoundError: If no package matches; the message lists the packages
            the clone does contain (and any manifests that failed to parse).
        MethodPackageAmbiguityError: If more than one package matches; the message lists them.
    """
    scan = scan_packages_in_clone(clone_root=clone_root)
    matches = [candidate for candidate in scan.candidates if _matches(candidate=candidate, requested=requested_address, clone_root=clone_root)]

    if len(matches) == 1:
        return matches[0]

    if not matches:
        if scan.candidates:
            available = ", ".join(sorted(candidate.full_address for candidate in scan.candidates))
            msg = f"No package at address '{requested_address}' in the fetched repository. Packages it contains: {available}."
        else:
            msg = f"No package (no {MANIFEST_FILENAME}) found in the repository fetched for '{requested_address}'."
        if scan.invalid_manifests:
            details = "; ".join(scan.invalid_manifests)
            msg = f"{msg} Manifests that failed to parse: {details}"
        raise MethodPackageNotFoundError(msg)

    matched = ", ".join(sorted(f"{candidate.full_address} ({candidate.package_dir.name}/)" for candidate in matches))
    msg = (
        f"Ambiguous method address '{requested_address}': it matches more than one package in the fetched repository: {matched}. "
        f"Use the package's full address (address + '/' + name) to disambiguate."
    )
    raise MethodPackageAmbiguityError(msg)
