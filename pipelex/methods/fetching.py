"""Fetch a method package by reference: clone, resolve the commit, locate, bound, refuse.

The clone rides the `mthds` fetch machinery as released (`clone_default_branch` for a bare
address, `clone_at_version` for `@<tag>`, both depth-1 with a bounded timeout). The commit
SHA of what was cloned is always resolved and recorded — tags can move, so the SHA is the
honest cache key and what keeps runs explainable.
"""

import subprocess  # ruff: ignore[suspicious-subprocess-import]
from pathlib import Path

from mthds.package.exceptions import VCSFetchError
from mthds.package.manifest.schema import MethodsManifest
from mthds.package.vcs_resolver import clone_at_version, clone_default_branch
from pydantic import BaseModel, ConfigDict

from pipelex.methods.exceptions import MethodFetchError, MethodPackageSymlinkError, MethodPackageTooLargeError
from pipelex.methods.fetch_limits import MAX_FETCHED_PACKAGE_FILES, MAX_FETCHED_PACKAGE_TOTAL_BYTES
from pipelex.methods.method_ref import MethodRef
from pipelex.methods.package_locator import locate_package_in_clone
from pipelex.methods.structures_check import ensure_no_structured_content_python

GIT_REV_PARSE_TIMEOUT_SECONDS = 30

_SKIPPED_DIR_NAMES = {".git"}


class MethodProvenance(BaseModel):
    """What a fetched-method run must record: address, tag, and the resolved commit SHA."""

    model_config = ConfigDict(frozen=True)

    address: str
    tag: str | None = None
    commit_sha: str


class FetchedMethodPackage(BaseModel):
    """The result of fetching a method package by reference."""

    model_config = ConfigDict(frozen=True)

    ref: MethodRef
    full_address: str
    commit_sha: str
    clone_dir: Path
    package_dir: Path
    manifest: MethodsManifest

    @property
    def provenance(self) -> MethodProvenance:
        return MethodProvenance(address=self.full_address, tag=self.ref.tag, commit_sha=self.commit_sha)


def resolve_head_commit_sha(*, clone_dir: Path) -> str:
    """Resolve the commit SHA a clone's HEAD points at.

    Args:
        clone_dir: The clone's root directory.

    Returns:
        The full commit SHA.

    Raises:
        MethodFetchError: If git is unavailable or the resolution fails.
    """
    try:
        result = subprocess.run(  # ruff: ignore[subprocess-without-shell-equals-true]
            ["git", "-C", str(clone_dir), "rev-parse", "HEAD"],  # ruff: ignore[start-process-with-partial-path]
            capture_output=True,
            text=True,
            check=True,
            timeout=GIT_REV_PARSE_TIMEOUT_SECONDS,
        )
    except FileNotFoundError as exc:
        msg = "git is not installed or not found on PATH"
        raise MethodFetchError(msg) from exc
    except subprocess.CalledProcessError as exc:
        msg = f"Failed to resolve the fetched commit in '{clone_dir}': {exc.stderr.strip()}"
        raise MethodFetchError(msg) from exc
    except subprocess.TimeoutExpired as exc:
        msg = f"Timed out resolving the fetched commit in '{clone_dir}'"
        raise MethodFetchError(msg) from exc
    return result.stdout.strip()


def ensure_cloned_at_tag(*, clone_dir: Path, ref: MethodRef) -> None:
    """Verify that a `@<tag>` clone actually checked out a tag, not a branch.

    `git clone --branch` accepts branch names too, so `@main` would otherwise silently pin
    a moving branch. A depth-1 clone at a tag carries `refs/tags/<tag>`; a clone at a
    branch does not — so the ref's presence in the clone is the discriminator.

    Args:
        clone_dir: The clone's root directory.
        ref: The method reference whose tag was cloned.

    Raises:
        MethodFetchError: If the cloned name is not a tag (or git fails).
    """
    try:
        result = subprocess.run(  # ruff: ignore[subprocess-without-shell-equals-true]
            ["git", "-C", str(clone_dir), "rev-parse", "--verify", "--quiet", f"refs/tags/{ref.tag}"],  # ruff: ignore[start-process-with-partial-path]
            capture_output=True,
            text=True,
            check=False,
            timeout=GIT_REV_PARSE_TIMEOUT_SECONDS,
        )
    except FileNotFoundError as exc:
        msg = "git is not installed or not found on PATH"
        raise MethodFetchError(msg) from exc
    except subprocess.TimeoutExpired as exc:
        msg = f"Timed out verifying tag '{ref.tag}' in '{clone_dir}'"
        raise MethodFetchError(msg) from exc
    if result.returncode != 0:
        msg = (
            f"'{ref.tag}' in method reference '{ref.ref_str}' does not name a git tag on the repository — "
            f"`@<tag>` pins a git tag (recommended form vX.Y.Z); branch names are not accepted."
        )
        raise MethodFetchError(msg)


