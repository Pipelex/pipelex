from pathlib import Path

import pytest
from click.exceptions import Exit

from pipelex.cli.commands.pkg.graph_cmd import do_pkg_graph
from tests.unit.pipelex.core.packages.graph.test_data import (
    LEGAL_TOOLS_ADDRESS,
    make_test_package_index,
)


def _mock_build_index(_project_root: Path):
    """Return the shared test index regardless of project_root."""
    return make_test_package_index()


class TestPkgGraph:
    """Tests for pipelex pkg graph command logic."""

    def test_graph_no_options_exits(self) -> None:
        """No --from, --to, or --check flags -> exit 1."""
        with pytest.raises(Exit):
            do_pkg_graph()

    def test_graph_from_finds_pipes(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """--from __native__::native.Text finds pipes that accept Text."""
        monkeypatch.setattr(
            "pipelex.cli.commands.pkg.graph_cmd.build_index_from_project",
            _mock_build_index,
        )

        # Should not raise — pipes consuming Text exist in the test data
        do_pkg_graph(from_concept="__native__::native.Text")

    def test_graph_to_finds_pipes(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """--to with a known concept finds producing pipes."""
        monkeypatch.setattr(
            "pipelex.cli.commands.pkg.graph_cmd.build_index_from_project",
            _mock_build_index,
        )

        # pkg_test_analyze_clause produces Text
        do_pkg_graph(to_concept="__native__::native.Text")

    def test_graph_check_compatible(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """--check with compatible pipes shows compatible params."""
        monkeypatch.setattr(
            "pipelex.cli.commands.pkg.graph_cmd.build_index_from_project",
            _mock_build_index,
        )

        # extract_clause outputs PkgTestContractClause, analyze_clause accepts it
        source_key = f"{LEGAL_TOOLS_ADDRESS}::pkg_test_extract_clause"
        target_key = f"{LEGAL_TOOLS_ADDRESS}::pkg_test_analyze_clause"

        do_pkg_graph(check=f"{source_key},{target_key}")

    def test_graph_check_incompatible(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """--check with incompatible pipes shows yellow warning, no error."""
        monkeypatch.setattr(
            "pipelex.cli.commands.pkg.graph_cmd.build_index_from_project",
            _mock_build_index,
        )

        # analyze_clause: input=PkgTestContractClause, output=Text
        # Checking analyze -> analyze: output Text does NOT match input PkgTestContractClause
        source_key = f"{LEGAL_TOOLS_ADDRESS}::pkg_test_analyze_clause"
        target_key = f"{LEGAL_TOOLS_ADDRESS}::pkg_test_analyze_clause"

        do_pkg_graph(check=f"{source_key},{target_key}")

    def test_graph_invalid_concept_format_exits(self) -> None:
        """Bad concept format (missing ::) -> exit 1."""
        with pytest.raises(Exit):
            do_pkg_graph(from_concept="bad_format_no_separator")

    def test_graph_compose_without_from_to_exits(self) -> None:
        """--compose without both --from and --to -> exit 1."""
        with pytest.raises(Exit):
            do_pkg_graph(compose=True)

        with pytest.raises(Exit):
            do_pkg_graph(from_concept="__native__::native.Text", compose=True)

        with pytest.raises(Exit):
            do_pkg_graph(to_concept="__native__::native.Text", compose=True)

    def test_graph_compose_with_from_to_succeeds(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """--compose with --from and --to prints composition template without error."""
        monkeypatch.setattr(
            "pipelex.cli.commands.pkg.graph_cmd.build_index_from_project",
            _mock_build_index,
        )

        do_pkg_graph(
            from_concept="__native__::native.Text",
            to_concept=f"{LEGAL_TOOLS_ADDRESS}::pkg_test_legal.PkgTestContractClause",
            compose=True,
        )
