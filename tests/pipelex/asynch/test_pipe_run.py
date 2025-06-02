from typing import cast

import pytest

from pipelex import log, pretty_print
from pipelex.core.pipe_output import PipeOutput
from pipelex.core.stuff_content import ListContent, TextContent
from pipelex.core.working_memory_factory import WorkingMemoryFactory
from pipelex.hub import get_report_delegate
from pipelex.run import run_pipe_code
from tests.pipelex.test_data import PipeTestCases


@pytest.mark.llm
@pytest.mark.ocr
@pytest.mark.inference
@pytest.mark.asyncio(loop_scope="class")
class TestPipeRun:
    async def test_pipe_run(self):
        working_memory = WorkingMemoryFactory.make_from_text(
            text=PipeTestCases.USER_TEXT_COLORS,
        )
        pipe_output: PipeOutput = await run_pipe_code(
            pipe_code="extract_colors",
            working_memory=working_memory,
        )

        colors_list = cast(ListContent[TextContent], pipe_output.main_stuff.content)
        pretty_print(colors_list, title="colors_list")
        colors_list = pipe_output.main_stuff.as_list_of_fixed_content_type(item_type=TextContent)
        pretty_print(colors_list, title="colors_list")
        colors_list = pipe_output.main_stuff_as_list(item_type=TextContent)
        pretty_print(colors_list, title="colors_list")

    @pytest.mark.parametrize("pipe_code, input_concept_code, str_value", PipeTestCases.SIMPLE_PIPE_RUN_FROM_STR)
    async def test_execute_pipe_from_str(self, pipe_code: str, input_concept_code: str, str_value: str):
        working_memory = WorkingMemoryFactory.make_from_text(
            concept_code=input_concept_code,
            text=str_value,
        )
        pipe_output: PipeOutput = await run_pipe_code(
            pipe_code=pipe_code,
            working_memory=working_memory,
        )

        log.verbose(pipe_output, title="pipe_output")
        pretty_print(pipe_output, title="pipe_output")
        get_report_delegate().generate_report()
