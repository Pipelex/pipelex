from __future__ import annotations

import asyncio
import io
import json
import logging
from typing import TYPE_CHECKING, Any

import pytest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from typing_extensions import override

from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory
from pipelex.core.pipes.exceptions import PipeRunError
from pipelex.core.pipes.pipe_output import PipeOutput
from pipelex.core.pipes.stuff_spec.stuff_spec import StuffSpec
from pipelex.pipe_machinery.pipe_abstract import PIPE_RUN_ENDS_MESSAGE, PIPE_RUN_STARTS_MESSAGE, PipeAbstract
from pipelex.pipe_run.pipe_run_params import PipeRunParams
from pipelex.system.job_metadata import JobMetadata, OtelContext, RunMetadata
from pipelex.system.pipe_run_mode import PipeRunMode
from pipelex.system.telemetry.current_span import PIPELEX_SPAN_ID_KEY
from pipelex.system.telemetry.otel_constants import OTelConstants
from pipelex.system.telemetry.telemetry_manager_abstract import TelemetryManagerAbstract
from pipelex.tools.log.console_layouts import LogLayout
from pipelex.tools.log.json_log_sink import LOGGER_KEY, MESSAGE_KEY, JsonLogSink
from pipelex.tools.log.log_fields import LAYOUT_MARK, attached_field_names
from tests.helpers.console_log_rendering import rendered_text

if TYPE_CHECKING:
    from collections.abc import Iterator

    from opentelemetry.sdk.trace import ReadableSpan
    from pytest_mock import MockerFixture

    from pipelex.core.memory.working_memory import WorkingMemory
    from pipelex.libraries.library_crate import LibraryCrate

PIPE_LOGGER = PipeAbstract.__module__
STARTED_AT = 10.0
ENDED_AT = 11.25
DURATION_MS = 1250.0
# The trace the submission derived for the run, under the virtual root parent every root pipe span takes.
RUN_OTEL_CONTEXT = OtelContext(
    trace_id=0x0123456789ABCDEF0123456789ABCDEF,
    trace_name="pipe_run_end_test",
    trace_name_redacted="pipe_run_end_test",
    span_id=OTelConstants.OTEL_VIRTUAL_ROOT_PARENT_SPAN_ID,
)


class EndingPipe(PipeAbstract):
    """A pipe whose live run runs its child pipe, if it has one, then returns or fails; its dry run returns."""

    pipe_category: Any = "PipeOperator"
    type: Any = "PipeFunc"
    child: EndingPipe | None = None
    fails: bool = False
    is_cancelled: bool = False

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
        if self.child is not None:
            await self.child.run_pipe(job_metadata=job_metadata, working_memory=working_memory, pipe_run_params=pipe_run_params)
        if self.fails:
            msg = f"{self.code} failed"
            raise PipeRunError(msg, run_mode=pipe_run_params.run_mode, pipe_code=self.code)
        if self.is_cancelled:
            raise asyncio.CancelledError
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
        if self.child is not None:
            await self.child.run_pipe(job_metadata=job_metadata, working_memory=working_memory, pipe_run_params=pipe_run_params)
        return PipeOutput(working_memory=working_memory, pipeline_run_id=job_metadata.run_metadata.pipeline_run_id)


def _make_pipe(*, code: str, child: EndingPipe | None = None, fails: bool = False, is_cancelled: bool = False) -> EndingPipe:
    return EndingPipe(
        code=code,
        domain_code="test_pipe_run_end",
        description=code,
        output=StuffSpec(concept=ConceptFactory.make_native_concept(NativeConceptCode.TEXT)),
        child=child,
        fails=fails,
        is_cancelled=is_cancelled,
    )


def _job_metadata(*, otel_context: OtelContext | None = None) -> JobMetadata:
    return JobMetadata(
        run_metadata=RunMetadata(user_id="pytest", storage_scope="test/scope", read_scope=None, pipeline_run_id="plr-end"),
        otel_context=otel_context,
    )


def _pipe_run_params(*, run_mode: PipeRunMode) -> PipeRunParams:
    return PipeRunParams(run_mode=run_mode, batch_max_concurrency=1, pipe_stack_limit=10)


