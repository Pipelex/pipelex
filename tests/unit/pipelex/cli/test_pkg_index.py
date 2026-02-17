import shutil
from pathlib import Path

import pytest
from click.exceptions import Exit

from pipelex.cli.commands.pkg.index_cmd import do_pkg_index
from pipelex.core.packages.index.models import PackageIndex

PACKAGES_DATA_DIR = Path(__file__).resolve().parent.parent.parent.parent / "data" / "packages"


class TestPkgIndex:
    """Tests for pipelex pkg index command logic."""

    def test_index_project_with_manifest(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """With valid package directory -> displays index table without error."""
        src_dir = PACKAGES_DATA_DIR / "legal_tools"
        shutil.copytree(src_dir, tmp_path / "legal_tools")

        monkeypatch.chdir(tmp_path / "legal_tools")

        do_pkg_index()

    def test_index_empty_project_exits(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Empty directory with no METHODS.toml -> exit 1."""
        monkeypatch.chdir(tmp_path)

        with pytest.raises(Exit):
            do_pkg_index()

    def test_index_cache_empty_exits(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Monkeypatched build_index_from_cache returning empty index -> exit 1."""

        def _empty_cache(_cache_root: Path | None = None) -> PackageIndex:
            return PackageIndex()

        monkeypatch.setattr(
            "pipelex.cli.commands.pkg.index_cmd.build_index_from_cache",
            _empty_cache,
        )

        with pytest.raises(Exit):
            do_pkg_index(cache=True)
