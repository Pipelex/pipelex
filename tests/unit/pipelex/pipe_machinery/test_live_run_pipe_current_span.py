"""``live_run_pipe`` makes the pipe's span current from its start to its end, so the run's log lines carry it.

The span is started with an explicit parent read off the job metadata, which is how a child running in
another process reaches it, and that stays as it was: the pipe only makes its already-started span the
current one for the in-process work, and restores the previous context when the span ends, however it
ends. Both wire sinks read the current span, so a line logged during the run names the pipe's span: the
``json`` sink under ``trace_id`` and ``span_id``, the ``otlp`` sink as the record's own trace context.
Each test runs once per sink.
"""

from __future__ import annotations

import asyncio
import io
import json
import logging
from typing import TYPE_CHECKING, Any, NamedTuple

import pytest
from opentelemetry import trace
from opentelemetry.sdk._logs.export import InMemoryLogExporter, SimpleLogRecordProcessor
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import StatusCode
from pydantic import Field, PrivateAttr
from typing_extensions import override

from pipelex import log
from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory
from pipelex.core.pipes.pipe_output import PipeOutput
from pipelex.core.pipes.stuff_spec.stuff_spec import StuffSpec
from pipelex.pipe_machinery.pipe_abstract import PipeAbstract
from pipelex.pipe_run.pipe_run_params import PipeRunParams
from pipelex.system.configuration.config_loader import ConfigLoader
from pipelex.system.job_metadata import JobMetadata, OtelContext, RunMetadata
from pipelex.system.pipe_run_mode import PipeRunMode
from pipelex.system.telemetry.otel_constants import OTelConstants
from pipelex.system.telemetry.telemetry_manager_abstract import TelemetryManagerAbstract
from pipelex.tools.log.json_log_sink import LOGGER_KEY, MESSAGE_KEY, SPAN_ID_KEY, TRACE_ID_KEY, JsonLogSink
from pipelex.tools.log.log import Log
from pipelex.tools.log.log_config import LogConfig
from pipelex.tools.log.otlp_log_sink import OtlpLogSink
from pipelex.tools.misc.toml_utils import load_toml_from_path
from pipelex.tools.typing.pydantic_utils import empty_list_factory_of

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

    from opentelemetry.sdk.trace import ReadableSpan
    from pytest_mock import MockerFixture

    from pipelex.core.memory.working_memory import WorkingMemory
    from pipelex.libraries.library_crate import LibraryCrate

# The trace the submission derived for the run, and the virtual root parent every root pipe span takes.
RUN_TRACE_ID = 0x0123456789ABCDEF0123456789ABCDEF
RUN_OTEL_CONTEXT = OtelContext(
    trace_id=RUN_TRACE_ID,
    trace_name="current_span_test",
    trace_name_redacted="current_span_test",
    span_id=OTelConstants.OTEL_VIRTUAL_ROOT_PARENT_SPAN_ID,
)


class LineTrace(NamedTuple):
    """The trace context a sink wrote for one line, as hex, or ``None`` where the line carries none."""

    trace_id: str | None
    span_id: str | None


class Sunk(NamedTuple):
    """A fresh ``Log`` with a sink installed, and how to read back the trace context of each of this module's lines."""

    log: Log
    read_lines: Callable[[], dict[str, LineTrace]]


class CurrentSpanPipe(PipeAbstract):
    """A pipe whose live run logs a line and records the span current at that moment; it may nest a pipe, and it may fail."""

    pipe_category: Any = "PipeOperator"
    type: Any = "PipeFunc"
    nested: CurrentSpanPipe | None = None
    fails: bool = False
    hangs: bool = False
    seen_span_ids: list[int] = Field(default_factory=empty_list_factory_of(int))
    _hanging: asyncio.Event = PrivateAttr(default_factory=asyncio.Event)

    @property
    def hanging(self) -> asyncio.Event:
        """Set once a hanging pipe has logged its line and started to wait."""
        return self._hanging

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
        self.seen_span_ids.append(trace.get_current_span().get_span_context().span_id)
        log.info(f"inside {self.code}")
        if self.nested is not None:
            await self.nested.live_run_pipe(job_metadata=job_metadata, working_memory=working_memory, pipe_run_params=pipe_run_params)
            log.info(f"back in {self.code}")
        if self.fails:
            msg = f"{self.code} failed"
            raise RuntimeError(msg)
        if self.hangs:
            self._hanging.set()
            await asyncio.Event().wait()
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


