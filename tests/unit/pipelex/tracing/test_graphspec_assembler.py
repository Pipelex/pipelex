"""Tests for GraphSpecAssembler."""

from datetime import UTC, datetime, timedelta
from typing import Any

from pipelex.graph.graphspec import EdgeKind, ErrorSpec, IOSpec, NodeKind, NodeStatus
from pipelex.tracing.graphspec_assembler import GraphSpecAssembler
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

# ---------------------------------------------------------------------------
# Shared test constants and helpers
# ---------------------------------------------------------------------------

_GRAPH_ID = "test_graph"
_PIPELINE_RUN_ID = "run_001"
_WF_A = "wf_a"
_WF_B = "wf_b"
_T0 = datetime(2025, 6, 15, 10, 0, 0, tzinfo=UTC)


def _time_at(seconds: int) -> datetime:
    """Create a timestamp offset from T0."""
    return _T0 + timedelta(seconds=seconds)


def _node_id(workflow_id: str, index: int) -> str:
    return f"{_GRAPH_ID}:{workflow_id}:node_{index}"


def _edge_id(workflow_id: str, index: int) -> str:
    return f"{_GRAPH_ID}:{workflow_id}:edge_{index}"


def _base(workflow_id: str, sequence: int, timestamp_offset: int = 0) -> dict[str, Any]:
    """Base fields for event construction."""
    return {
        "pipeline_run_id": _PIPELINE_RUN_ID,
        "workflow_id": workflow_id,
        "timestamp": _time_at(timestamp_offset or sequence),
        "sequence": sequence,
    }


