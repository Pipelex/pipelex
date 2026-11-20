"""A pipe span opened in replayable workflow code is exported once, with its true start, across a replay.

An orchestrator such as Temporal runs a controller inline in its workflow code and re-executes that code from the
start when it replays the workflow, after an eviction or on another worker. The orchestrator lends pipelex the
workflow's deterministic sources through ``workflow_execution_slot``; here a fake workflow execution stands in for
it: a seeded random a replay reproduces, a clock the test moves as history does, a replaying flag, and the answer
Temporal's probe gives to ``is_unwinding``: an eviction unwinds, and so does an error that fails the workflow task,
one that is neither among the worker's failure types, which list ``PipelexError``, nor a cancellation. The provider is
Pipelex's own shape, with ``ReplaySafeIdGenerator`` as its id generator, exporting to memory, so what the memory holds
is what every exporter would have received.
"""

from __future__ import annotations

import asyncio
import logging
from random import Random
from typing import TYPE_CHECKING, Any

import pytest
from mthds.protocol.problem.registry import CoreCode
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.sdk.trace.id_generator import IdGenerator, RandomIdGenerator
from opentelemetry.trace import TraceState
from pydantic import Field
from typing_extensions import override

from pipelex.base_exceptions import PipelexError
from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory
from pipelex.core.pipes.pipe_output import PipeOutput
from pipelex.core.pipes.stuff_spec.stuff_spec import StuffSpec
from pipelex.pipe_machinery.pipe_abstract import PipeAbstract
from pipelex.pipe_run.pipe_run_params import PipeRunParams
from pipelex.system.job_metadata import JobMetadata, OtelContext, RunMetadata
from pipelex.system.pipe_run_mode import PipeRunMode
from pipelex.system.telemetry.otel_constants import OTelConstants, PipelexSpanAttr, SpanOutcome
from pipelex.system.telemetry.otel_factory import OtelFactory
from pipelex.system.telemetry.replay_safe_id_generator import ReplaySafeIdGenerator
from pipelex.system.telemetry.telemetry_manager_abstract import TelemetryManagerAbstract
from pipelex.system.telemetry.workflow_execution import WorkflowExecutionProtocol, get_workflow_execution, workflow_execution_slot
from pipelex.tools.typing.pydantic_utils import empty_list_factory_of

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

    from opentelemetry.sdk.trace import ReadableSpan
    from pytest_mock import MockerFixture

    from pipelex.core.memory.working_memory import WorkingMemory
    from pipelex.libraries.library_crate import LibraryCrate

PIPELINE_RUN_ID = "plr-replay-safe-spans"
WORKFLOW_SEED = 20261119
STARTED_AT_NS = 1_700_000_000_000_000_000
SECOND_TASK_AT_NS = STARTED_AT_NS + 5_000_000_000
LAST_TASK_AT_NS = STARTED_AT_NS + 9_000_000_000
HOST_SPAN_ID = 0x00000000000000AB
HOST_TRACE_STATE = "vendor=host"

PROBE_FAILED_WARNING = "A pipe's end was not counted: the workflow probe failed"


class WorkflowEviction(BaseException):
    """The exception an orchestrator tears a cached workflow's code down with, as Temporal does on an eviction."""


class PipeFailedError(PipelexError):
    """A pipe's own failure, which the worker lists among the errors that fail the workflow."""

    error_code = CoreCode.RUNTIME_UNEXPECTED


class ProbeOutOfWorkflowError(RuntimeError):
    """What a probe raises when asked from outside the workflow's event loop, as a torn-down workflow's code may be."""


class FakeWorkflowExecution:
    """One execution of a workflow's code, live or replaying, with the workflow's deterministic sources."""

    def __init__(self, *, is_replaying: bool) -> None:
        # A fresh generator from the workflow's seed, as each execution of the workflow on a worker gets.
        self._random = Random(WORKFLOW_SEED)
        self.now_ns = STARTED_AT_NS
        self.replaying = is_replaying

    def is_replaying(self) -> bool:
        return self.replaying

    def time_ns(self) -> int:
        return self.now_ns

    def random(self) -> Random:
        return self._random

    def is_unwinding(self, *, error: BaseException) -> bool:
        # Temporal's answer: an eviction, or an error that fails the workflow task, being neither one of the worker's
        # failure types, tested by isinstance wherever it is raised, nor a cancellation, which ends the workflow.
        if isinstance(error, WorkflowEviction):
            return True
        return not isinstance(error, (PipelexError, asyncio.CancelledError))


