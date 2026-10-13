"""Unit tests for the decisions a controller records as it makes them, and for the run mode every trace event states."""

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from pipelex.graph.graph_tracer import GraphTracer
from pipelex.graph.graph_tracer_manager import GraphTracerManager
from pipelex.graph.graph_tracer_protocol import GraphTracerNoOp
from pipelex.graph.graphspec import IOSpec, NodeKind
from pipelex.system.pipe_run_mode import PipeRunMode
from pipelex.system.trace_context import TraceContext
from pipelex.tracing.in_memory_event_log import InMemoryEventLog
from pipelex.tracing.trace_events import (
    BatchFannedOutEvent,
    ConditionResolvedEvent,
    PipeStartEvent,
    TraceEvent,
)
from tests.unit.pipelex.graph.conftest import make_defaulted_data_inclusion_config

_PIPELINE_RUN_ID = "run_decisions_001"
_GRAPH_ID = "graph-decisions"
_T0 = datetime(2026, 10, 13, 9, 0, 0, tzinfo=UTC)


def _make_tracer(*, run_mode: PipeRunMode) -> tuple[GraphTracer, TraceContext, InMemoryEventLog]:
    event_log = InMemoryEventLog()
    tracer = GraphTracer()
    context = tracer.setup(
        graph_id=_GRAPH_ID,
        data_inclusion=make_defaulted_data_inclusion_config(),
        event_log=event_log,
        pipeline_run_id=_PIPELINE_RUN_ID,
        run_mode=run_mode,
    )
    return tracer, context, event_log


def _start_of(*, events: list[TraceEvent], node_id: str) -> PipeStartEvent:
    return next(event for event in events if isinstance(event, PipeStartEvent) and event.node_id == node_id)


