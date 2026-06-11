"""Unit tests for GraphTracerManager's per-run tracer lifecycle (open/close registration)."""

import pytest
from pytest_mock import MockerFixture

from pipelex.graph.graph_config import DataInclusionConfig
from pipelex.graph.graph_tracer import GraphTracer
from pipelex.graph.graph_tracer_manager import GraphTracerManager


def _make_data_inclusion() -> DataInclusionConfig:
    return DataInclusionConfig(
        stuff_json_content=False,
        stuff_text_content=False,
        stuff_html_content=False,
        error_stack_traces=False,
        pipe_and_concept_registry=False,
    )


class TestGraphTracerManagerOpenTracer:
    def test_open_tracer_registers_then_close_pops(self) -> None:
        """Happy path: open_tracer registers the tracer under graph_id; close_tracer pops it."""
        GraphTracerManager.clear_instance()
        manager = GraphTracerManager.get_or_create_instance()
        try:
            trace_context = manager.open_tracer(graph_id="lifecycle_graph", data_inclusion=_make_data_inclusion())
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
                manager.open_tracer(graph_id="leak_check_graph", data_inclusion=_make_data_inclusion())

            assert manager.get_tracer("leak_check_graph") is None
        finally:
            GraphTracerManager.clear_instance()
