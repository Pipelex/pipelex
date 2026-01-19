"""Unit tests for GraphSpec validation."""

import pytest
from pydantic import ValidationError

from pipelex.graph.exceptions import GraphSpecValidationError
from pipelex.graph.graphspec import (
    EdgeKind,
    EdgeSpec,
    ErrorSpec,
    GraphSpec,
    NodeKind,
    NodeSpec,
    NodeStatus,
    PipelineRef,
)
from pipelex.graph.validation import validate_graphspec
from tests.unit.pipelex.graph.test_data import ValidGraphData


class TestGraphSpecValidation:
    """Tests for GraphSpec validation rules."""

    def test_reject_edge_with_missing_source_node(self) -> None:
        """Test that edges referencing non-existent source nodes are rejected."""
        node = NodeSpec(
            node_id="node_001",
            kind=NodeKind.OPERATOR,
            pipe_code="test_pipe",
            pipe_type="PipeLLM",
            status=NodeStatus.SUCCEEDED,
        )

        edge = EdgeSpec(
            edge_id="edge_001",
            source="non_existent_source",  # This node doesn't exist
            target="node_001",
            kind=EdgeKind.CONTROL,
        )

        graph = GraphSpec(
            graph_id="test_graph",
            created_at=ValidGraphData.CREATED_AT,
            pipeline_ref=PipelineRef(),
            nodes=[node],
            edges=[edge],
        )

        with pytest.raises(GraphSpecValidationError) as exc_info:
            validate_graphspec(graph)

        assert "non_existent_source" in str(exc_info.value)
        assert "source" in str(exc_info.value).lower()

    def test_reject_edge_with_missing_target_node(self) -> None:
        """Test that edges referencing non-existent target nodes are rejected."""
        node = NodeSpec(
            node_id="node_001",
            kind=NodeKind.OPERATOR,
            pipe_code="test_pipe",
            pipe_type="PipeLLM",
            status=NodeStatus.SUCCEEDED,
        )

        edge = EdgeSpec(
            edge_id="edge_001",
            source="node_001",
            target="non_existent_target",  # This node doesn't exist
            kind=EdgeKind.CONTROL,
        )

        graph = GraphSpec(
            graph_id="test_graph",
            created_at=ValidGraphData.CREATED_AT,
            pipeline_ref=PipelineRef(),
            nodes=[node],
            edges=[edge],
        )

        with pytest.raises(GraphSpecValidationError) as exc_info:
            validate_graphspec(graph)

        assert "non_existent_target" in str(exc_info.value)
        assert "target" in str(exc_info.value).lower()

    def test_reject_duplicate_node_ids(self) -> None:
        """Test that duplicate node IDs are rejected."""
        node1 = NodeSpec(
            node_id="duplicate_id",
            kind=NodeKind.OPERATOR,
            pipe_code="pipe_a",
            pipe_type="PipeLLM",
            status=NodeStatus.SUCCEEDED,
        )

        node2 = NodeSpec(
            node_id="duplicate_id",  # Same ID as node1
            kind=NodeKind.OPERATOR,
            pipe_code="pipe_b",
            pipe_type="PipeCompose",
            status=NodeStatus.SUCCEEDED,
        )

        graph = GraphSpec(
            graph_id="test_graph",
            created_at=ValidGraphData.CREATED_AT,
            pipeline_ref=PipelineRef(),
            nodes=[node1, node2],
            edges=[],
        )

        with pytest.raises(GraphSpecValidationError) as exc_info:
            validate_graphspec(graph)

        assert "duplicate_id" in str(exc_info.value)
        assert "duplicate" in str(exc_info.value).lower()

    def test_reject_duplicate_edge_ids(self) -> None:
        """Test that duplicate edge IDs are rejected."""
        nodes = [
            NodeSpec(
                node_id="node_a",
                kind=NodeKind.OPERATOR,
                pipe_code="pipe_a",
                pipe_type="PipeLLM",
                status=NodeStatus.SUCCEEDED,
            ),
            NodeSpec(
                node_id="node_b",
                kind=NodeKind.OPERATOR,
                pipe_code="pipe_b",
                pipe_type="PipeLLM",
                status=NodeStatus.SUCCEEDED,
            ),
            NodeSpec(
                node_id="node_c",
                kind=NodeKind.OPERATOR,
                pipe_code="pipe_c",
                pipe_type="PipeLLM",
                status=NodeStatus.SUCCEEDED,
            ),
        ]

        edge1 = EdgeSpec(
            edge_id="duplicate_edge_id",
            source="node_a",
            target="node_b",
            kind=EdgeKind.CONTROL,
        )

        edge2 = EdgeSpec(
            edge_id="duplicate_edge_id",  # Same ID as edge1
            source="node_b",
            target="node_c",
            kind=EdgeKind.CONTROL,
        )

        graph = GraphSpec(
            graph_id="test_graph",
            created_at=ValidGraphData.CREATED_AT,
            pipeline_ref=PipelineRef(),
            nodes=nodes,
            edges=[edge1, edge2],
        )

        with pytest.raises(GraphSpecValidationError) as exc_info:
            validate_graphspec(graph)

        assert "duplicate_edge_id" in str(exc_info.value)
        assert "duplicate" in str(exc_info.value).lower()

    def test_reject_invalid_status_enum(self) -> None:
        """Test that invalid status values are rejected by Pydantic."""
        with pytest.raises(ValidationError):
            NodeSpec(
                node_id="node_001",
                kind=NodeKind.OPERATOR,
                pipe_code="test_pipe",
                pipe_type="PipeLLM",
                status="invalid_status",  # type: ignore[arg-type]
            )

    def test_reject_invalid_node_kind_enum(self) -> None:
        """Test that invalid node kind values are rejected by Pydantic."""
        with pytest.raises(ValidationError):
            NodeSpec(
                node_id="node_001",
                kind="invalid_kind",  # type: ignore[arg-type]
                pipe_code="test_pipe",
                pipe_type="PipeLLM",
                status=NodeStatus.SUCCEEDED,
            )

    def test_reject_invalid_edge_kind_enum(self) -> None:
        """Test that invalid edge kind values are rejected by Pydantic."""
        with pytest.raises(ValidationError):
            EdgeSpec(
                edge_id="edge_001",
                source="node_a",
                target="node_b",
                kind="invalid_kind",  # type: ignore[arg-type]
            )

    def test_reject_failed_status_without_error(self) -> None:
        """Test that nodes with status=failed but no error are rejected."""
        node = NodeSpec(
            node_id="failed_node",
            kind=NodeKind.OPERATOR,
            pipe_code="failed_pipe",
            pipe_type="PipeLLM",
            status=NodeStatus.FAILED,
            error=None,  # Missing error for failed status
        )

        graph = GraphSpec(
            graph_id="test_graph",
            created_at=ValidGraphData.CREATED_AT,
            pipeline_ref=PipelineRef(),
            nodes=[node],
            edges=[],
        )

        with pytest.raises(GraphSpecValidationError) as exc_info:
            validate_graphspec(graph)

        assert "failed" in str(exc_info.value).lower()
        assert "error" in str(exc_info.value).lower()

    def test_accept_failed_status_with_error(self) -> None:
        """Test that nodes with status=failed and proper error are accepted."""
        error = ErrorSpec(
            error_type="PipeRunError",
            message="Pipe execution failed",
        )

        node = NodeSpec(
            node_id="failed_node",
            kind=NodeKind.OPERATOR,
            pipe_code="failed_pipe",
            pipe_type="PipeLLM",
            status=NodeStatus.FAILED,
            error=error,
        )

        graph = GraphSpec(
            graph_id="test_graph",
            created_at=ValidGraphData.CREATED_AT,
            pipeline_ref=PipelineRef(),
            nodes=[node],
            edges=[],
        )

        # Should not raise
        validate_graphspec(graph)

    def test_valid_graph_passes_validation(self) -> None:
        """Test that a valid graph passes all validation checks."""
        nodes = [
            NodeSpec(
                node_id="node_001",
                kind=NodeKind.CONTROLLER,
                pipe_code="main_sequence",
                pipe_type="PipeSequence",
                status=NodeStatus.SUCCEEDED,
            ),
            NodeSpec(
                node_id="node_002",
                kind=NodeKind.OPERATOR,
                pipe_code="generate_text",
                pipe_type="PipeLLM",
                status=NodeStatus.SUCCEEDED,
            ),
        ]

        edges = [
            EdgeSpec(
                edge_id="edge_001",
                source="node_001",
                target="node_002",
                kind=EdgeKind.CONTAINS,
            )
        ]

        graph = GraphSpec(
            graph_id="valid_graph",
            created_at=ValidGraphData.CREATED_AT,
            pipeline_ref=PipelineRef(
                domain="test_domain",
                main_pipe="test_pipe",
            ),
            nodes=nodes,
            edges=edges,
        )

        # Should not raise
        validate_graphspec(graph)

    def test_empty_graph_passes_validation(self) -> None:
        """Test that an empty graph (no nodes, no edges) passes validation."""
        graph = GraphSpec(
            graph_id="empty_graph",
            created_at=ValidGraphData.CREATED_AT,
            pipeline_ref=PipelineRef(),
            nodes=[],
            edges=[],
        )

        # Should not raise
        validate_graphspec(graph)

    def test_reject_extra_fields_on_load(self) -> None:
        """Test that extra/unknown fields in JSON are rejected."""
        graph = GraphSpec(
            graph_id="test_graph",
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
        # Add an unknown field
        bad_json = json_str.replace(
            '"graph_id"',
            '"unknown_field": "bad_value", "graph_id"',
        )

        with pytest.raises((ValidationError, GraphSpecValidationError)):
            GraphSpec.model_validate_json(bad_json)
