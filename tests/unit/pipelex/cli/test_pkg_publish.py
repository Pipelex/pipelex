import os
import shutil
import subprocess  # noqa: S404
import textwrap
from pathlib import Path

import pytest
from click.exceptions import Exit

from pipelex.cli.commands.pkg.publish_cmd import do_pkg_publish
from pipelex.core.packages.discovery import MANIFEST_FILENAME
from pipelex.core.packages.publish_validation import PublishValidationResult, validate_for_publish

PACKAGES_DATA_DIR = Path(__file__).resolve().parent.parent.parent.parent / "data" / "packages"

_original_validate = validate_for_publish


def _validate_no_git(package_root: Path, check_git: bool = True) -> PublishValidationResult:
    _ = check_git
    return _original_validate(package_root, check_git=False)


class TestPkgPublish:
    """Tests for pipelex pkg publish command logic."""

    def test_publish_no_manifest_exits(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Empty directory with no METHODS.toml -> exit 1."""
        monkeypatch.chdir(tmp_path)

        with pytest.raises(Exit):
            do_pkg_publish()

    def test_publish_valid_package_succeeds(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """legal_tools copy (with lock file stub) -> no exit."""
        src_dir = PACKAGES_DATA_DIR / "legal_tools"
        pkg_dir = tmp_path / "legal_tools"
        shutil.copytree(src_dir, pkg_dir)

        # Create a stub lock file so the remote-dep check passes
        lock_content = textwrap.dedent("""\
            ["github.com/pipelexlab/scoring-lib"]
            version = "2.0.0"
            hash = "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
            source = "https://github.com/pipelexlab/scoring-lib"
        """)
        (pkg_dir / "methods.lock").write_text(lock_content, encoding="utf-8")

        monkeypatch.setattr(
            "pipelex.cli.commands.pkg.publish_cmd.validate_for_publish",
            _validate_no_git,
        )
        monkeypatch.chdir(pkg_dir)

        # Should not raise
        do_pkg_publish()

    def test_publish_with_tag_creates_tag(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Init git repo + minimal_package (no remote deps) -> tag created."""
        src_dir = PACKAGES_DATA_DIR / "minimal_package"
        pkg_dir = tmp_path / "minimal_package"
        shutil.copytree(src_dir, pkg_dir)

        # Add authors and license to avoid warnings-only issues blocking tag
        manifest_content = textwrap.dedent("""\
            [package]
            address = "github.com/pipelexlab/minimal"
            version = "0.1.0"
            description = "A minimal MTHDS package"
            authors = ["Test"]
            license = "MIT"
        """)
        (pkg_dir / MANIFEST_FILENAME).write_text(manifest_content, encoding="utf-8")

        # Initialize a git repo so tagging works
        subprocess.run(["git", "init"], cwd=pkg_dir, capture_output=True, check=True)  # noqa: S607
        subprocess.run(["git", "add", "."], cwd=pkg_dir, capture_output=True, check=True)  # noqa: S607
        subprocess.run(
            ["git", "commit", "-m", "initial"],  # noqa: S607
            cwd=pkg_dir,
            capture_output=True,
            check=True,
            env={
                **os.environ,
                "GIT_AUTHOR_NAME": "Test",
                "GIT_AUTHOR_EMAIL": "test@test.com",
                "GIT_COMMITTER_NAME": "Test",
                "GIT_COMMITTER_EMAIL": "test@test.com",
                "HOME": str(tmp_path),
            },
        )

        monkeypatch.chdir(pkg_dir)

        do_pkg_publish(tag=True)

        # Verify tag was created
        result = subprocess.run(
            ["git", "tag", "-l", "v0.1.0"],  # noqa: S607
            cwd=pkg_dir,
            capture_output=True,
            text=True,
            check=True,
        )
        assert "v0.1.0" in result.stdout

    def test_publish_tag_does_not_reparse_manifest(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Tag creation uses version from validation result, not by re-reading METHODS.toml.

        Regression test: previously _create_git_tag re-parsed METHODS.toml, which could
        raise unhandled ManifestParseError/ManifestValidationError if the file was
        modified or corrupted between validation and tagging.
        """
        src_dir = PACKAGES_DATA_DIR / "minimal_package"
        pkg_dir = tmp_path / "reparse_check"
        shutil.copytree(src_dir, pkg_dir)

        manifest_content = textwrap.dedent("""\
            [package]
            address = "github.com/pipelexlab/minimal"
            version = "0.2.0"
            description = "A minimal MTHDS package"
            authors = ["Test"]
            license = "MIT"
        """)
        (pkg_dir / MANIFEST_FILENAME).write_text(manifest_content, encoding="utf-8")

        # Initialize a git repo so tagging works
        subprocess.run(["git", "init"], cwd=pkg_dir, capture_output=True, check=True)  # noqa: S607
        subprocess.run(["git", "add", "."], cwd=pkg_dir, capture_output=True, check=True)  # noqa: S607
        subprocess.run(
            ["git", "commit", "-m", "initial"],  # noqa: S607
            cwd=pkg_dir,
            capture_output=True,
            check=True,
            env={
                **os.environ,
                "GIT_AUTHOR_NAME": "Test",
                "GIT_AUTHOR_EMAIL": "test@test.com",
                "GIT_COMMITTER_NAME": "Test",
                "GIT_COMMITTER_EMAIL": "test@test.com",
                "HOME": str(tmp_path),
            },
        )

        monkeypatch.chdir(pkg_dir)

        # Delete METHODS.toml after validation would have parsed it.
        # Old code re-read it here and would crash; new code uses the cached version.
        original_validate = validate_for_publish

        def validate_then_delete(package_root: Path, check_git: bool = True) -> PublishValidationResult:
            _ = check_git
            result = original_validate(package_root, check_git=False)
            (package_root / MANIFEST_FILENAME).unlink()
            return result

        monkeypatch.setattr(
            "pipelex.cli.commands.pkg.publish_cmd.validate_for_publish",
            validate_then_delete,
        )

        # Should not raise — version comes from validation result, not re-parsed file
        do_pkg_publish(tag=True)

        # Verify tag was created with the correct version
        result = subprocess.run(
            ["git", "tag", "-l", "v0.2.0"],  # noqa: S607
            cwd=pkg_dir,
            capture_output=True,
            text=True,
            check=True,
        )
        assert "v0.2.0" in result.stdout

    def test_publish_with_warnings_still_succeeds(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """minimal_package (no authors/license) -> warnings but no exit."""
        src_dir = PACKAGES_DATA_DIR / "minimal_package"
        pkg_dir = tmp_path / "minimal_package"
        shutil.copytree(src_dir, pkg_dir)

        monkeypatch.setattr(
            "pipelex.cli.commands.pkg.publish_cmd.validate_for_publish",
            _validate_no_git,
        )
        monkeypatch.chdir(pkg_dir)

        # Should not raise — warnings don't block
        do_pkg_publish()
