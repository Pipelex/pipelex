"""Test data for GraphSpec unit tests."""

from datetime import UTC, datetime
from typing import Any, ClassVar


class ValidGraphData:
    """Valid graph test data using ClassVar pattern per repo standards."""

    SCHEMA_VERSION: ClassVar[str] = "1.0"
    GRAPH_ID: ClassVar[str] = "run_abc123"
    CREATED_AT: ClassVar[datetime] = datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC)

    PIPELINE_REF: ClassVar[dict[str, str | None]] = {
        "domain": "test_domain",
        "main_pipe": "test_main_pipe",
        "entrypoint": "test_entrypoint",
    }

    MINIMAL_NODE: ClassVar[dict[str, Any]] = {
        "id": "node_001",
        "kind": "operator",
        "pipe_name": "generate_text",
        "pipe_type": "PipeLLM",
        "status": "succeeded",
        "timing": None,
        "node_io": {"inputs": [], "outputs": []},
        "error": None,
        "tags": {},
        "metrics": {},
    }

    MINIMAL_GRAPH: ClassVar[dict[str, Any]] = {
        "schema_version": SCHEMA_VERSION,
        "graph_id": GRAPH_ID,
        "created_at": CREATED_AT,
        "pipeline_ref": PIPELINE_REF,
        "nodes": [MINIMAL_NODE],
        "edges": [],
        "meta": {},
    }

    TIMING_SPEC: ClassVar[dict[str, Any]] = {
        "started_at": datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC),
        "ended_at": datetime(2024, 1, 15, 10, 30, 5, tzinfo=UTC),
        "duration_ms": 5000,
    }

    IO_SPEC_INPUT: ClassVar[dict[str, Any]] = {
        "name": "topic",
        "concept": "Text",
        "content_type": "TextContent",
        "preview": "Hello world",
        "size": 11,
        "digest": "abc123hash",
        "extra": {},
    }

    IO_SPEC_OUTPUT: ClassVar[dict[str, Any]] = {
        "name": "generated_text",
        "concept": "Text",
        "content_type": "TextContent",
        "preview": "Generated output text...",
        "size": 500,
        "digest": "def456hash",
        "extra": {},
    }

    COMPLEX_NODE_1: ClassVar[dict[str, Any]] = {
        "id": "run_abc123:span_001",
        "kind": "controller",
        "pipe_name": "main_sequence",
        "pipe_type": "PipeSequence",
        "status": "succeeded",
        "timing": TIMING_SPEC,
        "node_io": {
            "inputs": [IO_SPEC_INPUT],
            "outputs": [IO_SPEC_OUTPUT],
        },
        "error": None,
        "tags": {"layer": "root"},
        "metrics": {"llm_tokens": 150.0},
    }

    COMPLEX_NODE_2: ClassVar[dict[str, Any]] = {
        "id": "run_abc123:span_002",
        "kind": "operator",
        "pipe_name": "generate_text",
        "pipe_type": "PipeLLM",
        "status": "succeeded",
        "timing": {
            "started_at": datetime(2024, 1, 15, 10, 30, 1, tzinfo=UTC),
            "ended_at": datetime(2024, 1, 15, 10, 30, 4, tzinfo=UTC),
            "duration_ms": 3000,
        },
        "node_io": {
            "inputs": [IO_SPEC_INPUT],
            "outputs": [IO_SPEC_OUTPUT],
        },
        "error": None,
        "tags": {"layer": "child"},
        "metrics": {"llm_tokens": 150.0},
    }

    CONTROL_EDGE: ClassVar[dict[str, Any]] = {
        "id": "edge_001",
        "source": "run_abc123:span_001",
        "target": "run_abc123:span_002",
        "kind": "contains",
        "label": "step 1",
        "meta": {},
    }

    COMPLEX_GRAPH: ClassVar[dict[str, Any]] = {
        "schema_version": SCHEMA_VERSION,
        "graph_id": "run_abc123",
        "created_at": CREATED_AT,
        "pipeline_ref": PIPELINE_REF,
        "nodes": [COMPLEX_NODE_1, COMPLEX_NODE_2],
        "edges": [CONTROL_EDGE],
        "meta": {"run_mode": "live"},
    }


