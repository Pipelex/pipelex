"""Equivalence tests: compare GraphTracer teardown output with GraphSpecAssembler output.

Runs identical tracing scenarios through both paths:
- Path A: GraphTracer in direct mode (no event log) → teardown() → GraphSpec
- Path B: GraphTracer with InMemoryEventLog → read events → GraphSpecAssembler.assemble() → GraphSpec

The two GraphSpecs must be structurally identical (same nodes, edges, statuses, data flow),
allowing for normalized IDs (workflow_id segment stripped) and ignored TimingSpec.
"""

import re
from datetime import UTC, datetime, timedelta
from typing import Any, Callable

import pytest

from pipelex.graph.graph_tracer import GraphTracer
from pipelex.graph.graphspec import EdgeKind, EdgeSpec, GraphSpec, IOSpec, NodeKind, NodeSpec
from pipelex.system.trace_context import TraceContext
from pipelex.tracing.graphspec_assembler import GraphSpecAssembler
from pipelex.tracing.in_memory_event_log import InMemoryEventLog
from tests.unit.pipelex.graph.conftest import make_defaulted_data_inclusion_config

# ---------------------------------------------------------------------------
# Shared constants
# ---------------------------------------------------------------------------

_GRAPH_ID = "equiv_graph"
_PIPELINE_RUN_ID = "equiv_run_001"
_WORKFLOW_ID = "wf_equiv"
_T0 = datetime(2025, 6, 15, 10, 0, 0, tzinfo=UTC)

# ---------------------------------------------------------------------------
# Structural comparison helpers
# ---------------------------------------------------------------------------

# Pattern to strip the workflow_id segment from node/edge IDs:
# "graph_id:wf_xxx:node_0" → "graph_id:node_0"
_WF_SEGMENT_RE = re.compile(r":" + re.escape(_WORKFLOW_ID) + r":")


def _normalize_id(identifier: str) -> str:
    """Strip the workflow_id segment from a node or edge ID."""
    return _WF_SEGMENT_RE.sub(":", identifier)


def _normalize_node(node: NodeSpec) -> dict[str, Any]:
    """Extract structurally comparable fields from a NodeSpec, ignoring timing."""
    return {
        "node_id": _normalize_id(node.node_id),
        "kind": node.kind,
        "pipe_code": node.pipe_code,
        "pipe_type": node.pipe_type,
        "status": node.status,
        "error_type": node.error.error_type if node.error else None,
        "error_message": node.error.message if node.error else None,
        "metrics": node.metrics,
        "inputs": sorted(
            [(spec.name, spec.digest) for spec in node.node_io.inputs],
            key=lambda pair: (pair[0] or "", pair[1] or ""),
        ),
        "outputs": sorted(
            [(spec.name, spec.digest) for spec in node.node_io.outputs],
            key=lambda pair: (pair[0] or "", pair[1] or ""),
        ),
    }


def _normalize_edge(edge: EdgeSpec) -> tuple[str, str, EdgeKind, str | None]:
    """Extract structurally comparable fields from an EdgeSpec."""
    return (
        _normalize_id(edge.source),
        _normalize_id(edge.target),
        edge.kind,
        edge.label,
    )


def _assert_graphs_equivalent(direct_spec: GraphSpec, assembled_spec: GraphSpec) -> None:
    """Assert two GraphSpecs are structurally equivalent.

    Compares nodes and edges with normalized IDs and without timing information.
    """
    # Compare nodes by normalized ID
    direct_normalized = [_normalize_node(node) for node in direct_spec.nodes]
    direct_nodes = {normalized["node_id"]: normalized for normalized in direct_normalized}
    assembled_normalized = [_normalize_node(node) for node in assembled_spec.nodes]
    assembled_nodes = {normalized["node_id"]: normalized for normalized in assembled_normalized}

    assert set(direct_nodes.keys()) == set(assembled_nodes.keys()), (
        f"Node ID mismatch.\n"
        f"Direct only: {set(direct_nodes.keys()) - set(assembled_nodes.keys())}\n"
        f"Assembled only: {set(assembled_nodes.keys()) - set(direct_nodes.keys())}"
    )

    for node_id, direct_node in direct_nodes.items():
        assert direct_node == assembled_nodes[node_id], f"Node {node_id} differs.\nDirect:    {direct_node}\nAssembled: {assembled_nodes[node_id]}"

    # Compare edges as sets (order doesn't matter)
    direct_edges = {_normalize_edge(edge) for edge in direct_spec.edges}
    assembled_edges = {_normalize_edge(edge) for edge in assembled_spec.edges}

    assert direct_edges == assembled_edges, (
        f"Edge mismatch.\nDirect only: {direct_edges - assembled_edges}\nAssembled only: {assembled_edges - direct_edges}"
    )


