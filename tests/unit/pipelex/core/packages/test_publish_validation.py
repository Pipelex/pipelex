import shutil
import textwrap
from pathlib import Path

from pipelex.core.packages.discovery import MANIFEST_FILENAME
from pipelex.core.packages.publish_validation import (
    IssueCategory,
    IssueLevel,
    PublishValidationIssue,
    PublishValidationResult,
    validate_for_publish,
)

PACKAGES_DATA_DIR = Path(__file__).resolve().parent.parent.parent.parent.parent / "data" / "packages"


def _issues_by_category(result: PublishValidationResult, category: IssueCategory) -> list[PublishValidationIssue]:
    return [issue for issue in result.issues if issue.category == category]


def _issues_by_level_warning(result: PublishValidationResult) -> list[PublishValidationIssue]:
    return [issue for issue in result.issues if issue.level.is_warning]


class TestPublishValidation:
    """Tests for publish validation logic."""

    def test_issue_level_properties(self) -> None:
        """IssueLevel.is_error and is_warning are mutually exclusive and exhaustive."""
        assert IssueLevel.ERROR.is_error is True
        assert IssueLevel.ERROR.is_warning is False
        assert IssueLevel.WARNING.is_error is False
        assert IssueLevel.WARNING.is_warning is True

    def test_valid_package_passes(self, tmp_path: Path) -> None:
        """legal_tools with full manifest, bundles, and exports -> is_publishable=True (git checks off)."""
        src_dir = PACKAGES_DATA_DIR / "legal_tools"
        pkg_dir = tmp_path / "legal_tools"
        shutil.copytree(src_dir, pkg_dir)

        result = validate_for_publish(pkg_dir, check_git=False)

        # legal_tools has a remote dep but no lock file, so there will be a lock file error
        # Filter out lock file issues for this test — the package is otherwise valid
        non_lock_errors = [issue for issue in result.issues if issue.level.is_error and issue.category != IssueCategory.LOCK_FILE]
        assert not non_lock_errors, f"Unexpected errors: {non_lock_errors}"

    def test_no_manifest_errors(self, tmp_path: Path) -> None:
        """Empty directory -> manifest ERROR."""
        result = validate_for_publish(tmp_path, check_git=False)

        assert not result.is_publishable
        manifest_errors = _issues_by_category(result, IssueCategory.MANIFEST)
        assert len(manifest_errors) == 1
        assert manifest_errors[0].level.is_error
        assert MANIFEST_FILENAME in manifest_errors[0].message

    def test_no_bundles_errors(self, tmp_path: Path) -> None:
        """Manifest but no .mthds files -> bundle ERROR."""
        manifest_content = textwrap.dedent("""\
            [package]
            address = "github.com/test/no-bundles"
            version = "1.0.0"
            description = "No bundles"
            authors = ["Test"]
            license = "MIT"
        """)
        (tmp_path / MANIFEST_FILENAME).write_text(manifest_content, encoding="utf-8")

        result = validate_for_publish(tmp_path, check_git=False)

        assert not result.is_publishable
        bundle_errors = _issues_by_category(result, IssueCategory.BUNDLE)
        assert len(bundle_errors) == 1
        assert bundle_errors[0].level.is_error
        assert ".mthds" in bundle_errors[0].message

    def test_missing_authors_warns(self, tmp_path: Path) -> None:
        """minimal_package has no authors -> WARNING."""
        src_dir = PACKAGES_DATA_DIR / "minimal_package"
        pkg_dir = tmp_path / "minimal_package"
        shutil.copytree(src_dir, pkg_dir)

        result = validate_for_publish(pkg_dir, check_git=False)

        warnings = _issues_by_level_warning(result)
        author_warnings = [warning for warning in warnings if "authors" in warning.message.lower()]
        assert len(author_warnings) == 1

    def test_missing_license_warns(self, tmp_path: Path) -> None:
        """minimal_package has no license -> WARNING."""
        src_dir = PACKAGES_DATA_DIR / "minimal_package"
        pkg_dir = tmp_path / "minimal_package"
        shutil.copytree(src_dir, pkg_dir)

        result = validate_for_publish(pkg_dir, check_git=False)

        warnings = _issues_by_level_warning(result)
        license_warnings = [warning for warning in warnings if "license" in warning.message.lower()]
        assert len(license_warnings) == 1

    def test_phantom_export_errors(self, tmp_path: Path) -> None:
        """Package with export listing a non-existent pipe -> EXPORT ERROR."""
        src_dir = PACKAGES_DATA_DIR / "minimal_package"
        pkg_dir = tmp_path / "phantom_export"
        shutil.copytree(src_dir, pkg_dir)

        # Rewrite manifest to add an export for a pipe that doesn't exist
        manifest_content = textwrap.dedent("""\
            [package]
            address = "github.com/test/phantom"
            version = "1.0.0"
            description = "Phantom export test"
            authors = ["Test"]
            license = "MIT"

            [exports.pkg_test_minimal_core]
            pipes = ["pkg_test_hello", "pkg_test_nonexistent_pipe"]
        """)
        (pkg_dir / MANIFEST_FILENAME).write_text(manifest_content, encoding="utf-8")

        result = validate_for_publish(pkg_dir, check_git=False)

        export_errors = _issues_by_category(result, IssueCategory.EXPORT)
        assert len(export_errors) == 1
        assert export_errors[0].level.is_error
        assert "pkg_test_nonexistent_pipe" in export_errors[0].message

    def test_lock_file_missing_with_remote_deps_errors(self, tmp_path: Path) -> None:
        """Manifest with remote dep but no methods.lock -> LOCK_FILE ERROR."""
        src_dir = PACKAGES_DATA_DIR / "minimal_package"
        pkg_dir = tmp_path / "missing_lock"
        shutil.copytree(src_dir, pkg_dir)

        # Rewrite manifest to add a remote dependency
        manifest_content = textwrap.dedent("""\
            [package]
            address = "github.com/test/missing-lock"
            version = "1.0.0"
            description = "Missing lock test"
            authors = ["Test"]
            license = "MIT"

            [dependencies]
            some_lib = { address = "github.com/test/some-lib", version = "1.0.0" }
        """)
        (pkg_dir / MANIFEST_FILENAME).write_text(manifest_content, encoding="utf-8")

        result = validate_for_publish(pkg_dir, check_git=False)

        lock_errors = _issues_by_category(result, IssueCategory.LOCK_FILE)
        assert len(lock_errors) == 1
        assert lock_errors[0].level.is_error
        assert "methods.lock" in lock_errors[0].message

    def test_lock_file_not_required_without_remote_deps(self, tmp_path: Path) -> None:
        """Local-only deps -> no lock file error."""
        src_dir = PACKAGES_DATA_DIR / "minimal_package"
        pkg_dir = tmp_path / "local_only"
        shutil.copytree(src_dir, pkg_dir)

        # Rewrite manifest with a local path dependency
        manifest_content = textwrap.dedent("""\
            [package]
            address = "github.com/test/local-only"
            version = "1.0.0"
            description = "Local only test"
            authors = ["Test"]
            license = "MIT"

            [dependencies]
            local_lib = { address = "github.com/test/local-lib", version = "1.0.0", path = "../local-lib" }
        """)
        (pkg_dir / MANIFEST_FILENAME).write_text(manifest_content, encoding="utf-8")

        result = validate_for_publish(pkg_dir, check_git=False)

        lock_errors = _issues_by_category(result, IssueCategory.LOCK_FILE)
        assert not lock_errors

    def test_wildcard_version_warns(self, tmp_path: Path) -> None:
        """Dependency with version * -> DEPENDENCY WARNING."""
        src_dir = PACKAGES_DATA_DIR / "minimal_package"
        pkg_dir = tmp_path / "wildcard_dep"
        shutil.copytree(src_dir, pkg_dir)

        manifest_content = textwrap.dedent("""\
            [package]
            address = "github.com/test/wildcard"
            version = "1.0.0"
            description = "Wildcard dep test"
            authors = ["Test"]
            license = "MIT"

            [dependencies]
            some_lib = { address = "github.com/test/some-lib", version = "*" }
        """)
        (pkg_dir / MANIFEST_FILENAME).write_text(manifest_content, encoding="utf-8")

        result = validate_for_publish(pkg_dir, check_git=False)

        dep_warnings = _issues_by_category(result, IssueCategory.DEPENDENCY)
        assert len(dep_warnings) == 1
        assert dep_warnings[0].level.is_warning
        assert "wildcard" in dep_warnings[0].message.lower()

    def test_git_checks_skipped_when_disabled(self, tmp_path: Path) -> None:
        """check_git=False -> no GIT issues regardless of git state."""
        src_dir = PACKAGES_DATA_DIR / "minimal_package"
        pkg_dir = tmp_path / "no_git"
        shutil.copytree(src_dir, pkg_dir)

        result = validate_for_publish(pkg_dir, check_git=False)

        git_issues = _issues_by_category(result, IssueCategory.GIT)
        assert not git_issues

    def test_result_includes_package_version_on_success(self, tmp_path: Path) -> None:
        """Successful validation populates package_version from the parsed manifest."""
        src_dir = PACKAGES_DATA_DIR / "minimal_package"
        pkg_dir = tmp_path / "version_check"
        shutil.copytree(src_dir, pkg_dir)

        result = validate_for_publish(pkg_dir, check_git=False)

        assert result.package_version is not None
        assert result.package_version == "0.1.0"

    def test_result_has_no_package_version_when_manifest_missing(self, tmp_path: Path) -> None:
        """Missing manifest -> package_version is None."""
        result = validate_for_publish(tmp_path, check_git=False)

        assert result.package_version is None

    def test_manifest_field_checks_produce_no_errors(self, tmp_path: Path) -> None:
        """Manifest field checks only produce warnings (authors/license), never errors.

        Address, version, and description are validated by Pydantic validators
        during parsing. If the manifest parsed successfully, those fields are
        guaranteed valid — the field checker should not re-check them.
        """
        src_dir = PACKAGES_DATA_DIR / "minimal_package"
        pkg_dir = tmp_path / "manifest_fields"
        shutil.copytree(src_dir, pkg_dir)

        result = validate_for_publish(pkg_dir, check_git=False)

        manifest_issues = _issues_by_category(result, IssueCategory.MANIFEST)
        manifest_errors = [issue for issue in manifest_issues if issue.level.is_error]
        assert not manifest_errors, f"Expected no MANIFEST errors, got: {manifest_errors}"
        # minimal_package has no authors and no license -> exactly 2 warnings
        manifest_warnings = [issue for issue in manifest_issues if issue.level.is_warning]
        assert len(manifest_warnings) == 2
        warning_messages = {issue.message for issue in manifest_warnings}
        assert any("authors" in msg.lower() for msg in warning_messages)
        assert any("license" in msg.lower() for msg in warning_messages)
