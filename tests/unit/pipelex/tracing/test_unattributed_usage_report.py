"""Tests for the report of a run whose graph left usage unattributed (``pipelex.run.graph_incomplete``)."""

from datetime import UTC, datetime, timedelta
from typing import Any

from pydantic import ValidationError
from pytest_mock import MockerFixture

from pipelex import log
from pipelex.cogt.llm.llm_report import LLMTokensUsage
from pipelex.cogt.usage.cost_category import CostCategory, CostsByCategoryDict
from pipelex.cogt.usage.token_category import TokenCategory
from pipelex.errors.problem import error_code_spec, problem_status_of
from pipelex.errors.registry.pipelex_codes import PipelexErrorCode
from pipelex.graph.graphspec import NodeKind
from pipelex.system.error_tracking.error_report import ErrorReportKind
from pipelex.system.error_tracking.error_tracking import install_error_trackers, installed_error_trackers, reaches_error_trackers
from pipelex.system.job_metadata import JobCategory, JobMetadata, RunMetadata, UnitJobId
from pipelex.system.pipe_run_mode import PipeRunMode
from pipelex.test_extras.recording_error_tracker import recording_error_tracker
from pipelex.tracing import unattributed_usage_report as unattributed_usage_report_module
from pipelex.tracing.graphspec_assembler import GraphSpecAssembler
from pipelex.tracing.trace_events import UNATTRIBUTED_NODE_ID, PipeEndSuccessEvent, PipeStartEvent, TraceEvent, UsageReportEvent
from pipelex.tracing.unattributed_usage_report import REPORTED_NODE_IDS_LIMIT

_PIPELINE_RUN_ID = "run_incomplete"
_REQUEST_ID = "req_incomplete"
_WORKFLOW_ID = "wf_a"
_T0 = datetime(2025, 6, 15, 10, 0, 0, tzinfo=UTC)
_RATES: CostsByCategoryDict = {CostCategory.INPUT: 3.0, CostCategory.OUTPUT: 15.0}
# 100 input tokens at $3 per million and 50 output tokens at $15 per million: $0.00105, 1050 millionths of a dollar.
_MICRO_USD_OF_ONE_CALL = 1050
# What a run's content would leak through if the report quoted it: the pipe, the model, the prompt's owner.
_RUN_CONTENT_MARKERS = ("secret_pipe", "secret-model", "user_secret")

_LLM_NODE_ID = f"{_PIPELINE_RUN_ID}:{_WORKFLOW_ID}:node_llm"
_GHOST_NODE_ID = f"{_PIPELINE_RUN_ID}:wf_lost:node_ghost"
_OTHER_GHOST_NODE_ID = f"{_PIPELINE_RUN_ID}:wf_lost:node_another"


def _base(sequence: int) -> dict[str, Any]:
    return {
        "pipeline_run_id": _PIPELINE_RUN_ID,
        "workflow_id": _WORKFLOW_ID,
        "attempt": 1,
        "lineage": [],
        "path": None,
        "timestamp": _T0 + timedelta(seconds=sequence),
        "sequence": sequence,
        "mode": PipeRunMode.LIVE,
    }


def _usage_event(*, sequence: int, node_id: str) -> UsageReportEvent:
    usage = LLMTokensUsage(
        job_metadata=JobMetadata(
            run_metadata=RunMetadata(storage_scope="test/scope", read_scope=None, user_id="user_secret", pipeline_run_id=_PIPELINE_RUN_ID),
            pipe_code="secret_pipe",
            unit_job_id=UnitJobId.LLM_GEN_TEXT,
            job_category=JobCategory.LLM_JOB,
        ),
        inference_model_name="secret-model",
        inference_model_id="secret-model-id",
        unit_costs=_RATES,
        nb_tokens_by_category={TokenCategory.INPUT: 100, TokenCategory.OUTPUT: 50},
    )
    return UsageReportEvent(**_base(sequence), node_id=node_id, tokens_usage=usage)


def _one_node_run() -> list[TraceEvent]:
    """A run of one LLM node that started, ran one call and ended."""
    return [
        PipeStartEvent(
            pipe_ref=None,
            **_base(0),
            node_id=_LLM_NODE_ID,
            parent_node_id=None,
            pipe_code="secret_pipe",
            pipe_type="PipeLLM",
            node_kind=NodeKind.OPERATOR,
        ),
        _usage_event(sequence=1, node_id=_LLM_NODE_ID),
        PipeEndSuccessEvent(
            pipe_code="secret_pipe", pipe_ref=None, pipe_type="PipeLLM", **_base(2), node_id=_LLM_NODE_ID, ended_at=_T0 + timedelta(seconds=2)
        ),
    ]


def _run_with_lost_starts() -> list[TraceEvent]:
    """The run, plus two calls made by a node whose start event was lost and one by another such node."""
    return [
        *_one_node_run(),
        _usage_event(sequence=3, node_id=_GHOST_NODE_ID),
        _usage_event(sequence=4, node_id=_GHOST_NODE_ID),
        _usage_event(sequence=5, node_id=_OTHER_GHOST_NODE_ID),
    ]


