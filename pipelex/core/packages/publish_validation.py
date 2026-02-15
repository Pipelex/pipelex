"""Publish validation logic for MTHDS packages.

Validates that a package is ready for distribution by checking manifest
completeness, export consistency, bundle validity, dependency pinning,
lock file freshness, and git tag readiness.
"""

import subprocess  # noqa: S404
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from pipelex.core.bundles.pipelex_bundle_blueprint import PipelexBundleBlueprint
from pipelex.core.packages.bundle_scanner import scan_bundles_for_domain_info
from pipelex.core.packages.dependency_resolver import collect_mthds_files
from pipelex.core.packages.discovery import MANIFEST_FILENAME
from pipelex.core.packages.exceptions import LockFileError, ManifestError, PublishValidationError
from pipelex.core.packages.lock_file import LOCK_FILENAME, parse_lock_file
from pipelex.core.packages.manifest import MthdsPackageManifest
from pipelex.core.packages.manifest_parser import parse_methods_toml
from pipelex.core.packages.visibility import check_visibility_for_blueprints
from pipelex.tools.typing.pydantic_utils import empty_list_factory_of
from pipelex.types import StrEnum


class IssueLevel(StrEnum):
    """Severity level for a publish validation issue."""

    ERROR = "error"
    WARNING = "warning"

    @property
    def is_error(self) -> bool:
        match self:
            case IssueLevel.ERROR:
                return True
            case IssueLevel.WARNING:
                return False

    @property
    def is_warning(self) -> bool:
        match self:
            case IssueLevel.ERROR:
                return False
            case IssueLevel.WARNING:
                return True


class IssueCategory(StrEnum):
    """Category of a publish validation issue."""

    MANIFEST = "manifest"
    BUNDLE = "bundle"
    EXPORT = "export"
    DEPENDENCY = "dependency"
    LOCK_FILE = "lock_file"
    GIT = "git"
    VISIBILITY = "visibility"


class PublishValidationIssue(BaseModel):
    """A single validation issue found during publish readiness check."""

    model_config = ConfigDict(frozen=True)

    level: IssueLevel = Field(strict=False)
    category: IssueCategory = Field(strict=False)
    message: str
    suggestion: str | None = None


class PublishValidationResult(BaseModel):
    """Aggregated result of publish validation."""

    model_config = ConfigDict(frozen=True)

    issues: list[PublishValidationIssue] = Field(default_factory=empty_list_factory_of(PublishValidationIssue))
    package_version: str | None = None

    @property
    def is_publishable(self) -> bool:
        """Package is publishable if there are no ERROR-level issues."""
        return not any(issue.level.is_error for issue in self.issues)


# ---------------------------------------------------------------------------
# Private validation helpers
# ---------------------------------------------------------------------------


def _check_manifest_exists(package_root: Path) -> tuple[MthdsPackageManifest | None, list[PublishValidationIssue]]:
    """Check that METHODS.toml exists and parses successfully.

    Returns:
        Tuple of (parsed manifest or None, list of issues)
    """
    manifest_path = package_root / MANIFEST_FILENAME
    if not manifest_path.is_file():
        return None, [
            PublishValidationIssue(
                level=IssueLevel.ERROR,
                category=IssueCategory.MANIFEST,
                message=f"{MANIFEST_FILENAME} not found in {package_root}",
                suggestion=f"Create a {MANIFEST_FILENAME} with 'pipelex pkg init'",
            )
        ]

    content = manifest_path.read_text(encoding="utf-8")
    try:
        manifest = parse_methods_toml(content)
    except ManifestError as exc:
        return None, [
            PublishValidationIssue(
                level=IssueLevel.ERROR,
                category=IssueCategory.MANIFEST,
                message=f"{MANIFEST_FILENAME} parse error: {exc.message}",
            )
        ]

    return manifest, []


def _check_manifest_fields(manifest: MthdsPackageManifest) -> list[PublishValidationIssue]:
    """Check manifest field completeness (authors, license).

    Note: address, version, and description are validated by Pydantic validators
    in MthdsPackageManifest during parse_methods_toml(). If parsing succeeded,
    those fields are guaranteed valid — no need to re-check here.
    """
    issues: list[PublishValidationIssue] = []

    if not manifest.authors:
        issues.append(
            PublishValidationIssue(
                level=IssueLevel.WARNING,
                category=IssueCategory.MANIFEST,
                message="No authors specified",
                suggestion='Add authors = ["Your Name"] to [package] in METHODS.toml',
            )
        )

    if not manifest.license:
        issues.append(
            PublishValidationIssue(
                level=IssueLevel.WARNING,
                category=IssueCategory.MANIFEST,
                message="No license specified",
                suggestion='Add license = "MIT" (or other) to [package] in METHODS.toml',
            )
        )

    return issues


