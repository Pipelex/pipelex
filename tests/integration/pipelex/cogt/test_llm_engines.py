import pytest

from pipelex import log, pretty_print
from pipelex.cogt.llm.llm_job import LLMJob
from pipelex.cogt.llm.llm_job_components import LLMJobParams
from pipelex.cogt.llm.llm_job_factory import LLMJobFactory
from pipelex.cogt.llm.llm_worker_abstract import LLMWorkerAbstract
from pipelex.hub import get_inference_manager
from tests.integration.pipelex.cogt.test_data import LLMTestConstants, Person


@pytest.mark.llm
@pytest.mark.inference
@pytest.mark.asyncio(loop_scope="class")
class TestLLMEngines:
    async def run_inference(self, llm_worker: LLMWorkerAbstract, llm_job: LLMJob):
        generated_text = await llm_worker.gen_text(llm_job=llm_job)
        assert generated_text
        pretty_print(generated_text)
        if llm_worker.is_gen_object_supported:
            generated_object = await llm_worker.gen_object(llm_job=llm_job, schema=Person)
            assert generated_object
            pretty_print(generated_object)
        else:
            log.info(f"No object generation supported for this worker: '{llm_worker.desc}'")

    async def test_one_llm_engine_by_llm_handle(self, llm_job_params: LLMJobParams, llm_handle: str):
        log.info(f"Testing llm_handle '{llm_handle}'")
        inference_manager = get_inference_manager()
        llm_worker = inference_manager.get_llm_worker(llm_handle=llm_handle)
        log.info(f"Using llm_worker: {llm_worker.desc}")
        llm_job = LLMJobFactory.make_llm_job_from_prompt_contents(
            system_text=None,
            user_text=LLMTestConstants.USER_TEXT_SHORT,
            llm_job_params=llm_job_params,
        )
        await self.run_inference(llm_worker=llm_worker, llm_job=llm_job)
