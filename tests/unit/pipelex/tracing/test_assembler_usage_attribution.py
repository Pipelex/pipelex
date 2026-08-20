"""Tests for usage attribution inside GraphSpecAssembler (NodeUsageSpec invariant 1, the run total)."""

import math
from datetime import UTC, datetime, timedelta
from typing import Any

from pipelex.cogt.llm.llm_report import LLMTokensUsage
from pipelex.cogt.usage.cost_category import CostCategory, CostsByCategoryDict
from pipelex.cogt.usage.token_category import TokenCategory
from pipelex.graph.graphspec import GraphSpec, NodeKind, NodeSpec
from pipelex.reporting.reporting_types import AnyTokensUsage
from pipelex.system.job_metadata import JobCategory, JobMetadata, RunMetadata, UnitJobId
from pipelex.tracing.graphspec_assembler import GraphSpecAssembler
from pipelex.tracing.trace_events import (
    UNATTRIBUTED_NODE_ID,
    PipeEndSuccessEvent,
    PipeStartEvent,
    TraceEvent,
    UsageReportEvent,
)

_GRAPH_ID = "usage_graph"
_PIPELINE_RUN_ID = "run_001"
_WORKFLOW_ID = "wf_a"
_T0 = datetime(2025, 6, 15, 10, 0, 0, tzinfo=UTC)

_RATES: CostsByCategoryDict = {CostCategory.INPUT: 3.0, CostCategory.OUTPUT: 15.0}
_UNRATED: CostsByCategoryDict = {}
_COST_OF_ONE_RATED_CALL = 100 * 3.0 / 1_000_000 + 50 * 15.0 / 1_000_000

_CONTROLLER_NODE_ID = f"{_GRAPH_ID}:{_WORKFLOW_ID}:node_ctrl"
_LLM_NODE_ID = f"{_GRAPH_ID}:{_WORKFLOW_ID}:node_llm"
_FUNC_NODE_ID = f"{_GRAPH_ID}:{_WORKFLOW_ID}:node_func"


def _base(sequence: int) -> dict[str, Any]:
    return {
        "pipeline_run_id": _PIPELINE_RUN_ID,
        "workflow_id": _WORKFLOW_ID,
        "timestamp": _T0 + timedelta(seconds=sequence),
        "sequence": sequence,
    }


def _make_usage(*, unit_costs: CostsByCategoryDict, model_name: str = "test-model") -> AnyTokensUsage:
    return LLMTokensUsage(
        job_metadata=JobMetadata(
            run_metadata=RunMetadata(storage_scope="test/scope", user_id="user_test", pipeline_run_id=_PIPELINE_RUN_ID),
            pipe_code="test_pipe",
            unit_job_id=UnitJobId.LLM_GEN_TEXT,
            job_category=JobCategory.LLM_JOB,
        ),
        inference_model_name=model_name,
        inference_model_id=f"{model_name}-id",
        unit_costs=unit_costs,
        nb_tokens_by_category={TokenCategory.INPUT: 100, TokenCategory.OUTPUT: 50},
    )


def _pipe_start(*, sequence: int, node_id: str, parent_node_id: str | None, node_kind: NodeKind, pipe_type: str) -> PipeStartEvent:
    return PipeStartEvent(
        **_base(sequence),
        node_id=node_id,
        parent_node_id=parent_node_id,
        pipe_code="test_pipe",
        pipe_type=pipe_type,
        node_kind=node_kind,
    )


def _pipe_end(*, sequence: int, node_id: str) -> PipeEndSuccessEvent:
    return PipeEndSuccessEvent(**_base(sequence), node_id=node_id, ended_at=_T0 + timedelta(seconds=sequence))


def _usage_event(*, sequence: int, node_id: str, unit_costs: CostsByCategoryDict, model_name: str = "test-model") -> UsageReportEvent:
    return UsageReportEvent(
        **_base(sequence),
        node_id=node_id,
        tokens_usage=_make_usage(unit_costs=unit_costs, model_name=model_name),
    )


def _skeleton_events() -> list[TraceEvent]:
    """A controller with one LLM child and one inference-free child, all completed."""
    return [
        _pipe_start(
            sequence=0,
            node_id=_CONTROLLER_NODE_ID,
            parent_node_id=None,
            node_kind=NodeKind.CONTROLLER,
            pipe_type="PipeSequence",
        ),
        _pipe_start(
            sequence=1,
            node_id=_LLM_NODE_ID,
            parent_node_id=_CONTROLLER_NODE_ID,
            node_kind=NodeKind.OPERATOR,
            pipe_type="PipeLLM",
        ),
        _pipe_end(sequence=2, node_id=_LLM_NODE_ID),
        _pipe_start(
            sequence=3,
            node_id=_FUNC_NODE_ID,
            parent_node_id=_CONTROLLER_NODE_ID,
            node_kind=NodeKind.OPERATOR,
            pipe_type="PipeFunc",
        ),
        _pipe_end(sequence=4, node_id=_FUNC_NODE_ID),
        _pipe_end(sequence=5, node_id=_CONTROLLER_NODE_ID),
    ]