# ---------------------------------------------------------------------------
# Scenario runners: execute the same scenario through both paths
# ---------------------------------------------------------------------------

# A scenario is a callable that takes a GraphTracer and its initial TraceContext,
# and exercises a tracing scenario on it.
ScenarioFn = Callable[[GraphTracer, TraceContext], None]


def _run_both_paths(scenario: ScenarioFn) -> tuple[GraphSpec, GraphSpec]:
    """Run a scenario through both direct and event-log paths, return both GraphSpecs."""
    data_inclusion = make_defaulted_data_inclusion_config()

    # Path A: direct mode (no event log)
    tracer_direct = GraphTracer()
    ctx_direct = tracer_direct.setup(graph_id=_GRAPH_ID, data_inclusion=data_inclusion)
    scenario(tracer_direct, ctx_direct)
    direct_spec = tracer_direct.teardown()
    assert direct_spec is not None

    # Path B: event log mode
    event_log = InMemoryEventLog()
    tracer_event = GraphTracer()
    ctx_event = tracer_event.setup(
        graph_id=_GRAPH_ID,
        data_inclusion=data_inclusion,
        event_log=event_log,
        workflow_id=_WORKFLOW_ID,
        pipeline_run_id=_PIPELINE_RUN_ID,
    )
    scenario(tracer_event, ctx_event)
    # Don't call teardown on the event-log tracer — we want to assemble from events
    # But we do need to let the tracer flush remaining state
    tracer_event.teardown()

    events = event_log.read_events(_PIPELINE_RUN_ID)
    assembled_spec = GraphSpecAssembler.assemble(events=events, graph_id=_GRAPH_ID)

    return direct_spec, assembled_spec


# ---------------------------------------------------------------------------
# Scenarios
# ---------------------------------------------------------------------------


def _scenario_simple_sequence(tracer: GraphTracer, context: TraceContext) -> None:
    """3 child pipes in sequence under a parent controller."""
    started_at = _T0

    # Parent controller
    parent_id, child_ctx = tracer.on_pipe_start(
        trace_context=context,
        pipe_code="sequence",
        pipe_type="PipeSequence",
        node_kind=NodeKind.CONTROLLER,
        started_at=started_at,
    )

    # Child 1: produces digest_a
    child1_id, _ = tracer.on_pipe_start(
        trace_context=child_ctx,
        pipe_code="gen_text",
        pipe_type="PipeLLM",
        node_kind=NodeKind.OPERATOR,
        started_at=started_at + timedelta(seconds=1),
    )
    tracer.on_pipe_end_success(
        node_id=child1_id,
        ended_at=started_at + timedelta(seconds=2),
        output_spec=IOSpec(name="output_text", digest="digest_a"),
    )

    # Child 2: consumes digest_a, produces digest_b
    child2_id, _ = tracer.on_pipe_start(
        trace_context=child_ctx,
        pipe_code="refine",
        pipe_type="PipeLLM",
        node_kind=NodeKind.OPERATOR,
        started_at=started_at + timedelta(seconds=3),
        input_specs=[IOSpec(name="input_text", digest="digest_a")],
    )
    tracer.on_pipe_end_success(
        node_id=child2_id,
        ended_at=started_at + timedelta(seconds=4),
        output_spec=IOSpec(name="refined_text", digest="digest_b"),
    )

    # Child 3: consumes digest_b
    child3_id, _ = tracer.on_pipe_start(
        trace_context=child_ctx,
        pipe_code="format",
        pipe_type="PipeLLM",
        node_kind=NodeKind.OPERATOR,
        started_at=started_at + timedelta(seconds=5),
        input_specs=[IOSpec(name="input_text", digest="digest_b")],
    )
    tracer.on_pipe_end_success(
        node_id=child3_id,
        ended_at=started_at + timedelta(seconds=6),
        output_spec=IOSpec(name="formatted_text", digest="digest_c"),
    )

    # Parent ends
    tracer.on_pipe_end_success(
        node_id=parent_id,
        ended_at=started_at + timedelta(seconds=7),
    )


