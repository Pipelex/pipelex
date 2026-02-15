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

    def test_graph_invalid_concept_format_exits(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Bad concept format (missing ::) -> exit 1."""
        monkeypatch.setattr(
            "pipelex.cli.commands.pkg.graph_cmd.build_index_from_project",
            _mock_build_index,
        )

        with pytest.raises(Exit):
            do_pkg_graph(from_concept="bad_format_no_separator")

    @pytest.mark.parametrize(
        "raw_concept",
        [
            pytest.param("package::", id="empty_concept_ref"),
            pytest.param("::concept", id="empty_package_address"),
            pytest.param("::", id="both_empty"),
        ],
    )
    def test_graph_concept_id_empty_parts_exits(self, monkeypatch: pytest.MonkeyPatch, raw_concept: str) -> None:
        """Concept IDs with empty package_address or concept_ref after splitting -> exit 1."""
        monkeypatch.setattr(
            "pipelex.cli.commands.pkg.graph_cmd.build_index_from_project",
            _mock_build_index,
        )

        with pytest.raises(Exit):
            do_pkg_graph(from_concept=raw_concept)

    def test_graph_concept_id_multiple_separators_exits(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Concept ID with multiple :: separators -> exit 1."""
        monkeypatch.setattr(
            "pipelex.cli.commands.pkg.graph_cmd.build_index_from_project",
            _mock_build_index,
        )

        with pytest.raises(Exit):
            do_pkg_graph(from_concept="package::domain::Concept")

    @pytest.mark.parametrize(
        "check_arg",
        [
            pytest.param("pipe1,", id="empty_target"),
            pytest.param(",pipe2", id="empty_source"),
            pytest.param(",", id="both_empty"),
        ],
    )
    def test_graph_check_empty_pipe_key_exits(self, monkeypatch: pytest.MonkeyPatch, check_arg: str) -> None:
        """--check with empty pipe key after comma split -> exit 1."""
        monkeypatch.setattr(
            "pipelex.cli.commands.pkg.graph_cmd.build_index_from_project",
            _mock_build_index,
        )

        with pytest.raises(Exit):
            do_pkg_graph(check=check_arg)
