from typing import Any, Optional, Type

from typing_extensions import override

from pipelex import log
from pipelex.cogt.exceptions import LLMCapabilityError, LLMEngineParameterError, SdkTypeError
from pipelex.cogt.inference.inference_report_delegate import InferenceReportDelegate
from pipelex.cogt.llm.llm_job import LLMJob
from pipelex.cogt.llm.llm_job_func import llm_job_func
from pipelex.cogt.llm.llm_models.llm_engine import LLMEngine
from pipelex.cogt.llm.llm_worker_abstract import LLMWorkerAbstract
from pipelex.cogt.llm.structured_output import StructureMethod
from pipelex.plugins.bedrock.bedrock_client_protocol import BedrockClientProtocol
from pipelex.plugins.bedrock.bedrock_factory import BedrockFactory
from pipelex.tools.typing.pydantic_utils import BaseModelTypeVar


class BedrockLLMWorker(LLMWorkerAbstract):
    def __init__(
        self,
        sdk_instance: Any,
        llm_engine: LLMEngine,
        structure_method: Optional[StructureMethod] = None,
        report_delegate: Optional[InferenceReportDelegate] = None,
    ):
        LLMWorkerAbstract.__init__(
            self,
            llm_engine=llm_engine,
            structure_method=structure_method,
            report_delegate=report_delegate,
        )

        if not isinstance(sdk_instance, BedrockClientProtocol):
            raise SdkTypeError(
                f"Provided sdk_instance for {self.__class__.__name__} is not of type BedrockClientProtocol: it's a '{type(sdk_instance)}'"
            )

        if default_max_tokens := llm_engine.llm_model.max_tokens:
            self.default_max_tokens = default_max_tokens
        else:
            raise LLMEngineParameterError(f"No max_tokens provided for llm model '{self.llm_engine.llm_model.desc}', but it is required for Bedrock")
        self.bedrock_client_for_text = sdk_instance

    @override
    @llm_job_func
    async def gen_text(
        self,
        llm_job: LLMJob,
    ) -> str:
        message = BedrockFactory.make_simple_message(llm_job=llm_job)

        log.debug(self.llm_engine.llm_id)

        bedrock_response_text, nb_tokens_by_category = await self.bedrock_client_for_text.chat(
            messages=message.to_dict_list(),
            system_text=llm_job.llm_prompt.system_text,
            model=self.llm_engine.llm_id,
            temperature=llm_job.job_params.temperature,
            max_tokens=llm_job.job_params.max_tokens or self.default_max_tokens,
        )
        if (llm_tokens_usage := llm_job.job_report.llm_tokens_usage) and nb_tokens_by_category:
            llm_tokens_usage.nb_tokens_by_category = nb_tokens_by_category
        return bedrock_response_text

    @override
    @llm_job_func
    async def gen_object(
        self,
        llm_job: LLMJob,
        schema: Type[BaseModelTypeVar],
    ) -> BaseModelTypeVar:
        # TODO: try with the newest instructor release
        raise LLMCapabilityError(f"It is not possible to generate objects with a {self.__class__.__name__}.")