async def _run(*, pipe: EndingPipe, run_mode: PipeRunMode = PipeRunMode.LIVE, otel_context: OtelContext | None = None) -> None:
    await pipe.run_pipe(
        job_metadata=_job_metadata(otel_context=otel_context),
        working_memory=WorkingMemoryFactory.make_empty(),
        pipe_run_params=_pipe_run_params(run_mode=run_mode),
    )


def _records(caplog: pytest.LogCaptureFixture, *, message: str) -> list[logging.LogRecord]:
    return [record for record in caplog.records if record.name == PIPE_LOGGER and record.getMessage() == message]


def _field(record: logging.LogRecord, *, name: str) -> Any:
    """A field carried on the record, read the way a sink reads it."""
    return getattr(record, name)


def _fields(record: logging.LogRecord) -> dict[str, Any]:
    """The fields the call attached to the record, without the context identifiers the run bound."""
    return {name: getattr(record, name) for name in attached_field_names(record=record) if name != "pipe_run_id"}


def _span_id_of(spans: tuple[ReadableSpan, ...], *, code: str) -> str:
    """The span id of the pipe span named after `code`, as the `json` sink writes it."""
    (span,) = [span for span in spans if span.name.endswith(f": {code}")]
    span_context = span.get_span_context()
    assert span_context is not None
    return f"{span_context.span_id:016x}"


@pytest.fixture
def fixed_clock(mocker: MockerFixture) -> None:
    """Every run starts at the same reading and ends 1.25 s later, so its duration is known."""
    mocker.patch("pipelex.tools.log.summary_event.start_clock", return_value=STARTED_AT)
    mocker.patch("pipelex.tools.log.summary_fields.perf_counter", return_value=ENDED_AT)


@pytest.fixture
def span_exporter(mocker: MockerFixture) -> InMemorySpanExporter:
    """The runtime's tracer, replaced by one exporting to memory, so the test reads back the spans the pipes started."""
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    mocker.patch.object(TelemetryManagerAbstract, "get_instance_tracer", return_value=provider.get_tracer(__name__))
    return exporter


@pytest.fixture
def json_lines() -> Iterator[io.StringIO]:
    """The `json` sink's lines for every record the pipe logger writes, written as it logs them, with the span active then."""
    buffer = io.StringIO()
    handler = JsonLogSink(stream=buffer).handler
    pipe_logger = logging.getLogger(PIPE_LOGGER)
    pipe_logger.addHandler(handler)
    try:
        yield buffer
    finally:
        pipe_logger.removeHandler(handler)


def _run_end_lines(buffer: io.StringIO) -> list[dict[str, Any]]:
    """The `json` lines of the events the pipe runs ended with, in the order they ended."""
    lines = [json.loads(line) for line in buffer.getvalue().splitlines() if line]
    return [line for line in lines if line[MESSAGE_KEY] == PIPE_RUN_ENDS_MESSAGE]


