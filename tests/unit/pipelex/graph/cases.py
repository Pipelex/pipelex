"""Test data for GraphSpec unit tests."""

from datetime import UTC, datetime
from typing import Any, ClassVar

from pipelex.graph.graphspec import EdgeKind, NodeKind, NodeStatus


class ValidGraphData:
    """Valid graph test data using ClassVar pattern per repo standards."""

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
        "pipe_code": "generate_text",
        "pipe_type": "PipeLLM",
        "status": "succeeded",
        "timing": None,
        "node_io": {"inputs": [], "outputs": []},
        "error": None,
        "tags": {},
        "metrics": {},
    }

    MINIMAL_GRAPH: ClassVar[dict[str, Any]] = {
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
        "pipe_code": "main_sequence",
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
        "pipe_code": "generate_text",
        "pipe_type": "PipeLLM",
        "status": "succeeded",
        "timing": {
            "started_at": datetime(2024, 1, 15, 10, 30, 1, tzinfo=UTC),
            "ended_at": datetime(2024, 1, 15, 10, 30, 4, tzinfo=UTC),
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
        "pipe_code": "failed_pipe",
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
        "pipe_code": "failed_pipe",
        "pipe_type": "PipeLLM",
        "status": "failed",
        "timing": None,
        "node_io": {"inputs": [], "outputs": []},
        "error": ERROR_SPEC,
        "tags": {},
        "metrics": {},
    }

    # Duplicate node IDs
    DUPLICATE_NODE_ID_1: ClassVar[dict[str, Any]] = {
        "id": "duplicate_id",
        "kind": "operator",
        "pipe_code": "pipe_a",
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
        "pipe_code": "pipe_b",
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


class MermaidTestData:
    """Test data for Mermaid exporter tests."""

    GRAPH_ID: ClassVar[str] = "test_run:123"
    CREATED_AT: ClassVar[datetime] = datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC)

    # Node with special characters in ID
    CONTROLLER_NODE: ClassVar[dict[str, Any]] = {
        "node_id": "run:123:step-1",
        "kind": NodeKind.CONTROLLER,
        "pipe_code": "main_sequence",
        "pipe_type": "PipeSequence",
        "status": NodeStatus.SUCCEEDED,
    }

    OPERATOR_NODE_1: ClassVar[dict[str, Any]] = {
        "node_id": "run:123:step-2",
        "kind": NodeKind.OPERATOR,
        "pipe_code": "generate_text",
        "pipe_type": "PipeLLM",
        "status": NodeStatus.SUCCEEDED,
    }

    OPERATOR_NODE_2: ClassVar[dict[str, Any]] = {
        "node_id": "run:123:step-3",
        "kind": NodeKind.OPERATOR,
        "pipe_code": "compose_output",
        "pipe_type": "PipeCompose",
        "status": NodeStatus.SUCCEEDED,
    }

    FAILED_NODE: ClassVar[dict[str, Any]] = {
        "node_id": "run:123:step-4",
        "kind": NodeKind.OPERATOR,
        "pipe_code": "failed_pipe",
        "pipe_type": "PipeLLM",
        "status": NodeStatus.FAILED,
    }

    INPUT_NODE: ClassVar[dict[str, Any]] = {
        "node_id": "run:123:input-1",
        "kind": NodeKind.INPUT,
        "pipe_code": "topic_input",
        "pipe_type": None,
        "status": NodeStatus.SUCCEEDED,
    }

    # Edges
    CONTAINS_EDGE_1: ClassVar[dict[str, Any]] = {
        "edge_id": "edge_contains_1",
        "source": "run:123:step-1",
        "target": "run:123:step-2",
        "kind": EdgeKind.CONTAINS,
        "label": None,
    }

    CONTAINS_EDGE_2: ClassVar[dict[str, Any]] = {
        "edge_id": "edge_contains_2",
        "source": "run:123:step-1",
        "target": "run:123:step-3",
        "kind": EdgeKind.CONTAINS,
        "label": None,
    }

    DATA_EDGE: ClassVar[dict[str, Any]] = {
        "edge_id": "edge_data_1",
        "source": "run:123:step-2",
        "target": "run:123:step-3",
        "kind": EdgeKind.DATA,
        "label": "generated_text",
    }

    CONTROL_EDGE: ClassVar[dict[str, Any]] = {
        "edge_id": "edge_control_1",
        "source": "run:123:step-2",
        "target": "run:123:step-3",
        "kind": EdgeKind.CONTROL,
        "label": None,
    }

    SELECTED_OUTCOME_EDGE: ClassVar[dict[str, Any]] = {
        "edge_id": "edge_outcome_1",
        "source": "run:123:step-1",
        "target": "run:123:step-4",
        "kind": EdgeKind.SELECTED_OUTCOME,
        "label": "success_branch",
    }

    # Nodes with IOSpec containing data for _with_data tests
    PRODUCER_NODE_WITH_DATA: ClassVar[dict[str, Any]] = {
        "node_id": "run:123:producer",
        "kind": NodeKind.OPERATOR,
        "pipe_code": "data_producer",
        "pipe_type": "PipeLLM",
        "status": NodeStatus.SUCCEEDED,
        "node_io": {
            "inputs": [],
            "outputs": [
                {
                    "name": "generated_output",
                    "concept": "Text",
                    "digest": "digest_abc123",
                    "data": "This is the full output content from the LLM",
                }
            ],
        },
    }

    CONSUMER_NODE_WITH_DATA: ClassVar[dict[str, Any]] = {
        "node_id": "run:123:consumer",
        "kind": NodeKind.OPERATOR,
        "pipe_code": "data_consumer",
        "pipe_type": "PipeCompose",
        "status": NodeStatus.SUCCEEDED,
        "node_io": {
            "inputs": [
                {
                    "name": "input_text",
                    "concept": "Text",
                    "digest": "digest_abc123",
                    "data": "This is the full output content from the LLM",
                }
            ],
            "outputs": [
                {
                    "name": "composed_output",
                    "concept": "Text",
                    "digest": "digest_xyz789",
                    "data": {"title": "Composed Result", "content": "Rich structured data"},
                }
            ],
        },
    }

    PIPELINE_INPUT_NODE_WITH_DATA: ClassVar[dict[str, Any]] = {
        "node_id": "run:123:pipeline-input",
        "kind": NodeKind.OPERATOR,
        "pipe_code": "first_step",
        "pipe_type": "PipeLLM",
        "status": NodeStatus.SUCCEEDED,
        "node_io": {
            "inputs": [
                {
                    "name": "user_prompt",
                    "concept": "Text",
                    "digest": "digest_input_001",
                    "data": "User's original input prompt",
                }
            ],
            "outputs": [],
        },
    }

    # Multi-consumer scenario: one stuff consumed by multiple pipes
    SHARED_STUFF_PRODUCER: ClassVar[dict[str, Any]] = {
        "node_id": "run:123:shared-producer",
        "kind": NodeKind.OPERATOR,
        "pipe_code": "shared_producer",
        "pipe_type": "PipeLLM",
        "status": NodeStatus.SUCCEEDED,
        "node_io": {
            "inputs": [],
            "outputs": [
                {
                    "name": "shared_data",
                    "concept": "Text",
                    "digest": "digest_shared",
                    "data": "Data that will be consumed by multiple pipes",
                }
            ],
        },
    }

    SHARED_STUFF_CONSUMER_A: ClassVar[dict[str, Any]] = {
        "node_id": "run:123:consumer-a",
        "kind": NodeKind.OPERATOR,
        "pipe_code": "consumer_a",
        "pipe_type": "PipeCompose",
        "status": NodeStatus.SUCCEEDED,
        "node_io": {
            "inputs": [
                {
                    "name": "shared_input",
                    "concept": "Text",
                    "digest": "digest_shared",
                    "data": "Data that will be consumed by multiple pipes",
                }
            ],
            "outputs": [],
        },
    }

    SHARED_STUFF_CONSUMER_B: ClassVar[dict[str, Any]] = {
        "node_id": "run:123:consumer-b",
        "kind": NodeKind.OPERATOR,
        "pipe_code": "consumer_b",
        "pipe_type": "PipeCompose",
        "status": NodeStatus.SUCCEEDED,
        "node_io": {
            "inputs": [
                {
                    "name": "shared_input",
                    "concept": "Text",
                    "digest": "digest_shared",
                    "data": "Data that will be consumed by multiple pipes",
                }
            ],
            "outputs": [],
        },
    }