class InvalidGraphData:
    """Invalid graph test data for validation tests."""

    # Edge referencing non-existent source node
    EDGE_MISSING_SOURCE: ClassVar[dict[str, Any]] = {
        "id": "edge_bad_001",
        "source": "non_existent_node",
        "target": "node_001",
        "kind": "control",
        "label": None,
        "meta": {},
    }

    # Edge referencing non-existent target node
    EDGE_MISSING_TARGET: ClassVar[dict[str, Any]] = {
        "id": "edge_bad_002",
        "source": "node_001",
        "target": "non_existent_node",
        "kind": "control",
        "label": None,
        "meta": {},
    }

    # Node with failed status but no error
    NODE_FAILED_NO_ERROR: ClassVar[dict[str, Any]] = {
        "id": "node_failed_001",
        "kind": "operator",
        "pipe_name": "failed_pipe",
        "pipe_type": "PipeLLM",
        "status": "failed",
        "timing": None,
        "node_io": {"inputs": [], "outputs": []},
        "error": None,  # Should have error when failed
        "tags": {},
        "metrics": {},
    }

    # Error spec for testing failed nodes
    ERROR_SPEC: ClassVar[dict[str, Any]] = {
        "error_type": "PipeRunError",
        "message": "LLM generation failed",
        "stack": "Traceback (most recent call last):\n  File ...\nPipeRunError: LLM generation failed",
    }

    # Valid failed node (with error)
    NODE_FAILED_WITH_ERROR: ClassVar[dict[str, Any]] = {
        "id": "node_failed_002",
        "kind": "operator",
        "pipe_name": "failed_pipe",
        "pipe_type": "PipeLLM",
        "status": "failed",
        "timing": None,
        "node_io": {"inputs": [], "outputs": []},
        "error": ERROR_SPEC,
        "tags": {},
        "metrics": {},
    }

    # Unsupported schema version
    UNSUPPORTED_VERSION_GRAPH: ClassVar[dict[str, Any]] = {
        "schema_version": "99.0",
        "graph_id": "run_bad",
        "created_at": datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC),
        "pipeline_ref": {"domain": None, "main_pipe": None, "entrypoint": None},
        "nodes": [],
        "edges": [],
        "meta": {},
    }

    # Duplicate node IDs
    DUPLICATE_NODE_ID_1: ClassVar[dict[str, Any]] = {
        "id": "duplicate_id",
        "kind": "operator",
        "pipe_name": "pipe_a",
        "pipe_type": "PipeLLM",
        "status": "succeeded",
        "timing": None,
        "node_io": {"inputs": [], "outputs": []},
        "error": None,
        "tags": {},
        "metrics": {},
    }

    DUPLICATE_NODE_ID_2: ClassVar[dict[str, Any]] = {
        "id": "duplicate_id",
        "kind": "operator",
        "pipe_name": "pipe_b",
        "pipe_type": "PipeCompose",
        "status": "succeeded",
        "timing": None,
        "node_io": {"inputs": [], "outputs": []},
        "error": None,
        "tags": {},
        "metrics": {},
    }

    # Duplicate edge IDs
    DUPLICATE_EDGE_1: ClassVar[dict[str, Any]] = {
        "id": "duplicate_edge_id",
        "source": "node_a",
        "target": "node_b",
        "kind": "control",
        "label": None,
        "meta": {},
    }

    DUPLICATE_EDGE_2: ClassVar[dict[str, Any]] = {
        "id": "duplicate_edge_id",
        "source": "node_b",
        "target": "node_c",
        "kind": "control",
        "label": None,
        "meta": {},
    }


class PreviewTruncationData:
    """Test data for preview truncation tests."""

    MAX_PREVIEW_LENGTH: ClassVar[int] = 200
    MAX_STACK_LENGTH: ClassVar[int] = 2000

    LONG_PREVIEW_TEXT: ClassVar[str] = "A" * 500
    EXPECTED_TRUNCATED_PREVIEW: ClassVar[str] = "A" * 197 + "..."

    LONG_STACK_TEXT: ClassVar[str] = "S" * 5000
    EXPECTED_TRUNCATED_STACK: ClassVar[str] = "S" * 1997 + "..."
