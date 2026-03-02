"""Unit tests for discover_methods_from_library_dirs and find_method_by_name with library_dirs."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from mthds.package.discovery import MANIFEST_FILENAME
from mthds.package.manifest.parser import parse_methods_toml

from pipelex.cli.installed_methods import (
    DuplicateMethodNameError,
    InstalledMethod,
    MethodNotFoundError,
    discover_methods_from_library_dirs,
    find_method_by_name,
)

if TYPE_CHECKING:
    from pathlib import Path

MINIMAL_MANIFEST_TEMPLATE = """\
[package]
address = "github.com/test/{address_suffix}"
version = "0.1.0"
description = "A test method"
{name_line}
main_pipe = "test_pipe"

[exports.test]
pipes = ["test_pipe"]
"""


def _write_manifest(method_dir: Path, name: str | None = None, address_suffix: str = "pkg") -> None:
    """Write a minimal METHODS.toml into *method_dir*."""
    method_dir.mkdir(parents=True, exist_ok=True)
    name_line = f'name = "{name}"' if name else ""
    content = MINIMAL_MANIFEST_TEMPLATE.format(address_suffix=address_suffix, name_line=name_line)
    (method_dir / MANIFEST_FILENAME).write_text(content, encoding="utf-8")


class TestDiscoverMethodsFromLibraryDirs:
    """Tests for discover_methods_from_library_dirs and find_method_by_name with library_dirs."""

    def test_discovers_method_with_manifest(self, tmp_path: Path) -> None:
        """A directory containing METHODS.toml is discovered as an installed method."""
        method_dir = tmp_path / "my-method"
        _write_manifest(method_dir, name="my_method")
        (method_dir / "core.mthds").write_text("# placeholder", encoding="utf-8")

        results = discover_methods_from_library_dirs([str(method_dir)])

        assert len(results) == 1
        assert results[0].name == "my_method"
        assert results[0].path == method_dir.resolve()
        assert len(results[0].mthds_files) == 1
        assert results[0].mthds_files[0].name == "core.mthds"

    def test_skips_directory_without_manifest(self, tmp_path: Path) -> None:
        """A directory without METHODS.toml is silently skipped."""
        method_dir = tmp_path / "no-manifest"
        method_dir.mkdir()
        (method_dir / "core.mthds").write_text("# placeholder", encoding="utf-8")

        results = discover_methods_from_library_dirs([str(method_dir)])

        assert results == []

    def test_skips_nonexistent_directory(self, tmp_path: Path) -> None:
        """A non-existent directory path is silently skipped."""
        results = discover_methods_from_library_dirs([str(tmp_path / "does-not-exist")])

        assert results == []

    def test_deduplicates_by_resolved_path(self, tmp_path: Path) -> None:
        """The same directory passed multiple times yields only one method."""
        method_dir = tmp_path / "dup-method"
        _write_manifest(method_dir, name="dup_method")

        results = discover_methods_from_library_dirs([str(method_dir), str(method_dir)])

        assert len(results) == 1

    def test_name_falls_back_to_directory_name(self, tmp_path: Path) -> None:
        """When manifest has no 'name', the directory name is used."""
        method_dir = tmp_path / "fallback-name"
        _write_manifest(method_dir, name=None)

        results = discover_methods_from_library_dirs([str(method_dir)])

        assert len(results) == 1
        assert results[0].name == "fallback-name"

    def test_discovers_methods_in_subdirectories(self, tmp_path: Path) -> None:
        """When -L points to a parent dir (no METHODS.toml at root), subdirs are scanned."""
        parent_dir = tmp_path / "methods"
        parent_dir.mkdir()

        method_a = parent_dir / "method-a"
        _write_manifest(method_a, name="method_a", address_suffix="a")
        (method_a / "a.mthds").write_text("# placeholder", encoding="utf-8")

        method_b = parent_dir / "method-b"
        _write_manifest(method_b, name="method_b", address_suffix="b")
        (method_b / "b.mthds").write_text("# placeholder", encoding="utf-8")

        # A non-method subdirectory (no METHODS.toml) should be ignored
        (parent_dir / "not-a-method").mkdir()

        results = discover_methods_from_library_dirs([str(parent_dir)])

        assert len(results) == 2
        names = {result.name for result in results}
        assert names == {"method_a", "method_b"}

    def test_discovers_methods_nested_deeply(self, tmp_path: Path) -> None:
        """When -L points to a grandparent dir, methods nested multiple levels deep are found."""
        # Simulates: -L . where ./methods/cv-analyzer/METHODS.toml exists
        root_dir = tmp_path / "project"
        root_dir.mkdir()
        method_dir = root_dir / "methods" / "cv-analyzer"
        _write_manifest(method_dir, name="cv_analyzer", address_suffix="cv")
        (method_dir / "cv.mthds").write_text("# placeholder", encoding="utf-8")

        results = discover_methods_from_library_dirs([str(root_dir)])

        assert len(results) == 1
        assert results[0].name == "cv_analyzer"

    def test_find_method_by_name_with_library_dirs(self, tmp_path: Path) -> None:
        """find_method_by_name discovers a method via library_dirs when not in standard locations."""
        method_dir = tmp_path / "lib-method"
        _write_manifest(method_dir, name="lib_method")
        (method_dir / "lib.mthds").write_text("# placeholder", encoding="utf-8")

        result = find_method_by_name("lib_method", methods=[], library_dirs=[str(method_dir)])

        assert result.name == "lib_method"
        assert result.path == method_dir.resolve()

    def test_find_method_by_name_not_found_raises(self, tmp_path: Path) -> None:
        """MethodNotFoundError is raised when the method is absent from both standard and library dirs."""
        method_dir = tmp_path / "other-method"
        _write_manifest(method_dir, name="other_method")

        with pytest.raises(MethodNotFoundError):
            find_method_by_name("nonexistent", methods=[], library_dirs=[str(method_dir)])

    def test_find_method_by_name_duplicate_raises(self, tmp_path: Path) -> None:
        """DuplicateMethodNameError is raised when same name appears in standard and library dirs."""
        method_dir = tmp_path / "dup"
        _write_manifest(method_dir, name="dup_name", address_suffix="pkg2")
        (method_dir / "dup.mthds").write_text("# placeholder", encoding="utf-8")

        # Simulate a pre-discovered method with the same name but different path
        other_dir = tmp_path / "other-dup"
        _write_manifest(other_dir, name="dup_name", address_suffix="pkg3")

        manifest_content = (other_dir / MANIFEST_FILENAME).read_text(encoding="utf-8")
        pre_existing = InstalledMethod(
            name="dup_name",
            path=other_dir.resolve(),
            manifest=parse_methods_toml(manifest_content),
            mthds_files=[],
        )

        with pytest.raises(DuplicateMethodNameError):
            find_method_by_name("dup_name", methods=[pre_existing], library_dirs=[str(method_dir)])