class TestUnattributedUsageReport:
    def test_a_graph_with_nodes_that_never_started_is_reported_once_with_its_ids_and_no_content(self) -> None:
        with recording_error_tracker() as recorder, log.context(request_id=_REQUEST_ID, pipeline_run_id=_PIPELINE_RUN_ID):
            graph_spec = GraphSpecAssembler.assemble(events=_run_with_lost_starts(), graph_id=_PIPELINE_RUN_ID)

        assert graph_spec.usage is not None
        assert graph_spec.usage.unattributed.inference_calls == 3
        assert len(recorder.reports) == 1
        report = recorder.reports[0]
        assert report.kind == ErrorReportKind.HANDLED
        assert report.code == PipelexErrorCode.RUN_GRAPH_INCOMPLETE
        assert report.exception is None
        assert (report.pipeline_run_id, report.request_id) == (_PIPELINE_RUN_ID, _REQUEST_ID)
        assert report.problem.pipeline_run_id == _PIPELINE_RUN_ID
        assert report.problem.params is not None
        assert report.problem.params.as_wire() == {
            "node_ids": sorted([_GHOST_NODE_ID, _OTHER_GHOST_NODE_ID]),
            "node_count": 2,
            "inference_calls": 3,
            "cost_micro_usd": 3 * _MICRO_USD_OF_ONE_CALL,
        }
        assert report.problem.location is None
        assert report.problem.diagnostics is None
        assert report.pipe_code is None
        wire = str(report.problem.to_wire())
        for marker in _RUN_CONTENT_MARKERS:
            assert marker not in wire

    def test_a_complete_graph_is_not_reported(self) -> None:
        with recording_error_tracker() as recorder:
            graph_spec = GraphSpecAssembler.assemble(events=_one_node_run(), graph_id=_PIPELINE_RUN_ID)

        assert graph_spec.usage is not None
        assert graph_spec.usage.unattributed.inference_calls == 0
        assert recorder.reports == []

    def test_usage_outside_any_pipe_is_unattributed_but_not_reported(self) -> None:
        """The fallback node id names no node that went missing, so the graph is not incomplete."""
        events = [*_one_node_run(), _usage_event(sequence=3, node_id=UNATTRIBUTED_NODE_ID)]

        with recording_error_tracker() as recorder:
            graph_spec = GraphSpecAssembler.assemble(events=events, graph_id=_PIPELINE_RUN_ID)

        assert graph_spec.usage is not None
        assert graph_spec.usage.unattributed.inference_calls == 1
        assert recorder.reports == []

    def test_the_report_names_a_bounded_number_of_nodes_and_counts_them_all(self) -> None:
        node_count = REPORTED_NODE_IDS_LIMIT + 5
        ghost_ids = [f"{_PIPELINE_RUN_ID}:wf_lost:node_{index_node:03d}" for index_node in range(node_count)]
        events = [*_one_node_run(), *(_usage_event(sequence=3 + index_node, node_id=ghost_id) for index_node, ghost_id in enumerate(ghost_ids))]

        with recording_error_tracker() as recorder:
            GraphSpecAssembler.assemble(events=events, graph_id=_PIPELINE_RUN_ID)

        assert len(recorder.reports) == 1
        params = recorder.reports[0].problem.params
        assert params is not None
        wire_params = params.as_wire()
        assert wire_params["node_ids"] == ghost_ids[:REPORTED_NODE_IDS_LIMIT]
        assert wire_params["node_count"] == node_count

    def test_with_no_tracker_installed_the_assembly_is_unchanged(self, mocker: MockerFixture) -> None:
        previous_trackers = installed_error_trackers()
        install_error_trackers(trackers=[])
        warning_spy = mocker.spy(log, "warning")
        make_problem_spy = mocker.spy(unattributed_usage_report_module, "make_problem")
        try:
            bare_graph = GraphSpecAssembler.assemble(events=_run_with_lost_starts(), graph_id=_PIPELINE_RUN_ID)
        finally:
            install_error_trackers(trackers=previous_trackers)
        make_problem_spy.assert_not_called()
        warned_node_ids = [call.kwargs["fields"]["node_id"] for call in warning_spy.call_args_list if "never started" in call.args[0]]
        assert warned_node_ids == [_GHOST_NODE_ID, _OTHER_GHOST_NODE_ID]

        with recording_error_tracker():
            tracked_graph = GraphSpecAssembler.assemble(events=_run_with_lost_starts(), graph_id=_PIPELINE_RUN_ID)
        assert bare_graph.model_dump() == tracked_graph.model_dump()

    def test_a_report_that_cannot_be_built_never_fails_the_assembly(self, mocker: MockerFixture) -> None:
        validation_error = ValidationError.from_exception_data(title="RunGraphIncompleteParams", line_errors=[])
        mocker.patch.object(unattributed_usage_report_module, "make_problem", side_effect=validation_error)

        with recording_error_tracker() as recorder:
            graph_spec = GraphSpecAssembler.assemble(events=_run_with_lost_starts(), graph_id=_PIPELINE_RUN_ID)

        assert graph_spec.usage is not None
        assert graph_spec.usage.unattributed.inference_calls == 3
        assert recorder.reports == []

    def test_the_code_is_an_operator_fault_the_error_trackers_admit(self) -> None:
        spec = error_code_spec(PipelexErrorCode.RUN_GRAPH_INCOMPLETE)

        assert spec.status is not None
        assert reaches_error_trackers(status=spec.status, domain=spec.domain)

    def test_the_reported_problem_is_weighed_as_a_server_fault(self) -> None:
        with recording_error_tracker() as recorder:
            GraphSpecAssembler.assemble(events=_run_with_lost_starts(), graph_id=_PIPELINE_RUN_ID)

        assert problem_status_of(problem=recorder.reports[0].problem) == 500
