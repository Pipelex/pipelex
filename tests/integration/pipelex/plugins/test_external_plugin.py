import pytest
from polyfactory.factories.pydantic_factory import ModelFactory
from typing_extensions import override

from pipelex import log, pretty_print
from pipelex.cogt.llm.llm_job import LLMJob
from pipelex.cogt.llm.llm_job_components import LLMJobParams
from pipelex.cogt.llm.llm_job_factory import LLMJobFactory
from pipelex.cogt.llm.llm_prompt import LLMPrompt
from pipelex.cogt.llm.llm_setting import LLMSetting
from pipelex.cogt.llm.llm_worker_abstract import LLMWorkerAbstract
from pipelex.cogt.usage.token_category import NbTokensByCategoryDict, TokenCategory
from pipelex.core.concepts.concept_native import NativeConceptCode
from pipelex.hub import get_inference_manager, get_pipe_router, get_report_delegate
from pipelex.pipe_operators.llm.pipe_llm_blueprint import PipeLLMBlueprint
from pipelex.pipe_operators.llm.pipe_llm_factory import PipeLLMFactory
from pipelex.pipe_run.pipe_job_factory import PipeJobFactory
from pipelex.tools.typing.pydantic_utils import BaseModelTypeVar
from tests.integration.pipelex.cogt.test_data import LLMTestConstants, Person
from tests.integration.pipelex.test_data import PipeTestCases

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
    async def test_external_llm_worker(self):
        llm_worker = MockExternalLLMWorker(reporting_delegate=get_report_delegate())
        llm_job = LLMJobFactory.make_llm_job(
            llm_prompt=LLMPrompt(
                system_text=None,
                user_text=LLMTestConstants.USER_TEXT_SHORT,
            ),
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
        llm_handle = EXTERNAL_PLUGIN_NAME
        get_inference_manager().set_llm_worker_from_external_plugin(
            llm_handle=llm_handle,
            llm_worker_class=MockExternalLLMWorker,
        )

        pipe_llm_blueprint = PipeLLMBlueprint(
            description="LLM test with external plugin",
            output=NativeConceptCode.TEXT,
            system_prompt=PipeTestCases.SYSTEM_PROMPT,
            prompt=PipeTestCases.USER_PROMPT,
            model=LLMSetting(
                model=llm_handle,
                temperature=0.5,
                max_tokens=None,
            ),
        )

        pipe_job = PipeJobFactory.make_pipe_job(
            pipe=PipeLLMFactory.make_from_blueprint(
                domain="generic",
                pipe_code="adhoc_for_test_pipe_llm_with_external_llm_handle",
                blueprint=pipe_llm_blueprint,
            ),
        )
        pipe_llm_output = await get_pipe_router().run(
            pipe_job=pipe_job,
        )

        log.verbose(pipe_llm_output, title="stuff")
        llm_generated_text = pipe_llm_output.main_stuff_as_text
        pretty_print(llm_generated_text, title="llm_generated_text")
