"""The line every live pipe run starts with: a fixed message, the pipe in its fields, and the console's pipe-run layout.

The announcement used to be Rich markup assembled into the message, which every sink but the console wrote
with its tags. It is now ``Pipe run starts`` with ``pipe_type``, ``pipe_code``, ``output_concept`` and
``pipe_depth`` as fields, and the console draws the pipe tree from them through ``LogLayout.PIPE_RUN``.
The reference for that drawing is the markup the message used to carry, rendered by a Rich handler that
read it, so the console line is checked byte for byte, colour codes included. Only a live run announces
itself, and ``live_run_pipe`` refuses a dry run mode.
"""

from __future__ import annotations

import io
import json
import logging
from typing import TYPE_CHECKING, Any

import pytest
from rich.console import Console
from rich.highlighter import Highlighter, JSONHighlighter, ReprHighlighter
from rich.logging import RichHandler
from rich.text import Text
from typing_extensions import override

from pipelex.cli.dev_cli.commands.log_call_guard import find_markup_tags
from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory
from pipelex.core.pipes.pipe_output import PipeOutput
from pipelex.core.pipes.stuff_spec.stuff_spec import StuffSpec
from pipelex.pipe_machinery.pipe_abstract import PIPE_RUN_STARTS_MESSAGE, PipeAbstract
from pipelex.pipe_run.pipe_run_params import PipeRunParams
from pipelex.system.console_target import ConsoleTarget
from pipelex.system.job_metadata import JobMetadata, RunMetadata
from pipelex.system.pipe_run_mode import PipeRunMode
from pipelex.tools.log.console_layouts import LogLayout
from pipelex.tools.log.console_log_sink import ConsoleLogSink
from pipelex.tools.log.json_log_sink import MESSAGE_KEY, JsonLogSink
from pipelex.tools.log.log_config import HighlighterName, RichLogConfig
from pipelex.tools.log.log_fields import LAYOUT_MARK
from tests.helpers.console_log_rendering import package_log_config

if TYPE_CHECKING:
    from pipelex.core.memory.working_memory import WorkingMemory
    from pipelex.libraries.library_crate import LibraryCrate

PIPE_CODE = "compose_company"
CONSOLE_WIDTH = 120
# Every field the announcement carries, all of which the console's pipe-run layout draws.
ANNOUNCEMENT_FIELDS = ("pipe_type", "pipe_code", "output_concept", "pipe_depth")

# The pipes a run is nested under, the announcing pipe last, as `run_pipe` leaves the stack when it calls
# `live_run_pipe`, with the depth the announcement reports for each.
PIPE_STACKS: list[tuple[list[str], int]] = [
    ([], 0),
    ([PIPE_CODE], 0),
    (["build_profile", PIPE_CODE], 1),
    (["run_batch", "build_profile", PIPE_CODE], 2),
]
PIPE_STACK_IDS = ["no stack at all", "a top-level run", "nested once", "nested twice"]


class QuietPipe(PipeAbstract):
    """A pipe whose live run does nothing but return, so the only line it writes is its announcement."""

    pipe_category: Any = "PipeOperator"
    type: Any = "PipeFunc"

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


def _make_pipe() -> QuietPipe:
    return QuietPipe(
        code=PIPE_CODE,
        domain_code="test_announcement",
        description="A pipe that announces itself",
        output=StuffSpec(concept=ConceptFactory.make_native_concept(NativeConceptCode.TEXT)),
    )


def _job_metadata() -> JobMetadata:
    return JobMetadata(run_metadata=RunMetadata(user_id="pytest", storage_scope="test/scope", read_scope=None, pipeline_run_id="plr-announce"))


def _pipe_run_params(*, run_mode: PipeRunMode, pipe_stack: list[str]) -> PipeRunParams:
    return PipeRunParams(run_mode=run_mode, batch_max_concurrency=1, pipe_stack_limit=10, pipe_stack=list(pipe_stack))


async def _announcement(*, caplog: pytest.LogCaptureFixture, pipe_stack: list[str]) -> logging.LogRecord:
    """The record the pipe's live run announced itself with, the pipe stack left as `run_pipe` leaves it."""
    pipe = _make_pipe()
    pipe_run_params = _pipe_run_params(run_mode=PipeRunMode.LIVE, pipe_stack=pipe_stack)
    with caplog.at_level(logging.INFO, logger=PipeAbstract.__module__):
        await pipe.live_run_pipe(job_metadata=_job_metadata(), working_memory=WorkingMemoryFactory.make_empty(), pipe_run_params=pipe_run_params)
    (record,) = [record for record in caplog.records if record.name == PipeAbstract.__module__ and record.getMessage() == PIPE_RUN_STARTS_MESSAGE]
    return record


def _markup_announcement(*, pipe: PipeAbstract, pipe_stack: list[str]) -> str:
    """The announcement as `PipeAbstract._format_pipe_run_info` wrote it, Rich markup in the message, for a live run."""
    indent_level = len(pipe_stack) - 1
    indent = "   " * indent_level
    if indent_level > 0:
        indent = f"{indent}[yellow]↳[/yellow] "
    pipe_type_label = f"[white]{pipe.pipe_type}:[/white]"
    pipe_code_label = f"[red]{pipe.code}[/red]"
    concept_code_label = f"[bold green]{pipe.output.concept.code}[/bold green]"
    arrow = "[yellow]→[/yellow]"
    return f"{indent}{pipe_type_label} {pipe_code_label} {arrow} {concept_code_label}"


def _colour_console(*, buffer: io.StringIO) -> Console:
    return Console(file=buffer, width=CONSOLE_WIDTH, force_terminal=True, color_system="truecolor", legacy_windows=False)


