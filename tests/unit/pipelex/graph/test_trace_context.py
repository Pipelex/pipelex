"""Unit tests for TraceContext."""

import pytest

from pipelex.system.exceptions import InvocationPathError
from pipelex.system.execution_chain import ExecutionAttempt
from pipelex.system.trace_context import TraceContext
from tests.unit.pipelex.graph.conftest import make_trace_context


class TestTraceContext:
    """Tests for TraceContext model."""

    def test_make_node_id(self) -> None:
        """Test node ID generation."""
        context = make_trace_context(graph_id="ctx-test", node_sequence=5)
        node_id = context.make_node_id()

        assert node_id == "ctx-test:node_5"

    def test_copy_for_child(self) -> None:
        """Test creating child context."""
        parent = make_trace_context(graph_id="ctx-test", parent_node_id=None, node_sequence=0)
        child = parent.copy_for_child(child_node_id="ctx-test:node_0", next_sequence=1, invocation_path="tests.ctx_pipe")

        assert child.graph_id == "ctx-test"
        assert child.parent_node_id == "ctx-test:node_0"
        assert child.node_sequence == 1
        # The child continues the parent's invocation path, names no segment yet, and keeps the parent's chain
        assert child.parent_path == "tests.ctx_pipe"
        assert child.child_segment is None
        assert child.chain == parent.chain
        # Parent should be unchanged
        assert parent.parent_node_id is None
        assert parent.node_sequence == 0
        assert parent.parent_path is None

    def test_copy_for_child_preserves_data_inclusion(self) -> None:
        """Test that copy_for_child preserves data_inclusion config."""
        parent = make_trace_context(
            graph_id="ctx-test",
            stuff_json_content=True,
        )
        child = parent.copy_for_child(child_node_id="ctx-test:node_0", next_sequence=1, invocation_path="tests.ctx_pipe")

        assert child.data_inclusion.stuff_json_content is True

    def test_the_entry_pipe_is_named_by_its_pipe_ref(self) -> None:
        assert make_trace_context().invocation_path(pipe_ref="filings.review_filings") == "filings.review_filings"

    def test_a_child_pipe_continues_its_parent_path_with_the_segment_its_controller_gave(self) -> None:
        parent = make_trace_context().copy_for_child(child_node_id="test-graph:node_0", next_sequence=1, invocation_path="filings.review_filings")
        placed = parent.with_child_segment(segment="step_3")

        assert placed.invocation_path(pipe_ref="filings.summarize_filing_batch") == "filings.review_filings/step_3"
        # The segment rides on the copy handed to that one pipe, never on the controller's own context.
        assert parent.child_segment is None

    @pytest.mark.parametrize(
        ("parent_path", "child_segment", "message"),
        [
            ("filings.review_filings", None, "without the segment its controller gives it"),
            (None, "step_1", "with no parent invocation to place it under"),
        ],
        ids=["segment_missing", "parent_missing"],
    )
    def test_a_path_that_cannot_be_derived_is_refused(self, parent_path: str | None, child_segment: str | None, message: str) -> None:
        context = make_trace_context().model_copy(update={"parent_path": parent_path, "child_segment": child_segment})

        with pytest.raises(InvocationPathError, match=message):
            context.invocation_path(pipe_ref="filings.read_filing")

    def test_the_chain_names_the_writing_attempt_and_its_lineage(self) -> None:
        run_attempt = ExecutionAttempt(execution="exec-run", attempt=1)
        item_attempt = ExecutionAttempt(execution="exec-item-2", attempt=2)
        context = make_trace_context().model_copy(update={"chain": [run_attempt, item_attempt]})

        assert (context.own_attempt, context.lineage) == (item_attempt, [run_attempt])
        assert make_trace_context().chain == [ExecutionAttempt(execution="direct", attempt=1)]
        assert make_trace_context().lineage == []

    def test_the_path_prefix_and_the_chain_survive_serialization(self) -> None:
        """What a dispatched execution reads back from its input is what the dispatcher sent."""
        context = (
            make_trace_context()
            .copy_for_child(child_node_id="test-graph:node_4", next_sequence=5, invocation_path="filings.review_filings/step_3")
            .with_child_segment(segment="item_2")
            .model_copy(update={"chain": [ExecutionAttempt(execution="exec-run", attempt=3)]})
        )

        recovered = TraceContext.model_validate_json(context.model_dump_json())

        assert recovered == context
        assert (recovered.parent_path, recovered.child_segment, recovered.chain) == (
            "filings.review_filings/step_3",
            "item_2",
            [ExecutionAttempt(execution="exec-run", attempt=3)],
        )
        assert recovered.invocation_path(pipe_ref="filings.summarize_filing") == "filings.review_filings/step_3/item_2"
