import asyncio

import pytest
from pydantic import BaseModel

from pipelex import pretty_print
from pipelex.cogt.llm.llm_job_components import LLMJobConfig, LLMJobParams
from pipelex.cogt.llm.llm_job_factory import LLMJobFactory
from pipelex.cogt.llm.llm_prompt import LLMPrompt
from pipelex.service_hub import get_llm_worker, get_model_deck
from pipelex.system.job_metadata import JobMetadata
from tests.integration.pipelex.cogt.test_data import LLMTestCases
from tests.integration.pipelex.fixtures.model_combo import ModelCombo


def get_async_worker_and_job(llm_preset_id: str, user_text: str, job_metadata: JobMetadata):
    llm_setting = get_model_deck().get_llm_setting(llm_choice=llm_preset_id)
    pretty_print(llm_setting, title=llm_preset_id)
    pretty_print(user_text)
    llm_worker = get_llm_worker(llm_handle=llm_setting.model)
    llm_job_params = llm_setting.make_llm_job_params()
    llm_job = LLMJobFactory.make_llm_job(
        llm_prompt=LLMPrompt(
            user_text=user_text,
        ),
        job_metadata=job_metadata,
        llm_job_params=llm_job_params,
        llm_job_config=LLMJobConfig(
            schema_reask_max_attempts=3,
        ),
    )
    return llm_worker, llm_job


@pytest.mark.llm
@pytest.mark.inference
@pytest.mark.asyncio(loop_scope="class")
class TestLLMGenObject:
    @pytest.mark.parametrize(("user_text", "expected_instance"), LLMTestCases.SINGLE_OBJECT)
    async def test_gen_object_async_using_handle(
        self,
        job_metadata: JobMetadata,
        llm_job_params: LLMJobParams,
        llm_combo: ModelCombo,
        user_text: str,
        expected_instance: BaseModel,
    ):
        llm_worker = get_llm_worker(llm_handle=llm_combo.handle)
        if not llm_worker.is_gen_object_supported:
            pytest.skip(f"LLM worker '{llm_worker.desc}' does not support object generation")
        llm_job = LLMJobFactory.make_llm_job(
            llm_prompt=LLMPrompt(
                user_text=user_text,
            ),
            job_metadata=job_metadata,
            llm_job_params=llm_job_params,
            llm_job_config=LLMJobConfig(
                schema_reask_max_attempts=3,
            ),
        )
        expected_class = expected_instance.__class__
        output = await llm_worker.gen_object(llm_job=llm_job, schema=expected_class)
        pretty_print(output, title=f"Output from {llm_combo.handle}")
        assert isinstance(output, expected_class)
        assert output.model_dump(serialize_as_any=True) == expected_instance.model_dump(serialize_as_any=True)

    @pytest.mark.parametrize(("user_text", "expected_instance"), LLMTestCases.SINGLE_OBJECT)
    async def test_gen_object_async_using_llm_preset(
        self, job_metadata: JobMetadata, llm_preset_id: str, user_text: str, expected_instance: BaseModel
    ):
        llm_worker, llm_job = get_async_worker_and_job(llm_preset_id=llm_preset_id, user_text=user_text, job_metadata=job_metadata)
        if not llm_worker.is_gen_object_supported:
            pytest.skip(f"'{llm_worker.desc}' does not support object generation")
        expected_class = expected_instance.__class__
        output = await llm_worker.gen_object(llm_job=llm_job, schema=expected_class)
        pretty_print(output, title=f"Output from {llm_preset_id}")
        assert isinstance(output, expected_class)
        assert output.model_dump(serialize_as_any=True) == expected_instance.model_dump(serialize_as_any=True)

    @pytest.mark.parametrize("case_tuples", LLMTestCases.MULTIPLE_OBJECTS)
    async def test_gen_object_async_multiple_using_handle(
        self,
        job_metadata: JobMetadata,
        llm_job_params: LLMJobParams,
        llm_combo: ModelCombo,
        case_tuples: list[tuple[str, BaseModel]],
    ):
        llm_worker = get_llm_worker(llm_handle=llm_combo.handle)
        if not llm_worker.is_gen_object_supported:
            pytest.skip(f"'{llm_worker.desc}' does not support object generation")
        tasks: list[asyncio.Task[BaseModel]] = []
        for case_tuple in case_tuples:
            user_text, expected_instance = case_tuple
            expected_class = expected_instance.__class__
            llm_job = LLMJobFactory.make_llm_job(
                llm_prompt=LLMPrompt(
                    user_text=user_text,
                ),
                job_metadata=job_metadata,
                llm_job_params=llm_job_params,
                llm_job_config=LLMJobConfig(
                    schema_reask_max_attempts=3,
                ),
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
    async def test_gen_object_async_multiple_using_llm_preset(
        self, job_metadata: JobMetadata, llm_preset_id: str, case_tuples: list[tuple[str, BaseModel]]
    ):
        llm_worker, llm_job = get_async_worker_and_job(llm_preset_id=llm_preset_id, user_text=case_tuples[0][0], job_metadata=job_metadata)
        if not llm_worker.is_gen_object_supported:
            pytest.skip(f"'{llm_worker.desc}' does not support object generation")
        tasks: list[asyncio.Task[BaseModel]] = []
        for case_tuple in case_tuples:
            user_text, expected_instance = case_tuple
            expected_class = expected_instance.__class__
            llm_job = LLMJobFactory.make_llm_job(
                llm_prompt=LLMPrompt(
                    user_text=user_text,
                ),
                job_metadata=job_metadata,
                llm_job_params=llm_job.job_params,
                llm_job_config=LLMJobConfig(
                    schema_reask_max_attempts=3,
                ),
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