def _console_rich_log_config() -> RichLogConfig:
    """The shipped console settings with file links off: Rich mints a fresh random id for every link it prints."""
    return package_log_config().rich_log.model_copy(update={"is_link_path_enabled": False})


def _markup_reading_handler(*, config: RichLogConfig, buffer: io.StringIO) -> RichHandler:
    """The console handler as it was when it read every message as markup, setting for setting."""
    highlighter: Highlighter
    match config.highlighter_name:
        case HighlighterName.JSON:
            highlighter = JSONHighlighter()
        case HighlighterName.REPR:
            highlighter = ReprHighlighter()
    handler = RichHandler(
        console=_colour_console(buffer=buffer),
        show_time=config.is_show_time,
        show_level=config.is_show_level,
        show_path=config.is_show_path,
        enable_link_path=config.is_link_path_enabled,
        highlighter=highlighter,
        markup=True,
        rich_tracebacks=config.is_rich_tracebacks,
        tracebacks_word_wrap=config.is_tracebacks_word_wrap,
        tracebacks_show_locals=config.is_tracebacks_show_locals,
        tracebacks_suppress=config.tracebacks_suppress,
        keywords=config.keywords_to_hilight,
    )
    handler.setFormatter(logging.Formatter())
    return handler


@pytest.mark.asyncio
class TestLiveRunPipeAnnouncement:
    @pytest.mark.parametrize(("pipe_stack", "pipe_depth"), PIPE_STACKS, ids=PIPE_STACK_IDS)
    async def test_the_announcement_is_a_fixed_message_with_the_pipe_in_its_fields(
        self, caplog: pytest.LogCaptureFixture, pipe_stack: list[str], pipe_depth: int
    ) -> None:
        record = await _announcement(caplog=caplog, pipe_stack=pipe_stack)

        assert find_markup_tags(text=record.getMessage()) == []
        assert {name: getattr(record, name) for name in ANNOUNCEMENT_FIELDS} == {
            "pipe_type": "QuietPipe",
            "pipe_code": PIPE_CODE,
            "output_concept": "Text",
            "pipe_depth": pipe_depth,
        }
        assert not hasattr(record, "is_dry_run"), "only a live run announces itself, so the announcement carries no run mode"
        assert record.__dict__[LAYOUT_MARK] == LogLayout.PIPE_RUN

    @pytest.mark.parametrize(("pipe_stack", "pipe_depth"), PIPE_STACKS, ids=PIPE_STACK_IDS)
    async def test_the_console_prints_the_line_the_markup_announcement_printed_byte_for_byte(
        self, caplog: pytest.LogCaptureFixture, pipe_stack: list[str], pipe_depth: int
    ) -> None:
        """The indentation, the `↳`, `QuietPipe: compose_company → Text` and every colour code, as the markup message printed them."""
        record = await _announcement(caplog=caplog, pipe_stack=pipe_stack)
        config = _console_rich_log_config()
        markup_record = logging.LogRecord(
            name=record.name,
            level=record.levelno,
            pathname=record.pathname,
            lineno=record.lineno,
            msg=_markup_announcement(pipe=_make_pipe(), pipe_stack=pipe_stack),
            args=(),
            exc_info=None,
        )
        reference_buffer = io.StringIO()
        _markup_reading_handler(config=config, buffer=reference_buffer).handle(markup_record)
        buffer = io.StringIO()
        handler = ConsoleLogSink(rich_log_config=config, target=ConsoleTarget.STDERR).handler
        assert isinstance(handler, RichHandler)
        handler.console = _colour_console(buffer=buffer)

        handler.handle(record)

        rendered = buffer.getvalue()
        assert "\x1b[" in rendered, "the comparison is only worth something with the colour codes in it"
        assert f"{'   ' * pipe_depth}{'↳ ' if pipe_depth else ''}QuietPipe: {PIPE_CODE} → Text" in Text.from_ansi(rendered).plain
        assert rendered == reference_buffer.getvalue()

    async def test_the_json_sink_writes_the_plain_message_and_the_pipe_as_keys(self, caplog: pytest.LogCaptureFixture) -> None:
        record = await _announcement(caplog=caplog, pipe_stack=["build_profile", PIPE_CODE])
        buffer = io.StringIO()

        JsonLogSink(stream=buffer).handler.handle(record)

        line: dict[str, Any] = json.loads(buffer.getvalue())
        assert line[MESSAGE_KEY] == PIPE_RUN_STARTS_MESSAGE
        assert {name: line[name] for name in ANNOUNCEMENT_FIELDS} == {
            "pipe_type": "QuietPipe",
            "pipe_code": PIPE_CODE,
            "output_concept": "Text",
            "pipe_depth": 1,
        }
        assert "is_dry_run" not in line
        assert LogLayout.PIPE_RUN not in line.values()

    async def test_a_dry_run_mode_is_refused_before_anything_is_announced(self, caplog: pytest.LogCaptureFixture) -> None:
        """Only `run_pipe`'s live case calls it, but it is public: a dry run handed to it would announce itself and open a span."""
        pipe_run_params = _pipe_run_params(run_mode=PipeRunMode.DRY, pipe_stack=[PIPE_CODE])

        with (
            caplog.at_level(logging.INFO, logger=PipeAbstract.__module__),
            pytest.raises(AssertionError, match=rf"^Live run of PipeFunc '{PIPE_CODE}' called with run_mode = dry$"),
        ):
            await _make_pipe().live_run_pipe(
                job_metadata=_job_metadata(), working_memory=WorkingMemoryFactory.make_empty(), pipe_run_params=pipe_run_params
            )

        assert not [record for record in caplog.records if record.getMessage() == PIPE_RUN_STARTS_MESSAGE]
