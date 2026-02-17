import shutil
from io import StringIO
from pathlib import Path

import pytest
from click.exceptions import Exit
from rich.console import Console

from pipelex.cli.commands.pkg.search_cmd import do_pkg_search
from pipelex.core.packages.index.models import PackageIndex
from tests.unit.pipelex.core.packages.graph.test_data import make_test_package_index


def _mock_build_index(_path: Path) -> PackageIndex:
    return make_test_package_index()


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

    def test_search_both_concept_and_pipe_flags(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """When both --concept and --pipe flags are set, treat as 'show both'."""
        src_dir = PACKAGES_DATA_DIR / "legal_tools"
        shutil.copytree(src_dir, tmp_path / "legal_tools")
        monkeypatch.chdir(tmp_path / "legal_tools")

        # Should not raise or show "no results" — both concepts and pipes are searched
        do_pkg_search(query="ContractClause", concept_only=True, pipe_only=True)

    def test_search_empty_project_exits(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """No packages in empty dir -> exit 1."""
        monkeypatch.chdir(tmp_path)

        with pytest.raises(Exit):
            do_pkg_search(query="anything")

    # --- Type-compatible search tests (Phase 7A) ---

    def test_search_accepts_finds_pipes(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """accepts='Text' resolves to native.Text and finds pipes that accept it."""
        monkeypatch.setattr(
            "pipelex.cli.commands.pkg.search_cmd.build_index_from_project",
            _mock_build_index,
        )
        # All test pipes accept Text as input, so this should not raise
        do_pkg_search(accepts="Text")

    def test_search_produces_finds_pipes(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """produces='PkgTestContractClause' resolves uniquely and finds extract_clause."""
        monkeypatch.setattr(
            "pipelex.cli.commands.pkg.search_cmd.build_index_from_project",
            _mock_build_index,
        )
        do_pkg_search(produces="PkgTestContractClause")

    def test_search_accepts_ambiguous_concept(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """accepts='Score' matches multiple concepts across packages -> Exit raised."""
        monkeypatch.setattr(
            "pipelex.cli.commands.pkg.search_cmd.build_index_from_project",
            _mock_build_index,
        )
        with pytest.raises(Exit):
            do_pkg_search(accepts="Score")

    def test_search_accepts_no_concept_found(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """accepts='zzz_nonexistent_zzz' matches nothing -> prints message, no raise."""
        monkeypatch.setattr(
            "pipelex.cli.commands.pkg.search_cmd.build_index_from_project",
            _mock_build_index,
        )
        do_pkg_search(accepts="zzz_nonexistent_zzz")

    def test_search_produces_no_pipes(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """produces='Dynamic' resolves to native.Dynamic but no pipe produces it."""
        monkeypatch.setattr(
            "pipelex.cli.commands.pkg.search_cmd.build_index_from_project",
            _mock_build_index,
        )
        do_pkg_search(produces="Dynamic")

    def test_search_no_query_or_type_flag_exits(self) -> None:
        """No query, no accepts, no produces -> Exit raised."""
        with pytest.raises(Exit):
            do_pkg_search()

    def test_search_accepts_exact_match_preferred(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """accepts='Text' resolves to exactly native.Text (not TextAndImages) -> no Exit."""
        monkeypatch.setattr(
            "pipelex.cli.commands.pkg.search_cmd.build_index_from_project",
            _mock_build_index,
        )
        # "Text" is a substring of "TextAndImages", but exact match should prevent ambiguity
        do_pkg_search(accepts="Text")

    def test_search_accepts_with_domain_filter(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """accepts='Text' with domain='pkg_test_legal' returns only legal-domain pipes."""
        monkeypatch.setattr(
            "pipelex.cli.commands.pkg.search_cmd.build_index_from_project",
            _mock_build_index,
        )
        # Use a wide console to avoid Rich truncation
        string_io = StringIO()
        wide_console = Console(file=string_io, width=300)
        monkeypatch.setattr(
            "pipelex.cli.commands.pkg.search_cmd.get_console",
            lambda: wide_console,
        )
        do_pkg_search(accepts="Text", domain="pkg_test_legal")
        captured = string_io.getvalue()
        # The legal pipe that accepts Text should appear
        assert "pkg_test_extract_clause" in captured
        # Pipes from other domains should be excluded
        assert "pkg_test_compute_score" not in captured
        assert "pkg_test_refine_score" not in captured
        assert "pkg_test_compute_analytics" not in captured

    def test_search_produces_with_domain_filter(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """produces='Text' with domain from a non-matching domain yields no results."""
        monkeypatch.setattr(
            "pipelex.cli.commands.pkg.search_cmd.build_index_from_project",
            _mock_build_index,
        )
        # pkg_test_analyze_clause produces Text and is in pkg_test_legal domain.
        # Filtering to pkg_test_scoring_dep should exclude it, yielding no results.
        do_pkg_search(produces="Text", domain="pkg_test_scoring_dep")
