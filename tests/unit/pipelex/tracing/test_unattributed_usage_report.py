"""Tests for the report of a run whose graph left usage unattributed (``pipelex.run.graph_incomplete``)."""

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from pydantic import ValidationError
from pytest_mock import MockerFixture

from pipelex import log
from pipelex.cogt.llm.llm_report import LLMTokensUsage
from pipelex.cogt.usage.cost_category import CostCategory, CostsByCategoryDict
from pipelex.cogt.usage.token_category import TokenCategory
from pipelex.errors.problem import error_code_spec, problem_status_of
from pipelex.errors.registry.pipelex_codes import PipelexErrorCode
from pipelex.graph.graphspec import GraphSpecMode, NodeKind
from pipelex.pipe_run import pipe_run as pipe_run_module
from pipelex.pipe_run.pipe_run import PipeRun
from pipelex.pipe_run.tracing_assembly import RunTraceEvents, TracingAssembly, assemble_tracing
from pipelex.system.data_inclusion_config import DataInclusionConfig
from pipelex.system.error_tracking.error_report import ErrorReportKind
from pipelex.system.error_tracking.error_tracking import install_error_trackers, installed_error_trackers, reaches_error_trackers
from pipelex.system.execution_chain import make_direct_chain
from pipelex.system.job_metadata import JobCategory, JobMetadata, RunMetadata, UnitJobId
from pipelex.system.pipe_run_mode import PipeRunMode
from pipelex.system.trace_context import TraceContext
from pipelex.test_extras.recording_error_tracker import recording_error_tracker
from pipelex.tracing import unattributed_usage_report as unattributed_usage_report_module
from pipelex.tracing.graphspec_assembler import GraphSpecAssembler
from pipelex.tracing.trace_events import UNATTRIBUTED_NODE_ID, PipeEndSuccessEvent, PipeStartEvent, TraceEvent, UsageReportEvent
from pipelex.tracing.unattributed_usage_report import REPORTED_NODE_IDS_LIMIT, report_unattributed_usage

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


def _base(sequence: int, mode: PipeRunMode = PipeRunMode.LIVE) -> dict[str, Any]:
    return {
        "pipeline_run_id": _PIPELINE_RUN_ID,
        "workflow_id": _WORKFLOW_ID,
        "attempt": 1,
        "lineage": [],
        "path": None,
        "timestamp": _T0 + timedelta(seconds=sequence),
        "sequence": sequence,
        "mode": mode,
    }


def _usage_event(*, sequence: int, node_id: str, mode: PipeRunMode = PipeRunMode.LIVE) -> UsageReportEvent:
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
    return UsageReportEvent(**_base(sequence, mode), node_id=node_id, tokens_usage=usage)


def _one_node_run(mode: PipeRunMode = PipeRunMode.LIVE) -> list[TraceEvent]:
    """A run of one LLM node that started, ran one call and ended."""
    return [
        PipeStartEvent(
            pipe_ref=None,
            **_base(0, mode),
            node_id=_LLM_NODE_ID,
            parent_node_id=None,
            pipe_code="secret_pipe",
            pipe_type="PipeLLM",
            node_kind=NodeKind.OPERATOR,
        ),
        _usage_event(sequence=1, node_id=_LLM_NODE_ID, mode=mode),
        PipeEndSuccessEvent(
            pipe_code="secret_pipe",
            pipe_ref=None,
            pipe_type="PipeLLM",
            **_base(2, mode),
            node_id=_LLM_NODE_ID,
            ended_at=_T0 + timedelta(seconds=2),
        ),
    ]


def _run_with_lost_starts(mode: PipeRunMode = PipeRunMode.LIVE) -> list[TraceEvent]:
    """The run, plus two calls made by a node whose start event was lost and one by another such node."""
    return [
        *_one_node_run(mode),
        _usage_event(sequence=3, node_id=_GHOST_NODE_ID, mode=mode),
        _usage_event(sequence=4, node_id=_GHOST_NODE_ID, mode=mode),
        _usage_event(sequence=5, node_id=_OTHER_GHOST_NODE_ID, mode=mode),
    ]