def _make_pipe(*, code: str, nested: CurrentSpanPipe | None = None, fails: bool = False, hangs: bool = False) -> CurrentSpanPipe:
    return CurrentSpanPipe(
        code=code,
        domain_code="test_current_span",
        description=code,
        output=StuffSpec(concept=ConceptFactory.make_native_concept(NativeConceptCode.TEXT)),
        nested=nested,
        fails=fails,
        hangs=hangs,
    )


def _traced_metadata() -> JobMetadata:
    """What a submission builds when the runtime traces: the run's identifiers and its derived trace."""
    return JobMetadata(
        run_metadata=RunMetadata(user_id="pytest", storage_scope="test/scope", pipeline_run_id="plr-span"),
        otel_context=RUN_OTEL_CONTEXT,
    )


def _live_params() -> PipeRunParams:
    return PipeRunParams(run_mode=PipeRunMode.LIVE, batch_max_concurrency=1, pipe_stack_limit=10)


async def _run(pipe: CurrentSpanPipe) -> None:
    await pipe.live_run_pipe(job_metadata=_traced_metadata(), working_memory=WorkingMemoryFactory.make_empty(), pipe_run_params=_live_params())


def _package_log_config() -> LogConfig:
    config_dict = load_toml_from_path(ConfigLoader().pipelex_root_dir / "pipelex.toml")
    return LogConfig.model_validate(config_dict["runtime"]["log"])


def _json_lines(buffer: io.StringIO) -> dict[str, LineTrace]:
    lines = [json.loads(line) for line in buffer.getvalue().splitlines() if line]
    return {
        line[MESSAGE_KEY]: LineTrace(trace_id=line.get(TRACE_ID_KEY), span_id=line.get(SPAN_ID_KEY)) for line in lines if line[LOGGER_KEY] == __name__
    }


def _otlp_lines(exporter: InMemoryLogExporter) -> dict[str, LineTrace]:
    lines: dict[str, LineTrace] = {}
    for log_data in exporter.get_finished_logs():
        if log_data.instrumentation_scope.name != __name__:
            continue
        record = log_data.log_record
        trace_id = f"{record.trace_id:032x}" if record.trace_id else None
        span_id = f"{record.span_id:016x}" if record.span_id else None
        lines[str(record.body)] = LineTrace(trace_id=trace_id, span_id=span_id)
    return lines


def _span_id(span: ReadableSpan) -> int:
    span_context = span.get_span_context()
    assert span_context is not None
    return int(span_context.span_id)


def _hex_span_id(span: ReadableSpan) -> str:
    return f"{_span_id(span):016x}"


def _span_named(spans: tuple[ReadableSpan, ...], *, code: str) -> ReadableSpan:
    (span,) = [span for span in spans if span.name.endswith(f": {code}")]
    return span


