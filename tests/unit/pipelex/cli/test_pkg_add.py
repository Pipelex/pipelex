import shutil
from pathlib import Path

import pytest
from click.exceptions import Exit

from pipelex.cli.commands.pkg.add_cmd import derive_alias_from_address, do_pkg_add
from pipelex.core.packages.discovery import MANIFEST_FILENAME
from pipelex.core.packages.manifest_parser import parse_methods_toml

# Path to the physical test data
PACKAGES_DATA_DIR = Path(__file__).resolve().parent.parent.parent.parent / "data" / "packages"


class TestPkgAdd:
    """Tests for pipelex pkg add command logic."""

    def test_add_dependency_to_manifest(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Add a dependency to an existing METHODS.toml."""
        # Copy a minimal package
        src = PACKAGES_DATA_DIR / "minimal_package"
        shutil.copytree(src, tmp_path / "pkg")
        pkg_dir = tmp_path / "pkg"
        monkeypatch.chdir(pkg_dir)

        do_pkg_add(
            address="github.com/org/scoring-lib",
            alias="scoring_lib",
            version="^2.0.0",
            path="../scoring-lib",
        )

        content = (pkg_dir / MANIFEST_FILENAME).read_text(encoding="utf-8")
        manifest = parse_methods_toml(content)
        assert len(manifest.dependencies) == 1
        dep = manifest.dependencies[0]
        assert dep.alias == "scoring_lib"
        assert dep.address == "github.com/org/scoring-lib"
        assert dep.version == "^2.0.0"
        assert dep.path == "../scoring-lib"

    def test_add_dependency_without_path(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Add a dependency without local path."""
        src = PACKAGES_DATA_DIR / "minimal_package"
        shutil.copytree(src, tmp_path / "pkg")
        pkg_dir = tmp_path / "pkg"
        monkeypatch.chdir(pkg_dir)

        do_pkg_add(
            address="github.com/org/other-lib",
            alias="other_lib",
            version="1.0.0",
        )

        content = (pkg_dir / MANIFEST_FILENAME).read_text(encoding="utf-8")
        manifest = parse_methods_toml(content)
        assert len(manifest.dependencies) == 1
        assert manifest.dependencies[0].path is None

    def test_auto_derive_alias(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Alias should be auto-derived from address if not provided."""
        src = PACKAGES_DATA_DIR / "minimal_package"
        shutil.copytree(src, tmp_path / "pkg")
        pkg_dir = tmp_path / "pkg"
        monkeypatch.chdir(pkg_dir)

        do_pkg_add(
            address="github.com/org/scoring-lib",
            version="1.0.0",
        )

        content = (pkg_dir / MANIFEST_FILENAME).read_text(encoding="utf-8")
        manifest = parse_methods_toml(content)
        assert len(manifest.dependencies) == 1
        assert manifest.dependencies[0].alias == "scoring_lib"

    def test_duplicate_alias_refuses(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Adding a dependency with duplicate alias refuses."""
        src = PACKAGES_DATA_DIR / "minimal_package"
        shutil.copytree(src, tmp_path / "pkg")
        pkg_dir = tmp_path / "pkg"
        monkeypatch.chdir(pkg_dir)

        do_pkg_add(
            address="github.com/org/first-lib",
            alias="my_dep",
            version="1.0.0",
        )

        with pytest.raises(Exit):
            do_pkg_add(
                address="github.com/org/second-lib",
                alias="my_dep",
                version="2.0.0",
            )

    def test_no_manifest_refuses(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Adding without existing METHODS.toml refuses."""
        monkeypatch.chdir(tmp_path)

        with pytest.raises(Exit):
            do_pkg_add(
                address="github.com/org/lib",
                alias="my_lib",
                version="1.0.0",
            )

    @pytest.mark.parametrize(
        ("address", "expected_alias"),
        [
            ("github.com/org/scoring-lib", "scoring_lib"),
            ("github.com/org/my.package", "my_package"),
            ("gitlab.com/team/simple", "simple"),
            ("github.com/org/UPPERCASE", "uppercase"),
        ],
    )
    def testderive_alias_from_address(self, address: str, expected_alias: str) -> None:
        """Auto-derived alias from various address formats."""
        assert derive_alias_from_address(address) == expected_alias
