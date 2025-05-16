# SPDX-FileCopyrightText: © 2025 Evotis S.A.S.
# SPDX-License-Identifier: Elastic-2.0
# "Pipelex" is a trademark of Evotis S.A.S.


import pytest

from pipelex import log, pretty_print
from pipelex.core.domain import SpecialDomain
from pipelex.core.stuff import Stuff
from pipelex.core.stuff_content import ImageContent, StructuredContent
from pipelex.core.stuff_factory import StuffFactory
from pipelex.core.working_memory import WorkingMemory
from pipelex.core.working_memory_factory import WorkingMemoryFactory
from pipelex.hub import get_report_delegate
from pipelex.pipe_operators.pipe_llm import PipeLLM, PipeLLMOutput
from pipelex.pipe_operators.pipe_llm_prompt import PipeLLMPrompt
from pipelex.pipe_works.pipe_job_factory import PipeJobFactory
from pipelex.pipe_works.pipe_router_protocol import PipeRouterProtocol
from tests.pipelex.test_data import PipeTestCases


@pytest.mark.llm
@pytest.mark.inference
@pytest.mark.asyncio(loop_scope="class")
class TestPipeLLM:
    async def test_pipe_llm(self, pipe_router: PipeRouterProtocol):
        pipe_job = PipeJobFactory.make_pipe_job(
            pipe=PipeLLM(
                code="adhoc_for_test_pipe_llm",
                domain="generic",
                output_concept_code=f"{SpecialDomain.NATIVE}.Text",
                pipe_llm_prompt=PipeLLMPrompt(
                    code="adhoc_for_test_pipe_llm",
                    domain="generic",
                    system_prompt=PipeTestCases.SYSTEM_PROMPT,
                    user_text=PipeTestCases.USER_PROMPT,
                ),
            ),
        )
        pipe_llm_output: PipeLLMOutput = await pipe_router.run_pipe_job(
            pipe_job=pipe_job,
        )

        log.verbose(pipe_llm_output, title="stuff")
        llm_generated_text = pipe_llm_output.main_stuff_as_text
        pretty_print(llm_generated_text, title="llm_generated_text")
        get_report_delegate().general_report()

    @pytest.mark.llm
    @pytest.mark.inference
    @pytest.mark.asyncio(loop_scope="class")
    async def test_pipe_llm_image(self, pipe_router: PipeRouterProtocol):
        class ImageWrapper(StructuredContent):
            image: ImageContent

        image_wrapper = ImageWrapper(image=ImageContent(url="https://www.google.com/images/branding/googlelogo/1x/googlelogo_color_272x92dp.png"))
        image_wrapper_stuff = StuffFactory.make_stuff(
            concept_code="native.Image",
            content=image_wrapper,
        )
        working_memory = WorkingMemoryFactory.make_from_stuff_and_name(stuff=image_wrapper_stuff, name="image_wrapper")

        pipe_job = PipeJobFactory.make_pipe_job(
            working_memory=working_memory,
            pipe=PipeLLM(
                code="adhoc_for_test_pipe_llm",
                domain="generic",
                output_concept_code=f"{SpecialDomain.NATIVE}.Text",
                pipe_llm_prompt=PipeLLMPrompt(
                    code="adhoc_for_test_pipe_llm",
                    domain="generic",
                    system_prompt=PipeTestCases.SYSTEM_PROMPT,
                    user_text=PipeTestCases.IMG_DESC_PROMPT,
                    user_images=["image_wrapper.image"],
                ),
            ),
        )
        pipe_llm_output: PipeLLMOutput = await pipe_router.run_pipe_job(
            pipe_job=pipe_job,
        )

        log.verbose(pipe_llm_output, title="stuff")
        llm_generated_text = pipe_llm_output.main_stuff_as_text
        pretty_print(llm_generated_text, title="llm_generated_text")
        get_report_delegate().general_report()
