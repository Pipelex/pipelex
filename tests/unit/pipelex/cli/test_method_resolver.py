"""Unit tests for method-reference, local-path, and name dispatch in resolve_method_target."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
import typer
from mthds.package.discovery import MANIFEST_FILENAME
from mthds.package.exceptions import VCSFetchError

from pipelex.cli.method_resolver import (
    is_local_path,
    resolve_method_from_path,
    resolve_method_from_ref,
    resolve_method_target,
)

if TYPE_CHECKING:
    from pathlib import Path

    from pytest_mock import MockerFixture

FAKE_SHA = "0123456789abcdef0123456789abcdef01234567"

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

STRUCTURES_MODULE = """\
from pipelex.core.stuffs.structured_content import StructuredContent


class Invoice(StructuredContent):
    total: float
"""


def _write_method_package(dest: Path) -> None:
    """Write a minimal method package (METHODS.toml + .mthds file) into *dest*."""
    dest.mkdir(parents=True, exist_ok=True)
    (dest / MANIFEST_FILENAME).write_text(MINIMAL_MANIFEST, encoding="utf-8")
    (dest / "core.mthds").write_text("# placeholder", encoding="utf-8")


class TestResolveMethodTarget:
    """Tests for reference detection, fetch-backed resolution, and local-path resolution."""

    def _mock_clone(self, mocker: MockerFixture, dest_dir: Path) -> None:
        def fake_clone(*, clone_url: str, destination: Path) -> None:
            assert clone_url.endswith(".git")
            _write_method_package(destination)

        mocker.patch("pipelex.methods.fetching.clone_default_branch", side_effect=fake_clone)
        mocker.patch("pipelex.methods.fetching.resolve_head_commit_sha", return_value=FAKE_SHA)
        mocker.patch("pipelex.cli.method_resolver.tempfile.mkdtemp", return_value=str(dest_dir))

    def test_resolve_method_from_ref_success(self, mocker: MockerFixture, tmp_path: Path) -> None:
        """A successful fetch containing a matching package returns an InstalledMethod with provenance."""
        self._mock_clone(mocker, tmp_path / "cloned")

        method = resolve_method_from_ref("github.com/test/remote-method")

        assert method.name == "remote_method"
        assert method.manifest.main_pipe == "test_pipe"
        assert len(method.mthds_files) == 1
        assert method.provenance is not None
        assert method.provenance.address == "github.com/test/remote-method/remote_method"
        assert method.provenance.commit_sha == FAKE_SHA

    def test_resolve_method_from_ref_accepts_full_url(self, mocker: MockerFixture, tmp_path: Path) -> None:
        """Full https GitHub URLs keep working, normalized into the address form."""
        self._mock_clone(mocker, tmp_path / "cloned")

        method = resolve_method_from_ref("https://github.com/test/remote-method")

        assert method.name == "remote_method"

    def test_resolve_method_from_ref_clone_failure(self, mocker: MockerFixture, tmp_path: Path) -> None:
        """A VCSFetchError during clone raises typer.Exit."""
        mocker.patch("pipelex.methods.fetching.clone_default_branch", side_effect=VCSFetchError("connection refused"))
        mocker.patch("pipelex.cli.method_resolver.tempfile.mkdtemp", return_value=str(tmp_path / "dest"))

        with pytest.raises(typer.Exit):
            resolve_method_from_ref("github.com/test/broken-repo")

    def test_resolve_method_from_ref_no_matching_package(self, mocker: MockerFixture, tmp_path: Path) -> None:
        """A clone whose packages match no requested address raises typer.Exit."""
        self._mock_clone(mocker, tmp_path / "cloned")

        with pytest.raises(typer.Exit):
            resolve_method_from_ref("github.com/test/other-address")

    def test_resolve_method_from_ref_parse_error(self, mocker: MockerFixture) -> None:
        """An invalid reference raises typer.Exit without attempting a clone."""
        clone_spy = mocker.patch("pipelex.methods.fetching.clone_default_branch")

        with pytest.raises(typer.Exit):
            resolve_method_from_ref("github.com/only-owner")

        assert clone_spy.call_count == 0

    def test_resolve_method_from_ref_warns_on_structures(self, mocker: MockerFixture, tmp_path: Path) -> None:
        """Hosted-parity: a fetched package declaring StructuredContent subclasses resolves locally with a warning."""
        dest_dir = tmp_path / "cloned"

        def fake_clone(*, clone_url: str, destination: Path) -> None:
            assert clone_url.endswith(".git")
            _write_method_package(destination)
            (destination / "structures.py").write_text(STRUCTURES_MODULE, encoding="utf-8")

        mocker.patch("pipelex.methods.fetching.clone_default_branch", side_effect=fake_clone)
        mocker.patch("pipelex.methods.fetching.resolve_head_commit_sha", return_value=FAKE_SHA)
        mocker.patch("pipelex.cli.method_resolver.tempfile.mkdtemp", return_value=str(dest_dir))
        secho_spy = mocker.patch("pipelex.cli.method_resolver.typer.secho")

        method = resolve_method_from_ref("github.com/test/remote-method")

        assert method.name == "remote_method"
        warning_calls = [call for call in secho_spy.call_args_list if "hosted execution would refuse" in str(call)]
        assert len(warning_calls) == 1

    def test_resolve_method_target_dispatches_bare_address(self, mocker: MockerFixture, tmp_path: Path) -> None:
        """A bare github.com address dispatches to the fetch arm, not the local-path arm."""
        self._mock_clone(mocker, tmp_path / "dispatched")

        pipe_code, lib_dirs, method = resolve_method_target("github.com/test/remote-method")

        assert pipe_code == "test_pipe"
        assert method.name == "remote_method"
        assert len(lib_dirs) == 1

    def test_resolve_method_target_dispatches_tagged_address(self, mocker: MockerFixture, tmp_path: Path) -> None:
        """A `@<tag>` address dispatches to the tag-clone arm."""

        def fake_clone(*, clone_url: str, version_tag: str, destination: Path) -> None:
            assert clone_url == "https://github.com/test/remote-method.git"
            assert version_tag == "v0.1.0"
            _write_method_package(destination)

        mocker.patch("pipelex.methods.fetching.clone_at_version", side_effect=fake_clone)
        mocker.patch("pipelex.methods.fetching.ensure_cloned_at_tag")
        mocker.patch("pipelex.methods.fetching.resolve_head_commit_sha", return_value=FAKE_SHA)
        mocker.patch("pipelex.cli.method_resolver.tempfile.mkdtemp", return_value=str(tmp_path / "tagged"))

        pipe_code, _, method = resolve_method_target("github.com/test/remote-method@v0.1.0")

        assert pipe_code == "test_pipe"
        assert method.provenance is not None
        assert method.provenance.tag == "v0.1.0"

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
        assert method.provenance is None

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
