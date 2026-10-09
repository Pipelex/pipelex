"""A live run writes no log message carrying Rich markup, at any level, as the ``json`` sink receives it.

Colour is the console sink's job: it styles a record's fields by their names and draws the few named layouts,
and reads no message as markup. A message carrying a tag would reach every other sink with the tag in it, as
the pipe announcement did when a helper assembled its markup, which is exactly what a search of the log calls
cannot see. So this runs a method and reads every message the ``json`` sink was handed, at the lowest level,
for a tag Rich would apply as styling. A bracketed word that names no style, a ``list[int]``, a ``[cycle]``
marker or a backend's ``[openai]`` table, is plain text that prints as written, and passes.

The run is live, because only a live run announces its pipes, a dry one taking another path. Every model call
is answered by a stand-in worker, so nothing reaches a provider and the run costs nothing.
"""

from __future__ import annotations

import io
import json
import logging
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any

import pytest
from typing_extensions import override

from pipelex.cli.dev_cli.commands.log_call_guard import find_markup_tags
from pipelex.cogt.llm.llm_worker_abstract import LLMWorkerAbstract
from pipelex.cogt.llm.thinking_mode import ThinkingMode
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.cogt.model_backends.model_type import ModelType
from pipelex.pipe_machinery.pipe_abstract import PIPE_RUN_STARTS_MESSAGE
from pipelex.pipeline.runner import PipelexMTHDSProtocol
from pipelex.system.pipe_run_mode import PipeRunMode
from pipelex.tools.log.json_log_sink import LOGGER_KEY, MESSAGE_KEY, SEVERITY_KEY, JsonLogSink
from pipelex.tools.log.log_levels import LOGGING_LEVEL_VERBOSE, LOGGING_LEVEL_VERBOSE_NAME
from tests.integration.pipelex.pipeline.test_data import LogMarkupTestData

if TYPE_CHECKING:
    from collections.abc import Generator

    from pytest_mock import MockerFixture

    from pipelex.cogt.llm.llm_job import LLMJob
    from pipelex.tools.typing.pydantic_utils import BaseModelTypeVar

STAND_IN_ANSWER = "Acme builds reusable rockets for research labs."


class StandInLLMWorker(LLMWorkerAbstract):
    """Answers every generation without a provider: a fixed text, and an object whose every field is a fixed text."""

    @override
    async def _gen_text(self, llm_job: LLMJob) -> str:
        return STAND_IN_ANSWER

    @override
    async def _gen_object(self, llm_job: LLMJob, *, schema: type[BaseModelTypeVar]) -> BaseModelTypeVar:
        return schema.model_validate({field_name: f"Stand-in {field_name}" for field_name in schema.model_fields})


def _stand_in_worker() -> StandInLLMWorker:
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
    return StandInLLMWorker(inference_model=inference_model, reporting_delegate=None)


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


@pytest.mark.asyncio(loop_scope="class")
class TestLogMessagesCarryNoMarkup:
    async def test_a_live_run_logs_no_message_carrying_markup(self, mocker: MockerFixture, caplog: pytest.LogCaptureFixture) -> None:
        mocker.patch("pipelex.cogt.content_generation.llm_generate.get_llm_worker", return_value=_stand_in_worker())
        # Every Pipelex logger down to the lowest level; `caplog` puts the level back afterwards.
        caplog.set_level(LOGGING_LEVEL_VERBOSE, logger="pipelex")
        runner = PipelexMTHDSProtocol(pipe_run_mode=PipeRunMode.LIVE)
        buffer = io.StringIO()

        with _json_sink_on_root(buffer=buffer):
            response = await runner.execute(
                pipe_code=LogMarkupTestData.MAIN_PIPE, mthds_contents=[LogMarkupTestData.MTHDS], inputs=LogMarkupTestData.INPUTS
            )

        lines: list[dict[str, Any]] = [json.loads(line) for line in buffer.getvalue().splitlines() if line]
        assert response.pipe_output.main_stuff_as_text.text == f"Stand-in name works in Stand-in sector: {STAND_IN_ANSWER}"
        # The run was read at every level, and live: each pipe announced itself, the nested ones below the method's.
        assert any(line[SEVERITY_KEY] == LOGGING_LEVEL_VERBOSE_NAME for line in lines)
        announced = {(line["pipe_code"], line["pipe_depth"]) for line in lines if line[MESSAGE_KEY] == PIPE_RUN_STARTS_MESSAGE}
        assert announced == {
            ("profile_company", 0),
            ("describe_company", 1),
            ("structure_company", 1),
            ("summarize_company", 1),
            ("summarize_short", 2),
            ("summarize_detailed", 2),
            ("route_report", 1),
            ("compose_report", 2),
        }
        carrying_markup = [
            f"{line[LOGGER_KEY]}: {line[MESSAGE_KEY]!r} holds {find_markup_tags(text=line[MESSAGE_KEY])}"
            for line in lines
            if find_markup_tags(text=line[MESSAGE_KEY])
        ]
        assert not carrying_markup, "These log messages carry what Rich would apply as markup:\n" + "\n".join(carrying_markup)
