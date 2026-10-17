import io
import json
import logging
from collections.abc import Generator
from contextlib import contextmanager
from typing import Any

import pytest
from mthds.protocol.problem.registry import CoreCode
from pytest_mock import MockerFixture
from typing_extensions import override

from pipelex.base_exceptions import PipelexError
from pipelex.cogt.llm.llm_job import LLMJob
from pipelex.cogt.llm.llm_worker_abstract import LLMWorkerAbstract
from pipelex.cogt.llm.thinking_mode import ThinkingMode
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.cogt.model_backends.model_type import ModelType
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.stuffs.text_content import TextContent
from pipelex.errors.error_codes import ErrorCode
from pipelex.errors.problem import ProblemView, problem_metadata
from pipelex.pipeline.runner import PipelexMTHDSProtocol
from pipelex.system.registries.func_registry import pipe_func
from pipelex.tools.log.json_log_sink import JsonLogSink
from pipelex.tools.log.log_levels import LOGGING_LEVEL_VERBOSE
from pipelex.tools.typing.pydantic_utils import BaseModelTypeVar
from tests.integration.pipelex.pipeline.test_data import RunContentMarkerTestData

# No `from __future__ import annotations`: the function a `PipeFunc` calls has its annotations read when it is bound.
MARKER = RunContentMarkerTestData.MARKER


@pipe_func()
def run_content_quote_the_note(working_memory: WorkingMemory) -> TextContent:
    """A method's function refusing its input in a message that quotes it, as a function's own code is free to."""
    note = working_memory.get_stuff_as_str(name="note")
    msg = f"cannot file the note {note!r}"
    raise ValueError(msg)


class MarkerAnsweringLLMWorker(LLMWorkerAbstract):
    """Answers every generation with the marker, which a structure's integer field refuses."""

    @override
    async def _gen_text(self, llm_job: LLMJob) -> str:
        return MARKER

    @override
    async def _gen_object(self, llm_job: LLMJob, *, schema: type[BaseModelTypeVar]) -> BaseModelTypeVar:
        return schema.model_validate(dict.fromkeys(schema.model_fields, MARKER))


def _marker_answering_worker() -> MarkerAnsweringLLMWorker:
    inference_model = InferenceModelSpec(
        backend_name="stand_in",
        name="stand-in-llm",
        sdk="stand_in",
        model_type=ModelType.LLM,
        model_id="stand-in-llm-1",
        inputs=["text"],
        outputs=["text", "structured"],
        costs={},
        thinking_mode=ThinkingMode.NONE,
        max_tokens=None,
        max_prompt_images=None,
    )
    return MarkerAnsweringLLMWorker(inference_model=inference_model, reporting_delegate=None)


@contextmanager
def _json_sink_on_root(*, buffer: io.StringIO) -> Generator[None]:
    """The ``json`` sink's handler on the root logger, beside whatever the session installed, for as long as the block runs."""
    handler = JsonLogSink(stream=buffer).handler
    root_logger = logging.getLogger()
    root_logger.addHandler(handler)
    try:
        yield
    finally:
        root_logger.removeHandler(handler)
        handler.close()


def _cause_chain(error: BaseException) -> list[BaseException]:
    """The error and every exception below it, by ``__cause__`` or else ``__context__``."""
    chain: list[BaseException] = []
    current: BaseException | None = error
    while current is not None and current not in chain:
        chain.append(current)
        current = current.__cause__ or current.__context__
    return chain