def _assemble_and_report(*, events: list[TraceEvent], reports_incomplete_graph: bool = True) -> TracingAssembly:
    """The run's tracing assembly from ``events``, as a caller reporting the run's incomplete graph runs it."""
    return assemble_tracing(
        pipeline_run_id=_PIPELINE_RUN_ID,
        assemble_graph=True,
        assemble_usage=False,
        trace_events=RunTraceEvents(events=events, read_error=None),
        reports_incomplete_graph=reports_incomplete_graph,
    )


def _router_and_job(*, mocker: MockerFixture, run_mode: PipeRunMode) -> tuple[Any, Any]:
    """A router whose run succeeds and a job tracing its graph, carrying the run's ids and its run mode."""
    job = mocker.MagicMock()
    job.pipe.code = "secret_pipe"
    job.pipe.domain_code = "secret_domain"
    job.pipe_run_params.run_mode = run_mode
    job.job_metadata = JobMetadata(
        run_metadata=RunMetadata(
            user_id="pytest", pipeline_run_id=_PIPELINE_RUN_ID, storage_scope="test/scope", read_scope=None, request_id=_REQUEST_ID
        ),
        trace_context=TraceContext(
            graph_id=_PIPELINE_RUN_ID,
            data_inclusion=DataInclusionConfig(stuff_json_content=False, error_stack_traces=False, pipe_and_concept_registry=False),
            emit_graph_events=True,
            emit_usage_events=False,
            describe_pipe_io=False,
            run_mode=run_mode,
            chain=make_direct_chain(),
        ),
    )
    pipe_output = mocker.MagicMock()
    pipe_output.job_metadata = job.job_metadata
    router = mocker.AsyncMock()
    router.run = mocker.AsyncMock(return_value=pipe_output)
    return router, job


