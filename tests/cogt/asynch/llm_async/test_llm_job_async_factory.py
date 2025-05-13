# SPDX-FileCopyrightText: © 2025 Evotis S.A.S.
# SPDX-License-Identifier: Elastic-2.0
# "Pipelex" is a trademark of Evotis S.A.S.

import random

import pytest

from pipelex import pretty_print
from pipelex.cogt.llm.llm_job import LLMJobParams
from pipelex.cogt.llm.llm_job_factory import LLMJobFactory
from pipelex.cogt.llm.llm_prompt_template import LLMPromptTemplate
from pipelex.hub import get_async_llm_worker
from tests.cogt.test_data import LLMTestConstants


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
        llm_worker_async = get_async_llm_worker(llm_handle=llm_handle)
        llm_prompt_template = LLMPromptTemplate.from_template_contents(user_text=LLMTestConstants.PROMPT_TEMPLATE_TEXT)
        random_color = random.choice(LLMTestConstants.PROMPT_COLOR_EXAMPLES)
        llm_job = await LLMJobFactory.make_llm_job_from_prompt_template(
            llm_prompt_template=llm_prompt_template,
            llm_prompt_arguments={"color": random_color},
            llm_job_params=LLMJobParams(temperature=0.5, max_tokens=50, seed=None),
        )
        generated_text = await llm_worker_async.gen_text(llm_job=llm_job)
        assert generated_text
        pretty_print(generated_text)
