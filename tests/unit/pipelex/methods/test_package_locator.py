"""Unit tests for manifest-identity package location inside a fetched clone."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

import pytest

from pipelex.methods.exceptions import MethodPackageAmbiguityError, MethodPackageNotFoundError
from pipelex.methods.package_locator import locate_package_in_clone, scan_packages_in_clone

if TYPE_CHECKING:
    from pathlib import Path


def _write_manifest(package_dir: Path, *, address: str, name: str | None = None, main_pipe: str | None = None) -> None:
    package_dir.mkdir(parents=True, exist_ok=True)
    lines = ["[package]", f'address = "{address}"', 'version = "0.1.0"', 'description = "A test package."']
    if name is not None:
        lines.insert(1, f'name = "{name}"')
    if main_pipe is not None:
        lines.append(f'main_pipe = "{main_pipe}"')
    (package_dir / "METHODS.toml").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (package_dir / "core.mthds").write_text("# placeholder", encoding="utf-8")


class TestPackageLocator:
    """Tests for locating a package by manifest identity (repo-root and library-repo layouts)."""

    def test_repo_root_package_matches_by_address(self, tmp_path: Path) -> None:
        """A repo-root package whose manifest address equals the requested address is located."""
        _write_manifest(tmp_path, address="github.com/acme/legal-tools", name="legal_tools")

        located = locate_package_in_clone(clone_root=tmp_path, requested_address="github.com/acme/legal-tools")

        assert located.package_dir == tmp_path
        assert located.manifest.name == "legal_tools"
        assert located.full_address == "github.com/acme/legal-tools/legal_tools"

    def test_library_repo_package_matches_by_address_plus_name(self, tmp_path: Path) -> None:
        """In a library repo, address + '/' + name identifies the package regardless of directory path."""
        _write_manifest(tmp_path / "methods" / "documents", address="github.com/Pipelex/methods", name="documents")
        _write_manifest(tmp_path / "methods" / "imaging", address="github.com/Pipelex/methods", name="image_generation")

        located = locate_package_in_clone(clone_root=tmp_path, requested_address="github.com/Pipelex/methods/documents")

        assert located.package_dir == tmp_path / "methods" / "documents"
        assert located.full_address == "github.com/Pipelex/methods/documents"

        # Directory path is not the identity: the imaging/ directory holds image_generation
        located_by_name = locate_package_in_clone(clone_root=tmp_path, requested_address="github.com/Pipelex/methods/image_generation")
        assert located_by_name.package_dir == tmp_path / "methods" / "imaging"

    def test_address_match_is_case_insensitive(self, tmp_path: Path) -> None:
        """GitHub owner/repo names are case-insensitive, so the manifest-identity match is too."""
        _write_manifest(tmp_path / "pkg", address="github.com/pipelex/methods", name="documents")

        located = locate_package_in_clone(clone_root=tmp_path, requested_address="github.com/Pipelex/Methods/documents")

        assert located.full_address == "github.com/pipelex/methods/documents"

    def test_no_match_lists_candidates(self, tmp_path: Path) -> None:
        """A miss is a loud error naming the packages the clone does contain."""
        _write_manifest(tmp_path / "methods" / "documents", address="github.com/Pipelex/methods", name="documents")
        _write_manifest(tmp_path / "methods" / "imaging", address="github.com/Pipelex/methods", name="image_generation")

        with pytest.raises(MethodPackageNotFoundError) as exc_info:
            locate_package_in_clone(clone_root=tmp_path, requested_address="github.com/Pipelex/methods/nonexistent")

        message = str(exc_info.value)
        assert "github.com/Pipelex/methods/documents" in message
        assert "github.com/Pipelex/methods/image_generation" in message

    def test_empty_clone_is_a_loud_miss(self, tmp_path: Path) -> None:
        """A clone with no METHODS.toml at all raises with a clear message."""
        with pytest.raises(MethodPackageNotFoundError, match=re.escape("METHODS.toml")):
            locate_package_in_clone(clone_root=tmp_path, requested_address="github.com/acme/empty")

    def test_ambiguity_is_a_loud_error(self, tmp_path: Path) -> None:
        """Two packages matching the same requested address raise an ambiguity error listing both."""
        _write_manifest(tmp_path / "one", address="github.com/Pipelex/methods", name="documents")
        _write_manifest(tmp_path / "two", address="github.com/Pipelex/methods", name="documents")

        with pytest.raises(MethodPackageAmbiguityError, match="documents"):
            locate_package_in_clone(clone_root=tmp_path, requested_address="github.com/Pipelex/methods/documents")

    def test_bare_library_repo_address_lists_its_packages(self, tmp_path: Path) -> None:
        """Requesting a library repo's bare address matches every package that shares it — ambiguous, listing them."""
        _write_manifest(tmp_path / "methods" / "documents", address="github.com/Pipelex/methods", name="documents")
        _write_manifest(tmp_path / "methods" / "imaging", address="github.com/Pipelex/methods", name="image_generation")

        with pytest.raises(MethodPackageAmbiguityError) as exc_info:
            locate_package_in_clone(clone_root=tmp_path, requested_address="github.com/Pipelex/methods")

        message = str(exc_info.value)
        assert "github.com/Pipelex/methods/documents" in message
        assert "github.com/Pipelex/methods/image_generation" in message

    def test_invalid_manifest_is_reported_on_miss(self, tmp_path: Path) -> None:
        """A manifest that fails to parse is skipped but named when the location misses."""
        broken_dir = tmp_path / "broken"
        broken_dir.mkdir(parents=True)
        (broken_dir / "METHODS.toml").write_text("not [valid toml", encoding="utf-8")

        with pytest.raises(MethodPackageNotFoundError, match=re.escape("broken/METHODS.toml")):
            locate_package_in_clone(clone_root=tmp_path, requested_address="github.com/acme/broken")

    def test_scan_skips_git_directory(self, tmp_path: Path) -> None:
        """Manifests under .git/ are not candidates."""
        _write_manifest(tmp_path / ".git" / "junk", address="github.com/acme/junk", name="junk")
        _write_manifest(tmp_path / "pkg", address="github.com/acme/real", name="real")

        scan = scan_packages_in_clone(clone_root=tmp_path)

        assert [candidate.full_address for candidate in scan.candidates] == ["github.com/acme/real/real"]