def _node_by_id(graph_spec: GraphSpec, *, node_id: str) -> NodeSpec:
    return next(node for node in graph_spec.nodes if node.node_id == node_id)


def _is_close(actual: float | None, *, expected: float) -> bool:
    return actual is not None and math.isclose(actual, expected, rel_tol=1e-9)


class TestAssemblerUsageAttribution:
    """Tests for GraphSpecAssembler usage folding, rollup and totals."""

    def test_invariant_1_no_usage_event_leaves_every_node_none(self) -> None:
        """No usage in the stream: the graph and every node read as "not collected"."""
        graph_spec = GraphSpecAssembler.assemble(events=_skeleton_events(), graph_id=_GRAPH_ID)

        assert graph_spec.usage is None
        assert all(node.usage is None for node in graph_spec.nodes)

    def test_invariant_1_one_usage_event_gives_every_node_a_spec(self) -> None:
        """One usage event: the controller and the inference-free child are zeroed, not None."""
        events = [*_skeleton_events(), _usage_event(sequence=6, node_id=_LLM_NODE_ID, unit_costs=_RATES)]

        graph_spec = GraphSpecAssembler.assemble(events=events, graph_id=_GRAPH_ID)

        assert all(node.usage is not None for node in graph_spec.nodes)
        func_usage = _node_by_id(graph_spec, node_id=_FUNC_NODE_ID).usage
        assert func_usage is not None
        assert func_usage.inference_calls == 0
        assert func_usage.subtree_inference_calls == 0
        assert func_usage.cost is None

    def test_own_usage_lands_on_the_node_that_reported_it(self) -> None:
        """The LLM node carries its own call; the controller carries none of its own."""
        events = [*_skeleton_events(), _usage_event(sequence=6, node_id=_LLM_NODE_ID, unit_costs=_RATES)]

        graph_spec = GraphSpecAssembler.assemble(events=events, graph_id=_GRAPH_ID)

        llm_usage = _node_by_id(graph_spec, node_id=_LLM_NODE_ID).usage
        assert llm_usage is not None
        assert llm_usage.inference_calls == 1
        assert llm_usage.rated_inference_calls == 1
        assert llm_usage.total_tokens == 150
        assert _is_close(llm_usage.cost, expected=_COST_OF_ONE_RATED_CALL)

        controller_usage = _node_by_id(graph_spec, node_id=_CONTROLLER_NODE_ID).usage
        assert controller_usage is not None
        assert controller_usage.inference_calls == 0
        assert controller_usage.cost is None

    def test_subtree_rolls_up_to_the_controller(self) -> None:
        """The controller reports its children's tokens and cost as its subtree."""
        events = [
            *_skeleton_events(),
            _usage_event(sequence=6, node_id=_LLM_NODE_ID, unit_costs=_RATES),
            _usage_event(sequence=7, node_id=_LLM_NODE_ID, unit_costs=_RATES),
        ]

        graph_spec = GraphSpecAssembler.assemble(events=events, graph_id=_GRAPH_ID)

        controller_usage = _node_by_id(graph_spec, node_id=_CONTROLLER_NODE_ID).usage
        assert controller_usage is not None
        assert controller_usage.subtree_inference_calls == 2
        assert controller_usage.subtree_total_tokens == 300
        assert _is_close(controller_usage.subtree_cost, expected=2 * _COST_OF_ONE_RATED_CALL)

    def test_unrated_usage_keeps_cost_none_all_the_way_up(self) -> None:
        """A dry/mock run has tokens and no dollar — at the node and at the controller."""
        events = [*_skeleton_events(), _usage_event(sequence=6, node_id=_LLM_NODE_ID, unit_costs=_UNRATED)]

        graph_spec = GraphSpecAssembler.assemble(events=events, graph_id=_GRAPH_ID)

        llm_usage = _node_by_id(graph_spec, node_id=_LLM_NODE_ID).usage
        controller_usage = _node_by_id(graph_spec, node_id=_CONTROLLER_NODE_ID).usage
        assert llm_usage is not None
        assert controller_usage is not None
        assert llm_usage.cost is None
        assert llm_usage.total_tokens == 150
        assert controller_usage.subtree_cost is None
        assert controller_usage.subtree_total_tokens == 150

    def test_unattributed_node_id_goes_to_the_graph_bucket(self) -> None:
        """Usage emitted outside any pipe context is surfaced, not dropped."""
        events = [
            *_skeleton_events(),
            _usage_event(sequence=6, node_id=UNATTRIBUTED_NODE_ID, unit_costs=_RATES),
        ]

        graph_spec = GraphSpecAssembler.assemble(events=events, graph_id=_GRAPH_ID)

        assert graph_spec.usage is not None
        assert graph_spec.usage.unattributed.inference_calls == 1
        assert _is_close(graph_spec.usage.unattributed.cost, expected=_COST_OF_ONE_RATED_CALL)
        assert all(node.usage is not None and node.usage.inference_calls == 0 for node in graph_spec.nodes)

    def test_usage_for_a_node_that_never_started_goes_to_the_graph_bucket(self) -> None:
        """A node_id with no PipeStartEvent still counts toward the run total."""
        events = [
            *_skeleton_events(),
            _usage_event(sequence=6, node_id="graph:wf_other:node_ghost", unit_costs=_RATES),
        ]

        graph_spec = GraphSpecAssembler.assemble(events=events, graph_id=_GRAPH_ID)

        assert graph_spec.usage is not None
        assert graph_spec.usage.unattributed.inference_calls == 1
        assert graph_spec.usage.total.inference_calls == 1

    def test_run_total_covers_attributed_and_unattributed_usage(self) -> None:
        """graph.usage.total is what the cost report's own total must agree with."""
        events = [
            *_skeleton_events(),
            _usage_event(sequence=6, node_id=_LLM_NODE_ID, unit_costs=_RATES),
            _usage_event(sequence=7, node_id=UNATTRIBUTED_NODE_ID, unit_costs=_RATES),
        ]

        graph_spec = GraphSpecAssembler.assemble(events=events, graph_id=_GRAPH_ID)

        assert graph_spec.usage is not None
        assert graph_spec.usage.total.inference_calls == 2
        assert graph_spec.usage.total.total_tokens == 300
        assert _is_close(graph_spec.usage.total.cost, expected=2 * _COST_OF_ONE_RATED_CALL)

        own_calls = sum(node.usage.inference_calls for node in graph_spec.nodes if node.usage is not None)
        assert graph_spec.usage.total.inference_calls == own_calls + graph_spec.usage.unattributed.inference_calls

    def test_usage_event_read_before_the_node_started_still_attributes(self) -> None:
        """Cross-worker ordering can put usage first; attribution waits for pass 2."""
        events: list[TraceEvent] = [
            _usage_event(sequence=0, node_id=_LLM_NODE_ID, unit_costs=_RATES),
            *_skeleton_events(),
        ]

        graph_spec = GraphSpecAssembler.assemble(events=events, graph_id=_GRAPH_ID)

        assert graph_spec.usage is not None
        assert graph_spec.usage.unattributed.inference_calls == 0
        llm_usage = _node_by_id(graph_spec, node_id=_LLM_NODE_ID).usage
        assert llm_usage is not None
        assert llm_usage.inference_calls == 1

    def test_usage_survives_the_graphspec_json_roundtrip(self) -> None:
        """The assembled usage is wire-stable, cost=None included."""
        events = [
            *_skeleton_events(),
            _usage_event(sequence=6, node_id=_LLM_NODE_ID, unit_costs=_UNRATED),
        ]
        graph_spec = GraphSpecAssembler.assemble(events=events, graph_id=_GRAPH_ID)

        restored = GraphSpec.model_validate_json(graph_spec.to_json())

        assert restored.usage is not None
        assert restored.usage.total.cost is None
        assert restored.usage.total.inference_calls == 1
        llm_usage = _node_by_id(restored, node_id=_LLM_NODE_ID).usage
        assert llm_usage is not None
        assert llm_usage.cost is None
        assert llm_usage.total_tokens == 150

    def test_by_model_records_the_models_that_actually_ran(self) -> None:
        """The graph's only record of the model that RAN, as opposed to the one requested."""
        events = [
            *_skeleton_events(),
            _usage_event(sequence=6, node_id=_LLM_NODE_ID, unit_costs=_RATES, model_name="claude-4.6-sonnet"),
            _usage_event(sequence=7, node_id=_LLM_NODE_ID, unit_costs=_RATES, model_name="structurer"),
        ]

        graph_spec = GraphSpecAssembler.assemble(events=events, graph_id=_GRAPH_ID)

        llm_usage = _node_by_id(graph_spec, node_id=_LLM_NODE_ID).usage
        assert llm_usage is not None
        assert [entry.inference_model_name for entry in llm_usage.by_model] == ["claude-4.6-sonnet", "structurer"]
        assert [entry.inference_model_id for entry in llm_usage.by_model] == ["claude-4.6-sonnet-id", "structurer-id"]

        # The controller carries none of its own but reports the branch's models.
        controller_usage = _node_by_id(graph_spec, node_id=_CONTROLLER_NODE_ID).usage
        assert controller_usage is not None
        assert controller_usage.by_model == []
        assert {entry.inference_model_name for entry in controller_usage.subtree_by_model} == {
            "claude-4.6-sonnet",
            "structurer",
        }
