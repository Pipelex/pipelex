import shutil
from pathlib import Path

import pytest
from click.exceptions import Exit

from pipelex.cli.commands.pkg.inspect_cmd import do_pkg_inspect

PACKAGES_DATA_DIR = Path(__file__).resolve().parent.parent.parent.parent / "data" / "packages"


class TestPkgInspect:
    """Tests for pipelex pkg inspect command logic."""

    def test_inspect_existing_package(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Inspecting a known package address displays details without error."""
        src_dir = PACKAGES_DATA_DIR / "legal_tools"
        shutil.copytree(src_dir, tmp_path / "legal_tools")
        monkeypatch.chdir(tmp_path / "legal_tools")

        do_pkg_inspect(address="github.com/pipelexlab/legal-tools")

    def test_inspect_unknown_address_exits(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Inspecting a nonexistent address -> exit 1 with hint."""
        src_dir = PACKAGES_DATA_DIR / "legal_tools"
        shutil.copytree(src_dir, tmp_path / "legal_tools")
        monkeypatch.chdir(tmp_path / "legal_tools")

        with pytest.raises(Exit):
            do_pkg_inspect(address="no/such/package")

    def test_inspect_empty_project_exits(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """No packages in empty dir -> exit 1."""
        monkeypatch.chdir(tmp_path)

        with pytest.raises(Exit):
            do_pkg_inspect(address="any/address")
