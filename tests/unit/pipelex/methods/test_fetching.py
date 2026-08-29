"""Unit tests for fetch_method_package: clone dispatch, SHA recording, bounds, refusal guardrail."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

import pytest
from mthds.package.exceptions import VCSFetchError

from pipelex.methods.exceptions import MethodFetchError, MethodPackageTooLargeError, MethodStructuresRefusedError
from pipelex.methods.fetching import ensure_package_within_bounds, fetch_method_package
from pipelex.methods.method_ref import parse_method_ref

if TYPE_CHECKING:
    from pathlib import Path

    from pytest_mock import MockerFixture

FAKE_SHA = "0123456789abcdef0123456789abcdef01234567"

MANIFEST = """\
[package]
name = "documents"
address = "github.com/Pipelex/methods"
version = "0.1.0"
description = "A test package."
main_pipe = "extract"

[exports.documents]
pipes = ["extract"]
"""

STRUCTURES_MODULE = """\
from pipelex.core.stuffs.structured_content import StructuredContent


class Invoice(StructuredContent):
    total: float
"""


def _write_package(destination: Path) -> None:
    package_dir = destination / "methods" / "documents"
    package_dir.mkdir(parents=True, exist_ok=True)
    (package_dir / "METHODS.toml").write_text(MANIFEST, encoding="utf-8")
    (package_dir / "documents.mthds").write_text("# placeholder", encoding="utf-8")


class TestFetchMethodPackage:
    """Tests for the fetch orchestration with the clone machinery mocked."""

    def test_bare_address_clones_default_branch(self, mocker: MockerFixture, tmp_path: Path) -> None:
        """A tag-less reference clones the default branch and records the resolved SHA."""

        def fake_clone(*, clone_url: str, destination: Path) -> None:
            assert clone_url == "https://github.com/Pipelex/methods.git"
            _write_package(destination)

        clone_default = mocker.patch("pipelex.methods.fetching.clone_default_branch", side_effect=fake_clone)
        clone_at_tag = mocker.patch("pipelex.methods.fetching.clone_at_version")
        mocker.patch("pipelex.methods.fetching.resolve_head_commit_sha", return_value=FAKE_SHA)

        fetched = fetch_method_package(ref=parse_method_ref("github.com/Pipelex/methods/documents"), dest_dir=tmp_path)

        assert clone_default.call_count == 1
        assert clone_at_tag.call_count == 0
        assert fetched.commit_sha == FAKE_SHA
        assert fetched.full_address == "github.com/Pipelex/methods/documents"
        assert fetched.package_dir == tmp_path / "methods" / "documents"
        assert fetched.manifest.main_pipe == "extract"
        assert fetched.provenance.address == "github.com/Pipelex/methods/documents"
        assert fetched.provenance.tag is None
        assert fetched.provenance.commit_sha == FAKE_SHA

    def test_tagged_ref_clones_at_version(self, mocker: MockerFixture, tmp_path: Path) -> None:
        """A `@<tag>` reference clones at that tag."""

        def fake_clone(*, clone_url: str, version_tag: str, destination: Path) -> None:
            assert clone_url == "https://github.com/Pipelex/methods.git"
            assert version_tag == "v0.2.0"
            _write_package(destination)

        clone_at_tag = mocker.patch("pipelex.methods.fetching.clone_at_version", side_effect=fake_clone)
        clone_default = mocker.patch("pipelex.methods.fetching.clone_default_branch")
        tag_check = mocker.patch("pipelex.methods.fetching.ensure_cloned_at_tag")
        mocker.patch("pipelex.methods.fetching.resolve_head_commit_sha", return_value=FAKE_SHA)

        fetched = fetch_method_package(ref=parse_method_ref("github.com/Pipelex/methods/documents@v0.2.0"), dest_dir=tmp_path)

        assert clone_at_tag.call_count == 1
        assert clone_default.call_count == 0
        assert tag_check.call_count == 1
        assert fetched.provenance.tag == "v0.2.0"

    def test_clone_failure_is_a_method_fetch_error(self, mocker: MockerFixture, tmp_path: Path) -> None:
        """A VCS failure surfaces as MethodFetchError naming the reference."""
        mocker.patch("pipelex.methods.fetching.clone_default_branch", side_effect=VCSFetchError("connection refused"))

        with pytest.raises(MethodFetchError, match=re.escape("github.com/Pipelex/methods/documents")):
            fetch_method_package(ref=parse_method_ref("github.com/Pipelex/methods/documents"), dest_dir=tmp_path)

    def test_refusal_fires_before_any_module_import(self, mocker: MockerFixture, tmp_path: Path) -> None:
        """Guardrail: a fetched package carrying a StructuredContent subclass is refused with the
        rule-naming error before anything reaches the module-import machinery.
        """

        def fake_clone(*, clone_url: str, destination: Path) -> None:
            assert clone_url == "https://github.com/Pipelex/methods.git"
            _write_package(destination)
            (destination / "methods" / "documents" / "structures.py").write_text(STRUCTURES_MODULE, encoding="utf-8")

        mocker.patch("pipelex.methods.fetching.clone_default_branch", side_effect=fake_clone)
        mocker.patch("pipelex.methods.fetching.resolve_head_commit_sha", return_value=FAKE_SHA)
        import_module_spy = mocker.patch("pipelex.tools.typing.module_inspector.import_module_from_file")
        import_folder_spy = mocker.patch("pipelex.system.registries.class_registry_utils.ClassRegistryUtils.import_modules_in_folder")

        with pytest.raises(MethodStructuresRefusedError, match="not in-process Python"):
            fetch_method_package(
                ref=parse_method_ref("github.com/Pipelex/methods/documents"),
                dest_dir=tmp_path,
                refuse_structures=True,
            )

        assert import_module_spy.call_count == 0
        assert import_folder_spy.call_count == 0

    def test_without_refusal_flag_structures_package_is_returned(self, mocker: MockerFixture, tmp_path: Path) -> None:
        """The refusal is opt-in: without the flag (local CLI parity-warning mode) the package is returned."""

        def fake_clone(*, clone_url: str, destination: Path) -> None:
            assert clone_url == "https://github.com/Pipelex/methods.git"
            _write_package(destination)
            (destination / "methods" / "documents" / "structures.py").write_text(STRUCTURES_MODULE, encoding="utf-8")

        mocker.patch("pipelex.methods.fetching.clone_default_branch", side_effect=fake_clone)
        mocker.patch("pipelex.methods.fetching.resolve_head_commit_sha", return_value=FAKE_SHA)

        fetched = fetch_method_package(ref=parse_method_ref("github.com/Pipelex/methods/documents"), dest_dir=tmp_path)

        assert fetched.full_address == "github.com/Pipelex/methods/documents"

    def test_file_count_bound_is_enforced(self, mocker: MockerFixture, tmp_path: Path) -> None:
        """A selected package with more files than the cap is rejected."""
        package_dir = tmp_path / "pkg"
        package_dir.mkdir()
        for index_file in range(5):
            (package_dir / f"file_{index_file}.mthds").write_text("# x", encoding="utf-8")
        mocker.patch("pipelex.methods.fetching.MAX_FETCHED_PACKAGE_FILES", 3)

        with pytest.raises(MethodPackageTooLargeError, match="files"):
            ensure_package_within_bounds(package_dir=package_dir, package_address="github.com/acme/big")

    def test_total_bytes_bound_is_enforced(self, mocker: MockerFixture, tmp_path: Path) -> None:
        """A selected package larger than the byte cap is rejected."""
        package_dir = tmp_path / "pkg"
        package_dir.mkdir()
        (package_dir / "big.mthds").write_text("x" * 1024, encoding="utf-8")
        mocker.patch("pipelex.methods.fetching.MAX_FETCHED_PACKAGE_TOTAL_BYTES", 512)

        with pytest.raises(MethodPackageTooLargeError, match="bytes"):
            ensure_package_within_bounds(package_dir=package_dir, package_address="github.com/acme/heavy")

    def test_bounds_ignore_git_directory(self, tmp_path: Path) -> None:
        """Files under .git/ do not count toward the ceilings."""
        package_dir = tmp_path / "pkg"
        git_dir = package_dir / ".git" / "objects"
        git_dir.mkdir(parents=True)
        (git_dir / "blob").write_bytes(b"x" * 4096)
        (package_dir / "core.mthds").write_text("# placeholder", encoding="utf-8")

        ensure_package_within_bounds(package_dir=package_dir, package_address="github.com/acme/small")
