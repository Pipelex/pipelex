"""Unit tests for GraphTracer wiring of node-level pipe metadata."""

from datetime import datetime, timedelta, timezone

from pipelex.graph.graph_tracer import GraphTracer
from pipelex.graph.graphspec import NodeKind
from tests.unit.pipelex.graph.conftest import make_defaulted_data_inclusion_config


class TestGraphTracerNodeMetadata:
    def test_on_pipe_start_persists_description_and_domain_code(self) -> None:
        tracer = GraphTracer()
        context = tracer.setup(graph_id="meta-test", data_inclusion=make_defaulted_data_inclusion_config())

        started_at = datetime.now(timezone.utc)
        node_id, _child = tracer.on_pipe_start(
            graph_context=context,
            pipe_code="summarize",
            pipe_type="PipeLLM",
            node_kind=NodeKind.OPERATOR,
            started_at=started_at,
            description="Summarize the input document.",
            domain_code="summarization",
        )

        tracer.on_pipe_end_success(
            node_id=node_id,
            ended_at=started_at + timedelta(milliseconds=10),
        )

        graph_spec = tracer.teardown()

        assert graph_spec is not None
        assert len(graph_spec.nodes) == 1
        node = graph_spec.nodes[0]
        assert node.description == "Summarize the input document."
        assert node.domain_code == "summarization"

    def test_on_pipe_start_defaults_metadata_to_none(self) -> None:
        tracer = GraphTracer()
        context = tracer.setup(graph_id="meta-default-test", data_inclusion=make_defaulted_data_inclusion_config())

        started_at = datetime.now(timezone.utc)
        node_id, _child = tracer.on_pipe_start(
            graph_context=context,
            pipe_code="noop",
            pipe_type="PipeLLM",
            node_kind=NodeKind.OPERATOR,
            started_at=started_at,
        )

        tracer.on_pipe_end_success(
            node_id=node_id,
            ended_at=started_at + timedelta(milliseconds=10),
        )

        graph_spec = tracer.teardown()

        assert graph_spec is not None
        assert len(graph_spec.nodes) == 1
        node = graph_spec.nodes[0]
        assert node.description is None
        assert node.domain_code is None