class TornDownWorkflowExecution(FakeWorkflowExecution):
    """A workflow execution whose code is being torn down: it answers that it unwinds, and every other question raises."""

    @override
    def is_replaying(self) -> bool:
        msg = "not in the workflow's event loop"
        raise ProbeOutOfWorkflowError(msg)

    @override
    def time_ns(self) -> int:
        msg = "not in the workflow's event loop"
        raise ProbeOutOfWorkflowError(msg)

    @override
    def is_unwinding(self, *, error: BaseException) -> bool:
        return True


class BrokenWorkflowExecution(FakeWorkflowExecution):
    """A probe that raises whatever it is asked about a pipe's end."""

    @override
    def is_unwinding(self, *, error: BaseException) -> bool:
        msg = "the probe broke"
        raise ProbeOutOfWorkflowError(msg)


class ScriptedPipe(PipeAbstract):
    """A controller whose live run takes its steps in order: a child pipe it runs, or a hook moving history along."""

    pipe_category: Any = "PipeController"
    type: Any = "PipeSequence"
    steps: list[Any] = Field(default_factory=list)
    seen_span_ids: list[int] = Field(default_factory=empty_list_factory_of(int))

    @override
    def validate_inputs_with_library(self) -> None: ...

    @override
    def validate_inputs_static(self) -> None: ...

    @override
    def validate_output_with_library(self) -> None: ...

    @override
    def validate_output_static(self) -> None: ...

    @override
    async def _validate_before_run(self, **kwargs: Any) -> None: ...

    @override
    async def _validate_after_run(self, **kwargs: Any) -> None: ...

    @override
    def required_variables(self) -> set[str]:
        return set()

    @override
    def needed_inputs(self, *, visited_pipes: set[str] | None = None) -> Any:
        return self.inputs

    @override
    async def _live_run_pipe(
        self,
        *,
        job_metadata: JobMetadata,
        working_memory: WorkingMemory,
        pipe_run_params: PipeRunParams,
        output_name: str | None = None,
        library_crate: LibraryCrate | None = None,
    ) -> PipeOutput:
        assert job_metadata.otel_context is not None
        self.seen_span_ids.append(job_metadata.otel_context.span_id)
        for step in self.steps:
            if isinstance(step, ScriptedPipe):
                await step.live_run_pipe(job_metadata=job_metadata, working_memory=working_memory, pipe_run_params=pipe_run_params)
            else:
                step()
        return PipeOutput(working_memory=working_memory, pipeline_run_id=job_metadata.run_metadata.pipeline_run_id)

    @override
    async def _dry_run_pipe(
        self,
        *,
        job_metadata: JobMetadata,
        working_memory: WorkingMemory,
        pipe_run_params: PipeRunParams,
        output_name: str | None = None,
        library_crate: LibraryCrate | None = None,
    ) -> PipeOutput:
        raise NotImplementedError


def _make_pipe(*, code: str, steps: list[Any]) -> ScriptedPipe:
    return ScriptedPipe(
        code=code,
        domain_code="test_replay_safe_spans",
        description=code,
        output=StuffSpec(concept=ConceptFactory.make_native_concept(NativeConceptCode.TEXT)),
        steps=steps,
    )


def _host_joined_otel_context() -> OtelContext:
    """The context the runner put in the job metadata for a run that joined its host's trace, as the workflow receives it."""
    trace_name, trace_name_redacted = OtelFactory.make_trace_names(pipeline_run_id=PIPELINE_RUN_ID, pipe_code="outer")
    return OtelContext(
        trace_id=0x0123456789ABCDEF0123456789ABCDEF,
        trace_name=trace_name,
        trace_name_redacted=trace_name_redacted,
        span_id=OTelConstants.OTEL_VIRTUAL_ROOT_PARENT_SPAN_ID,
        is_sampled=True,
        trace_state=HOST_TRACE_STATE,
        host_span_id=HOST_SPAN_ID,
        is_host_span_pipelex=False,
    )


