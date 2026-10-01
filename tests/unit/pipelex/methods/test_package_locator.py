"""Unit tests for manifest-identity package location inside a fetched clone."""

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING, Self

import pytest

from pipelex.methods.exceptions import MethodPackageAmbiguityError, MethodPackageNotFoundError, MethodPackageTooLargeError
from pipelex.methods.package_locator import locate_package_in_clone, scan_packages_in_clone

if TYPE_CHECKING:
    from pytest_mock import MockerFixture


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
    """Tests for locating a package by manifest identity (repo-root and library-repo layouts), and for how the scan reads each manifest."""

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
        """Requesting a library repo's bare address matches no nested package — a loud miss listing them."""
        _write_manifest(tmp_path / "methods" / "documents", address="github.com/Pipelex/methods", name="documents")
        _write_manifest(tmp_path / "methods" / "imaging", address="github.com/Pipelex/methods", name="image_generation")

        with pytest.raises(MethodPackageNotFoundError) as exc_info:
            locate_package_in_clone(clone_root=tmp_path, requested_address="github.com/Pipelex/methods")

        message = str(exc_info.value)
        assert "github.com/Pipelex/methods/documents" in message
        assert "github.com/Pipelex/methods/image_generation" in message

    def test_single_nested_package_does_not_match_bare_repo_address(self, tmp_path: Path) -> None:
        """Address-only identity belongs to repo-root packages: one nested library package is not
        silently selected by the bare repository address — the miss lists its full address.
        """
        _write_manifest(tmp_path / "methods" / "documents", address="github.com/Pipelex/methods", name="documents")

        with pytest.raises(MethodPackageNotFoundError, match=re.escape("github.com/Pipelex/methods/documents")):
            locate_package_in_clone(clone_root=tmp_path, requested_address="github.com/Pipelex/methods")

    def test_oversized_manifest_is_skipped_and_reported(self, mocker: MockerFixture, tmp_path: Path) -> None:
        """A manifest larger than the size ceiling is never parsed; the miss names it."""
        big_dir = tmp_path / "big"
        big_dir.mkdir()
        (big_dir / "METHODS.toml").write_text("# " + "x" * 2048, encoding="utf-8")
        mocker.patch("pipelex.methods.package_locator.MAX_MANIFEST_FILE_BYTES", 1024)
        parse_spy = mocker.patch("pipelex.methods.package_locator.parse_methods_toml")

        with pytest.raises(MethodPackageNotFoundError, match="size ceiling"):
            locate_package_in_clone(clone_root=tmp_path, requested_address="github.com/acme/big")

        assert parse_spy.call_count == 0

    def test_manifest_scan_count_is_bounded(self, mocker: MockerFixture, tmp_path: Path) -> None:
        """A repository with more manifests than the scan ceiling is rejected."""
        for index_pkg in range(4):
            _write_manifest(tmp_path / f"pkg_{index_pkg}", address="github.com/acme/many", name=f"pkg_{index_pkg}")
        mocker.patch("pipelex.methods.package_locator.MAX_SCANNED_MANIFESTS", 3)

        with pytest.raises(MethodPackageTooLargeError, match="refusing to scan"):
            locate_package_in_clone(clone_root=tmp_path, requested_address="github.com/acme/many/pkg_0")

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

    # How the scan reads one manifest: a fetched repository can commit a `METHODS.toml` that is a
    # symlink, a directory or arbitrary bytes, and none of them may make the scan read outside the
    # clone, read without end, or crash. Only a regular file within the size ceiling is read, as UTF-8.

    def test_symlinked_manifest_is_skipped_unread(self, tmp_path: Path) -> None:
        """A symlinked manifest pointing outside the clone is never read: its target's values stay out of the miss.

        A valid sibling package in the same clone is still located, so the scan goes on past the skip.
        """
        clone_root = tmp_path / "clone"
        _write_manifest(clone_root / "real", address="github.com/acme/tools", name="real")
        outside_file = tmp_path / "host-settings.toml"
        outside_file.write_text('secret_token = "sentinel-value-1234"\n', encoding="utf-8")
        linked_dir = clone_root / "linked"
        linked_dir.mkdir()
        (linked_dir / "METHODS.toml").symlink_to(outside_file)

        scan = scan_packages_in_clone(clone_root=clone_root)

        assert [candidate.full_address for candidate in scan.candidates] == ["github.com/acme/tools/real"]
        assert scan.skipped_manifests == ["linked/METHODS.toml: is a symlink, skipped (fetched manifests must be regular files)"]

        located = locate_package_in_clone(clone_root=clone_root, requested_address="github.com/acme/tools/real")
        assert located.package_dir == clone_root / "real"

        with pytest.raises(MethodPackageNotFoundError) as exc_info:
            locate_package_in_clone(clone_root=clone_root, requested_address="github.com/acme/tools/missing")
        message = str(exc_info.value)
        assert "Manifests skipped: linked/METHODS.toml: is a symlink" in message
        assert "sentinel-value-1234" not in message
        assert "secret_token" not in message
        assert str(tmp_path) not in message

    @pytest.mark.timeout(10)
    @pytest.mark.skipif(not Path("/dev/zero").exists(), reason="needs a /dev/zero device")
    def test_symlink_to_an_endless_device_is_skipped_unread(self, tmp_path: Path) -> None:
        """A manifest linked to /dev/zero reports a size of 0 but would read forever: the scan never opens it."""
        (tmp_path / "METHODS.toml").symlink_to(Path("/dev/zero"))

        scan = scan_packages_in_clone(clone_root=tmp_path)

        assert scan.candidates == []
        assert scan.skipped_manifests == ["METHODS.toml: is a symlink, skipped (fetched manifests must be regular files)"]

    def test_dangling_symlinked_manifest_is_skipped(self, tmp_path: Path) -> None:
        """A dangling symlinked manifest is reported as a symlink, rather than escaping as a FileNotFoundError."""
        (tmp_path / "METHODS.toml").symlink_to(tmp_path / "nowhere.toml")

        with pytest.raises(MethodPackageNotFoundError) as exc_info:
            locate_package_in_clone(clone_root=tmp_path, requested_address="github.com/acme/dangling")

        message = str(exc_info.value)
        assert "METHODS.toml: is a symlink" in message
        assert "nowhere.toml" not in message
        assert str(tmp_path) not in message

    def test_directory_named_like_a_manifest_is_skipped(self, tmp_path: Path) -> None:
        """A directory named METHODS.toml is reported as not a regular file, rather than escaping as an IsADirectoryError."""
        (tmp_path / "pkg" / "METHODS.toml").mkdir(parents=True)

        scan = scan_packages_in_clone(clone_root=tmp_path)

        assert scan.candidates == []
        assert scan.skipped_manifests == ["pkg/METHODS.toml: is not a regular file, skipped"]

    def test_manifest_that_is_not_utf8_is_skipped(self, tmp_path: Path) -> None:
        """A manifest of invalid UTF-8 bytes is reported, rather than escaping as a UnicodeDecodeError."""
        package_dir = tmp_path / "pkg"
        package_dir.mkdir()
        (package_dir / "METHODS.toml").write_bytes(b'[package]\naddress = "\xff\xfe"\n')

        scan = scan_packages_in_clone(clone_root=tmp_path)

        assert scan.candidates == []
        assert scan.skipped_manifests == ["pkg/METHODS.toml: is not valid UTF-8, skipped"]

    def test_the_read_stops_at_the_size_ceiling(self, mocker: MockerFixture, tmp_path: Path) -> None:
        """The read itself is bounded: a regular file whose content outruns any size reported for it is cut at the ceiling.

        The stream stands in for such a file and fails the test on a read without a bound.
        """
        (tmp_path / "METHODS.toml").write_text("# placeholder", encoding="utf-8")
        mocker.patch("pipelex.methods.package_locator.MAX_MANIFEST_FILE_BYTES", 1024)
        read_sizes: list[int] = []

        class _EndlessStream:
            def __enter__(self) -> Self:
                return self

            def __exit__(self, *exc_info: object) -> None:
                return None

            def read(self, size: int = -1) -> bytes:
                if size < 0:
                    msg = "the manifest was read without a bound"
                    raise AssertionError(msg)
                read_sizes.append(size)
                return b"#" * size

        mocker.patch.object(Path, "open", return_value=_EndlessStream())

        scan = scan_packages_in_clone(clone_root=tmp_path)

        assert read_sizes == [1025]
        assert scan.skipped_manifests == ["METHODS.toml: exceeds the manifest size ceiling of 1024 bytes, skipped"]

    def test_symlinked_directory_is_not_descended(self, tmp_path: Path) -> None:
        """A symlinked directory pointing outside the clone is not walked, so a manifest behind it is no candidate.

        The scan only ever meets links named METHODS.toml themselves because the walk does not follow
        directory links; this pins that against a future Python or a walker that would.
        """
        clone_root = tmp_path / "clone"
        clone_root.mkdir()
        outside_dir = tmp_path / "outside"
        _write_manifest(outside_dir, address="github.com/acme/outside", name="outside")
        (clone_root / "vendored").symlink_to(outside_dir, target_is_directory=True)

        scan = scan_packages_in_clone(clone_root=clone_root)

        assert scan.candidates == []
        assert scan.skipped_manifests == []