def _check_bundles(
    package_root: Path,
) -> tuple[dict[str, list[str]], list[PipelexBundleBlueprint], list[PublishValidationIssue]]:
    """Check that .mthds files exist and parse without error.

    Returns:
        Tuple of (domain_pipes mapping, parsed blueprints, list of issues)
    """
    issues: list[PublishValidationIssue] = []

    mthds_files = collect_mthds_files(package_root)
    if not mthds_files:
        issues.append(
            PublishValidationIssue(
                level=IssueLevel.ERROR,
                category=IssueCategory.BUNDLE,
                message="No .mthds files found in package",
                suggestion="Add at least one .mthds bundle file",
            )
        )
        return {}, [], issues

    domain_pipes, _domain_main_pipes, blueprints, scan_errors = scan_bundles_for_domain_info(mthds_files)

    for error in scan_errors:
        issues.append(
            PublishValidationIssue(
                level=IssueLevel.ERROR,
                category=IssueCategory.BUNDLE,
                message=f"Bundle parse error: {error}",
            )
        )

    return domain_pipes, blueprints, issues


def _check_exports(manifest: MthdsPackageManifest, domain_pipes: dict[str, list[str]]) -> list[PublishValidationIssue]:
    """Check that exported pipes actually exist in scanned bundles."""
    issues: list[PublishValidationIssue] = []

    for domain_export in manifest.exports:
        domain_path = domain_export.domain_path
        actual_pipes = set(domain_pipes.get(domain_path, []))

        for pipe_code in domain_export.pipes:
            if pipe_code not in actual_pipes:
                issues.append(
                    PublishValidationIssue(
                        level=IssueLevel.ERROR,
                        category=IssueCategory.EXPORT,
                        message=f"Exported pipe '{pipe_code}' in domain '{domain_path}' not found in bundles",
                        suggestion=f"Remove '{pipe_code}' from [exports.{domain_path}] or add it to a .mthds file",
                    )
                )

    return issues


def _check_visibility(manifest: MthdsPackageManifest, blueprints: list[PipelexBundleBlueprint]) -> list[PublishValidationIssue]:
    """Check cross-domain visibility rules using already-parsed blueprints."""
    issues: list[PublishValidationIssue] = []

    visibility_errors = check_visibility_for_blueprints(manifest, blueprints)
    for vis_error in visibility_errors:
        issues.append(
            PublishValidationIssue(
                level=IssueLevel.ERROR,
                category=IssueCategory.VISIBILITY,
                message=vis_error.message,
            )
        )

    return issues


def _check_dependencies(manifest: MthdsPackageManifest) -> list[PublishValidationIssue]:
    """Check that dependencies have pinned versions (not wildcard *)."""
    issues: list[PublishValidationIssue] = []

    for dep in manifest.dependencies:
        if dep.version == "*":
            issues.append(
                PublishValidationIssue(
                    level=IssueLevel.WARNING,
                    category=IssueCategory.DEPENDENCY,
                    message=f"Dependency '{dep.alias}' has wildcard version '*'",
                    suggestion=f"Pin '{dep.alias}' to a specific version (e.g. '1.0.0' or '^1.0.0')",
                )
            )

    return issues