class TestGraphTracerDecisionEvents:
    @pytest.mark.parametrize(
        ("rendered_value", "selected_outcome"),
        [("urgent", "urgent"), ("unmatched", None)],
        ids=["matched_key", "default_outcome"],
    )
    def test_condition_resolution_precedes_the_chosen_pipe(self, rendered_value: str, selected_outcome: str | None) -> None:
        """The resolution is recorded before the chosen pipe starts, and the graph's SELECTED_OUTCOME edge to it is labelled with the key."""
        tracer, context, event_log = _make_tracer(run_mode=PipeRunMode.LIVE)
        condition_id, condition_ctx = tracer.on_pipe_start(
            trace_context=context, pipe_code="route", pipe_type="PipeCondition", node_kind=NodeKind.CONTROLLER, started_at=_T0
        )

        tracer.register_condition_resolution(condition_node_id=condition_id, rendered_value=rendered_value, selected_outcome=selected_outcome)
        chosen_id, _ = tracer.on_pipe_start(
            trace_context=condition_ctx,
            pipe_code="handle",
            pipe_type="PipeCompose",
            node_kind=NodeKind.OPERATOR,
            started_at=_T0 + timedelta(seconds=1),
        )
        tracer.on_pipe_end_success(node_id=chosen_id, ended_at=_T0 + timedelta(seconds=2))
        tracer.on_pipe_end_success(node_id=condition_id, ended_at=_T0 + timedelta(seconds=3))
        graph_spec = tracer.teardown()

        events = event_log.read_events(_PIPELINE_RUN_ID)
        resolutions = [event for event in events if isinstance(event, ConditionResolvedEvent)]
        assert len(resolutions) == 1
        resolution = resolutions[0]
        assert resolution.node_id == condition_id
        assert resolution.rendered_value == rendered_value
        assert resolution.selected_outcome == selected_outcome
        assert resolution.sequence < _start_of(events=events, node_id=chosen_id).sequence

        assert graph_spec is not None
        graph_edges = [edge for edge in graph_spec.edges if edge.kind.is_selected_outcome]
        assert [(edge.source, edge.target, edge.label) for edge in graph_edges] == [(condition_id, chosen_id, selected_outcome)]

    def test_condition_resolution_without_a_pipe_draws_no_edge(self) -> None:
        """An outcome mapped to `continue` or `fail` starts no pipe: the resolution is recorded, and the graph has no edge from it."""
        tracer, context, event_log = _make_tracer(run_mode=PipeRunMode.LIVE)
        sequence_id, sequence_ctx = tracer.on_pipe_start(
            trace_context=context, pipe_code="flow", pipe_type="PipeSequence", node_kind=NodeKind.CONTROLLER, started_at=_T0, step_count=2
        )
        condition_id, _ = tracer.on_pipe_start(
            trace_context=sequence_ctx, pipe_code="route", pipe_type="PipeCondition", node_kind=NodeKind.CONTROLLER, started_at=_T0
        )

        tracer.register_condition_resolution(condition_node_id=condition_id, rendered_value="skip", selected_outcome="skip")
        tracer.on_pipe_end_success(node_id=condition_id, ended_at=_T0 + timedelta(seconds=1))
        # The next step starts under the sequence, never under the condition
        next_step_id, _ = tracer.on_pipe_start(
            trace_context=sequence_ctx,
            pipe_code="later",
            pipe_type="PipeCompose",
            node_kind=NodeKind.OPERATOR,
            started_at=_T0 + timedelta(seconds=2),
        )
        tracer.on_pipe_end_success(node_id=next_step_id, ended_at=_T0 + timedelta(seconds=3))
        tracer.on_pipe_end_success(node_id=sequence_id, ended_at=_T0 + timedelta(seconds=4))
        graph_spec = tracer.teardown()

        events = event_log.read_events(_PIPELINE_RUN_ID)
        assert [event.selected_outcome for event in events if isinstance(event, ConditionResolvedEvent)] == ["skip"]
        assert graph_spec is not None
        assert [edge for edge in graph_spec.edges if edge.kind.is_selected_outcome] == []

    def test_batch_fan_out_precedes_the_first_item(self) -> None:
        tracer, context, event_log = _make_tracer(run_mode=PipeRunMode.LIVE)
        batch_id, batch_ctx = tracer.on_pipe_start(
            trace_context=context,
            pipe_code="per_item",
            pipe_type="PipeBatch",
            node_kind=NodeKind.CONTROLLER,
            started_at=_T0,
            input_specs=[IOSpec(name="items", digest="digest_items", multiplicity=True)],
        )

        tracer.register_batch_fan_out(
            batch_node_id=batch_id, item_count=2, branch_pipe_code="process", branch_pipe_ref="flows.process", branch_pipe_type="PipeCompose"
        )
        item_ids: list[str] = []
        for index_item in range(2):
            item_id, _ = tracer.on_pipe_start(
                trace_context=batch_ctx,
                pipe_code="process",
                pipe_type="PipeCompose",
                node_kind=NodeKind.OPERATOR,
                started_at=_T0 + timedelta(seconds=1 + index_item),
            )
            item_ids.append(item_id)

        events = event_log.read_events(_PIPELINE_RUN_ID)
        fan_outs = [event for event in events if isinstance(event, BatchFannedOutEvent)]
        assert len(fan_outs) == 1
        fan_out = fan_outs[0]
        assert fan_out.node_id == batch_id
        assert fan_out.item_count == 2
        assert fan_out.branch_pipe_code == "process"
        assert fan_out.branch_pipe_ref == "flows.process"
        assert fan_out.branch_pipe_type == "PipeCompose"
        first_item_start = _start_of(events=events, node_id=item_ids[0])
        assert fan_out.sequence < first_item_start.sequence

    def test_controllers_state_their_width_as_they_start(self) -> None:
        tracer, context, event_log = _make_tracer(run_mode=PipeRunMode.LIVE)
        sequence_id, sequence_ctx = tracer.on_pipe_start(
            trace_context=context, pipe_code="flow", pipe_type="PipeSequence", node_kind=NodeKind.CONTROLLER, started_at=_T0, step_count=3
        )
        parallel_id, _ = tracer.on_pipe_start(
            trace_context=sequence_ctx,
            pipe_code="fan",
            pipe_type="PipeParallel",
            node_kind=NodeKind.CONTROLLER,
            started_at=_T0 + timedelta(seconds=1),
            branch_count=2,
        )

        events = event_log.read_events(_PIPELINE_RUN_ID)
        sequence_start = _start_of(events=events, node_id=sequence_id)
        parallel_start = _start_of(events=events, node_id=parallel_id)
        assert (sequence_start.step_count, sequence_start.branch_count) == (3, None)
        assert (parallel_start.step_count, parallel_start.branch_count) == (None, 2)

    @pytest.mark.parametrize("run_mode", [PipeRunMode.LIVE, PipeRunMode.DRY], ids=["live", "dry"])
    def test_every_event_states_the_run_mode(self, run_mode: PipeRunMode) -> None:
        """The tracer stamps its run's mode on every event it writes, and its contexts carry the mode down."""
        tracer, context, event_log = _make_tracer(run_mode=run_mode)
        assert context.run_mode == run_mode

        batch_id, batch_ctx = tracer.on_pipe_start(
            trace_context=context, pipe_code="per_item", pipe_type="PipeBatch", node_kind=NodeKind.CONTROLLER, started_at=_T0
        )
        assert batch_ctx.run_mode == run_mode
        tracer.register_batch_fan_out(
            batch_node_id=batch_id, item_count=1, branch_pipe_code="route", branch_pipe_ref="flows.route", branch_pipe_type="PipeCondition"
        )
        tracer.register_batch_item_extraction(list_stuff_code="list", item_stuff_code="item", item_index=0, batch_controller_node_id=batch_id)
        condition_id, condition_ctx = tracer.on_pipe_start(
            trace_context=batch_ctx,
            pipe_code="route",
            pipe_type="PipeCondition",
            node_kind=NodeKind.CONTROLLER,
            started_at=_T0 + timedelta(seconds=1),
        )
        tracer.register_condition_resolution(condition_node_id=condition_id, rendered_value="yes", selected_outcome="yes")
        chosen_id, _ = tracer.on_pipe_start(
            trace_context=condition_ctx,
            pipe_code="handle",
            pipe_type="PipeCompose",
            node_kind=NodeKind.OPERATOR,
            started_at=_T0 + timedelta(seconds=2),
        )
        tracer.register_execution_data(node_id=chosen_id, execution_data={"rendered": "text"})
        tracer.on_pipe_end_success(node_id=chosen_id, ended_at=_T0 + timedelta(seconds=3), output_spec=IOSpec(name="result", digest="result"))
        tracer.on_pipe_end_success(node_id=condition_id, ended_at=_T0 + timedelta(seconds=4))
        tracer.register_batch_aggregation(output_list_stuff_code="out", item_stuff_code="result", item_index=0, batch_controller_node_id=batch_id)
        tracer.on_pipe_end_success(node_id=batch_id, ended_at=_T0 + timedelta(seconds=5))
        tracer.teardown()

        events = event_log.read_events(_PIPELINE_RUN_ID)
        kinds = {event.model_dump()["event_kind"] for event in events}
        assert {"pipe_start", "pipe_end_success", "edge", "batch_fanned_out", "condition_resolved", "batch_item", "batch_aggregate"} <= kinds
        assert {event.mode for event in events} == {run_mode}

    def test_an_inactive_tracer_records_no_decision(self) -> None:
        tracer, _, event_log = _make_tracer(run_mode=PipeRunMode.LIVE)
        tracer.teardown()

        tracer.register_batch_fan_out(
            batch_node_id="gone", item_count=1, branch_pipe_code="process", branch_pipe_ref="flows.process", branch_pipe_type="PipeCompose"
        )
        tracer.register_condition_resolution(condition_node_id="gone", rendered_value="yes", selected_outcome="yes")

        assert event_log.read_events(_PIPELINE_RUN_ID) == []

    def test_a_costs_only_run_records_no_decision(self) -> None:
        """A run that emits no graph events records no decision, even on a tracer it hands an event log."""
        event_log = InMemoryEventLog()
        tracer = GraphTracer()
        context = tracer.setup(
            graph_id=_GRAPH_ID,
            data_inclusion=make_defaulted_data_inclusion_config(),
            event_log=event_log,
            pipeline_run_id=_PIPELINE_RUN_ID,
            emit_graph_events=False,
            run_mode=PipeRunMode.LIVE,
        )
        batch_id, batch_ctx = tracer.on_pipe_start(
            trace_context=context, pipe_code="per_item", pipe_type="PipeBatch", node_kind=NodeKind.CONTROLLER, started_at=_T0
        )
        tracer.register_batch_fan_out(
            batch_node_id=batch_id, item_count=1, branch_pipe_code="route", branch_pipe_ref="flows.route", branch_pipe_type="PipeCondition"
        )
        condition_id, _ = tracer.on_pipe_start(
            trace_context=batch_ctx,
            pipe_code="route",
            pipe_type="PipeCondition",
            node_kind=NodeKind.CONTROLLER,
            started_at=_T0 + timedelta(seconds=1),
        )
        tracer.register_condition_resolution(condition_node_id=condition_id, rendered_value="yes", selected_outcome="yes")
        assert tracer.teardown() is None

        events = event_log.read_events(_PIPELINE_RUN_ID)
        assert [event for event in events if isinstance(event, (BatchFannedOutEvent, ConditionResolvedEvent))] == []

    def test_a_tracer_records_no_decision_on_a_node_it_never_started(self) -> None:
        """A decision looked up on a tracer that does not hold the controller's node is dropped, as its execution data is.

        The pipe started under that node, as a distributed run's child workflow starts its first pipe under its parent's
        controller, gets no SELECTED_OUTCOME edge from a node absent from this tracer's graph.
        """
        tracer, context, event_log = _make_tracer(run_mode=PipeRunMode.LIVE)
        foreign_node_id = "graph-decisions:other_workflow:node_0"
        foreign_ctx = context.copy_for_child(child_node_id=foreign_node_id, next_sequence=0)

        tracer.register_batch_fan_out(
            batch_node_id=foreign_node_id,
            item_count=1,
            branch_pipe_code="process",
            branch_pipe_ref="flows.process",
            branch_pipe_type="PipeCompose",
        )
        tracer.register_condition_resolution(condition_node_id=foreign_node_id, rendered_value="yes", selected_outcome="yes")
        chosen_id, _ = tracer.on_pipe_start(
            trace_context=foreign_ctx, pipe_code="handle", pipe_type="PipeCompose", node_kind=NodeKind.OPERATOR, started_at=_T0
        )
        tracer.on_pipe_end_success(node_id=chosen_id, ended_at=_T0 + timedelta(seconds=1))
        graph_spec = tracer.teardown()

        events = event_log.read_events(_PIPELINE_RUN_ID)
        assert [event for event in events if isinstance(event, (BatchFannedOutEvent, ConditionResolvedEvent))] == []
        assert graph_spec is not None
        assert [edge for edge in graph_spec.edges if edge.kind.is_selected_outcome] == []

    def test_a_trace_context_states_its_run_mode(self) -> None:
        """A context has no default mode: one built without it would stamp a dry run's events as live."""
        with pytest.raises(ValidationError, match="run_mode"):
            TraceContext(graph_id=_GRAPH_ID, data_inclusion=make_defaulted_data_inclusion_config())  # type: ignore[call-arg] # pyright: ignore[reportCallIssue] # the static error is the runtime contract under test

    def test_the_noop_tracer_accepts_decisions_and_carries_the_mode(self) -> None:
        tracer = GraphTracerNoOp()
        context = tracer.setup(graph_id="noop", data_inclusion=make_defaulted_data_inclusion_config(), run_mode=PipeRunMode.DRY)

        tracer.register_batch_fan_out(
            batch_node_id="node", item_count=1, branch_pipe_code="process", branch_pipe_ref="flows.process", branch_pipe_type="PipeCompose"
        )
        tracer.register_condition_resolution(condition_node_id="node", rendered_value="yes", selected_outcome=None)

        assert context.run_mode == PipeRunMode.DRY
        assert tracer.teardown() is None

    def test_the_manager_routes_decisions_to_the_run_tracer(self) -> None:
        GraphTracerManager.clear_instance()
        manager = GraphTracerManager.get_or_create_instance()
        event_log = InMemoryEventLog()
        try:
            context = manager.open_tracer(
                graph_id=_GRAPH_ID,
                data_inclusion=make_defaulted_data_inclusion_config(),
                event_log=event_log,
                pipeline_run_id=_PIPELINE_RUN_ID,
                run_mode=PipeRunMode.DRY,
            )
            batch_id, _ = manager.on_pipe_start(
                trace_context=context, pipe_code="per_item", pipe_type="PipeBatch", node_kind=NodeKind.CONTROLLER, started_at=_T0
            )
            assert batch_id is not None
            manager.register_batch_fan_out(
                lookup_key=context.lookup_key,
                batch_node_id=batch_id,
                item_count=4,
                branch_pipe_code="process",
                branch_pipe_ref="flows.process",
                branch_pipe_type="PipeCompose",
            )
            manager.register_condition_resolution(
                lookup_key=context.lookup_key, condition_node_id=batch_id, rendered_value="yes", selected_outcome="yes"
            )
            # A key no tracer answers to is a no-op
            manager.register_condition_resolution(lookup_key="unknown", condition_node_id=batch_id, rendered_value="yes", selected_outcome="yes")
        finally:
            manager.close_tracer(_GRAPH_ID)
            GraphTracerManager.clear_instance()

        events = event_log.read_events(_PIPELINE_RUN_ID)
        assert [event.item_count for event in events if isinstance(event, BatchFannedOutEvent)] == [4]
        assert [event.rendered_value for event in events if isinstance(event, ConditionResolvedEvent)] == ["yes"]
        assert {event.mode for event in events} == {PipeRunMode.DRY}
