import asyncio
from typing import List

import pytest

from pipelex import pretty_print
from pipelex.cogt.llm.llm_job_factory import LLMJobFactory
from pipelex.hub import get_llm_worker, get_models_manager, get_report_delegate
from tests.integration.pipelex.cogt.test_data import LLMTestCases


@pytest.mark.asyncio
async def test_llm_report_without_running_anything():
    get_report_delegate().generate_report()


@pytest.mark.llm
@pytest.mark.inference
@pytest.mark.asyncio(loop_scope="class")
class TestLLMReport:
    @pytest.mark.parametrize("topic, prompt_text", LLMTestCases.SINGLE_TEXT)
    async def test_llm_report_single(self, llm_preset_id: str, topic: str, prompt_text: str):
        llm_worker, llm_job = self._get_async_worker_and_job(llm_preset_id=llm_preset_id, prompt_text=prompt_text)
        generated_text = await llm_worker.gen_text(llm_job=llm_job)
        assert generated_text
        pretty_print(generated_text)
        get_report_delegate().generate_report()

    def _get_async_worker_and_job(self, llm_preset_id: str, prompt_text: str):
        llm_setting = get_models_manager().get_llm_deck().get_llm_setting(llm_setting_or_preset_id=llm_preset_id)
        pretty_print(llm_setting, title=llm_preset_id)
        pretty_print(prompt_text)
        llm_worker = get_llm_worker(llm_handle=llm_setting.llm_handle)
        llm_job_params = llm_setting.make_llm_job_params()
        llm_job = LLMJobFactory.make_llm_job_from_prompt_contents(
            user_text=prompt_text,
            llm_job_params=llm_job_params,
        )
        return llm_worker, llm_job

    async def test_llm_report_multiple(self):
        nb_generations = 3
        prompt_text = LLMTestCases.USER_TEXT_HAIKU
        llm_preset_ids = [
            "llm_for_testing_gen_text",
            "llm_for_testing_gen_object",
        ]
        tasks: List[asyncio.Task[str]] = []
        for llm_preset_id in llm_preset_ids:
            llm_worker, llm_job = self._get_async_worker_and_job(llm_preset_id=llm_preset_id, prompt_text=prompt_text)
            job_params_base = llm_job.job_params
            max_tokens = 30
            for _ in range(nb_generations):
                max_tokens += 50
                job_params = job_params_base.model_copy(update={"max_tokens": max_tokens})
                llm_job = llm_job.model_copy(update={"job_params": job_params})
                task: asyncio.Task[str] = asyncio.create_task(llm_worker.gen_text(llm_job=llm_job))
                tasks.append(task)
        generated_texts = await asyncio.gather(*tasks)
        pretty_print(generated_texts)

        get_report_delegate().generate_report()
