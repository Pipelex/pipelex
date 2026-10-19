"""Unit tests for GraphTracer event emission (dual-write mode).

Validates that when an EventLogProtocol is provided, GraphTracer emits the
correct trace events as a side effect alongside its existing in-memory accumulation.
"""

from datetime import UTC, datetime, timedelta

import pytest
from mthds.protocol.problem.registry import CoreCode

from pipelex.core.stuffs.exceptions import StuffFactoryError
from pipelex.errors.problem import ProblemView, make_location, make_problem
from pipelex.graph.graph_tracer import GraphTracer
from pipelex.graph.graphspec import EdgeKind, IOSpec, NodeKind, NodeStatus
from pipelex.graph.node_problem import make_node_problem
from pipelex.system.execution_chain import ExecutionAttempt
from pipelex.system.pipe_run_mode import PipeRunMode
from pipelex.tracing.in_memory_event_log import InMemoryEventLog
from pipelex.tracing.trace_events import (
    BatchAggregateEvent,
    BatchItemEvent,
    ControllerOutputEvent,
    EdgeEvent,
    ParallelCombineEvent,
    PipeEndErrorEvent,
    PipeEndSuccessEvent,
    PipeStartEvent,
)
from tests.unit.pipelex.graph.conftest import make_defaulted_data_inclusion_config