def _scenario_parallel_branches(tracer: GraphTracer, context: TraceContext) -> None:
    """Controller with 2 branch pipes producing PARALLEL_COMBINE edges."""
    started_at = _T0

    ctrl_id, ctrl_ctx = tracer.on_pipe_start(
        trace_context=context,
        pipe_code="parallel",
        pipe_type="PipeParallel",
        node_kind=NodeKind.CONTROLLER,
        started_at=started_at,
    )

    # Branch A
    branch_a_id, _ = tracer.on_pipe_start(
        trace_context=ctrl_ctx,
        pipe_code="branch_a",
        pipe_type="PipeLLM",
        node_kind=NodeKind.OPERATOR,
        started_at=started_at + timedelta(seconds=1),
    )
    tracer.on_pipe_end_success(
        node_id=branch_a_id,
        ended_at=started_at + timedelta(seconds=2),
        output_spec=IOSpec(name="out_a", digest="digest_branch_a"),
    )

    # Branch B
    branch_b_id, _ = tracer.on_pipe_start(
        trace_context=ctrl_ctx,
        pipe_code="branch_b",
        pipe_type="PipeLLM",
        node_kind=NodeKind.OPERATOR,
        started_at=started_at + timedelta(seconds=1),
    )
    tracer.on_pipe_end_success(
        node_id=branch_b_id,
        ended_at=started_at + timedelta(seconds=3),
        output_spec=IOSpec(name="out_b", digest="digest_branch_b"),
    )

    # Register parallel combine (must happen before register_controller_output)
    tracer.register_parallel_combine(
        combined_stuff_code="digest_combined",
        branch_stuff_codes=["digest_branch_a", "digest_branch_b"],
        parallel_controller_node_id=ctrl_id,
    )

    # Register controller outputs (overrides producer map)
    tracer.register_controller_output(
        node_id=ctrl_id,
        output_spec=IOSpec(name="combined_a", digest="digest_branch_a"),
    )
    tracer.register_controller_output(
        node_id=ctrl_id,
        output_spec=IOSpec(name="combined_b", digest="digest_branch_b"),
    )

    # Controller ends
    tracer.on_pipe_end_success(
        node_id=ctrl_id,
        ended_at=started_at + timedelta(seconds=4),
        output_spec=IOSpec(name="combined_out", digest="digest_combined"),
    )


def _scenario_batch_fan_out_fan_in(tracer: GraphTracer, context: TraceContext) -> None:
    """Batch controller with item extraction and aggregation."""
    started_at = _T0

    ctrl_id, ctrl_ctx = tracer.on_pipe_start(
        trace_context=context,
        pipe_code="batch",
        pipe_type="PipeBatch",
        node_kind=NodeKind.CONTROLLER,
        started_at=started_at,
        input_specs=[IOSpec(name="input_list", digest="digest_list")],
    )

    # Register batch item extractions
    tracer.register_batch_item_extraction(
        list_stuff_code="digest_list",
        item_stuff_code="digest_item_0",
        item_index=0,
        batch_controller_node_id=ctrl_id,
    )
    tracer.register_batch_item_extraction(
        list_stuff_code="digest_list",
        item_stuff_code="digest_item_1",
        item_index=1,
        batch_controller_node_id=ctrl_id,
    )

    # Branch 0: processes item 0
    branch0_id, _ = tracer.on_pipe_start(
        trace_context=ctrl_ctx,
        pipe_code="process",
        pipe_type="PipeLLM",
        node_kind=NodeKind.OPERATOR,
        started_at=started_at + timedelta(seconds=1),
        input_specs=[IOSpec(name="item", digest="digest_item_0")],
    )
    tracer.on_pipe_end_success(
        node_id=branch0_id,
        ended_at=started_at + timedelta(seconds=2),
        output_spec=IOSpec(name="result", digest="digest_result_0"),
    )

    # Branch 1: processes item 1
    branch1_id, _ = tracer.on_pipe_start(
        trace_context=ctrl_ctx,
        pipe_code="process",
        pipe_type="PipeLLM",
        node_kind=NodeKind.OPERATOR,
        started_at=started_at + timedelta(seconds=1),
        input_specs=[IOSpec(name="item", digest="digest_item_1")],
    )
    tracer.on_pipe_end_success(
        node_id=branch1_id,
        ended_at=started_at + timedelta(seconds=3),
        output_spec=IOSpec(name="result", digest="digest_result_1"),
    )

    # Register batch aggregations
    tracer.register_batch_aggregation(
        output_list_stuff_code="digest_output_list",
        item_stuff_code="digest_result_0",
        item_index=0,
        batch_controller_node_id=ctrl_id,
    )
    tracer.register_batch_aggregation(
        output_list_stuff_code="digest_output_list",
        item_stuff_code="digest_result_1",
        item_index=1,
        batch_controller_node_id=ctrl_id,
    )

    # Controller ends
    tracer.on_pipe_end_success(
        node_id=ctrl_id,
        ended_at=started_at + timedelta(seconds=4),
        output_spec=IOSpec(name="output_list", digest="digest_output_list"),
    )


