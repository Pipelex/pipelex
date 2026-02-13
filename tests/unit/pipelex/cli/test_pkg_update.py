import shutil
from pathlib import Path

import pytest
from click.exceptions import Exit

from pipelex.cli.commands.pkg.update_cmd import do_pkg_update
from pipelex.core.packages.lock_file import LOCK_FILENAME

PACKAGES_DATA_DIR = Path(__file__).resolve().parent.parent.parent.parent / "data" / "packages"


class TestPkgUpdate:
    """Tests for pipelex pkg update command logic."""

    def test_update_no_manifest_exits(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """No METHODS.toml -> Exit."""
        monkeypatch.chdir(tmp_path)

        with pytest.raises(Exit):
            do_pkg_update()

    def test_update_creates_lock_fresh(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Creates methods.lock when none exists."""
        src = PACKAGES_DATA_DIR / "minimal_package"
        shutil.copytree(src, tmp_path / "pkg")
        pkg_dir = tmp_path / "pkg"
        monkeypatch.chdir(pkg_dir)

        do_pkg_update()

        lock_path = pkg_dir / LOCK_FILENAME
        assert lock_path.exists()