class TestGraphTracerEventEmission:
    """Tests for GraphTracer dual-write event emission."""

    PIPELINE_RUN_ID = "run_evt_001"
    WORKFLOW_ID = "wf_test_abc"
    GRAPH_ID = "graph-emit-test"

    def _make_tracer_with_event_log(
        self,
        workflow_id: str | None = None,
    ) -> tuple[GraphTracer, InMemoryEventLog]:
        """Create a GraphTracer configured with an InMemoryEventLog."""
        event_log = InMemoryEventLog()
        tracer = GraphTracer()
        tracer.setup(
            graph_id=self.GRAPH_ID,
            data_inclusion=make_defaulted_data_inclusion_config(),
            event_log=event_log,
            workflow_id=workflow_id or self.WORKFLOW_ID,
            pipeline_run_id=self.PIPELINE_RUN_ID,
            run_mode=PipeRunMode.LIVE,
        )
        return tracer, event_log

    def test_pipe_start_emits_event(self) -> None:
        """PipeStartEvent is emitted on on_pipe_start."""
        tracer, event_log = self._make_tracer_with_event_log()

        context = tracer.setup(
            graph_id=self.GRAPH_ID,
            data_inclusion=make_defaulted_data_inclusion_config(),
            event_log=event_log,
            workflow_id=self.WORKFLOW_ID,
            pipeline_run_id=self.PIPELINE_RUN_ID,
            run_mode=PipeRunMode.LIVE,
        )

        started_at = datetime(2025, 6, 15, 10, 0, 0, tzinfo=UTC)
        node_id, _child_ctx = tracer.on_pipe_start(
            pipe_ref="tests.test_pipe",
            trace_context=context,
            pipe_code="test_pipe",
            pipe_type="PipeLLM",
            node_kind=NodeKind.OPERATOR,
            started_at=started_at,
        )

        events = event_log.read_events(self.PIPELINE_RUN_ID)
        pipe_starts = [evt for evt in events if isinstance(evt, PipeStartEvent)]
        assert len(pipe_starts) == 1

        evt = pipe_starts[0]
        assert evt.node_id == node_id
        assert evt.pipe_code == "test_pipe"
        assert evt.pipe_type == "PipeLLM"
        assert evt.node_kind == NodeKind.OPERATOR
        assert evt.parent_node_id is None
        assert evt.workflow_id == self.WORKFLOW_ID
        assert evt.pipeline_run_id == self.PIPELINE_RUN_ID

    def test_pipe_start_with_parent_emits_contains_edge(self) -> None:
        """CONTAINS EdgeEvent is emitted when parent_node_id is present."""
        tracer, event_log = self._make_tracer_with_event_log()

        context = tracer.setup(
            graph_id=self.GRAPH_ID,
            data_inclusion=make_defaulted_data_inclusion_config(),
            event_log=event_log,
            workflow_id=self.WORKFLOW_ID,
            pipeline_run_id=self.PIPELINE_RUN_ID,
            run_mode=PipeRunMode.LIVE,
        )

        started_at = datetime(2025, 6, 15, 10, 0, 0, tzinfo=UTC)
        parent_id, child_ctx = tracer.on_pipe_start(
            pipe_ref="tests.parent_pipe",
            trace_context=context,
            pipe_code="parent_pipe",
            pipe_type="PipeSequence",
            node_kind=NodeKind.CONTROLLER,
            started_at=started_at,
        )

        child_id, _ = tracer.on_pipe_start(
            pipe_ref="tests.child_pipe",
            trace_context=child_ctx.with_child_segment(segment="step_1"),
            pipe_code="child_pipe",
            pipe_type="PipeLLM",
            node_kind=NodeKind.OPERATOR,
            started_at=started_at + timedelta(milliseconds=10),
        )

        events = event_log.read_events(self.PIPELINE_RUN_ID)
        edge_events = [evt for evt in events if isinstance(evt, EdgeEvent)]
        contains_edges = [evt for evt in edge_events if evt.edge_kind == EdgeKind.CONTAINS]
        assert len(contains_edges) == 1
        assert contains_edges[0].source_node_id == parent_id
        assert contains_edges[0].target_node_id == child_id

    def test_pipe_end_success_emits_event(self) -> None:
        """PipeEndSuccessEvent is emitted on on_pipe_end_success."""
        tracer, event_log = self._make_tracer_with_event_log()

        context = tracer.setup(
            graph_id=self.GRAPH_ID,
            data_inclusion=make_defaulted_data_inclusion_config(),
            event_log=event_log,
            workflow_id=self.WORKFLOW_ID,
            pipeline_run_id=self.PIPELINE_RUN_ID,
            run_mode=PipeRunMode.LIVE,
        )

        started_at = datetime(2025, 6, 15, 10, 0, 0, tzinfo=UTC)
        node_id, _ = tracer.on_pipe_start(
            pipe_ref="tests.test_pipe",
            trace_context=context,
            pipe_code="test_pipe",
            pipe_type="PipeLLM",
            node_kind=NodeKind.OPERATOR,
            started_at=started_at,
        )

        ended_at = started_at + timedelta(milliseconds=100)
        output_spec = IOSpec(name="output", concept="Text", content_type="text/plain", digest="abc123")
        tracer.on_pipe_end_success(
            node_id=node_id,
            ended_at=ended_at,
            metrics={"tokens": 150.0},
            output_spec=output_spec,
        )

        events = event_log.read_events(self.PIPELINE_RUN_ID)
        success_events = [evt for evt in events if isinstance(evt, PipeEndSuccessEvent)]
        assert len(success_events) == 1

        evt = success_events[0]
        assert evt.node_id == node_id
        assert evt.ended_at == ended_at
        assert evt.metrics == {"tokens": 150.0}
        assert evt.output_spec is not None
        assert evt.output_spec.digest == "abc123"

    def test_pipe_end_error_emits_event(self) -> None:
        """PipeEndErrorEvent is emitted on on_pipe_end_error."""
        tracer, event_log = self._make_tracer_with_event_log()

        context = tracer.setup(
            graph_id=self.GRAPH_ID,
            data_inclusion=make_defaulted_data_inclusion_config(),
            event_log=event_log,
            workflow_id=self.WORKFLOW_ID,
            pipeline_run_id=self.PIPELINE_RUN_ID,
            run_mode=PipeRunMode.LIVE,
        )

        started_at = datetime(2025, 6, 15, 10, 0, 0, tzinfo=UTC)
        node_id, _ = tracer.on_pipe_start(
            pipe_ref="tests.test_pipe",
            trace_context=context,
            pipe_code="test_pipe",
            pipe_type="PipeLLM",
            node_kind=NodeKind.OPERATOR,
            started_at=started_at,
        )

        ended_at = started_at + timedelta(milliseconds=50)
        problem = make_problem(
            code=CoreCode.RUNTIME_UNEXPECTED,
            view=ProblemView.CALLER,
            location=make_location(pipe="test_pipe", path=["test_pipe"]),
        )
        tracer.on_pipe_end_error(
            node_id=node_id,
            ended_at=ended_at,
            problem=problem,
            error_stack="traceback line 1\nline 2",
        )

        events = event_log.read_events(self.PIPELINE_RUN_ID)
        error_events = [evt for evt in events if isinstance(evt, PipeEndErrorEvent)]
        assert len(error_events) == 1

        evt = error_events[0]
        assert evt.node_id == node_id
        assert evt.ended_at == ended_at
        assert evt.error == problem
        assert evt.error_stack == "traceback line 1\nline 2"
        # An end event names the pipe it ends, as its start does, and the invocation's path.
        assert (evt.pipe_code, evt.pipe_ref, evt.pipe_type, evt.path) == ("test_pipe", "tests.test_pipe", "PipeLLM", "tests.test_pipe")

    @pytest.mark.builds_problems_without_required_params(
        reason="builds the step's failure with a message alone, to check where its problem is recorded"
    )
    def test_pipe_end_error_records_the_same_caller_view_on_the_event_and_the_node(self) -> None:
        """The node's problem reaches the event and the node of the graph alike, in the caller's view, without the error's message."""
        tracer, event_log = self._make_tracer_with_event_log()
        context = tracer.setup(
            graph_id=self.GRAPH_ID,
            data_inclusion=make_defaulted_data_inclusion_config(),
            event_log=event_log,
            workflow_id=self.WORKFLOW_ID,
            pipeline_run_id=self.PIPELINE_RUN_ID,
            run_mode=PipeRunMode.LIVE,
        )
        started_at = datetime(2025, 6, 15, 10, 0, 0, tzinfo=UTC)
        node_id, _ = tracer.on_pipe_start(
            pipe_ref="tests.test_pipe",
            trace_context=context,
            pipe_code="test_pipe",
            pipe_type="PipeParallel",
            node_kind=NodeKind.CONTROLLER,
            started_at=started_at,
        )

        error_message = "PipeParallel 'test_pipe' cannot combine its branch results into its output 'Report'."
        problem = make_node_problem(
            error=StuffFactoryError(error_message).with_error_code(CoreCode.PIPE_OUTPUT_INVALID),
            pipe_code="test_pipe",
            pipe_path=["test_pipe"],
        )
        tracer.on_pipe_end_error(node_id=node_id, ended_at=started_at + timedelta(milliseconds=50), problem=problem)
        graph_spec = tracer.teardown()

        error_events = [evt for evt in event_log.read_events(self.PIPELINE_RUN_ID) if isinstance(evt, PipeEndErrorEvent)]
        assert [evt.error for evt in error_events] == [problem]
        assert graph_spec is not None
        failed_node = next(node for node in graph_spec.nodes if node.node_id == node_id)
        assert failed_node.error is not None
        assert failed_node.error == problem
        assert failed_node.error.code == CoreCode.PIPE_OUTPUT_INVALID
        assert failed_node.error.diagnostics is None
        assert error_message not in str(failed_node.error.to_wire())
        assert failed_node.path == "tests.test_pipe"

    def test_add_edge_emits_event(self) -> None:
        """EdgeEvent is emitted on add_edge."""
        tracer, event_log = self._make_tracer_with_event_log()

        context = tracer.setup(
            graph_id=self.GRAPH_ID,
            data_inclusion=make_defaulted_data_inclusion_config(),
            event_log=event_log,
            workflow_id=self.WORKFLOW_ID,
            pipeline_run_id=self.PIPELINE_RUN_ID,
            run_mode=PipeRunMode.LIVE,
        )

        started_at = datetime(2025, 6, 15, 10, 0, 0, tzinfo=UTC)
        node_a, _ctx_a = tracer.on_pipe_start(
            pipe_ref="tests.pipe_a",
            trace_context=context,
            pipe_code="pipe_a",
            pipe_type="PipeLLM",
            node_kind=NodeKind.OPERATOR,
            started_at=started_at,
        )
        node_b, _ = tracer.on_pipe_start(
            pipe_ref="tests.pipe_b",
            trace_context=context,
            pipe_code="pipe_b",
            pipe_type="PipeLLM",
            node_kind=NodeKind.OPERATOR,
            started_at=started_at,
        )

        tracer.add_edge(
            source_node_id=node_a,
            target_node_id=node_b,
            edge_kind=EdgeKind.DATA,
            label="output",
            source_stuff_digest="digest_a",
            target_stuff_digest="digest_b",
        )

        events = event_log.read_events(self.PIPELINE_RUN_ID)
        edge_events = [evt for evt in events if isinstance(evt, EdgeEvent) and evt.edge_kind == EdgeKind.DATA]
        assert len(edge_events) == 1

        evt = edge_events[0]
        assert evt.source_node_id == node_a
        assert evt.target_node_id == node_b
        assert evt.label == "output"
        assert evt.source_stuff_digest == "digest_a"
        assert evt.target_stuff_digest == "digest_b"

    def test_register_controller_output_emits_event(self) -> None:
        """ControllerOutputEvent is emitted on register_controller_output."""
        tracer, event_log = self._make_tracer_with_event_log()

        context = tracer.setup(
            graph_id=self.GRAPH_ID,
            data_inclusion=make_defaulted_data_inclusion_config(),
            event_log=event_log,
            workflow_id=self.WORKFLOW_ID,
            pipeline_run_id=self.PIPELINE_RUN_ID,
            run_mode=PipeRunMode.LIVE,
        )

        started_at = datetime(2025, 6, 15, 10, 0, 0, tzinfo=UTC)
        node_id, _ = tracer.on_pipe_start(
            pipe_ref="tests.parallel_pipe",
            trace_context=context,
            pipe_code="parallel_pipe",
            pipe_type="PipeParallel",
            node_kind=NodeKind.CONTROLLER,
            started_at=started_at,
        )

        output_spec = IOSpec(name="branch_output", concept="Text", content_type="text/plain", digest="branch_abc")
        tracer.register_controller_output(node_id=node_id, output_spec=output_spec)

        events = event_log.read_events(self.PIPELINE_RUN_ID)
        ctrl_events = [evt for evt in events if isinstance(evt, ControllerOutputEvent)]
        assert len(ctrl_events) == 1

        evt = ctrl_events[0]
        assert evt.node_id == node_id
        assert evt.output_spec.digest == "branch_abc"

    def test_register_batch_item_extraction_emits_event(self) -> None:
        """BatchItemEvent is emitted on register_batch_item_extraction."""
        tracer, event_log = self._make_tracer_with_event_log()

        _context = tracer.setup(
            graph_id=self.GRAPH_ID,
            data_inclusion=make_defaulted_data_inclusion_config(),
            event_log=event_log,
            workflow_id=self.WORKFLOW_ID,
            pipeline_run_id=self.PIPELINE_RUN_ID,
            run_mode=PipeRunMode.LIVE,
        )

        tracer.register_batch_item_extraction(
            list_stuff_code="list_digest",
            item_stuff_code="item_0_digest",
            item_index=0,
            batch_controller_node_id="graph-emit-test:node_0",
        )

        events = event_log.read_events(self.PIPELINE_RUN_ID)
        batch_events = [evt for evt in events if isinstance(evt, BatchItemEvent)]
        assert len(batch_events) == 1

        evt = batch_events[0]
        assert evt.list_stuff_code == "list_digest"
        assert evt.item_stuff_code == "item_0_digest"
        assert evt.item_index == 0
        assert evt.batch_controller_node_id == "graph-emit-test:node_0"

    def test_register_batch_aggregation_emits_event(self) -> None:
        """BatchAggregateEvent is emitted on register_batch_aggregation."""
        tracer, event_log = self._make_tracer_with_event_log()

        _context = tracer.setup(
            graph_id=self.GRAPH_ID,
            data_inclusion=make_defaulted_data_inclusion_config(),
            event_log=event_log,
            workflow_id=self.WORKFLOW_ID,
            pipeline_run_id=self.PIPELINE_RUN_ID,
            run_mode=PipeRunMode.LIVE,
        )

        tracer.register_batch_aggregation(
            output_list_stuff_code="out_list_digest",
            item_stuff_code="item_0_digest",
            item_index=0,
            batch_controller_node_id="graph-emit-test:node_1",
        )

        events = event_log.read_events(self.PIPELINE_RUN_ID)
        agg_events = [evt for evt in events if isinstance(evt, BatchAggregateEvent)]
        assert len(agg_events) == 1

        evt = agg_events[0]
        assert evt.output_list_stuff_code == "out_list_digest"
        assert evt.item_stuff_code == "item_0_digest"
        assert evt.item_index == 0
        assert evt.batch_controller_node_id == "graph-emit-test:node_1"

    def test_register_parallel_combine_emits_event_with_snapshotted_producers(self) -> None:
        """ParallelCombineEvent is emitted with correct snapshotted producer IDs."""
        tracer, event_log = self._make_tracer_with_event_log()

        context = tracer.setup(
            graph_id=self.GRAPH_ID,
            data_inclusion=make_defaulted_data_inclusion_config(),
            event_log=event_log,
            workflow_id=self.WORKFLOW_ID,
            pipeline_run_id=self.PIPELINE_RUN_ID,
            run_mode=PipeRunMode.LIVE,
        )

        started_at = datetime(2025, 6, 15, 10, 0, 0, tzinfo=UTC)

        # Create controller node
        ctrl_id, ctrl_ctx = tracer.on_pipe_start(
            pipe_ref="tests.parallel_ctrl",
            trace_context=context,
            pipe_code="parallel_ctrl",
            pipe_type="PipeParallel",
            node_kind=NodeKind.CONTROLLER,
            started_at=started_at,
        )

        # Create branch nodes and end them with outputs
        branch_a_id, _ = tracer.on_pipe_start(
            pipe_ref="tests.branch_a",
            trace_context=ctrl_ctx.with_child_segment(segment="step_1"),
            pipe_code="branch_a",
            pipe_type="PipeLLM",
            node_kind=NodeKind.OPERATOR,
            started_at=started_at,
        )
        tracer.on_pipe_end_success(
            node_id=branch_a_id,
            ended_at=started_at + timedelta(milliseconds=50),
            output_spec=IOSpec(name="out_a", concept="Text", content_type="text/plain", digest="digest_a"),
        )

        branch_b_id, _ = tracer.on_pipe_start(
            pipe_ref="tests.branch_b",
            trace_context=ctrl_ctx.with_child_segment(segment="step_2"),
            pipe_code="branch_b",
            pipe_type="PipeLLM",
            node_kind=NodeKind.OPERATOR,
            started_at=started_at,
        )
        tracer.on_pipe_end_success(
            node_id=branch_b_id,
            ended_at=started_at + timedelta(milliseconds=60),
            output_spec=IOSpec(name="out_b", concept="Text", content_type="text/plain", digest="digest_b"),
        )

        # Register parallel combine — should snapshot producers
        tracer.register_parallel_combine(
            combined_stuff_code="combined_digest",
            branch_stuff_codes=["digest_a", "digest_b"],
            parallel_controller_node_id=ctrl_id,
        )

        events = event_log.read_events(self.PIPELINE_RUN_ID)
        combine_events = [evt for evt in events if isinstance(evt, ParallelCombineEvent)]
        assert len(combine_events) == 1

        evt = combine_events[0]
        assert evt.combined_stuff_code == "combined_digest"
        assert evt.parallel_controller_node_id == ctrl_id
        assert evt.branch_stuff_codes == ["digest_a", "digest_b"]
        # Snapshotted producers should be the branch nodes, not the controller
        assert ("digest_a", branch_a_id) in evt.branch_producer_node_ids
        assert ("digest_b", branch_b_id) in evt.branch_producer_node_ids

    def test_no_event_log_works_as_before(self) -> None:
        """GraphTracer without event_log (direct mode) works exactly as before."""
        tracer = GraphTracer()
        context = tracer.setup(graph_id="direct-mode-test", data_inclusion=make_defaulted_data_inclusion_config(), run_mode=PipeRunMode.LIVE)

        started_at = datetime(2025, 6, 15, 10, 0, 0, tzinfo=UTC)
        node_id, _child_ctx = tracer.on_pipe_start(
            pipe_ref="tests.test_pipe",
            trace_context=context,
            pipe_code="test_pipe",
            pipe_type="PipeLLM",
            node_kind=NodeKind.OPERATOR,
            started_at=started_at,
        )

        assert node_id == "direct-mode-test:node_0"

        tracer.on_pipe_end_success(
            node_id=node_id,
            ended_at=started_at + timedelta(milliseconds=100),
        )

        graph_spec = tracer.teardown()
        assert graph_spec is not None
        assert len(graph_spec.nodes) == 1
        assert graph_spec.nodes[0].status == NodeStatus.SUCCEEDED

    def test_node_id_includes_workflow_id_in_temporal_mode(self) -> None:
        """Node IDs name the workflow and its attempt when not in direct mode."""
        tracer, event_log = self._make_tracer_with_event_log(workflow_id="wf_run_123")

        context = tracer.setup(
            graph_id=self.GRAPH_ID,
            data_inclusion=make_defaulted_data_inclusion_config(),
            event_log=event_log,
            workflow_id="wf_run_123",
            pipeline_run_id=self.PIPELINE_RUN_ID,
            run_mode=PipeRunMode.LIVE,
        )

        started_at = datetime(2025, 6, 15, 10, 0, 0, tzinfo=UTC)
        node_id, _ = tracer.on_pipe_start(
            pipe_ref="tests.test_pipe",
            trace_context=context,
            pipe_code="test_pipe",
            pipe_type="PipeLLM",
            node_kind=NodeKind.OPERATOR,
            started_at=started_at,
        )

        assert "wf_run_123" in node_id
        assert node_id == f"{self.GRAPH_ID}:wf_run_123:attempt_1:node_0"

    def test_each_attempt_and_each_dispatch_mints_its_own_ids(self) -> None:
        """Two attempts of one workflow, and a workflow two attempts of its parent dispatched under one name, number
        their nodes and edges from 0 alike: their ids differ by the chain alone, so no reader keyed on an id merges the
        node a lost attempt failed with the one its retry ran.
        """
        run_1 = ExecutionAttempt(execution="wf_run", attempt=1)
        run_2 = ExecutionAttempt(execution="wf_run", attempt=2)
        setups: list[tuple[str, int, list[ExecutionAttempt]]] = [
            ("wf_run", 1, []),
            ("wf_run", 2, []),
            ("wf_item", 1, [run_1]),
            ("wf_item", 2, [run_1]),
            ("wf_item", 1, [run_2]),
        ]
        ids_by_chain: list[set[str]] = []
        for workflow_id, attempt, lineage in setups:
            event_log = InMemoryEventLog()
            tracer = GraphTracer()
            context = tracer.setup(
                graph_id=self.GRAPH_ID,
                data_inclusion=make_defaulted_data_inclusion_config(),
                event_log=event_log,
                workflow_id=workflow_id,
                attempt=attempt,
                lineage=lineage,
                pipeline_run_id=self.PIPELINE_RUN_ID,
                run_mode=PipeRunMode.LIVE,
            )
            started_at = datetime(2025, 6, 15, 10, 0, 0, tzinfo=UTC)
            node_a, _ = tracer.on_pipe_start(
                pipe_ref="tests.pipe_a",
                trace_context=context,
                pipe_code="pipe_a",
                pipe_type="PipeLLM",
                node_kind=NodeKind.OPERATOR,
                started_at=started_at,
            )
            node_b, _ = tracer.on_pipe_start(
                pipe_ref="tests.pipe_b",
                trace_context=context,
                pipe_code="pipe_b",
                pipe_type="PipeLLM",
                node_kind=NodeKind.OPERATOR,
                started_at=started_at,
            )
            tracer.add_edge(source_node_id=node_a, target_node_id=node_b, edge_kind=EdgeKind.DATA)
            edge_ids = {evt.edge_id for evt in event_log.read_events(self.PIPELINE_RUN_ID) if isinstance(evt, EdgeEvent)}
            assert len(edge_ids) == 1
            ids_by_chain.append({node_a, node_b, *edge_ids})
            tracer.teardown()

        all_ids = [minted_id for chain_ids in ids_by_chain for minted_id in chain_ids]
        assert len(all_ids) == len(set(all_ids)) == 3 * len(setups)

    def test_edge_id_includes_workflow_id_in_temporal_mode(self) -> None:
        """Edge IDs include workflow_id segment when not in direct mode."""
        tracer, event_log = self._make_tracer_with_event_log(workflow_id="wf_run_456")

        context = tracer.setup(
            graph_id=self.GRAPH_ID,
            data_inclusion=make_defaulted_data_inclusion_config(),
            event_log=event_log,
            workflow_id="wf_run_456",
            pipeline_run_id=self.PIPELINE_RUN_ID,
            run_mode=PipeRunMode.LIVE,
        )

        started_at = datetime(2025, 6, 15, 10, 0, 0, tzinfo=UTC)
        node_a, _ = tracer.on_pipe_start(
            pipe_ref="tests.pipe_a",
            trace_context=context,
            pipe_code="pipe_a",
            pipe_type="PipeLLM",
            node_kind=NodeKind.OPERATOR,
            started_at=started_at,
        )
        node_b, _ = tracer.on_pipe_start(
            pipe_ref="tests.pipe_b",
            trace_context=context,
            pipe_code="pipe_b",
            pipe_type="PipeLLM",
            node_kind=NodeKind.OPERATOR,
            started_at=started_at,
        )

        tracer.add_edge(
            source_node_id=node_a,
            target_node_id=node_b,
            edge_kind=EdgeKind.DATA,
        )

        events = event_log.read_events(self.PIPELINE_RUN_ID)
        edge_events = [evt for evt in events if isinstance(evt, EdgeEvent) and evt.edge_kind == EdgeKind.DATA]
        assert len(edge_events) == 1
        assert edge_events[0].edge_id == f"{self.GRAPH_ID}:wf_run_456:attempt_1:edge_0"

    def test_event_sequence_is_monotonic(self) -> None:
        """Events have monotonically increasing sequence numbers."""
        tracer, event_log = self._make_tracer_with_event_log()

        context = tracer.setup(
            graph_id=self.GRAPH_ID,
            data_inclusion=make_defaulted_data_inclusion_config(),
            event_log=event_log,
            workflow_id=self.WORKFLOW_ID,
            pipeline_run_id=self.PIPELINE_RUN_ID,
            run_mode=PipeRunMode.LIVE,
        )

        started_at = datetime(2025, 6, 15, 10, 0, 0, tzinfo=UTC)
        for index in range(5):
            node_id, _ = tracer.on_pipe_start(
                pipe_ref=f"tests.{f'pipe_{index}'}",
                trace_context=context,
                pipe_code=f"pipe_{index}",
                pipe_type="PipeLLM",
                node_kind=NodeKind.OPERATOR,
                started_at=started_at + timedelta(milliseconds=index),
            )
            tracer.on_pipe_end_success(
                node_id=node_id,
                ended_at=started_at + timedelta(milliseconds=index + 50),
            )

        events = event_log.read_events(self.PIPELINE_RUN_ID)
        sequences = [evt.sequence for evt in events]
        assert sequences == sorted(sequences)
        assert len(set(sequences)) == len(sequences)  # All unique

    def test_direct_mode_node_id_unchanged(self) -> None:
        """In direct mode (no workflow_id), node ID format is unchanged."""
        tracer = GraphTracer()
        context = tracer.setup(graph_id="direct-graph", data_inclusion=make_defaulted_data_inclusion_config(), run_mode=PipeRunMode.LIVE)

        started_at = datetime(2025, 6, 15, 10, 0, 0, tzinfo=UTC)
        node_id, _ = tracer.on_pipe_start(
            pipe_ref="tests.test_pipe",
            trace_context=context,
            pipe_code="test_pipe",
            pipe_type="PipeLLM",
            node_kind=NodeKind.OPERATOR,
            started_at=started_at,
        )

        assert node_id == "direct-graph:node_0"
