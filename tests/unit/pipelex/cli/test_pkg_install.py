from pathlib import Path

import pytest
from click.exceptions import Exit

from pipelex.cli.commands.pkg.install_cmd import do_pkg_install
from pipelex.core.packages.lock_file import LOCK_FILENAME


class TestPkgInstall:
    """Tests for pipelex pkg install command logic."""

    def test_install_no_lock_exits(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """No methods.lock -> Exit."""
        monkeypatch.chdir(tmp_path)

        with pytest.raises(Exit):
            do_pkg_install()

    def test_install_empty_lock(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Empty lock file -> 'Nothing to install'."""
        monkeypatch.chdir(tmp_path)
        lock_path = tmp_path / LOCK_FILENAME
        lock_path.write_text("", encoding="utf-8")

        # Should not raise — prints "Nothing to install"
        do_pkg_install()
