import random

import pytest

from pipelex import pretty_print
from pipelex.cogt.llm.llm_job import LLMJobParams
from pipelex.cogt.llm.llm_job_factory import LLMJobFactory
from pipelex.cogt.llm.llm_prompt_template import LLMPromptTemplate
from pipelex.hub import get_llm_worker
from tests.integration.pipelex.cogt.test_data import LLMTestConstants


@pytest.mark.asyncio(loop_scope="class")
class TestAsyncLLMJobFactory:
    async def test_llm_job_using_generic_prompt_factory(self):
        llm_prompt_template = LLMPromptTemplate.from_template_contents(user_text=LLMTestConstants.PROMPT_TEMPLATE_TEXT)
        random_color = random.choice(LLMTestConstants.PROMPT_COLOR_EXAMPLES)
        llm_job = await LLMJobFactory.make_llm_job_from_prompt_factory(
            llm_prompt_factory=llm_prompt_template,
            llm_prompt_arguments={"color": random_color},
            llm_job_params=LLMJobParams(temperature=0.5, max_tokens=50, seed=None),
        )
        assert llm_job
        pretty_print(llm_job)

    async def test_llm_job_using_prompt_template(self):
        llm_prompt_template = LLMPromptTemplate.from_template_contents(user_text=LLMTestConstants.PROMPT_TEMPLATE_TEXT)
        random_color = random.choice(LLMTestConstants.PROMPT_COLOR_EXAMPLES)
        llm_job = await LLMJobFactory.make_llm_job_from_prompt_template(
            llm_prompt_template=llm_prompt_template,
            llm_prompt_arguments={"color": random_color},
            llm_job_params=LLMJobParams(temperature=0.5, max_tokens=50, seed=None),
        )
        assert llm_job
        pretty_print(llm_job)

    @pytest.mark.llm
    @pytest.mark.inference
    async def test_llm_job_and_gen_text(self, llm_handle: str):
        llm_worker = get_llm_worker(llm_handle=llm_handle)
        llm_prompt_template = LLMPromptTemplate.from_template_contents(user_text=LLMTestConstants.PROMPT_TEMPLATE_TEXT)
        random_color = random.choice(LLMTestConstants.PROMPT_COLOR_EXAMPLES)
        llm_job = await LLMJobFactory.make_llm_job_from_prompt_template(
            llm_prompt_template=llm_prompt_template,
            llm_prompt_arguments={"color": random_color},
            llm_job_params=LLMJobParams(temperature=0.5, max_tokens=50, seed=None),
        )
        generated_text = await llm_worker.gen_text(llm_job=llm_job)
        assert generated_text
        pretty_print(generated_text)