@pytest.mark.asyncio(loop_scope="class")
class TestRunContentStaysOutOfSinks:
    @pytest.mark.parametrize(
        ("topic", "pipe_code", "inputs", "expected_code", "is_quoted_below"),
        [
            ("a number input given a text", "echo_amount", {"amount": MARKER}, CoreCode.INPUT_INVALID, False),
            ("a structure refusing a field's value", "echo_tally", {"tally": {"count": MARKER}}, CoreCode.INPUT_INVALID, True),
            (
                "an explicit envelope its structure refuses",
                "echo_tally",
                {"tally": {"concept": "run_content_marker.Tally", "content": {"count": MARKER}}},
                CoreCode.INPUT_INVALID,
                True,
            ),
            ("a date the content factory cannot read", "echo_date", {"when": MARKER}, CoreCode.INPUT_INVALID, False),
            ("a function quoting its input", "file_note", {"note": MARKER}, CoreCode.PIPE_FUNCTION_RAISED, True),
            ("a value the composer copied into a choice", "make_ticket", {"level": MARKER}, CoreCode.PIPE_OUTPUT_INVALID, True),
            ("a model answer the structure refuses", "count_notes", {"note": "three apples"}, CoreCode.RUNTIME_UNEXPECTED, True),
        ],
    )
    async def test_the_run_s_data_reaches_no_log_record_and_no_view(
        self,
        mocker: MockerFixture,
        caplog: pytest.LogCaptureFixture,
        topic: str,
        pipe_code: str,
        inputs: dict[str, Any],
        expected_code: ErrorCode,
        is_quoted_below: bool,
    ) -> None:
        """A run whose data holds a marker fails at one family of raise site, and the marker reaches no sink.

        Every log record the run wrote, at the lowest level and as the ``json`` sink writes it, the failure's message and
        every view of its problem are read for the marker. Where a foreign exception below the failure, pydantic's or the
        method function's, does quote it, the case says so, which proves the raise sites above kept it out.
        """
        mocker.patch("pipelex.cogt.content_generation.llm_generate.get_llm_worker", return_value=_marker_answering_worker())
        # Every Pipelex logger down to the lowest level; `caplog` puts the level back afterwards.
        caplog.set_level(LOGGING_LEVEL_VERBOSE, logger="pipelex")
        buffer = io.StringIO()

        with _json_sink_on_root(buffer=buffer), pytest.raises(PipelexError) as exc_info:
            await PipelexMTHDSProtocol().execute(pipe_code=pipe_code, mthds_contents=[RunContentMarkerTestData.MTHDS], inputs=inputs)

        error = exc_info.value
        operator = error.to_problem(view=ProblemView.OPERATOR)
        # The run failed where the case aims, on its data and on nothing else.
        assert operator.code == expected_code, topic
        assert any(MARKER in str(cause) for cause in _cause_chain(error)) is is_quoted_below, topic

        assert MARKER not in error.message, topic
        assert MARKER not in json.dumps(operator.to_wire()), topic
        assert MARKER not in json.dumps(error.to_problem(view=ProblemView.CALLER).to_wire()), topic
        assert MARKER not in json.dumps(problem_metadata(problem=operator).to_wire()), topic
        json_lines = [line for line in buffer.getvalue().splitlines() if line]
        assert json_lines, topic
        assert [line for line in json_lines if MARKER in line] == [], topic
        assert [record.getMessage() for record in caplog.records if MARKER in str(vars(record))] == [], topic

    async def test_a_library_logging_the_run_s_data_reaches_no_sink(self) -> None:
        """`instructor` logs each refused answer, which quotes the model's text: no sink of Pipelex writes its records."""
        buffer = io.StringIO()
        instructor_logger = logging.getLogger("instructor.core.retry")
        pipelex_logger = logging.getLogger("pipelex.marker_probe")
        previous_levels = (instructor_logger.level, pipelex_logger.level)
        instructor_logger.setLevel(logging.DEBUG)
        pipelex_logger.setLevel(logging.DEBUG)
        try:
            with _json_sink_on_root(buffer=buffer):
                instructor_logger.error("Validation error on attempt 1: count, input_value='%s'", MARKER)
                pipelex_logger.error("A line of Pipelex's own reaches the sink")
        finally:
            instructor_logger.setLevel(previous_levels[0])
            pipelex_logger.setLevel(previous_levels[1])

        json_lines = [line for line in buffer.getvalue().splitlines() if line]
        assert [json.loads(line)["message"] for line in json_lines] == ["A line of Pipelex's own reaches the sink"]
        assert [line for line in json_lines if MARKER in line] == []
