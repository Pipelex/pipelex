from typing import List

import pytest

from pipelex import log, pretty_print
from pipelex.core.concepts.concept_native import NativeConceptEnum
from pipelex.core.domains.domain import SpecialDomain
from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory
from pipelex.core.pipes.pipe_input_spec_blueprint import InputRequirementBlueprint
from pipelex.core.pipes.pipe_run_params import PipeRunMode
from pipelex.core.pipes.pipe_run_params_factory import PipeRunParamsFactory
from pipelex.core.stuffs.stuff import Stuff
from pipelex.hub import get_pipe_router, get_report_delegate
from pipelex.pipe_operators.llm.pipe_llm import PipeLLMOutput
from pipelex.pipe_operators.llm.pipe_llm_blueprint import PipeLLMBlueprint
from pipelex.pipe_operators.llm.pipe_llm_factory import PipeLLMFactory
from pipelex.pipe_works.pipe_job_factory import PipeJobFactory
from tests.integration.pipelex.test_data import PipeTestCases


@pytest.mark.dry_runnable
@pytest.mark.llm
@pytest.mark.inference
@pytest.mark.asyncio(loop_scope="class")
class TestPipeLLM:
    async def test_pipe_llm(
        self,
        pipe_run_mode: PipeRunMode,
    ):
        pipe_llm_blueprint = PipeLLMBlueprint(
            definition="LLM test for basic text generation",
            output=NativeConceptEnum.TEXT.value,
            system_prompt=PipeTestCases.SYSTEM_PROMPT,
            prompt=PipeTestCases.USER_PROMPT,
        )

        pipe_job = PipeJobFactory.make_pipe_job(
            pipe=PipeLLMFactory.make_from_blueprint(
                domain="generic",
                pipe_code="adhoc_for_test_pipe_llm",
                blueprint=pipe_llm_blueprint,
            ),
            pipe_run_params=PipeRunParamsFactory.make_run_params(pipe_run_mode=pipe_run_mode),
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
        pipe_run_mode: PipeRunMode,
    ):
        for attribute_path in attribute_paths:
            stuff_name = attribute_path
            if not stuff_name:
                pytest.fail(f"Cannot use nameless stuff in this test: {stuff}")
            working_memory = WorkingMemoryFactory.make_from_single_stuff(stuff=stuff)
            pipe_llm_blueprint = PipeLLMBlueprint(
                definition="LLM test for image processing with attributes",
                inputs={stuff_name: InputRequirementBlueprint(concept=stuff.concept.concept_string)},
                output=f"{SpecialDomain.NATIVE.value}.{NativeConceptEnum.TEXT.value}",
                system_prompt=PipeTestCases.SYSTEM_PROMPT,
                prompt=PipeTestCases.MULTI_IMG_DESC_PROMPT,
            )

            pipe_job = PipeJobFactory.make_pipe_job(
                working_memory=working_memory,
                pipe=PipeLLMFactory.make_from_blueprint(
                    domain="generic",
                    pipe_code="adhoc_for_test_pipe_llm_image",
                    blueprint=pipe_llm_blueprint,
                ),
                pipe_run_params=PipeRunParamsFactory.make_run_params(pipe_run_mode=pipe_run_mode),
            )

            pipe_llm_output: PipeLLMOutput = await get_pipe_router().run_pipe_job(
                pipe_job=pipe_job,
            )

            log.verbose(pipe_llm_output, title="stuff")
            llm_generated_text = pipe_llm_output.main_stuff_as_text
            pretty_print(llm_generated_text, title="llm_generated_text")
            get_report_delegate().generate_report()
