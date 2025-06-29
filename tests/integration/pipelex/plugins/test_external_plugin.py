from typing import Type

import pytest
from polyfactory.factories.pydantic_factory import ModelFactory
from typing_extensions import override

from pipelex import pretty_print
from pipelex.cogt.llm.llm_job import LLMJob
from pipelex.cogt.llm.llm_job_components import LLMJobParams
from pipelex.cogt.llm.llm_job_factory import LLMJobFactory
from pipelex.cogt.llm.llm_worker_abstract import LLMWorkerAbstract
from pipelex.cogt.llm.llm_worker_factory import LLMWorkerFactory
from pipelex.cogt.llm.token_category import NbTokensByCategoryDict, TokenCategory
from pipelex.hub import get_inference_manager, get_plugin_manager, get_report_delegate
from pipelex.tools.typing.pydantic_utils import BaseModelTypeVar
from tests.integration.pipelex.cogt.test_data import LLMTestConstants, Person

EXTERNAL_PLUGIN_NAME = "mock_external_llm"


class MockExternalLLMWorker(LLMWorkerAbstract):
    @property
    @override
    def is_gen_object_supported(self) -> bool:
        return True

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
    async def test_external_plugin(self):
        plugin_name = EXTERNAL_PLUGIN_NAME
        get_plugin_manager().register_plugin(name=plugin_name, plugin_class=MockExternalLLMWorker)
        llm_worker = LLMWorkerFactory.make_llm_worker_from_external_plugin(
            external_plugin_name=plugin_name,
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
        generated_text = await llm_worker.gen_text(llm_job=llm_job)
        assert generated_text
        pretty_print(generated_text)
        generated_object = await llm_worker.gen_object(llm_job=llm_job, schema=Person)
        assert generated_object
        pretty_print(generated_object)

    async def test_external_llm_handle(self):
        plugin_name = EXTERNAL_PLUGIN_NAME
        get_plugin_manager().register_plugin(name=plugin_name, plugin_class=MockExternalLLMWorker)
        llm_external_worker = LLMWorkerFactory.make_llm_worker_from_external_plugin(
            external_plugin_name=plugin_name,
            reporting_delegate=get_report_delegate(),
        )
        inference_manager = get_inference_manager()
        llm_handle = plugin_name
        inference_manager.set_llm_worker(llm_handle=llm_handle, llm_worker=llm_external_worker)
        llm_worker = inference_manager.get_llm_worker(llm_handle=llm_handle)
        llm_job = LLMJobFactory.make_llm_job_from_prompt_contents(
            system_text=None,
            user_text=LLMTestConstants.USER_TEXT_SHORT,
            llm_job_params=LLMJobParams(
                temperature=0.5,
                max_tokens=None,
                seed=None,
            ),
        )
        generated_text = await llm_worker.gen_text(llm_job=llm_job)
        assert generated_text
        pretty_print(generated_text)
        generated_object = await llm_worker.gen_object(llm_job=llm_job, schema=Person)
        assert generated_object
        pretty_print(generated_object)

    async def test_pipe_llm_with_external_llm_handle(self):
        plugin_name = EXTERNAL_PLUGIN_NAME
        get_plugin_manager().register_plugin(name=plugin_name, plugin_class=MockExternalLLMWorker)
        llm_external_worker = LLMWorkerFactory.make_llm_worker_from_external_plugin(
            external_plugin_name=plugin_name,
            reporting_delegate=get_report_delegate(),
        )
        inference_manager = get_inference_manager()
        llm_handle = plugin_name
        inference_manager.set_llm_worker(llm_handle=llm_handle, llm_worker=llm_external_worker)
        llm_worker = inference_manager.get_llm_worker(llm_handle=llm_handle)
        llm_job = LLMJobFactory.make_llm_job_from_prompt_contents(
            system_text=None,
            user_text=LLMTestConstants.USER_TEXT_SHORT,
            llm_job_params=LLMJobParams(
                temperature=0.5,
                max_tokens=None,
                seed=None,
            ),
        )
        generated_text = await llm_worker.gen_text(llm_job=llm_job)
        assert generated_text
        pretty_print(generated_text)
        generated_object = await llm_worker.gen_object(llm_job=llm_job, schema=Person)
        assert generated_object
        pretty_print(generated_object)