def _scenario_partial_failure(tracer: GraphTracer, context: TraceContext) -> None:
    """Child pipe fails, parent has no end event → FAILED + CANCELED nodes."""
    started_at = _T0

    _parent_id, child_ctx = tracer.on_pipe_start(
        trace_context=context,
        pipe_code="sequence",
        pipe_type="PipeSequence",
        node_kind=NodeKind.CONTROLLER,
        started_at=started_at,
    )

    child_id, _ = tracer.on_pipe_start(
        trace_context=child_ctx,
        pipe_code="gen_text",
        pipe_type="PipeLLM",
        node_kind=NodeKind.OPERATOR,
        started_at=started_at + timedelta(seconds=1),
    )

    tracer.on_pipe_end_error(
        node_id=child_id,
        ended_at=started_at + timedelta(seconds=2),
        error_type="LLMError",
        error_message="Model returned an error",
    )
    # Parent has no end event → will be marked CANCELED


def _scenario_pass_through(tracer: GraphTracer, context: TraceContext) -> None:
    """Pass-through output (same digest as input) is not registered as producer."""
    started_at = _T0

    # Pass-through pipe: input digest_a → output digest_a (same)
    pt_id, _ = tracer.on_pipe_start(
        trace_context=context,
        pipe_code="passthrough",
        pipe_type="PipeParallel",
        node_kind=NodeKind.CONTROLLER,
        started_at=started_at,
        input_specs=[IOSpec(name="main_input", digest="digest_a")],
    )
    tracer.on_pipe_end_success(
        node_id=pt_id,
        ended_at=started_at + timedelta(seconds=1),
        output_spec=IOSpec(name="main_output", digest="digest_a"),  # Same digest = pass-through
    )

    # Downstream pipe consumes digest_a
    down_id, _ = tracer.on_pipe_start(
        trace_context=context,
        pipe_code="consumer",
        pipe_type="PipeLLM",
        node_kind=NodeKind.OPERATOR,
        started_at=started_at + timedelta(seconds=2),
        input_specs=[IOSpec(name="input", digest="digest_a")],
    )
    tracer.on_pipe_end_success(
        node_id=down_id,
        ended_at=started_at + timedelta(seconds=3),
    )


def _scenario_condition_selected_outcome(tracer: GraphTracer, context: TraceContext) -> None:
    """Condition pipe with SELECTED_OUTCOME edge."""
    started_at = _T0

    cond_id, cond_ctx = tracer.on_pipe_start(
        trace_context=context,
        pipe_code="check",
        pipe_type="PipeCondition",
        node_kind=NodeKind.CONTROLLER,
        started_at=started_at,
    )

    outcome_id, _ = tracer.on_pipe_start(
        trace_context=cond_ctx,
        pipe_code="branch_true",
        pipe_type="PipeLLM",
        node_kind=NodeKind.OPERATOR,
        started_at=started_at + timedelta(seconds=1),
    )

    tracer.add_edge(
        source_node_id=cond_id,
        target_node_id=outcome_id,
        edge_kind=EdgeKind.SELECTED_OUTCOME,
        label="true",
    )

    tracer.on_pipe_end_success(
        node_id=outcome_id,
        ended_at=started_at + timedelta(seconds=2),
    )
    tracer.on_pipe_end_success(
        node_id=cond_id,
        ended_at=started_at + timedelta(seconds=3),
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestAssemblerEquivalence:
    """Equivalence tests comparing GraphTracer teardown with GraphSpecAssembler."""

    @pytest.mark.parametrize(
        "scenario_fn",
        [
            pytest.param(_scenario_simple_sequence, id="simple_sequence"),
            pytest.param(_scenario_parallel_branches, id="parallel_branches"),
            pytest.param(_scenario_batch_fan_out_fan_in, id="batch_fan_out_fan_in"),
            pytest.param(_scenario_partial_failure, id="partial_failure"),
            pytest.param(_scenario_pass_through, id="pass_through"),
            pytest.param(_scenario_condition_selected_outcome, id="condition_selected_outcome"),
        ],
    )
    def test_equivalence(self, scenario_fn: ScenarioFn) -> None:
        """GraphTracer teardown and GraphSpecAssembler produce structurally identical GraphSpecs."""
        direct_spec, assembled_spec = _run_both_paths(scenario_fn)
        _assert_graphs_equivalent(direct_spec, assembled_spec)
