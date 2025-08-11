import pytest

from pipelex import log, pretty_print
from pipelex.cogt.llm.llm_job import LLMJob
from pipelex.cogt.llm.llm_job_components import LLMJobParams
from pipelex.cogt.llm.llm_job_factory import LLMJobFactory
from pipelex.cogt.llm.llm_models.llm_engine import LLMEngine
from pipelex.cogt.llm.llm_models.llm_engine_factory import LLMEngineFactory
from pipelex.cogt.llm.llm_models.llm_family import LLMCreator, LLMFamily
from pipelex.cogt.llm.llm_models.llm_platform import LLMPlatform
from pipelex.cogt.llm.llm_worker_abstract import LLMWorkerAbstract
from pipelex.cogt.llm.llm_worker_factory import LLMWorkerFactory
from pipelex.hub import get_inference_manager, get_llm_deck, get_llm_models_provider, get_report_delegate
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
        log.info(f"Testing {llm_handle}")
        inference_manager = get_inference_manager()
        llm_worker = inference_manager.get_llm_worker(llm_handle=llm_handle)
        log.info(f"LLM Worker: {llm_worker.desc}")
        llm_job = LLMJobFactory.make_llm_job_from_prompt_contents(
            system_text=None,
            user_text=LLMTestConstants.USER_TEXT_SHORT,
            llm_job_params=llm_job_params,
        )
        await self.run_inference(llm_worker=llm_worker, llm_job=llm_job)

    async def test_one_llm_engine_by_llm_id_and_platform(self, llm_job_params: LLMJobParams, llm_id: str, llm_platform: LLMPlatform):
        log.info(f"Testing {llm_id} on {llm_platform}")
        llm_models_provider = get_llm_models_provider()
        llm_models = llm_models_provider.get_all_llm_models()
        count = 0
        for llm_model in llm_models:
            platform_llm_id = llm_model.platform_llm_id.get(llm_platform)
            if llm_id != platform_llm_id:
                continue

            llm_engine = LLMEngine(
                llm_platform=llm_platform,
                llm_model=llm_model,
            )
            llm_worker = LLMWorkerFactory.make_llm_worker(
                llm_engine=llm_engine,
                reporting_delegate=get_report_delegate(),
            )
            llm_job = LLMJobFactory.make_llm_job_from_prompt_contents(
                system_text=None,
                user_text=LLMTestConstants.USER_TEXT_SHORT,
                llm_job_params=llm_job_params,
            )
            log.info(f"Running inference for {llm_model.name_and_version_and_platform}")
            await self.run_inference(llm_worker=llm_worker, llm_job=llm_job)
            count += 1
        if count > 0:
            log.info(f"Tested {count} llm_engines for llm_id '{llm_id}' on platform '{llm_platform}'")
        else:
            pytest.fail(f"No llm_engines found for llm_id '{llm_id}' on platform '{llm_platform}'")

    async def test_llm_engines_from_one_family(self, llm_job_params: LLMJobParams, llm_family: LLMFamily):
        llm_handle_to_llm_engine_blueprint = get_llm_deck().llm_handles
        count = 0
        for _, llm_engine_blueprint in llm_handle_to_llm_engine_blueprint.items():
            llm_engine = LLMEngineFactory.make_llm_engine(llm_engine_blueprint=llm_engine_blueprint)
            if llm_engine.llm_model.llm_family != llm_family:
                continue
            llm_worker = LLMWorkerFactory.make_llm_worker(
                llm_engine=llm_engine,
                reporting_delegate=get_report_delegate(),
            )
            llm_job = LLMJobFactory.make_llm_job_from_prompt_contents(
                system_text=None,
                user_text=LLMTestConstants.USER_TEXT_SHORT,
                llm_job_params=llm_job_params,
            )
            await self.run_inference(llm_worker=llm_worker, llm_job=llm_job)
            count += 1

        log.info(f"Tested {count} llm_engines for family {llm_family}")

    async def test_llm_engines_from_one_creator(self, llm_job_params: LLMJobParams, llm_creator: LLMCreator):
        llm_handle_to_llm_engine_blueprint = get_llm_deck().llm_handles
        for _, llm_engine_blueprint in llm_handle_to_llm_engine_blueprint.items():
            llm_engine = LLMEngineFactory.make_llm_engine(llm_engine_blueprint=llm_engine_blueprint)
            if llm_engine.llm_model.llm_family.creator != llm_creator:
                continue
            llm_worker = LLMWorkerFactory.make_llm_worker(
                llm_engine=llm_engine,
                reporting_delegate=get_report_delegate(),
            )
            llm_job = LLMJobFactory.make_llm_job_from_prompt_contents(
                system_text=None,
                user_text=LLMTestConstants.USER_TEXT_SHORT,
                llm_job_params=llm_job_params,
            )
            await self.run_inference(llm_worker=llm_worker, llm_job=llm_job)

    async def test_llm_engines_from_one_platform(self, llm_job_params: LLMJobParams, llm_platform: LLMPlatform):
        llm_models_provider = get_llm_models_provider()
        llm_models = llm_models_provider.get_all_llm_models()
        for llm_model in llm_models:
            if llm_platform not in llm_model.enabled_platforms:
                continue
            llm_engine = LLMEngine(
                llm_platform=llm_platform,
                llm_model=llm_model,
            )
            llm_worker = LLMWorkerFactory.make_llm_worker(
                llm_engine=llm_engine,
                reporting_delegate=get_report_delegate(),
            )
            llm_job = LLMJobFactory.make_llm_job_from_prompt_contents(
                system_text=None,
                user_text=LLMTestConstants.USER_TEXT_SHORT,
                llm_job_params=llm_job_params,
            )
            await self.run_inference(llm_worker=llm_worker, llm_job=llm_job)

    async def test_llm_handle_to_llm_engine_default(self, llm_job_params: LLMJobParams):
        inference_manager = get_inference_manager()
        llm_handle_to_llm_engine_blueprint = get_llm_deck().llm_handles
        for llm_handle in llm_handle_to_llm_engine_blueprint.keys():
            llm_worker = inference_manager.get_llm_worker(llm_handle=llm_handle)
            assert llm_worker
            llm_job = LLMJobFactory.make_llm_job_from_prompt_contents(
                system_text=None,
                user_text=LLMTestConstants.USER_TEXT_SHORT,
                llm_job_params=llm_job_params,
            )
            assert llm_job
            # ENABLE THIS TO TEST THE INFERENCE with all base models
            # await self.run_inference(llm_worker=llm_worker, llm_job=llm_job)
