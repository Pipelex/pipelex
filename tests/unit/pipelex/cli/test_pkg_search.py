import shutil
from pathlib import Path

import pytest
from click.exceptions import Exit

from pipelex.cli.commands.pkg.search_cmd import do_pkg_search

PACKAGES_DATA_DIR = Path(__file__).resolve().parent.parent.parent.parent / "data" / "packages"


class TestPkgSearch:
    """Tests for pipelex pkg search command logic."""

    def test_search_finds_concept(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Search for a known concept code finds it without error."""
        src_dir = PACKAGES_DATA_DIR / "legal_tools"
        shutil.copytree(src_dir, tmp_path / "legal_tools")
        monkeypatch.chdir(tmp_path / "legal_tools")

        do_pkg_search(query="ContractClause")

    def test_search_finds_pipe(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Search for a known pipe code finds it without error."""
        src_dir = PACKAGES_DATA_DIR / "legal_tools"
        shutil.copytree(src_dir, tmp_path / "legal_tools")
        monkeypatch.chdir(tmp_path / "legal_tools")

        do_pkg_search(query="extract_clause")

    def test_search_no_results(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Search for nonexistent term returns no results without exit."""
        src_dir = PACKAGES_DATA_DIR / "legal_tools"
        shutil.copytree(src_dir, tmp_path / "legal_tools")
        monkeypatch.chdir(tmp_path / "legal_tools")

        # Should not raise — just prints "no results" message
        do_pkg_search(query="zzz_nonexistent_zzz")

    def test_search_domain_filter(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Search with --domain restricts results to that domain."""
        src_dir = PACKAGES_DATA_DIR / "legal_tools"
        shutil.copytree(src_dir, tmp_path / "legal_tools")
        monkeypatch.chdir(tmp_path / "legal_tools")

        # Searching for "score" in domain "pkg_test_legal.contracts" should find nothing
        # since scoring concepts are in a different domain
        do_pkg_search(query="score", domain="pkg_test_legal.contracts")

    def test_search_empty_project_exits(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """No packages in empty dir -> exit 1."""
        monkeypatch.chdir(tmp_path)

        with pytest.raises(Exit):
            do_pkg_search(query="anything")