class TestUnattributedUsageReport:
    def test_a_graph_with_nodes_that_never_started_is_reported_once_with_its_ids_and_no_content(self) -> None:
        with recording_error_tracker() as recorder, log.context(request_id=_REQUEST_ID, pipeline_run_id=_PIPELINE_RUN_ID):
            assembly = _assemble_and_report(events=_run_with_lost_starts())

        assert assembly.graph_spec is not None
        assert assembly.graph_spec.usage is not None
        assert assembly.graph_spec.usage.unattributed.inference_calls == 3
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

    def test_the_assembler_reports_nothing_and_returns_the_nodes_that_never_started(self) -> None:
        """The assembler is pure: whether an incomplete graph is reported is the run's policy, which its caller applies."""
        with recording_error_tracker() as recorder:
            graph_spec = GraphSpecAssembler.assemble(events=_run_with_lost_starts(), graph_id=_PIPELINE_RUN_ID)
            assembled = GraphSpecAssembler.assemble_with_never_started_usage(events=_run_with_lost_starts(), graph_id=_PIPELINE_RUN_ID)

        assert recorder.reports == []
        assert graph_spec.model_dump() == assembled.graph_spec.model_dump()
        assert assembled.mode == GraphSpecMode.LIVE
        assert {node_id: len(usages) for node_id, usages in assembled.usages_by_never_started_node.items()} == {
            _GHOST_NODE_ID: 2,
            _OTHER_GHOST_NODE_ID: 1,
        }

    def test_a_tracing_assembly_not_asked_to_report_reports_nothing(self) -> None:
        """The default, which code that must stay free of side effects, such as a durable workflow's own, relies on."""
        with recording_error_tracker() as recorder:
            assembly = _assemble_and_report(events=_run_with_lost_starts(), reports_incomplete_graph=False)

        assert assembly.graph_spec is not None
        assert recorder.reports == []

    def test_a_dry_run_s_graph_is_not_reported_even_when_asked(self) -> None:
        """A caller that does not know the run's mode, such as a durable-execution activity, still holds the dry-run rule."""
        with recording_error_tracker() as recorder:
            assembly = _assemble_and_report(events=_run_with_lost_starts(PipeRunMode.DRY))

        assert assembly.graph_spec is not None
        assert assembly.graph_spec.usage is not None
        assert assembly.graph_spec.usage.unattributed.inference_calls == 3
        assert recorder.reports == []

    def test_a_complete_graph_is_not_reported(self) -> None:
        with recording_error_tracker() as recorder:
            assembly = _assemble_and_report(events=_one_node_run())

        assert assembly.graph_spec is not None
        assert assembly.graph_spec.usage is not None
        assert assembly.graph_spec.usage.unattributed.inference_calls == 0
        assert recorder.reports == []

    def test_usage_outside_any_pipe_is_unattributed_but_not_reported(self) -> None:
        """The fallback node id names no node that went missing, so the graph is not incomplete."""
        events = [*_one_node_run(), _usage_event(sequence=3, node_id=UNATTRIBUTED_NODE_ID)]

        with recording_error_tracker() as recorder:
            assembly = _assemble_and_report(events=events)

        assert assembly.graph_spec is not None
        assert assembly.graph_spec.usage is not None
        assert assembly.graph_spec.usage.unattributed.inference_calls == 1
        assert recorder.reports == []

    def test_the_report_names_a_bounded_number_of_nodes_and_counts_them_all(self) -> None:
        node_count = REPORTED_NODE_IDS_LIMIT + 5
        ghost_ids = [f"{_PIPELINE_RUN_ID}:wf_lost:node_{index_node:03d}" for index_node in range(node_count)]
        events = [*_one_node_run(), *(_usage_event(sequence=3 + index_node, node_id=ghost_id) for index_node, ghost_id in enumerate(ghost_ids))]

        with recording_error_tracker() as recorder:
            _assemble_and_report(events=events)

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
            bare_assembly = _assemble_and_report(events=_run_with_lost_starts())
        finally:
            install_error_trackers(trackers=previous_trackers)
        make_problem_spy.assert_not_called()
        warned_node_ids = [call.kwargs["fields"]["node_id"] for call in warning_spy.call_args_list if "never started" in call.args[0]]
        assert warned_node_ids == [_GHOST_NODE_ID, _OTHER_GHOST_NODE_ID]

        with recording_error_tracker():
            tracked_assembly = _assemble_and_report(events=_run_with_lost_starts())
        assert bare_assembly.model_dump() == tracked_assembly.model_dump()

    def test_a_report_that_cannot_be_built_never_fails_the_assembly(self, mocker: MockerFixture) -> None:
        validation_error = ValidationError.from_exception_data(title="RunGraphIncompleteParams", line_errors=[])
        mocker.patch.object(unattributed_usage_report_module, "make_problem", side_effect=validation_error)

        with recording_error_tracker() as recorder:
            assembly = _assemble_and_report(events=_run_with_lost_starts())

        assert assembly.graph_assembly_error is None
        assert assembly.graph_spec is not None
        assert assembly.graph_spec.usage is not None
        assert assembly.graph_spec.usage.unattributed.inference_calls == 3
        assert recorder.reports == []

    def test_a_cost_that_cannot_be_summed_never_fails_the_report_s_caller(self, mocker: MockerFixture) -> None:
        """The usage total and its cost conversion are inside the guard, not only the problem's validation."""
        mocker.patch.object(unattributed_usage_report_module, "make_self_contained_spec", side_effect=OverflowError("cost overflow"))
        assembled = GraphSpecAssembler.assemble_with_never_started_usage(events=_run_with_lost_starts(), graph_id=_PIPELINE_RUN_ID)

        with recording_error_tracker() as recorder:
            report_unattributed_usage(pipeline_run_id=_PIPELINE_RUN_ID, usages_by_never_started_node=assembled.usages_by_never_started_node)

        assert recorder.reports == []

    def test_a_cost_too_large_to_scale_is_left_out_of_the_report(self, mocker: MockerFixture) -> None:
        """A finite cost that overflows to infinity once scaled to micro-USD is dropped from the report, never raised."""
        assembled = GraphSpecAssembler.assemble_with_never_started_usage(events=_run_with_lost_starts(), graph_id=_PIPELINE_RUN_ID)
        huge_usage_spec = unattributed_usage_report_module.make_self_contained_spec(
            [usage for usages in assembled.usages_by_never_started_node.values() for usage in usages]
        ).model_copy(update={"cost": 1e305})
        mocker.patch.object(unattributed_usage_report_module, "make_self_contained_spec", return_value=huge_usage_spec)

        with recording_error_tracker() as recorder:
            report_unattributed_usage(pipeline_run_id=_PIPELINE_RUN_ID, usages_by_never_started_node=assembled.usages_by_never_started_node)

        (report,) = recorder.reports
        assert report.problem.params is not None
        assert "cost_micro_usd" not in report.problem.params.as_wire()

    def test_the_code_is_an_operator_fault_the_error_trackers_admit(self) -> None:
        spec = error_code_spec(PipelexErrorCode.RUN_GRAPH_INCOMPLETE)

        assert spec.status is not None
        assert reaches_error_trackers(status=spec.status, domain=spec.domain)

    def test_the_reported_problem_is_weighed_as_a_server_fault(self) -> None:
        with recording_error_tracker() as recorder:
            _assemble_and_report(events=_run_with_lost_starts())

        assert problem_status_of(problem=recorder.reports[0].problem) == 500


