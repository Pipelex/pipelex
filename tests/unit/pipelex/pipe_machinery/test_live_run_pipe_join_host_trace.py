"""With ``join_host_trace`` on, a run's pipe spans join the host's trace and are made current while they run.

The host is a process with its own OpenTelemetry provider, in memory here, whose current span the run reads
at pipeline start through ``host_span_to_join`` and ``OtelFactory.make_run_otel_context``, as
``pipeline_run_setup`` does. The run's root pipe span then starts under the host's span in the host's trace,
its spans are OpenTelemetry's current span while the pipe runs, so a span the host opens inside the pipe is
parented under the Pipelex span, and the host's sampling decision is followed on both sides. With the switch
off, the current span inside a run stays whatever it was outside, which ``test_live_run_pipe_current_span``
pins line by line; the off case here only contrasts the parent a host span gets.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.sdk.trace.sampling import ParentBased, TraceIdRatioBased
from pydantic import Field
from typing_extensions import override

from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory
from pipelex.core.pipes.pipe_output import PipeOutput
from pipelex.core.pipes.stuff_spec.stuff_spec import StuffSpec
from pipelex.pipe_machinery.pipe_abstract import PipeAbstract
from pipelex.pipe_run.pipe_run_params import PipeRunParams
from pipelex.system.job_metadata import JobMetadata, OtelContext, RunMetadata
from pipelex.system.pipe_run_mode import PipeRunMode
from pipelex.system.telemetry.current_span import host_span_to_join
from pipelex.system.telemetry.otel_constants import PipelexSpanAttr
from pipelex.system.telemetry.otel_factory import OtelFactory
from pipelex.system.telemetry.telemetry_manager_abstract import TelemetryManagerAbstract
from pipelex.tools.typing.pydantic_utils import empty_list_factory_of

if TYPE_CHECKING:
    from opentelemetry.sdk.trace import ReadableSpan
    from opentelemetry.trace import Tracer
    from pytest_mock import MockerFixture

    from pipelex.core.memory.working_memory import WorkingMemory
    from pipelex.libraries.library_crate import LibraryCrate

PIPELINE_RUN_ID = "plr-join-host-trace"


class HostInstrumentedPipe(PipeAbstract):
    """A pipe whose live run records OpenTelemetry's current span and opens a span of the host's, as host instrumentation would."""

    pipe_category: Any = "PipeOperator"
    type: Any = "PipeFunc"
    host_tracer: Any = None
    nested: HostInstrumentedPipe | None = None
    # A pipe whose run starts a run of its own inside it, as a pipe calling a method in-process does.
    nested_run: HostInstrumentedPipe | None = None
    started_contexts: list[OtelContext] = Field(default_factory=empty_list_factory_of(OtelContext))
    seen_current_span_ids: list[int] = Field(default_factory=empty_list_factory_of(int))

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
        self.seen_current_span_ids.append(trace.get_current_span().get_span_context().span_id)
        host_tracer: Tracer = self.host_tracer
        with host_tracer.start_as_current_span(f"host work in {self.code}"):
            pass
        if self.nested is not None:
            await self.nested.live_run_pipe(job_metadata=job_metadata, working_memory=working_memory, pipe_run_params=pipe_run_params)
        if self.nested_run is not None:
            await _run_as_pipeline_start(self.nested_run, is_join_host_trace=True, pipeline_run_id="plr-nested-run")
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


def _make_pipe(
    *, code: str, host_tracer: Tracer, nested: HostInstrumentedPipe | None = None, nested_run: HostInstrumentedPipe | None = None
) -> HostInstrumentedPipe:
    return HostInstrumentedPipe(
        code=code,
        domain_code="test_join_host_trace",
        description=code,
        output=StuffSpec(concept=ConceptFactory.make_native_concept(NativeConceptCode.TEXT)),
        host_tracer=host_tracer,
        nested=nested,
        nested_run=nested_run,
    )


async def _run_as_pipeline_start(pipe: HostInstrumentedPipe, *, is_join_host_trace: bool, pipeline_run_id: str = PIPELINE_RUN_ID) -> None:
    """Build the run's root context as ``pipeline_run_setup`` does, reading the host's span only with the switch on, and run the pipe."""
    host_span = host_span_to_join() if is_join_host_trace else None
    otel_context = OtelFactory.make_run_otel_context(pipeline_run_id=pipeline_run_id, pipe_code=pipe.code, host_span=host_span)
    # The job metadata crosses the Temporal boundary as JSON.
    otel_context = OtelContext.model_validate_json(otel_context.model_dump_json())
    pipe.started_contexts.append(otel_context)
    job_metadata = JobMetadata(
        run_metadata=RunMetadata(user_id="pytest", storage_scope="test/scope", read_scope=None, pipeline_run_id=pipeline_run_id),
        otel_context=otel_context,
    )
    await pipe.live_run_pipe(
        job_metadata=job_metadata,
        working_memory=WorkingMemoryFactory.make_empty(),
        pipe_run_params=PipeRunParams(run_mode=PipeRunMode.LIVE, batch_max_concurrency=1, pipe_stack_limit=10),
    )


def _span_named(spans: tuple[ReadableSpan, ...], *, name: str) -> ReadableSpan:
    (span,) = [span for span in spans if span.name == name]
    return span


def _context_of(span: ReadableSpan) -> trace.SpanContext:
    span_context = span.get_span_context()
    assert span_context is not None
    return span_context


def _parent_of(span: ReadableSpan) -> trace.SpanContext:
    assert span.parent is not None
    return span.parent


def _in_memory_provider(*, exporter: InMemorySpanExporter, sampler: Any = None) -> TracerProvider:
    provider = TracerProvider(sampler=sampler) if sampler is not None else TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    return provider


@pytest.mark.asyncio
class TestLiveRunPipeJoinHostTrace:
    @pytest.fixture
    def pipelex_spans(self, mocker: MockerFixture) -> InMemorySpanExporter:
        """Pipelex's own tracer, exporting to memory, with the default parent-based sampler."""
        exporter = InMemorySpanExporter()
        provider = _in_memory_provider(exporter=exporter)
        mocker.patch.object(TelemetryManagerAbstract, "get_instance_tracer", return_value=provider.get_tracer("pipelex"))
        return exporter

    def _switch(self, mocker: MockerFixture, *, is_on: bool) -> None:
        mocker.patch.object(TelemetryManagerAbstract, "is_join_host_trace_enabled", return_value=is_on)

    async def test_the_run_joins_the_hosts_trace_and_the_hosts_spans_nest_under_its_pipes(
        self, mocker: MockerFixture, pipelex_spans: InMemorySpanExporter
    ) -> None:
        self._switch(mocker, is_on=True)
        host_spans = InMemorySpanExporter()
        host_tracer = _in_memory_provider(exporter=host_spans).get_tracer("host")
        pipe = _make_pipe(code="outer", host_tracer=host_tracer, nested=_make_pipe(code="inner", host_tracer=host_tracer))

        with host_tracer.start_as_current_span("host request") as host_request:
            await _run_as_pipeline_start(pipe, is_join_host_trace=True)
            # The host's span is current again once the run is over.
            assert trace.get_current_span() is host_request

        host_context = host_request.get_span_context()
        outer_span = _span_named(pipelex_spans.get_finished_spans(), name="HostInstrumentedPipe: outer")
        inner_span = _span_named(pipelex_spans.get_finished_spans(), name="HostInstrumentedPipe: inner")
        # The run's root pipe span is a child of the host's span, in the host's trace, and is marked as the run's root.
        assert _context_of(outer_span).trace_id == host_context.trace_id
        assert _parent_of(outer_span).span_id == host_context.span_id
        assert outer_span.attributes is not None
        assert outer_span.attributes.get(PipelexSpanAttr.RUN_ROOT) is True
        # The nested pipe still takes its parent from the job metadata, in the same trace.
        assert _parent_of(inner_span).span_id == _context_of(outer_span).span_id
        assert _context_of(inner_span).trace_id == host_context.trace_id
        assert inner_span.attributes is not None
        assert PipelexSpanAttr.RUN_ROOT not in inner_span.attributes
        # Each pipe's span was OpenTelemetry's current span while it ran, so the host's spans opened there nest under it.
        assert pipe.seen_current_span_ids == [_context_of(outer_span).span_id]
        assert pipe.nested is not None
        assert pipe.nested.seen_current_span_ids == [_context_of(inner_span).span_id]
        host_work_outer = _span_named(host_spans.get_finished_spans(), name="host work in outer")
        host_work_inner = _span_named(host_spans.get_finished_spans(), name="host work in inner")
        assert _parent_of(host_work_outer).span_id == _context_of(outer_span).span_id
        assert _parent_of(host_work_inner).span_id == _context_of(inner_span).span_id
        assert _context_of(host_work_inner).trace_id == host_context.trace_id

    async def test_with_the_switch_off_the_run_keeps_its_own_trace_and_the_hosts_spans_stay_under_the_host(
        self, mocker: MockerFixture, pipelex_spans: InMemorySpanExporter
    ) -> None:
        self._switch(mocker, is_on=False)
        host_spans = InMemorySpanExporter()
        host_tracer = _in_memory_provider(exporter=host_spans).get_tracer("host")
        pipe = _make_pipe(code="solo", host_tracer=host_tracer)

        with host_tracer.start_as_current_span("host request") as host_request:
            await _run_as_pipeline_start(pipe, is_join_host_trace=False)

        host_context = host_request.get_span_context()
        pipe_span = _span_named(pipelex_spans.get_finished_spans(), name="HostInstrumentedPipe: solo")
        assert _context_of(pipe_span).trace_id == OtelFactory.make_trace_id(pipeline_run_id=PIPELINE_RUN_ID)
        assert pipe.seen_current_span_ids == [host_request.get_span_context().span_id]
        host_work = _span_named(host_spans.get_finished_spans(), name="host work in solo")
        assert _parent_of(host_work).span_id == host_context.span_id

    async def test_a_host_that_samples_its_request_out_keeps_nothing_on_either_side(
        self, mocker: MockerFixture, pipelex_spans: InMemorySpanExporter
    ) -> None:
        self._switch(mocker, is_on=True)
        host_spans = InMemorySpanExporter()
        host_tracer = _in_memory_provider(exporter=host_spans, sampler=ParentBased(TraceIdRatioBased(0.0))).get_tracer("host")
        pipe = _make_pipe(code="outer", host_tracer=host_tracer, nested=_make_pipe(code="inner", host_tracer=host_tracer))

        with host_tracer.start_as_current_span("host request") as host_request:
            assert not host_request.get_span_context().trace_flags.sampled
            await _run_as_pipeline_start(pipe, is_join_host_trace=True)

        assert pipelex_spans.get_finished_spans() == ()
        assert host_spans.get_finished_spans() == ()

    async def test_with_no_host_span_the_run_roots_its_own_trace_and_its_spans_are_still_current(
        self, mocker: MockerFixture, pipelex_spans: InMemorySpanExporter
    ) -> None:
        self._switch(mocker, is_on=True)
        host_spans = InMemorySpanExporter()
        host_tracer = _in_memory_provider(exporter=host_spans).get_tracer("host")
        pipe = _make_pipe(code="solo", host_tracer=host_tracer)

        await _run_as_pipeline_start(pipe, is_join_host_trace=True)

        pipe_span = _span_named(pipelex_spans.get_finished_spans(), name="HostInstrumentedPipe: solo")
        assert _context_of(pipe_span).trace_id == OtelFactory.make_trace_id(pipeline_run_id=PIPELINE_RUN_ID)
        assert pipe.seen_current_span_ids == [_context_of(pipe_span).span_id]
        host_work = _span_named(host_spans.get_finished_spans(), name="host work in solo")
        assert _parent_of(host_work).span_id == _context_of(pipe_span).span_id
        assert trace.get_current_span() is trace.INVALID_SPAN

    async def test_with_no_tracer_the_switch_makes_nothing_current(self, mocker: MockerFixture) -> None:
        """No tracer, no Pipelex span: the host's span stays current inside the pipe, switch or not."""
        self._switch(mocker, is_on=True)
        mocker.patch.object(TelemetryManagerAbstract, "get_instance_tracer", return_value=None)
        host_tracer = TracerProvider().get_tracer("host")
        pipe = _make_pipe(code="untraced", host_tracer=host_tracer)

        with host_tracer.start_as_current_span("host request") as host_request:
            await _run_as_pipeline_start(pipe, is_join_host_trace=True)

        assert pipe.seen_current_span_ids == [host_request.get_span_context().span_id]

    async def test_a_run_started_inside_a_running_pipe_is_a_subtree_of_the_enclosing_run(
        self, mocker: MockerFixture, pipelex_spans: InMemorySpanExporter
    ) -> None:
        """The inner run joins the outer pipe's span, which Pipelex's streams receive: it is neither a root nor announced."""
        self._switch(mocker, is_on=True)
        host_tracer = TracerProvider().get_tracer("host")
        inner_run_pipe = _make_pipe(code="inner_run", host_tracer=host_tracer)
        outer = _make_pipe(code="outer", host_tracer=host_tracer, nested_run=inner_run_pipe)

        with host_tracer.start_as_current_span("host request"):
            await _run_as_pipeline_start(outer, is_join_host_trace=True)

        spans = pipelex_spans.get_finished_spans()
        outer_span = _span_named(spans, name="HostInstrumentedPipe: outer")
        inner_run_span = _span_named(spans, name="HostInstrumentedPipe: inner_run")
        (outer_context,) = outer.started_contexts
        (inner_context,) = inner_run_pipe.started_contexts
        assert outer_context.is_host_span_pipelex is False
        assert outer_context.is_trace_root_announced is True
        assert inner_context.is_host_span_pipelex is True
        assert inner_context.is_trace_root_announced is False
        assert _parent_of(inner_run_span).span_id == _context_of(outer_span).span_id
        assert _context_of(inner_run_span).trace_id == _context_of(outer_span).trace_id
        assert outer_span.attributes is not None
        assert outer_span.attributes.get(PipelexSpanAttr.RUN_ROOT) is True
        assert inner_run_span.attributes is not None
        assert PipelexSpanAttr.RUN_ROOT not in inner_run_span.attributes

    async def test_the_hosts_trace_state_reaches_every_pipe_span(self, mocker: MockerFixture, pipelex_spans: InMemorySpanExporter) -> None:
        self._switch(mocker, is_on=True)
        host_tracer = TracerProvider().get_tracer("host")
        pipe = _make_pipe(code="outer", host_tracer=host_tracer, nested=_make_pipe(code="inner", host_tracer=host_tracer))
        host_parent = trace.set_span_in_context(
            trace.NonRecordingSpan(
                trace.SpanContext(
                    trace_id=0x0123456789ABCDEF0123456789ABCDEF,
                    span_id=0x00000000000000CD,
                    is_remote=True,
                    trace_flags=trace.TraceFlags(trace.TraceFlags.SAMPLED),
                    trace_state=trace.TraceState([("vendor", "value")]),
                )
            )
        )

        with host_tracer.start_as_current_span("host request", context=host_parent):
            await _run_as_pipeline_start(pipe, is_join_host_trace=True)

        (root_context,) = pipe.started_contexts
        assert root_context.trace_state == "vendor=value"
        for code in ("outer", "inner"):
            pipe_span = _span_named(pipelex_spans.get_finished_spans(), name=f"HostInstrumentedPipe: {code}")
            assert _context_of(pipe_span).trace_state.to_header() == "vendor=value"

    @pytest.mark.parametrize("is_host_sampled", [True, False])
    async def test_a_span_that_records_nothing_serializes_no_content(
        self, mocker: MockerFixture, pipelex_spans: InMemorySpanExporter, is_host_sampled: bool
    ) -> None:
        """Langfuse's input and output documents are built only for a span that records them, never for one the host sampled out."""
        self._switch(mocker, is_on=True)
        mocker.patch.object(TelemetryManagerAbstract, "get_langfuse_enabled", return_value=True)
        make_inputs_json = mocker.patch.object(OtelFactory, "make_inputs_json", return_value="{}")
        make_output_json = mocker.patch.object(OtelFactory, "make_output_json", return_value="{}")
        sampler = None if is_host_sampled else ParentBased(TraceIdRatioBased(0.0))
        host_tracer = _in_memory_provider(exporter=InMemorySpanExporter(), sampler=sampler).get_tracer("host")
        pipe = _make_pipe(code="solo", host_tracer=host_tracer)

        with host_tracer.start_as_current_span("host request"):
            await _run_as_pipeline_start(pipe, is_join_host_trace=True)

        expected_calls = 1 if is_host_sampled else 0
        assert make_inputs_json.call_count == expected_calls
        assert make_output_json.call_count == expected_calls
        assert len(pipelex_spans.get_finished_spans()) == expected_calls
