from typing import Any, Optional, Type

import instructor
import openai
from openai import NOT_GIVEN, APIConnectionError, BadRequestError, NotFoundError
from openai.types.chat import ChatCompletionMessage
from typing_extensions import override

from pipelex import log
from pipelex.cogt.exceptions import LLMCompletionError, LLMEngineParameterError, LLMModelNotFoundError, SdkTypeError
from pipelex.cogt.llm.llm_job import LLMJob
from pipelex.cogt.llm.llm_models.llm_engine import LLMEngine
from pipelex.cogt.llm.llm_models.llm_family import LLMFamily
from pipelex.cogt.llm.llm_worker_abstract import LLMWorkerAbstract
from pipelex.cogt.llm.structured_output import StructureMethod
from pipelex.cogt.llm.token_category import NbTokensByCategoryDict, TokenCategory
from pipelex.plugins.openai.openai_factory import OpenAIFactory
from pipelex.reporting.reporting_protocol import ReportingProtocol
from pipelex.tools.typing.pydantic_utils import BaseModelTypeVar


class TemplateLLMWorker(LLMWorkerAbstract):
    # def __init__(
    #     self,
    #     llm_engine: LLMEngine,
    #     reporting_delegate: Optional[ReportingProtocol] = None,
    # ):
    #     super().__init__(llm_engine=llm_engine, structure_method=None, reporting_delegate=reporting_delegate)

    #########################################################

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
        raise NotImplementedError()
