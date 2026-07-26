from typing import Callable

import pytest
from polyfactory.factories.pydantic_factory import ModelFactory
from typing_extensions import override

from pipelex import pretty_print
from pipelex.cogt.llm.llm_job import LLMJob
from pipelex.cogt.llm.llm_job_components import LLMJobParams
from pipelex.cogt.llm.llm_job_factory import LLMJobFactory
from pipelex.cogt.llm.llm_prompt import LLMPrompt
from pipelex.cogt.llm.llm_worker_abstract import LLMWorkerAbstract
from pipelex.cogt.llm.thinking_mode import ThinkingMode
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.cogt.model_backends.model_type import ModelType
from pipelex.cogt.usage.token_category import NbTokensByCategoryDict, TokenCategory
from pipelex.pipeline.job_metadata import JobMetadata
from pipelex.service_hub import get_report_delegate
from pipelex.tools.typing.pydantic_utils import BaseModelTypeVar
from tests.integration.pipelex.cogt.test_data import LLMTestConstants, Person

EXTERNAL_MODEL_NAME = "mock_external_llm"


def _make_mock_inference_model() -> InferenceModelSpec:
    return InferenceModelSpec(
        backend_name="mock_backend",
        name=EXTERNAL_MODEL_NAME,
        sdk="mock_sdk",
        model_type=ModelType.LLM,
        model_id="mock-external-llm-1",
        inputs=["text", "images"],
        outputs=["text", "structured"],
        costs={},
        thinking_mode=ThinkingMode.NONE,
        max_tokens=None,
        max_prompt_images=None,
    )


class MockExternalLLMWorker(LLMWorkerAbstract):
    @property
    @override
    def is_gen_object_supported(self) -> bool:
        return True

    @property
    @override
    def is_vision_supported(self) -> bool:
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
        *,
        schema: type[BaseModelTypeVar],
    ) -> BaseModelTypeVar:
        class ObjectFactory(ModelFactory[schema]):  # type: ignore[valid-type]
            __model__ = schema
            __check_model__ = True
            __use_examples__ = True
            __allow_none_optionals__ = False  # Ensure Optional fields always get values

        return ObjectFactory.build()


@pytest.mark.asyncio(loop_scope="class")
class TestExternalPlugin:
    async def test_external_llm_worker(self, job_metadata: JobMetadata, load_empty_library: Callable[[], None]):
        """An out-of-tree LLMWorkerAbstract subclass runs the full gen_text/gen_object template with just the two _gen impls."""
        load_empty_library()
        llm_worker = MockExternalLLMWorker(
            inference_model=_make_mock_inference_model(),
            reporting_delegate=get_report_delegate(),
        )
        llm_job = LLMJobFactory.make_llm_job(
            llm_prompt=LLMPrompt(
                system_text=None,
                user_text=LLMTestConstants.USER_TEXT_SHORT,
            ),
            job_metadata=job_metadata,
            llm_job_params=LLMJobParams(
                temperature=0.5,
                max_tokens=None,
                image_detail=None,
                seed=None,
            ),
        )
        generated_text = await llm_worker.gen_text(llm_job=llm_job)
        assert generated_text
        pretty_print(generated_text)
        generated_object = await llm_worker.gen_object(llm_job=llm_job, schema=Person)
        assert generated_object
        pretty_print(generated_object)
