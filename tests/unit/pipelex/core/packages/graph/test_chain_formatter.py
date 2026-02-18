from pipelex.core.packages.graph.chain_formatter import format_chain_as_mthds_snippet
from pipelex.core.packages.graph.graph_builder import build_know_how_graph
from pipelex.core.packages.graph.models import (
    NATIVE_PACKAGE_ADDRESS,
    ConceptId,
    PipeNode,
)
from tests.unit.pipelex.core.packages.graph.test_data import (
    LEGAL_TOOLS_ADDRESS,
    SCORING_LIB_ADDRESS,
    make_test_package_index,
)

NATIVE_TEXT_ID = ConceptId(package_address=NATIVE_PACKAGE_ADDRESS, concept_ref="native.Text")
LEGAL_CONCEPT_ID = ConceptId(package_address=LEGAL_TOOLS_ADDRESS, concept_ref="pkg_test_legal.PkgTestContractClause")


def _build_graph_and_resolve(pipe_keys: list[str]) -> list[PipeNode]:
    """Build graph from test index and resolve pipe node_keys to PipeNodes."""
    index = make_test_package_index()
    graph = build_know_how_graph(index)
    pipe_nodes: list[PipeNode] = []
    for key in pipe_keys:
        node = graph.get_pipe_node(key)
        assert node is not None, f"Pipe node not found: {key}"
        pipe_nodes.append(node)
    return pipe_nodes


class TestChainFormatter:
    """Tests for the MTHDS chain composition formatter."""

    def test_format_single_step_chain(self) -> None:
        """Single-step chain shows Step 1 with correct pipe info, no cross-package note."""
        extract_key = f"{LEGAL_TOOLS_ADDRESS}::pkg_test_extract_clause"
        chain_pipes = _build_graph_and_resolve([extract_key])

        result = format_chain_as_mthds_snippet(chain_pipes, NATIVE_TEXT_ID, LEGAL_CONCEPT_ID)

        assert "Step 1: pkg_test_extract_clause" in result
        assert "Step 2" not in result
        assert LEGAL_TOOLS_ADDRESS in result
        assert "pkg_test_legal" in result
        assert "native.Text" in result
        assert "pkg_test_legal.PkgTestContractClause" in result
        assert "Note:" not in result

    def test_format_two_step_same_package(self) -> None:
        """Two-step same-package chain shows both steps with correct wiring, no cross-package note."""
        extract_key = f"{LEGAL_TOOLS_ADDRESS}::pkg_test_extract_clause"
        analyze_key = f"{LEGAL_TOOLS_ADDRESS}::pkg_test_analyze_clause"
        chain_pipes = _build_graph_and_resolve([extract_key, analyze_key])

        result = format_chain_as_mthds_snippet(chain_pipes, NATIVE_TEXT_ID, NATIVE_TEXT_ID)

        assert "Step 1: pkg_test_extract_clause" in result
        assert "Step 2: pkg_test_analyze_clause" in result
        # Step 1 output should feed into step 2 input
        assert "pkg_test_legal.PkgTestContractClause" in result
        assert "Note:" not in result

    def test_format_cross_package_chain(self) -> None:
        """Chain spanning multiple packages includes the cross-package note."""
        analyze_key = f"{LEGAL_TOOLS_ADDRESS}::pkg_test_analyze_clause"
        score_key = f"{SCORING_LIB_ADDRESS}::pkg_test_compute_score"
        chain_pipes = _build_graph_and_resolve([analyze_key, score_key])

        result = format_chain_as_mthds_snippet(chain_pipes, LEGAL_CONCEPT_ID, LEGAL_CONCEPT_ID)

        assert "Note: This chain spans multiple packages" in result

    def test_format_empty_chain(self) -> None:
        """Empty chain list returns empty string."""
        result = format_chain_as_mthds_snippet([], NATIVE_TEXT_ID, NATIVE_TEXT_ID)
        assert result == ""

    def test_format_header_shows_concept_flow(self) -> None:
        """Composition header line shows from -> intermediate -> to concept refs."""
        extract_key = f"{LEGAL_TOOLS_ADDRESS}::pkg_test_extract_clause"
        analyze_key = f"{LEGAL_TOOLS_ADDRESS}::pkg_test_analyze_clause"
        chain_pipes = _build_graph_and_resolve([extract_key, analyze_key])

        result = format_chain_as_mthds_snippet(chain_pipes, NATIVE_TEXT_ID, NATIVE_TEXT_ID)

        header_line = result.split("\n")[0]
        assert header_line.startswith("Composition:")
        assert "native.Text" in header_line
        assert "pkg_test_legal.PkgTestContractClause" in header_line
        # Final output should also be in the header
        parts = header_line.split(" -> ")
        assert parts[0] == "Composition: native.Text"
        assert parts[1] == "pkg_test_legal.PkgTestContractClause"
        assert parts[2] == "native.Text"
