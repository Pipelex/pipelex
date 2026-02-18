import shutil
from pathlib import Path

import pytest
from click.exceptions import Exit

from pipelex.cli.commands.pkg.list_cmd import do_pkg_list
from pipelex.core.packages.discovery import MANIFEST_FILENAME

# Path to the physical test data
PACKAGES_DATA_DIR = Path(__file__).resolve().parent.parent.parent.parent / "data" / "packages"


class TestPkgList:
    """Tests for pipelex pkg list command logic."""

    def test_display_manifest_info(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """With valid METHODS.toml -> displays info without error."""
        src_manifest = PACKAGES_DATA_DIR / "minimal_package" / MANIFEST_FILENAME
        shutil.copy(src_manifest, tmp_path / MANIFEST_FILENAME)

        monkeypatch.chdir(tmp_path)

        # Should not raise — it prints to console but doesn't return anything
        do_pkg_list()

    def test_no_manifest_found_error(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """No METHODS.toml found -> error exit."""
        monkeypatch.chdir(tmp_path)

        with pytest.raises(Exit):
            do_pkg_list()

    def test_display_manifest_with_exports(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """With full METHODS.toml including exports -> displays all sections."""
        src_dir = PACKAGES_DATA_DIR / "legal_tools"
        shutil.copytree(src_dir, tmp_path / "legal_tools")

        monkeypatch.chdir(tmp_path / "legal_tools")

        # Should not raise — it prints tables including exports
        do_pkg_list()
