"""Unit tests for GraphTracerManager's per-run tracer lifecycle (open/close registration)."""

from datetime import UTC, datetime

import pytest
from pytest_mock import MockerFixture

from pipelex.graph.graph_tracer import GraphTracer
from pipelex.graph.graph_tracer_manager import GraphTracerManager
from pipelex.graph.graphspec import NodeKind
from pipelex.system.data_inclusion_config import DataInclusionConfig
from pipelex.system.execution_chain import ExecutionAttempt
from pipelex.system.pipe_run_mode import PipeRunMode
from pipelex.tracing.in_memory_event_log import InMemoryEventLog
from pipelex.tracing.trace_events import PipeStartEvent


def _make_data_inclusion() -> DataInclusionConfig:
    return DataInclusionConfig(
        stuff_json_content=False,
        error_stack_traces=False,
        pipe_and_concept_registry=False,
    )


class TestGraphTracerManagerOpenTracer:
    def test_open_tracer_registers_then_close_pops(self) -> None:
        """Happy path: open_tracer registers the tracer under graph_id; close_tracer pops it."""
        GraphTracerManager.clear_instance()
        manager = GraphTracerManager.get_or_create_instance()
        try:
            trace_context = manager.open_tracer(graph_id="lifecycle_graph", data_inclusion=_make_data_inclusion(), run_mode=PipeRunMode.LIVE)
            assert trace_context.graph_id == "lifecycle_graph"
            assert manager.get_tracer("lifecycle_graph") is not None

            manager.close_tracer("lifecycle_graph")
            assert manager.get_tracer("lifecycle_graph") is None
        finally:
            GraphTracerManager.clear_instance()

    def test_setup_failure_does_not_leak_registration(self, mocker: MockerFixture) -> None:
        """A failure inside GraphTracer.setup must not leave a tracer registered in the manager."""
        GraphTracerManager.clear_instance()
        manager = GraphTracerManager.get_or_create_instance()
        try:
            mocker.patch.object(GraphTracer, "setup", side_effect=ValueError("setup blew up"))

            with pytest.raises(ValueError, match="setup blew up"):
                manager.open_tracer(graph_id="leak_check_graph", data_inclusion=_make_data_inclusion(), run_mode=PipeRunMode.LIVE)

            assert manager.get_tracer("leak_check_graph") is None
        finally:
            GraphTracerManager.clear_instance()

    def test_a_dispatched_execution_continues_the_place_and_the_chain_it_received(self) -> None:
        """A batch item run as an execution of its own stamps paths under its item's, and the dispatching attempt as its lineage."""
        GraphTracerManager.clear_instance()
        manager = GraphTracerManager.get_or_create_instance()
        event_log = InMemoryEventLog()
        try:
            run_context = manager.open_tracer(
                graph_id="run_7Qd2kV",
                data_inclusion=_make_data_inclusion(),
                event_log=event_log,
                workflow_id="exec-run",
                attempt=2,
                pipeline_run_id="run_7Qd2kV",
                tracer_key="exec-run-key",
                run_mode=PipeRunMode.LIVE,
            )
            assert (run_context.chain, run_context.lineage) == ([ExecutionAttempt(execution="exec-run", attempt=2)], [])
            _, entry_context = manager.on_pipe_start(
                trace_context=run_context,
                pipe_code="review_filings",
                pipe_ref="filings.review_filings",
                pipe_type="PipeSequence",
                node_kind=NodeKind.CONTROLLER,
                started_at=datetime.now(UTC),
            )
            assert entry_context is not None
            batch_node_id, batch_context = manager.on_pipe_start(
                trace_context=entry_context.with_child_segment(segment="step_3"),
                pipe_code="summarize_filing_batch",
                pipe_ref="filings.summarize_filing_batch",
                pipe_type="PipeBatch",
                node_kind=NodeKind.CONTROLLER,
                started_at=datetime.now(UTC),
            )
            assert batch_context is not None

            item_context = manager.open_tracer(
                graph_id="run_7Qd2kV",
                data_inclusion=_make_data_inclusion(),
                event_log=event_log,
                workflow_id="exec-item-2",
                received_context=batch_context.with_child_segment(segment="item_2"),
                pipeline_run_id="run_7Qd2kV",
                tracer_key="exec-item-2-key",
                run_mode=PipeRunMode.LIVE,
            )
            assert item_context.chain == [ExecutionAttempt(execution="exec-run", attempt=2), ExecutionAttempt(execution="exec-item-2", attempt=1)]
            assert (item_context.parent_node_id, item_context.parent_path, item_context.child_segment) == (
                batch_node_id,
                "filings.review_filings/step_3",
                "item_2",
            )
            manager.on_pipe_start(
                trace_context=item_context,
                pipe_code="summarize_filing",
                pipe_ref="filings.summarize_filing",
                pipe_type="PipeSequence",
                node_kind=NodeKind.CONTROLLER,
                started_at=datetime.now(UTC),
            )
        finally:
            manager.close_tracer("exec-item-2-key")
            manager.close_tracer("exec-run-key")
            GraphTracerManager.clear_instance()

        starts = [event for event in event_log.read_events("run_7Qd2kV") if isinstance(event, PipeStartEvent)]
        assert sorted((event.workflow_id, event.attempt, event.path, len(event.lineage)) for event in starts) == [
            ("exec-item-2", 1, "filings.review_filings/step_3/item_2", 1),
            ("exec-run", 2, "filings.review_filings", 0),
            ("exec-run", 2, "filings.review_filings/step_3", 0),
        ]
        item_start = next(event for event in starts if event.workflow_id == "exec-item-2")
        assert item_start.lineage == [ExecutionAttempt(execution="exec-run", attempt=2)]

    def test_a_received_context_naming_no_place_leaves_the_lineage_empty(self) -> None:
        """The run's own execution receives the submitter's context, which names no place: it was dispatched by no attempt."""
        GraphTracerManager.clear_instance()
        manager = GraphTracerManager.get_or_create_instance()
        try:
            submitted_context = manager.open_tracer(
                graph_id="submitted_graph", data_inclusion=_make_data_inclusion(), tracer_key="submitter", run_mode=PipeRunMode.LIVE
            )
            run_context = manager.open_tracer(
                graph_id="submitted_graph",
                data_inclusion=_make_data_inclusion(),
                workflow_id="exec-run",
                attempt=3,
                received_context=submitted_context,
                tracer_key="exec-run-key",
                run_mode=PipeRunMode.LIVE,
            )
            assert run_context.chain == [ExecutionAttempt(execution="exec-run", attempt=3)]
            assert (run_context.parent_path, run_context.child_segment) == (None, None)
            assert run_context.invocation_path(pipe_ref="filings.review_filings") == "filings.review_filings"
        finally:
            GraphTracerManager.clear_instance()
