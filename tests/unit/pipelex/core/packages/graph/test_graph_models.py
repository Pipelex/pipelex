from typing import ClassVar

import pytest
from pydantic import ValidationError

from pipelex.core.packages.graph.models import (
    NATIVE_PACKAGE_ADDRESS,
    ConceptId,
    ConceptNode,
    EdgeKind,
    GraphEdge,
    KnowHowGraph,
    PipeNode,
)


class TestData:
    NATIVE_TEXT_ID: ClassVar[ConceptId] = ConceptId(
        package_address=NATIVE_PACKAGE_ADDRESS,
        concept_ref="native.Text",
    )

    SCORING_CONCEPT_ID: ClassVar[ConceptId] = ConceptId(
        package_address="github.com/pkg_test/scoring-lib",
        concept_ref="pkg_test_scoring_dep.PkgTestWeightedScore",
    )

    LEGAL_CONCEPT_ID: ClassVar[ConceptId] = ConceptId(
        package_address="github.com/pkg_test/legal-tools",
        concept_ref="pkg_test_legal.PkgTestContractClause",
    )

    REFINED_CONCEPT_ID: ClassVar[ConceptId] = ConceptId(
        package_address="github.com/pkg_test/refining-app",
        concept_ref="pkg_test_refining.PkgTestRefinedScore",
    )

    PIPE_NODE: ClassVar[PipeNode] = PipeNode(
        package_address="github.com/pkg_test/legal-tools",
        pipe_code="pkg_test_extract_clause",
        pipe_type="PipeLLM",
        domain_code="pkg_test_legal",
        description="Extract clause from text",
        is_exported=True,
        input_concept_ids={
            "text": ConceptId(package_address=NATIVE_PACKAGE_ADDRESS, concept_ref="native.Text"),
        },
        output_concept_id=ConceptId(
            package_address="github.com/pkg_test/legal-tools",
            concept_ref="pkg_test_legal.PkgTestContractClause",
        ),
    )


