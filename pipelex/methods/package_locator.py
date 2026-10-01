"""Locate a package inside a fetched clone by manifest identity.

Package location is by manifest identity, not directory path: the clone is scanned for
`METHODS.toml` files, and the requested package is the one whose manifest `address` equals
the requested address (a repo-root package) or whose `address + "/" + name` equals it (a
package in a library repo). No match, or more than one, is a loud error listing the
packages the clone does contain.

Address comparison is case-insensitive: GitHub owner and repository names are
case-insensitive, and manifests in the wild mix their casing.
"""

import stat
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
    skipped_manifests: list[str] = Field(default_factory=list)


class _ManifestRead(BaseModel):
    """What reading one manifest yielded: its text, or the reason it was skipped."""

    model_config = ConfigDict(frozen=True)

    text: str | None = None
    skip_reason: str | None = None


def _read_manifest_text(*, manifest_path: Path) -> _ManifestRead:
    """Read one fetched manifest, accepting only a regular file within the size ceiling.

    Nothing about a fetched manifest is trusted. `lstat` establishes its type without following
    a link, so a symlink, which could point anywhere on the fetching machine, and any other
    file that is not regular are skipped without ever being opened. The read is bounded by
    itself rather than by a size reported beforehand, which a link to a device such as
    `/dev/zero` reports as 0. A skip reason never names a link's target or an absolute path,
    both of which belong to the fetching machine.
    """
    try:
        mode = manifest_path.lstat().st_mode
    except OSError:
        return _ManifestRead(skip_reason="could not be inspected, skipped")
    if stat.S_ISLNK(mode):
        return _ManifestRead(skip_reason="is a symlink, skipped (fetched manifests must be regular files)")
    if not stat.S_ISREG(mode):
        return _ManifestRead(skip_reason="is not a regular file, skipped")
    try:
        with manifest_path.open("rb") as handle:
            raw = handle.read(MAX_MANIFEST_FILE_BYTES + 1)
    except OSError:
        return _ManifestRead(skip_reason="could not be read, skipped")
    if len(raw) > MAX_MANIFEST_FILE_BYTES:
        return _ManifestRead(skip_reason=f"exceeds the manifest size ceiling of {MAX_MANIFEST_FILE_BYTES} bytes, skipped")
    try:
        return _ManifestRead(text=raw.decode("utf-8"))
    except UnicodeDecodeError:
        return _ManifestRead(skip_reason="is not valid UTF-8, skipped")


def scan_packages_in_clone(*, clone_root: Path) -> PackageScan:
    """Scan a clone for packages, skipping and reporting every manifest it cannot use.

    The scan is bounded, since the repository is fetched content: at most
    ``MAX_SCANNED_MANIFESTS`` manifests are considered, and each is read only if it is a
    regular file. A manifest that is a symlink or not a regular file is skipped without being
    opened, so the scan never reads outside the clone; one that holds more than
    ``MAX_MANIFEST_FILE_BYTES`` is skipped after a read that stops at the ceiling; one that is
    not valid UTF-8 or fails to parse is skipped too. Each skip is noted with the manifest's
    path relative to the clone.

    Args:
        clone_root: The root directory of the fetched clone.

    Returns:
        The scan result: valid candidates and a note for each skipped manifest.

    Raises:
        MethodPackageTooLargeError: If the repository contains more manifests than the scan ceiling.
    """
    candidates: list[PackageCandidate] = []
    skipped_manifests: list[str] = []
    manifest_count = 0
    for manifest_path in sorted(clone_root.rglob(MANIFEST_FILENAME)):
        relative_parts = manifest_path.relative_to(clone_root).parts
        if any(part in _SKIPPED_DIR_NAMES for part in relative_parts):
            continue
        manifest_count += 1
        if manifest_count > MAX_SCANNED_MANIFESTS:
            msg = f"The fetched repository contains more than {MAX_SCANNED_MANIFESTS} {MANIFEST_FILENAME} manifests; refusing to scan further."
            raise MethodPackageTooLargeError(msg)
        relative_path = "/".join(relative_parts)
        manifest_read = _read_manifest_text(manifest_path=manifest_path)
        if manifest_read.text is None:
            skipped_manifests.append(f"{relative_path}: {manifest_read.skip_reason}")
            continue
        try:
            manifest = parse_methods_toml(manifest_read.text)
        except ManifestError as exc:
            skipped_manifests.append(f"{relative_path}: {exc.message}")
            continue
        candidates.append(PackageCandidate(package_dir=manifest_path.parent, manifest=manifest))
    return PackageScan(candidates=candidates, skipped_manifests=skipped_manifests)


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
            the clone does contain, and every manifest the scan skipped (a symlink, a file that
            is not regular, one over the size ceiling, not UTF-8, or failing to parse) with why.
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
        if scan.skipped_manifests:
            details = "; ".join(scan.skipped_manifests)
            msg = f"{msg} Manifests skipped: {details}"
        raise MethodPackageNotFoundError(msg)

    matched = ", ".join(sorted(f"{candidate.full_address} ({candidate.package_dir.name}/)" for candidate in matches))
    msg = (
        f"Ambiguous method address '{requested_address}': it matches more than one package in the fetched repository: {matched}. "
        f"Use the package's full address (address + '/' + name) to disambiguate."
    )
    raise MethodPackageAmbiguityError(msg)