def ensure_package_within_bounds(*, package_dir: Path, package_address: str) -> None:
    """Reject a selected package that exceeds the fetched-package ceilings or carries a symlink.

    Symlinks are refused outright: the structures scan and these bounds walk the tree without
    following links, while a later copy would copy the link's *target* — a scan bypass, and a way
    to exfiltrate host files into the installed store. Fetched packages have no legitimate use
    for symlinks.

    Args:
        package_dir: The selected package directory.
        package_address: The package's full address, named in the error.

    Raises:
        MethodPackageTooLargeError: If the package exceeds the file-count or total-bytes cap.
        MethodPackageSymlinkError: If the package directory, or anything inside it, is a symlink.
    """
    if package_dir.is_symlink():
        msg = f"Method package '{package_address}' is a symlink — fetched packages must not contain symlinks."
        raise MethodPackageSymlinkError(msg)
    file_count = 0
    total_bytes = 0
    for file_path in package_dir.rglob("*"):
        relative_parts = file_path.relative_to(package_dir).parts
        if any(part in _SKIPPED_DIR_NAMES for part in relative_parts):
            continue
        if file_path.is_symlink():
            relative = "/".join(relative_parts)
            msg = f"Method package '{package_address}' contains a symlink ('{relative}') — fetched packages must not contain symlinks."
            raise MethodPackageSymlinkError(msg)
        if not file_path.is_file():
            continue
        file_count += 1
        total_bytes += file_path.stat().st_size
        if file_count > MAX_FETCHED_PACKAGE_FILES:
            msg = f"Method package '{package_address}' exceeds the fetched-package ceiling of {MAX_FETCHED_PACKAGE_FILES} files."
            raise MethodPackageTooLargeError(msg)
        if total_bytes > MAX_FETCHED_PACKAGE_TOTAL_BYTES:
            msg = f"Method package '{package_address}' exceeds the fetched-package ceiling of {MAX_FETCHED_PACKAGE_TOTAL_BYTES} bytes in total."
            raise MethodPackageTooLargeError(msg)


def fetch_method_package(
    *,
    ref: MethodRef,
    dest_dir: Path,
    clone_url: str | None = None,
    refuse_structures: bool = False,
) -> FetchedMethodPackage:
    """Fetch the method package a reference points at.

    Clones the repository (at the tag when the reference names one, at the default branch
    otherwise), resolves the fetched commit SHA, locates the package by manifest identity,
    enforces the fetched-package ceilings, and — when *refuse_structures* is set — refuses
    a package that declares in-process Python structure classes before anything can load it.

    Args:
        ref: The parsed method reference.
        dest_dir: The directory to clone into (must not already contain a clone).
        clone_url: Override for the derived clone URL (tests, non-default remotes).
        refuse_structures: Refuse `StructuredContent`-declaring packages (the runner's
            hard-refusal mode; the CLI scans separately and warns instead).

    Returns:
        The fetched package with its provenance.

    Raises:
        MethodFetchError: If the clone fails, `@<tag>` does not name a tag, or commit resolution fails.
        MethodPackageNotFoundError: If no package matches the requested address.
        MethodPackageAmbiguityError: If more than one package matches.
        MethodPackageTooLargeError: If the selected package exceeds the ceilings.
        MethodPackageSymlinkError: If the selected package contains a symlink.
        MethodStructuresRefusedError: If *refuse_structures* is set and the package
            declares structure classes.
    """
    effective_clone_url = clone_url or ref.clone_url
    try:
        if ref.tag:
            clone_at_version(clone_url=effective_clone_url, version_tag=ref.tag, destination=dest_dir)
        else:
            clone_default_branch(clone_url=effective_clone_url, destination=dest_dir)
    except VCSFetchError as exc:
        msg = f"Failed to fetch method '{ref.ref_str}': {exc.message}"
        raise MethodFetchError(msg) from exc

    if ref.tag:
        ensure_cloned_at_tag(clone_dir=dest_dir, ref=ref)

    commit_sha = resolve_head_commit_sha(clone_dir=dest_dir)
    located = locate_package_in_clone(clone_root=dest_dir, requested_address=ref.address)
    ensure_package_within_bounds(package_dir=located.package_dir, package_address=located.full_address)
    if refuse_structures:
        ensure_no_structured_content_python(package_dir=located.package_dir, package_address=located.full_address)

    return FetchedMethodPackage(
        ref=ref,
        full_address=located.full_address,
        commit_sha=commit_sha,
        clone_dir=dest_dir,
        package_dir=located.package_dir,
        manifest=located.manifest,
    )