async def _run_workflow_code(pipe: ScriptedPipe) -> None:
    job_metadata = JobMetadata(
        run_metadata=RunMetadata(user_id="pytest", storage_scope="test/scope", read_scope=None, pipeline_run_id=PIPELINE_RUN_ID),
        otel_context=_host_joined_otel_context(),
    )
    await pipe.live_run_pipe(
        job_metadata=job_metadata,
        working_memory=WorkingMemoryFactory.make_empty(),
        pipe_run_params=PipeRunParams(run_mode=PipeRunMode.LIVE, batch_max_concurrency=1, pipe_stack_limit=10),
    )


def _span_named(spans: tuple[ReadableSpan, ...], *, name: str) -> ReadableSpan:
    (span,) = [span for span in spans if span.name == name]
    return span


def _span_id_of(span: ReadableSpan) -> int:
    span_context = span.get_span_context()
    assert span_context is not None
    return span_context.span_id


def _parent_id_of(span: ReadableSpan) -> int:
    assert span.parent is not None
    return span.parent.span_id


def _set(*, execution: FakeWorkflowExecution, now_ns: int | None = None, is_replaying: bool | None = None) -> Callable[[], None]:
    """A step moving the workflow along its history: to a later workflow task, or from replay to live."""

    def step() -> None:
        if now_ns is not None:
            execution.now_ns = now_ns
        if is_replaying is not None:
            execution.replaying = is_replaying

    return step


def _evict() -> None:
    raise WorkflowEviction


