from typing import Type

from polyfactory.factories.pydantic_factory import ModelFactory
from typing_extensions import override

from pipelex.cogt.llm.llm_job import LLMJob
from pipelex.cogt.llm.llm_worker_abstract import LLMWorkerAbstract
from pipelex.cogt.llm.token_category import NbTokensByCategoryDict, TokenCategory
from pipelex.tools.typing.pydantic_utils import BaseModelTypeVar


class TemplateLLMWorker(LLMWorkerAbstract):
    @override
    async def _gen_text(
        self,
        llm_job: LLMJob,
    ) -> str:
        response_text = "This is a mock LLM response"

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