@pytest.mark.asyncio(loop_scope="class")
class TestPipeRunIncompleteGraphReport:
    """The run's boundary applies its own reporting policy to its incomplete graph, as it does to its failure."""

    async def test_a_live_run_reports_its_incomplete_graph_exactly_once(self, mocker: MockerFixture) -> None:
        router, job = _router_and_job(mocker=mocker, run_mode=PipeRunMode.LIVE)
        mocker.patch.object(pipe_run_module, "read_run_trace_events", return_value=RunTraceEvents(events=_run_with_lost_starts(), read_error=None))

        with recording_error_tracker() as recorder:
            await PipeRun(pipe_router=router, reports_usage_stats=False).run(pipe_job=job)

        (report,) = recorder.reports
        assert report.code == PipelexErrorCode.RUN_GRAPH_INCOMPLETE
        assert (report.pipeline_run_id, report.request_id) == (_PIPELINE_RUN_ID, _REQUEST_ID)

    async def test_a_dry_run_reports_nothing(self, mocker: MockerFixture) -> None:
        router, job = _router_and_job(mocker=mocker, run_mode=PipeRunMode.DRY)
        mocker.patch.object(
            pipe_run_module, "read_run_trace_events", return_value=RunTraceEvents(events=_run_with_lost_starts(PipeRunMode.DRY), read_error=None)
        )
        assemble_spy = mocker.spy(pipe_run_module, "assemble_tracing_on_output")

        with recording_error_tracker() as recorder:
            await PipeRun(pipe_router=router, reports_usage_stats=False).run(pipe_job=job)

        assert recorder.reports == []
        assert assemble_spy.call_args.kwargs["reports_incomplete_graph"] is False

    async def test_a_validation_s_run_reports_nothing(self, mocker: MockerFixture) -> None:
        """A validation runs its pipes with `reports_errors=False`; a live trace proves the policy, not the mode, decides."""
        router, job = _router_and_job(mocker=mocker, run_mode=PipeRunMode.LIVE)
        mocker.patch.object(pipe_run_module, "read_run_trace_events", return_value=RunTraceEvents(events=_run_with_lost_starts(), read_error=None))

        with recording_error_tracker() as recorder:
            await PipeRun(pipe_router=router, reports_usage_stats=False, reports_errors=False).run(pipe_job=job)

        assert recorder.reports == []