class TestGraphModels:
    """Tests for know-how graph data models."""

    def test_concept_id_node_key(self) -> None:
        """ConceptId.node_key combines package_address and concept_ref."""
        assert TestData.SCORING_CONCEPT_ID.node_key == "github.com/pkg_test/scoring-lib::pkg_test_scoring_dep.PkgTestWeightedScore"

    def test_concept_id_concept_code(self) -> None:
        """ConceptId.concept_code returns the last segment of concept_ref."""
        assert TestData.SCORING_CONCEPT_ID.concept_code == "PkgTestWeightedScore"
        assert TestData.NATIVE_TEXT_ID.concept_code == "Text"

    def test_concept_id_is_native(self) -> None:
        """ConceptId.is_native returns True for native package address."""
        assert TestData.NATIVE_TEXT_ID.is_native is True
        assert TestData.SCORING_CONCEPT_ID.is_native is False

    def test_concept_id_is_frozen(self) -> None:
        """ConceptId fields cannot be mutated."""
        with pytest.raises(ValidationError):
            TestData.SCORING_CONCEPT_ID.package_address = "changed"  # type: ignore[misc]

    def test_concept_id_equality(self) -> None:
        """Two ConceptIds with the same fields are equal."""
        duplicate = ConceptId(
            package_address="github.com/pkg_test/scoring-lib",
            concept_ref="pkg_test_scoring_dep.PkgTestWeightedScore",
        )
        assert duplicate == TestData.SCORING_CONCEPT_ID

    def test_concept_id_different_packages_not_equal(self) -> None:
        """Same concept_ref in different packages are not equal."""
        analytics_score = ConceptId(
            package_address="github.com/pkg_test/analytics-lib",
            concept_ref="pkg_test_analytics.PkgTestWeightedScore",
        )
        assert analytics_score != TestData.SCORING_CONCEPT_ID

    def test_edge_kind_values(self) -> None:
        """EdgeKind enum has expected values."""
        assert EdgeKind.DATA_FLOW == "data_flow"
        assert EdgeKind.REFINEMENT == "refinement"

    def test_pipe_node_key(self) -> None:
        """PipeNode.node_key combines package_address and pipe_code."""
        assert TestData.PIPE_NODE.node_key == "github.com/pkg_test/legal-tools::pkg_test_extract_clause"

    def test_pipe_node_is_frozen(self) -> None:
        """PipeNode fields cannot be mutated."""
        with pytest.raises(ValidationError):
            TestData.PIPE_NODE.pipe_code = "changed"  # type: ignore[misc]

    def test_concept_node_without_refines(self) -> None:
        """ConceptNode can be created without a refines link."""
        node = ConceptNode(
            concept_id=TestData.LEGAL_CONCEPT_ID,
            description="A clause from a contract",
        )
        assert node.refines is None
        assert node.structure_fields == []

    def test_concept_node_with_refines(self) -> None:
        """ConceptNode stores a refinement link to another ConceptId."""
        node = ConceptNode(
            concept_id=TestData.REFINED_CONCEPT_ID,
            description="A refined score",
            refines=TestData.SCORING_CONCEPT_ID,
        )
        assert node.refines is not None
        assert node.refines.concept_code == "PkgTestWeightedScore"

    def test_graph_edge_data_flow(self) -> None:
        """GraphEdge with DATA_FLOW kind stores pipe keys and input param."""
        edge = GraphEdge(
            kind=EdgeKind.DATA_FLOW,
            source_pipe_key="pkg_a::pipe_x",
            target_pipe_key="pkg_b::pipe_y",
            input_param="text",
        )
        assert edge.kind == EdgeKind.DATA_FLOW
        assert edge.source_pipe_key == "pkg_a::pipe_x"
        assert edge.source_concept_id is None

    def test_graph_edge_refinement(self) -> None:
        """GraphEdge with REFINEMENT kind stores concept ids."""
        edge = GraphEdge(
            kind=EdgeKind.REFINEMENT,
            source_concept_id=TestData.REFINED_CONCEPT_ID,
            target_concept_id=TestData.SCORING_CONCEPT_ID,
        )
        assert edge.kind == EdgeKind.REFINEMENT
        assert edge.source_concept_id == TestData.REFINED_CONCEPT_ID
        assert edge.source_pipe_key is None

    def test_know_how_graph_get_pipe_node(self) -> None:
        """KnowHowGraph.get_pipe_node retrieves by key, returns None for unknown."""
        graph = KnowHowGraph()
        graph.pipe_nodes[TestData.PIPE_NODE.node_key] = TestData.PIPE_NODE
        assert graph.get_pipe_node(TestData.PIPE_NODE.node_key) is not None
        assert graph.get_pipe_node("nonexistent::key") is None

    def test_know_how_graph_get_concept_node(self) -> None:
        """KnowHowGraph.get_concept_node retrieves by ConceptId."""
        graph = KnowHowGraph()
        node = ConceptNode(
            concept_id=TestData.LEGAL_CONCEPT_ID,
            description="A clause",
        )
        graph.concept_nodes[TestData.LEGAL_CONCEPT_ID.node_key] = node
        assert graph.get_concept_node(TestData.LEGAL_CONCEPT_ID) is not None
        assert graph.get_concept_node(TestData.SCORING_CONCEPT_ID) is None

    def test_know_how_graph_outgoing_data_flow(self) -> None:
        """KnowHowGraph.get_outgoing_data_flow filters edges by source pipe."""
        graph = KnowHowGraph()
        edge_a = GraphEdge(
            kind=EdgeKind.DATA_FLOW,
            source_pipe_key="pkg::pipe_a",
            target_pipe_key="pkg::pipe_b",
            input_param="text",
        )
        edge_b = GraphEdge(
            kind=EdgeKind.DATA_FLOW,
            source_pipe_key="pkg::pipe_b",
            target_pipe_key="pkg::pipe_c",
            input_param="data",
        )
        graph.data_flow_edges.extend([edge_a, edge_b])
        outgoing = graph.get_outgoing_data_flow("pkg::pipe_a")
        assert len(outgoing) == 1
        assert outgoing[0].target_pipe_key == "pkg::pipe_b"

    def test_know_how_graph_incoming_data_flow(self) -> None:
        """KnowHowGraph.get_incoming_data_flow filters edges by target pipe."""
        graph = KnowHowGraph()
        edge = GraphEdge(
            kind=EdgeKind.DATA_FLOW,
            source_pipe_key="pkg::pipe_a",
            target_pipe_key="pkg::pipe_b",
            input_param="text",
        )
        graph.data_flow_edges.append(edge)
        incoming = graph.get_incoming_data_flow("pkg::pipe_b")
        assert len(incoming) == 1
        assert incoming[0].source_pipe_key == "pkg::pipe_a"
        assert graph.get_incoming_data_flow("pkg::pipe_a") == []
