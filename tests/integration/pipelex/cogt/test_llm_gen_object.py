import asyncio
from typing import List, Tuple

import pytest
from pydantic import BaseModel

from pipelex import pretty_print
from pipelex.cogt.llm.llm_job_components import LLMJobParams
from pipelex.cogt.llm.llm_job_factory import LLMJobFactory
from pipelex.hub import get_llm_worker, get_models_manager
from tests.integration.pipelex.cogt.test_data import LLMTestCases


def get_async_worker_and_job(llm_preset_id: str, user_text: str):
    llm_setting = get_models_manager().get_model_deck().get_llm_setting(llm_setting_or_preset_id=llm_preset_id)
    pretty_print(llm_setting, title=llm_preset_id)
    pretty_print(user_text)
    llm_worker = get_llm_worker(llm_handle=llm_setting.llm_handle)
    llm_job_params = llm_setting.make_llm_job_params()
    llm_job = LLMJobFactory.make_llm_job_from_prompt_contents(
        user_text=user_text,
        llm_job_params=llm_job_params,
    )
    return llm_worker, llm_job


@pytest.mark.llm
@pytest.mark.inference
@pytest.mark.asyncio(loop_scope="class")
class TestLLMGenObject:
    @pytest.mark.parametrize("user_text, expected_instance", LLMTestCases.SINGLE_OBJECT)
    async def test_gen_object_async_using_handle(self, llm_job_params: LLMJobParams, llm_handle: str, user_text: str, expected_instance: BaseModel):
        llm_worker = get_llm_worker(llm_handle=llm_handle)
        if not llm_worker.is_gen_object_supported:
            pytest.skip(f"LLM worker '{llm_worker.desc}' does not support object generation")
        llm_job = LLMJobFactory.make_llm_job_from_prompt_contents(
            user_text=user_text,
            llm_job_params=llm_job_params,
        )
        expected_class = expected_instance.__class__
        output = await llm_worker.gen_object(llm_job=llm_job, schema=expected_class)
        pretty_print(output, title=f"Output from {llm_handle}")
        assert isinstance(output, expected_class)
        assert output.model_dump(serialize_as_any=True) == expected_instance.model_dump(serialize_as_any=True)

    @pytest.mark.parametrize("user_text, expected_instance", LLMTestCases.SINGLE_OBJECT)
    async def test_gen_object_async_using_llm_preset(self, llm_preset_id: str, user_text: str, expected_instance: BaseModel):
        llm_worker, llm_job = get_async_worker_and_job(llm_preset_id=llm_preset_id, user_text=user_text)
        if not llm_worker.is_gen_object_supported:
            pytest.skip(f"'{llm_worker.desc}' does not support object generation")
        expected_class = expected_instance.__class__
        output = await llm_worker.gen_object(llm_job=llm_job, schema=expected_class)
        pretty_print(output)
        assert isinstance(output, expected_class)
        assert output.model_dump(serialize_as_any=True) == expected_instance.model_dump(serialize_as_any=True)

    @pytest.mark.parametrize("case_tuples", LLMTestCases.MULTIPLE_OBJECTS)
    async def test_gen_object_async_multiple_using_handle(
        self, llm_job_params: LLMJobParams, llm_handle: str, case_tuples: List[Tuple[str, BaseModel]]
    ):
        llm_worker = get_llm_worker(llm_handle=llm_handle)
        if not llm_worker.is_gen_object_supported:
            pytest.skip(f"'{llm_worker.desc}' does not support object generation")
        tasks: List[asyncio.Task[BaseModel]] = []
        for case_tuple in case_tuples:
            user_text, expected_instance = case_tuple
            expected_class = expected_instance.__class__
            llm_job = LLMJobFactory.make_llm_job_from_prompt_contents(
                user_text=user_text,
                llm_job_params=llm_job_params,
            )
            task: asyncio.Task[BaseModel] = asyncio.create_task(llm_worker.gen_object(llm_job=llm_job, schema=expected_class))
            tasks.append(task)

        output = await asyncio.gather(*tasks)
        pretty_print(output)
        for output_index, output_instance in enumerate(output):
            expected_instance = case_tuples[output_index][1]
            expected_class = expected_instance.__class__
            assert isinstance(output_instance, expected_class)
            assert output_instance.model_dump(serialize_as_any=True) == expected_instance.model_dump(serialize_as_any=True)

    @pytest.mark.parametrize("case_tuples", LLMTestCases.MULTIPLE_OBJECTS)
    async def test_gen_object_async_multiple_using_llm_preset(self, llm_preset_id: str, case_tuples: List[Tuple[str, BaseModel]]):
        llm_worker, llm_job = get_async_worker_and_job(llm_preset_id=llm_preset_id, user_text=case_tuples[0][0])
        if not llm_worker.is_gen_object_supported:
            pytest.skip(f"'{llm_worker.desc}' does not support object generation")
        tasks: List[asyncio.Task[BaseModel]] = []
        for case_tuple in case_tuples:
            user_text, expected_instance = case_tuple
            expected_class = expected_instance.__class__
            llm_job = LLMJobFactory.make_llm_job_from_prompt_contents(
                user_text=user_text,
                llm_job_params=llm_job.job_params,
            )
            task: asyncio.Task[BaseModel] = asyncio.create_task(llm_worker.gen_object(llm_job=llm_job, schema=expected_class))
            tasks.append(task)

        output = await asyncio.gather(*tasks)
        pretty_print(output)
        for output_index, output_instance in enumerate(output):
            expected_instance = case_tuples[output_index][1]
            expected_class = expected_instance.__class__
            assert isinstance(output_instance, expected_class)
            assert output_instance.model_dump(serialize_as_any=True) == expected_instance.model_dump(serialize_as_any=True)
