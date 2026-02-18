import shutil
from pathlib import Path

import pytest
from click.exceptions import Exit

from pipelex.cli.commands.pkg.init_cmd import do_pkg_init
from pipelex.core.packages.discovery import MANIFEST_FILENAME
from pipelex.core.packages.manifest_parser import parse_methods_toml

# Path to the physical test data
PACKAGES_DATA_DIR = Path(__file__).resolve().parent.parent.parent.parent / "data" / "packages"


class TestPkgInit:
    """Tests for pipelex pkg init command logic."""

    def test_generate_manifest_from_mthds_files(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """With .mthds files in tmp dir -> generates valid METHODS.toml."""
        src = PACKAGES_DATA_DIR / "minimal_package" / "core.mthds"
        shutil.copy(src, tmp_path / "core.mthds")

        monkeypatch.chdir(tmp_path)

        do_pkg_init(force=False)

        manifest_path = tmp_path / MANIFEST_FILENAME
        assert manifest_path.exists()

        content = manifest_path.read_text(encoding="utf-8")
        manifest = parse_methods_toml(content)
        assert manifest.version == "0.1.0"
        assert len(manifest.exports) >= 1

    def test_existing_manifest_without_force_refuses(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Existing METHODS.toml without --force -> refuses."""
        src = PACKAGES_DATA_DIR / "minimal_package" / "core.mthds"
        shutil.copy(src, tmp_path / "core.mthds")
        (tmp_path / MANIFEST_FILENAME).write_text("[package]\n", encoding="utf-8")

        monkeypatch.chdir(tmp_path)

        with pytest.raises(Exit):
            do_pkg_init(force=False)

    def test_existing_manifest_with_force_overwrites(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """With --force -> overwrites existing METHODS.toml."""
        src = PACKAGES_DATA_DIR / "minimal_package" / "core.mthds"
        shutil.copy(src, tmp_path / "core.mthds")
        (tmp_path / MANIFEST_FILENAME).write_text("[package]\nold = true\n", encoding="utf-8")

        monkeypatch.chdir(tmp_path)

        do_pkg_init(force=True)

        content = (tmp_path / MANIFEST_FILENAME).read_text(encoding="utf-8")
        assert "old" not in content
        manifest = parse_methods_toml(content)
        assert manifest.version == "0.1.0"

    def test_main_pipe_appears_first_in_exports(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """main_pipe should appear first in domain exports, not buried alphabetically."""
        legal_tools_dir = PACKAGES_DATA_DIR / "legal_tools"
        # Copy both .mthds files preserving subdirectory structure
        for mthds_file in legal_tools_dir.rglob("*.mthds"):
            rel = mthds_file.relative_to(legal_tools_dir)
            dest = tmp_path / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(mthds_file, dest)

        monkeypatch.chdir(tmp_path)
        do_pkg_init(force=False)

        manifest_path = tmp_path / MANIFEST_FILENAME
        manifest = parse_methods_toml(manifest_path.read_text(encoding="utf-8"))

        # Find the contracts domain
        contracts_export = next(
            (exp for exp in manifest.exports if exp.domain_path == "pkg_test_legal.contracts"),
            None,
        )
        assert contracts_export is not None, "Expected pkg_test_legal.contracts domain in exports"
        assert contracts_export.pipes[0] == "pkg_test_extract_clause", f"main_pipe should be first in exports, got: {contracts_export.pipes}"

    def test_no_mthds_files_error(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """No .mthds files -> error message."""
        monkeypatch.chdir(tmp_path)

        with pytest.raises(Exit):
            do_pkg_init(force=False)
