"""Unit tests for NodeSpec pipe metadata fields (description, domain_code)."""

from pipelex.graph.graphspec import NodeKind, NodeSpec, NodeStatus


class TestNodeSpecPipeMetadata:
    def test_node_spec_accepts_description_and_domain_code(self) -> None:
        node = NodeSpec(
            node_id="node_001",
            kind=NodeKind.OPERATOR,
            pipe_code="generate_text",
            pipe_type="PipeLLM",
            status=NodeStatus.SUCCEEDED,
            description="Generate a paragraph of text from a topic.",
            domain_code="text_generation",
        )

        assert node.description == "Generate a paragraph of text from a topic."
        assert node.domain_code == "text_generation"

    def test_node_spec_defaults_description_and_domain_code_to_none(self) -> None:
        node = NodeSpec(
            node_id="node_002",
            kind=NodeKind.INPUT,
            pipe_code=None,
            pipe_type=None,
            status=NodeStatus.SUCCEEDED,
        )

        assert node.description is None
        assert node.domain_code is None

    def test_node_spec_round_trip_preserves_pipe_metadata(self) -> None:
        original = NodeSpec(
            node_id="node_003",
            kind=NodeKind.CONTROLLER,
            pipe_code="main_sequence",
            pipe_type="PipeSequence",
            status=NodeStatus.SUCCEEDED,
            description="Top-level orchestration pipe.",
            domain_code="orchestration",
        )

        round_tripped = NodeSpec(**original.model_dump(by_alias=True))

        assert round_tripped.description == original.description
        assert round_tripped.domain_code == original.domain_code
