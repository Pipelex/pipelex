"""Unit tests for GraphSpec JSON round-trip serialization."""

from datetime import UTC, datetime
from pathlib import Path

from pipelex.graph.graphspec import (
    EdgeKind,
    EdgeSpec,
    ErrorSpec,
    GraphSpec,
    GraphSpecMode,
    IOSpec,
    NodeIOSpec,
    NodeKind,
    NodeSpec,
    NodeStatus,
    PipelineRef,
    TimingSpec,
)
from pipelex.tools.misc.file_utils import load_text_from_path, save_text_to_path
from tests.unit.pipelex.graph.test_data import (
    PreviewTruncationData,
    ValidGraphData,
)


class TestGraphSpecRoundtrip:
    """Tests for GraphSpec JSON round-trip serialization."""

    def test_roundtrip_minimal_graph(self) -> None:
        """Test round-trip for a minimal graph with single node and no edges."""
        graph = GraphSpec(
            graph_id=ValidGraphData.GRAPH_ID,
            created_at=ValidGraphData.CREATED_AT,
            pipeline_ref=PipelineRef(
                domain="test_domain",
                main_pipe="test_main_pipe",
                entrypoint="test_entrypoint",
            ),
            nodes=[
                NodeSpec(
                    node_id="node_001",
                    kind=NodeKind.OPERATOR,
                    pipe_code="generate_text",
                    pipe_type="PipeLLM",
                    status=NodeStatus.SUCCEEDED,
                )
            ],
            edges=[],
        )

        json_str = graph.to_json()
        restored = GraphSpec.model_validate_json(json_str)

        assert restored.graph_id == graph.graph_id
        assert restored.created_at == graph.created_at
        assert restored.pipeline_ref == graph.pipeline_ref
        assert len(restored.nodes) == 1
        assert restored.nodes[0].node_id == "node_001"
        assert restored.nodes[0].kind == NodeKind.OPERATOR
        assert restored.nodes[0].status == NodeStatus.SUCCEEDED
        assert len(restored.edges) == 0
        assert '"format": "mthds"' in json_str
        assert restored.meta["format"] == "mthds"

    def test_roundtrip_complex_graph(self) -> None:
        """Test round-trip for a complex graph with multiple nodes, edges, and timing."""
        timing1 = TimingSpec(
            started_at=datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC),
            ended_at=datetime(2024, 1, 15, 10, 30, 5, tzinfo=UTC),
        )
        timing2 = TimingSpec(
            started_at=datetime(2024, 1, 15, 10, 30, 1, tzinfo=UTC),
            ended_at=datetime(2024, 1, 15, 10, 30, 4, tzinfo=UTC),
        )

        input_io = IOSpec(
            name="topic",
            concept="Text",
            content_type="TextContent",
            preview="Hello world",
            size=11,
            digest="abc123hash",
        )
        output_io = IOSpec(
            name="generated_text",
            concept="Text",
            content_type="TextContent",
            preview="Generated output text...",
            size=500,
            digest="def456hash",
        )

        node1 = NodeSpec(
            node_id="run_abc123:span_001",
            kind=NodeKind.CONTROLLER,
            pipe_code="main_sequence",
            pipe_type="PipeSequence",
            status=NodeStatus.SUCCEEDED,
            timing=timing1,
            node_io=NodeIOSpec(inputs=[input_io], outputs=[output_io]),
            tags={"layer": "root"},
            metrics={"llm_tokens": 150.0},
        )
        node2 = NodeSpec(
            node_id="run_abc123:span_002",
            kind=NodeKind.OPERATOR,
            pipe_code="generate_text",
            pipe_type="PipeLLM",
            status=NodeStatus.SUCCEEDED,
            timing=timing2,
            node_io=NodeIOSpec(inputs=[input_io], outputs=[output_io]),
            tags={"layer": "child"},
            metrics={"llm_tokens": 150.0},
        )

        edge = EdgeSpec(
            edge_id="edge_001",
            source="run_abc123:span_001",
            target="run_abc123:span_002",
            kind=EdgeKind.CONTAINS,
            label="step 1",
        )

        graph = GraphSpec(
            graph_id="run_abc123",
            created_at=ValidGraphData.CREATED_AT,
            pipeline_ref=PipelineRef(
                domain="test_domain",
                main_pipe="test_main_pipe",
                entrypoint="test_entrypoint",
            ),
            nodes=[node1, node2],
            edges=[edge],
            meta={"mode": GraphSpecMode.LIVE, "extra": "value"},
        )

        json_str = graph.to_json()
        restored = GraphSpec.model_validate_json(json_str)

        # Verify structure
        assert restored.graph_id == graph.graph_id
        assert restored.created_at == graph.created_at
        assert len(restored.nodes) == 2
        assert len(restored.edges) == 1

        # Verify node 1
        assert restored.nodes[0].node_id == "run_abc123:span_001"
        assert restored.nodes[0].kind == NodeKind.CONTROLLER
        assert restored.nodes[0].timing is not None
        assert restored.nodes[0].timing.duration == 5.0
        assert restored.nodes[0].tags == {"layer": "root"}
        assert restored.nodes[0].metrics == {"llm_tokens": 150.0}

        # Verify node 2
        assert restored.nodes[1].node_id == "run_abc123:span_002"
        assert restored.nodes[1].kind == NodeKind.OPERATOR

        # Verify edge
        assert restored.edges[0].edge_id == "edge_001"
        assert restored.edges[0].source == "run_abc123:span_001"
        assert restored.edges[0].target == "run_abc123:span_002"
        assert restored.edges[0].kind == EdgeKind.CONTAINS
        assert restored.edges[0].label == "step 1"

        # Verify meta
        assert restored.meta == {"mode": GraphSpecMode.LIVE, "extra": "value", "format": "mthds"}

    def test_roundtrip_with_error_spec(self) -> None:
        """Test round-trip for a graph with a failed node containing error info."""
        error = ErrorSpec(
            error_type="PipeRunError",
            message="LLM generation failed",
            stack="Traceback (most recent call last):\n  File ...\nPipeRunError: LLM generation failed",
        )

        node = NodeSpec(
            node_id="failed_node_001",
            kind=NodeKind.OPERATOR,
            pipe_code="failed_pipe",
            pipe_type="PipeLLM",
            status=NodeStatus.FAILED,
            error=error,
        )

        graph = GraphSpec(
            graph_id="run_failed",
            created_at=ValidGraphData.CREATED_AT,
            pipeline_ref=PipelineRef(),
            nodes=[node],
            edges=[],
        )

        json_str = graph.to_json()
        restored = GraphSpec.model_validate_json(json_str)

        assert restored.nodes[0].status == NodeStatus.FAILED
        assert restored.nodes[0].error is not None
        assert restored.nodes[0].error.error_type == "PipeRunError"
        assert restored.nodes[0].error.message == "LLM generation failed"
        assert "Traceback" in (restored.nodes[0].error.stack or "")

    def test_roundtrip_file_save_load(self, tmp_path: Path) -> None:
        """Test save/load to file produces identical GraphSpec."""
        graph = GraphSpec(
            graph_id="file_test",
            created_at=ValidGraphData.CREATED_AT,
            pipeline_ref=PipelineRef(domain="test"),
            nodes=[
                NodeSpec(
                    node_id="node_file_001",
                    kind=NodeKind.OPERATOR,
                    pipe_code="test_pipe",
                    pipe_type="PipeLLM",
                    status=NodeStatus.SUCCEEDED,
                )
            ],
            edges=[],
        )

        file_path = tmp_path / "test_graph.json"
        save_text_to_path(graph.to_json(), path=file_path)
        json_str = load_text_from_path(file_path)
        restored = GraphSpec.model_validate_json(json_str)

        assert restored.graph_id == graph.graph_id
        assert restored.nodes[0].node_id == graph.nodes[0].node_id

    def test_loads_old_fixture_without_mode(self) -> None:
        """Old GraphSpec JSON without meta.mode remains readable."""
        fixture_path = Path(__file__).parents[3] / "data" / "graphs" / "cv_batch_old.json"

        restored = GraphSpec.model_validate_json(load_text_from_path(fixture_path))

        assert restored.meta["format"] == "mthds"
        assert "mode" not in restored.meta

    def test_json_is_human_readable(self) -> None:
        """Test that generated JSON is indented and human-readable."""
        graph = GraphSpec(
            graph_id="readable_test",
            created_at=ValidGraphData.CREATED_AT,
            pipeline_ref=PipelineRef(),
            nodes=[
                NodeSpec(
                    node_id="node_001",
                    kind=NodeKind.OPERATOR,
                    pipe_code="test",
                    pipe_type="PipeLLM",
                    status=NodeStatus.SUCCEEDED,
                )
            ],
            edges=[],
        )

        json_str = graph.to_json()

        # Check for indentation (newlines and spaces)
        assert "\n" in json_str
        assert "  " in json_str  # At least 2-space indent

    def test_preview_truncation_on_creation(self) -> None:
        """Test that long previews are truncated on IOSpec creation."""
        long_preview = PreviewTruncationData.LONG_PREVIEW_TEXT
        io_spec = IOSpec(
            name="long_content",
            concept="Text",
            preview=long_preview,
        )

        # Preview should be truncated to max length
        assert len(io_spec.preview or "") <= PreviewTruncationData.MAX_PREVIEW_LENGTH
        if io_spec.preview and len(long_preview) > PreviewTruncationData.MAX_PREVIEW_LENGTH:
            assert io_spec.preview.endswith("...")

    def test_stack_truncation_on_creation(self) -> None:
        """Test that long stack traces are truncated on ErrorSpec creation."""
        long_stack = PreviewTruncationData.LONG_STACK_TEXT
        error_spec = ErrorSpec(
            error_type="TestError",
            message="Test message",
            stack=long_stack,
        )

        # Stack should be truncated to max length
        assert len(error_spec.stack or "") <= PreviewTruncationData.MAX_STACK_LENGTH
        if error_spec.stack and len(long_stack) > PreviewTruncationData.MAX_STACK_LENGTH:
            assert error_spec.stack.endswith("...")

    def test_roundtrip_with_all_node_kinds(self) -> None:
        """Test round-trip preserves all NodeKind enum values."""
        nodes = [
            NodeSpec(
                node_id=f"node_{kind}",
                kind=kind,
                pipe_code=f"pipe_{kind}",
                pipe_type="TestType",
                status=NodeStatus.SUCCEEDED,
            )
            for kind in NodeKind
        ]

        graph = GraphSpec(
            graph_id="all_kinds",
            created_at=ValidGraphData.CREATED_AT,
            pipeline_ref=PipelineRef(),
            nodes=nodes,
            edges=[],
        )

        json_str = graph.to_json()
        restored = GraphSpec.model_validate_json(json_str)

        for idx, kind in enumerate(NodeKind):
            assert restored.nodes[idx].kind == kind

    def test_roundtrip_with_all_edge_kinds(self) -> None:
        """Test round-trip preserves all EdgeKind enum values."""
        # Create enough nodes for all edges
        nodes = [
            NodeSpec(
                node_id=f"node_{idx}",
                kind=NodeKind.OPERATOR,
                pipe_code=f"pipe_{idx}",
                pipe_type="TestType",
                status=NodeStatus.SUCCEEDED,
            )
            for idx in range(len(EdgeKind) + 1)
        ]

        edges = [
            EdgeSpec(
                edge_id=f"edge_{kind}",
                source=f"node_{idx}",
                target=f"node_{idx + 1}",
                kind=kind,
            )
            for idx, kind in enumerate(EdgeKind)
        ]

        graph = GraphSpec(
            graph_id="all_edge_kinds",
            created_at=ValidGraphData.CREATED_AT,
            pipeline_ref=PipelineRef(),
            nodes=nodes,
            edges=edges,
        )

        json_str = graph.to_json()
        restored = GraphSpec.model_validate_json(json_str)

        for idx, kind in enumerate(EdgeKind):
            assert restored.edges[idx].kind == kind

    def test_roundtrip_with_all_node_statuses(self) -> None:
        """Test round-trip preserves all NodeStatus enum values."""
        nodes: list[NodeSpec] = []
        for status in NodeStatus:
            node = NodeSpec(
                node_id=f"node_{status}",
                kind=NodeKind.OPERATOR,
                pipe_code=f"pipe_{status}",
                pipe_type="TestType",
                status=status,
            )
            # Add error for failed status to satisfy invariant
            if status == NodeStatus.FAILED:
                node = NodeSpec(
                    node_id=f"node_{status}",
                    kind=NodeKind.OPERATOR,
                    pipe_code=f"pipe_{status}",
                    pipe_type="TestType",
                    status=status,
                    error=ErrorSpec(error_type="TestError", message="Test"),
                )
            nodes.append(node)

        graph = GraphSpec(
            graph_id="all_statuses",
            created_at=ValidGraphData.CREATED_AT,
            pipeline_ref=PipelineRef(),
            nodes=nodes,
            edges=[],
        )

        json_str = graph.to_json()
        restored = GraphSpec.model_validate_json(json_str)

        status_list = list(NodeStatus)
        for idx, status in enumerate(status_list):
            assert restored.nodes[idx].status == status
