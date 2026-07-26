import asyncio

import pytest

from pipelex import log, pretty_print
from pipelex.cogt.llm.llm_job import LLMJob
from pipelex.cogt.llm.llm_job_components import LLMJobConfig, LLMJobParams
from pipelex.cogt.llm.llm_job_factory import LLMJobFactory
from pipelex.cogt.llm.llm_prompt import LLMPrompt
from pipelex.cogt.llm.llm_worker_abstract import LLMWorkerAbstract
from pipelex.cogt.model_backends.constraints import ListedConstraint, ValuedConstraint
from pipelex.runtime_hub import get_llm_worker, get_model_deck
from pipelex.system.job_metadata import JobMetadata
from tests.integration.pipelex.cogt.test_data import LLMTestCases
from tests.integration.pipelex.fixtures.model_combo import ModelCombo


def get_worker_and_job(llm_preset_id: str, user_text: str, job_metadata: JobMetadata) -> tuple[LLMWorkerAbstract, LLMJob]:
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
class TestLLMGenText:
    @pytest.mark.parametrize(("topic", "prompt_text"), LLMTestCases.SINGLE_TEXT)
    async def test_gen_text_using_handle(
        self,
        job_metadata: JobMetadata,
        llm_job_params: LLMJobParams,
        llm_combo: ModelCombo,
        topic: str,
        prompt_text: str,
    ):
        pretty_print(prompt_text, title=f"Generating text about '{topic}' using '{llm_combo.handle}'")
        llm_worker = get_llm_worker(llm_handle=llm_combo.handle)
        llm_job = LLMJobFactory.make_llm_job(
            llm_prompt=LLMPrompt(
                user_text=prompt_text,
            ),
            job_metadata=job_metadata,
            llm_job_params=llm_job_params,
            llm_job_config=LLMJobConfig(
                schema_reask_max_attempts=3,
            ),
        )
        generated_text = await llm_worker.gen_text(llm_job=llm_job)
        assert generated_text
        pretty_print(generated_text)

    @pytest.mark.parametrize(("topic", "prompt_text"), LLMTestCases.SINGLE_TEXT)
    async def test_gen_text_using_llm_preset(self, job_metadata: JobMetadata, llm_preset_id: str, topic: str, prompt_text: str):  # noqa: ARG002
        llm_worker, llm_job = get_worker_and_job(llm_preset_id=llm_preset_id, user_text=prompt_text, job_metadata=job_metadata)
        generated_text = await llm_worker.gen_text(llm_job=llm_job)
        assert generated_text
        pretty_print(generated_text)

    @pytest.mark.parametrize(("topic", "prompt_text"), LLMTestCases.SINGLE_TEXT)
    async def test_gen_text_multiple_using_llm_preset(self, job_metadata: JobMetadata, llm_preset_id: str, topic: str, prompt_text: str):  # noqa: ARG002
        llm_worker, llm_job = get_worker_and_job(llm_preset_id=llm_preset_id, user_text=prompt_text, job_metadata=job_metadata)
        job_params_base = llm_job.job_params
        max_tokens = 30
        temperature = 0.1
        tasks: list[asyncio.Task[str]] = []
        for _ in range(4):
            max_tokens += 50
            temperature += 0.2
            if temperature > 1:
                break
            llm_job.job_params = job_params_base.model_copy(update={"max_tokens": max_tokens, "temperature": temperature})
            fixed_temp = llm_worker.inference_model.valued_constraints.get(ValuedConstraint.FIXED_TEMPERATURE)
            if fixed_temp is not None:
                log.warning(f"ValuedConstraint FIXED_TEMPERATURE={fixed_temp}, forcing temperature")
                llm_job.job_params = job_params_base.model_copy(update={"temperature": fixed_temp})
            if ListedConstraint.MAX_TOKENS_MUST_BE_HIGH_ENOUGH in llm_worker.inference_model.listed_constraints:
                log.warning("ListedConstraint MAX_TOKENS_MUST_BE_HIGH_ENOUGH, forcing max tokens to at least2000")
                completion_max_tokens = max(max_tokens, 2000)
                llm_job.job_params = job_params_base.model_copy(update={"max_tokens": completion_max_tokens})
            task: asyncio.Task[str] = asyncio.create_task(llm_worker.gen_text(llm_job=llm_job))
            tasks.append(task)

        generated_texts = await asyncio.gather(*tasks)
        for generated_text in generated_texts:
            assert generated_text
            pretty_print(generated_text)
