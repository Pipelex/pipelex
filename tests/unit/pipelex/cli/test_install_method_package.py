"""Unit tests for install_method_package and the provenance-aware discovery around it."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from mthds.package.discovery import MANIFEST_FILENAME

from pipelex.cli.installed_methods import (
    PROVENANCE_FILENAME,
    discover_installed_methods,
    find_method_by_full_address,
    install_method_package,
)
from pipelex.methods.exceptions import MethodInstallError
from pipelex.methods.fetching import MethodProvenance

if TYPE_CHECKING:
    from pathlib import Path

MANIFEST = """\
[package]
name = "scoring"
address = "github.com/pipelex-tests/fom-methods"
version = "0.1.0"
description = "A test package for install tests"
main_pipe = "compute"

[exports.scoring]
pipes = ["compute"]
"""

PROVENANCE = MethodProvenance(
    address="github.com/pipelex-tests/fom-methods/scoring",
    tag="v0.1.0",
    commit_sha="a" * 40,
)


def _make_package_dir(base: Path) -> Path:
    """Build a source package directory with a manifest, a bundle, and a fake .git/."""
    package_dir = base / "source-pkg"
    package_dir.mkdir(parents=True)
    (package_dir / MANIFEST_FILENAME).write_text(MANIFEST, encoding="utf-8")
    (package_dir / "scoring.mthds").write_text("# placeholder", encoding="utf-8")
    git_dir = package_dir / ".git"
    git_dir.mkdir()
    (git_dir / "HEAD").write_text("ref: refs/heads/main", encoding="utf-8")
    return package_dir


class TestInstallMethodPackage:
    def test_install_copies_files_writes_provenance_and_strips_git(self, tmp_path: Path) -> None:
        """A successful install lands the package files, the provenance sidecar, and no .git or staging leftovers."""
        package_dir = _make_package_dir(tmp_path)
        methods_dir = tmp_path / "methods"

        installed = install_method_package(package_dir=package_dir, name="scoring", provenance=PROVENANCE, methods_dir=methods_dir)

        assert installed.name == "scoring"
        assert installed.path == (methods_dir / "scoring").resolve()
        assert (installed.path / MANIFEST_FILENAME).is_file()
        assert (installed.path / "scoring.mthds").read_text(encoding="utf-8") == "# placeholder"
        assert not (installed.path / ".git").exists()
        assert installed.provenance == PROVENANCE
        assert MethodProvenance.model_validate_json((installed.path / PROVENANCE_FILENAME).read_text(encoding="utf-8")) == PROVENANCE
        leftovers = [entry.name for entry in methods_dir.iterdir() if entry.name != "scoring"]
        assert leftovers == []

    def test_install_without_provenance_writes_no_sidecar(self, tmp_path: Path) -> None:
        """Installing without provenance records nothing and discovery reports None."""
        package_dir = _make_package_dir(tmp_path)
        methods_dir = tmp_path / "methods"

        installed = install_method_package(package_dir=package_dir, name="scoring", methods_dir=methods_dir)

        assert installed.provenance is None
        assert not (installed.path / PROVENANCE_FILENAME).exists()

    def test_install_refuses_an_occupied_target(self, tmp_path: Path) -> None:
        """An existing target directory is never overwritten."""
        package_dir = _make_package_dir(tmp_path)
        methods_dir = tmp_path / "methods"
        (methods_dir / "scoring").mkdir(parents=True)

        with pytest.raises(MethodInstallError, match="already exists"):
            install_method_package(package_dir=package_dir, name="scoring", methods_dir=methods_dir)

    @pytest.mark.parametrize("bad_name", ["../evil", ".hidden", ""])
    def test_install_refuses_an_escaping_or_hidden_name(self, tmp_path: Path, bad_name: str) -> None:
        """A name that escapes the methods directory or would be skipped by discovery is refused."""
        package_dir = _make_package_dir(tmp_path)
        methods_dir = tmp_path / "methods"

        with pytest.raises(MethodInstallError):
            install_method_package(package_dir=package_dir, name=bad_name, methods_dir=methods_dir)

    def test_installed_method_is_found_by_full_address_case_insensitively(self, tmp_path: Path) -> None:
        """The installed method resolves by its full address, mirroring GitHub's case semantics."""
        package_dir = _make_package_dir(tmp_path)
        methods_dir = tmp_path / "methods"
        install_method_package(package_dir=package_dir, name="scoring", provenance=PROVENANCE, methods_dir=methods_dir)

        methods = discover_installed_methods(include_global=False, include_project=False, extra_search_dirs=[methods_dir])
        found = find_method_by_full_address("github.com/Pipelex-Tests/FOM-Methods/scoring", methods=methods)

        assert found is not None
        assert found.path == (methods_dir / "scoring").resolve()
        assert found.provenance == PROVENANCE

    def test_discovery_skips_dot_prefixed_directories(self, tmp_path: Path) -> None:
        """A dot-prefixed directory (e.g. a leftover staging dir) is never discovered as a method."""
        methods_dir = tmp_path / "methods"
        stale_staging = methods_dir / ".scoring.staging"
        stale_staging.mkdir(parents=True)
        (stale_staging / MANIFEST_FILENAME).write_text(MANIFEST, encoding="utf-8")

        methods = discover_installed_methods(include_global=False, include_project=False, extra_search_dirs=[methods_dir])

        assert methods == []