def _check_lock_file(manifest: MthdsPackageManifest, package_root: Path) -> list[PublishValidationIssue]:
    """Check lock file existence and consistency for remote dependencies."""
    issues: list[PublishValidationIssue] = []

    remote_deps = [dep for dep in manifest.dependencies if dep.path is None]
    if not remote_deps:
        return issues

    lock_path = package_root / LOCK_FILENAME
    if not lock_path.is_file():
        issues.append(
            PublishValidationIssue(
                level=IssueLevel.ERROR,
                category=IssueCategory.LOCK_FILE,
                message=f"{LOCK_FILENAME} not found but package has remote dependencies",
                suggestion="Run 'pipelex pkg lock' to generate the lock file",
            )
        )
        return issues

    # Parse lock file and compare addresses
    content = lock_path.read_text(encoding="utf-8")
    try:
        lock_file = parse_lock_file(content)
    except LockFileError as exc:
        issues.append(
            PublishValidationIssue(
                level=IssueLevel.ERROR,
                category=IssueCategory.LOCK_FILE,
                message=f"Failed to parse {LOCK_FILENAME}: {exc}",
            )
        )
        return issues

    remote_addresses = {dep.address for dep in remote_deps}
    locked_addresses = set(lock_file.packages.keys())

    missing_from_lock = remote_addresses - locked_addresses
    for address in sorted(missing_from_lock):
        issues.append(
            PublishValidationIssue(
                level=IssueLevel.WARNING,
                category=IssueCategory.LOCK_FILE,
                message=f"Remote dependency '{address}' not found in {LOCK_FILENAME}",
                suggestion="Run 'pipelex pkg lock' to update the lock file",
            )
        )

    return issues


def _check_git(manifest: MthdsPackageManifest, package_root: Path) -> list[PublishValidationIssue]:
    """Check git working directory status and tag availability."""
    issues: list[PublishValidationIssue] = []

    # Check working directory is clean
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],  # noqa: S607
            capture_output=True,
            text=True,
            check=True,
            timeout=10,
            cwd=package_root,
        )
        if result.stdout.strip():
            issues.append(
                PublishValidationIssue(
                    level=IssueLevel.WARNING,
                    category=IssueCategory.GIT,
                    message="Git working directory has uncommitted changes",
                    suggestion="Commit or stash changes before publishing",
                )
            )
    except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        issues.append(
            PublishValidationIssue(
                level=IssueLevel.WARNING,
                category=IssueCategory.GIT,
                message="Could not check git status (git not available or not a git repository)",
            )
        )
        return issues

    # Check tag does not already exist
    version_tag = f"v{manifest.version}"
    try:
        result = subprocess.run(  # noqa: S603
            ["git", "tag", "-l", version_tag],  # noqa: S607
            capture_output=True,
            text=True,
            check=True,
            timeout=10,
            cwd=package_root,
        )
        if result.stdout.strip():
            issues.append(
                PublishValidationIssue(
                    level=IssueLevel.ERROR,
                    category=IssueCategory.GIT,
                    message=f"Git tag '{version_tag}' already exists",
                    suggestion=f"Bump the version in {MANIFEST_FILENAME} or delete the existing tag",
                )
            )
    except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        issues.append(
            PublishValidationIssue(
                level=IssueLevel.WARNING,
                category=IssueCategory.GIT,
                message=f"Could not verify whether git tag '{version_tag}' already exists",
                suggestion="Manually check existing tags with `git tag -l` before publishing",
            )
        )

    return issues


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def validate_for_publish(package_root: Path, check_git: bool = True) -> PublishValidationResult:
    """Validate a package's readiness for distribution.

    Runs all validation checks and returns an aggregated result.

    Args:
        package_root: Path to the package root directory
        check_git: Whether to run git-related checks (disable in tests without git repos)

    Returns:
        PublishValidationResult with all issues found

    Raises:
        PublishValidationError: If the package root does not exist
    """
    if not package_root.is_dir():
        msg = f"Package root '{package_root}' does not exist or is not a directory"
        raise PublishValidationError(msg)

    all_issues: list[PublishValidationIssue] = []

    # 1. Check manifest exists and parses
    manifest, manifest_issues = _check_manifest_exists(package_root)
    all_issues.extend(manifest_issues)

    if manifest is None:
        return PublishValidationResult(issues=all_issues, package_version=None)

    # 2-6. Check manifest fields
    all_issues.extend(_check_manifest_fields(manifest))

    # 7-8. Check bundles exist and parse
    domain_pipes, blueprints, bundle_issues = _check_bundles(package_root)
    all_issues.extend(bundle_issues)

    # 9. Check exports consistency
    all_issues.extend(_check_exports(manifest, domain_pipes))

    # 10. Check visibility rules
    if blueprints:
        all_issues.extend(_check_visibility(manifest, blueprints))

    # 11. Check dependency pinning
    all_issues.extend(_check_dependencies(manifest))

    # 12-13. Check lock file
    all_issues.extend(_check_lock_file(manifest, package_root))

    # 14-15. Check git status
    if check_git:
        all_issues.extend(_check_git(manifest, package_root))

    return PublishValidationResult(issues=all_issues, package_version=manifest.version)
