from typing import Type

import pytest
from polyfactory.factories.pydantic_factory import ModelFactory
from typing_extensions import override

from pipelex import log, pretty_print
from pipelex.cogt.llm.llm_job import LLMJob
from pipelex.cogt.llm.llm_job_components import LLMJobParams
from pipelex.cogt.llm.llm_job_factory import LLMJobFactory
from pipelex.cogt.llm.llm_models.llm_engine import LLMEngine
from pipelex.cogt.llm.llm_models.llm_family import LLMFamily
from pipelex.cogt.llm.llm_models.llm_model import LATEST_VERSION_NAME, LLMModel
from pipelex.cogt.llm.llm_models.llm_platform import LLMPlatform
from pipelex.cogt.llm.llm_worker_abstract import LLMWorkerAbstract
from pipelex.cogt.llm.llm_worker_factory import LLMWorkerFactory
from pipelex.cogt.llm.token_category import NbTokensByCategoryDict, TokenCategory
from pipelex.hub import get_plugin_manager, get_report_delegate
from pipelex.tools.typing.pydantic_utils import BaseModelTypeVar
from tests.integration.pipelex.cogt.test_data import LLMTestConstants, Person

EXTERNAL_PLUGIN_NAME = "mock_external_llm"


class MockExternalLLMWorker(LLMWorkerAbstract):
    @override
    async def _gen_text(
        self,
        llm_job: LLMJob,
    ) -> str:
        response_text = f"This is a mock LLM response from '{self.__class__}'"

        if llm_tokens_usage := llm_job.job_report.llm_tokens_usage:
            nb_tokens_by_category: NbTokensByCategoryDict = {
                TokenCategory.INPUT: 100,
                TokenCategory.OUTPUT: 100,
            }
            llm_tokens_usage.nb_tokens_by_category = nb_tokens_by_category
        return response_text

    @override
    async def _gen_object(
        self,
        llm_job: LLMJob,
        schema: Type[BaseModelTypeVar],
    ) -> BaseModelTypeVar:
        class ObjectFactory(ModelFactory[schema]):  # type: ignore
            __model__ = schema
            __use_examples__ = True

        obj = ObjectFactory.build()
        return obj


@pytest.mark.asyncio(loop_scope="class")
class TestExternalPlugin:
    async def run_inference(self, llm_worker: LLMWorkerAbstract, llm_job: LLMJob):
        generated_text = await llm_worker.gen_text(llm_job=llm_job)
        assert generated_text
        pretty_print(generated_text)
        llm_model = llm_worker.llm_engine.llm_model
        if llm_model.is_gen_object_supported:
            generated_object = await llm_worker.gen_object(llm_job=llm_job, schema=Person)
            assert generated_object
            pretty_print(generated_object)
        else:
            log.info(f"No object generation supported for this model: '{llm_model.name_and_version_and_platform}'")

    async def test_external_plugin(self):
        get_plugin_manager().register_plugin(name=EXTERNAL_PLUGIN_NAME, plugin_class=MockExternalLLMWorker)

        llm_engine = LLMEngine(
            llm_platform=LLMPlatform.SPECIFIC_LLM,
            llm_model=LLMModel(
                llm_name=EXTERNAL_PLUGIN_NAME,
                version=LATEST_VERSION_NAME,
                default_platform=LLMPlatform.SPECIFIC_LLM,
                llm_family=LLMFamily.SPECIFIC,
                is_gen_object_supported=True,
                platform_llm_id={LLMPlatform.SPECIFIC_LLM: EXTERNAL_PLUGIN_NAME},
                max_prompt_images=0,
            ),
        )
        llm_worker_factory = LLMWorkerFactory()
        llm_worker = llm_worker_factory.make_llm_worker(
            llm_engine=llm_engine,
            reporting_delegate=get_report_delegate(),
        )
        llm_job = LLMJobFactory.make_llm_job_from_prompt_contents(
            system_text=None,
            user_text=LLMTestConstants.USER_TEXT_SHORT,
            llm_job_params=LLMJobParams(
                temperature=0.5,
                max_tokens=None,
                seed=None,
            ),
        )
        await self.run_inference(llm_worker=llm_worker, llm_job=llm_job)
