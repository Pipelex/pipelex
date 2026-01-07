from datetime import datetime, timezone
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
from pipelex.graph.mermaidflow.mermaidflow_factory import (
    Mermaidflow,
    MermaidflowFactory,
)

from .conftest import make_graph_config


class TestMermaidflowWithData:
    """Tests for MermaidflowFactory.make_from_graphspec with data inclusion enabled."""

    GRAPH_ID: ClassVar[str] = "mermaidflow_data_test:001"
    CREATED_AT: ClassVar[datetime] = datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc)

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

    def test_returns_mermaid_and_stuff(self) -> None:
        """Test that function returns MermaidAndStuff instance with stuff_data when configured."""
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
        graph_config = make_graph_config(include_stuff_json=True)
        result = MermaidflowFactory.make_from_graphspec(graph, graph_config)

        assert isinstance(result, Mermaidflow)
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
        graph_config = make_graph_config(include_stuff_json=True)
        result = MermaidflowFactory.make_from_graphspec(graph, graph_config)

        # Should have stuff_data with the data content
        assert result.stuff_data is not None
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
        graph_config = make_graph_config(include_stuff_json=True)
        result = MermaidflowFactory.make_from_graphspec(graph, graph_config)

        # Keys should start with s_ prefix
        assert result.stuff_data is not None
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
        graph_config = make_graph_config(include_stuff_json=True)
        result = MermaidflowFactory.make_from_graphspec(graph, graph_config)

        # Should have stuff_data for the input
        assert result.stuff_data is not None
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
        graph_config = make_graph_config(include_stuff_json=True)
        result = MermaidflowFactory.make_from_graphspec(graph, graph_config)

        # Should only have one entry for this digest
        assert result.stuff_data is not None
        data_values = list(result.stuff_data.values())
        assert data_values.count("the data") == 1

    def test_mermaid_code_same_regardless_of_data_config(self) -> None:
        """Test that mermaid_code is the same regardless of data inclusion config."""
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

        result_with_data = MermaidflowFactory.make_from_graphspec(graph, make_graph_config(include_stuff_json=True))
        result_without_data = MermaidflowFactory.make_from_graphspec(graph, make_graph_config(include_stuff_json=False))

        assert result_with_data.mermaid_code == result_without_data.mermaid_code

    def test_stuff_data_none_when_not_configured(self) -> None:
        """Test that stuff_data is None when data inclusion is disabled."""
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
        graph_config = make_graph_config(include_stuff_json=False)
        result = MermaidflowFactory.make_from_graphspec(graph, graph_config)

        # stuff_data should be None when not configured
        assert result.stuff_data is None

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
        graph_config = make_graph_config(include_stuff_json=True)
        result = MermaidflowFactory.make_from_graphspec(graph, graph_config)

        # stuff_data should be empty since data=None
        assert result.stuff_data is not None
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
        graph_config = make_graph_config(include_stuff_json=True)
        result = MermaidflowFactory.make_from_graphspec(graph, graph_config)

        # Dict data should be preserved
        assert result.stuff_data is not None
        assert len(result.stuff_data) > 0
        data_values = list(result.stuff_data.values())
        assert dict_data in data_values

    def test_stuff_data_text_populated_from_outputs(self) -> None:
        """Test that stuff_data_text is populated from IOSpec.data_text field."""
        text_content = "This is pre-rendered ASCII text content"
        producer_node = {
            "node_id": "node_1",
            "kind": NodeKind.OPERATOR,
            "pipe_code": "producer",
            "status": NodeStatus.SUCCEEDED,
            "node_io": NodeIOSpec(
                inputs=[],
                outputs=[IOSpec(name="output", concept="Text", digest="stuff_001", data_text=text_content)],
            ),
        }
        graph = self._make_graph(nodes=[producer_node])
        graph_config = make_graph_config(include_stuff_text=True)
        result = MermaidflowFactory.make_from_graphspec(graph, graph_config)

        # Should have stuff_data_text with the pre-rendered text
        assert result.stuff_data_text is not None
        assert len(result.stuff_data_text) > 0
        text_values = list(result.stuff_data_text.values())
        assert text_content in text_values

    def test_stuff_data_html_populated_from_outputs(self) -> None:
        """Test that stuff_data_html is populated from IOSpec.data_html field."""
        html_content = "<pre>This is pre-rendered HTML content</pre>"
        producer_node = {
            "node_id": "node_1",
            "kind": NodeKind.OPERATOR,
            "pipe_code": "producer",
            "status": NodeStatus.SUCCEEDED,
            "node_io": NodeIOSpec(
                inputs=[],
                outputs=[IOSpec(name="output", concept="Text", digest="stuff_001", data_html=html_content)],
            ),
        }
        graph = self._make_graph(nodes=[producer_node])
        graph_config = make_graph_config(include_stuff_html=True)
        result = MermaidflowFactory.make_from_graphspec(graph, graph_config)

        # Should have stuff_data_html with the pre-rendered HTML
        assert result.stuff_data_html is not None
        assert len(result.stuff_data_html) > 0
        html_values = list(result.stuff_data_html.values())
        assert html_content in html_values

    def test_stuff_data_text_empty_when_field_missing(self) -> None:
        """Test that stuff_data_text is empty when IOSpec has only data field (no data_text)."""
        producer_node = {
            "node_id": "node_1",
            "kind": NodeKind.OPERATOR,
            "pipe_code": "producer",
            "status": NodeStatus.SUCCEEDED,
            "node_io": NodeIOSpec(
                inputs=[],
                outputs=[IOSpec(name="output", concept="Text", digest="stuff_001", data="json data only")],
            ),
        }
        graph = self._make_graph(nodes=[producer_node])
        graph_config = make_graph_config(include_stuff_text=True)
        result = MermaidflowFactory.make_from_graphspec(graph, graph_config)

        # stuff_data_text should be empty since data_text=None
        assert result.stuff_data_text is not None
        assert len(result.stuff_data_text) == 0

    def test_stuff_data_html_empty_when_field_missing(self) -> None:
        """Test that stuff_data_html is empty when IOSpec has only data field (no data_html)."""
        producer_node = {
            "node_id": "node_1",
            "kind": NodeKind.OPERATOR,
            "pipe_code": "producer",
            "status": NodeStatus.SUCCEEDED,
            "node_io": NodeIOSpec(
                inputs=[],
                outputs=[IOSpec(name="output", concept="Text", digest="stuff_001", data="json data only")],
            ),
        }
        graph = self._make_graph(nodes=[producer_node])
        graph_config = make_graph_config(include_stuff_html=True)
        result = MermaidflowFactory.make_from_graphspec(graph, graph_config)

        # stuff_data_html should be empty since data_html=None
        assert result.stuff_data_html is not None
        assert len(result.stuff_data_html) == 0
