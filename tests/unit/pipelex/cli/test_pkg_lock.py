import shutil
from pathlib import Path

import pytest
from click.exceptions import Exit

from pipelex.cli.commands.pkg.lock_cmd import do_pkg_lock
from pipelex.core.packages.lock_file import LOCK_FILENAME

PACKAGES_DATA_DIR = Path(__file__).resolve().parent.parent.parent.parent / "data" / "packages"


class TestPkgLock:
    """Tests for pipelex pkg lock command logic."""

    def test_lock_no_manifest_exits(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """No METHODS.toml -> Exit."""
        monkeypatch.chdir(tmp_path)

        with pytest.raises(Exit):
            do_pkg_lock()

    def test_lock_creates_methods_lock(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Manifest with no remote deps -> empty methods.lock."""
        src = PACKAGES_DATA_DIR / "minimal_package"
        shutil.copytree(src, tmp_path / "pkg")
        pkg_dir = tmp_path / "pkg"
        monkeypatch.chdir(pkg_dir)

        do_pkg_lock()

        lock_path = pkg_dir / LOCK_FILENAME
        assert lock_path.exists()

    def test_lock_with_local_dep_only(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Local path dep -> empty lock file (local deps excluded)."""
        src = PACKAGES_DATA_DIR / "consumer_package"
        shutil.copytree(src, tmp_path / "pkg")

        # Also copy the scoring_dep directory so the local path resolves
        scoring_src = PACKAGES_DATA_DIR / "scoring_dep"
        shutil.copytree(scoring_src, tmp_path / "scoring_dep")

        pkg_dir = tmp_path / "pkg"
        monkeypatch.chdir(pkg_dir)

        do_pkg_lock()

        lock_path = pkg_dir / LOCK_FILENAME
        assert lock_path.exists()
        # Local deps are excluded from lock file
        content = lock_path.read_text(encoding="utf-8")
        assert "github.com/mthds/scoring-lib" not in content
