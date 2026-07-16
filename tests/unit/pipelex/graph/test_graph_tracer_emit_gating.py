from datetime import UTC, datetime

from pipelex.graph.graph_tracer import GraphTracer
from pipelex.graph.graphspec import NodeKind
from tests.unit.pipelex.graph.conftest import make_defaulted_data_inclusion_config


class TestGraphTracerEmitGating:
    """The emit flags threaded into setup are born onto the TraceContext and gate teardown (E1)."""

    def _start_a_node(self, tracer: GraphTracer, context: object) -> None:
        tracer.on_pipe_start(
            trace_context=context,  # type: ignore[arg-type]
            pipe_code="some_pipe",
            pipe_type="PipeLLM",
            node_kind=NodeKind.OPERATOR,
            started_at=datetime.now(UTC),
        )

    def test_setup_stamps_emit_flags_onto_context(self) -> None:
        tracer = GraphTracer()
        context = tracer.setup(
            graph_id="emit-flags",
            data_inclusion=make_defaulted_data_inclusion_config(),
            emit_graph_events=False,
            emit_usage_events=True,
        )
        assert context.emit_graph_events is False
        assert context.emit_usage_events is True

    def test_setup_defaults_emit_flags_true(self) -> None:
        tracer = GraphTracer()
        context = tracer.setup(graph_id="emit-defaults", data_inclusion=make_defaulted_data_inclusion_config())
        assert context.emit_graph_events is True
        assert context.emit_usage_events is True

    def test_teardown_returns_none_when_graph_events_off(self) -> None:
        """Costs-only mode: the tracer still mints node ids, but teardown skips the discarded spec build."""
        tracer = GraphTracer()
        context = tracer.setup(
            graph_id="costs-only",
            data_inclusion=make_defaulted_data_inclusion_config(),
            emit_graph_events=False,
        )
        self._start_a_node(tracer, context)
        assert tracer.teardown() is None
        assert tracer.is_active is False

    def test_teardown_builds_spec_when_graph_events_on(self) -> None:
        tracer = GraphTracer()
        context = tracer.setup(
            graph_id="graph-on",
            data_inclusion=make_defaulted_data_inclusion_config(),
            emit_graph_events=True,
        )
        self._start_a_node(tracer, context)
        graph_spec = tracer.teardown()
        assert graph_spec is not None
        assert graph_spec.graph_id == "graph-on"
        assert len(graph_spec.nodes) == 1