@pytest.mark.asyncio
class TestLiveRunPipeReplaySafeSpans:
    @pytest.fixture
    def pipelex_spans(self, mocker: MockerFixture) -> InMemorySpanExporter:
        """Pipelex's own tracer provider, with its replay-safe id generator, exporting to memory."""
        exporter = InMemorySpanExporter()
        provider = TracerProvider(id_generator=ReplaySafeIdGenerator())
        provider.add_span_processor(SimpleSpanProcessor(exporter))
        mocker.patch.object(TelemetryManagerAbstract, "get_instance_tracer", return_value=provider.get_tracer("pipelex"))
        mocker.patch.object(TelemetryManagerAbstract, "is_instance_tracer_replay_safe", return_value=True)
        mocker.patch.object(TelemetryManagerAbstract, "is_join_host_trace_enabled", return_value=False)
        return exporter

    @pytest.fixture
    def workflow(self) -> Iterator[dict[str, FakeWorkflowExecution]]:
        """The workflow execution the orchestrator's probe answers with, swapped as the workflow moves to another worker."""
        current: dict[str, FakeWorkflowExecution] = {}

        def probe() -> WorkflowExecutionProtocol | None:
            return current.get("execution")

        workflow_execution_slot.install(probe=probe)
        try:
            yield current
        finally:
            workflow_execution_slot.reset()

    async def test_a_pipe_crossing_an_eviction_yields_one_span_with_its_true_start(
        self, pipelex_spans: InMemorySpanExporter, workflow: dict[str, FakeWorkflowExecution]
    ) -> None:
        # The live execution: `first` runs to its end, then the workflow is evicted while `second` runs.
        live = FakeWorkflowExecution(is_replaying=False)
        workflow["execution"] = live
        first = _make_pipe(code="first", steps=[_set(execution=live, now_ns=SECOND_TASK_AT_NS)])
        second = _make_pipe(code="second", steps=[_evict])
        outer = _make_pipe(code="outer", steps=[first, second])
        with pytest.raises(WorkflowEviction):
            await _run_workflow_code(outer)

        # Only the pipe that really ended was exported; the eviction is no pipe's end.
        assert [span.name for span in pipelex_spans.get_finished_spans()] == ["ScriptedPipe: first"]
        live_ids = (outer.seen_span_ids[0], first.seen_span_ids[0], second.seen_span_ids[0])

        # Another worker replays the workflow from its history: `first` ends again, in replay, and history runs out
        # while `second` runs, which then reaches its end live, in a later workflow task, as does `outer`.
        replay = FakeWorkflowExecution(is_replaying=True)
        workflow["execution"] = replay
        first.steps = [_set(execution=replay, now_ns=SECOND_TASK_AT_NS)]
        second.steps = [_set(execution=replay, is_replaying=False, now_ns=LAST_TASK_AT_NS)]
        await _run_workflow_code(outer)

        spans = pipelex_spans.get_finished_spans()
        assert sorted(span.name for span in spans) == ["ScriptedPipe: first", "ScriptedPipe: outer", "ScriptedPipe: second"]
        outer_span = _span_named(spans, name="ScriptedPipe: outer")
        first_span = _span_named(spans, name="ScriptedPipe: first")
        second_span = _span_named(spans, name="ScriptedPipe: second")
        # The replay recomputed every id the live execution gave out, so each span is the one the live run opened.
        assert (outer.seen_span_ids[1], first.seen_span_ids[1], second.seen_span_ids[1]) == live_ids
        assert (_span_id_of(outer_span), _span_id_of(first_span), _span_id_of(second_span)) == live_ids
        # Their starts are the workflow's clock where history opened them, the outer pipe's from before the eviction.
        assert outer_span.start_time == STARTED_AT_NS
        assert first_span.start_time == STARTED_AT_NS
        assert second_span.start_time == SECOND_TASK_AT_NS
        assert first_span.end_time == SECOND_TASK_AT_NS
        assert second_span.end_time == LAST_TASK_AT_NS
        assert outer_span.end_time == LAST_TASK_AT_NS
        # The tree holds: the children exported by two executions both point at the one outer span, which keeps the
        # trace join's parent, the host's span, with the host's trace state.
        assert _parent_id_of(first_span) == _span_id_of(outer_span)
        assert _parent_id_of(second_span) == _span_id_of(outer_span)
        assert _parent_id_of(outer_span) == HOST_SPAN_ID
        outer_context = outer_span.get_span_context()
        assert outer_context is not None
        assert outer_context.trace_id == _host_joined_otel_context().trace_id
        assert outer_context.trace_state == TraceState.from_header([HOST_TRACE_STATE])

    @pytest.mark.parametrize(
        "error",
        [PipeFailedError("the pipe failed"), asyncio.CancelledError("the run was cancelled")],
        ids=["a pipe failure the worker lists", "a cancellation of the run"],
    )
    async def test_a_nested_pipe_ending_the_workflow_live_exports_its_failure_at_every_depth(
        self, pipelex_spans: InMemorySpanExporter, workflow: dict[str, FakeWorkflowExecution], error: BaseException
    ) -> None:
        live = FakeWorkflowExecution(is_replaying=False)
        workflow["execution"] = live

        def fail() -> None:
            live.now_ns = LAST_TASK_AT_NS
            raise error

        inner = _make_pipe(code="inner", steps=[fail])
        outer = _make_pipe(code="outer", steps=[inner])
        with pytest.raises(type(error)):
            await _run_workflow_code(outer)

        spans = pipelex_spans.get_finished_spans()
        assert sorted(span.name for span in spans) == ["ScriptedPipe: inner", "ScriptedPipe: outer"]
        for span in spans:
            assert span.attributes is not None
            assert span.attributes.get(PipelexSpanAttr.OUTCOME) == SpanOutcome.FAILURE
            assert span.start_time == STARTED_AT_NS
            assert span.end_time == LAST_TASK_AT_NS
            # The exception is stamped on the clock the span ends on, never the wall clock.
            assert [event.timestamp for event in span.events if event.name == "exception"] == [LAST_TASK_AT_NS]
        assert _parent_id_of(_span_named(spans, name="ScriptedPipe: inner")) == _span_id_of(_span_named(spans, name="ScriptedPipe: outer"))

    async def test_an_error_failing_the_workflow_task_is_left_to_the_retry_that_reaches_the_real_end(
        self, pipelex_spans: InMemorySpanExporter, workflow: dict[str, FakeWorkflowExecution]
    ) -> None:
        workflow["execution"] = FakeWorkflowExecution(is_replaying=False)

        def fail_the_task() -> None:
            msg = "a bug in workflow code"
            raise RuntimeError(msg)

        with pytest.raises(RuntimeError, match="a bug in workflow code"):
            await _run_workflow_code(_make_pipe(code="retried", steps=[fail_the_task]))

        assert pipelex_spans.get_finished_spans() == ()

    async def test_an_end_during_teardown_asks_unwinding_first_and_keeps_the_pipes_own_exception(
        self, pipelex_spans: InMemorySpanExporter, workflow: dict[str, FakeWorkflowExecution]
    ) -> None:
        workflow["execution"] = FakeWorkflowExecution(is_replaying=False)
        eviction = WorkflowEviction()

        def evict() -> None:
            # Once torn down, the probe answers that the code unwinds, and would raise on any other question: none is asked.
            workflow["execution"] = TornDownWorkflowExecution(is_replaying=False)
            raise eviction

        with pytest.raises(WorkflowEviction) as raised:
            await _run_workflow_code(_make_pipe(code="evicted", steps=[evict]))

        assert raised.value is eviction
        assert pipelex_spans.get_finished_spans() == ()

    @pytest.mark.parametrize(
        "error",
        [PipeFailedError("the pipe failed"), WorkflowEviction()],
        ids=["the pipe failed", "the code is torn down"],
    )
    async def test_a_probe_raising_while_a_pipe_fails_never_replaces_the_pipes_exception(
        self,
        pipelex_spans: InMemorySpanExporter,
        workflow: dict[str, FakeWorkflowExecution],
        error: BaseException,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        workflow["execution"] = BrokenWorkflowExecution(is_replaying=False)

        def fail() -> None:
            raise error

        with caplog.at_level(logging.WARNING), pytest.raises(type(error)) as raised:
            await _run_workflow_code(_make_pipe(code="failing", steps=[fail]))

        assert raised.value is error
        # The span does not count an end the probe could not classify, and says so.
        assert pipelex_spans.get_finished_spans() == ()
        assert [record.getMessage() for record in caplog.records if record.getMessage() == PROBE_FAILED_WARNING] == [PROBE_FAILED_WARNING]

    async def test_a_probe_raising_while_a_pipe_succeeds_never_fails_the_pipe(
        self, pipelex_spans: InMemorySpanExporter, workflow: dict[str, FakeWorkflowExecution], caplog: pytest.LogCaptureFixture
    ) -> None:
        workflow["execution"] = FakeWorkflowExecution(is_replaying=False)

        def tear_down() -> None:
            # The pipe's work is done, then every question the probe is asked about its end raises.
            workflow["execution"] = TornDownWorkflowExecution(is_replaying=False)

        succeeding = _make_pipe(code="succeeding", steps=[tear_down])
        with caplog.at_level(logging.WARNING):
            await _run_workflow_code(succeeding)

        assert succeeding.seen_span_ids != []
        assert pipelex_spans.get_finished_spans() == ()
        assert [record.getMessage() for record in caplog.records if record.getMessage() == PROBE_FAILED_WARNING] == [PROBE_FAILED_WARNING]

    async def test_a_coroutine_closed_in_workflow_code_ends_no_span_without_asking_the_workflow_execution(
        self, pipelex_spans: InMemorySpanExporter, workflow: dict[str, FakeWorkflowExecution]
    ) -> None:
        workflow["execution"] = FakeWorkflowExecution(is_replaying=False)

        def close() -> None:
            # From where a torn-down coroutine is closed, the workflow execution can only raise.
            workflow["execution"] = BrokenWorkflowExecution(is_replaying=False)
            raise GeneratorExit

        with pytest.raises(GeneratorExit):
            await _run_workflow_code(_make_pipe(code="closed", steps=[close]))

        assert pipelex_spans.get_finished_spans() == ()

    @pytest.mark.usefixtures("workflow")
    async def test_a_coroutine_closed_outside_workflow_code_is_the_pipes_real_end(self, pipelex_spans: InMemorySpanExporter) -> None:
        # The slot is claimed, but the probe answers that this call runs in no workflow code, as in an activity.
        assert get_workflow_execution() is None

        def close() -> None:
            raise GeneratorExit

        with pytest.raises(GeneratorExit):
            await _run_workflow_code(_make_pipe(code="activity_side", steps=[close]))

        (span,) = pipelex_spans.get_finished_spans()
        assert span.attributes is not None
        assert span.attributes.get(PipelexSpanAttr.OUTCOME) == SpanOutcome.FAILURE

    @pytest.mark.usefixtures("pipelex_spans")
    async def test_a_span_of_another_kind_in_workflow_code_never_shifts_the_pipe_span_ids(self, workflow: dict[str, FakeWorkflowExecution]) -> None:
        workflow["execution"] = FakeWorkflowExecution(is_replaying=False)
        plain = _make_pipe(code="plain", steps=[])
        await _run_workflow_code(plain)

        # The same workflow on a worker whose configuration opens a span of its own in workflow code before the pipe.
        workflow["execution"] = FakeWorkflowExecution(is_replaying=False)
        tracer = TelemetryManagerAbstract.get_instance_tracer()
        assert tracer is not None
        tracer.start_span("a worker's own span").end()
        with_extra_span = _make_pipe(code="plain", steps=[])
        await _run_workflow_code(with_extra_span)

        assert with_extra_span.seen_span_ids == plain.seen_span_ids
        assert plain.seen_span_ids == [Random(WORKFLOW_SEED).getrandbits(64)]

    @pytest.mark.parametrize(
        "id_generator",
        [RandomIdGenerator(), ReplaySafeIdGenerator()],
        ids=["a provider of its own", "a replay-safe id generator under a manager that does not answer for it"],
    )
    async def test_a_tracer_that_cannot_recompute_ids_keeps_random_ids_the_wall_clock_and_every_end(
        self, workflow: dict[str, FakeWorkflowExecution], mocker: MockerFixture, id_generator: IdGenerator
    ) -> None:
        # A telemetry manager injected with a provider of its own, which does not say its tracer is replay-safe: the
        # id, the start and the end all follow that answer, whatever the provider's id generator.
        exporter = InMemorySpanExporter()
        provider = TracerProvider(id_generator=id_generator)
        provider.add_span_processor(SimpleSpanProcessor(exporter))
        mocker.patch.object(TelemetryManagerAbstract, "get_instance_tracer", return_value=provider.get_tracer("injected"))
        mocker.patch.object(TelemetryManagerAbstract, "is_instance_tracer_replay_safe", return_value=False)
        mocker.patch.object(TelemetryManagerAbstract, "is_join_host_trace_enabled", return_value=False)
        workflow["execution"] = FakeWorkflowExecution(is_replaying=True)

        await _run_workflow_code(_make_pipe(code="replayed", steps=[]))

        (span,) = exporter.get_finished_spans()
        assert _span_id_of(span) != Random(WORKFLOW_SEED).getrandbits(64)
        assert span.start_time is not None
        assert span.start_time > LAST_TASK_AT_NS
        assert span.end_time is not None
        assert span.end_time > LAST_TASK_AT_NS

    async def test_a_failure_replayed_from_history_is_not_exported_again(
        self, pipelex_spans: InMemorySpanExporter, workflow: dict[str, FakeWorkflowExecution]
    ) -> None:
        workflow["execution"] = FakeWorkflowExecution(is_replaying=True)

        def fail() -> None:
            msg = "the pipe failed"
            raise RuntimeError(msg)

        with pytest.raises(RuntimeError, match="the pipe failed"):
            await _run_workflow_code(_make_pipe(code="failing", steps=[fail]))

        assert pipelex_spans.get_finished_spans() == ()

    async def test_outside_workflow_code_ids_are_random_and_times_are_the_wall_clock(self, pipelex_spans: InMemorySpanExporter) -> None:
        assert get_workflow_execution() is None
        first = _make_pipe(code="solo", steps=[])
        second = _make_pipe(code="solo", steps=[])

        await _run_workflow_code(first)
        await _run_workflow_code(second)

        spans = pipelex_spans.get_finished_spans()
        assert len(spans) == 2
        assert first.seen_span_ids != second.seen_span_ids
        seeded_first_id = Random(WORKFLOW_SEED).getrandbits(64)
        assert seeded_first_id not in {_span_id_of(span) for span in spans}
        for span in spans:
            assert span.start_time is not None
            assert span.start_time > LAST_TASK_AT_NS
