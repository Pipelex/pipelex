"""Unit tests for the graphspec_to_combo_mermaid_with_data function."""

from datetime import UTC, datetime
from typing import Any, ClassVar

from pipelex.graph.graphspec import (
    EdgeSpec,
    GraphSpec,
    IOSpec,
    NodeIOSpec,
    NodeKind,
    NodeSpec,
    NodeStatus,
    PipelineRef,
)
from pipelex.graph.mermaid import (
    MermaidWithData,
    graphspec_to_combo_mermaid,
    graphspec_to_combo_mermaid_with_data,
)


class TestComboMermaidWithData:
    """Tests for graphspec_to_combo_mermaid_with_data function."""

    GRAPH_ID: ClassVar[str] = "combo_data_test:001"
    CREATED_AT: ClassVar[datetime] = datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC)

    def _make_graph(
        self,
        nodes: list[dict[str, Any]],
        edges: list[dict[str, Any]] | None = None,
    ) -> GraphSpec:
        """Helper to create a GraphSpec with nodes and edges."""
        node_specs: list[NodeSpec] = []
        for node_dict in nodes:
            node_specs.append(NodeSpec(**node_dict))

        edge_specs: list[EdgeSpec] = []
        if edges:
            for edge_dict in edges:
                edge_specs.append(EdgeSpec(**edge_dict))

        return GraphSpec(
            graph_id=self.GRAPH_ID,
            created_at=self.CREATED_AT,
            pipeline_ref=PipelineRef(),
            nodes=node_specs,
            edges=edge_specs,
        )

    def test_returns_mermaid_with_data(self) -> None:
        """Test that function returns MermaidWithData instance."""
        producer_node = {
            "node_id": "node_1",
            "kind": NodeKind.OPERATOR,
            "pipe_code": "producer",
            "status": NodeStatus.SUCCEEDED,
            "node_io": NodeIOSpec(
                inputs=[],
                outputs=[IOSpec(name="output", concept="Text", digest="stuff_001", data="test data content")],
            ),
        }
        graph = self._make_graph(nodes=[producer_node])
        result = graphspec_to_combo_mermaid_with_data(graph)

        assert isinstance(result, MermaidWithData)
        assert isinstance(result.mermaid_code, str)
        assert isinstance(result.stuff_data, dict)

    def test_stuff_data_populated_from_outputs(self) -> None:
        """Test that stuff_data is populated from node outputs with data."""
        producer_node = {
            "node_id": "node_1",
            "kind": NodeKind.OPERATOR,
            "pipe_code": "producer",
            "status": NodeStatus.SUCCEEDED,
            "node_io": NodeIOSpec(
                inputs=[],
                outputs=[IOSpec(name="output", concept="Text", digest="stuff_abc123", data="output data content")],
            ),
        }
        graph = self._make_graph(nodes=[producer_node])
        result = graphspec_to_combo_mermaid_with_data(graph)

        # Should have stuff_data with the data content
        assert len(result.stuff_data) > 0
        # Data should be present in values
        data_values = list(result.stuff_data.values())
        assert "output data content" in data_values

    def test_stuff_data_keys_match_mermaid_ids(self) -> None:
        """Test that stuff_data keys use s_xxx format matching mermaid node IDs."""
        producer_node = {
            "node_id": "node_1",
            "kind": NodeKind.OPERATOR,
            "pipe_code": "producer",
            "status": NodeStatus.SUCCEEDED,
            "node_io": NodeIOSpec(
                inputs=[],
                outputs=[IOSpec(name="output", concept="Text", digest="stuff_abc123", data="test data")],
            ),
        }
        graph = self._make_graph(nodes=[producer_node])
        result = graphspec_to_combo_mermaid_with_data(graph)

        # Keys should start with s_ prefix
        for key in result.stuff_data:
            assert key.startswith("s_"), f"Key {key} should start with 's_'"

    def test_stuff_data_from_inputs_without_producer(self) -> None:
        """Test that stuff_data includes inputs that have no producer (pipeline inputs)."""
        consumer_node = {
            "node_id": "node_1",
            "kind": NodeKind.OPERATOR,
            "pipe_code": "consumer",
            "status": NodeStatus.SUCCEEDED,
            "node_io": NodeIOSpec(
                inputs=[IOSpec(name="pipeline_input", concept="Text", digest="input_digest", data="input data content")],
                outputs=[],
            ),
        }
        graph = self._make_graph(nodes=[consumer_node])
        result = graphspec_to_combo_mermaid_with_data(graph)

        # Should have stuff_data for the input
        assert len(result.stuff_data) > 0
        data_values = list(result.stuff_data.values())
        assert "input data content" in data_values

    def test_stuff_data_not_duplicated(self) -> None:
        """Test that stuff_data doesn't duplicate when same digest appears in output and input."""
        producer_node = {
            "node_id": "node_1",
            "kind": NodeKind.OPERATOR,
            "pipe_code": "producer",
            "status": NodeStatus.SUCCEEDED,
            "node_io": NodeIOSpec(
                inputs=[],
                outputs=[IOSpec(name="output", concept="Text", digest="shared_digest", data="the data")],
            ),
        }
        consumer_node = {
            "node_id": "node_2",
            "kind": NodeKind.OPERATOR,
            "pipe_code": "consumer",
            "status": NodeStatus.SUCCEEDED,
            "node_io": NodeIOSpec(
                inputs=[IOSpec(name="input", concept="Text", digest="shared_digest", data="the data")],
                outputs=[],
            ),
        }
        graph = self._make_graph(nodes=[producer_node, consumer_node])
        result = graphspec_to_combo_mermaid_with_data(graph)

        # Should only have one entry for this digest
        data_values = list(result.stuff_data.values())
        assert data_values.count("the data") == 1

    def test_mermaid_code_matches_non_data_version(self) -> None:
        """Test that mermaid_code is the same as graphspec_to_combo_mermaid output."""
        producer_node = {
            "node_id": "node_1",
            "kind": NodeKind.OPERATOR,
            "pipe_code": "producer",
            "status": NodeStatus.SUCCEEDED,
            "node_io": NodeIOSpec(
                inputs=[],
                outputs=[IOSpec(name="output", concept="Text", digest="stuff_001", data="test data")],
            ),
        }
        graph = self._make_graph(nodes=[producer_node])

        result_with_data = graphspec_to_combo_mermaid_with_data(graph)
        result_without_data = graphspec_to_combo_mermaid(graph)

        assert result_with_data.mermaid_code == result_without_data

    def test_empty_stuff_data_when_no_data_field(self) -> None:
        """Test that stuff_data is empty when IOSpec has no data field populated."""
        producer_node = {
            "node_id": "node_1",
            "kind": NodeKind.OPERATOR,
            "pipe_code": "producer",
            "status": NodeStatus.SUCCEEDED,
            "node_io": NodeIOSpec(
                inputs=[],
                outputs=[IOSpec(name="output", concept="Text", digest="stuff_001", data=None)],
            ),
        }
        graph = self._make_graph(nodes=[producer_node])
        result = graphspec_to_combo_mermaid_with_data(graph)

        # stuff_data should be empty since data=None
        assert len(result.stuff_data) == 0

    def test_dict_data_preserved(self) -> None:
        """Test that dict data in IOSpec is preserved in stuff_data."""
        dict_data = {"key1": "value1", "key2": 123, "nested": {"inner": "value"}}
        producer_node = {
            "node_id": "node_1",
            "kind": NodeKind.OPERATOR,
            "pipe_code": "producer",
            "status": NodeStatus.SUCCEEDED,
            "node_io": NodeIOSpec(
                inputs=[],
                outputs=[IOSpec(name="output", concept="Text", digest="stuff_001", data=dict_data)],
            ),
        }
        graph = self._make_graph(nodes=[producer_node])
        result = graphspec_to_combo_mermaid_with_data(graph)

        # Dict data should be preserved
        assert len(result.stuff_data) > 0
        data_values = list(result.stuff_data.values())
        assert dict_data in data_values