def _io_spec(name: str, digest: str) -> IOSpec:
    return IOSpec(name=name, digest=digest)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestGraphSpecAssembler:
    """Tests for GraphSpecAssembler.assemble()."""

    def test_empty_events(self) -> None:
        """Empty event list produces empty GraphSpec."""
        result = GraphSpecAssembler.assemble(events=[], graph_id=_GRAPH_ID)
        assert result.graph_id == _GRAPH_ID
        assert result.nodes == []
        assert result.edges == []

    def test_registry_source_payloads_survive_assembly(self) -> None:
        """PipeStartEvent and PipeEndSuccessEvent registry payloads are copied unchanged."""
        pipe_source = "/fake/sourceful_pipe.mthds"
        input_concept_source = "/fake/input_concepts.mthds"
        output_concept_source = "/fake/output_concepts.mthds"
        node_id = _node_id(_WF_A, 0)

        result = GraphSpecAssembler.assemble(
            events=[
                PipeStartEvent(
                    **_base(_WF_A, 0),
                    node_id=node_id,
                    pipe_code="sourceful_pipe",
                    pipe_type="PipeLLM",
                    node_kind=NodeKind.OPERATOR,
                    domain_code="sourceful",
                    pipe_data={
                        "code": "sourceful_pipe",
                        "domain_code": "sourceful",
                        "type": "PipeLLM",
                        "source": pipe_source,
                    },
                    concept_data=[
                        {
                            "code": "InputConcept",
                            "domain_code": "sourceful",
                            "source": input_concept_source,
                        }
                    ],
                ),
                PipeEndSuccessEvent(
                    **_base(_WF_A, 1),
                    node_id=node_id,
                    ended_at=_time_at(1),
                    output_concept_data={
                        "code": "OutputConcept",
                        "domain_code": "sourceful",
                        "source": output_concept_source,
                    },
                ),
            ],
            graph_id=_GRAPH_ID,
        )

        assert result.pipe_registry["sourceful.sourceful_pipe"]["source"] == pipe_source
        assert result.concept_registry["sourceful.InputConcept"]["source"] == input_concept_source
        assert result.concept_registry["sourceful.OutputConcept"]["source"] == output_concept_source

    def test_simple_sequence(self) -> None:
        """3 child pipes in sequence under a parent.

        parent contains child_1, child_2, child_3.
        child_1 produces digest_a, child_2 consumes digest_a and produces digest_b,
        child_3 consumes digest_b.
        Expected: 4 SUCCEEDED nodes, 3 CONTAINS edges, 2 DATA edges.
        """
        parent = _node_id(_WF_A, 0)
        child_1 = _node_id(_WF_A, 1)
        child_2 = _node_id(_WF_A, 2)
        child_3 = _node_id(_WF_A, 3)

        events = [
            # Parent starts
            PipeStartEvent(
                **_base(_WF_A, 0),
                node_id=parent,
                pipe_code="sequence",
                pipe_type="PipeSequence",
                node_kind=NodeKind.CONTROLLER,
            ),
            # Child 1 starts
            PipeStartEvent(
                **_base(_WF_A, 1),
                node_id=child_1,
                parent_node_id=parent,
                pipe_code="gen_text",
                pipe_type="PipeLLM",
                node_kind=NodeKind.OPERATOR,
            ),
            # CONTAINS edge parent → child_1
            EdgeEvent(
                **_base(_WF_A, 2),
                edge_id=_edge_id(_WF_A, 0),
                source_node_id=parent,
                target_node_id=child_1,
                edge_kind=EdgeKind.CONTAINS,
            ),
            # Child 1 ends with output digest_a
            PipeEndSuccessEvent(
                **_base(_WF_A, 3),
                node_id=child_1,
                ended_at=_time_at(3),
                output_spec=_io_spec("output_text", "digest_a"),
            ),
            # Child 2 starts with input digest_a
            PipeStartEvent(
                **_base(_WF_A, 4),
                node_id=child_2,
                parent_node_id=parent,
                pipe_code="refine",
                pipe_type="PipeLLM",
                node_kind=NodeKind.OPERATOR,
                input_specs=[_io_spec("input_text", "digest_a")],
            ),
            # CONTAINS edge parent → child_2
            EdgeEvent(
                **_base(_WF_A, 5),
                edge_id=_edge_id(_WF_A, 1),
                source_node_id=parent,
                target_node_id=child_2,
                edge_kind=EdgeKind.CONTAINS,
            ),
            # Child 2 ends with output digest_b
            PipeEndSuccessEvent(
                **_base(_WF_A, 6),
                node_id=child_2,
                ended_at=_time_at(6),
                output_spec=_io_spec("refined_text", "digest_b"),
            ),
            # Child 3 starts with input digest_b
            PipeStartEvent(
                **_base(_WF_A, 7),
                node_id=child_3,
                parent_node_id=parent,
                pipe_code="format",
                pipe_type="PipeLLM",
                node_kind=NodeKind.OPERATOR,
                input_specs=[_io_spec("input_text", "digest_b")],
            ),
            # CONTAINS edge parent → child_3
            EdgeEvent(
                **_base(_WF_A, 8),
                edge_id=_edge_id(_WF_A, 2),
                source_node_id=parent,
                target_node_id=child_3,
                edge_kind=EdgeKind.CONTAINS,
            ),
            # Child 3 ends
            PipeEndSuccessEvent(
                **_base(_WF_A, 9),
                node_id=child_3,
                ended_at=_time_at(9),
                output_spec=_io_spec("formatted_text", "digest_c"),
            ),
            # Parent ends
            PipeEndSuccessEvent(
                **_base(_WF_A, 10),
                node_id=parent,
                ended_at=_time_at(10),
            ),
        ]

        result = GraphSpecAssembler.assemble(events=events, graph_id=_GRAPH_ID)

        # 4 nodes, all SUCCEEDED
        assert len(result.nodes) == 4
        for node in result.nodes:
            assert node.status == NodeStatus.SUCCEEDED

        # 3 CONTAINS edges + 2 DATA edges = 5 total
        contains_edges = [edge for edge in result.edges if edge.kind == EdgeKind.CONTAINS]
        data_edges = [edge for edge in result.edges if edge.kind == EdgeKind.DATA]

        assert len(contains_edges) == 3
        assert len(data_edges) == 2

        # DATA edges: child_1 → child_2 (digest_a), child_2 → child_3 (digest_b)
        data_edge_pairs = {(edge.source, edge.target) for edge in data_edges}
        assert (child_1, child_2) in data_edge_pairs
        assert (child_2, child_3) in data_edge_pairs

    def test_parallel_branches(self) -> None:
        """Controller + 2 branch pipes → PARALLEL_COMBINE edges."""
        controller = _node_id(_WF_A, 0)
        branch_1 = _node_id(_WF_A, 1)
        branch_2 = _node_id(_WF_A, 2)

        events = [
            PipeStartEvent(
                **_base(_WF_A, 0),
                node_id=controller,
                pipe_code="parallel",
                pipe_type="PipeParallel",
                node_kind=NodeKind.CONTROLLER,
            ),
            PipeStartEvent(
                **_base(_WF_A, 1),
                node_id=branch_1,
                parent_node_id=controller,
                pipe_code="branch_a",
                pipe_type="PipeLLM",
                node_kind=NodeKind.OPERATOR,
            ),
            EdgeEvent(
                **_base(_WF_A, 2),
                edge_id=_edge_id(_WF_A, 0),
                source_node_id=controller,
                target_node_id=branch_1,
                edge_kind=EdgeKind.CONTAINS,
            ),
            PipeEndSuccessEvent(
                **_base(_WF_A, 3),
                node_id=branch_1,
                ended_at=_time_at(3),
                output_spec=_io_spec("branch_out", "digest_branch_1"),
            ),
            PipeStartEvent(
                **_base(_WF_A, 4),
                node_id=branch_2,
                parent_node_id=controller,
                pipe_code="branch_b",
                pipe_type="PipeLLM",
                node_kind=NodeKind.OPERATOR,
            ),
            EdgeEvent(
                **_base(_WF_A, 5),
                edge_id=_edge_id(_WF_A, 1),
                source_node_id=controller,
                target_node_id=branch_2,
                edge_kind=EdgeKind.CONTAINS,
            ),
            PipeEndSuccessEvent(
                **_base(_WF_A, 6),
                node_id=branch_2,
                ended_at=_time_at(6),
                output_spec=_io_spec("branch_out", "digest_branch_2"),
            ),
            # ParallelCombine with snapshotted branch producers
            ParallelCombineEvent(
                **_base(_WF_A, 7),
                combined_stuff_code="digest_combined",
                branch_stuff_codes=["digest_branch_1", "digest_branch_2"],
                parallel_controller_node_id=controller,
                branch_producer_node_ids=[
                    ("digest_branch_1", branch_1),
                    ("digest_branch_2", branch_2),
                ],
            ),
            # Controller registers combined output (overrides producer map)
            ControllerOutputEvent(
                **_base(_WF_A, 8),
                node_id=controller,
                output_spec=_io_spec("combined_out", "digest_combined"),
            ),
            PipeEndSuccessEvent(
                **_base(_WF_A, 9),
                node_id=controller,
                ended_at=_time_at(9),
            ),
        ]

        result = GraphSpecAssembler.assemble(events=events, graph_id=_GRAPH_ID)

        parallel_edges = [edge for edge in result.edges if edge.kind == EdgeKind.PARALLEL_COMBINE]
        assert len(parallel_edges) == 2

        parallel_pairs = {(edge.source, edge.target) for edge in parallel_edges}
        assert (branch_1, controller) in parallel_pairs
        assert (branch_2, controller) in parallel_pairs

    def test_batch_fan_out_fan_in(self) -> None:
        """Batch controller + 2 items → BATCH_ITEM + BATCH_AGGREGATE edges."""
        controller = _node_id(_WF_A, 0)
        branch_0 = _node_id(_WF_A, 1)
        branch_1 = _node_id(_WF_A, 2)

        events = [
            PipeStartEvent(
                **_base(_WF_A, 0),
                node_id=controller,
                pipe_code="batch",
                pipe_type="PipeBatch",
                node_kind=NodeKind.CONTROLLER,
                input_specs=[_io_spec("input_list", "digest_list")],
            ),
            # Register batch item extractions
            BatchItemEvent(
                **_base(_WF_A, 1),
                list_stuff_code="digest_list",
                item_stuff_code="digest_item_0",
                item_index=0,
                batch_controller_node_id=controller,
            ),
            BatchItemEvent(
                **_base(_WF_A, 2),
                list_stuff_code="digest_list",
                item_stuff_code="digest_item_1",
                item_index=1,
                batch_controller_node_id=controller,
            ),
            # Branch 0 processes item 0
            PipeStartEvent(
                **_base(_WF_A, 3),
                node_id=branch_0,
                parent_node_id=controller,
                pipe_code="process",
                pipe_type="PipeLLM",
                node_kind=NodeKind.OPERATOR,
                input_specs=[_io_spec("item", "digest_item_0")],
            ),
            EdgeEvent(
                **_base(_WF_A, 4),
                edge_id=_edge_id(_WF_A, 0),
                source_node_id=controller,
                target_node_id=branch_0,
                edge_kind=EdgeKind.CONTAINS,
            ),
            PipeEndSuccessEvent(
                **_base(_WF_A, 5),
                node_id=branch_0,
                ended_at=_time_at(5),
                output_spec=_io_spec("result", "digest_result_0"),
            ),
            # Branch 1 processes item 1
            PipeStartEvent(
                **_base(_WF_A, 6),
                node_id=branch_1,
                parent_node_id=controller,
                pipe_code="process",
                pipe_type="PipeLLM",
                node_kind=NodeKind.OPERATOR,
                input_specs=[_io_spec("item", "digest_item_1")],
            ),
            EdgeEvent(
                **_base(_WF_A, 7),
                edge_id=_edge_id(_WF_A, 1),
                source_node_id=controller,
                target_node_id=branch_1,
                edge_kind=EdgeKind.CONTAINS,
            ),
            PipeEndSuccessEvent(
                **_base(_WF_A, 8),
                node_id=branch_1,
                ended_at=_time_at(8),
                output_spec=_io_spec("result", "digest_result_1"),
            ),
            # Register batch aggregations
            BatchAggregateEvent(
                **_base(_WF_A, 9),
                output_list_stuff_code="digest_output_list",
                item_stuff_code="digest_result_0",
                item_index=0,
                batch_controller_node_id=controller,
            ),
            BatchAggregateEvent(
                **_base(_WF_A, 10),
                output_list_stuff_code="digest_output_list",
                item_stuff_code="digest_result_1",
                item_index=1,
                batch_controller_node_id=controller,
            ),
            # Controller ends
            PipeEndSuccessEvent(
                **_base(_WF_A, 11),
                node_id=controller,
                ended_at=_time_at(11),
                output_spec=_io_spec("output_list", "digest_output_list"),
            ),
        ]

        result = GraphSpecAssembler.assemble(events=events, graph_id=_GRAPH_ID)

        batch_item_edges = [edge for edge in result.edges if edge.kind == EdgeKind.BATCH_ITEM]
        batch_agg_edges = [edge for edge in result.edges if edge.kind == EdgeKind.BATCH_AGGREGATE]

        # 2 BATCH_ITEM edges: controller → branch_0, controller → branch_1
        assert len(batch_item_edges) == 2
        batch_item_pairs = {(edge.source, edge.target) for edge in batch_item_edges}
        assert (controller, branch_0) in batch_item_pairs
        assert (controller, branch_1) in batch_item_pairs

        # 2 BATCH_AGGREGATE edges: branch_0 → controller, branch_1 → controller
        assert len(batch_agg_edges) == 2
        batch_agg_pairs = {(edge.source, edge.target) for edge in batch_agg_edges}
        assert (branch_0, controller) in batch_agg_pairs
        assert (branch_1, controller) in batch_agg_pairs

    def test_condition_selected_outcome(self) -> None:
        """Condition pipe with SELECTED_OUTCOME edge."""
        condition = _node_id(_WF_A, 0)
        outcome = _node_id(_WF_A, 1)

        events = [
            PipeStartEvent(
                **_base(_WF_A, 0),
                node_id=condition,
                pipe_code="check",
                pipe_type="PipeCondition",
                node_kind=NodeKind.CONTROLLER,
            ),
            PipeStartEvent(
                **_base(_WF_A, 1),
                node_id=outcome,
                parent_node_id=condition,
                pipe_code="branch_true",
                pipe_type="PipeLLM",
                node_kind=NodeKind.OPERATOR,
            ),
            EdgeEvent(
                **_base(_WF_A, 2),
                edge_id=_edge_id(_WF_A, 0),
                source_node_id=condition,
                target_node_id=outcome,
                edge_kind=EdgeKind.CONTAINS,
            ),
            EdgeEvent(
                **_base(_WF_A, 3),
                edge_id=_edge_id(_WF_A, 1),
                source_node_id=condition,
                target_node_id=outcome,
                edge_kind=EdgeKind.SELECTED_OUTCOME,
                label="true",
            ),
            PipeEndSuccessEvent(
                **_base(_WF_A, 4),
                node_id=outcome,
                ended_at=_time_at(4),
            ),
            PipeEndSuccessEvent(
                **_base(_WF_A, 5),
                node_id=condition,
                ended_at=_time_at(5),
            ),
        ]

        result = GraphSpecAssembler.assemble(events=events, graph_id=_GRAPH_ID)

        selected_edges = [edge for edge in result.edges if edge.kind == EdgeKind.SELECTED_OUTCOME]
        assert len(selected_edges) == 1
        assert selected_edges[0].source == condition
        assert selected_edges[0].target == outcome
        assert selected_edges[0].label == "true"

    def test_partial_failure(self) -> None:
        """Child fails with error, parent has no end event → FAILED + CANCELED."""
        parent = _node_id(_WF_A, 0)
        child = _node_id(_WF_A, 1)

        events = [
            PipeStartEvent(
                **_base(_WF_A, 0),
                node_id=parent,
                pipe_code="sequence",
                pipe_type="PipeSequence",
                node_kind=NodeKind.CONTROLLER,
            ),
            PipeStartEvent(
                **_base(_WF_A, 1),
                node_id=child,
                parent_node_id=parent,
                pipe_code="gen_text",
                pipe_type="PipeLLM",
                node_kind=NodeKind.OPERATOR,
            ),
            EdgeEvent(
                **_base(_WF_A, 2),
                edge_id=_edge_id(_WF_A, 0),
                source_node_id=parent,
                target_node_id=child,
                edge_kind=EdgeKind.CONTAINS,
            ),
            PipeEndErrorEvent(
                **_base(_WF_A, 3),
                node_id=child,
                ended_at=_time_at(3),
                error=ErrorSpec(
                    error_type="LLMError",
                    message="Model returned an error",
                ),
            ),
            # No end event for parent
        ]

        result = GraphSpecAssembler.assemble(events=events, graph_id=_GRAPH_ID)

        nodes_by_id = {node.node_id: node for node in result.nodes}
        assert nodes_by_id[child].status == NodeStatus.FAILED
        child_error = nodes_by_id[child].error
        assert child_error is not None
        assert child_error.error_type == "LLMError"
        assert nodes_by_id[parent].status == NodeStatus.CANCELED

    def test_multiple_workflows(self) -> None:
        """Events from two workflows assemble into one graph."""
        node_a0 = _node_id(_WF_A, 0)
        node_b0 = _node_id(_WF_B, 0)

        events = [
            # wf_a events (sorted first alphabetically)
            PipeStartEvent(
                **_base(_WF_A, 0),
                node_id=node_a0,
                pipe_code="pipe_a",
                pipe_type="PipeLLM",
                node_kind=NodeKind.OPERATOR,
            ),
            PipeEndSuccessEvent(
                **_base(_WF_A, 1),
                node_id=node_a0,
                ended_at=_time_at(1),
                output_spec=_io_spec("output", "digest_from_a"),
            ),
            # wf_b events (sorted second)
            PipeStartEvent(
                **_base(_WF_B, 0),
                node_id=node_b0,
                pipe_code="pipe_b",
                pipe_type="PipeLLM",
                node_kind=NodeKind.OPERATOR,
                input_specs=[_io_spec("input", "digest_from_a")],
            ),
            PipeEndSuccessEvent(
                **_base(_WF_B, 1),
                node_id=node_b0,
                ended_at=_time_at(3),
            ),
        ]

        result = GraphSpecAssembler.assemble(events=events, graph_id=_GRAPH_ID)

        assert len(result.nodes) == 2
        data_edges = [edge for edge in result.edges if edge.kind == EdgeKind.DATA]
        assert len(data_edges) == 1
        assert data_edges[0].source == node_a0
        assert data_edges[0].target == node_b0

    def test_cross_workflow_producer_map(self) -> None:
        """Producer in alphabetically-later workflow, consumer in earlier.

        wf_a consumes digest_x (events come first in sorted order).
        wf_b produces digest_x (events come second).
        Two-pass algorithm builds complete producer map in Pass 1
        before generating DATA edges in Pass 2.
        """
        consumer = _node_id(_WF_A, 0)
        producer = _node_id(_WF_B, 0)

        events = [
            # wf_a: consumer (sorted first)
            PipeStartEvent(
                **_base(_WF_A, 0),
                node_id=consumer,
                pipe_code="consumer_pipe",
                pipe_type="PipeLLM",
                node_kind=NodeKind.OPERATOR,
                input_specs=[_io_spec("input", "digest_x")],
            ),
            PipeEndSuccessEvent(
                **_base(_WF_A, 1),
                node_id=consumer,
                ended_at=_time_at(5),
            ),
            # wf_b: producer (sorted second)
            PipeStartEvent(
                **_base(_WF_B, 0),
                node_id=producer,
                pipe_code="producer_pipe",
                pipe_type="PipeLLM",
                node_kind=NodeKind.OPERATOR,
            ),
            PipeEndSuccessEvent(
                **_base(_WF_B, 1),
                node_id=producer,
                ended_at=_time_at(3),
                output_spec=_io_spec("output", "digest_x"),
            ),
        ]

        result = GraphSpecAssembler.assemble(events=events, graph_id=_GRAPH_ID)

        data_edges = [edge for edge in result.edges if edge.kind == EdgeKind.DATA]
        assert len(data_edges) == 1
        assert data_edges[0].source == producer
        assert data_edges[0].target == consumer

    def test_pass_through_detection(self) -> None:
        """Output digest matching input digest is not registered as producer."""
        passthrough = _node_id(_WF_A, 0)
        downstream = _node_id(_WF_A, 1)

        events = [
            # Pass-through pipe: input digest_a → output digest_a (same)
            PipeStartEvent(
                **_base(_WF_A, 0),
                node_id=passthrough,
                pipe_code="passthrough",
                pipe_type="PipeParallel",
                node_kind=NodeKind.CONTROLLER,
                input_specs=[_io_spec("main_input", "digest_a")],
            ),
            PipeEndSuccessEvent(
                **_base(_WF_A, 1),
                node_id=passthrough,
                ended_at=_time_at(1),
                output_spec=_io_spec("main_output", "digest_a"),  # Same digest = pass-through
            ),
            # Downstream pipe consumes digest_a
            PipeStartEvent(
                **_base(_WF_A, 2),
                node_id=downstream,
                pipe_code="consumer",
                pipe_type="PipeLLM",
                node_kind=NodeKind.OPERATOR,
                input_specs=[_io_spec("input", "digest_a")],
            ),
            PipeEndSuccessEvent(
                **_base(_WF_A, 3),
                node_id=downstream,
                ended_at=_time_at(3),
            ),
        ]

        result = GraphSpecAssembler.assemble(events=events, graph_id=_GRAPH_ID)

        # No DATA edge from passthrough → downstream because passthrough didn't register as producer
        data_edges = [edge for edge in result.edges if edge.kind == EdgeKind.DATA]
        assert len(data_edges) == 0

        # Verify passthrough node has no output_specs (pass-through was skipped)
        passthrough_node = next(node for node in result.nodes if node.node_id == passthrough)
        assert len(passthrough_node.node_io.outputs) == 0

    def test_pipe_start_description_and_domain_code_propagate_to_node_spec(self) -> None:
        node = _node_id(_WF_A, 0)
        events = [
            PipeStartEvent(
                **_base(_WF_A, 0),
                node_id=node,
                pipe_code="summarize",
                pipe_type="PipeLLM",
                node_kind=NodeKind.OPERATOR,
                description="Summarize the input document.",
                domain_code="summarization",
            ),
            PipeEndSuccessEvent(
                **_base(_WF_A, 1),
                node_id=node,
                ended_at=_time_at(1),
            ),
        ]

        result = GraphSpecAssembler.assemble(events=events, graph_id=_GRAPH_ID)

        assert len(result.nodes) == 1
        assembled_node = result.nodes[0]
        assert assembled_node.description == "Summarize the input document."
        assert assembled_node.domain_code == "summarization"

    def test_pipe_start_without_metadata_yields_none_on_node_spec(self) -> None:
        node = _node_id(_WF_A, 0)
        events = [
            PipeStartEvent(
                **_base(_WF_A, 0),
                node_id=node,
                pipe_code="noop",
                pipe_type="PipeLLM",
                node_kind=NodeKind.OPERATOR,
            ),
            PipeEndSuccessEvent(
                **_base(_WF_A, 1),
                node_id=node,
                ended_at=_time_at(1),
            ),
        ]

        result = GraphSpecAssembler.assemble(events=events, graph_id=_GRAPH_ID)

        assert len(result.nodes) == 1
        assembled_node = result.nodes[0]
        assert assembled_node.description is None
        assert assembled_node.domain_code is None
