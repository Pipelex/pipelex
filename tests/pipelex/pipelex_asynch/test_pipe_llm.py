from typing import List

import pytest

from pipelex import log, pretty_print
from pipelex.core.concept_native import NativeConcept
from pipelex.core.stuff import Stuff
from pipelex.core.working_memory_factory import WorkingMemoryFactory
from pipelex.hub import get_pipe_router, get_report_delegate
from pipelex.pipe_operators.pipe_llm import PipeLLM, PipeLLMOutput
from pipelex.pipe_operators.pipe_llm_prompt import PipeLLMPrompt
from pipelex.pipe_works.pipe_job_factory import PipeJobFactory
from tests.pipelex.test_data import PipeTestCases


@pytest.mark.llm
@pytest.mark.inference
@pytest.mark.asyncio(loop_scope="class")
class TestPipeLLM:
    async def test_pipe_llm(self):
        pipe_job = PipeJobFactory.make_pipe_job(
            pipe=PipeLLM(
                code="adhoc_for_test_pipe_llm",
                domain="generic",
                output_concept_code=NativeConcept.TEXT.code,
                pipe_llm_prompt=PipeLLMPrompt(
                    code="adhoc_for_test_pipe_llm",
                    domain="generic",
                    system_prompt=PipeTestCases.SYSTEM_PROMPT,
                    user_text=PipeTestCases.USER_PROMPT,
                ),
            ),
        )
        pipe_llm_output: PipeLLMOutput = await get_pipe_router().run_pipe_job(
            pipe_job=pipe_job,
        )

        log.verbose(pipe_llm_output, title="stuff")
        llm_generated_text = pipe_llm_output.main_stuff_as_text
        pretty_print(llm_generated_text, title="llm_generated_text")
        get_report_delegate().generate_report()

    @pytest.mark.llm
    @pytest.mark.inference
    @pytest.mark.asyncio(loop_scope="class")
    @pytest.mark.parametrize("stuff, attribute_paths", PipeTestCases.STUFFS_IMAGE_ATTRIBUTES)
    async def test_pipe_llm_attribute_image(
        self,
        stuff: Stuff,
        attribute_paths: List[str],
    ):
        working_memory = WorkingMemoryFactory.make_from_single_stuff(stuff=stuff)

        pipe_job = PipeJobFactory.make_pipe_job(
            working_memory=working_memory,
            pipe=PipeLLM(
                code="adhoc_for_test_pipe_llm_image",
                domain="generic",
                output_concept_code=NativeConcept.TEXT.code,
                pipe_llm_prompt=PipeLLMPrompt(
                    code="adhoc_for_test_pipe_llm_image",
                    domain="generic",
                    system_prompt=PipeTestCases.SYSTEM_PROMPT,
                    user_text=PipeTestCases.MULTI_IMG_DESC_PROMPT,
                    user_images=attribute_paths,
                ),
            ),
        )
        pipe_llm_output: PipeLLMOutput = await get_pipe_router().run_pipe_job(
            pipe_job=pipe_job,
        )

        log.verbose(pipe_llm_output, title="stuff")
        llm_generated_text = pipe_llm_output.main_stuff_as_text
        pretty_print(llm_generated_text, title="llm_generated_text")
        get_report_delegate().generate_report()