@pytest.mark.asyncio
class TestLiveRunPipeCurrentSpan:
    @pytest.fixture(params=["json", "otlp"])
    def sunk(self, request: pytest.FixtureRequest, caplog: pytest.LogCaptureFixture) -> Iterator[Sunk]:
        """A fresh ``Log`` with the sink under test installed, torn down so the root logger is left as found."""
        caplog.set_level(logging.INFO, logger=__name__)
        fresh = Log()
        fresh.configure(log_config=_package_log_config())
        read_lines: Callable[[], dict[str, LineTrace]]
        if request.param == "json":
            buffer = io.StringIO()
            fresh.install_sink(JsonLogSink(stream=buffer))

            def read_lines() -> dict[str, LineTrace]:
                return _json_lines(buffer)
        else:
            exporter = InMemoryLogExporter()
            fresh.install_sink(OtlpLogSink(processor=SimpleLogRecordProcessor(exporter)))

            def read_lines() -> dict[str, LineTrace]:
                return _otlp_lines(exporter)

        try:
            yield Sunk(log=fresh, read_lines=read_lines)
        finally:
            fresh.reset()

    @pytest.fixture
    def span_exporter(self, mocker: MockerFixture) -> InMemorySpanExporter:
        """The runtime's tracer, replaced by one exporting to memory, so the test reads back the spans the pipes started."""
        exporter = InMemorySpanExporter()
        provider = TracerProvider()
        provider.add_span_processor(SimpleSpanProcessor(exporter))
        mocker.patch.object(TelemetryManagerAbstract, "get_instance_tracer", return_value=provider.get_tracer(__name__))
        return exporter

    async def test_a_line_logged_during_the_run_carries_the_pipes_span(self, sunk: Sunk, span_exporter: InMemorySpanExporter) -> None:
        pipe = _make_pipe(code="solo")

        await _run(pipe)

        pipe_span = _span_named(span_exporter.get_finished_spans(), code="solo")
        assert sunk.read_lines()["inside solo"] == LineTrace(trace_id=f"{RUN_TRACE_ID:032x}", span_id=_hex_span_id(pipe_span))
        assert pipe.seen_span_ids == [_span_id(pipe_span)]
        assert trace.get_current_span() is trace.INVALID_SPAN
        log.info("after the run")
        assert sunk.read_lines()["after the run"] == LineTrace(trace_id=None, span_id=None)

    async def test_a_nested_pipe_makes_its_own_span_current_and_the_outer_one_comes_back(
        self, sunk: Sunk, span_exporter: InMemorySpanExporter
    ) -> None:
        outer = _make_pipe(code="outer", nested=_make_pipe(code="inner"))

        await _run(outer)

        spans = span_exporter.get_finished_spans()
        outer_span = _span_named(spans, code="outer")
        inner_span = _span_named(spans, code="inner")
        lines = sunk.read_lines()
        run_trace = f"{RUN_TRACE_ID:032x}"
        assert lines["inside outer"] == LineTrace(trace_id=run_trace, span_id=_hex_span_id(outer_span))
        assert lines["inside inner"] == LineTrace(trace_id=run_trace, span_id=_hex_span_id(inner_span))
        assert lines["back in outer"] == LineTrace(trace_id=run_trace, span_id=_hex_span_id(outer_span))
        # The nested span's parent still arrives through the job metadata, exactly as it did.
        assert inner_span.parent is not None
        assert inner_span.parent.span_id == _span_id(outer_span)

    async def test_a_failing_pipe_keeps_its_span_current_through_the_failure_and_records_it_once(
        self, sunk: Sunk, span_exporter: InMemorySpanExporter
    ) -> None:
        pipe = _make_pipe(code="failing", fails=True)

        with pytest.raises(RuntimeError, match="failing failed"):
            await _run(pipe)

        pipe_span = _span_named(span_exporter.get_finished_spans(), code="failing")
        assert sunk.read_lines()["inside failing"].span_id == _hex_span_id(pipe_span)
        assert trace.get_current_span() is trace.INVALID_SPAN
        # The pipe's own error hook records the failure; making the span current records nothing more.
        assert pipe_span.status.status_code is StatusCode.ERROR
        assert [event.name for event in pipe_span.events] == ["exception"]

    async def test_without_a_tracer_the_callers_span_stays_current(self, sunk: Sunk, mocker: MockerFixture) -> None:
        """No tracer, no pipe span: the context is left alone, so a line names whatever span the caller runs under."""
        mocker.patch.object(TelemetryManagerAbstract, "get_instance_tracer", return_value=None)
        caller_tracer = TracerProvider().get_tracer(__name__)
        pipe = _make_pipe(code="untraced")

        with caller_tracer.start_as_current_span("caller") as caller_span:
            await _run(pipe)
        caller_context = caller_span.get_span_context()

        assert sunk.read_lines()["inside untraced"] == LineTrace(trace_id=f"{caller_context.trace_id:032x}", span_id=f"{caller_context.span_id:016x}")

    async def test_a_cancelled_pipe_ends_its_span_and_restores_the_context(self, sunk: Sunk, span_exporter: InMemorySpanExporter) -> None:
        """A cancellation is not an ``Exception``; the span still ends, so the lines of the run name a span the backend receives."""
        pipe = _make_pipe(code="cancelled", hangs=True)
        task = asyncio.create_task(_run(pipe))
        await pipe.hanging.wait()

        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

        pipe_span = _span_named(span_exporter.get_finished_spans(), code="cancelled")
        assert pipe_span.status.status_code is StatusCode.ERROR
        assert sunk.read_lines()["inside cancelled"].span_id == _hex_span_id(pipe_span)
        assert trace.get_current_span() is trace.INVALID_SPAN

    async def test_a_no_op_tracer_leaves_the_callers_span_current(self, sunk: Sunk, mocker: MockerFixture) -> None:
        """A no-op tracer, what the SDK hands out under ``OTEL_SDK_DISABLED``, starts spans naming no trace, which must not hide the caller's."""
        mocker.patch.object(TelemetryManagerAbstract, "get_instance_tracer", return_value=trace.NoOpTracer())
        caller_tracer = TracerProvider().get_tracer(__name__)
        pipe = _make_pipe(code="no_op")

        with caller_tracer.start_as_current_span("caller") as caller_span:
            await _run(pipe)
        caller_context = caller_span.get_span_context()

        assert sunk.read_lines()["inside no_op"] == LineTrace(trace_id=f"{caller_context.trace_id:032x}", span_id=f"{caller_context.span_id:016x}")