@pytest.mark.usefixtures("fixed_clock")
@pytest.mark.asyncio
class TestLiveRunPipeEnd:
    async def test_a_run_that_succeeds_ends_with_the_event_under_its_announcement_id(self, caplog: pytest.LogCaptureFixture) -> None:
        with caplog.at_level(logging.INFO, logger=PIPE_LOGGER):
            await _run(pipe=_make_pipe(code="describe_company"))

        (announcement,) = _records(caplog, message=PIPE_RUN_STARTS_MESSAGE)
        (run_end,) = _records(caplog, message=PIPE_RUN_ENDS_MESSAGE)
        assert run_end.levelno == logging.INFO
        assert run_end.__dict__[LAYOUT_MARK] == LogLayout.PIPE_RUN_END
        assert _field(run_end, name="pipe_run_id") == _field(announcement, name="pipe_run_id")
        assert _fields(run_end) == {
            "pipe_type": "EndingPipe",
            "pipe_code": "describe_company",
            "output_concept": "Text",
            "pipe_depth": 0,
            "duration_ms": DURATION_MS,
            "outcome": "success",
        }

    async def test_a_run_that_fails_ends_with_its_outcome_and_error_type(self, caplog: pytest.LogCaptureFixture) -> None:
        with caplog.at_level(logging.INFO, logger=PIPE_LOGGER), pytest.raises(PipeRunError, match="describe_company failed"):
            await _run(pipe=_make_pipe(code="describe_company", fails=True))

        (run_end,) = _records(caplog, message=PIPE_RUN_ENDS_MESSAGE)
        assert _fields(run_end) == {
            "pipe_type": "EndingPipe",
            "pipe_code": "describe_company",
            "output_concept": "Text",
            "pipe_depth": 0,
            "duration_ms": DURATION_MS,
            "outcome": "error",
            "error.type": "PipeRunError",
        }

    @pytest.mark.parametrize("child_fails", [False, True], ids=["the nested run succeeds", "the nested run fails"])
    async def test_every_announced_run_ends_once_the_nested_one_first_at_its_own_depth(
        self, caplog: pytest.LogCaptureFixture, child_fails: bool
    ) -> None:
        pipe = _make_pipe(code="build_profile", child=_make_pipe(code="describe_company", fails=child_fails))

        with caplog.at_level(logging.INFO, logger=PIPE_LOGGER):
            if child_fails:
                with pytest.raises(PipeRunError):
                    await _run(pipe=pipe)
            else:
                await _run(pipe=pipe)

        announcements = _records(caplog, message=PIPE_RUN_STARTS_MESSAGE)
        run_ends = _records(caplog, message=PIPE_RUN_ENDS_MESSAGE)
        outcome = "error" if child_fails else "success"
        assert [(_field(record, name="pipe_code"), _field(record, name="pipe_depth")) for record in announcements] == [
            ("build_profile", 0),
            ("describe_company", 1),
        ]
        assert [(_field(record, name="pipe_code"), _field(record, name="pipe_depth"), _field(record, name="outcome")) for record in run_ends] == [
            ("describe_company", 1, outcome),
            ("build_profile", 0, outcome),
        ]

    async def test_a_dry_run_ends_with_no_event_as_it_starts_with_no_announcement(self, caplog: pytest.LogCaptureFixture) -> None:
        with caplog.at_level(logging.INFO, logger=PIPE_LOGGER):
            await _run(pipe=_make_pipe(code="build_profile", child=_make_pipe(code="describe_company")), run_mode=PipeRunMode.DRY)

        assert not _records(caplog, message=PIPE_RUN_STARTS_MESSAGE)
        assert not _records(caplog, message=PIPE_RUN_ENDS_MESSAGE)

    async def test_the_console_draws_the_end_in_the_pipe_tree_at_its_depth(self, caplog: pytest.LogCaptureFixture) -> None:
        pipe = _make_pipe(code="build_profile", child=_make_pipe(code="describe_company"))
        with caplog.at_level(logging.INFO, logger=PIPE_LOGGER):
            await _run(pipe=pipe)
            with pytest.raises(PipeRunError):
                await _run(pipe=_make_pipe(code="describe_company", fails=True))

        lines = [rendered_text(record=record).plain for record in _records(caplog, message=PIPE_RUN_ENDS_MESSAGE)]
        assert lines == [
            "🧠:    ↳ EndingPipe: describe_company done in 1.25 s",
            "🧠: EndingPipe: build_profile done in 1.25 s",
            "🧠: EndingPipe: describe_company failed after 1.25 s error.type=PipeRunError",
        ]

    async def test_the_json_sink_writes_the_duration_and_the_depth_as_numbers(self, caplog: pytest.LogCaptureFixture) -> None:
        with caplog.at_level(logging.INFO, logger=PIPE_LOGGER):
            await _run(pipe=_make_pipe(code="describe_company"))
        (run_end,) = _records(caplog, message=PIPE_RUN_ENDS_MESSAGE)
        buffer = io.StringIO()

        JsonLogSink(stream=buffer).handler.handle(run_end)

        line: dict[str, Any] = json.loads(buffer.getvalue())
        assert (line[MESSAGE_KEY], line[LOGGER_KEY]) == (PIPE_RUN_ENDS_MESSAGE, PIPE_LOGGER)
        assert isinstance(line["duration_ms"], float)
        assert line["duration_ms"] == DURATION_MS
        assert isinstance(line["pipe_depth"], int)
        assert (line["pipe_code"], line["outcome"]) == ("describe_company", "success")
        assert "error.type" not in line
        assert LogLayout.PIPE_RUN_END not in line.values()

    @pytest.mark.parametrize("fails", [False, True], ids=["the run succeeds", "the run fails"])
    async def test_a_root_runs_end_is_logged_inside_its_own_span(
        self, caplog: pytest.LogCaptureFixture, span_exporter: InMemorySpanExporter, json_lines: io.StringIO, fails: bool
    ) -> None:
        with caplog.at_level(logging.INFO, logger=PIPE_LOGGER):
            if fails:
                with pytest.raises(PipeRunError):
                    await _run(pipe=_make_pipe(code="describe_company", fails=True), otel_context=RUN_OTEL_CONTEXT)
            else:
                await _run(pipe=_make_pipe(code="describe_company"), otel_context=RUN_OTEL_CONTEXT)

        (run_end,) = _run_end_lines(json_lines)
        assert (run_end["pipe_code"], run_end["outcome"]) == ("describe_company", "error" if fails else "success")
        assert run_end[PIPELEX_SPAN_ID_KEY] == _span_id_of(span_exporter.get_finished_spans(), code="describe_company")

    @pytest.mark.parametrize("child_fails", [False, True], ids=["the nested run succeeds", "the nested run fails"])
    async def test_a_nested_runs_end_carries_its_own_span_and_its_parents_end_the_parents(
        self, caplog: pytest.LogCaptureFixture, span_exporter: InMemorySpanExporter, json_lines: io.StringIO, child_fails: bool
    ) -> None:
        pipe = _make_pipe(code="build_profile", child=_make_pipe(code="describe_company", fails=child_fails))

        with caplog.at_level(logging.INFO, logger=PIPE_LOGGER):
            if child_fails:
                with pytest.raises(PipeRunError):
                    await _run(pipe=pipe, otel_context=RUN_OTEL_CONTEXT)
            else:
                await _run(pipe=pipe, otel_context=RUN_OTEL_CONTEXT)

        spans = span_exporter.get_finished_spans()
        child_end, parent_end = _run_end_lines(json_lines)
        assert (child_end["pipe_code"], child_end[PIPELEX_SPAN_ID_KEY]) == ("describe_company", _span_id_of(spans, code="describe_company"))
        assert (parent_end["pipe_code"], parent_end[PIPELEX_SPAN_ID_KEY]) == ("build_profile", _span_id_of(spans, code="build_profile"))

    async def test_a_failure_before_the_span_still_ends_the_run_once(
        self, caplog: pytest.LogCaptureFixture, mocker: MockerFixture, json_lines: io.StringIO
    ) -> None:
        """The setup between the announcement and the span can fail; the run still ends with one event, outside any span."""
        mocker.patch.object(EndingPipe, "_start_pipe_span", side_effect=RuntimeError("the tracer broke"))

        with caplog.at_level(logging.INFO, logger=PIPE_LOGGER), pytest.raises(RuntimeError, match="the tracer broke"):
            await _run(pipe=_make_pipe(code="describe_company"), otel_context=RUN_OTEL_CONTEXT)

        (run_end,) = _records(caplog, message=PIPE_RUN_ENDS_MESSAGE)
        assert (_field(run_end, name="outcome"), _field(run_end, name="error.type")) == ("error", "RuntimeError")
        (run_end_line,) = _run_end_lines(json_lines)
        assert PIPELEX_SPAN_ID_KEY not in run_end_line

    async def test_a_cancelled_run_ends_with_a_cancelled_outcome_and_no_error_type(self, caplog: pytest.LogCaptureFixture) -> None:
        """A run cancelled from outside, a sibling of a failed batch item or a run its client cancelled, did not fail."""
        with caplog.at_level(logging.INFO, logger=PIPE_LOGGER), pytest.raises(asyncio.CancelledError):
            await _run(pipe=_make_pipe(code="describe_company", is_cancelled=True))

        (run_end,) = _records(caplog, message=PIPE_RUN_ENDS_MESSAGE)
        assert _fields(run_end) == {
            "pipe_type": "EndingPipe",
            "pipe_code": "describe_company",
            "output_concept": "Text",
            "pipe_depth": 0,
            "duration_ms": DURATION_MS,
            "outcome": "cancelled",
        }
        assert rendered_text(record=run_end).plain == "🧠: EndingPipe: describe_company cancelled after 1.25 s"
