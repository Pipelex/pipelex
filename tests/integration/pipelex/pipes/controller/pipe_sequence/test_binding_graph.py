from typing import Any

import pytest
from pytest_mock import MockerFixture

from pipelex.base_exceptions import PipelexError
from pipelex.config import get_config
from pipelex.graph.graph_tracer import GraphTracer
from pipelex.graph.graphspec import EdgeKind, GraphSpec, NodeKind, NodeSpec, NodeStatus
from pipelex.pipe_controllers.binding.binding_step import BINDING_NODE_PIPE_TYPE
from pipelex.pipeline.runner import PipelexMTHDSProtocol
from pipelex.runtime_hub import scoped_event_log
from pipelex.system.pipe_run_mode import PipeRunMode
from pipelex.tracing.in_memory_event_log import InMemoryEventLog

_BUNDLE = """
domain      = "binding_graph"
description = "Acknowledging an invoice by its total, to draw the binding in the graph"
main_pipe   = "acknowledge_invoice"

[concept.Invoice]
description = "An invoice received from a supplier"

[concept.Invoice.structure]
total = { type = "number", description = "The amount due, in euros", required = true }
note  = { type = "text", description = "A note from the supplier, when there is one" }

[pipe.make_invoice]
type        = "PipeCompose"
description = "Writes out an invoice for an amount"
inputs      = { amount = "Number" }
output      = "Invoice"

[pipe.make_invoice.construct]
total = { from = "amount.number" }

[pipe.acknowledge_invoice]
type        = "PipeSequence"
description = "Makes an invoice, binds its total and its note, then writes the receipt"
inputs      = { amount = "Number" }
output      = "Text"
steps = [
  { pipe = "make_invoice", result = "invoice" },
  { from = "invoice.total", result = "total_amount" },
  { from = "invoice.note", result = "supplier_note" },
  { pipe = "write_receipt", result = "receipt" },
]

[pipe.write_receipt]
type        = "PipeCompose"
description = "Writes the receipt for an amount"
inputs      = { total_amount = "Number" }
output      = "Text"
template    = "Received: $total_amount euros"
"""


def _in_process_graph(teardown_spy: Any) -> GraphSpec:
    graphs = [graph for graph in teardown_spy.spy_return_list if isinstance(graph, GraphSpec)]
    assert len(graphs) == 1
    return graphs[0]


def _node(graph: GraphSpec, *, pipe_code: str) -> NodeSpec:
    nodes = [node for node in graph.nodes if node.pipe_code == pipe_code]
    assert len(nodes) == 1, f"expected one node for '{pipe_code}', got {[(node.kind, node.pipe_code) for node in graph.nodes]}"
    return nodes[0]


def _data_edges(graph: GraphSpec) -> set[tuple[str, str]]:
    return {(edge.source, edge.target) for edge in graph.edges if edge.kind == EdgeKind.DATA}


@pytest.mark.asyncio(loop_scope="class")
class TestBindingGraph:
    async def test_a_binding_is_a_node_producing_what_it_binds(self, mocker: MockerFixture) -> None:
        """The binding is a `binding` node fed by the root's producer, and the producer of the stuff it binds."""
        teardown_spy = mocker.spy(GraphTracer, "teardown")
        execution_config = get_config().interpreter.pipeline_execution.with_execution_overrides(generate_graph=True)
        runner = PipelexMTHDSProtocol(execution_config=execution_config, pipe_run_mode=PipeRunMode.LIVE)

        with scoped_event_log(InMemoryEventLog()):
            response = await runner.execute(mthds_contents=[_BUNDLE], inputs={"amount": {"concept": "native.Number", "content": {"number": 318}}})

        assert response.pipe_output.main_stuff.as_text.text == "Received: 318.0 euros"
        assembled_graph = response.pipe_output.graph_spec
        assert assembled_graph is not None
        in_process_graph = _in_process_graph(teardown_spy)

        for graph in (assembled_graph, in_process_graph):
            binding_node = _node(graph, pipe_code="invoice.total")
            assert binding_node.kind == NodeKind.BINDING
            assert binding_node.pipe_type == BINDING_NODE_PIPE_TYPE
            assert binding_node.status == NodeStatus.SUCCEEDED
            assert [io_spec.name for io_spec in binding_node.node_io.inputs] == ["invoice"]
            assert [io_spec.name for io_spec in binding_node.node_io.outputs] == ["total_amount"]
            assert [io_spec.concept for io_spec in binding_node.node_io.outputs] == ["Number"]

            producer_node = _node(graph, pipe_code="make_invoice")
            consumer_node = _node(graph, pipe_code="write_receipt")
            data_edges = _data_edges(graph)
            assert (producer_node.node_id, binding_node.node_id) in data_edges
            assert (binding_node.node_id, consumer_node.node_id) in data_edges
            assert (producer_node.node_id, consumer_node.node_id) not in data_edges

            note_node = _node(graph, pipe_code="invoice.note")
            assert note_node.kind == NodeKind.BINDING
            assert note_node.status == NodeStatus.SUCCEEDED
            assert note_node.node_io.outputs == []

    async def test_a_binding_failing_on_any_error_closes_its_node_as_failed(self, mocker: MockerFixture) -> None:
        """An error that is not a Pipelex one, such as a content failing its own validation, still closes the node."""
        mocker.patch("pipelex.pipe_controllers.binding.binding_step.bind_content", side_effect=ValueError("the content failed its validation"))
        teardown_spy = mocker.spy(GraphTracer, "teardown")
        execution_config = get_config().interpreter.pipeline_execution.with_execution_overrides(generate_graph=True)
        runner = PipelexMTHDSProtocol(execution_config=execution_config, pipe_run_mode=PipeRunMode.LIVE)

        with scoped_event_log(InMemoryEventLog()), pytest.raises(PipelexError):
            await runner.execute(mthds_contents=[_BUNDLE], inputs={"amount": {"concept": "native.Number", "content": {"number": 318}}})

        binding_node = _node(_in_process_graph(teardown_spy), pipe_code="invoice.total")
        assert binding_node.status == NodeStatus.FAILED
        assert binding_node.error is not None
        assert binding_node.error.error_type == "ValueError"
        assert binding_node.error.message == "the content failed its validation"
