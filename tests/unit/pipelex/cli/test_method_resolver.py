"""Unit tests for GitHub URL and local path support in resolve_method_target."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
import typer
from mthds.package.discovery import MANIFEST_FILENAME
from mthds.package.exceptions import VCSFetchError

from pipelex.cli.method_resolver import (
    is_github_url,
    is_local_path,
    parse_github_url,
    resolve_method_from_path,
    resolve_method_from_url,
    resolve_method_target,
)

if TYPE_CHECKING:
    from pathlib import Path

    from pytest_mock import MockerFixture

MINIMAL_MANIFEST = """\
[package]
address = "github.com/test/remote-method"
version = "0.1.0"
description = "A remote test method"
name = "remote_method"
main_pipe = "test_pipe"

[exports.test]
pipes = ["test_pipe"]
"""


def _write_method_package(dest: Path) -> None:
    """Write a minimal method package (METHODS.toml + .mthds file) into *dest*."""
    dest.mkdir(parents=True, exist_ok=True)
    (dest / MANIFEST_FILENAME).write_text(MINIMAL_MANIFEST, encoding="utf-8")
    (dest / "core.mthds").write_text("# placeholder", encoding="utf-8")


class TestResolveMethodTarget:
    """Tests for GitHub URL detection, parsing, and resolution in the method resolver."""

    @pytest.mark.parametrize(
        "url",
        [
            "https://github.com/org/repo",
            "https://github.com/org/repo.git",
            "https://github.com/org/repo/",
            "http://github.com/org/repo",
            "https://github.com/org/repo/tree/main/methods/my-method",
        ],
    )
    def test_is_github_url_positive(self, url: str) -> None:
        """Various valid GitHub URLs are correctly detected."""
        assert is_github_url(url) is True

    @pytest.mark.parametrize(
        "target",
        [
            "my-method",
            "some-random-string",
            "github.com/org/repo",
            "https://gitlab.com/org/repo",
            "",
        ],
    )
    def test_is_github_url_negative(self, target: str) -> None:
        """Method names and non-GitHub strings are not detected as GitHub URLs."""
        assert is_github_url(target) is False

    @pytest.mark.parametrize(
        ("url", "expected_clone_url", "expected_sub_path"),
        [
            ("https://github.com/org/repo", "https://github.com/org/repo.git", None),
            ("https://github.com/org/repo/", "https://github.com/org/repo.git", None),
            ("https://github.com/org/repo.git", "https://github.com/org/repo.git", None),
            ("http://github.com/org/repo", "http://github.com/org/repo.git", None),
            (
                "https://github.com/org/repo/tree/main/methods/my-method",
                "https://github.com/org/repo.git",
                "methods/my-method",
            ),
            (
                "https://github.com/org/repo/methods/my-method",
                "https://github.com/org/repo.git",
                "methods/my-method",
            ),
        ],
    )
    def test_parse_github_url(self, url: str, expected_clone_url: str, expected_sub_path: str | None) -> None:
        """Clone URL and sub-path are correctly extracted from various GitHub URL formats."""
        clone_url, sub_path = parse_github_url(url)
        assert clone_url == expected_clone_url
        assert sub_path == expected_sub_path

    def test_resolve_method_from_url_success(self, mocker: MockerFixture, tmp_path: Path) -> None:
        """A successful clone containing a valid package returns an InstalledMethod."""
        dest_dir = tmp_path / "cloned"

        def fake_clone(_clone_url: str, destination: Path) -> None:
            _write_method_package(destination)

        mocker.patch("pipelex.cli.method_resolver.clone_default_branch", side_effect=fake_clone)
        mocker.patch("pipelex.cli.method_resolver.tempfile.mkdtemp", return_value=str(dest_dir))

        method = resolve_method_from_url("https://github.com/test/remote-method")

        assert method.name == "remote_method"
        assert method.manifest.main_pipe == "test_pipe"
        assert len(method.mthds_files) == 1

    def test_resolve_method_from_url_with_sub_path(self, mocker: MockerFixture, tmp_path: Path) -> None:
        """A subdirectory URL correctly discovers the method in the sub-path."""
        dest_dir = tmp_path / "cloned"

        def fake_clone(_clone_url: str, destination: Path) -> None:
            destination.mkdir(parents=True, exist_ok=True)
            _write_method_package(destination / "methods" / "my-method")

        mocker.patch("pipelex.cli.method_resolver.clone_default_branch", side_effect=fake_clone)
        mocker.patch("pipelex.cli.method_resolver.tempfile.mkdtemp", return_value=str(dest_dir))

        method = resolve_method_from_url("https://github.com/test/repo/methods/my-method")

        assert method.name == "remote_method"
        assert method.manifest.main_pipe == "test_pipe"

    def test_resolve_method_from_url_clone_failure(self, mocker: MockerFixture, tmp_path: Path) -> None:
        """A VCSFetchError during clone raises typer.Exit."""
        mocker.patch(
            "pipelex.cli.method_resolver.clone_default_branch",
            side_effect=VCSFetchError("connection refused"),
        )
        mocker.patch("pipelex.cli.method_resolver.tempfile.mkdtemp", return_value=str(tmp_path / "dest"))

        with pytest.raises(typer.Exit):
            resolve_method_from_url("https://github.com/test/broken-repo")

    def test_resolve_method_from_url_no_manifest(self, mocker: MockerFixture, tmp_path: Path) -> None:
        """A clone that contains no METHODS.toml raises typer.Exit."""
        dest_dir = tmp_path / "empty"

        def fake_clone(_clone_url: str, destination: Path) -> None:
            destination.mkdir(parents=True, exist_ok=True)

        mocker.patch("pipelex.cli.method_resolver.clone_default_branch", side_effect=fake_clone)
        mocker.patch("pipelex.cli.method_resolver.tempfile.mkdtemp", return_value=str(dest_dir))

        with pytest.raises(typer.Exit):
            resolve_method_from_url("https://github.com/test/no-manifest")

    def test_resolve_method_target_dispatches_to_url(self, mocker: MockerFixture, tmp_path: Path) -> None:
        """resolve_method_target dispatches to resolve_method_from_url for GitHub URLs."""
        dest_dir = tmp_path / "dispatched"

        def fake_clone(_clone_url: str, destination: Path) -> None:
            _write_method_package(destination)

        mocker.patch("pipelex.cli.method_resolver.clone_default_branch", side_effect=fake_clone)
        mocker.patch("pipelex.cli.method_resolver.tempfile.mkdtemp", return_value=str(dest_dir))

        pipe_code, lib_dirs, method = resolve_method_target("https://github.com/test/remote-method")

        assert pipe_code == "test_pipe"
        assert method.name == "remote_method"
        assert len(lib_dirs) == 1

    @pytest.mark.parametrize(
        ("target", "expected"),
        [
            ("/absolute/path/to/method", True),
            ("./relative/path", True),
            ("../parent/path", True),
            ("path/with/slash", True),
            ("my-method", False),
            ("simple_name", False),
            ("", False),
            ("https://gitlab.com/org/repo", False),
            ("http://bitbucket.org/org/repo", False),
        ],
    )
    def test_is_local_path(self, target: str, expected: bool) -> None:
        """Strings with path separators are detected as local paths; URLs are not."""
        assert is_local_path(target) is expected

    def test_resolve_method_from_path_success(self, tmp_path: Path) -> None:
        """A local directory with a valid method package is discovered."""
        method_dir = tmp_path / "local-method"
        _write_method_package(method_dir)

        method = resolve_method_from_path(str(method_dir))

        assert method.name == "remote_method"
        assert method.manifest.main_pipe == "test_pipe"
        assert len(method.mthds_files) == 1

    def test_resolve_method_from_path_not_a_directory(self, tmp_path: Path) -> None:
        """A non-existent path raises typer.Exit."""
        with pytest.raises(typer.Exit):
            resolve_method_from_path(str(tmp_path / "does-not-exist"))

    def test_resolve_method_from_path_no_manifest(self, tmp_path: Path) -> None:
        """A directory without METHODS.toml raises typer.Exit."""
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()

        with pytest.raises(typer.Exit):
            resolve_method_from_path(str(empty_dir))

    def test_resolve_method_target_dispatches_to_local_path(self, tmp_path: Path) -> None:
        """resolve_method_target dispatches to resolve_method_from_path for local paths."""
        method_dir = tmp_path / "local-method"
        _write_method_package(method_dir)

        pipe_code, lib_dirs, method = resolve_method_target(str(method_dir))

        assert pipe_code == "test_pipe"
        assert method.name == "remote_method"
        assert len(lib_dirs) == 1
